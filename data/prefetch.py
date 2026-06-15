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
_WORKERS = 5

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


# Frische-Grenze: Ticker gilt als "heute schon gezogen" wenn jünger als …
_FRESH_HOURS = 18


def needs_prefetch_today() -> bool:
    """
    True wenn der heutige Voll-Prefetch noch nicht VOLLSTÄNDIG ist.
    Bei unvollständigem Lauf (z.B. Neustart mittendrin) → True, damit
    fortgesetzt wird; bereits gezogene Ticker werden dann übersprungen.
    """
    if is_running():
        return False
    meta = last_prefetch()
    today = datetime.now().strftime("%Y-%m-%d")
    if not meta or meta.get("date") != today:
        return True
    return not meta.get("complete", False)


def _is_ticker_warm(ticker: str) -> bool:
    """True wenn Value-Daten UND Optionskette für den Ticker frisch gecacht sind."""
    try:
        va = _dc.age_hours(f"value_data_{ticker}")
        oa = _dc.age_hours(f"opt_chain_{ticker}")
        return (va is not None and va < _FRESH_HOURS
                and oa is not None and oa < _FRESH_HOURS)
    except Exception:
        return False


def _warm_one(ticker: str) -> dict:
    """Wärmt alle Datenquellen für einen Ticker (inkl. Optionskette Puts+Calls).
    Bereits frisch gecachte Ticker werden übersprungen (Resume)."""
    ok = {"info": False, "fund": False, "hist": False, "value": False,
          "opt": False, "skipped": False}

    # Resume: heute schon vollständig gezogen → überspringen
    if _is_ticker_warm(ticker):
        ok.update({"info": True, "fund": True, "hist": True,
                   "value": True, "opt": True, "skipped": True})
        return ok

    try:
        from data.fetcher import (fetch_stock_info, fetch_fundamentals,
                                   fetch_price_history, warm_option_chain)
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
    try:
        # Optionsketten (Puts + Calls) persistent cachen → Scanner liest daraus
        ok["opt"] = warm_option_chain(ticker)
    except Exception:
        pass
    return ok


def _prefetch_worker(tickers: list) -> None:
    total = len(tickers)
    done = 0
    counts = {"info": 0, "fund": 0, "hist": 0, "value": 0, "opt": 0, "skipped": 0}
    completed_all = False

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
        completed_all = True   # Schleife vollständig durchlaufen (nicht abgebrochen)
    finally:
        meta = {
            "date":        datetime.now().strftime("%Y-%m-%d"),
            "finished_at": datetime.now().strftime("%d.%m.%Y %H:%M"),
            "total":       total,
            "counts":      counts,
            "complete":    completed_all,
        }
        _dc.save(_META_KEY, meta, ttl_hours=72)
        with _lock:
            _state["running"] = False
            _state["progress"] = 1.0 if completed_all else _state.get("progress", 0.0)
            _state["done"] = done


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
