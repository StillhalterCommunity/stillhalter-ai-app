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
    TechFilterParams, tf_summary_row,
    calc_convergence_score, calc_convergence_score_dte,
)
from ui.charts import render_option_mini_chart, render_payoff_diagram
from data.preset_manager import load_presets, save_preset, delete_preset, get_preset


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

# ── Notfall-Cache-Reset (global erreichbar) ───────────────────────────────────
with st.expander("⚙️ Keine Daten? Cache komplett zurücksetzen", expanded=False):
    st.markdown(
        "Wenn **nirgends** Daten erscheinen (Scanner, Aktienanalyse, Fundamentalanalyse) "
        "liegt es meist an gespeicherten leeren Ergebnissen im Cache. "
        "Hier alles auf einmal zurücksetzen:"
    )
    _rc1, _rc2 = st.columns(2)
    with _rc1:
        if st.button("🗑️ Alle Caches leeren (App + Disk)", type="primary", use_container_width=True,
                      key="btn_global_cache_clear"):
            st.cache_data.clear()
            try:
                from data import _persistent_cache as _pc2
                _n = _pc2.clear_all()
                st.success(f"✅ In-Memory + Disk-Cache geleert ({_n} Dateien). Daten werden neu geladen.")
            except Exception:
                st.success("✅ In-Memory-Cache geleert. Daten werden neu geladen.")
            for _k in ["scan_results", "scan_meta", "tf_results", "scan_running"]:
                if _k in st.session_state:
                    del st.session_state[_k]
            st.rerun()
    with _rc2:
        st.caption(
            "Danach einen neuen Scan starten oder die Seite neu laden. "
            "Alle Daten werden frisch von Yahoo Finance abgerufen."
        )

# ── Off-Hours Hinweis ─────────────────────────────────────────────────────────
if not market_open:
    st.info(
        "⏰ **Markt geschlossen** — Last Price Modus ist automatisch aktiviert. "
        "Der Scanner nutzt den letzten Handelskurs. Prämien können leicht von Live-Kursen abweichen.",
        icon="💡",
    )

# ── Benutzerdefinierte Presets (gespeichert in data/user_presets.json) ─────────
_user_presets = load_presets()
if _user_presets:
    _preset_names = list(_user_presets.keys())
    _up1, _up2, _up3 = st.columns([3, 1, 8])
    with _up1:
        _selected_user_preset = st.selectbox(
            "💾 Gespeicherte Konfiguration laden",
            ["— Auswählen —"] + _preset_names,
            key="load_user_preset",
        )
    with _up2:
        st.markdown("<br>", unsafe_allow_html=True)
        if _selected_user_preset != "— Auswählen —":
            if st.button("📂 Laden", use_container_width=True, key="btn_load_preset"):
                _cfg = get_preset(_selected_user_preset)
                if _cfg:
                    for _k, _v in _cfg.items():
                        st.session_state[_k] = _v
                    st.success(f"✅ Konfiguration **{_selected_user_preset}** geladen!")
                    st.rerun()
            if st.button("🗑️ Löschen", use_container_width=True, key="btn_del_preset"):
                delete_preset(_selected_user_preset)
                st.success(f"✅ **{_selected_user_preset}** gelöscht.")
                st.rerun()

st.markdown('<div style="height:4px"></div>', unsafe_allow_html=True)

# ── Neue Konfiguration speichern ──────────────────────────────────────────────
with st.expander("💾 **KONFIGURATION SPEICHERN** — Filter-Presets für Kunden/Strategien", expanded=False):
    sp1, sp2 = st.columns([3, 1])
    with sp1:
        _preset_save_name = st.text_input(
            "Name der Konfiguration",
            placeholder="z.B. Stefan – Konservativ, Kundin Maria, High IV Aggressiv…",
            key="preset_save_name",
        )
    with sp2:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("💾 Jetzt speichern", use_container_width=True, key="btn_save_preset", type="primary"):
            if _preset_save_name and _preset_save_name.strip():
                # Aktuelle Einstellungen aus Session State sammeln
                _save_cfg = {}
                _save_keys = [
                    "scan_universe", "ema_f", "ema_tf", "rsi_f", "rsi_tf",
                    "stoch_f", "stoch_tf", "macd_f", "macd_tf",
                    "filter_mode", "min_conv_score", "trend_mode_scan",
                ]
                for _sk in _save_keys:
                    if _sk in st.session_state:
                        _save_cfg[_sk] = st.session_state[_sk]
                # Option-Parameter aus aktuellen Widget-Werten
                _save_cfg["_note"] = f"Gespeichert am {__import__('datetime').datetime.now().strftime('%d.%m.%Y %H:%M')}"
                if save_preset(_preset_save_name.strip(), _save_cfg):
                    st.success(f"✅ Konfiguration **{_preset_save_name.strip()}** gespeichert!")
                    st.rerun()
            else:
                st.warning("Bitte einen Namen eingeben.")
    st.markdown("""
    <div style='color:#666;font-size:0.8rem'>
    💡 Es werden gespeichert: Universum, alle technischen Filter (Modus, Indikatoren, Timeframes, Score).
    Option-Parameter (DTE, Delta, IV, Prämie) werden mit dem Preset geladen, wenn sie beim Speichern aktiv waren.
    </div>
    """, unsafe_allow_html=True)

