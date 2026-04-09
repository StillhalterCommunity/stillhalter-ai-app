"""
Stillhalter AI App — Hintergrund-Preloader
Lädt alle Watchlist-Ticker im Hintergrund vor (parallel, 8 Threads).
Auto-Update alle 15 Minuten. Überlebt Seitenwechsel (Modul-Level State).
"""

import threading
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Modul-Level State ─────────────────────────────────────────────────────────
_lock = threading.Lock()

_state = {
    "running":      False,
    "progress":     0.0,
    "done":         0,
    "total":        0,
    "last_update":  None,   # datetime des letzten vollständigen Loads
    "started_at":   None,
}

_UPDATE_INTERVAL = 15 * 60   # 15 Minuten in Sekunden
_WORKERS = 8


def get_state() -> dict:
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return _state["running"]


def needs_update() -> bool:
    """True wenn noch nie geladen oder älter als 15 Minuten."""
    with _lock:
        if _state["running"]:
            return False
        last = _state["last_update"]
        if last is None:
            return True
        return (datetime.now() - last).total_seconds() > _UPDATE_INTERVAL


def start_preload(tickers: list) -> bool:
    """
    Startet den Hintergrund-Preload falls nötig.
    Gibt False zurück wenn bereits läuft.
    """
    with _lock:
        if _state["running"]:
            return False
        _state.update({
            "running":    True,
            "progress":   0.0,
            "done":       0,
            "total":      len(tickers),
            "started_at": datetime.now(),
        })

    thread = threading.Thread(
        target=_preload_worker,
        args=(tickers,),
        daemon=True,
        name="StillhalterPreloader",
    )
    thread.start()
    return True


def _fetch_one(ticker: str) -> None:
    """Lädt Kursdaten + Basisinfo für einen Ticker (Fehler werden ignoriert)."""
    try:
        from data.fetcher import fetch_price_history, fetch_stock_info
        fetch_price_history(ticker, period="1y")
        fetch_stock_info(ticker)
    except Exception:
        pass


def _preload_worker(tickers: list) -> None:
    """Paralleler Worker: lädt alle Ticker mit 8 Threads gleichzeitig."""
    total = len(tickers)
    done = 0

    with ThreadPoolExecutor(max_workers=_WORKERS, thread_name_prefix="preload") as ex:
        futures = {ex.submit(_fetch_one, t): t for t in tickers}
        for future in as_completed(futures):
            done += 1
            with _lock:
                _state["done"]     = done
                _state["progress"] = done / max(total, 1)
            # Kein sleep nötig — ThreadPoolExecutor regelt das

    with _lock:
        _state["running"]     = False
        _state["progress"]    = 1.0
        _state["done"]        = total
        _state["last_update"] = datetime.now()
