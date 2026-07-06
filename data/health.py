"""
Stillhalter AI — Selbsttest & Daten-Konsistenzprüfung.

Vom Nutzer gewünscht: "Kann die App nicht zu Beginn alle Funktionen überprüfen?"
→ run_light_check(): schneller Funktions-Check (Volume, Datenquellen,
  Quote-Qualität der gecachten Optionsketten, Kern-Dateien) — läuft beim
  App-Start (gecacht) und zeigt Probleme, BEVOR jemand rätselt, warum der
  Scanner 0 Treffer liefert.
→ check_consistency(repair=…): prüft/repariert die persistenten Dateien
  (Trades, Trade Cards, Scan-Cache, Disk-Cache) — die "Datenbank" der App.

Jeder Check liefert: {"name", "ok", "detail", ggf. "repaired"}.
"""

from __future__ import annotations

import json
import os
import pickle
from datetime import datetime
from typing import List


def _res(name: str, ok: bool, detail: str, repaired: str = "") -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail, "repaired": repaired}


# ══════════════════════════════════════════════════════════════════════════════
# KONSISTENZPRÜFUNG (persistente Dateien = "Datenbank")
# ══════════════════════════════════════════════════════════════════════════════

def check_consistency(repair: bool = False) -> List[dict]:
    out: List[dict] = []
    from data import _persistent_cache as _dc

    # 1) Volume erreichbar + beschreibbar
    data_dir = os.environ.get("STILLHALTER_DATA_DIR", "").strip() or \
        os.path.join(os.path.dirname(__file__))
    try:
        probe = os.path.join(data_dir, ".health_probe")
        with open(probe, "w") as f:
            f.write(datetime.now().isoformat())
        os.remove(probe)
        _persist = data_dir.startswith("/data")
        out.append(_res("Volume beschreibbar", True,
                        f"{data_dir} ({'persistent' if _persist else '⚠️ FLÜCHTIG — kein Volume!'})"))
    except Exception as e:
        out.append(_res("Volume beschreibbar", False, f"{data_dir}: {e}"))

    # 2) Trade Monitor (manual_trades.json): ladbar, Schema, Duplikate
    try:
        import data.monitor_store as ms
        path = ms.trades_path()
        if not os.path.exists(path):
            out.append(_res("Trades (Monitor)", True, "Noch keine Datei — ok"))
        else:
            raw = json.load(open(path, encoding="utf-8"))
            if not isinstance(raw, list):
                raise ValueError("Kein JSON-Array")
            ids, dupes, broken = set(), [], []
            clean = []
            for t in raw:
                if not isinstance(t, dict) or not t.get("ticker") or not t.get("trade_id"):
                    broken.append(t)
                    continue
                if t["trade_id"] in ids:
                    dupes.append(t["trade_id"])
                    continue
                ids.add(t["trade_id"])
                clean.append(t)
            msg = f"{len(clean)} Trades ok"
            rep = ""
            if dupes or broken:
                msg += f" · {len(dupes)} Duplikate · {len(broken)} defekte Einträge"
                if repair:
                    import shutil
                    shutil.copy2(path, path + ".bak")
                    ms.save_trades(clean)
                    rep = f"bereinigt (Backup: {os.path.basename(path)}.bak)"
            out.append(_res("Trades (Monitor)", not (dupes or broken) or bool(rep), msg, rep))
    except Exception as e:
        out.append(_res("Trades (Monitor)", False, f"NICHT LESBAR: {e}"))

    # 3) Trade Cards Store (Signal Pipeline)
    try:
        from data.trade_store import STORE_PATH
        if not os.path.exists(STORE_PATH):
            out.append(_res("Trade Cards Store", True, "Noch keine Datei — ok"))
        else:
            raw = json.load(open(STORE_PATH, encoding="utf-8"))
            ok = isinstance(raw, list)
            in_volume = STORE_PATH.startswith("/data") or bool(
                os.environ.get("STILLHALTER_DATA_DIR", "").strip())
            out.append(_res("Trade Cards Store", ok,
                            f"{len(raw) if ok else '?'} Cards · "
                            f"{'im Volume' if in_volume else '⚠️ im Code-Ordner (geht bei Deploy verloren)'}"))
    except Exception as e:
        out.append(_res("Trade Cards Store", False, f"NICHT LESBAR: {e}"))

    # 4) Letzter Scan (last_scan_cache.pkl)
    try:
        p = _dc.scan_cache_path()
        if not os.path.exists(p):
            out.append(_res("Scan-Cache", True, "Noch kein Scan gespeichert — ok"))
        else:
            d = pickle.load(open(p, "rb"))
            ts = d.get("timestamp")
            n = len(d.get("results", [])) if d.get("results") is not None else 0
            age_h = (datetime.now() - ts).total_seconds() / 3600 if ts else 999
            out.append(_res("Scan-Cache", True,
                            f"{n} Zeilen · {age_h:.1f}h alt ({d.get('strategy','?')})"))
    except Exception as e:
        detail = f"KORRUPT: {e}"
        rep = ""
        if repair:
            try:
                os.remove(_dc.scan_cache_path())
                rep = "korrupte Datei entfernt — nächster Scan legt sie neu an"
            except Exception:
                pass
        out.append(_res("Scan-Cache", bool(rep), detail, rep))

    # 5) Disk-Cache: korrupte Pickles finden (Folge nicht-atomarer Writes früher)
    try:
        cdir = _dc._CACHE_DIR
        files = [f for f in os.listdir(cdir) if f.endswith(".pkl")]
        corrupt = []
        for fn in files:
            fp = os.path.join(cdir, fn)
            try:
                with open(fp, "rb") as f:
                    pickle.load(f)
            except Exception:
                corrupt.append(fp)
        rep = ""
        if corrupt and repair:
            for fp in corrupt:
                try:
                    os.remove(fp)
                except Exception:
                    pass
            rep = f"{len(corrupt)} korrupte Cache-Dateien entfernt"
        out.append(_res("Disk-Cache", not corrupt or bool(rep),
                        f"{len(files)} Dateien · {len(corrupt)} korrupt", rep))
    except Exception as e:
        out.append(_res("Disk-Cache", False, str(e)))

    # 6) Verwaiste .tmp-Dateien (abgebrochene Writes) aufräumen
    try:
        removed = 0
        for root in {data_dir, getattr(_dc, "_CACHE_DIR", data_dir)}:
            if os.path.isdir(root):
                for fn in os.listdir(root):
                    if ".tmp." in fn:
                        if repair:
                            try:
                                os.remove(os.path.join(root, fn))
                                removed += 1
                            except Exception:
                                pass
                        else:
                            removed += 1
        out.append(_res("Temp-Dateien", True,
                        f"{removed} verwaiste .tmp-Dateien" + (" entfernt" if repair and removed else "")))
    except Exception as e:
        out.append(_res("Temp-Dateien", False, str(e)))

    return out