# ── Preset-Defaults ───────────────────────────────────────────────────────────
PRESETS = {
    # ── Klassische Presets ────────────────────────────────────────────────────
    "Konservativ 🟢": dict(dte_min=21, dte_max=45, d_min=-0.20, d_max=-0.05,
                           iv_min=0, iv_max=200, otm_min=5, otm_max=20,
                           prem_min=0.10, oi_min=50, max_spread=40.0,
                           prem_pct_min=0.0),
    "Ausgewogen 🟡":  dict(dte_min=14, dte_max=60, d_min=-0.30, d_max=-0.05,
                           iv_min=0, iv_max=200, otm_min=3, otm_max=25,
                           prem_min=0.05, oi_min=10, max_spread=60.0,
                           prem_pct_min=0.0),
    "Aggressiv 🔴":   dict(dte_min=7, dte_max=45, d_min=-0.40, d_max=-0.05,
                           iv_min=0, iv_max=300, otm_min=0, otm_max=30,
                           prem_min=0.01, oi_min=0, max_spread=80.0,
                           prem_pct_min=0.0),
    # ── IV-basierte Presets ───────────────────────────────────────────────────
    "Low IV 📘":  dict(dte_min=1, dte_max=42, d_min=-0.25, d_max=-0.05,
                       iv_min=0,  iv_max=30,  otm_min=3,  otm_max=15,
                       prem_min=0.05, oi_min=10, max_spread=50.0,
                       prem_pct_min=0.4),
    "Mid IV 📙":  dict(dte_min=1, dte_max=42, d_min=-0.35, d_max=-0.05,
                       iv_min=30, iv_max=60,  otm_min=5,  otm_max=20,
                       prem_min=0.05, oi_min=10, max_spread=60.0,
                       prem_pct_min=0.7),
    "High IV 📕": dict(dte_min=1, dte_max=42, d_min=-0.45, d_max=-0.05,
                       iv_min=60, iv_max=999, otm_min=7,  otm_max=30,
                       prem_min=0.05, oi_min=5,  max_spread=80.0,
                       prem_pct_min=1.0),
}

# Preset-Auswahl via Session-State
if "preset" not in st.session_state:
    st.session_state.preset = None

# ── Zeile 1: Klassische Presets ───────────────────────────────────────────────
st.markdown("<div style='font-size:0.72rem;color:#555;margin-bottom:4px'>Klassisch</div>",
            unsafe_allow_html=True)
pc1, pc2, pc3, pc_gap = st.columns([2, 2, 2, 6])
with pc1:
    if st.button("Konservativ 🟢", use_container_width=True,
                 help="DTE 21–45 · Delta ≤ 0.20 · OTM 5–20% · OI ≥ 50"):
        st.session_state.preset = "Konservativ 🟢"; st.rerun()
with pc2:
    if st.button("Ausgewogen 🟡", use_container_width=True,
                 help="DTE 14–60 · Delta ≤ 0.30 · OTM 3–25% · OI ≥ 10"):
        st.session_state.preset = "Ausgewogen 🟡"; st.rerun()
with pc3:
    if st.button("Aggressiv 🔴", use_container_width=True,
                 help="DTE 7–45 · Delta ≤ 0.40 · OTM 0–30% · OI ≥ 0"):
        st.session_state.preset = "Aggressiv 🔴"; st.rerun()

# ── Zeile 2: IV-Presets ────────────────────────────────────────────────────────
st.markdown("<div style='font-size:0.72rem;color:#555;margin:6px 0 4px'>IV-Kategorie</div>",
            unsafe_allow_html=True)
iv1, iv2, iv3, iv_gap = st.columns([2, 2, 2, 6])
with iv1:
    if st.button("Low IV 📘", use_container_width=True,
                 help="IV 0–30% · DTE 1–42 · OTM 3–15% · Min. 0,4% Rendite/LZ · Delta ≤ 0.25"):
        st.session_state.preset = "Low IV 📘"; st.rerun()
with iv2:
    if st.button("Mid IV 📙", use_container_width=True,
                 help="IV 30–60% · DTE 1–42 · OTM 5–20% · Min. 0,7% Rendite/LZ · Delta ≤ 0.35"):
        st.session_state.preset = "Mid IV 📙"; st.rerun()
with iv3:
    if st.button("High IV 📕", use_container_width=True,
                 help="IV >60% · DTE 1–42 · OTM 7–30% · Min. 1,0% Rendite/LZ · Delta ≤ 0.45"):
        st.session_state.preset = "High IV 📕"; st.rerun()

