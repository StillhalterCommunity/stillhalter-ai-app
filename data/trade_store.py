"""
Stillhalter AI — Trade Card Datenmodell + JSON-Persistenz
Single Source of Truth für alle Signale (live_ibkr + model).
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, List, Optional

# Persistent im Volume (überlebt Deploys/Neustarts); Fallback: Code-Ordner.
# Migration: existiert nur die alte Datei im Code-Ordner, wird sie einmalig
# ins Volume übernommen.
_DATA_DIR = os.environ.get("STILLHALTER_DATA_DIR", "").strip()
_LEGACY_PATH = os.path.join(os.path.dirname(__file__), "trade_cards.json")
STORE_PATH = (os.path.join(_DATA_DIR, "trade_cards.json") if _DATA_DIR else _LEGACY_PATH)
try:
    if _DATA_DIR and not os.path.exists(STORE_PATH) and os.path.exists(_LEGACY_PATH):
        import shutil as _sh
        _sh.copy2(_LEGACY_PATH, STORE_PATH)
except Exception:
    pass

# ── Dataclasses ───────────────────────────────────────────────────────────────

@dataclass
class SignalComponents:
    iv_rank:     float   # 0–100: Prämienreichtum (Primär-Ranking)
    iv_rv:       float   # IV / Realized Vol (> 1 = teuer)
    trend:       str     # "+" | "0" | "-"
    macd:        str     # "bestätigt" | "neutral" | "gegen"
    earnings:    str     # "clear" | "vor_earnings" | "nach_earnings"
    liquiditaet: str     # "hoch" | "mittel" | "niedrig"


@dataclass
class Expression:
    """Eine Ausdrucksform des Signals, gestaffelt nach Eignung."""
    eignung:        str   # "einsteiger" | "fortgeschritten" | "profi"
    strategy:       str   # "Cash-Secured Put" | "Put Credit Spread" | …
    strike_anchor:  str   # robust: "Short Put unter Support ~405"
    dte:            int
    kapitalbedarf:  str   # "~40.000 $ Collateral" | "max. Risiko ~1.000 $"
    defined_risk:   bool  # False = naked → niemals im offenen Daily-Feed
    optionstrat_url: str
    min_vip:        bool  # True → nur VIP sichtbar
    strikes:        Optional[str] = None   # "400/390"


@dataclass
class ManagementRules:
    take_profit_pct: float   # 0.50 = 50 % Prämienrückgang
    roll_dte:        int     # Rollen ab X verbleibenden Tagen
    roll_delta:      float   # Rollen ab Delta-Schwelle
    warning:         str     # Freitext-Trigger für WARNING
    cancel:          str     # Freitext-Trigger für CANCELLED


@dataclass
class ModelEntry:
    """Eingefrorener Entry-Snapshot für Modell-Trades."""
    ts:                   str
    legs:                 List[dict]   # [{ticker, strike, right, expiry, side}]
    entry_credit:         float        # konservativ gemarkt (mid − 1 Tick)
    underlying_at_entry:  float


@dataclass
class StatusEvent:
    ts:     str
    status: str
    note:   str = ""


@dataclass
class TradeCard:
    trade_id:       str
    ticker:         str
    view:           str   # "bullisch" | "bullisch-neutral" | "neutral" | …
    risk_class:     str   # "defensiv" | "balanced" | "opportunistisch"
    laufzeit:       str   # "1-2T" | "7-21T" | "1-3M" | "1-3J"
    signal_grade:   str   # "A+" | "A" | "A-" | "B+" | "B" | "B-" | "C"
    components:     SignalComponents
    thesis:         str   # 1–2 Sätze "das Warum"
    expressions:    List[Expression]
    management:     ManagementRules
    source:         str   # "live_ibkr" | "model"
    status:         str   # NEU | AKTIV | WATCH | WARNING | ROLL | CLOSE | …
    status_history: List[StatusEvent]
    visibility:     dict  # {"daily": bool, "masterclass": bool, "vip": bool}
    entry:          Optional[ModelEntry] = None
    circle_url:     str   = ""
    tags:           List[str] = field(default_factory=list)
    created_at:     str   = field(default_factory=lambda: datetime.now().isoformat())


# ── Serialisierung ────────────────────────────────────────────────────────────

def _to_dict(obj: Any) -> Any:
    """Rekursive dict-Konvertierung (Dataclasses → plain dict für JSON)."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [_to_dict(i) for i in obj]
    return obj


def _card_from_dict(d: dict) -> TradeCard:
    """Deserialisiert TradeCard aus JSON-dict (mit verschachtelten Dataclasses)."""
    d = dict(d)
    d["components"]     = SignalComponents(**d["components"])
    d["expressions"]    = [Expression(**e) for e in d["expressions"]]
    d["management"]     = ManagementRules(**d["management"])
    d["status_history"] = [StatusEvent(**s) for s in d["status_history"]]
    if d.get("entry"):
        d["entry"] = ModelEntry(**d["entry"])
    # Rückwärtskompatibilität: fehlende Felder mit Default auffüllen
    d.setdefault("circle_url", "")
    d.setdefault("tags", [])
    d.setdefault("created_at", "")
    return TradeCard(**d)


# ── Store ─────────────────────────────────────────────────────────────────────

def _load_raw() -> List[dict]:
    if not os.path.exists(STORE_PATH):
        return []
    try:
        with open(STORE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_raw(cards: List[dict]) -> None:
    # Atomar (tmp + replace) — schützt vor Korruption bei parallelen Nutzern
    _tmp = f"{STORE_PATH}.tmp.{os.getpid()}"
    with open(_tmp, "w", encoding="utf-8") as f:
        json.dump(cards, f, ensure_ascii=False, indent=2)
    os.replace(_tmp, STORE_PATH)


def load_all() -> List[TradeCard]:
    """Lädt alle Trade Cards aus dem JSON-Store."""
    return [_card_from_dict(d) for d in _load_raw()]


def load_open() -> List[TradeCard]:
    """Lädt nur offene Cards (nicht CLOSE / CANCELLED / EXPIRED / REVIEWED)."""
    closed = {"CLOSE", "CANCELLED", "EXPIRED", "REVIEWED"}
    return [c for c in load_all() if c.status not in closed]


def get_by_id(trade_id: str) -> Optional[TradeCard]:
    for d in _load_raw():
        if d.get("trade_id") == trade_id:
            return _card_from_dict(d)
    return None


def upsert(card: TradeCard) -> None:
    """Speichert oder überschreibt eine TradeCard (Match auf trade_id)."""
    raw = [d for d in _load_raw() if d.get("trade_id") != card.trade_id]
    raw.append(_to_dict(card))
    _save_raw(raw)


def delete(trade_id: str) -> None:
    raw = [d for d in _load_raw() if d.get("trade_id") != trade_id]
    _save_raw(raw)


def new_trade_id(ticker: str, strategy_short: str = "CSP") -> str:
    """Generiert eindeutige Trade-ID: TICKER-YYYYMMDD-STRATEGIE-XXXX."""
    date_str = datetime.now().strftime("%Y%m%d")
    uid = uuid.uuid4().hex[:4].upper()
    return f"{ticker}-{date_str}-{strategy_short}-{uid}"
