"""
Stillhalter AI App — Research & Backtesting (Seite 21)

Ziel: Die bestmögliche individuelle Optionsstrategie je Einzelaktie finden.
  Tab 1 — Strategie-Matrix: Grid-Backtest (Delta × DTE) auf Kursdaten seit ~2000
          (yfinance "max"), Prämien via Black-Scholes simuliert.
  Tab 2 — Echte Optionsdaten: Import gekaufter Historien (CSV) ins Volume.
  Tab 3 — Datenquellen-Guide: ehrlicher Anbieter-Vergleich (Historie/Kosten)
          inkl. Einordnung von TradingView und IBKR.
"""

from __future__ import annotations

import os
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(
    page_title="Research · Stillhalter AI App",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

from analysis.backtest import run_backtest

# ── Header ─────────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.markdown(get_logo_html("auto", 40), unsafe_allow_html=True)
with col_title:
    st.markdown("""
    <div style='padding-top:4px'>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.8rem;
                    letter-spacing:0.04em'>🔬 RESEARCH & BACKTESTING</div>
        <div style='font-family:RedRose,sans-serif;font-weight:300;font-size:0.8rem;
                    color:#888;text-transform:uppercase;letter-spacing:0.12em;margin-top:2px'>
            Beste Optionsstrategie je Aktie · Grid-Backtests · Historische Daten
        </div>
    </div>
    """, unsafe_allow_html=True)
st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

tab_grid, tab_data, tab_guide = st.tabs([
    "🔬 Strategie-Matrix (Grid-Backtest)",
    "📥 Echte Optionsdaten (Import)",
    "📚 Datenquellen-Guide",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — STRATEGIE-MATRIX
# ══════════════════════════════════════════════════════════════════════════════
with tab_grid:
    st.markdown(
        "Testet **eine Aktie** über ein Raster aus **Delta × Laufzeit** und zeigt, "
        "welche Kombination historisch die beste Verfallsquote und Rendite hatte."
    )
    st.info(
        "ℹ️ **Methodik (ehrlich):** Kursdaten aus der Markt-Historie (bis zu ~26 Jahre, "
        "je nach Aktie). Da echte historische Optionspreise so weit zurück nicht frei "
        "verfügbar sind, werden die **Prämien per Black-Scholes simuliert** (historische "
        "Volatilität, Delta-Targeting). Verfallsquote und Strike-Treffer sind exakt — "
        "die Prämienhöhe ist eine gute Näherung, kein Marktpreis. Für exakte Prämien "
        "→ Tab „Echte Optionsdaten\"."
    )

    gc1, gc2, gc3, gc4 = st.columns([2, 2, 2, 2])
    with gc1:
        g_ticker = st.text_input("Ticker", value="AAPL", key="rs_ticker").strip().upper()
    with gc2:
        g_strategy = st.selectbox("Strategie", ["Cash Covered Put", "Covered Call"],
                                  key="rs_strategy",
                                  help="Short Strangle folgt, sobald echte Optionsdaten "
                                       "importiert sind (Tab 2).")
    with gc3:
        g_period = st.selectbox("Zeitraum", ["5y", "10y", "15y", "max"], index=3,
                                key="rs_period",
                                help="'max' = komplette verfügbare Kurshistorie "
                                     "(bei alten Aktien bis ~2000 und früher)")
    with gc4:
        g_signal = st.selectbox("Einstiegssignal",
                                ["SC Trend bullish", "SC Trend Cross ↑",
                                 "RSI < 30 + SC Trend", "Stoch Cross 20 ↑"],
                                key="rs_signal",
                                help="'SC Trend bullish' = regelmäßig verkaufen, solange "
                                     "der Trend passt (max. 1 Trade/Monat)")

    gd1, gd2, gd3 = st.columns([3, 3, 2])
    with gd1:
        g_deltas = st.multiselect("Delta-Raster", [0.10, 0.15, 0.20, 0.25, 0.30, 0.35],
                                  default=[0.15, 0.25, 0.35], key="rs_deltas")
    with gd2:
        g_dtes = st.multiselect("DTE-Raster (Laufzeit)", [21, 30, 45, 60],
                                default=[30, 45], key="rs_dtes")
    with gd3:
        g_exit = st.selectbox("Take Profit", ["Kein (bis Verfall)", "50%", "70%"],
                              key="rs_exit")
    _exit_pct = {"Kein (bis Verfall)": 0.0, "50%": 50.0, "70%": 70.0}[g_exit]

    n_combos = len(g_deltas) * len(g_dtes)
    st.caption(f"⏱️ {n_combos} Kombinationen — erster Lauf ca. {max(10, n_combos*4)}s, "
               f"danach 1h gecacht.")

    if st.button(f"🚀 Matrix berechnen ({n_combos} Backtests)", type="primary",
                 disabled=(not g_ticker or n_combos == 0), key="rs_run"):
        rows = []
        prog = st.progress(0.0)
        status = st.empty()
        done = 0
        for d in sorted(g_deltas):
            for t in sorted(g_dtes):
                status.caption(f"Backtest Δ{d:.2f} · {t} DTE …")
                try:
                    res = run_backtest(
                        ticker=g_ticker, strategy=g_strategy,
                        signal_type=g_signal, target_delta=float(d),
                        dte=int(t), period=g_period,
                        early_exit_pct=_exit_pct,
                    )
                    if res.error or res.n_trades == 0:
                        rows.append({"Delta": d, "DTE": t, "Trades": res.n_trades,
                                     "Winrate %": None, "Ø p.a. %": None,
                                     "Max DD %": None, "Profit-Faktor": None,
                                     "_res": None})
                    else:
                        rows.append({"Delta": d, "DTE": t, "Trades": res.n_trades,
                                     "Winrate %": round(res.win_rate, 1),
                                     "Ø p.a. %": round(res.avg_annualized_pct, 1),
                                     "Max DD %": round(res.max_drawdown_pct, 1),
                                     "Profit-Faktor": round(res.profit_factor, 2),
                                     "_res": res})
                except Exception as e:
                    rows.append({"Delta": d, "DTE": t, "Trades": 0,
                                 "Winrate %": None, "Ø p.a. %": None,
                                 "Max DD %": None, "Profit-Faktor": None, "_res": None})
                done += 1
                prog.progress(done / n_combos)
        prog.empty(); status.empty()
        st.session_state["rs_matrix"] = rows
        st.session_state["rs_matrix_meta"] = {
            "ticker": g_ticker, "strategy": g_strategy,
            "period": g_period, "signal": g_signal, "exit": g_exit,
        }

    _rows = st.session_state.get("rs_matrix")
    _meta = st.session_state.get("rs_matrix_meta", {})
    if _rows:
        mdf = pd.DataFrame([{k: v for k, v in r.items() if k != "_res"} for r in _rows])
        valid = mdf.dropna(subset=["Winrate %"])
        st.markdown(
            f"### 📊 Ergebnis — {_meta.get('ticker','')} · {_meta.get('strategy','')} · "
            f"{_meta.get('period','')} · Signal: {_meta.get('signal','')}"
        )
        if valid.empty:
            st.warning("Keine gültigen Backtests — Ticker prüfen oder Zeitraum/Signal ändern.")
        else:
            # Beste Kombination: Score = Winrate × Profit-Faktor (robust & einfach)
            valid = valid.copy()
            valid["Score"] = (valid["Winrate %"] * valid["Profit-Faktor"].clip(upper=5)).round(1)
            best = valid.sort_values("Score", ascending=False).iloc[0]
            st.success(
                f"🏆 **Beste Kombination für {_meta.get('ticker','')}:** "
                f"Delta {best['Delta']:.2f} · {int(best['DTE'])} DTE — "
                f"Winrate **{best['Winrate %']:.1f}%**, Ø Rendite **{best['Ø p.a. %']:.1f}% p.a.**, "
                f"Profit-Faktor {best['Profit-Faktor']:.2f} ({int(best['Trades'])} Trades)"
            )
            show = mdf.copy()
            show["Score"] = (show["Winrate %"] * show["Profit-Faktor"].clip(upper=5)).round(1)
            st.dataframe(
                show.sort_values("Score", ascending=False, na_position="last"),
                use_container_width=True, hide_index=True,
                column_config={
                    "Delta":        st.column_config.NumberColumn("Δ Ziel", format="%.2f"),
                    "DTE":          st.column_config.NumberColumn("DTE", format="%d T"),
                    "Winrate %":    st.column_config.NumberColumn("Winrate", format="%.1f%%"),
                    "Ø p.a. %":     st.column_config.NumberColumn("Ø Rendite p.a.", format="%.1f%%"),
                    "Max DD %":     st.column_config.NumberColumn("Max Drawdown", format="%.1f%%"),
                    "Profit-Faktor": st.column_config.NumberColumn("PF", format="%.2f"),
                    "Score":        st.column_config.ProgressColumn(
                        "Score", min_value=0,
                        max_value=float(show["Score"].max() or 1), format="%.0f"),
                },
            )

            # Equity-Kurve der besten Kombination
            best_res = next((r["_res"] for r in _rows
                             if r["Delta"] == best["Delta"] and r["DTE"] == best["DTE"]
                             and r.get("_res") is not None), None)
            if best_res is not None and len(best_res.equity_curve) > 0:
                st.markdown(f"#### 📈 Equity-Kurve — Δ{best['Delta']:.2f} · {int(best['DTE'])} DTE")
                st.line_chart(best_res.equity_curve, height=260)
            if best_res is not None and not best_res.trade_df.empty:
                with st.expander(f"📋 Alle {len(best_res.trade_df)} Trades der besten Kombination"):
                    st.dataframe(best_res.trade_df, use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — ECHTE OPTIONSDATEN (IMPORT)
# ══════════════════════════════════════════════════════════════════════════════
with tab_data:
    st.markdown(
        "Hier landen **gekaufte historische Optionsdaten** (z. B. von "
        "historicaloptiondata.com oder CBOE DataShop) — persistent im Volume. "
        "Sobald Daten vorhanden sind, laufen Backtests mit **echten Prämien** "
        "statt Black-Scholes-Näherung (inkl. Short Strangle)."
    )
    _dir = os.path.join(os.environ.get("STILLHALTER_DATA_DIR", "").strip() or
                        os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"),
                        "options_history")
    try:
        os.makedirs(_dir, exist_ok=True)
    except Exception:
        pass

    up = st.file_uploader(
        "CSV hochladen (EOD-Optionsdaten, z. B. historicaloptiondata.com L2/L3)",
        type=["csv", "zip", "gz"], accept_multiple_files=True, key="rs_upload",
    )
    if up:
        saved = 0
        for f in up:
            try:
                with open(os.path.join(_dir, f.name), "wb") as out:
                    out.write(f.getbuffer())
                saved += 1
            except Exception as e:
                st.error(f"{f.name}: {e}")
        if saved:
            st.success(f"✅ {saved} Datei(en) gespeichert → {_dir}")

    try:
        files = sorted(os.listdir(_dir))
    except Exception:
        files = []
    if files:
        _sizes = [(fn, os.path.getsize(os.path.join(_dir, fn)) / 1e6) for fn in files]
        st.markdown("**📦 Vorhandene Daten im Volume:**")
        st.dataframe(pd.DataFrame(_sizes, columns=["Datei", "MB"]).round(1),
                     use_container_width=True, hide_index=True)
    else:
        st.caption("Noch keine Daten importiert.")

    st.markdown("""
**Erwartetes Format (Standard bei allen EOD-Anbietern):**
`Datum, Ticker, Verfall, Strike, Typ (C/P), Bid, Ask, Last, Volumen, Open Interest, IV, Delta …`
— eine Zeile pro Kontrakt und Tag. Der Backtest-Ausbau auf echte Prämien folgt,
sobald die ersten Dateien hier liegen.
""")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — DATENQUELLEN-GUIDE
# ══════════════════════════════════════════════════════════════════════════════
with tab_guide:
    st.markdown("### 📚 Historische Optionsdaten — was es wirklich gibt")
    st.markdown("""
**Die ehrliche Lage zu „seit 2000":** Vollständige US-Einzelaktien-Optionshistorie ab 2000
gibt es praktisch nur bei **OptionMetrics (IvyDB, ab 1996)** — institutionell, Preis auf
Anfrage (typisch fünfstellig/Jahr). Realistisch für uns sind **2002** (Einmalkauf) oder
**2007** (Abo mit fertigem Backtester):

| Anbieter | Historie ab | Kosten | Bewertung für uns |
|---|---|---|---|
| **historicaloptiondata.com** | **Feb 2002** (SPX ab 1990) | Einmalkauf komplette Historie: ≈ $1.015–1.895 (alle US-Symbole); einzelne Jahre günstiger | ⭐ Bester Preis für 24 Jahre EOD-Daten zum Selbst-Backtesten (CSV → Tab 2) |
| **ORATS** | **2007** | ≈ $99+/Monat | ⭐ Fertige Backtest-Engine für CSP/CC/Strangle inklusive — schnellster Weg zu seriösen Ergebnissen ohne eigenen Daten-Aufbau |
| **ThetaData** | ~2012 | $40–160/Monat | Günstig, sogar Minutendaten — aber „nur" ~14 Jahre |
| **Massive/Polygon** (dein Plan) | Starter: **2 Jahre** (Developer 4 J, Advanced 5+ J) | schon vorhanden ($29) | Gut für Kurzzeit-Validierung; keine Langzeit-Historie |
| **CBOE DataShop** | je nach Produkt | Pay-per-Download je Symbol/Zeitraum | Gut für einzelne Symbole; bei 225 Tickern × 24 Jahre teuer |
| **OptionMetrics (IvyDB)** | **1996** | institutionell (Anfrage) | Einzige echte „seit 2000"-Quelle — für Privatnutzung unrealistisch |

**Empfohlener Weg (Preis/Leistung):**
1. **Sofort (kostenlos):** Tab 1 nutzen — Kursdaten bis ~2000 + Black-Scholes-Simulation.
   Verfallsquoten/Strike-Treffer sind exakt, Prämien sind Näherung.
2. **Für echte Prämien:** Einmalkauf bei historicaloptiondata.com (ab 2002) → CSV in
   Tab 2 importieren → Backtests mit Marktpreisen (inkl. Strangle).
3. **Alternative ohne Datenpflege:** ORATS-Abo — dort sind Stillhalter-Backtests
   (Wheel, CSP, CC, Strangle) fertig eingebaut.

---

### 📺 Was kann TradingView?
- **Keine historischen Optionspreise** — Optionsketten gibt es nur live, Pine-Script-
  Backtests laufen ausschließlich auf **Kursdaten**.
- **Nützlich für:** das Backtesten deiner **Einstiegssignale** (Dual Stochastik,
  Trend BT, MACD Pro) über 20+ Jahre Kurshistorie — also *wann* verkauft wird,
  nicht *was die Option wert war*. Genau das deckt Tab 1 hier direkt in der App ab.

### 🏦 Was kann IBKR?
- **Keine Historie für verfallene Optionen** über die TWS-API — abgelaufene Kontrakte
  sind nicht mehr abrufbar. 26 Jahre Options-Backtesting geht darüber nicht.
- **Nützlich für:** aktuelle Ketten in Echtzeit, **IV-Historie des Basiswerts**
  (Implied-Volatility-Index, viele Jahre zurück — guter Ersatz für die simulierte
  Volatilität in Tab 1) und die eigene Trade-Historie via Flex Query (Seite 7).
""")