# ── Preset-Status ─────────────────────────────────────────────────────────────
if st.session_state.preset:
    _pname = st.session_state.preset
    _pdata = PRESETS[_pname]
    _iv_label = (f"IV {_pdata['iv_min']}–{_pdata['iv_max']}% · "
                 if _pdata.get("iv_max", 999) < 999 else f"IV >{_pdata['iv_min']}% · ")
    _pct_label = (f" · Min. {_pdata['prem_pct_min']}% Rendite/LZ"
                  if _pdata.get("prem_pct_min", 0) > 0 else "")
    st.info(
        f"✅ **{_pname}** aktiv — "
        f"{_iv_label}DTE {_pdata['dte_min']}–{_pdata['dte_max']} · "
        f"OTM {_pdata['otm_min']}–{_pdata['otm_max']}% · "
        f"Delta ≤ {abs(_pdata['d_min'])}{_pct_label}"
    )
    if st.button("✖ Preset zurücksetzen", key="reset_preset"):
        st.session_state.preset = None; st.rerun()

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
        # Markt geschlossen → Last Price immer aktiv (kann deaktiviert werden)
        _last_price_default = (not market_open) or st.session_state.get("use_last_price_override", False)
        use_last_price = st.checkbox(
            "Last Price verwenden",
            value=_last_price_default,
            help="Außerhalb der Börsenzeiten automatisch aktiv — nutzt letzten Handelspreis statt Bid/Ask",
        )
        if not market_open and not use_last_price:
            st.caption("⚠️ Markt geschlossen — aktiviere Last Price für Ergebnisse")

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
        iv_max = st.number_input("IV max %", 5, 999, _p.get("iv_max", 200), step=10)
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
        min_yield_laufzeit = st.number_input("Mind. Rendite % LZ", 0.0, 20.0,
                                              _p.get("prem_pct_min", 0.0), 0.1,
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

    # ── Earnings-Filter ───────────────────────────────────────────────────────
    earn_row = st.columns([3, 9])
    with earn_row[0]:
        exclude_earnings = st.checkbox(
            "📅 Earnings in Laufzeit ausschließen",
            value=False,
            help=(
                "Filtert Optionen heraus, bei denen ein Earnings-Termin "
                "innerhalb der Laufzeit liegt. Earnings erhöhen die IV und "
                "können die Prämie stark beeinflussen."
            ),
        )
    with earn_row[1]:
        if exclude_earnings:
            st.info(
                "🚫 **Earnings-Filter aktiv** — Optionen mit Earnings-Termin "
                "innerhalb der Laufzeit werden ausgeschlossen.",
                icon="📅",
            )

# ── Technische Filter ─────────────────────────────────────────────────────────
with st.expander("📊 **TECHNISCHE FILTER** — RSI · Dual Stochastik · MACD Pro · Trend Model · Score-basiert", expanded=False):

    TF_OPTIONS = ["4H", "1D", "1W", "Alle TFs"]

    # ── Filter-Modus ──────────────────────────────────────────────────────────
    fm1, fm2, fm3 = st.columns([3, 3, 6])
    with fm1:
        filter_mode = st.selectbox(
            "🎛️ Filter-Modus",
            ["AND — alle müssen passen", "OR — mindestens einer", "SCORE — Score-basiert ★"],
            index=2,
            key="filter_mode",
            help=(
                "AND: Alle aktivierten Filter müssen gleichzeitig erfüllt sein (streng, oft 0 Ergebnisse)\n"
                "OR: Mindestens einer der aktivierten Filter muss passen (flexibler)\n"
                "SCORE ★: Nutzt den Konvergenz-Score (0-100) — berücksichtigt zeitliche Nähe zum Signal automatisch"
            ),
        )
    _fmode = "AND" if filter_mode.startswith("AND") else ("OR" if filter_mode.startswith("OR") else "SCORE")

    with fm2:
        if _fmode == "SCORE":
            min_conv_score = st.slider(
                "Min. Konvergenz-Score",
                0, 100, 0, 5,
                key="min_conv_score",
                help=(
                    "0 = kein Mindest-Score (alle Ticker)\n"
                    "40+ = Indikatoren nähern sich dem Signal an\n"
                    "60+ = Sehr nah am idealen Einstieg\n"
                    "78+ = Perfekte Konvergenz (selten)"
                ),
            )
        else:
            min_conv_score = 0.0

    if _fmode == "SCORE":
        st.markdown("""
        <div style='color:#888;font-size:0.82rem;margin-bottom:12px;background:rgba(212,168,67,0.06);
                    padding:8px 12px;border-radius:6px;border-left:3px solid rgba(212,168,67,0.4)'>
        ★ <b>Score-Modus aktiv</b> — MACD-Kreuzung von vor 2–3 Tagen, RSI nah an 30, Stochastik nah an 20
        werden alle berücksichtigt und in einen Gesamt-Score (0–100) umgerechnet.<br>
        Einzelne Filter unten sind im Score-Modus <b>optional</b> (fungieren als OR-Zusatzbedingung, nicht als harter Filter).
        </div>
        """, unsafe_allow_html=True)
    elif _fmode == "AND":
        st.markdown("""
        <div style='color:#888;font-size:0.82rem;margin-bottom:12px'>
        AND-Modus: Alle aktivierten Filter müssen gleichzeitig erfüllt sein. Bei vielen kombinierten Signalen
        können Ergebnisse auf 0 sinken — dann Score-Modus empfohlen.
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style='color:#888;font-size:0.82rem;margin-bottom:12px'>
        OR-Modus: Mindestens einer der aktivierten Filter muss erfüllt sein. Flexibler als AND.
        </div>
        """, unsafe_allow_html=True)

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
        filter_mode=_fmode,
        min_convergence_score=float(min_conv_score),
    )

    use_tech_filter = any([
        ema_filter != "Alle", rsi_filter != "Alle",
        stoch_filter != "Alle", macd_filter != "Alle",
        require_align, min_conv_score > 0,
    ])

