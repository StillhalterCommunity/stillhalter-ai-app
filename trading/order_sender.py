"""
Zentraler IBKR-Order-Sender über die lokale TWS-Bridge (bridge.py).

Konzept: Die App läuft in der Cloud (Railway) und kann TWS auf Olivers Mac
nicht direkt erreichen. bridge.py läuft lokal, öffnet einen HTTPS-Tunnel und
leitet Orders an TWS weiter (transmit=False → "Held"/pausiert; Freigabe
["aktiv"] erfolgt später manuell in TWS).

Dieser Helfer macht die Bridge app-weit nutzbar (Scanner, Trade Monitor,
Order-Planung): Bridge-URL persistent im Volume (überlebt Deploys & Sessions),
Status-Check und Ein-Klick-Order-Versand.
"""

from __future__ import annotations

import requests

from data import _persistent_cache as _dc

_KEY      = "ibkr_bridge_url"
_API_KEY  = "stillhalter-bridge"


def save_bridge_url(url: str) -> None:
    """Bridge-URL persistent speichern (Volume, praktisch unbegrenzt gültig)."""
    _dc.save(_KEY, (url or "").strip().rstrip("/"), ttl_hours=24 * 365)


def load_bridge_url() -> str:
    """Zuletzt gespeicherte Bridge-URL (oder '')."""
    try:
        return (_dc.load_latest(_KEY) or "").strip()
    except Exception:
        return ""


def bridge_status(url: str | None = None) -> tuple[bool, str]:
    """Prüft, ob Bridge + TWS erreichbar sind.
    Rückgabe: (ok, url_bzw_fehlermeldung)."""
    u = (url or load_bridge_url()).strip().rstrip("/")
    if not u:
        return False, "Keine Bridge-URL gespeichert — Seite 14 → 🔌 TWS Verbindung"
    try:
        r = requests.get(f"{u}/ping", timeout=4,
                         headers={"Accept": "application/json"})
        d = r.json()
        if d.get("tws"):
            return True, u
        return False, "Bridge erreichbar, aber TWS antwortet nicht (TWS starten, Port 7497)"
    except Exception as e:
        return False, f"Bridge nicht erreichbar: {e}"


def send_short_option(
    ticker: str,
    right: str,               # "P" | "C"
    strike: float,
    expiration: str,          # "YYYY-MM-DD" oder "YYYYMMDD"
    limit_price: float,
    quantity: int = 1,
    url: str | None = None,
) -> tuple[bool, str]:
    """Platziert eine Short-Options-Order (SELL, Limit, Held) via Bridge.
    Rückgabe: (ok, beschreibung_oder_fehler)."""
    ok, u = bridge_status(url)
    if not ok:
        return False, u
    exp = str(expiration).replace("-", "")[:8]
    if len(exp) != 8 or not exp.isdigit():
        return False, f"Ungültiges Verfallsdatum: {expiration!r}"
    payload = {
        "ticker":      (ticker or "").upper(),
        "expiration":  exp,
        "strike":      float(strike),
        "right":       "C" if str(right).upper().startswith("C") else "P",
        "action":      "SELL",
        "quantity":    int(quantity),
        "limit_price": round(float(limit_price), 2),
        "order_type":  "LMT",
    }
    try:
        r = requests.post(f"{u}/order", json=payload,
                          headers={"X-API-Key": _API_KEY}, timeout=20)
        data = r.json()
        if r.status_code == 200 and not data.get("error"):
            oid = data.get("order_id", "?")
            return True, (f"Held-Order platziert: SELL {payload['quantity']}x "
                          f"{payload['ticker']} {payload['strike']:g}{payload['right']} "
                          f"{exp} @ ${payload['limit_price']:.2f} · Order-ID {oid} "
                          f"→ Freigabe in TWS")
        return False, str(data.get("error") or f"HTTP {r.status_code}: {r.text[:200]}")
    except Exception as e:
        return False, f"Bridge-Fehler: {e}"
