"""
Stillhalter AI — App-weiter QA-/Klick-Test (wiederholbar).

Nutzung (lokal, aus dem App-Ordner):
    STILLHALTER_DATA_DIR=/tmp/sth_qa python3 qa/run_qa.py            # Seiten-Sweep
    STILLHALTER_DATA_DIR=/tmp/sth_qa python3 qa/run_qa.py --clicks   # + Klick-Tests
    MASSIVE_API_KEY=... → aktiviert netzwerkabhängige Klick-Tests (Scanner)

Was passiert:
  1) SWEEP: Jede Seite wird headless via Streamlit AppTest geladen —
     als Admin und als Gast, in beiden Themes. Jede Exception = FAIL.
  2) CLICKS (--clicks): zentrale Interaktionen werden echt geklickt
     (Trade Monitor Verwaltung, Trade Management Bewertung, Top9-Chart,
     app.py Tagesdaten-Button, Scanner-Kurzscan bei API-Key).

Exit-Code 0 = alles grün, 1 = mindestens ein FAIL (CI-tauglich).
"""

from __future__ import annotations

import glob
import os
import sys
import warnings

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
os.environ.setdefault("STILLHALTER_DATA_DIR", "/tmp/sth_qa")

import streamlit as st
import streamlit.delta_generator as _dg

# page_link/switch_page brauchen die Multipage-Registry (fehlt im AppTest-Harness)
_noop = lambda *a, **k: None
st.page_link = _noop
_dg.DeltaGenerator.page_link = _noop
st.switch_page = _noop
_dg.DeltaGenerator.switch_page = _noop

from streamlit.testing.v1 import AppTest

ADMIN = "Oliver Riebartsch"
GUEST = "Gast (Trade Monitor)"
FAILS: list[str] = []


def _mk(page: str, user: str, theme: str, timeout: int = 90) -> AppTest:
    at = AppTest.from_file(page, default_timeout=timeout)
    at.session_state["authenticated"] = True
    at.session_state["auth_user"] = user
    at.session_state["app_theme"] = theme
    return at


def _check(label: str, at: AppTest) -> bool:
    if at.exception:
        msgs = [str(getattr(e, "message", e))[:110] for e in at.exception]
        print(f"  FAIL {label}: {msgs}")
        FAILS.append(f"{label}: {msgs}")
        return False
    print(f"  OK   {label}")
    return True


def sweep() -> None:
    pages = ["app.py"] + sorted(glob.glob("pages/*.py"))
    print(f"\n══ SWEEP: {len(pages)} Seiten × Admin/Gast × dark/green ══")
    for page in pages:
        for user in (ADMIN, GUEST):
            for theme in ("dark", "green"):
                label = f"{page.split('/')[-1]:34s} {('Admin' if user==ADMIN else 'Gast '):5s} {theme}"
                try:
                    at = _mk(page, user, theme)
                    at.run()
                    _check(label, at)
                except Exception as e:
                    print(f"  FAIL {label}: {type(e).__name__}: {e}")
                    FAILS.append(f"{label}: {e}")