# ── Ticker Liste ──────────────────────────────────────────────────────────────
scan_tickers = scan_tickers_universe   # aus Universe-Selector oben
try:
    from data.fetcher import USE_MASSIVE as _USE_MASSIVE
except Exception:
    _USE_MASSIVE = False
if _USE_MASSIVE:
    # Optionsketten kommen aus dem Tagescache → deutlich schneller
    mins = 1
    maxs = max(2, len(scan_tickers) // 60)
    _cache_note = " · liest aus Tagescache"
else:
    mins = max(1, len(scan_tickers) * 2 // 60)
    maxs = max(2, len(scan_tickers) * 4 // 60)
    _cache_note = ""

tech_filter_note = " + Technische Vorab-Filterung" if use_tech_filter else ""
off_hours_mode = use_last_price and not market_open
if off_hours_mode:
    price_mode_str = "⚠️ Last Price Modus — Renditen sind Schätzwerte, kein aktiver Markt"
else:
    price_mode_str = "✅ Nur Optionen mit echtem Bid/Ask — Renditen verifiziert"
strat_note = " · ⚡ Short Strangle" if scan_strategy == "Short Strangle" else ""
st.info(
    f"**{len(scan_tickers)} Aktien** aus *{scan_universe.split('—')[-1].strip().split('(')[0].strip()}* "
    f"· Dauer: **~{mins}–{maxs} Min.**{_cache_note}{tech_filter_note}{strat_note} · {price_mode_str}"
)

# ── Session State früh initialisieren (vor Hintergrund-Scan-Check) ───────────
for _k in ["scan_results", "scan_meta", "tf_results", "scan_running"]:
    if _k not in st.session_state:
        st.session_state[_k] = None

# ── Letzten Scan aus Cache wiederherstellen (nach Browser-Refresh) ────────────
# Quelle 1: persistenter Tages-Prefetch-Scan (Volume), Quelle 2: lokaler pkl-Cache
if st.session_state.scan_results is None and not st.session_state.get("scan_running"):
    import datetime as _dt
    _restored = False
    # 1) Standard-Scan aus dem Tages-Prefetch (überlebt Neustarts via Volume)
    try:
        from data import _persistent_cache as _dc
        _pf_scan = _dc.load("scan_default", max_age_hours=24)
        if _pf_scan and _pf_scan.get("results") is not None and not _pf_scan["results"].empty:
            _age_h = (_dt.datetime.now() - _pf_scan["timestamp"]).total_seconds() / 3600
            st.session_state.scan_results = _pf_scan["results"]
            st.session_state.scan_meta = {
                "strategy": _pf_scan.get("strategy", ""),
                "source": "tagescache",
                "cached_at": _pf_scan["timestamp"].strftime("%d.%m. %H:%M"),
                "age_h": round(_age_h, 1),
            }
            _restored = True
    except Exception:
        pass
    # 2) Fallback: lokaler pkl-Cache vom letzten manuellen Scan
    if not _restored:
        try:
            import pickle as _pickle
            _cache_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "last_scan_cache.pkl")
            if os.path.exists(_cache_path):
                with open(_cache_path, "rb") as _f:
                    _cached = _pickle.load(_f)
                _age_h = (_dt.datetime.now() - _cached["timestamp"]).total_seconds() / 3600
                if _age_h < 24:
                    st.session_state.scan_results = _cached["results"]
                    st.session_state.scan_meta = {
                        "strategy": _cached.get("strategy", ""),
                        "source": "cache",
                        "cached_at": _cached["timestamp"].strftime("%d.%m. %H:%M"),
                        "age_h": round(_age_h, 1),
                    }
        except Exception:
            pass

# ── Unterbrochenen Scan aufräumen ─────────────────────────────────────────────
# Wenn scan_running=True aber der Button nicht geklickt wurde, wurde der
# Scan durch eine Filteränderung unterbrochen → State zurücksetzen damit
# der Benutzer ohne Seitenaktualisierung neu starten kann.
if st.session_state.get("scan_running"):
    st.session_state.scan_running = False
    st.session_state.scan_results = None

# ── Hintergrund-Scan Status anzeigen ─────────────────────────────────────────
import data.background_scan as bg_scan
_bg = bg_scan.get_state()
_bg_poll_needed = False   # Polling-Flag: rerun erst am Ende, NACH Buttons!

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
    # ⚠️  KEIN sleep+rerun hier — Button-Klicks würden sonst verschluckt!
    # Das Polling passiert am Seitenende (nach allen Buttons).
    _bg_poll_needed = True
elif _bg["finished_at"] and _bg["results"] is not None and not _bg["results"].empty:
    # Ergebnisse aus Hintergrund-Scan übernehmen
    if st.session_state.scan_results is None or st.session_state.scan_results.empty:
        st.session_state.scan_results = _bg["results"]
        st.session_state.scan_meta = {"strategy": _bg["strategy"], "source": "background"}

# ── Scan Buttons ──────────────────────────────────────────────────────────────
# Bei großen Universen blockiert der synchrone Vordergrund-Scan den Streamlit-
# Worker (→ „keine Reaktion / weiße Seite"). Hintergrund-Scan empfehlen.
if len(scan_tickers) > 60:
    st.info(
        f"💡 **{len(scan_tickers)} Ticker** — für große Scans bitte **🌙 Im Hintergrund** "
        "nutzen. Der Vordergrund-Scan blockiert die Seite, bis er fertig ist."
    )
b1, b2, b3, b4, _ = st.columns([2, 2, 2, 2, 4])
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
with b4:
    if st.button("🔄 Scanner-Reset", use_container_width=True,
                 help="Setzt einen hängenden/abgebrochenen Scan zurück (auch für andere Nutzer)"):
        bg_scan.force_reset()
        st.session_state.scan_running = False
        st.success("✅ Scanner zurückgesetzt — du kannst neu scannen.")
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
        exclude_earnings=exclude_earnings,
    )
    if started:
        st.success("✅ Hintergrund-Scan gestartet — du kannst jetzt die Seite wechseln!")
        import time as _t; _t.sleep(1); st.rerun()
    else:
        st.warning("Ein Scan läuft bereits. Bitte warten.")

start_scan = start_scan_fg

# ── Scan-Verlauf anzeigen ────────────────────────────────────────────────────
try:
    import json as _json_hist, datetime as _dt_hist
    _hist_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "scan_history.json")
    if os.path.exists(_hist_path):
        with open(_hist_path, "r", encoding="utf-8") as _hf_r:
            _scan_hist = _json_hist.load(_hf_r)
        if _scan_hist:
            with st.expander(f"📋 Scan-Verlauf ({len(_scan_hist)} Einträge)", expanded=False):
                for _he in _scan_hist[:10]:
                    _he_ts = _dt_hist.datetime.fromisoformat(_he["ts"]).strftime("%d.%m. %H:%M")
                    st.caption(
                        f"**{_he_ts}** — {_he.get('strategy','?')} · "
                        f"{_he.get('sector','?')} · "
                        f"{_he.get('n_results',0)} Treffer aus {_he.get('n_tickers',0)} Aktien"
                    )
