"""
Stillhalter AI — Signal-Pipeline Publisher

A2: WhatsApp-Kanal via Wassenger oder Whapi.Cloud  (gewählter Weg)
    ⚠️  Verstößt gegen Meta ToS — nur für Gratis-Teaser / Marketing verwenden!
    Für zahlende Mitglieder: Publisher A1 (Meta Cloud API) separat nachrüsten.

B:  Circle Admin API v2

Secrets NIEMALS im Code — aus ENV / .streamlit/secrets.toml laden.
"""
from __future__ import annotations

import os
from typing import Optional

import requests

# ── ENV-Helper ────────────────────────────────────────────────────────────────

def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLISHER A2 — WhatsApp-Kanal (Wassenger / Whapi.Cloud)
# ═══════════════════════════════════════════════════════════════════════════════

class WhatsAppPublisher:
    """
    Sendet Text in einen WhatsApp-Kanal via Wassenger oder Whapi.Cloud.

    Konfiguration (ENV / Streamlit Secrets):
        WHATSAPP_API_KEY    = API-Token des Anbieters
        WHATSAPP_CHANNEL_ID = Kanal-ID oder Telefon@newsletter
        WHATSAPP_PROVIDER   = "wassenger" | "whapi"  (Default: wassenger)
    """

    def __init__(
        self,
        api_key:    Optional[str] = None,
        channel_id: Optional[str] = None,
        provider:   str           = "wassenger",
    ):
        self.api_key    = api_key    or _env("WHATSAPP_API_KEY")
        self.channel_id = channel_id or _env("WHATSAPP_CHANNEL_ID")
        self.provider   = provider   or _env("WHATSAPP_PROVIDER", "wassenger")

    def _check_config(self) -> None:
        if not self.api_key or not self.channel_id:
            raise ValueError(
                "WHATSAPP_API_KEY und WHATSAPP_CHANNEL_ID müssen gesetzt sein "
                "(ENV-Variablen oder .streamlit/secrets.toml)."
            )

    def publish(self, text: str) -> dict:
        """Sendet Text in den Kanal. Gibt die API-Response zurück."""
        self._check_config()
        if self.provider == "whapi":
            return self._publish_whapi(text)
        return self._publish_wassenger(text)

    def _publish_wassenger(self, text: str) -> dict:
        """Wassenger API — https://app.wassenger.com/docs"""
        r = requests.post(
            "https://api.wassenger.com/v1/messages",
            json={"phone": self.channel_id, "message": text},
            headers={"Token": self.api_key, "Content-Type": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        return r.json()

    def _publish_whapi(self, text: str) -> dict:
        """Whapi.Cloud API — https://whapi.cloud/docs"""
        r = requests.post(
            f"https://gate.whapi.cloud/channels/{self.channel_id}/messages/text",
            json={"body": text},
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        r.raise_for_status()
        return r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# PUBLISHER B — Circle Admin API v2
# ═══════════════════════════════════════════════════════════════════════════════

class CirclePublisher:
    """
    Erstellt Posts in Circle via Admin API v2 (Business/Enterprise Plan).

    Konfiguration (ENV / Streamlit Secrets):
        CIRCLE_API_TOKEN        = Admin API-Token
        CIRCLE_SPACE_DAILY      = Space-ID für 79€-Tier
        CIRCLE_SPACE_MASTERCLASS = Space-ID für Masterclass
        CIRCLE_SPACE_VIP        = Space-ID für VIP

    Reihenfolge der Pipeline: erst Circle posten → URL holen → WhatsApp senden.
    """

    def __init__(
        self,
        token:     Optional[str]  = None,
        space_ids: Optional[dict] = None,
    ):
        self.token = token or _env("CIRCLE_API_TOKEN")
        self.space_ids = space_ids or {
            "daily":        int(_env("CIRCLE_SPACE_DAILY",        "0") or 0),
            "masterclass":  int(_env("CIRCLE_SPACE_MASTERCLASS",  "0") or 0),
            "vip":          int(_env("CIRCLE_SPACE_VIP",          "0") or 0),
        }

    def _headers(self) -> dict:
        if not self.token:
            raise ValueError(
                "CIRCLE_API_TOKEN muss gesetzt sein "
                "(ENV-Variablen oder .streamlit/secrets.toml)."
            )
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def create_post(self, tier: str, title: str, html: str) -> str:
        """
        Erstellt einen Post im Space des angegebenen Tiers.
        tier: "daily" | "masterclass" | "vip"
        Gibt die Post-URL zurück.

        ⚠️ Endpunkt und Payload-Schema gegen aktuelle api.circle.so-Doku prüfen!
        """
        space_id = self.space_ids.get(tier, 0)
        if not space_id:
            raise ValueError(
                f"Space-ID für Tier '{tier}' nicht konfiguriert. "
                f"CIRCLE_SPACE_{tier.upper()} setzen."
            )

        payload = {
            "space_id":  space_id,
            "name":      title,
            "body":      {"html": html},
            "published": True,
        }
        r = requests.post(
            "https://app.circle.so/api/admin/v2/posts",
            json=payload,
            headers=self._headers(),
            timeout=20,
        )
        r.raise_for_status()
        data = r.json()
        # URL kann je nach API-Version unter verschiedenen Keys stehen
        return data.get("url") or data.get("post_url") or data.get("public_url") or ""

    def create_for_card(self, rendered: dict, visibility: dict) -> dict:
        """
        Erstellt Posts in allen sichtbaren Spaces einer TradeCard.

        rendered:   {"title": str, "html": str}  — Ausgabe von render_circle()
        visibility: {"daily": bool, "masterclass": bool, "vip": bool}
        Gibt {"daily": url, "masterclass": url, "vip": url} zurück.
        """
        urls: dict = {}
        title = rendered["title"]
        html  = rendered["html"]
        for tier in ("daily", "masterclass", "vip"):
            if visibility.get(tier):
                try:
                    urls[tier] = self.create_post(tier, title, html)
                except Exception as exc:
                    urls[tier] = f"ERROR: {exc}"
        return urls
