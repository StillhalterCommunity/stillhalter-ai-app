"""
Stillhalter AI App — Hintergrund-Scan Engine
Läuft in einem separaten Thread auf Modul-Level → überlebt Seitenwechsel.

Wichtig: Streamlit's Session State lebt nur innerhalb einer Sitzung/Seite.
Modul-Level-Variablen in Python leben so lange wie der Server-Prozess läuft.
Dadurch überlebt der Scan alle st.rerun() und Seitenwechsel.

ACHTUNG — geteilter Zustand: `_state` ist prozess-global, also über ALLE
Nutzer/Sessions geteilt. Damit ein abgebrochener oder toter Scan niemanden
dauerhaft blockiert, gibt es:
  • Selbstheilung: ein 'running'-Zustand, der älter als _MAX_RUNTIME_S ist,
    wird automatisch als tot zurückgesetzt.
  • Run-ID: jeder Start bekommt eine ID. Ein gestoppter/alter Worker, dessen
    ID nicht mehr aktuell ist, schreibt NICHTS mehr in den Zustand
    (verhindert Überschreiben eines frischen Scans durch einen Zombie-Thread).
"""

import threading
import pickle
import os
from datetime import datetime
import pandas as pd

# ── Modul-Level State (überlebt Seitenwechsel!) ──────────────────────────────
_lock = threading.Lock()
_MAX_RUNTIME_S = 600          # 10 Min — länger kann kein Scan dauern → gilt als tot
_run_id = 0                   # erhöht sich bei Start/Stop/Reset

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

def _scan_cache_path() -> str:
    """Persistenter Pfad (Volume) für das letzte Scan-Ergebnis."""
    try:
        from data._persistent_cache import scan_cache_path
        return scan_cache_path()
    except Exception:
        return os.path.join(os.path.dirname(__file__), "last_scan_cache.pkl")


_CACHE_PATH = _scan_cache_path()


def _maybe_expire_locked() -> None:
    """Setzt einen zu alten 'running'-Zustand zurück (verwaister/toter Scan).
    MUSS innerhalb von _lock aufgerufen werden."""
    if _state["running"] and _state["started_at"]:
        age = (datetime.now() - _state["started_at"]).total_seconds()
        if age > _MAX_RUNTIME_S:
            _state["running"] = False
            _state["progress"] = 0.0
            _state["current"] = ""
            _state["error"] = "Scan-Timeout — automatisch zurückgesetzt"


def get_state() -> dict:
    """Gibt eine Kopie des aktuellen Scan-Status zurück (thread-safe, self-healing)."""
    with _lock:
        _maybe_expire_locked()
        return dict(_state)


def is_running() -> bool:
    with _lock:
        _maybe_expire_locked()
        return _state["running"]


def force_reset() -> None:
    """Harter Reset des Scan-Zustands (für 'Scanner zurücksetzen'-Button).
    Invalidiert auch einen evtl. noch laufenden Zombie-Worker via Run-ID."""
    global _run_id
    with _lock:
        _run_id += 1
        _state.update({
            "running": False, "progress": 0.0, "current": "", "done": 0,
            "total": 0, "error": "", "finished_at": None,
        })


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
    exclude_earnings: bool = False,  # Optionen mit Earnings in Laufzeit ausschließen
) -> bool:
    """
    Startet den Hintergrund-Scan in einem Daemon-Thread.
    Gibt False zurück wenn bereits ein (lebendiger) Scan läuft.
    """
    global _run_id
    with _lock:
        _maybe_expire_locked()          # toten Scan erst freigeben
        if _state["running"]:
            return False
        _run_id += 1
        my_id = _run_id
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
            "tickers": tickers, "strategy": strategy,
            "delta_min": delta_min, "delta_max": delta_max,
            "dte_min": dte_min, "dte_max": dte_max,
            "iv_min": iv_min, "premium_min": premium_min, "min_oi": min_oi,
            "otm_min": otm_min, "otm_max": otm_max,
            "max_spread_pct": max_spread_pct,
            "require_valid_market": require_valid_market,
            "exclude_earnings": exclude_earnings,
            "_my_id": my_id,
        },
        daemon=True,
        name="StillhalterBackgroundScan",
    )
    thread.start()
    return True


def stop_scan() -> None:
    """Bricht den laufenden Scan ab. Invalidiert den Worker via Run-ID, sodass
    er weder Fortschritt noch Endergebnis mehr in den Zustand schreibt."""
    global _run_id
    with _lock:
        _run_id += 1                    # laufender Worker ist ab jetzt ungültig
        _state["running"] = False
        _state["progress"] = 0.0
        _state["current"] = ""
        _state["error"] = "Scan manuell gestoppt"


def _scan_worker(tickers, strategy, delta_min, delta_max, dte_min, dte_max,
                 iv_min, premium_min, min_oi, otm_min, otm_max,
                 max_spread_pct, require_valid_market, exclude_earnings=False,
                 _my_id=0):
    """Läuft im Hintergrund-Thread. Schreibt nur in den Zustand, solange seine
    Run-ID aktuell ist (sonst wurde gestoppt/neu gestartet → Zombie, no-op)."""
    def _current() -> bool:
        return _run_id == _my_id and _state["running"]

    try:
        from analysis.batch_screener import scan_watchlist
        total = len(tickers)

        def on_progress(current: int, total_: int, ticker: str):
            with _lock:
                if not _current():
                    return
                _state["current"]  = ticker
                _state["done"]     = current
                _state["progress"] = current / max(total_, 1)

        def on_result(ticker: str, df: pd.DataFrame):
            with _lock:
                if not _current():
                    return
                existing = _state.get("results")
                if existing is None or existing.empty:
                    _state["results"] = df.copy()
                else:
                    combined = pd.concat([existing, df], ignore_index=True)
                    if "CRV Score" in combined.columns:
                        combined = combined.sort_values("CRV Score", ascending=False)
                    _state["results"] = combined

        results = scan_watchlist(
            tickers=tickers, strategy=strategy,
            delta_min=delta_min, delta_max=delta_max,
            dte_min=dte_min, dte_max=dte_max, iv_min=iv_min,
            premium_min=premium_min, min_oi=min_oi,
            otm_min=otm_min, otm_max=otm_max,
            require_valid_market=require_valid_market,
            max_spread_pct=max_spread_pct, exclude_earnings=exclude_earnings,
            progress_callback=on_progress, result_callback=on_result,
        )

        if not results.empty and "CRV Score" in results.columns:
            results = results.sort_values("CRV Score", ascending=False).reset_index(drop=True)

        # Nur schreiben, wenn dieser Worker noch der aktuelle ist
        with _lock:
            if _run_id != _my_id:
                return   # gestoppt/neu gestartet → nichts überschreiben
            try:
                with open(_CACHE_PATH, "wb") as f:
                    pickle.dump({"results": results, "timestamp": datetime.now(),
                                 "strategy": strategy}, f)
            except Exception:
                pass
            _state["results"]     = results
            _state["progress"]    = 1.0
            _state["done"]        = total
            _state["current"]     = ""
            _state["running"]     = False
            _state["finished_at"] = datetime.now()

    except Exception as e:
        with _lock:
            if _run_id == _my_id:
                _state["running"] = False
                _state["error"]   = str(e)
                _state["finished_at"] = datetime.now()
