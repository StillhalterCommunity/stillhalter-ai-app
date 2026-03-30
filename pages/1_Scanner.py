"""
Stillhalter Community — Watchlist Scanner
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import os

st.set_page_config(
    page_title="Scanner · Stillhalter Community",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)

from data.watchlist import WATCHLIST, SECTOR_ICONS, ALL_TICKERS
from data.fetcher import market_status_text, is_market_open
from analysis.batch_screener import scan_watchlist
from analysis.multi_timeframe import (
    analyze_multi_timeframe, matches_tech_filter,
    TechFilterParams, tf_summary_row
)

# ── Header ────────────────────────────────────────────────────────────────────
h1, h2 = st.columns([1, 6])
with h1:
    st.markdown(get_logo_html("white", 36), unsafe_allow_html=True)
with h2:
    market_open = is_market_open()
    mkt_class = "market-open" if market_open else "market-closed"
    st.markdown(
        f'<div class="sc-page-title">Watchlist Scanner</div>'
        f'<div class="sc-page-subtitle"><span class="{mkt_class}">{market_status_text()}</span>'
        f' &nbsp;·&nbsp; 225 Aktien · 11 Sektoren</div>',
        unsafe_allow_html=True
    )

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── Off-Hours Hinweis ─────────────────────────────────────────────────────────
if not market_open:
    st.warning(
        "⏰ **Markt geschlossen** — Bid/Ask ist nicht verfügbar. "
        "Aktiviere **'Last Price verwenden'** → der Scanner nutzt dann den letzten Handelskurs "
        "und lockert automatisch die Prämien- & OI-Filter (Prämie min. $0.01 · OI ≥ 0), "
        "damit auch wenig gehandelte Optionen angezeigt werden. "
        "Prämien können leicht von den nächsten Live-Kursen abweichen.",
        icon="⚠️"
    )

# ── Haupt-Einstellungen ───────────────────────────────────────────────────────
with st.expander("⚙️ **SCAN-EINSTELLUNGEN & OPTIONS-FILTER**", expanded=True):
    row1 = st.columns(5)
    with row1[0]:
        sector_opts = ["Alle Sektoren (225)"] + list(WATCHLIST.keys())
        scan_sector = st.selectbox(
            "Sektor",
            sector_opts,
            format_func=lambda s: (
                s if "Alle" in s
                else f"{SECTOR_ICONS.get(s,'')} {s.split('.',1)[-1].strip().split('(')[0].strip()}"
            ),
        )
    with row1[1]:
        scan_strategy = st.selectbox("Strategie", ["Cash Covered Put", "Covered Call"])
    with row1[2]:
        max_per_ticker = st.number_input("Max. Optionen/Aktie", 1, 10, 3)
    with row1[3]:
        top_n = st.number_input("Top N Ergebnisse", 5, 500, 40, step=5)
    with row1[4]:
        use_last_price = st.checkbox(
            "Last Price verwenden",
            value=not market_open,
            help="Außerhalb der Börsenzeiten: Last Price statt Bid/Ask nutzen"
        )

    st.markdown('<div style="height:6px"></div>', unsafe_allow_html=True)
    row2 = st.columns(7)
    with row2[0]:
        dte_min = st.number_input("DTE min", 0, 180, 14)
        dte_max = st.number_input("DTE max", 1, 365, 60)
    with row2[1]:
        if scan_strategy == "Cash Covered Put":
            d_min = st.number_input("Delta min", -1.0, 0.0, -0.35, 0.01, format="%.2f")
            d_max = st.number_input("Delta max", -1.0, 0.0, -0.05, 0.01, format="%.2f")
        else:
            dp_min = st.number_input("Delta min", 0.0, 1.0, 0.05, 0.01, format="%.2f")
            dp_max = st.number_input("Delta max", 0.0, 1.0, 0.35, 0.01, format="%.2f")
            d_min, d_max = -dp_max, -dp_min
    with row2[2]:
        iv_min = st.number_input("IV min %", 0, 300, 0, step=5)
        iv_max = st.number_input("IV max %", 5, 500, 200, step=10)
    with row2[3]:
        otm_min = st.number_input("OTM min %", 0, 30, 3)
        otm_max = st.number_input("OTM max %", 1, 50, 25)
    with row2[4]:
        prem_min = st.number_input("Mind. Prämie ($)", 0.0, 20.0, 0.05, 0.05, format="%.2f")
        prem_day = st.number_input("Mind. Prämie/Tag ($)", 0.0, 5.0, 0.0, 0.01, format="%.3f")
        min_yield_laufzeit = st.number_input("Mind. Rendite % Laufzeit", 0.0, 20.0, 0.0, 0.1, format="%.1f",
                                              help="Mindestrendite auf Laufzeit (% auf Strike)")
        min_yield_day_pct = st.number_input("Mind. Rendite %/Tag", 0.0, 1.0, 0.0, 0.01, format="%.2f",
                                             help="Mindestrendite pro Tag (% auf Strike)")
    with row2[5]:
        oi_min = st.number_input("Mind. Open Interest", 0, 5000, 5, step=5)
        min_crv = st.number_input("Mind. CRV Score", 0.0, 500.0, 0.0, 10.0, format="%.0f",
                                   help="Filtert nach Mindest-CRV Score")
    with row2[6]:
        st.markdown("<br>", unsafe_allow_html=True)
        sort_by = st.selectbox(
            "Sortierung",
            ["CRV Score", "Rendite ann. %", "Rendite % Laufzeit", "Rendite %/Tag", "OTM %", "Prämie/Tag", "DTE", "|Delta|"],
        )

# ── Technische Filter ─────────────────────────────────────────────────────────
with st.expander("📊 **TECHNISCHE FILTER** — RSI · Stochastik · MACD · Stillhalter Trend Model · Multi-Timeframe", expanded=False):

    st.markdown("""
    <div style='color:#888;font-size:0.82rem;margin-bottom:12px'>
    Filtert Aktien nach technischen Signalen auf 4H · 1D · 1W Ebene.
    Aktivierte Filter werden mit AND verknüpft — die Aktie muss <b>alle</b> Bedingungen erfüllen.
    Crossover-Signale werden innerhalb der letzten 3 Kerzen erkannt.
    </div>
    """, unsafe_allow_html=True)

    TF_OPTIONS = ["4H", "1D", "1W", "Alle TFs"]

    tc1, tc2, tc3, tc4 = st.columns(4)

    with tc1:
        st.markdown("**📈 Stillhalter Trend Model®**")
        ema_filter = st.selectbox("SC Trend Signal", [
            "Alle",
            "SC Trend bullish ↑",
            "SC Trend bearish ↓",
            "Kaufsignal (Cross ↑)",
            "Verkaufssignal (Cross ↓)",
        ], key="ema_f")
        ema_tf = st.selectbox("SC Trend Timeframe", TF_OPTIONS, index=1, key="ema_tf")
        st.caption("Cross ↑ = Kaufsignal | Cross ↓ = Verkaufssignal")
        trend_mode_scan = st.selectbox("Trend Mode",
            ["Very Tight", "Tight", "Loose", "Very Loose"],
            index=0,
            key="trend_mode_scan",
            help="Very Tight = kurzfristig sensitiv · Very Loose = langfristig stabil")

    with tc2:
        st.markdown("**〰️ RSI (Momentum)**")
        rsi_filter = st.selectbox("RSI Signal", [
            "Alle",
            "Kreuzt 30 aufwärts ↑",
            "Kreuzt 70 abwärts ↓",
            "< 30 (überverkauft)",
            "> 70 (überkauft)",
            "Bullish (RSI > 50)",
            "Bearish (RSI < 50)",
        ], key="rsi_f")
        rsi_tf = st.selectbox("RSI Timeframe", TF_OPTIONS, index=1, key="rsi_tf")
        st.caption("Crossover-Signale = Trendumkehr-Hinweise")

    with tc3:
        st.markdown("**〽️ Stochastik (Overbought/Sold)**")
        stoch_filter = st.selectbox("Stochastik Signal", [
            "Alle",
            "Kreuzt 20 aufwärts ↑",
            "Kreuzt 80 abwärts ↓",
            "< 20 (überverkauft)",
            "> 80 (überkauft)",
            "%K > %D (bullish)",
            "%K < %D (bearish)",
        ], key="stoch_f")
        stoch_tf = st.selectbox("Stoch. Timeframe", TF_OPTIONS, index=1, key="stoch_tf")
        st.caption("%K kreuzt 20 aufwärts = klassisches Kaufsignal")

    with tc4:
        st.markdown("**🌊 MACD (Momentum)**")
        macd_filter = st.selectbox("MACD Signal", [
            "Alle",
            "Bullish Cross (neg → pos)",
            "Bearish Cross (pos → neg)",
            "MACD > Signal (bullish)",
            "MACD < Signal (bearish)",
            "MACD Linie > 0",
        ], key="macd_f")
        macd_tf = st.selectbox("MACD Timeframe", TF_OPTIONS, index=1, key="macd_tf")
        st.caption("MACD Cross neg→pos = starkes Bullish-Signal")

    st.markdown("---")
    al1, al2, al3 = st.columns([1, 2, 5])
    with al1:
        require_align = st.checkbox("Multi-TF Alignment", value=False,
                                     help="Alle/mind. 2 Timeframes müssen dieselbe Richtung zeigen")
    with al2:
        align_dir = st.selectbox("Alignment Richtung",
                                  ["bullish", "bearish"], disabled=not require_align)
    with al3:
        if require_align:
            st.info(
                f"✅ Nur Aktien anzeigen, bei denen mind. **2 von 3 Timeframes (4H · 1D · 1W)** "
                f"**{align_dir}** sind (RSI + Stoch + MACD + EMA alle berücksichtigt)"
            )

    tech_params = TechFilterParams(
        ema_filter=ema_filter, ema_timeframe=ema_tf,
        rsi_filter=rsi_filter, rsi_timeframe=rsi_tf,
        stoch_filter=stoch_filter, stoch_timeframe=stoch_tf,
        macd_filter=macd_filter, macd_timeframe=macd_tf,
        require_alignment=require_align,
        alignment_direction=align_dir,
    )

    use_tech_filter = any([
        ema_filter != "Alle", rsi_filter != "Alle",
        stoch_filter != "Alle", macd_filter != "Alle",
        require_align
    ])

# ── Ticker Liste ──────────────────────────────────────────────────────────────
scan_tickers = ALL_TICKERS if "Alle" in scan_sector else WATCHLIST.get(scan_sector, [])
mins = max(1, len(scan_tickers) * 2 // 60)
maxs = max(2, len(scan_tickers) * 4 // 60)

tech_filter_note = " + Technische Vorab-Filterung" if use_tech_filter else ""
off_hours_mode = use_last_price and not market_open
if off_hours_mode:
    price_mode_str = "⚠️ Last Price Modus (Prämie ≥ $0.01 · OI ≥ 0 automatisch)"
else:
    price_mode_str = "✅ Live Bid/Ask"
st.info(
    f"**{len(scan_tickers)} Aktien** · Dauer: **~{mins}–{maxs} Min.**{tech_filter_note} · {price_mode_str}"
)

# ── Scan Buttons ──────────────────────────────────────────────────────────────
b1, b2, _ = st.columns([2, 2, 8])
with b1:
    start_scan = st.button(f"🚀 Scan starten ({len(scan_tickers)} Ticker)", type="primary", use_container_width=True)
with b2:
    if st.button("🗑️ Cache leeren", use_container_width=True):
        st.cache_data.clear()
        for key in ["scan_results", "scan_meta", "tf_results"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── Session State ─────────────────────────────────────────────────────────────
for k in ["scan_results", "scan_meta", "tf_results"]:
    if k not in st.session_state:
        st.session_state[k] = None

# ── Scan ausführen ────────────────────────────────────────────────────────────
if start_scan:
    progress_bar = st.progress(0.0)
    status_ph = st.empty()

    # Schritt 1: Technische Vorab-Filterung
    filtered_tickers = scan_tickers
    tf_cache = {}

    if use_tech_filter:
        status_ph.markdown("**Phase 1/2:** Technische Analyse aller Ticker...")
        tech_passed = []

        for i, ticker in enumerate(scan_tickers):
            progress_bar.progress(i / len(scan_tickers) * 0.5)
            status_ph.markdown(f"**Phase 1/2** Technische Analyse: `{ticker}` ({i+1}/{len(scan_tickers)})")

            tf_result = analyze_multi_timeframe(ticker)
            tf_cache[ticker] = tf_result

            if matches_tech_filter(tf_result, tech_params):
                tech_passed.append(ticker)

        status_ph.markdown(
            f"✅ Phase 1 abgeschlossen: **{len(tech_passed)}/{len(scan_tickers)}** Aktien "
            f"bestehen den technischen Filter"
        )
        filtered_tickers = tech_passed

    if not filtered_tickers:
        st.warning("Kein Ticker erfüllt die technischen Filterkriterien. Passe die Tech-Filter an.")
        st.session_state.scan_results = pd.DataFrame()
    else:
        # Schritt 2: Optionen scannen
        phase_offset = 0.5 if use_tech_filter else 0.0
        phase_scale = 0.5 if use_tech_filter else 1.0

        def on_progress(current, total, ticker):
            pct = phase_offset + (current / max(total, 1)) * phase_scale
            progress_bar.progress(min(pct, 1.0))
            status_ph.markdown(
                f"**{'Phase 2/2' if use_tech_filter else 'Scan'}:** Options für `{ticker}` ({current}/{total})"
            )

        # Im Last-Price-Modus (Markt geschlossen): Filter automatisch lockern,
        # da Bid/Ask = 0 und nur lastPrice verfügbar ist (stale, ggf. niedrig)
        off_hours_mode = use_last_price and not market_open
        effective_premium_min = 0.01 if off_hours_mode else prem_min
        effective_oi_min      = 0    if off_hours_mode else int(oi_min)

        results = scan_watchlist(
            tickers=filtered_tickers,
            strategy=scan_strategy,
            delta_min=d_min, delta_max=d_max,
            dte_min=int(dte_min), dte_max=int(dte_max),
            iv_min=iv_min / 100,
            premium_min=effective_premium_min,
            min_oi=effective_oi_min,
            otm_min=float(otm_min), otm_max=float(otm_max),
            max_results_per_ticker=int(max_per_ticker),
            progress_callback=on_progress,
        )

        # CRV Score-Filter
        if min_crv > 0 and not results.empty and "CRV Score" in results.columns:
            results = results[results["CRV Score"] >= min_crv]

        # Premium/Tag Filter
        if prem_day > 0 and not results.empty and "Prämie/Tag" in results.columns:
            results = results[results["Prämie/Tag"] >= prem_day]

        # Rendite % Filter
        if min_yield_laufzeit > 0 and not results.empty and "Rendite % Laufzeit" in results.columns:
            results = results[results["Rendite % Laufzeit"] >= min_yield_laufzeit]
        if min_yield_day_pct > 0 and not results.empty and "Rendite %/Tag" in results.columns:
            results = results[results["Rendite %/Tag"] >= min_yield_day_pct]

        # Tech-Signale ergänzen (für Anzeige)
        if not results.empty and tf_cache:
            def add_tf_info(ticker):
                tf = tf_cache.get(ticker)
                if tf is None or tf.tf_1d is None:
                    return ("–", "–", "–", "–", "–")
                d = tf.tf_1d
                return (
                    f"{d.rsi:.0f}{'⬆' if d.rsi_cross_30_up else '⬇' if d.rsi_cross_70_down else ''}",
                    f"{d.stoch_k:.0f}{'⬆' if d.stoch_cross_20_up else '⬇' if d.stoch_cross_80_down else ''}",
                    "↑Cross" if d.macd_cross_bullish else ("↓Cross" if d.macd_cross_bearish else ("Bull" if d.macd_bullish else "Bear")),
                    "↑Cross" if d.ema_cross_bullish else ("↓Cross" if d.ema_cross_bearish else ("Bull" if d.ema_bullish else "Bear")),
                    f"{tf.alignment_score:.0f}",
                )

            tf_cols = results["Ticker"].apply(add_tf_info)
            results["RSI(1D)"] = [x[0] for x in tf_cols]
            results["Stoch(1D)"] = [x[1] for x in tf_cols]
            results["MACD(1D)"] = [x[2] for x in tf_cols]
            results["SC Trend(1D)"] = [x[3] for x in tf_cols]
            results["TF-Align"] = [x[4] for x in tf_cols]

        progress_bar.progress(1.0)
        n_found = len(results)
        n_tickers = results["Ticker"].nunique() if not results.empty else 0
        status_ph.markdown(
            f"✅ **Scan abgeschlossen** — **{n_found} Optionen** aus **{n_tickers} Aktien** gefunden"
        )

        st.session_state.scan_results = results

        # Top-9-Cache für Homepage aktualisieren (inkl. TF-Align wenn verfügbar)
        try:
            import pickle, datetime
            cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "last_scan_cache.pkl")
            with open(cache_path, "wb") as f:
                pickle.dump({
                    "results": results,
                    "timestamp": datetime.datetime.now(),
                    "strategy": scan_strategy,
                }, f)
        except Exception:
            pass

        st.session_state.scan_meta = {
            "sector": scan_sector, "strategy": scan_strategy,
            "n_tickers": len(scan_tickers), "n_filtered": len(filtered_tickers),
        }
        st.session_state.tf_results = tf_cache

# ── Ergebnisse ────────────────────────────────────────────────────────────────
results = st.session_state.scan_results
meta = st.session_state.scan_meta or {}

if results is None:
    st.markdown("""
    <div style='text-align:center;padding:4rem 2rem;color:#333'>
        <div style='font-size:3rem'>🔍</div>
        <div style='font-family:RedRose,sans-serif;font-size:1.1rem;margin-top:1rem;color:#555'>
            Filter konfigurieren und Scan starten
        </div>
    </div>
    """, unsafe_allow_html=True)

elif results.empty:
    st.warning(
        "**Keine Optionen gefunden.**\n\n"
        "Empfehlungen:\n"
        "- OTM min % senken (z.B. 0%)\n"
        "- Mind. Prämie auf $0.01 setzen\n"
        "- Open Interest auf 0 setzen\n"
        "- Tech-Filter deaktivieren oder lockern\n"
        "- Markt geschlossen: Last Price Modus aktivieren"
    )

else:
    # ── Kennzahlen ─────────────────────────────────────────────────────────
    n_tickers_found = results["Ticker"].nunique() if "Ticker" in results.columns else 0
    avg_crv  = results["CRV Score"].mean() if "CRV Score" in results.columns else 0
    best_crv = results["CRV Score"].max()  if "CRV Score" in results.columns else 0
    avg_yield = results["Rendite ann. %"].mean() if "Rendite ann. %" in results.columns else 0
    avg_otm   = results["OTM %"].mean() if "OTM %" in results.columns else 0

    mc = st.columns(6)
    mc[0].metric("Optionen gefunden",  len(results))
    mc[1].metric("Aktien",             n_tickers_found)
    mc[2].metric("Bester CRV",         f"{best_crv:.1f}")
    mc[3].metric("Ø CRV Score",        f"{avg_crv:.1f}")
    mc[4].metric("Ø Rendite ann.",      f"{avg_yield:.1f}%")
    mc[5].metric("Ø OTM Puffer",       f"{avg_otm:.1f}%")

    # ── Filter-Zeile ───────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns([4, 3, 3])
    with fc1:
        trend_f = st.radio("Trend-Filter (1D)", ["Alle", "↑ Aufwärts", "→ Seitwärts", "↓ Abwärts"], horizontal=True)
    with fc2:
        sort_col = sort_by if sort_by in results.columns else "CRV Score"
        if sort_by == "|Delta|" and "Delta" in results.columns:
            display_df = results.copy()
            display_df["_abs_delta"] = display_df["Delta"].abs()
            display_df = display_df.sort_values("_abs_delta").head(int(top_n)).reset_index(drop=True)
        else:
            display_df = results.sort_values(
                sort_col, ascending=(sort_by == "DTE")
            ).head(int(top_n)).reset_index(drop=True)
    with fc3:
        sector_f = st.multiselect("Sektor-Filter", sorted(results["Sektor"].unique()) if "Sektor" in results.columns else [], placeholder="Alle")

    if trend_f != "Alle" and "Trend" in display_df.columns:
        t_map = {"↑ Aufwärts": "↑", "→ Seitwärts": "→", "↓ Abwärts": "↓"}
        display_df = display_df[display_df["Trend"].str.contains(t_map.get(trend_f, ""), na=False)]
    if sector_f and "Sektor" in display_df.columns:
        display_df = display_df[display_df["Sektor"].isin(sector_f)]

    display_df["Rang"] = range(1, len(display_df) + 1)

    # CRV Medaillen
    if "CRV Score" in display_df.columns and len(display_df) > 0:
        q75 = display_df["CRV Score"].quantile(0.75)
        q50 = display_df["CRV Score"].quantile(0.50)
        display_df["⭐ CRV"] = display_df["CRV Score"].apply(
            lambda s: f"🥇 {s:.1f}" if s >= q75 else (f"🥈 {s:.1f}" if s >= q50 else f"🥉 {s:.1f}")
        )

    # Basis-Spalten
    base_cols = ["Rang", "Ticker", "Sektor", "Kurs", "Strike", "OTM %",
                 "Verfall", "DTE", "Prämie", "Prämie/Tag", "Rendite ann. %",
                 "Rendite % Laufzeit", "Rendite %/Tag",
                 "Delta", "IV %", "OI", "Trend"]
    # Tech-Spalten wenn vorhanden
    tech_cols = [c for c in ["RSI(1D)", "Stoch(1D)", "MACD(1D)", "SC Trend(1D)", "TF-Align"] if c in display_df.columns]
    show_cols = [c for c in base_cols + tech_cols + ["⭐ CRV"] if c in display_df.columns]

    col_config = {
        "Rang":          st.column_config.NumberColumn("Rang", width="small"),
        "Ticker":        st.column_config.TextColumn("Ticker", width="small"),
        "Kurs":          st.column_config.NumberColumn("Kurs", format="$%.2f"),
        "Strike":        st.column_config.NumberColumn("Strike", format="$%.2f"),
        "OTM %":         st.column_config.NumberColumn("OTM %", format="%.1f%%"),
        "Prämie":        st.column_config.NumberColumn("Prämie", format="$%.2f"),
        "Prämie/Tag":    st.column_config.NumberColumn("$/Tag", format="$%.3f"),
        "Rendite ann. %":st.column_config.NumberColumn("Rendite ann.", format="%.1f%%"),
        "Rendite % Laufzeit": st.column_config.NumberColumn("Rendite % LZ", format="%.2f%%", help="Rendite auf Laufzeit"),
        "Rendite %/Tag":      st.column_config.NumberColumn("Rendite %/Tag", format="%.3f%%", help="Rendite pro Tag"),
        "Delta":         st.column_config.NumberColumn("Δ", format="%.3f"),
        "IV %":          st.column_config.NumberColumn("IV %", format="%.1f%%"),
        "TF-Align":      st.column_config.ProgressColumn("TF Score", min_value=0, max_value=100, format="%.0f"),
        "⭐ CRV":        st.column_config.TextColumn("⭐ CRV", width="medium"),
    }

    # ── Max-Wert Hervorhebung (Gold-Highlight für Spalten-Maximum) ─────────
    HIGHLIGHT_COLS = [
        "OTM %", "Prämie", "Prämie/Tag",
        "Rendite ann. %", "Rendite % Laufzeit", "Rendite %/Tag",
        "CRV Score",
    ]
    highlight_targets = [c for c in HIGHLIGHT_COLS if c in display_df.columns]

    def _style_max(df_view: pd.DataFrame) -> pd.DataFrame:
        """Gibt Gold-Styling für den Maximalwert jeder Highlight-Spalte zurück."""
        styles = pd.DataFrame("", index=df_view.index, columns=df_view.columns)
        for col in highlight_targets:
            if col in df_view.columns and df_view[col].dtype.kind in "fiu":
                max_idx = df_view[col].idxmax()
                styles.loc[max_idx, col] = (
                    "background-color: rgba(212,168,67,0.18); "
                    "color: #d4a843; font-weight: 700;"
                )
        return styles

    view_df = display_df[show_cols].copy()
    try:
        styled = view_df.style.apply(_style_max, axis=None)
        st.dataframe(styled, use_container_width=True, height=560,
                     column_config=col_config, hide_index=True)
    except Exception:
        st.dataframe(view_df, use_container_width=True, height=560,
                     column_config=col_config, hide_index=True)

    # ── Export ─────────────────────────────────────────────────────────────
    ex1, ex2 = st.columns([2, 10])
    with ex1:
        st.download_button("📥 CSV", results.to_csv(index=False),
                           f"stillhalter_scan.csv", "text/csv", use_container_width=True)

    # ── Bubble Chart ───────────────────────────────────────────────────────
    st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)
    st.markdown("#### Chance-Risiko-Chart — OTM% vs. Rendite")
    st.caption("Blasengröße = CRV Score · Farbe = |Delta| (grün = niedriges Delta)")

    plot_df = results.head(25).copy()
    if all(c in plot_df.columns for c in ["OTM %", "Rendite ann. %", "CRV Score"]):
        delta_abs = plot_df["Delta"].abs() if "Delta" in plot_df.columns else pd.Series([0.2]*len(plot_df))
        crv_size  = (plot_df["CRV Score"].clip(1,500) / plot_df["CRV Score"].clip(1,500).max() * 44 + 8).clip(8, 50)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=plot_df["OTM %"], y=plot_df["Rendite ann. %"],
            mode="markers+text",
            text=plot_df["Ticker"] + "<br>$" + plot_df["Strike"].astype(str),
            textposition="top center",
            textfont=dict(size=9, color="#777", family="RedRose, sans-serif"),
            marker=dict(
                size=crv_size, color=delta_abs,
                colorscale=[[0,"#22c55e"],[0.5,"#f59e0b"],[1,"#ef4444"]],
                cmin=0, cmax=0.4,
                colorbar=dict(
                    title=dict(text="|Delta|", font=dict(color="#888", size=11, family="RedRose, sans-serif")),
                    tickfont=dict(color="#666", size=9),
                ),
                showscale=True, opacity=0.9,
                line=dict(color="rgba(212,168,67,0.3)", width=1),
            ),
            hovertemplate="<b>%{text}</b><br>OTM: %{x:.1f}%<br>Rendite ann.: %{y:.1f}%<extra></extra>",
        ))
        fig.add_vrect(x0=5, x1=15, fillcolor="rgba(212,168,67,0.04)", line_width=0,
                      annotation_text="Sweet Spot", annotation_font_color="#d4a843",
                      annotation_position="top left")
        fig.add_hline(y=20, line_dash="dot", line_color="rgba(212,168,67,0.3)",
                      annotation_text="20% p.a.", annotation_font_color="#d4a843",
                      annotation_position="right")
        fig.update_layout(
            height=460,
            paper_bgcolor="#0c0c0c", plot_bgcolor="#0c0c0c",
            font=dict(color="#888", family="RedRose, sans-serif", size=11),
            xaxis=dict(
                title=dict(text="OTM % (Sicherheitsabstand)", font=dict(color="#888", size=11)),
                gridcolor="#1a1a1a", zeroline=False,
            ),
            yaxis=dict(
                title=dict(text="Annualisierte Rendite %", font=dict(color="#888", size=11)),
                gridcolor="#1a1a1a", zeroline=False,
            ),
            margin=dict(l=10, r=10, t=20, b=40),
        )
        st.plotly_chart(fig, use_container_width=True)
