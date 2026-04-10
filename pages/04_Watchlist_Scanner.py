"""
Stillhalter AI App — Watchlist Scanner
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import time
import os

st.set_page_config(
    page_title="Watchlist Scanner · Stillhalter AI App",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

from data.watchlist import WATCHLIST, SECTOR_ICONS, ALL_TICKERS
from data.fetcher import market_status_text, is_market_open, fetch_price_history
from data.universes import get_universe_tickers, UNIVERSE_OPTIONS, UNIVERSE_COUNTS
from analysis.batch_screener import scan_watchlist
from analysis.multi_timeframe import (
    analyze_multi_timeframe, matches_tech_filter,
    TechFilterParams, tf_summary_row, calc_convergence_score
)
from ui.charts import render_option_mini_chart, render_payoff_diagram


@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_mini_hist(ticker: str):
    """Kurshistorie für Mini-Chart (90 Tage, gecacht)."""
    try:
        return fetch_price_history(ticker, period="3mo")
    except Exception:
        import pandas as pd
        return pd.DataFrame()

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
        f' &nbsp;·&nbsp; Watchlist 225 · S&amp;P 500 · Nasdaq 100 · Short Strangle</div>',
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

# ── Preset-Defaults ───────────────────────────────────────────────────────────
PRESETS = {
    "Konservativ 🟢": dict(dte_min=21, dte_max=45, d_min=-0.20, d_max=-0.05,
                           iv_min=0, iv_max=200, otm_min=5, otm_max=20,
                           prem_min=0.10, oi_min=50, max_spread=40.0),
    "Ausgewogen 🟡":  dict(dte_min=14, dte_max=60, d_min=-0.30, d_max=-0.05,
                           iv_min=0, iv_max=200, otm_min=3, otm_max=25,
                           prem_min=0.05, oi_min=10, max_spread=60.0),
    "Aggressiv 🔴":   dict(dte_min=7, dte_max=45, d_min=-0.40, d_max=-0.05,
                           iv_min=0, iv_max=300, otm_min=0, otm_max=30,
                           prem_min=0.01, oi_min=0, max_spread=80.0),
}

# Preset-Auswahl via Session-State
if "preset" not in st.session_state:
    st.session_state.preset = None

pc1, pc2, pc3, pc4 = st.columns([2, 2, 2, 6])
with pc1:
    if st.button("Konservativ 🟢", use_container_width=True,
                 help="DTE 21–45 · Delta ≤ 0.20 · OTM ≥ 5% · OI ≥ 50"):
        st.session_state.preset = "Konservativ 🟢"
        st.rerun()
with pc2:
    if st.button("Ausgewogen 🟡", use_container_width=True,
                 help="DTE 14–60 · Delta ≤ 0.30 · OTM ≥ 3% · OI ≥ 10"):
        st.session_state.preset = "Ausgewogen 🟡"
        st.rerun()
with pc3:
    if st.button("Aggressiv 🔴", use_container_width=True,
                 help="DTE 7–45 · Delta ≤ 0.40 · OTM ≥ 0% · OI ≥ 0"):
        st.session_state.preset = "Aggressiv 🔴"
        st.rerun()
with pc4:
    if st.session_state.preset:
        st.info(f"✅ Preset aktiv: **{st.session_state.preset}** — Filter unten sind vorbelegt")
        if st.button("✖ Preset zurücksetzen", key="reset_preset"):
            st.session_state.preset = None
            st.rerun()

# Preset-Werte laden
_p = PRESETS.get(st.session_state.preset, {})

# ── Haupt-Einstellungen ───────────────────────────────────────────────────────
with st.expander("⚙️ **SCAN-EINSTELLUNGEN & OPTIONS-FILTER**", expanded=True):
    # ── Universe & Sektor Zeile ────────────────────────────────────────────────
    urow = st.columns([3, 3, 2, 2, 2])
    with urow[0]:
        scan_universe = st.selectbox(
            "Universum",
            UNIVERSE_OPTIONS,
            help="Welche Aktien sollen gescannt werden?",
            key="scan_universe",
        )
    with urow[1]:
        # Sektor nur für eigene Watchlist verfügbar
        if "Watchlist" in scan_universe:
            sector_opts = ["Alle Sektoren (225)"] + list(WATCHLIST.keys())
            scan_sector = st.selectbox(
                "Sektor",
                sector_opts,
                format_func=lambda s: (
                    s if "Alle" in s
                    else f"{SECTOR_ICONS.get(s,'')} {s.split('.',1)[-1].strip().split('(')[0].strip()}"
                ),
            )
        else:
            scan_sector = "Alle Sektoren"
            st.selectbox("Sektor", ["Alle Komponenten"], disabled=True,
                         help="Sektor-Filter nur für eigene Watchlist verfügbar")

    # Tickers bestimmen
    if "Watchlist" in scan_universe:
        if "Alle" in scan_sector:
            scan_tickers_universe = ALL_TICKERS
        else:
            scan_tickers_universe = WATCHLIST.get(scan_sector, [])
    else:
        scan_tickers_universe = get_universe_tickers(scan_universe)

    with urow[2]:
        st.metric("Aktien im Scan", len(scan_tickers_universe))

    row1 = st.columns(5)
    with row1[0]:
        scan_strategy = st.selectbox(
            "Strategie",
            ["Cash Covered Put", "Covered Call", "Short Strangle"],
            help="Short Strangle: gleichzeitig Short PUT + Short CALL mit breiten OTM-Strikes",
        )

    # Strangle-Hinweis
    if scan_strategy == "Short Strangle":
        st.info(
            "⚡ **Short Strangle Modus** — Scanner sucht nach SHORT PUT + SHORT CALL Kombinationen "
            "auf dem gleichen Verfallstag. **OTM min/max** gilt für **beide Seiten** (Put unten, Call oben). "
            "Ideal: IV > 30%, OTM 15–40%, neutrale Marktlage oder hohe Volatilität.",
            icon="⚡",
        )
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
    row2 = st.columns(8)
    with row2[0]:
        dte_min = st.number_input("DTE min", 0, 180, _p.get("dte_min", 14))
        dte_max = st.number_input("DTE max", 1, 365, _p.get("dte_max", 60))
    with row2[1]:
        if scan_strategy == "Cash Covered Put":
            st.caption("⬇️ **Put Delta** (negativ)")
            d_min = st.number_input("Δ max (Risiko)", -1.0, 0.0,
                                    _p.get("d_min", -0.35), 0.01, format="%.2f",
                                    help="Untergrenze: z.B. -0.35 = max. 35% Ausübungswahrscheinlichkeit")
            d_max = st.number_input("Δ min (konservativ)", -1.0, 0.0,
                                    _p.get("d_max", -0.05), 0.01, format="%.2f",
                                    help="Obergrenze: z.B. -0.05 = sehr weit OTM")
        else:
            st.caption("⬆️ **Call Delta** (positiv)")
            dp_max = st.number_input("Δ max (Risiko)", 0.0, 1.0,
                                     abs(_p.get("d_min", -0.35)), 0.01, format="%.2f",
                                     help="Obergrenze: z.B. 0.35 = max. 35% Ausübungswahrscheinlichkeit")
            dp_min = st.number_input("Δ min (konservativ)", 0.0, 1.0,
                                     abs(_p.get("d_max", -0.05)), 0.01, format="%.2f",
                                     help="Untergrenze: z.B. 0.05 = sehr weit OTM")
            d_min, d_max = -dp_max, -dp_min
    with row2[2]:
        iv_min = st.number_input("IV min %", 0, 300, _p.get("iv_min", 0), step=5,
                                  help="Mindest-IV: höhere IV = höhere Prämien")
        iv_max = st.number_input("IV max %", 5, 500, _p.get("iv_max", 200), step=10)
    with row2[3]:
        _default_otm_min = 15 if scan_strategy == "Short Strangle" else _p.get("otm_min", 3)
        _default_otm_max = 40 if scan_strategy == "Short Strangle" else _p.get("otm_max", 25)
        otm_min = st.number_input("OTM min %", 0, 50, _default_otm_min,
                                   help="Strangle: für PUT (unten) und CALL (oben) gleichwertig")
        otm_max = st.number_input("OTM max %", 1, 80, _default_otm_max)
    with row2[4]:
        prem_min = st.number_input("Mind. Prämie ($)", 0.0, 20.0,
                                    _p.get("prem_min", 0.05), 0.05, format="%.2f")
        prem_day = st.number_input("Mind. Prämie/Tag ($)", 0.0, 5.0, 0.0, 0.01, format="%.3f")
        min_yield_laufzeit = st.number_input("Mind. Rendite % LZ", 0.0, 20.0, 0.0, 0.1,
                                              format="%.1f",
                                              help="Mindestrendite auf Laufzeit (% auf Strike)")
        min_yield_day_pct = st.number_input("Mind. Rendite %/Tag", 0.0, 1.0, 0.0, 0.01,
                                             format="%.2f",
                                             help="Mindestrendite pro Tag (% auf Strike)")
    with row2[5]:
        oi_min = st.number_input("Mind. Open Interest", 0, 5000,
                                  _p.get("oi_min", 5), step=5)
        min_crv = st.number_input("Mind. CRV Score", 0.0, 500.0, 0.0, 10.0, format="%.0f",
                                   help="Filtert nach Mindest-CRV Score")
    with row2[6]:
        max_spread_pct = st.number_input(
            "Max. Spread %", 0.0, 200.0, _p.get("max_spread", 60.0), 5.0, format="%.0f",
            help="Maximaler Bid/Ask-Spread als % des Mittelkurses. Niedrig = nur liquide Optionen."
        )
        st.caption("🟢 ≤15% · 🟡 ≤40% · 🔴 >40%")
    with row2[7]:
        st.markdown("<br>", unsafe_allow_html=True)
        sort_by = st.selectbox(
            "Sortierung",
            ["CRV Score", "Best Convergence", "Rendite ann. %", "Rendite % Laufzeit",
             "Rendite %/Tag", "OTM %", "Prämie/Tag", "DTE", "|Delta|"],
        )

# ── Technische Filter ─────────────────────────────────────────────────────────
with st.expander("📊 **TECHNISCHE FILTER** — RSI · Stillhalter Dual Stochastik · Stillhalter MACD Pro · Stillhalter Trend Model · Multi-Timeframe", expanded=False):

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
        st.markdown("**〽️ Stillhalter Dual Stochastik**")
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
        st.markdown("**🌊 Stillhalter MACD Pro**")
        macd_filter = st.selectbox("MACD Signal", [
            "Alle",
            "Bullish Cross (neg → pos)",
            "Bearish Cross (pos → neg)",
            "MACD > Signal (bullish)",
            "MACD < Signal (bearish)",
            "MACD Linie > 0",
        ], key="macd_f")
        macd_tf = st.selectbox("MACD Timeframe", TF_OPTIONS, index=1, key="macd_tf")
        st.caption("Cross neg→pos = starkes Bullish-Signal")

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
scan_tickers = scan_tickers_universe   # aus Universe-Selector oben
mins = max(1, len(scan_tickers) * 2 // 60)
maxs = max(2, len(scan_tickers) * 4 // 60)

tech_filter_note = " + Technische Vorab-Filterung" if use_tech_filter else ""
off_hours_mode = use_last_price and not market_open
if off_hours_mode:
    price_mode_str = "⚠️ Last Price Modus — Renditen sind Schätzwerte, kein aktiver Markt"
else:
    price_mode_str = "✅ Nur Optionen mit echtem Bid/Ask — Renditen verifiziert"
strat_note = " · ⚡ Short Strangle" if scan_strategy == "Short Strangle" else ""
st.info(
    f"**{len(scan_tickers)} Aktien** aus *{scan_universe.split('—')[-1].strip().split('(')[0].strip()}* "
    f"· Dauer: **~{mins}–{maxs} Min.**{tech_filter_note}{strat_note} · {price_mode_str}"
)

# ── Session State früh initialisieren (vor Hintergrund-Scan-Check) ───────────
for _k in ["scan_results", "scan_meta", "tf_results"]:
    if _k not in st.session_state:
        st.session_state[_k] = None

# ── Hintergrund-Scan Status anzeigen ─────────────────────────────────────────
import data.background_scan as bg_scan
_bg = bg_scan.get_state()
if _bg["running"]:
    pct  = _bg["progress"]
    done = _bg["done"]
    tot  = _bg["total"]
    cur  = _bg["current"]
    st.html(f"""
