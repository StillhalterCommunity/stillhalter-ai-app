"""
Stillhalter AI App — Morgen-Prefetch
====================================
Lädt einmal täglich alle wichtigen Daten für das gesamte Ticker-Universum
in den persistenten Disk-Cache. Danach laden Fundamentalanalyse & Co.
sofort aus dem Cache statt live von Yahoo Finance.

Gewärmt werden pro Ticker:
  - Stock-Info (Kurs, Market Cap, Beta, Sektor)
  - Fundamentals (Earnings-Datum, Kennzahlen)
  - Kurshistorie (1 Jahr, für Charts/TA)
  - Value-Daten (Score, KGV, PEG, IV-Proxy — Fundamentalanalyse)

Optionen werden NICHT hier geladen (kommen live von Polygon, unlimited).

Auslösung:
  - Admin-Button im System-Panel (manuell)
  - Automatisch einmal pro Tag beim ersten App-Aufruf (needs_prefetch_today)
"""

from __future__ import annotations

import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from data import _persistent_cache as _dc

_META_KEY = "prefetch_meta"
_WORKERS = 8

# ── Modul-Level State (überlebt Seitenwechsel) ────────────────────────────────
_lock = threading.Lock()
_state = {
    "running":    False,
    "progress":   0.0,
    "done":       0,
    "total":      0,
    "started_at": None,
}


def get_state() -> dict:
    with _lock:
        return dict(_state)


def is_running() -> bool:
    with _lock:
        return _state["running"]


def last_prefetch() -> dict | None:
    """Gibt die Metadaten des letzten Prefetch-Laufs zurück (oder None)."""
    return _dc.load_latest(_META_KEY)


def needs_prefetch_today() -> bool:
    """True wenn heute noch kein erfolgreicher Prefetch gelaufen ist."""
    if is_running():
        return False
    meta = last_prefetch()
    if not meta or "date" not in meta:
        return True
    today = datetime.now().strftime("%Y-%m-%d")
    return meta["date"] != today


def _warm_one(ticker: str) -> dict:
    """Wärmt alle Datenquellen für einen Ticker. Fehler werden geschluckt."""
    ok = {"info": False, "fund": False, "hist": False, "value": False}
    try:
        from data.fetcher import fetch_stock_info, fetch_fundamentals, fetch_price_history
        from data.value_screener import warm_value_data
    except Exception:
        return ok

    try:
        si = fetch_stock_info(ticker)
        ok["info"] = bool(si and si.get("price"))
    except Exception:
        pass
    try:
        fetch_fundamentals(ticker)
        ok["fund"] = True
    except Exception:
        pass
    try:
        df = fetch_price_history(ticker, period="1y")
        ok["hist"] = (df is not None) and (not df.empty)
    except Exception:
        pass
    try:
        ok["value"] = warm_value_data(ticker)
    except Exception:
        pass
    return ok


def _prefetch_worker(tickers: list) -> None:
    total = len(tickers)
    done = 0
    counts = {"info": 0, "fund": 0, "hist": 0, "value": 0}

    try:
        with ThreadPoolExecutor(max_workers=_WORKERS, thread_name_prefix="prefetch") as ex:
            futures = {ex.submit(_warm_one, t): t for t in tickers}
            for future in as_completed(futures):
                done += 1
                try:
                    res = future.result()
                    for k in counts:
                        if res.get(k):
                            counts[k] += 1
                except Exception:
                    pass
                with _lock:
                    _state["done"] = done
                    _state["progress"] = done / max(total, 1)
    finally:
        meta = {
            "date":        datetime.now().strftime("%Y-%m-%d"),
            "finished_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "total":       total,
            "counts":      counts,
        }
        _dc.save(_META_KEY, meta, ttl_hours=72)
        with _lock:
            _state["running"] = False
            _state["progress"] = 1.0
            _state["done"] = total


def start_prefetch(tickers: list | None = None) -> bool:
    """
    Startet den Prefetch im Hintergrund. Gibt False zurück wenn bereits läuft.
    """
    if tickers is None:
        try:
            from data.watchlist import ALL_TICKERS
            tickers = list(ALL_TICKERS)
        except Exception:
            tickers = []

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
        target=_prefetch_worker,
        args=(tickers,),
        daemon=True,
        name="StillhalterPrefetch",
    )
    thread.start()
    return True


def run_prefetch_blocking(tickers: list | None = None) -> dict:
    """
    Führt den Prefetch synchron aus (für CLI / Railway-Cron: `python -m data.prefetch`).
    Gibt die Metadaten zurück.
    """
    if tickers is None:
        from data.watchlist import ALL_TICKERS
        tickers = list(ALL_TICKERS)
    with _lock:
        _state.update({"running": True, "progress": 0.0, "done": 0,
                       "total": len(tickers), "started_at": datetime.now()})
    _prefetch_worker(tickers)
    return last_prefetch() or {}


if __name__ == "__main__":
    print(f"[{datetime.now():%H:%M:%S}] Starte Prefetch …")
    meta = run_prefetch_blocking()
    print(f"[{datetime.now():%H:%M:%S}] Fertig: {meta}")