# ══════════════════════════════════════════════════════════════════════════════
# FUNKTIONS-SELBSTTEST (Datenquellen + Datenqualität)
# ══════════════════════════════════════════════════════════════════════════════

def run_light_check() -> List[dict]:
    """Schneller Selbsttest der Kernfunktionen (~3–8s, wird gecacht aufgerufen)."""
    out: List[dict] = []

    # 1) Polygon/Massive erreichbar + Key gültig
    try:
        from data.massive_fetcher import is_api_key_configured, get_available_expirations
        if not is_api_key_configured():
            out.append(_res("Polygon/Massive", False, "Kein API-Key konfiguriert"))
        else:
            exps = get_available_expirations("AAPL")
            out.append(_res("Polygon/Massive", len(exps) > 0,
                            f"{len(exps)} AAPL-Verfälle abrufbar"))
    except Exception as e:
        out.append(_res("Polygon/Massive", False, str(e)[:120]))

    # 2) Yahoo Finance (Aktienkurse)
    try:
        from data.fetcher import fetch_stock_info
        px = fetch_stock_info("AAPL").get("price")
        out.append(_res("Yahoo Finance", bool(px and px > 0),
                        f"AAPL-Kurs: ${px:.2f}" if px else "kein Kurs"))
    except Exception as e:
        out.append(_res("Yahoo Finance", False, str(e)[:120]))

    # 3) Optionskette + QUOTE-QUALITÄT (der '0-Treffer'-Frühwarner!)
    try:
        from data.fetcher import fetch_options_chain, is_market_open
        puts, _c, exps = fetch_options_chain("AAPL", dte_min=14, dte_max=60,
                                             max_expiries=2, option_types=("put",))
        n = 0 if puts is None else len(puts)
        if n == 0:
            out.append(_res("Optionskette", False, "AAPL-Kette leer"))
        else:
            import pandas as pd
            b = pd.to_numeric(puts.get("bid"), errors="coerce").fillna(0)
            a = pd.to_numeric(puts.get("ask"), errors="coerce").fillna(0)
            lp = pd.to_numeric(puts.get("lastPrice"), errors="coerce").fillna(0)
            v = pd.to_numeric(puts.get("volume"), errors="coerce").fillna(0)
            quoted = ((b > 0) & (a > 0))
            traded = ((lp > 0) & (v > 0))
            usable = float((quoted | traded).mean()) * 100
            if is_market_open():
                # Polygon-Starter liefert keine NBBO-Quotes — Kriterium ist
                # daher 'nutzbar' = Quote ODER heutiger Handel (Preis+Volumen).
                ok = usable >= 15
                det = (f"{n} Puts · {usable:.0f}% nutzbar "
                       f"({float(quoted.mean())*100:.0f}% Quotes, "
                       f"{float(traded.mean())*100:.0f}% heute gehandelt)"
                       + ("" if ok else " — ⚠️ Markt offen, aber keine verwertbaren "
                                        "Preise → Scanner fände 0!"))
            else:
                ok = True
                det = f"{n} Puts · Markt zu — Last-Price-Modus normal"
            out.append(_res("Optionskette (Preisqualität)", ok, det))
    except Exception as e:
        out.append(_res("Optionskette (Quotes)", False, str(e)[:120]))

    # 4) Persistenz-Kurzcheck (Volume + Kern-Dateien lesbar)
    for c in check_consistency(repair=False):
        if c["name"] in ("Volume beschreibbar", "Trades (Monitor)", "Scan-Cache"):
            out.append(c)

    return out


