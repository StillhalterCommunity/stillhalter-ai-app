"""
Stillhalter AI App — Hintergrund-Scan Engine
Läuft in einem separaten Thread auf Modul-Level → überlebt Seitenwechsel.

Wichtig: Streamlit's Session State lebt nur innerhalb einer Sitzung/Seite.
Modul-Level-Variablen in Python leben so lange wie der Server-Prozess läuft.
Dadurch überlebt der Scan alle st.rerun() und Seitenwechsel.
"""

import threading
import time
import pickle
import os
from datetime import datetime
from typing import Optional, Callable
import pandas as pd

# ── Modul-Level State (überlebt Seitenwechsel!) ──────────────────────────────
_lock = threading.Lock()

_state: dict = {
    "running":    False,
    "progress":   0.0,          # 0.0 – 1.0
    "current":    "",           # Ticker der gerade gescannt wird
    "done":       0,            # Anzahl fertig
    "total":      0,            # Gesamt-Ticker
    "results":    None,         # pd.DataFrame mit Ergebnissen
    "strategy":   "",
    "started_at": None,         # datetime
    "finished_at": None,        # datetime
    "error":      "",
}

_CACHE_PATH = os.path.join(os.path.dirname(__file__), "last_scan_cache.pkl")


def get_state() -> dict:
    """Gibt eine Kopie des aktuellen Scan-Status zurück (thread-safe)."""
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return _state["running"]


def start_scan(
    tickers: list,
    strategy: str = "Cash Covered Put",
    delta_min: float = -0.35,
    delta_max: float = -0.05,
    dte_min: int = 14,
    dte_max: int = 60,
    iv_min: float = 0.0,
    premium_min: float = 0.05,
    min_oi: int = 5,
    otm_min: float = 0.0,
    otm_max: float = 30.0,
    max_spread_pct: float = 40.0,
    require_valid_market: bool = True,
) -> bool:
    """
    Startet den Hintergrund-Scan in einem Daemon-Thread.
    Gibt False zurück wenn bereits ein Scan läuft.
    """
    with _lock:
        if _state["running"]:
            return False
        _state.update({
            "running":    True,
            "progress":   0.0,
            "current":    "",
            "done":       0,
            "total":      len(tickers),
            "results":    None,
            "strategy":   strategy,
            "started_at": datetime.now(),
            "finished_at": None,
            "error":      "",
        })

    thread = threading.Thread(
        target=_scan_worker,
        kwargs={
            "tickers": tickers,
            "strategy": strategy,
            "delta_min": delta_min,
            "delta_max": delta_max,
            "dte_min": dte_min,
            "dte_max": dte_max,
            "iv_min": iv_min,
            "premium_min": premium_min,
            "min_oi": min_oi,
            "otm_min": otm_min,
            "otm_max": otm_max,
            "max_spread_pct": max_spread_pct,
            "require_valid_market": require_valid_market,
        },
        daemon=True,   # Daemon = wird beendet wenn Streamlit-Prozess endet
        name="StillhalterBackgroundScan",
    )
    thread.start()
    return True


def stop_scan() -> None:
    """Signalisiert dem Scan-Thread, zu stoppen."""
    with _lock:
        _state["running"] = False
        _state["error"] = "Scan manuell gestoppt"


def _scan_worker(tickers, strategy, delta_min, delta_max, dte_min, dte_max,
                 iv_min, premium_min, min_oi, otm_min, otm_max,
                 max_spread_pct, require_valid_market):
    """
    Läuft im Hintergrund-Thread — nutzt scan_watchlist() mit 8 parallelen Workern,
    identisch zum normalen Scan. Aktualisiert _state laufend via Callbacks.
    """
    try:
        from analysis.batch_screener import scan_watchlist

        total = len(tickers)

        def on_progress(current: int, total_: int, ticker: str):
            with _lock:
                if not _state["running"]:
                    return
                _state["current"]  = ticker
                _state["done"]     = current
                _state["progress"] = current / max(total_, 1)

        def on_result(ticker: str, df: pd.DataFrame):
            # Zwischenergebnis akkumulieren (thread-safe)
            with _lock:
                existing = _state.get("results")
                if existing is None or existing.empty:
                    _state["results"] = df.copy()
                else:
                    combined = pd.concat([existing, df], ignore_index=True)
                    if "CRV Score" in combined.columns:
                        combined = combined.sort_values("CRV Score", ascending=False)
                    _state["results"] = combined

        results = scan_watchlist(
            tickers=tickers,
            strategy=strategy,
            delta_min=delta_min,
            delta_max=delta_max,
            dte_min=dte_min,
            dte_max=dte_max,
            iv_min=iv_min,
            premium_min=premium_min,
            min_oi=min_oi,
            otm_min=otm_min,
            otm_max=otm_max,
            require_valid_market=require_valid_market,
            max_spread_pct=max_spread_pct,
            progress_callback=on_progress,
            result_callback=on_result,
        )

        if not results.empty and "CRV Score" in results.columns:
            results = results.sort_values("CRV Score", ascending=False).reset_index(drop=True)

        # Cache speichern (für Top-9-Seite)
        try:
            with open(_CACHE_PATH, "wb") as f:
                pickle.dump({
                    "results":   results,
                    "timestamp": datetime.now(),
                    "strategy":  strategy,
                }, f)
        except Exception:
            pass

        with _lock:
            _state["results"]     = results
            _state["progress"]    = 1.0
            _state["done"]        = total
            _state["current"]     = ""
            _state["running"]     = False
            _state["finished_at"] = datetime.now()

    except Exception as e:
        with _lock:
            _state["running"] = False
            _state["error"]   = str(e)
            _state["finished_at"] = datetime.now()