<div style='background:rgba(212,168,67,0.08);border:1px solid rgba(212,168,67,0.3);
            border-radius:10px;padding:10px 16px;margin-bottom:4px'>
    <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:0.85rem;color:#d4a843'>
        🔍 SCAN LÄUFT IM HINTERGRUND — du kannst die Seite wechseln
    </div>
    <div style='font-family:RedRose,sans-serif;font-size:0.8rem;color:#888;margin-top:4px'>
        {done}/{tot} Aktien · aktuell: <strong style='color:#f0f0f0'>{cur}</strong>
    </div>
</div>
""")
    st.progress(pct)
    if st.button("⏹ Scan abbrechen", key="btn_stop_bg"):
        bg_scan.stop_scan()
        st.rerun()
    import time as _t; _t.sleep(2); st.rerun()
elif _bg["finished_at"] and _bg["results"] is not None and not _bg["results"].empty:
    # Ergebnisse aus Hintergrund-Scan übernehmen
    if st.session_state.scan_results is None or st.session_state.scan_results.empty:
        st.session_state.scan_results = _bg["results"]
        st.session_state.scan_meta = {"strategy": _bg["strategy"], "source": "background"}

# ── Scan Buttons ──────────────────────────────────────────────────────────────
b1, b2, b3, _ = st.columns([2, 2, 2, 6])
with b1:
    start_scan_fg = st.button(f"🚀 Scan starten ({len(scan_tickers)} Ticker)", type="primary", use_container_width=True)
with b2:
    start_scan_bg = st.button(
        f"🌙 Im Hintergrund ({len(scan_tickers)})",
        use_container_width=True,
        help="Scan läuft im Hintergrund — du kannst die Seite wechseln, Scan läuft weiter",
        disabled=_bg["running"],
    )
with b3:
    if st.button("🗑️ Cache leeren", use_container_width=True):
        st.cache_data.clear()
        for key in ["scan_results", "scan_meta", "tf_results", "preset"]:
            if key in st.session_state:
                del st.session_state[key]
        st.rerun()

# Hintergrund-Scan starten
if start_scan_bg:
    off_hours_bg = use_last_price and not market_open
    started = bg_scan.start_scan(
        tickers=scan_tickers,
        strategy=scan_strategy,
        delta_min=d_min, delta_max=d_max,
        dte_min=int(dte_min), dte_max=int(dte_max),
        iv_min=iv_min / 100,
        premium_min=0.01 if off_hours_bg else prem_min,
        min_oi=0 if off_hours_bg else int(oi_min),
        otm_min=float(otm_min), otm_max=float(otm_max),
        max_spread_pct=float(max_spread_pct),
        require_valid_market=not off_hours_bg,
    )
    if started:
        st.success("✅ Hintergrund-Scan gestartet — du kannst jetzt die Seite wechseln!")
        import time as _t; _t.sleep(1); st.rerun()
    else:
        st.warning("Ein Scan läuft bereits. Bitte warten.")

start_scan = start_scan_fg

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# (Session State bereits oben initialisiert)

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
        # Schritt 2: Optionen scannen — mit Live-Anzeige
        phase_offset = 0.5 if use_tech_filter else 0.0
        phase_scale  = 0.5 if use_tech_filter else 1.0

        # ── Live-Ergebnis Platzhalter ─────────────────────────────────────
        live_count_ph = st.empty()
        live_table_ph = st.empty()
        live_partial: list = []      # akkumulierte Teil-Ergebnisse (thread-safe list)

        def _render_live(df: pd.DataFrame) -> None:
            """Zeigt die bisherigen Treffer sofort in der Tabelle."""
            n = len(df)
            t = df["Ticker"].nunique() if "Ticker" in df.columns else 0
            live_count_ph.markdown(
                f"<div style='font-family:RedRose,sans-serif;font-size:0.85rem;"
                f"color:#d4a843;padding:4px 0'>⚡ Live: <b>{n} Optionen</b> aus "
                f"<b>{t} Aktien</b> gefunden — Scan läuft...</div>",
                unsafe_allow_html=True,
            )
            # Kompakte Vorschau-Tabelle (Top 50 nach CRV)
            preview_cols = [c for c in [
                "Ticker","Sektor","Kurs","Strike","Verfall","DTE",
                "Prämie","Rendite % Laufzeit","Rendite %/Tag",
                "Delta","IV %","OTM %","CRV Score",
            ] if c in df.columns]
            top = df[preview_cols].head(50)
            live_table_ph.dataframe(
                top, use_container_width=True, hide_index=True, height=340,
            )

        def on_result(ticker: str, df: pd.DataFrame) -> None:
            """Wird nach jedem Treffer-Ticker aufgerufen."""
            live_partial.append(df)
            combined = pd.concat(live_partial, ignore_index=True)
            if "CRV Score" in combined.columns:
                combined = combined.sort_values("CRV Score", ascending=False)
            _render_live(combined)

        def on_progress(current: int, total: int, ticker: str) -> None:
            pct = phase_offset + (current / max(total, 1)) * phase_scale
            progress_bar.progress(min(pct, 1.0))
            label = "Phase 2/2" if use_tech_filter else "Scan"
            status_ph.markdown(
                f"**{label}:** `{ticker}` ({current}/{total}) — "
                f"{len(live_partial)} Aktien mit Treffern"
            )

        # Im Last-Price-Modus (Markt geschlossen): Filter automatisch lockern
        off_hours_mode        = use_last_price and not market_open
        effective_premium_min = 0.01 if off_hours_mode else prem_min
        effective_oi_min      = 0    if off_hours_mode else int(oi_min)
        # Liquiditätspflicht: während Marktzeiten nur echte Bid/Ask-Kurse
        # → Off-Hours-Modus deaktiviert diese Pflicht (lastPrice als Fallback)
        require_valid_mkt     = not off_hours_mode

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
            require_valid_market=require_valid_mkt,
            max_spread_pct=float(max_spread_pct),
            progress_callback=on_progress,
            result_callback=on_result,
        )

        # Live-Platzhalter entfernen (finale Tabelle übernimmt)
        live_count_ph.empty()
        live_table_ph.empty()

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
        # Wenn kein Tech-Filter aktiv war: TF-Daten für Ergebnis-Ticker nachladen
        if not results.empty:
            result_tickers = results["Ticker"].unique().tolist()
            missing = [t for t in result_tickers if t not in tf_cache]
            if missing:
                tf_ph = st.empty()
                tf_ph.caption(f"📊 Lade Trend-Signale für {len(missing)} Ticker...")
                for mt in missing:
                    tf_cache[mt] = analyze_multi_timeframe(mt)
                tf_ph.empty()

        if not results.empty and tf_cache:
            def add_tf_info(ticker):
                try:
                    tf = tf_cache.get(ticker)
                    if tf is None or tf.tf_1d is None:
                        return ("–", "–", "–", "–", "–")
                    d = tf.tf_1d
                    rsi_val   = d.rsi if d.rsi == d.rsi else 50.0   # NaN-guard
                    stoch_val = d.stoch_k if d.stoch_k == d.stoch_k else 50.0
                    rsi_arrow   = "⬆" if d.rsi_cross_30_up   else ("⬇" if d.rsi_cross_70_down   else "")
                    stoch_arrow = "⬆" if d.stoch_cross_20_up else ("⬇" if d.stoch_cross_80_down else "")
                    macd_str  = ("↑Cross" if d.macd_cross_bullish else
                                 "↓Cross" if d.macd_cross_bearish else
                                 "Bull"   if d.macd_bullish        else "Bear")
                    trend_str = ("↑Cross" if d.ema_cross_bullish else
                                 "↓Cross" if d.ema_cross_bearish else
                                 "Bull"   if d.ema_bullish         else "Bear")
                    align_val = tf.alignment_score if tf.alignment_score == tf.alignment_score else 0.0
                    return (
                        f"{rsi_val:.0f}{rsi_arrow}",
                        f"{stoch_val:.0f}{stoch_arrow}",
                        macd_str, trend_str,
                        f"{align_val:.0f}",
                    )
                except Exception:
                    return ("–", "–", "–", "–", "–")

            tf_cols = results["Ticker"].apply(add_tf_info)
            results["RSI(1D)"] = [x[0] for x in tf_cols]
            results["Stoch(1D)"] = [x[1] for x in tf_cols]
            results["MACD(1D)"] = [x[2] for x in tf_cols]
            results["SC Trend(1D)"] = [x[3] for x in tf_cols]
            results["TF-Align"] = [x[4] for x in tf_cols]

            # ── Best Convergence Score ──────────────────────────────────────
            conv_strategy = "call" if scan_strategy == "Covered Call" else "put"

            def _conv_score(ticker):
                try:
                    tf = tf_cache.get(ticker)
                    if tf is None:
                        return (0.0, "🔴 Entfernt")
                    c = calc_convergence_score(tf, conv_strategy)
                    return (c.score, c.label)
                except Exception:
                    return (0.0, "–")

            conv_cols = results["Ticker"].apply(_conv_score)
            results["Konvergenz"]  = [x[0] for x in conv_cols]
            results["Konv."]       = [x[1] for x in conv_cols]

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
        # P2: Memory-Lean — nur Ticker im Ergebnis cachen (nicht alle 225)
        result_keys = set(results["Ticker"].unique()) if not results.empty else set()
        st.session_state.tf_results = {k: v for k, v in tf_cache.items() if k in result_keys}

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
    # ── Konvergenz-Score nachladen falls nicht vorhanden (z.B. Hintergrund-Scan) ──
    if "Konvergenz" not in results.columns and "Ticker" in results.columns:
        _cached_tf = st.session_state.get("tf_results") or {}
        _conv_strategy = "call" if meta.get("strategy", scan_strategy) == "Covered Call" else "put"
        _missing_tf = [t for t in results["Ticker"].unique() if t not in _cached_tf]
        if _missing_tf:
            _ph = st.empty()
            _ph.caption(f"⚡ Berechne Konvergenz-Scores für {len(_missing_tf)} Ticker...")
            for _mt in _missing_tf:
                _cached_tf[_mt] = analyze_multi_timeframe(_mt)
            _ph.empty()

        def _lazy_conv(ticker):
            try:
                tf = _cached_tf.get(ticker)
                if tf is None:
                    return (0.0, "–")
                c = calc_convergence_score(tf, _conv_strategy)
                return (c.score, c.label)
            except Exception:
                return (0.0, "–")

        _cx = results["Ticker"].apply(_lazy_conv)
        results["Konvergenz"] = [x[0] for x in _cx]
        results["Konv."]      = [x[1] for x in _cx]
        st.session_state.scan_results = results
        st.session_state.tf_results = {**st.session_state.get("tf_results", {}), **_cached_tf}

    # ── Kennzahlen ─────────────────────────────────────────────────────────
    n_tickers_found = results["Ticker"].nunique() if "Ticker" in results.columns else 0
    avg_crv  = results["CRV Score"].mean() if "CRV Score" in results.columns else 0
    best_crv = results["CRV Score"].max()  if "CRV Score" in results.columns else 0
    avg_yield = results["Rendite ann. %"].mean() if "Rendite ann. %" in results.columns else 0
    avg_otm   = results["OTM %"].mean() if "OTM %" in results.columns else 0

    best_conv  = results["Konvergenz"].max()  if "Konvergenz" in results.columns else None
    mc = st.columns(6)
    mc[0].metric("Optionen gefunden",  len(results))
    mc[1].metric("Aktien",             n_tickers_found)
    mc[2].metric("Bester CRV",         f"{best_crv:.1f}")
    mc[3].metric("Ø CRV Score",        f"{avg_crv:.1f}")
    mc[4].metric("Ø Rendite ann.",      f"{avg_yield:.1f}%")
    mc[5].metric("⚡ Best Convergence", f"{best_conv:.0f}/100" if best_conv is not None else "–")

    # CRV, TF-Alignment & Konvergenz-Erklärung
    with st.expander("ℹ️ **Wie werden CRV Score, TF-Alignment & Best Convergence berechnet?**", expanded=False):
        icol1, icol2, icol3 = st.columns(3)
        with icol3:
            st.markdown("""
            **⚡ Best Convergence Score — Annäherung ans Ideal**

            Misst wie nah alle 4 Indikatoren gleichzeitig an ihrem idealen Einstiegssignal sind — auf **4H & 1D** Ebene.

            | Indikator | Short Put Ideal | Short Call Ideal |
            |-----------|----------------|-----------------|
            | **Stoch. Dual** | %K kreuzt 20 ↑ | %K kreuzt 80 ↓ |
            | **RSI** | kreuzt 30 ↑ | kreuzt 70 ↓ |
            | **Stillhalter Trendmodel** | EMA2 kreuzt EMA9 ↑ | EMA2 kreuzt EMA9 ↓ |
            | **MACD Pro** | Hist. neg → pos | Hist. pos → neg |

            Score = gewichteter Durchschnitt (1D 60% · 4H 40%)

            → **≥ 78**: 🟢 Perfekte Konvergenz — idealer Einstieg
            → **60–77**: 🟡 Sehr nah — 3-4 Indikatoren konvergieren
            → **40–59**: 🟠 Nah — 2 Indikatoren nähern sich an
            → **< 40**: 🔴 Noch entfernt
            """)
        with icol1:
            st.markdown("""
            **📐 CRV Score — Chance-Risiko-Verhältnis**

            ```
            CRV = (ann. Rendite% × √(1 + OTM%)) / (|Delta| + 0.05)
            ```
            | Faktor | Bedeutung |
            |--------|-----------|
            | **ann. Rendite %** | Prämie/Strike × 365/DTE × 100 |
            | **√(1 + OTM%)** | Sicherheitspuffer (je größer OTM, desto besser) |
            | **\|Delta\| + 0.05** | Ausübungsrisiko (je kleiner Delta, desto besser) |

            → **Hoher CRV** = hohe Prämie + großer Puffer + niedriges Delta ✅
            """)
        with icol2:
            st.markdown("""
            **🧭 TF-Alignment Score — Multi-Timeframe Trendstärke**

            ```
            Score = Σ (Timeframe-Gewicht × Bullish-Signal) × 100
            ```
            | Timeframe | Gewicht | Bullish-Bedingung |
            |-----------|---------|-------------------|
            | **1W** | 35% | SC Trend + RSI + Stoch + MACD bullish |
            | **1D** | 40% | SC Trend + RSI + Stoch + MACD bullish |
            | **4H** | 25% | SC Trend + RSI + Stoch + MACD bullish |

            → **Score ≥ 70**: Starker, bestätigter Aufwärtstrend über alle TFs ✅
            → **Score ≤ 30**: Abwärtstrend — für Cash Covered Puts aufpassen ⚠️
            """)

    # ── Filter-Zeile ───────────────────────────────────────────────────────
    fc1, fc2, fc3 = st.columns([4, 3, 3])
    with fc1:
        trend_f = st.radio("Trend-Filter (1D)", ["Alle", "↑ Aufwärts", "→ Seitwärts", "↓ Abwärts"], horizontal=True)
    with fc2:
        if sort_by == "|Delta|" and "Delta" in results.columns:
            display_df = results.copy()
            display_df["_abs_delta"] = display_df["Delta"].abs()
            display_df = display_df.sort_values("_abs_delta").head(int(top_n)).reset_index(drop=True)
        elif sort_by == "Best Convergence" and "Konvergenz" in results.columns:
            display_df = results.sort_values("Konvergenz", ascending=False).head(int(top_n)).reset_index(drop=True)
        else:
            sort_col = sort_by if sort_by in results.columns else "CRV Score"
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

    # ── Top-Rang als Medaillen-Spalte ─────────────────────────────────────────
    def _medal(i: int) -> str:
        return {1: "🥇 Top 1", 2: "🥈 Top 2", 3: "🥉 Top 3"}.get(i, f"#{i}")
    display_df["Top"] = display_df["Rang"].apply(_medal)

    # Liq.-Spalte kommt bereits aus batch_screener — nur Fallback wenn fehlt
    if "Liq." not in display_df.columns:
        display_df["Liq."] = "⚪"

    # ── CRV Medaillen ─────────────────────────────────────────────────────────
    if "CRV Score" in display_df.columns and len(display_df) > 0:
        q75 = display_df["CRV Score"].quantile(0.75)
        q50 = display_df["CRV Score"].quantile(0.50)
        display_df["⭐ CRV"] = display_df["CRV Score"].apply(
            lambda s: f"🥇 {s:.1f}" if s >= q75 else (f"🥈 {s:.1f}" if s >= q50 else f"🥉 {s:.1f}")
        )

    # Spalten je nach Strategie — Top + Liq. immer zuerst
    is_strangle = "Strangle" in meta.get("strategy", scan_strategy)
    if is_strangle and "Strike PUT" in display_df.columns:
        base_cols = ["Top", "Liq.", "Ticker", "Sektor", "Kurs",
                     "Strike PUT", "Strike CALL", "OTM% PUT", "OTM% CALL", "Range %",
                     "Verfall", "DTE",
                     "Prämie gesamt", "Prämie PUT", "Prämie CALL", "Prämie/Tag",
                     "Rendite ann. %", "Rendite % Laufzeit",
                     "Delta PUT", "Delta CALL", "IV %", "IV Rank",
                     "Break-even Low", "Break-even High",
                     "Trend", "⚠️ Earnings"]
    else:
        base_cols = ["Top", "Liq.", "Ticker", "Sektor", "Kurs", "Strike", "OTM %",
                     "Verfall", "DTE", "Prämie", "Bid", "Ask", "Kursquelle", "Spread %",
                     "Prämie/Tag", "Rendite ann. %", "Rendite % Laufzeit", "Rendite %/Tag",
                     "Delta", "Theta/Tag", "IV %", "IV Rank", "OI", "Volumen",
                     "Trend", "⚠️ Earnings"]
    # Tech-Spalten wenn vorhanden
    tech_cols = [c for c in ["RSI(1D)", "Stoch(1D)", "MACD(1D)", "SC Trend(1D)", "TF-Align"] if c in display_df.columns]
    # Konvergenz-Spalten
    conv_cols_show = [c for c in ["Konvergenz", "Konv."] if c in display_df.columns]
    show_cols = [c for c in base_cols + tech_cols + conv_cols_show + ["⭐ CRV"] if c in display_df.columns]

    col_config = {
        "Top":           st.column_config.TextColumn("Top", width="small",
                                                      help="Rang nach gewählter Sortierung"),
        "Liq.":          st.column_config.TextColumn("Liq.", width="small",
                                                      help="🟢 Spread ≤5% · 🟡 5–15% · 🔴 >15%"),
        "Ticker":        st.column_config.TextColumn("Ticker", width="small"),
        "Kurs":          st.column_config.NumberColumn("Kurs", format="$%.2f"),
        "Strike":        st.column_config.NumberColumn("Strike", format="$%.2f"),
        "OTM %":         st.column_config.NumberColumn("OTM %", format="%.1f%%"),
        "Prämie":        st.column_config.NumberColumn("Prämie", format="$%.2f"),
        "Bid":           st.column_config.NumberColumn("Bid",   format="$%.2f",
                                                        help="Geldkurs (Bid) — was du beim Verkauf bekommst"),
        "Ask":           st.column_config.NumberColumn("Ask",   format="$%.2f",
                                                        help="Briefkurs (Ask) — was der Käufer bezahlt"),
        "Prämie/Tag":    st.column_config.NumberColumn("$/Tag", format="$%.3f"),
        "Rendite ann. %":st.column_config.NumberColumn("Rendite ann.", format="%.1f%%"),
        "Rendite % Laufzeit": st.column_config.NumberColumn("Rendite % LZ", format="%.2f%%", help="Rendite auf Laufzeit"),
        "Rendite %/Tag":      st.column_config.NumberColumn("Rendite %/Tag", format="%.3f%%", help="Rendite pro Tag"),
        "Delta":         st.column_config.NumberColumn("Δ", format="%.3f"),
        "Theta/Tag":     st.column_config.NumberColumn("Θ/Tag", format="%.3f",
                                                        help="Theta pro Tag — Zeitwertverlust (negativ für Optionskäufer, positiv für Stillhalter)"),
        "IV %":          st.column_config.NumberColumn("IV %", format="%.1f%%"),
        "TF-Align":      st.column_config.ProgressColumn("TF Score", min_value=0, max_value=100, format="%.0f"),
        "⭐ CRV":        st.column_config.TextColumn("⭐ CRV", width="medium"),
        "Kursquelle":   st.column_config.TextColumn("Kurs", width="small",
                                                       help="Mid = Bid/Ask Midprice (echt) · Last = letzter Handel (geschätzt, Off-Hours)"),
        "Spread %":     st.column_config.NumberColumn("Spread %", format="%.1f%%",
                                                       help="Bid/Ask Spread — niedrig = liquide · leer = kein aktiver Markt"),
        "IV Rank":      st.column_config.TextColumn("IV Rank", width="small",
                                                     help="IV Rank 0–100: zeigt ob IV aktuell hoch/niedrig ist (52-Wochen HV-Proxy)"),
        "Volumen":      st.column_config.NumberColumn("Vol.", format="%d",
                                                       help="Handelsvolumen der Option heute"),
        "⚠️ Earnings":  st.column_config.TextColumn("Earnings", width="medium",
                                                      help="⚠️ Earnings-Termin fällt in die Laufzeit der Option"),
        # Konvergenz-Spalten
        "Konvergenz": st.column_config.ProgressColumn(
            "⚡ Konvergenz", min_value=0, max_value=100, format="%.0f",
            help="Best Convergence 0–100: Annäherung aller 7 Indikatoren an idealen Einstiegszeitpunkt (4H · 1D)"
        ),
        "Konv.": st.column_config.TextColumn("Konv.", width="small"),
    }

    # ── Styling: Top-3 Zeilen + Spalten-Max/Min ────────────────────────────
    HIGHLIGHT_MAX = ["OTM %", "Prämie", "Prämie/Tag",
                     "Rendite ann. %", "Rendite % Laufzeit", "Rendite %/Tag", "⭐ CRV"]
    HIGHLIGHT_MIN = ["Delta", "Spread %"]    # kleinste = beste
    hl_max = [c for c in HIGHLIGHT_MAX if c in display_df.columns]
    hl_min = [c for c in HIGHLIGHT_MIN  if c in display_df.columns]

    def _style_scanner(df_view: pd.DataFrame) -> pd.DataFrame:
        styles = pd.DataFrame("", index=df_view.index, columns=df_view.columns)
        # Top-3 Zeilen farbig hinterlegen
        row_bg = [
            "background-color:rgba(212,168,67,0.18);",   # 🥇 Gold
            "background-color:rgba(160,160,180,0.12);",  # 🥈 Silber
            "background-color:rgba(180,130,80,0.10);",   # 🥉 Bronze
        ]
        for i in range(min(3, len(df_view))):
            styles.iloc[i] = row_bg[i]
        # Liq.-Spalte: grüne/gelbe/rote Hinterlegung
        if "Liq." in df_view.columns:
            for idx, val in df_view["Liq."].items():
                if val == "🟢":
                    styles.loc[idx, "Liq."] = "background-color:rgba(34,197,94,0.15);"
                elif val == "🟡":
                    styles.loc[idx, "Liq."] = "background-color:rgba(234,179,8,0.15);"
                elif val == "🔴":
                    styles.loc[idx, "Liq."] = "background-color:rgba(239,68,68,0.15);"
        # Spalten-Maxima gold
        for col in hl_max:
            if col in df_view.columns and df_view[col].dtype.kind in "fiu":
                try:
                    idx = df_view[col].idxmax()
                    styles.loc[idx, col] = (
                        "background-color:rgba(212,168,67,0.28);"
                        "color:#d4a843;font-weight:700;"
                    )
                except Exception:
                    pass
        # Spalten-Minima grün (niedrigster positiver Wert)
        for col in hl_min:
            if col in df_view.columns and df_view[col].dtype.kind in "fiu":
                try:
                    valid = df_view[col].replace(0, np.nan).dropna()
                    if not valid.empty:
                        styles.loc[valid.idxmin(), col] = (
                            "background-color:rgba(34,197,94,0.15);"
                            "color:#22c55e;font-weight:700;"
                        )
                except Exception:
                    pass
        return styles

    view_df = display_df[show_cols].copy()
    try:
        styled = view_df.style.apply(_style_scanner, axis=None)
        _scan_event = st.dataframe(
            styled, use_container_width=True, height=480,
            column_config=col_config, hide_index=True,
            on_select="rerun", selection_mode="single-row",
            key="scan_table_sel",
        )
    except Exception:
        _scan_event = st.dataframe(
            view_df, use_container_width=True, height=480,
            column_config=col_config, hide_index=True,
            on_select="rerun", selection_mode="single-row",
            key="scan_table_sel_fb",
        )

    st.caption("💡 Zeile anklicken → Mini-Chart mit Payoff-Overlay")

    # ── Mini-Chart bei Zeilenauswahl ──────────────────────────────────────
    _scan_sel = (getattr(_scan_event, "selection", None) or {})
    _scan_sel_rows = _scan_sel.get("rows", []) if isinstance(_scan_sel, dict) else getattr(_scan_sel, "rows", [])
    if _scan_sel_rows:
        _scan_idx = _scan_sel_rows[0]
        if _scan_idx < len(view_df):
            _r = view_df.iloc[_scan_idx]
            _tkr     = str(_r.get("Ticker", ""))
            _kurs    = float(_r.get("Kurs",    0) or 0)
            _strike  = float(_r.get("Strike",  0) or 0)
            _premium = float(_r.get("Prämie",  0) or 0)
            _dte     = int(_r.get("DTE",      30) or 30)
            _iv_pct  = float(_r.get("IV %",   30) or 30)
            _expiry  = str(_r.get("Verfall",  ""))
            # Optionstyp aus Strategie ableiten
            _is_call  = "Call" in meta.get("strategy", scan_strategy)
            _opt_type = "call" if _is_call else "put"

            if _tkr and _strike > 0 and _premium > 0:
                st.markdown("---")
                _mc1, _mc2 = st.columns([3, 2])
                with _mc1:
                    _mini_hist = _fetch_mini_hist(_tkr)
                    if not _mini_hist.empty and _kurs > 0:
                        fig_mini = render_option_mini_chart(
                            hist=_mini_hist,
                            ticker=_tkr,
                            current_price=_kurs,
                            strike=_strike,
                            premium=_premium,
                            dte=_dte,
                            iv_pct=_iv_pct,
                            option_type=_opt_type,
                            expiry_date=_expiry,
                        )
                        st.plotly_chart(fig_mini, use_container_width=True,
                                        config={"displayModeBar": False})
                with _mc2:
                    if _kurs > 0:
                        fig_pay = render_payoff_diagram(
                            _kurs, _strike, _premium,
                            _opt_type, _tkr, _dte,
                        )
                        fig_pay.update_layout(height=260, margin=dict(l=5,r=5,t=45,b=30))
                        st.plotly_chart(fig_pay, use_container_width=True,
                                        config={"displayModeBar": False})

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
                    title="|Delta|",
                    tickcolor="#666",
                    ticklen=4,
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
