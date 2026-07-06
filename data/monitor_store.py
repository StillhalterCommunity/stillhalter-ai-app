"""
Gemeinsamer Speicher für die Trades des Trade Monitors (manual_trades.json).

Eine einzige Quelle für Pfad + Laden/Speichern/Hinzufügen, damit sowohl der
Trade Monitor (Seite 20) als auch die Trade Cards (Seite 17) exakt denselben
Bestand nutzen. Liegt persistent im Volume (STILLHALTER_DATA_DIR), überlebt
also Deploys/Neustarts.
"""

from __future__ import annotations

import os
import json
import hashlib
from datetime import datetime
from typing import List, Optional


def trades_path() -> str:
    base = os.environ.get("STILLHALTER_DATA_DIR", "").strip()
    if base:
        return os.path.join(base, "manual_trades.json")
    return os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "manual_trades.json")


def load_trades() -> List[dict]:
    path = trades_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def save_trades(trades: List[dict]) -> None:
    """ATOMAR schreiben (tmp + os.replace) — schützt vor korrupten Dateien,
    wenn mehrere Nutzer/Sessions gleichzeitig speichern."""
    path = trades_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    except Exception:
        pass
    tmp = f"{path}.tmp.{os.getpid()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(trades, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def new_trade_id(ticker: str, strategy: str = "") -> str:
    """Eindeutige, stabile ID: TICKER-YYYYMMDD-<kurzhash>."""
    t = (ticker or "X").upper()
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    h = hashlib.md5(f"{t}{strategy}{stamp}".encode()).hexdigest()[:6]
    return f"{t}-{datetime.now().strftime('%Y%m%d')}-{h}"


def add_trade(trade: dict) -> bool:
    """Fügt einen Trade hinzu (Dedupe über trade_id).
    Gibt True zurück, wenn neu hinzugefügt; False, wenn die trade_id schon existiert."""
    trades = load_trades()
    tid = trade.get("trade_id")
    if tid and any(t.get("trade_id") == tid for t in trades):
        return False
    trades.insert(0, trade)
    save_trades(trades)
    return True


def make_trade(
    ticker: str,
    strategy: str,
    strike: float,
    expiry: str,
    premium: float,
    *,
    cls: str = "A",
    company: str = "",
    call_strike: float = 0.0,
    call_expiry: str = "",
    delta: float = -0.2,
    iv_pct: float = 25.0,
    price_at_entry: float = 0.0,
    optionstrat_url: str = "",
    status: str = "AKTIV",
) -> dict:
    """Baut ein Trade-Dict im Schema des Trade Monitors."""
    return {
        "trade_id":        new_trade_id(ticker, strategy),
        "class":           cls,
        "ticker":          (ticker or "").upper(),
        "company":         company or (ticker or "").upper(),
        "strategy":        strategy or "Short PUT",
        "strike":          float(strike or 0),
        "call_strike":     float(call_strike or 0),
        "expiry":          expiry or "",
        "call_expiry":     call_expiry or "",
        "premium":         float(premium or 0),
        "delta":           float(delta or 0),
        "iv_pct":          float(iv_pct or 0),
        "price_at_entry":  float(price_at_entry or 0),
        "created_at":      datetime.now().isoformat(timespec="seconds"),
        "post_ts":         datetime.now().strftime("%d.%m.%Y · %H:%M"),
        "optionstrat_url": optionstrat_url or "",
        "tracking_url":    "",
        "status":          status,
        "status_log":      [],
    }