except Exception:
    pass

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# (Session State bereits oben initialisiert)

# ── Scan ausführen ────────────────────────────────────────────────────────────
if start_scan:
    # Scan-Status setzen: ermöglicht saubere Erkennung bei Unterbrechung
    st.session_state.scan_running = True
    # Vorherige Ergebnisse löschen (auch von unterbrochenen Scans)
    st.session_state.scan_results = None

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
        st.session_state.scan_running = False
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

        try:
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
                exclude_earnings=exclude_earnings,
                progress_callback=on_progress,
                result_callback=on_result,
            )
        except Exception as _scan_err:
            st.session_state.scan_running = False
            st.error(f"⚠️ Scan-Fehler: {type(_scan_err).__name__}: {_scan_err}")
            import traceback as _tb
            with st.expander("🔧 Technische Details (für Diagnose)"):
                st.code(_tb.format_exc())
            results = pd.DataFrame()

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

            # ── DTE-gewichtete Konvergenz + Breakdown ──────────────────────
            conv_strategy = "call" if scan_strategy == "Covered Call" else "put"

            def _conv_score_dte(row):
                """DTE-gewichtete Konvergenz: 4H-primär für <21T, 1D für 21-60T, 1W für >60T."""
                try:
                    tf  = tf_cache.get(row.get("Ticker", ""))
                    dte = int(row.get("DTE", 30))
                    if tf is None:
                        return (0.0, "🔴 Entfernt", "", "", "", False)
                    c = calc_convergence_score_dte(tf, conv_strategy, dte)
                    # Primär-TF-Kürzel für Anzeige
                    prim_label = f"{c.primary_tf} primär"
                    # Komponenten-Kurzinfo: Stoch/RSI/EMA/MACD je Ampel
                    def _amp(v):
                        return "🟢" if v >= 70 else "🟡" if v >= 40 else "🔴"
                    cp = c.components_primary
                    breakdown = (
                        f"Dual-Stoch {_amp(cp.get('stoch',0))} "
                        f"RSI {_amp(cp.get('rsi',0))} "
                        f"Trend {_amp(cp.get('ema',0))} "
                        f"MACD {_amp(cp.get('macd',0))} "
                        f"Vol {_amp(cp.get('volume',0))}"
                    )
                    warn = "⚠️ Widerspruch" if c.contradiction else ""
                    return (c.score, c.label, prim_label, breakdown, warn, c.contradiction)
                except Exception:
                    return (0.0, "–", "", "", "", False)

            conv_rows = results.apply(_conv_score_dte, axis=1)
            results["Konvergenz"]     = [x[0] for x in conv_rows]
            results["Konv."]          = [x[1] for x in conv_rows]
            results["Konv. TF"]       = [x[2] for x in conv_rows]
            results["Konv. Ampeln"]   = [x[3] for x in conv_rows]
            results["Konv. Hinweis"]  = [x[4] for x in conv_rows]

            # ── S/R-Schutz: Strike hinter Support/Widerstand ───────────────
            def _sr_protection(row):
                """Prüft ob der Strike hinter einem S/R-Level liegt."""
                try:
                    ticker   = str(row.get("Ticker", ""))
                    strike   = float(row.get("Strike", 0))
                    is_put   = "call" not in conv_strategy
                    hist     = fetch_price_history(ticker, period="3mo")
                    if hist.empty or strike <= 0:
                        return ("–", 0.0)

                    if is_put:
                        # Support finden: Swing-Tiefs ÜBER dem Strike (schützen ihn)
                        lows = hist["Low"]
                        # Lokale Minima: niedriger als Nachbarn (5-Bar-Fenster)
                        is_local_min = (
                            (lows < lows.shift(1)) & (lows < lows.shift(2)) &
                            (lows < lows.shift(-1)) & (lows < lows.shift(-2))
                        )
                        swing_lows = lows[is_local_min]
                        protecting = swing_lows[(swing_lows > strike) & (swing_lows < float(hist["Close"].iloc[-1]))]
                        if not protecting.empty:
                            nearest = float(protecting.iloc[-1])
                            buf_pct = (nearest - strike) / nearest * 100
                            return (f"✅ S {nearest:.0f} (+{buf_pct:.1f}%)", nearest)
                        # Fallback: 20-Tage-Tief als einfacher Proxy
                        low20 = float(lows.tail(20).min())
                        if low20 > strike:
                            return (f"✅ Low {low20:.0f}", low20)
                        return ("⚠️ kein S/R", 0.0)
                    else:
                        # Resistance finden: Swing-Hochs UNTER dem Strike (schützen ihn)
                        highs = hist["High"]
                        is_local_max = (
                            (highs > highs.shift(1)) & (highs > highs.shift(2)) &
                            (highs > highs.shift(-1)) & (highs > highs.shift(-2))
                        )
                        swing_highs = highs[is_local_max]
                        price_now = float(hist["Close"].iloc[-1])
                        protecting = swing_highs[(swing_highs < strike) & (swing_highs > price_now)]
                        if not protecting.empty:
                            nearest = float(protecting.iloc[-1])
                            buf_pct = (strike - nearest) / strike * 100
                            return (f"✅ R {nearest:.0f} (-{buf_pct:.1f}%)", nearest)
                        high20 = float(highs.tail(20).max())
                        if high20 < strike:
                            return (f"✅ Hoch {high20:.0f}", high20)
                        return ("⚠️ kein S/R", 0.0)
                except Exception:
                    return ("–", 0.0)

            sr_ph = st.empty()
            sr_ph.caption("🛡️ Berechne S/R-Schutz…")
            sr_rows = results.apply(_sr_protection, axis=1)
            results["S/R Schutz"] = [x[0] for x in sr_rows]
            sr_ph.empty()

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

        # Scan-Verlauf in JSON schreiben (max. 50 Einträge)
        try:
            import json as _json, datetime as _dt2
            _history_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "scan_history.json")
            _history = []
            if os.path.exists(_history_path):
                with open(_history_path, "r", encoding="utf-8") as _hf:
                    _history = _json.load(_hf)
            _history.insert(0, {
                "ts": _dt2.datetime.now().isoformat(),
                "strategy": scan_strategy,
                "sector": scan_sector,
                "n_tickers": len(scan_tickers),
                "n_results": n_found,
            })
            _history = _history[:50]
            with open(_history_path, "w", encoding="utf-8") as _hf:
                _json.dump(_history, _hf, ensure_ascii=False, indent=2)
        except Exception:
            pass
        # P2: Memory-Lean — nur Ticker im Ergebnis cachen (nicht alle 225)
        result_keys = set(results["Ticker"].unique()) if not results.empty else set()
        st.session_state.tf_results = {k: v for k, v in tf_cache.items() if k in result_keys}

    # Scan erfolgreich abgeschlossen — Flag zurücksetzen
    st.session_state.scan_running = False

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
    # ── Auto-Diagnose: Warum 0 Ergebnisse? ──────────────────────────────────
    from data.fetcher import is_market_open as _is_mkt_open
    _mkt = _is_mkt_open()
    _diagnose = []
    if not _mkt and not use_last_price:
        _diagnose.append(("🔴", "Markt geschlossen + 'Last Price verwenden' ist DEAKTIVIERT",
                          "Aktiviere 'Last Price verwenden' im Filter-Bereich"))
    if iv_min > 20:
        _diagnose.append(("🟡", f"IV-Minimum zu hoch: {iv_min}% filtert viele Aktien raus",
                          "Setze IV-Min auf 10% oder niedriger"))
    if float(otm_min) > 5:
        _diagnose.append(("🟡", f"OTM-Minimum {otm_min}% zu restriktiv",
                          "Setze OTM-Min auf 0–3%"))
    if int(oi_min) > 50:
        _diagnose.append(("🟡", f"Open Interest-Minimum {oi_min} filtert illiquide Optionen heraus",
                          "Setze OI-Min auf 0–10"))

    st.html("""
    <div style='background:#1a0a0a;border:1px solid #ef444440;border-radius:10px;padding:20px;margin:12px 0'>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1rem;color:#ef4444;
                    margin-bottom:12px'>⚠️ Keine Optionen gefunden — Diagnose</div>
    """)
    if _diagnose:
        for icon, prob, fix in _diagnose:
            st.html(f"""
            <div style='display:flex;gap:10px;margin-bottom:8px;font-family:sans-serif'>
                <span style='font-size:1rem'>{icon}</span>
                <div>
                    <div style='color:#f0f0f0;font-size:0.84rem;font-weight:600'>{prob}</div>
                    <div style='color:#888;font-size:0.78rem;margin-top:2px'>→ {fix}</div>
                </div>
            </div>""")
    else:
        st.html("""<div style='color:#888;font-size:0.84rem;font-family:sans-serif'>
            Keine offensichtlichen Filter-Probleme — möglicherweise temporärer Datenfehler.</div>""")
    st.html("</div>")

    # Schnell-Fix Buttons
    _fix1, _fix2, _fix3 = st.columns(3)
    with _fix1:
        if st.button("🔄 Cache leeren + neu scannen", use_container_width=True, type="primary"):
            st.cache_data.clear()
            from data import _persistent_cache as _pc
            _pc.clear_all()
            st.session_state.scan_results = None
            st.session_state.scan_running = False
            st.rerun()
    with _fix2:
        if st.button("📉 Filter lockern (Standard)", use_container_width=True):
            st.session_state.preset = None
            for k in ["dte_min", "dte_max", "d_min", "d_max", "iv_min", "prem_min",
                       "oi_min", "otm_min", "otm_max"]:
                if k in st.session_state:
                    del st.session_state[k]
            st.rerun()
    with _fix3:
        if st.button("📡 Last Price aktivieren", use_container_width=True):
            st.session_state["use_last_price_override"] = True
            st.rerun()