def clicks() -> None:
    print("\n══ KLICK-TESTS ══")
    import pandas as pd
    from datetime import date, timedelta

    # Seed: Monitor-Trade + Top9-Scan-Cache
    import data.monitor_store as ms
    if not any(t.get("ticker") == "HON" for t in ms.load_trades()):
        ms.add_trade(ms.make_trade("HON", "Short PUT", 220, "2026-07-10", 3.60,
                                   cls="A", price_at_entry=229.86, delta=-0.22))
    import pickle, datetime as _dt
    from data import _persistent_cache as pc
    rows = [{"Ticker": "AAPL", "Kurs": 205.0, "Strike": 190.0, "Verfall": "2026-07-17",
             "DTE": 29, "Prämie": 1.8, "CRV Score": 120, "Delta": -0.2, "IV %": 25,
             "OTM %": 7.3, "Rendite % Laufzeit": 0.95, "Rendite ann. %": 11.8,
             "Rendite %/Tag": 0.03, "Sektor": "Tech", "IV Rank": "50",
             "⚠️ Earnings": "", "Trend": "↑", "_strategie": "Short PUT"}]
    with open(pc.scan_cache_path(), "wb") as f:
        pickle.dump({"results": pd.DataFrame(rows),
                     "timestamp": _dt.datetime.now(), "strategy": "Komplett-Scan"}, f)

    # 1) Trade Monitor: Verwaltung sichtbar (Admin), Gast ohne
    at = _mk("pages/20_Trade_Monitor.py", ADMIN, "dark", 120); at.run()
    if _check("Monitor Admin", at):
        b = [x.label or "" for x in at.button]
        assert any("Status speichern" in x for x in b), "Kein Status-Button"
        assert any("Trade entfernen" in x for x in b), "Kein Entfernen-Button"
        print("       ↳ Verwaltung vorhanden")
    at = _mk("pages/20_Trade_Monitor.py", GUEST, "dark", 120); at.run()
    if _check("Monitor Gast", at):
        b = [x.label or "" for x in at.button]
        assert not any("entfernen" in x for x in b), "Gast sieht Verwaltung!"
        print("       ↳ Gast read-only")

    # 2) Trade Management: Position seeden + bewerten klicken
    at = _mk("pages/07_Trade_Management.py", ADMIN, "dark", 300)
    at.session_state["tm_positions"] = pd.DataFrame([{
        "Ticker": "HON", "Typ": "PUT", "Strike": 220.0,
        "Verfall": date.today() + timedelta(days=7),
        "Menge": -1, "Prämie_Ein": 3.60, "Notizen": ""}])
    at.session_state["tm_results"] = {}
    at.run()
    if _check("TM laden", at):
        bew = [x for x in at.button if "bewerten" in (x.label or "").lower()]
        if bew:
            bew[0].click(); at.run()
            _check("TM bewerten-Klick", at)

    # 3) Top 9: Chart-Dialog-Klick (Karten via geseedetem Cache)
    at = _mk("pages/05_Top9_Trading_Ideen.py", ADMIN, "dark", 120)
    at.session_state["top9_dte_range"] = "📅 Mittel 21–60T"
    at.run()
    if _check("Top9 laden", at):
        cb = [x for x in at.button if "Chart" in (x.label or "")]
        if cb:
            cb[0].click(); at.run()
            _check("Top9 Chart-Klick", at)

    # 4) app.py: System-Buttons klicken (Tagesdaten, Konsistenz-Reparatur,
    #    tiefer Selbsttest) — Klick-Handler-Pfade, die Lade-Tests nicht sehen!
    at = _mk("app.py", ADMIN, "dark", 120); at.run()
    if _check("app laden", at):
        tb = [x for x in at.button if "Tagesdaten" in (x.label or "")]
        if tb:
            tb[0].click(); at.run()
            _check("app Tagesdaten-Klick", at)
    at = _mk("app.py", ADMIN, "dark", 180); at.run()
    rb = [x for x in at.button if "Konsistenz" in (x.label or "")]
    if rb:
        rb[0].click(); at.run()
        _check("app Konsistenz-Reparatur-Klick", at)
    if os.environ.get("MASSIVE_API_KEY"):
        at = _mk("app.py", ADMIN, "dark", 300); at.run()
        hb = [x for x in at.button if "Selbsttest" in (x.label or "")]
        if hb:
            hb[0].click(); at.run()
            _check("app Tiefer-Selbsttest-Klick", at)

    # 5) Scanner-Kurzscan (nur mit API-Key — Netzwerk!)
    if os.environ.get("MASSIVE_API_KEY"):
        at = _mk("pages/04_Watchlist_Scanner.py", ADMIN, "dark", 400); at.run()
        if _check("Scanner laden", at):
            for sb in at.selectbox:
                if sb.options and any("IMMOBILIEN" in str(o) for o in sb.options):
                    sb.set_value("7. IMMOBILIEN (REITS)")
            at.run()
            btns = [x for x in at.button if (x.label or "").startswith("🚀 Scan starten")]
            if btns:
                btns[0].click(); at.run()
                if _check("Scanner Scan-Klick", at):
                    sr = None
                    try:
                        sr = at.session_state["scan_results"]
                    except Exception:
                        pass
                    shape = getattr(sr, "shape", None)
                    print(f"       ↳ scan_results: {shape}")
                    if shape is not None and shape[0] == 0:
                        print("       ↳ HINWEIS: 0 Treffer — nach vielen QA-Loads "
                              "meist Yahoo-Drosselung, kein Code-Fehler. "
                              "Einzeln prüfen: scan_ticker('O', ...)")
    else:
        print("  SKIP Scanner-Klick (kein MASSIVE_API_KEY gesetzt)")


if __name__ == "__main__":
    sweep()
    if "--clicks" in sys.argv:
        clicks()
    print(f"\n══ ERGEBNIS: {'✅ ALLES GRÜN' if not FAILS else f'❌ {len(FAILS)} FEHLER'} ══")
    for f in FAILS:
        print("  •", f)
    sys.exit(1 if FAILS else 0)