# ── Hintergrund-Selbsttest (blockiert die App NICHT) ──────────────────────────
_BG_LOCK = __import__("threading").Lock()
_BG_STARTED = {"v": False}


def start_background_check() -> None:
    """Startet den Light-Check einmal pro Prozess im Daemon-Thread.
    Ergebnis → Disk-Cache 'health_last' (App-Start bleibt schnell)."""
    import threading
    with _BG_LOCK:
        if _BG_STARTED["v"]:
            return
        _BG_STARTED["v"] = True

    def _worker():
        try:
            from data import _persistent_cache as _dc
            res = run_light_check()
            _dc.save("health_last", {
                "ts": datetime.now().isoformat(timespec="seconds"),
                "results": res,
            }, ttl_hours=24)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True,
                     name="StillhalterHealthCheck").start()


def last_check() -> dict | None:
    """Letztes Hintergrund-Selbsttest-Ergebnis (oder None)."""
    try:
        from data import _persistent_cache as _dc
        return _dc.load_latest("health_last")
    except Exception:
        return None


def run_deep_check() -> List[dict]:
    """Gründlicher Test: light + echter Mini-Scan (CSP + Strangle, 1 Ticker)
    + volle Konsistenzprüfung. Dauer ~20–60s."""
    out = run_light_check()
    try:
        from analysis.batch_screener import scan_ticker, scan_strangle
        from data.fetcher import is_market_open
        rvm = is_market_open()
        df = scan_ticker("AAPL", strategy="Cash Covered Put", dte_min=14, dte_max=60,
                         iv_min=0.0, premium_min=0.05, min_oi=0, otm_min=3.0,
                         otm_max=25.0, require_valid_market=rvm, max_spread_pct=999.0)
        out.append(_res("Mini-Scan CSP", len(df) > 0, f"AAPL: {len(df)} Treffer"))
        ds = scan_strangle("AAPL", dte_min=14, dte_max=60, iv_min=0.0, premium_min=0.05,
                           min_oi=0, otm_min=3.0, otm_max=40.0, max_spread_pct=999.0,
                           require_valid_market=rvm)
        out.append(_res("Mini-Scan Strangle", len(ds) > 0, f"AAPL: {len(ds)} Treffer"))
    except Exception as e:
        out.append(_res("Mini-Scan", False, str(e)[:140]))
    for c in check_consistency(repair=False):
        if c["name"] not in [o["name"] for o in out]:
            out.append(c)
    return out