else:
    # Cache-Hinweis anzeigen
    if meta.get("source") == "cache":
        _cache_age = meta.get("age_h", 0)
        _cache_ts = meta.get("cached_at", "")
        _age_str = f"{int(_cache_age * 60)} Min." if _cache_age < 1 else f"{_cache_age:.1f}h"
        st.info(
            f"💾 **Ergebnisse aus letztem Scan** (vom {_cache_ts}, vor {_age_str}) — "
            f"starte einen neuen Scan um aktuelle Daten zu laden.",
            icon=None,
        )

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

        def _lazy_conv(row):
            try:
                tf  = _cached_tf.get(row.get("Ticker", ""))
                dte = int(row.get("DTE", 30))
                if tf is None:
                    return (0.0, "–", "", "", "")
                c = calc_convergence_score_dte(tf, _conv_strategy, dte)
                def _amp(v):
                    return "🟢" if v >= 70 else "🟡" if v >= 40 else "🔴"
                cp = c.components_primary
                breakdown = (
                    f"Dual-Stoch {_amp(cp.get('stoch',0))} "
                    f"RSI {_amp(cp.get('rsi',0))} "
                    f"Trend {_amp(cp.get('ema',0))} "
                    f"MACD {_amp(cp.get('macd',0))} "
                    f"Vol {_amp(cp.get('volume',0))}"
                )
                return (c.score, c.label, f"{c.primary_tf} primär", breakdown,
                        "⚠️ Widerspruch" if c.contradiction else "")
            except Exception:
                return (0.0, "–", "", "", "")

        _cx = results.apply(_lazy_conv, axis=1)
        results["Konvergenz"]    = [x[0] for x in _cx]
        results["Konv."]         = [x[1] for x in _cx]
        results["Konv. TF"]      = [x[2] for x in _cx]
        results["Konv. Ampeln"]  = [x[3] for x in _cx]
        results["Konv. Hinweis"] = [x[4] for x in _cx]
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
                     "Trend", "⚠️ Earnings", "OptionStrat"]
    else:
        base_cols = ["Top", "Liq.", "Ticker", "Sektor", "Kurs", "Strike", "OTM %",
                     "Verfall", "DTE", "Prämie", "Bid", "Ask", "Kursquelle", "Spread %",
                     "Prämie/Tag", "Rendite ann. %", "Rendite % Laufzeit", "Rendite %/Tag",
                     "Delta", "Theta/Tag", "IV %", "IV Rank", "OI", "Volumen",
                     "Trend", "⚠️ Earnings", "OptionStrat"]
    # Tech-Spalten wenn vorhanden
    tech_cols = [c for c in ["RSI(1D)", "Stoch(1D)", "MACD(1D)", "SC Trend(1D)", "TF-Align"] if c in display_df.columns]
    # Konvergenz-Spalten inkl. neue Breakdown + S/R Schutz
    conv_cols_show = [c for c in [
        "Konvergenz", "Konv.", "Konv. TF", "Konv. Ampeln", "Konv. Hinweis", "S/R Schutz",
    ] if c in display_df.columns]
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
        # Konvergenz-Spalten (DTE-gewichtet)
        "Konvergenz": st.column_config.ProgressColumn(
            "⚡ Konvergenz", min_value=0, max_value=100, format="%.0f",
            help=(
                "DTE-gewichtete Konvergenz: 0–21T → 4H primär (65%), "
                "21–60T → 1D primär (65%), >60T → 1W primär (55%). "
                "Widerspruch zwischen primärem und sekundärem TF = 30% Penalty."
            ),
        ),
        "Konv.":         st.column_config.TextColumn("Konv.", width="small"),
        "Konv. TF":      st.column_config.TextColumn("TF-Basis", width="small",
                                                      help="Primärer Timeframe (DTE-abhängig)"),
        "Konv. Ampeln":  st.column_config.TextColumn("Indikatoren", width="large",
                                                      help="🟢≥70 · 🟡40-70 · 🔴<40 (Dual-Stoch · RSI · Trend · MACD · Vol)"),
        "Konv. Hinweis": st.column_config.TextColumn("Hinweis", width="small",
                                                      help="⚠️ Widerspruch wenn primärer und sekundärer Timeframe widersprechen"),
        "S/R Schutz":    st.column_config.TextColumn("S/R Schutz", width="medium",
                                                      help="✅ Strike liegt hinter einer Unterstützung/Widerstand · ⚠️ Kein S/R gefunden"),
        "OptionStrat":   st.column_config.LinkColumn(
            "📊 OptionStrat",
            display_text="→ Analysieren",
            width="medium",
            help="Direkt auf OptionStrat öffnen — Live-Prämie, Payoff-Diagramm, Greeks",
        ),
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

                    # ── OptionStrat-Button ────────────────────────────────
                    _os_url = str(_r.get("OptionStrat", ""))
                    if not _os_url and _tkr and _strike > 0 and _expiry:
                        # Fallback: live generieren falls Spalte fehlt
                        from analysis.batch_screener import _optionstrat_url as _mkurl
                        _os_url = _mkurl(_tkr, _strike, _expiry, _is_call)
                    if _os_url:
                        st.link_button(
                            "📊 Auf OptionStrat analysieren →",
                            url=_os_url,
                            use_container_width=True,
                        )

                    # ── Trade-Button ──────────────────────────────────────
                    _delta_val = float(_r.get("Delta", 0) or 0)
                    _expiry_raw = str(_r.get("Verfall", "") or "")
                    _strategy_raw = meta.get("strategy", scan_strategy)

                    st.html("""
<div style='background:#0a0e0a;border:1px solid #22c55e;border-radius:10px;
     padding:14px 16px;margin-top:8px'>
  <div style='font-size:0.82rem;font-weight:700;color:#22c55e;margin-bottom:8px'>
    📋 Order vorbereiten
  </div>
""")
                    st.caption(
                        f"**{_tkr}** · Strike ${_strike:.2f} · "
                        f"Delta {_delta_val:.2f} · Prämie ${_premium:.2f} · DTE {_dte}"
                    )

                    # Limit-Preis vorschlag: 90% des Mid-Price (konservativ)
                    _suggested_lmt = round(_premium * 0.90, 2)
                    _lmt_input = st.number_input(
                        "Limit-Preis $", min_value=0.01,
                        value=max(0.01, _suggested_lmt),
                        step=0.05, format="%.2f",
                        key=f"lmt_quick_{_tkr}_{_strike}",
                        help="Vorschlag: 90% des Midpoints — anpassen nach Marktlage",
                    )
                    _qty_input = st.number_input(
                        "Kontrakte", min_value=1, max_value=100,
                        value=1, step=1,
                        key=f"qty_quick_{_tkr}_{_strike}",
                    )

                    if st.button(
                        "📋 In Order-Planung öffnen",
                        key=f"trade_btn_{_tkr}_{_strike}",
                        type="primary",
                        use_container_width=True,
                    ):
                        # Werte in Session State schreiben → Seite 14 liest sie aus
                        st.session_state["order_prefill"] = {
                            "ticker":       _tkr,
                            "expiration":   _expiry_raw,
                            "strike":       _strike,
                            "right":        "C" if _is_call else "P",
                            "action":       "SELL",
                            "quantity":     _qty_input,
                            "limit_price":  _lmt_input,
                            "strategy":     _strategy_raw,
                            "premium":      _premium,
                            "delta":        _delta_val,
                            "dte":          _dte,
                        }
                        st.switch_page("pages/14_Order_Planung.py")

                    st.html("</div>")

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

# ── Hintergrund-Scan Polling (am Seitenende — nach allen Buttons!) ────────────
# Erst hier sleep+rerun, damit Button-Klicks in dieser Runde verarbeitet werden.
if _bg_poll_needed and not start_scan:
    import time as _t
    _t.sleep(2)
    st.rerun()
