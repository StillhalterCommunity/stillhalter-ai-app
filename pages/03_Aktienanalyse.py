"""
Stillhalter AI App — Einzelanalyse
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go

st.set_page_config(
    page_title="Aktienanalyse · Stillhalter AI App",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

from data.watchlist import WATCHLIST, SECTOR_ICONS, get_sector_for_ticker, ALL_TICKERS
from data.universes import get_universe_tickers, UNIVERSE_OPTIONS
from data.fetcher import (fetch_options_chain, fetch_price_history, fetch_stock_info,
                           fetch_fundamentals, calculate_dte, market_status_text, is_market_open)
from analysis.technicals import analyze_technicals
from analysis.screening import screen_options, ScreeningParams
from analysis.batch_screener import calculate_crv_score
from analysis.multi_timeframe import analyze_multi_timeframe, tf_summary_row, stillhalter_trend_html
from ui.charts import render_stock_chart, render_payoff_diagram, render_option_mini_chart


# ── Helper ────────────────────────────────────────────────────────────────────
def fmt(val, spec=".2f", pre="", suf="", fb="–"):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return fb
    try:
        return f"{pre}{val:{spec}}{suf}"
    except Exception:
        return str(val)

def pct(val, fb="–"):
    return f"{val*100:.1f}%" if val is not None else fb

def mcap(val):
    if not val: return "–"
    if val >= 1e12: return f"${val/1e12:.1f}T"
    if val >= 1e9:  return f"${val/1e9:.1f}B"
    return f"${val/1e6:.0f}M"

def peg_info(peg):
    if peg is None: return "–", "#555"
    c = "#22c55e" if peg < 1.5 else "#f59e0b" if peg < 2.5 else "#ef4444"
    l = "Günstig" if peg < 1.5 else "Fair" if peg < 2.5 else "Teuer"
    return f"{peg:.2f} ({l})", c


# ── Sidebar: Ticker-Auswahl ───────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## 📊 Aktie wählen")

    analyse_universe = st.selectbox(
        "Universum",
        UNIVERSE_OPTIONS,
        key="analyse_universe",
        help="Aus welchem Index soll die Aktie gewählt werden?",
    )

    if "Watchlist" in analyse_universe:
        sector_sel = st.selectbox(
            "Sektor",
            list(WATCHLIST.keys()),
            format_func=lambda s: f"{SECTOR_ICONS.get(s,'')} {s.split('.',1)[-1].strip().split('(')[0].strip()}",
        )
        ticker_list = WATCHLIST.get(sector_sel, [])
    else:
        sector_sel = ""
        ticker_list = sorted(get_universe_tickers(analyse_universe))

    # Freitexteingabe für beliebige Ticker
    manual_ticker = st.text_input("Oder Ticker direkt eingeben", "",
                                   placeholder="z.B. AAPL, TSLA, META…").strip().upper()

    if manual_ticker:
        selected_ticker = manual_ticker
    else:
        selected_ticker = st.selectbox("Ticker", ticker_list)

    st.markdown("---")
    if st.button("🔄 Daten aktualisieren", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    market_open = is_market_open()
    mkt_class = "market-open" if market_open else "market-closed"
    st.markdown(f'<div class="{mkt_class}" style="font-size:0.8rem;margin-top:8px">{market_status_text()}</div>',
                unsafe_allow_html=True)
    if not market_open:
        st.caption("Preise basieren auf Last Price")


# ── Daten laden ───────────────────────────────────────────────────────────────
with st.spinner(f"Lade {selected_ticker}..."):
    stock_info   = fetch_stock_info(selected_ticker)
    price_hist   = fetch_price_history(selected_ticker, period="1y")
    puts_df, calls_df, expirations = fetch_options_chain(selected_ticker)
    fundamentals = fetch_fundamentals(selected_ticker)
    mtf          = analyze_multi_timeframe(selected_ticker)

current_price = stock_info.get("price")
tech_signal   = analyze_technicals(price_hist) if not price_hist.empty else None
sector        = get_sector_for_ticker(selected_ticker)
company_name  = stock_info.get("name", selected_ticker)

# ── Header ────────────────────────────────────────────────────────────────────
h1, h2 = st.columns([5, 2])
with h1:
    prev = stock_info.get("prev_close")
    chg_pct = ((current_price / prev) - 1) * 100 if current_price and prev else None
    chg_color = "#22c55e" if (chg_pct or 0) >= 0 else "#ef4444"
    chg_str = f'<span style="color:{chg_color};font-size:1.2rem"> {chg_pct:+.2f}%</span>' if chg_pct else ""

    st.markdown(f"""
    <div class="sc-header">
        <div>
            <div class="sc-page-title">
                {SECTOR_ICONS.get(sector,'')} {company_name}
                <span style='color:#d4a843;margin-left:8px'>({selected_ticker})</span>
                {f'<span style="color:#e0e0e0;font-size:1.4rem;margin-left:12px">${current_price:.2f}</span>' if current_price else ''}
                {chg_str}
            </div>
            <div class="sc-page-subtitle">{sector.split('.',1)[-1].strip() if '.' in sector else sector}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

with h2:
    st.markdown("<br>", unsafe_allow_html=True)
    if not market_open:
        st.warning("⏰ Markt geschlossen — Last Price", icon="⚠️")

# ── Kurs-Metriken ─────────────────────────────────────────────────────────────
f = fundamentals
m1,m2,m3,m4,m5,m6,m7 = st.columns(7)
m1.metric("Kurs",        fmt(current_price,".2f","$"),
          fmt(chg_pct,"+.2f",suf="%") if chg_pct else None)
m2.metric("Market Cap",  mcap(stock_info.get("market_cap")))
m3.metric("Beta",        fmt(stock_info.get("beta"),".2f"))
m4.metric("52W Hoch",    fmt(f.get("week_52_high"),".2f","$"))
m5.metric("52W Tief",    fmt(f.get("week_52_low"),".2f","$"))
m6.metric("Ø Kursziel",  fmt(f.get("target_price"),".2f","$"))
rating = f.get("analyst_rating","–") or "–"
m7.metric("Analysten",   f"{rating.upper()} ({f.get('num_analysts','?')})")

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── Multi-TF Signalbox ────────────────────────────────────────────────────────
if any([mtf.tf_4h, mtf.tf_1d, mtf.tf_1w]):
    align_color = {"bullish":"#22c55e","bearish":"#ef4444","neutral":"#f59e0b"}.get(mtf.alignment_direction,"#555")
    align_icon  = {"bullish":"↑","bearish":"↓","neutral":"→"}.get(mtf.alignment_direction,"–")

    # Stillhalter Trend Model (4H · 1D · 1W · 1M) — immer sichtbar
    st.markdown(stillhalter_trend_html(mtf), unsafe_allow_html=True)

    tf_rows = [tf_summary_row(t) for t in [mtf.tf_4h, mtf.tf_1d, mtf.tf_1w, mtf.tf_1m] if t]
    tf_df = pd.DataFrame(tf_rows)

    with st.expander(
        f"📊 Multi-Timeframe Signale — "
        f"Alignment: {align_icon} {mtf.alignment_direction.upper()} "
        f"(Score {mtf.alignment_score:.0f}/100)",
        expanded=False
    ):
        tc1, tc2 = st.columns([3, 2])
        with tc1:
            def style_tf(val):
                if "↑" in str(val) or "Bull" in str(val) or "Cross" == str(val)[:5] and "↑" in str(val):
                    return "color: #22c55e"
                if "↓" in str(val) or "Bear" in str(val):
                    return "color: #ef4444"
                return "color: #888"

            st.dataframe(
                tf_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "TF":       st.column_config.TextColumn("Timeframe", width="small"),
                    "RSI":      st.column_config.TextColumn("RSI (14)"),
                    "Stoch %K": st.column_config.TextColumn("Stoch %K"),
                    "MACD":     st.column_config.TextColumn("MACD"),
                    "SC Trend": st.column_config.TextColumn("SC Trend"),
                    "Score":    st.column_config.TextColumn("Score"),
                    "Richtung": st.column_config.TextColumn("Richtung"),
                },
                height=160,
            )

        with tc2:
            # Bestätigte Signale
            confirmed = []
            if mtf.confirmed_stoch_cross_up:   confirmed.append("✅ Stoch kreuzt 20 aufwärts (≥2 TFs)")
            if mtf.confirmed_rsi_oversold:     confirmed.append("✅ RSI überverkauft (≥2 TFs)")
            if mtf.confirmed_macd_bullish_cross: confirmed.append("✅ MACD Bullish Cross (≥2 TFs)")
            if mtf.confirmed_ema_bullish:      confirmed.append("✅ SC Trend bullish (≥2 TFs)")
            if mtf.confirmed_stoch_cross_down: confirmed.append("🔴 Stoch kreuzt 80 abwärts (≥2 TFs)")
            if mtf.confirmed_rsi_overbought:   confirmed.append("🔴 RSI überkauft (≥2 TFs)")
            if mtf.confirmed_macd_bearish_cross: confirmed.append("🔴 MACD Bearish Cross (≥2 TFs)")
            if mtf.confirmed_ema_bearish:      confirmed.append("🔴 SC Trend bearish (≥2 TFs)")

            if confirmed:
                st.markdown("**Bestätigte Signale (≥2 Timeframes):**")
                for c in confirmed:
                    st.markdown(c)
            else:
                st.markdown('<div style="color:#555;font-size:0.85rem">Keine übergreifenden Bestätigungen.</div>',
                            unsafe_allow_html=True)

# ── Haupt-Tabs ────────────────────────────────────────────────────────────────
tab_opts, tab_chart, tab_fund, tab_news, tab_bt = st.tabs([
    "📋  OPTIONEN",
    "📈  CHART & INDIKATOREN",
    "💹  BEWERTUNG & FUNDAMENTALS",
    "📰  EARNINGS & NEWS",
    "🔬  BACKTEST",
])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1: OPTIONEN
# ═══════════════════════════════════════════════════════════════════════════════
with tab_opts:
    if not market_open:
        st.info("⏰ Markt geschlossen — Prämien basieren auf Last Price. Reale Bid/Ask kann abweichen.")

    if not expirations:
        st.warning(f"Keine Options-Daten für {selected_ticker} verfügbar.")
    elif not current_price:
        st.error("Kurs konnte nicht geladen werden.")
    else:
        # Inline Filter
        st.markdown("#### ⚙️ Options-Filter")
        oc1,oc2,oc3,oc4,oc5 = st.columns(5)
        with oc1:
            strategy = st.selectbox("Strategie",
                ["Cash Covered Put","Covered Call","Short Strangle"], key="opt_strat")
        with oc2:
            dte_min_o = st.number_input("DTE min", 0, 180, 14, key="o_dmin")
            dte_max_o = st.number_input("DTE max", 1, 365, 60, key="o_dmax")
        with oc3:
            if strategy in ["Cash Covered Put","Short Strangle"]:
                d_min = st.number_input("Delta min",-1.0,0.0,-0.35,0.01,format="%.2f",key="o_dm")
                d_max = st.number_input("Delta max",-1.0,0.0,-0.05,0.01,format="%.2f",key="o_dx")
            else:
                dp_min = st.number_input("Delta min",0.0,1.0,0.05,0.01,format="%.2f",key="o_dpm")
                dp_max = st.number_input("Delta max",0.0,1.0,0.35,0.01,format="%.2f",key="o_dpx")
                d_min,d_max = -dp_max,-dp_min
        with oc4:
            iv_min_o  = st.number_input("IV min %",   0, 300, 0,  key="o_iv")
            otm_min_o = st.number_input("OTM min %",  0,  30, 0,  key="o_otm")
        with oc5:
            prem_min_o = st.number_input("Mind. Prämie ($)", 0.0, 20.0, 0.05,
                                          step=0.05, format="%.2f", key="o_pm")
            oi_min_o   = st.number_input("Mind. OI", 0, 5000, 5, key="o_oi")

        params = ScreeningParams(
            strategy=strategy,
            delta_min=d_min, delta_max=d_max,
            dte_min=int(dte_min_o), dte_max=int(dte_max_o),
            iv_min=iv_min_o/100, iv_max=2.0,
            premium_min=prem_min_o,
            min_open_interest=int(oi_min_o),
            otm_min_pct=float(otm_min_o), otm_max_pct=30.0,
        )

        with st.spinner("Berechne Greeks & CRV..."):
            screened = screen_options(puts_df, calls_df, current_price, params, tech_signal)

        if screened.empty:
            st.info("Keine Optionen mit diesen Filtern — OTM min, IV min oder Prämie senken.")
        else:
            opt_type = "call" if strategy == "Covered Call" else "put"
            if "Strike" in screened.columns and "Prämie" in screened.columns:
                screened["⭐ CRV"] = screened.apply(
                    lambda r: calculate_crv_score(
                        premium=float(r.get("Prämie",0)),
                        strike=float(r.get("Strike",1)),
                        current_price=current_price,
                        delta=float(r.get("Delta",-0.2)) if r.get("Delta") != "" else -0.2,
                        dte=int(r.get("DTE",30)),
                        option_type=opt_type,
                    ), axis=1
                ).round(1)
                screened = screened.sort_values("⭐ CRV", ascending=False).reset_index(drop=True)

            # Kennzahlen
            sc1,sc2,sc3,sc4 = st.columns(4)
            sc1.metric("Optionen gefunden", len(screened))
            sc2.metric("Bester CRV", f"{screened['⭐ CRV'].max():.1f}" if "⭐ CRV" in screened.columns else "–")
            sc3.metric("Trend (1D)", {"bullish":"↑ Aufwärts","bearish":"↓ Abwärts","neutral":"→ Seitwärts"}.get(
                mtf.tf_1d.direction if mtf.tf_1d else "neutral","–"))
            sc4.metric("TF-Alignment Score", f"{mtf.alignment_score:.0f}/100")

            # S/R Hinweise
            if tech_signal and tech_signal.support_levels:
                st.markdown("🟢 **Unterstützungen:** " + " | ".join([f"${s:.2f}" for s in tech_signal.support_levels]))
            if tech_signal and tech_signal.resistance_levels:
                st.markdown("🔴 **Widerstände:** " + " | ".join([f"${r:.2f}" for r in tech_signal.resistance_levels]))

            # Im Session State cachen für Chart-Overlay
            st.session_state.setdefault("screened_cache", {})[selected_ticker] = screened

            hide = ["_highlight"]
            show = [c for c in screened.columns if c not in hide]
            view = screened[show].copy()

            # Top-3 Badge hinzufügen
            rank_badges = ["🥇 Top 1", "🥈 Top 2", "🥉 Top 3"]
            view.insert(0, "Top", [rank_badges[i] if i < 3 else "" for i in range(len(view))])

            # Kurs als Referenz-Spalte ergänzen (direkt nach Top, Liq.)
            if "Kurs" not in view.columns:
                view.insert(2, "Kurs", current_price)

            # ── Einheitliche Spaltenreihenfolge (identisch mit Watchlist Scanner) ──
            UNIFIED_COLS = [
                "Top", "Liq.", "Kurs", "Strike", "OTM %", "Verfall", "DTE",
                "Prämie", "Bid", "Ask", "Kursquelle", "Spread %", "Prämie/Tag",
                "Rendite % Laufzeit", "Rendite ann. %", "Rendite %/Tag",
                "Delta", "Theta/Tag", "IV %", "OI", "Volumen", "Score", "⭐ CRV",
            ]
            ordered = [c for c in UNIFIED_COLS if c in view.columns]
            extras  = [c for c in view.columns if c not in ordered]
            view = view[ordered + extras]

            # Max-Wert Hervorhebung
            _HL = ["OTM %", "Prämie", "Prämie/Tag",
                   "Rendite ann. %", "Rendite % Laufzeit", "Rendite %/Tag", "IV %", "Score"]
            _hl_max  = [c for c in _HL if c in view.columns]
            _hl_min  = ["Delta", "Spread %"]  # kleine Werte = besser
            _min_cols = [c for c in _hl_min if c in view.columns]

            def _style_analyse(df_v):
                s = pd.DataFrame("", index=df_v.index, columns=df_v.columns)
                # Top-3 Zeilen Gold/Silber/Bronze
                row_bg = ["rgba(212,168,67,0.18)", "rgba(160,160,180,0.12)", "rgba(180,130,80,0.10)"]
                for i in range(min(3, len(df_v))):
                    s.iloc[i] = f"background-color:{row_bg[i]};"
                # Liq.-Spalte einfärben (🟢🟡🔴)
                if "Liq." in df_v.columns:
                    for idx, val in df_v["Liq."].items():
                        if val == "🟢":
                            s.loc[idx, "Liq."] = "background-color:rgba(34,197,94,0.15);"
                        elif val == "🟡":
                            s.loc[idx, "Liq."] = "background-color:rgba(234,179,8,0.15);"
                        elif val == "🔴":
                            s.loc[idx, "Liq."] = "background-color:rgba(239,68,68,0.15);"
                # Spalten-Maxima gold
                for col in _hl_max:
                    if col in df_v.columns and df_v[col].dtype.kind in "fiu" and len(df_v) > 0:
                        try:
                            idx = df_v[col].idxmax()
                            s.loc[idx, col] = "background-color:rgba(212,168,67,0.28);color:#d4a843;font-weight:700;"
                        except Exception:
                            pass
                # Spalten-Minima grün
                for col in _min_cols:
                    if col in df_v.columns and df_v[col].dtype.kind in "fiu" and len(df_v) > 0:
                        try:
                            valid = df_v[col].replace(0, np.nan).dropna()
                            if not valid.empty:
                                s.loc[valid.idxmin(), col] = "background-color:rgba(34,197,94,0.15);color:#22c55e;font-weight:700;"
                        except Exception:
                            pass
                return s

            col_cfg_analyse = {
                "Top":                st.column_config.TextColumn("Top", width="small",
                                                                   help="Rang nach CRV Score"),
                "Liq.":               st.column_config.TextColumn("Liq.", width="small",
                                                                   help="🟢 Spread ≤5% · 🟡 5–15% · 🔴 >15%"),
                "Kurs":               st.column_config.NumberColumn("Kurs",         format="$%.2f"),
                "Strike":             st.column_config.NumberColumn("Strike",        format="$%.2f"),
                "OTM %":              st.column_config.NumberColumn("OTM %",         format="%.1f%%"),
                "Verfall":            st.column_config.TextColumn("Verfall",         width="small"),
                "DTE":                st.column_config.NumberColumn("DTE",           format="%d"),
                "Prämie":             st.column_config.NumberColumn("Prämie",        format="$%.2f"),
                "Bid":                st.column_config.NumberColumn("Bid",           format="$%.2f",
                                                                     help="Geldkurs — was du beim Verkauf erhältst"),
                "Ask":                st.column_config.NumberColumn("Ask",           format="$%.2f",
                                                                     help="Briefkurs — was der Käufer bezahlt"),
                "Kursquelle":         st.column_config.TextColumn("Quelle", width="small",
                                                                   help="Mid = Bid/Ask Midprice · Letztkurs = Off-Hours Schätzung"),
                "Spread %":           st.column_config.NumberColumn("Spread %",      format="%.1f%%",
                                                                     help="Bid/Ask Spread — niedrig = liquide"),
                "Prämie/Tag":         st.column_config.NumberColumn("$/Tag",         format="$%.3f"),
                "Rendite % Laufzeit": st.column_config.NumberColumn("Rendite % LZ",  format="%.2f%%",
                                                                     help="Rendite auf Laufzeit (Prämie / Strike)"),
                "Rendite ann. %":     st.column_config.NumberColumn("Rendite ann.",  format="%.1f%%"),
                "Rendite %/Tag":      st.column_config.NumberColumn("Rend. %/Tag",   format="%.4f%%",
                                                                     help="Tagesrendite in % auf Strike"),
                "Delta":              st.column_config.NumberColumn("Δ",             format="%.3f"),
                "Theta/Tag":          st.column_config.NumberColumn("Θ/Tag",         format="%.3f",
                                                                     help="Theta — täglicher Zeitwertverlust der Option"),
                "IV %":               st.column_config.NumberColumn("IV %",          format="%.1f%%"),
                "OI":                 st.column_config.NumberColumn("OI",            format="%d",
                                                                     help="Open Interest — offene Kontrakte"),
                "Volumen":            st.column_config.NumberColumn("Vol.",           format="%d"),
                "Score":              st.column_config.NumberColumn("Score",          format="%.1f",
                                                                     help="Stillhalter-Score: gewichtet Prämie/Tag, IV, Delta, Trend, Liquidität"),
                "⭐ CRV":             st.column_config.NumberColumn("⭐ CRV",         format="%.1f",
                                                                     help="Chance-Risiko-Verhältnis: Rendite × Puffer / Delta"),
            }
            try:
                _styled = view.style.apply(_style_analyse, axis=None)
                _tbl_event = st.dataframe(
                    _styled,
                    use_container_width=True, height=420,
                    column_config=col_cfg_analyse, hide_index=True,
                    on_select="rerun", selection_mode="single-row",
                    key="opt_table_sel",
                )
            except Exception:
                _tbl_event = st.dataframe(
                    view, use_container_width=True, height=420,
                    column_config=col_cfg_analyse, hide_index=True,
                    on_select="rerun", selection_mode="single-row",
                    key="opt_table_sel_fb",
                )

            st.caption("💡 Zeile anklicken → Mini-Chart mit Payoff-Overlay")

            # ── Mini-Chart bei Zeilenauswahl ──────────────────────────────
            _sel_rows = (getattr(_tbl_event, "selection", None) or {})
            _sel_rows = _sel_rows.get("rows", []) if isinstance(_sel_rows, dict) else getattr(_sel_rows, "rows", [])
            if _sel_rows:
                _sel_idx = _sel_rows[0]
                if _sel_idx < len(view):
                    _row = view.iloc[_sel_idx]
                    _strike  = float(_row.get("Strike", 0) or 0)
                    _premium = float(_row.get("Prämie", 0) or 0)
                    _dte     = int(_row.get("DTE", 30) or 30)
                    _iv_pct  = float(_row.get("IV %", 30) or 30)
                    _expiry  = str(_row.get("Verfall", ""))

                    st.markdown("---")
                    _c1, _c2 = st.columns([3, 2])
                    with _c1:
                        if not price_hist.empty and _strike > 0 and _premium > 0:
                            fig_mini = render_option_mini_chart(
                                hist=price_hist,
                                ticker=selected_ticker,
                                current_price=current_price,
                                strike=_strike,
                                premium=_premium,
                                dte=_dte,
                                iv_pct=_iv_pct,
                                option_type=opt_type,
                                expiry_date=_expiry,
                            )
                            st.plotly_chart(fig_mini, use_container_width=True,
                                            config={"displayModeBar": False})
                    with _c2:
                        if _strike > 0 and _premium > 0:
                            fig_pay = render_payoff_diagram(
                                current_price, _strike, _premium,
                                opt_type, selected_ticker, _dte,
                            )
                            fig_pay.update_layout(height=260, margin=dict(l=5,r=5,t=45,b=30))
                            st.plotly_chart(fig_pay, use_container_width=True,
                                            config={"displayModeBar": False})


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2: CHART
# ═══════════════════════════════════════════════════════════════════════════════
with tab_chart:
    if price_hist.empty:
        st.warning("Keine Kursdaten verfügbar.")
    else:
        cc1,cc2,cc3,cc4 = st.columns([3,2,2,2])
        with cc1:
            period_map = {"3 Monate":"3mo","6 Monate":"6mo","1 Jahr":"1y","2 Jahre":"2y","5 Jahre":"5y"}
            period_sel = st.selectbox("Zeitraum", list(period_map.keys()), index=2)
        with cc2:
            show_inds = st.checkbox("MACD + Stochastik", value=True)
        with cc3:
            ch_height = st.slider("Höhe", 500, 900, 700, 50)
        with cc4:
            trend_mode_chart = st.selectbox("Trend Mode",
                ["Very Tight", "Tight", "Loose", "Very Loose"],
                index=0,
                key="trend_mode_chart",
                help="Stillhalter Trend Model Modus")

        cp = period_map[period_sel]
        ch_hist = fetch_price_history(selected_ticker, period=cp) if cp != "1y" else price_hist
        ch_tech = analyze_technicals(ch_hist) if not ch_hist.empty else tech_signal

        # Top-3 Optionen für Chart-Overlay aus Session State holen
        _top3_for_chart = None
        _screened_cached = st.session_state.get("screened_cache", {}).get(selected_ticker)
        if _screened_cached is not None and not _screened_cached.empty:
            _top3_for_chart = _screened_cached.head(3)

        col_chart, col_dark = st.columns([6, 1])
        with col_dark:
            dark_chart = st.checkbox("🌙 Dark", value=True, key="chart_dark")

        fig = render_stock_chart(
            ch_hist, ticker=selected_ticker,
            tech_signal=ch_tech, show_indicators=show_inds, height=ch_height,
            trend_mode=trend_mode_chart,
            top_options=_top3_for_chart,
            dark_mode=dark_chart,
        )
        st.plotly_chart(fig, use_container_width=True)

        if ch_tech:
            st.markdown("#### 📊 Technische Zusammenfassung")
            tc1,tc2,tc3,tc4,tc5,tc6 = st.columns(6)
            tc1.metric("Trend-Score", f"{ch_tech.trend_score:.0f}/100",
                       {"bullish":"↑ Aufwärts","bearish":"↓ Abwärts","neutral":"→ Seitwärts"}.get(ch_tech.trend,""))
            sc_m = ch_tech.sc_macd
            if sc_m:
                tc2.metric("SC MACD Pro",
                           {"strong_bull":"⭐ STARK ↑↑","bull":"Bullish ↑",
                            "neutral":"Neutral →","bear":"Bearish ↓",
                            "strong_bear":"⭐ STARK ↓↓"}.get(sc_m.signal_strength,"–"),
                           f"ADX {sc_m.adx_val:.0f}")
            else:
                tc2.metric("SC MACD Pro", "–")
            ds_s = ch_tech.dual_stoch
            if ds_s:
                fast_lbl = ("🟢 Ready Buy" if ds_s.fast_ready_buy
                            else "🔴 Ready Sell" if ds_s.fast_ready_sell
                            else ds_s.signal_strength)
                slow_lbl = ("🟢 Ready Buy" if ds_s.slow_ready_buy
                            else "🔴 Ready Sell" if ds_s.slow_ready_sell
                            else ds_s.signal_strength)
                tc3.metric("Stoch Schnell %K", f"{ds_s.fast_k:.0f}", fast_lbl)
                tc4.metric("Stoch Langsam %K", f"{ds_s.slow_k:.0f}", slow_lbl)
            else:
                tc3.metric("Stoch %K/%D", f"{ch_tech.stoch_k:.0f}/{ch_tech.stoch_d:.0f}", ch_tech.stoch_signal)
                tc4.metric("Stoch Langsam", "–")
            tc5.metric("EMA 50",  "✅ Kurs darüber" if ch_tech.above_sma50  else "❌ Kurs darunter")
            tc6.metric("EMA 200", "✅ Kurs darüber" if ch_tech.above_sma200 else "❌ Kurs darunter")

            # S/R Legende unter Chart
            sr_col1, sr_col2 = st.columns(2)
            with sr_col1:
                if ch_tech.support_levels:
                    lvls = " · ".join([f"**${s:.2f}**" for s in ch_tech.support_levels[:5]])
                    st.markdown(f"🟢 **Unterstützungen:** {lvls}")
            with sr_col2:
                if ch_tech.resistance_levels:
                    lvls = " · ".join([f"**${r:.2f}**" for r in ch_tech.resistance_levels[:5]])
                    st.markdown(f"🔴 **Widerstände:** {lvls}")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3: BEWERTUNG
# ═══════════════════════════════════════════════════════════════════════════════
with tab_fund:
    st.markdown("### 💹 Bewertung & Fundamentaldaten")

    # Bewertung
    st.markdown("#### Aktuelle Bewertung")
    bw1,bw2,bw3,bw4 = st.columns(4)
    bw1.metric("KGV aktuell",  fmt(f.get("pe_trailing"),  ".1f", suf="x"))
    pe_f = f.get("pe_forward"); pe_t = f.get("pe_trailing")
    kgv_delta = f"{((pe_f/pe_t)-1)*100:+.1f}%" if pe_f and pe_t and pe_t>0 else None
    bw2.metric("KGV erwartet", fmt(pe_f, ".1f", suf="x"), kgv_delta)
    bw3.metric("P/B Ratio",    fmt(f.get("price_to_book"),  ".2f", suf="x"))
    bw4.metric("P/S Ratio",    fmt(f.get("price_to_sales"), ".2f", suf="x"))

    # EPS & Wachstum
    st.markdown("#### EPS & Wachstum")
    g1,g2,g3,g4 = st.columns(4)
    g1.metric("EPS (TTM)",     fmt(f.get("eps_trailing"), ".2f", "$"))
    eps_f = f.get("eps_forward"); eps_t = f.get("eps_trailing")
    eps_delta = f"{((eps_f/eps_t)-1)*100:+.1f}% Wachstum" if eps_f and eps_t and eps_t > 0 else None
    g2.metric("EPS (erwartet)", fmt(eps_f, ".2f", "$"), eps_delta)
    g3.metric("Gewinnwachstum YoY", pct(f.get("earnings_growth_yoy")))
    g4.metric("Umsatzwachstum YoY", pct(f.get("revenue_growth")))

    # PEG
    st.markdown("#### 🎯 PEG Ratio")
    peg = f.get("peg_ratio")
    p1, p2 = st.columns([1,3])
    with p1:
        peg_text, peg_color = peg_info(peg)
        st.markdown(f"""
        <div style='background:#111;border:1px solid #1e1e1e;border-radius:12px;
                    padding:20px;text-align:center;border-top:3px solid {peg_color}'>
            <div style='font-family:RedRose,sans-serif;font-size:2.8rem;
                        font-weight:700;color:{peg_color}'>{fmt(peg,".2f")}</div>
            <div style='color:#555;font-size:0.8rem;margin-top:4px;font-family:RedRose,sans-serif'>
                PEG RATIO
            </div>
            <div style='color:{peg_color};font-size:0.82rem;margin-top:6px'>
                {'Günstig (< 1.5)' if peg and peg < 1.5 else 'Fair (1.5–2.5)' if peg and peg < 2.5 else 'Teuer (> 2.5)' if peg else '–'}
            </div>
        </div>
        """, unsafe_allow_html=True)
    with p2:
        st.markdown("""
        **PEG = KGV ÷ Gewinnwachstum %**

        | PEG | Bewertung | Stillhalter-Eignung |
        |---|---|---|
        | < 1.0 | Stark unterbewertet | ⭐⭐⭐ Ideal für Puts |
        | 1.0–1.5 | Günstig | ⭐⭐⭐ Sehr gut |
        | 1.5–2.5 | Fair bewertet | ⭐⭐ OK |
        | > 2.5 | Teuer / Wachstumsprämie | ⭐ Vorsicht |

        Ein niedriger PEG bedeutet: hohe Sicherheitsmarge für Puts —
        selbst bei Rückgang bleibt die Position fundamental gedeckt.
        """)

    # Rentabilität
    st.markdown("#### Rentabilität & Bilanz")
    r1,r2,r3,r4,r5 = st.columns(5)
    r1.metric("ROE",           pct(f.get("return_on_equity")))
    r2.metric("Profit Margin", pct(f.get("profit_margin")))
    fcf = f.get("free_cashflow")
    r3.metric("Free Cashflow", f"${fcf/1e9:.1f}B" if fcf and abs(fcf)>=1e9 else (f"${fcf/1e6:.0f}M" if fcf else "–"))
    r4.metric("Debt/Equity",   fmt((f.get("debt_to_equity") or 0)/100, ".2f") if f.get("debt_to_equity") else "–")
    r5.metric("Current Ratio", fmt(f.get("current_ratio"), ".2f"))

    if f.get("dividend_yield"):
        st.markdown("#### Dividende")
        d1,d2,d3 = st.columns(3)
        d1.metric("Dividendenrendite", pct(f.get("dividend_yield")))
        d2.metric("Dividende/Jahr",    fmt(f.get("dividend_rate"), ".2f", "$"))
        d3.metric("Payout Ratio",      pct(f.get("payout_ratio")))

    # Bewertungsdiagramm
    st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)
    chart_data = {k:v for k,v in [
        ("KGV aktuell", f.get("pe_trailing")),
        ("KGV erwartet", f.get("pe_forward")),
        ("P/B × 5", (f.get("price_to_book") or 0) * 5),
        ("PEG × 10", (f.get("peg_ratio") or 0) * 10),
    ] if v}
    if chart_data:
        fig_f = go.Figure(go.Bar(
            x=list(chart_data.keys()), y=list(chart_data.values()),
            marker=dict(
                color=["#d4a843","#b8912f","#4fc3f7","#22c55e"],
                line=dict(color="rgba(255,255,255,0.1)", width=1),
            ),
            text=[f"{v:.1f}" for v in chart_data.values()],
            textposition="outside", textfont=dict(color="#888", family="RedRose, sans-serif"),
        ))
        fig_f.update_layout(
            height=280, paper_bgcolor="#0c0c0c", plot_bgcolor="#0c0c0c",
            font=dict(color="#888", family="RedRose, sans-serif"),
            yaxis=dict(gridcolor="#161616", zeroline=False),
            xaxis=dict(tickfont=dict(color="#aaa")),
            showlegend=False, margin=dict(l=10,r=10,t=10,b=10),
        )
        st.plotly_chart(fig_f, use_container_width=True)
        st.caption("P/B × 5 und PEG × 10 zur besseren visuellen Vergleichbarkeit skaliert")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4: EARNINGS & NEWS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_news:
    # Earnings
    st.markdown("### 📅 Nächste Earnings")
    earnings_date = f.get("earnings_date")
    if earnings_date:
        try:
            ed_str = (earnings_date.strftime("%d.%m.%Y")
                      if hasattr(earnings_date, "strftime")
                      else str(earnings_date)[:10])
            dte_earn = calculate_dte(str(earnings_date)[:10])
            warn_color = "#ef4444" if dte_earn <= 14 else "#f59e0b" if dte_earn <= 30 else "#22c55e"
            st.markdown(f"""
            <div style='display:inline-block;background:#111;
                        border:2px solid {warn_color};border-radius:10px;padding:16px 24px'>
                <span style='font-family:RedRose,sans-serif;font-size:1.4rem;
                              font-weight:700;color:{warn_color}'>📅 {ed_str}</span>
                <span style='color:#666;margin-left:16px;font-family:RedRose,sans-serif'>
                    in {dte_earn} Tagen
                </span>
                {"<br><span style='color:#ef4444;font-size:0.82rem;font-family:RedRose,sans-serif'>⚠️ Earnings innerhalb des DTE — Vorsicht beim Stillhalten!</span>" if dte_earn <= 21 else ""}
            </div>
            """, unsafe_allow_html=True)
        except Exception:
            st.info(f"Earnings-Datum: {earnings_date}")
    else:
        st.info("Kein Earnings-Datum verfügbar.")

    if expirations and earnings_date:
        try:
            earn_str = str(earnings_date)[:10]
            before = [e for e in expirations if e < earn_str]
            after  = [e for e in expirations if e >= earn_str]
            st.markdown(
                f"**{len(before)}** Verfälle **vor** Earnings &nbsp;·&nbsp; "
                f"**{len(after)}** Verfälle **über/nach** Earnings"
            )
            if after:
                st.warning(f"Verfälle über Earnings (IV-Crush Risiko): {', '.join(after[:6])}")
        except Exception:
            pass

    st.markdown("---")
    st.markdown("### 📰 Aktuelle News")
    news = f.get("news", [])
    if not news:
        st.info("Keine News verfügbar.")
    else:
        for item in news:
            title  = item.get("title","")
            pub    = item.get("publisher","")
            link   = item.get("link","")
            t_str  = item.get("time","")
            href   = f'href="{link}" target="_blank"' if link else ""
            st.markdown(f"""
            <div class="news-card">
                <div class="news-title">
                    <a {href} style="color:#e0e0e0;text-decoration:none">{title}</a>
                </div>
                <div class="news-meta">🗞️ {pub} &nbsp;·&nbsp; 🕐 {t_str}</div>
            </div>
            """, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 5: BACKTEST
# ═══════════════════════════════════════════════════════════════════════════════
with tab_bt:
    from analysis.backtest import run_backtest
    from analysis.multi_timeframe import TREND_MODES

    st.markdown("### 🔬 Stillhalter Backtest")
    st.markdown("""
    <div style='font-family:RedRose,sans-serif;font-size:0.85rem;color:#666;
                line-height:1.7;margin-bottom:16px'>
        Simuliert historische Trades basierend auf dem <b style='color:#d4a843'>SC Trend Signal</b>.
        Prämien werden über <b style='color:#888'>Black-Scholes + historische Volatilität</b> berechnet,
        da Yahoo Finance keine historischen Optionspreise liefert.
        Ergebnisse sind <i>theoretisch</i> — reale Bid/Ask-Spreads & Slippage nicht enthalten.
    </div>
    """, unsafe_allow_html=True)

    # ── Backtest-Parameter ────────────────────────────────────────────────
    with st.expander("⚙️ **BACKTEST-EINSTELLUNGEN**", expanded=True):
        bc1, bc2, bc3, bc4, bc5 = st.columns(5)
        with bc1:
            bt_strategy = st.selectbox("Strategie", ["Cash Covered Put", "Covered Call"],
                                        key="bt_strategy")
        with bc2:
            bt_signal = st.selectbox("Einstiegs-Signal", [
                "SC Trend Cross ↑",
                "SC Trend bullish",
                "RSI < 30 + SC Trend",
                "Stoch Cross 20 ↑",
            ], key="bt_signal", help="Wann wird ein Trade eröffnet?")
        with bc3:
            bt_trend_mode = st.selectbox("Trend Mode",
                list(TREND_MODES.keys()), index=0, key="bt_trend_mode")
        with bc4:
            bt_delta = st.number_input("Ziel-Delta (abs.)", 0.10, 0.50, 0.25, 0.05,
                                        key="bt_delta",
                                        help="z.B. 0.25 = 25-Delta Put/Call")
            bt_dte = st.number_input("DTE (Tage)", 14, 90, 30, 7, key="bt_dte")
        with bc5:
            bt_period = st.selectbox("Zeitraum", ["1y", "2y", "3y", "5y"], index=2,
                                      key="bt_period")
            bt_rfr = st.number_input("Risikofreier Zinssatz %", 0.0, 10.0, 5.0, 0.5,
                                      key="bt_rfr") / 100
            bt_early_exit = st.number_input(
                "Early Exit %", 0.0, 90.0, 50.0, 10.0, key="bt_early_exit",
                help="0 = kein Early Exit · 50 = Position schließen wenn 50% des Gewinns erreicht"
            )
            bt_commission = st.number_input(
                "Kommission $/Kontrakt", 0.0, 5.0, 1.30, 0.10,
                format="%.2f", key="bt_commission",
                help="Open + Close Kommission. IBKR: ca. $0.65×2 = $1.30 pro Kontrakt"
            )

    bt_run = st.button("▶ Backtest starten", type="primary", key="bt_run")

    if bt_run:
        with st.spinner(f"Backtest läuft für {selected_ticker}..."):
            bt_result = run_backtest(
                ticker=selected_ticker,
                strategy=bt_strategy,
                trend_mode=bt_trend_mode,
                signal_type=bt_signal,
                target_delta=bt_delta,
                dte=int(bt_dte),
                period=bt_period,
                risk_free_rate=bt_rfr,
                early_exit_pct=float(bt_early_exit),
                commission_per_contract=float(bt_commission),
            )
        st.session_state["bt_result"] = bt_result
        st.session_state["bt_ticker"] = selected_ticker

    bt_result = st.session_state.get("bt_result")
    bt_cached_ticker = st.session_state.get("bt_ticker", "")

    if bt_result is not None:
        if bt_result.error:
            st.error(f"**Backtest-Fehler:** {bt_result.error}")
        elif bt_cached_ticker != selected_ticker:
            st.info("Ticker geändert — Backtest erneut starten.")
        else:
            st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

            # ── KPI-Kacheln ──────────────────────────────────────────────
            k1,k2,k3,k4,k5,k6,k7,k8 = st.columns(8)
            k1.metric("Trades",            bt_result.n_trades)
            k2.metric("Win Rate",          f"{bt_result.win_rate:.1f}%")
            k3.metric("Ø Rendite/Trade",   f"{bt_result.avg_return_pct:.2f}%")
            k4.metric("Ø Rendite ann.",    f"{bt_result.avg_annualized_pct:.1f}%")
            k5.metric("Gesamtrendite",     f"{bt_result.total_return_pct:.1f}%")
            k6.metric("Profit Faktor",     f"{bt_result.profit_factor:.2f}")
            k7.metric("Max Drawdown",      f"{bt_result.max_drawdown_pct:.1f}%",
                       delta_color="inverse")
            k8.metric("Bester Trade",      f"{bt_result.best_trade_pct:.2f}%")

            st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

            # ── Equity-Kurve ──────────────────────────────────────────────
            col_eq, col_dist = st.columns([3, 2])
            with col_eq:
                st.markdown("#### 📈 Equity-Kurve")
                eq = bt_result.equity_curve
                if not eq.empty:
                    fig_eq = go.Figure()
                    eq_color = "#22c55e" if float(eq.iloc[-1]) >= 100 else "#ef4444"
                    fig_eq.add_trace(go.Scatter(
                        x=eq.index, y=eq.values,
                        mode="lines", fill="tozeroy",
                        fillcolor="rgba(34,197,94,0.08)" if float(eq.iloc[-1]) >= 100
                                  else "rgba(239,68,68,0.08)",
                        line=dict(color=eq_color, width=2),
                        name="Kapital (Start=100)",
                        hovertemplate="%{x|%d.%m.%Y}: %{y:.1f}<extra></extra>",
                    ))
                    fig_eq.add_hline(y=100, line_dash="dot",
                                     line_color="rgba(212,168,67,0.4)",
                                     annotation_text="Start",
                                     annotation_font_color="#d4a843")
                    fig_eq.update_layout(
                        height=280,
                        paper_bgcolor="#0c0c0c", plot_bgcolor="#0c0c0c",
                        font=dict(color="#888", size=11),
                        xaxis=dict(gridcolor="#1a1a1a", zeroline=False),
                        yaxis=dict(
                            title=dict(text="Kapital (Basis 100)", font=dict(color="#888")),
                            gridcolor="#1a1a1a", zeroline=False,
                        ),
                        margin=dict(l=10, r=10, t=10, b=30),
                        showlegend=False,
                    )
                    st.plotly_chart(fig_eq, use_container_width=True)

            with col_dist:
                st.markdown("#### 📊 Trade-Verteilung")
                pnls = [t.pnl_pct for t in bt_result.trades]
                win_c  = sum(1 for p in pnls if p > 0)
                loss_c = sum(1 for p in pnls if p <= 0)
                fig_d = go.Figure()
                fig_d.add_trace(go.Bar(
                    x=["✅ Gewinn", "❌ Verlust"],
                    y=[win_c, loss_c],
                    marker_color=["#22c55e", "#ef4444"],
                    text=[f"{win_c}<br>{bt_result.avg_win_pct:.2f}% Ø",
                          f"{loss_c}<br>{bt_result.avg_loss_pct:.2f}% Ø"],
                    textposition="inside",
                    textfont=dict(color="#fff", size=11),
                ))
                fig_d.update_layout(
                    height=280,
                    paper_bgcolor="#0c0c0c", plot_bgcolor="#0c0c0c",
                    font=dict(color="#888", size=11),
                    xaxis=dict(gridcolor="#1a1a1a"),
                    yaxis=dict(gridcolor="#1a1a1a",
                               title=dict(text="Anzahl Trades",
                                         font=dict(color="#888"))),
                    margin=dict(l=10, r=10, t=10, b=30),
                    showlegend=False,
                )
                st.plotly_chart(fig_d, use_container_width=True)

            # ── Trade-Tabelle ─────────────────────────────────────────────
            st.markdown("#### 📋 Alle Trades")
            if not bt_result.trade_df.empty:

                def _color_result(val):
                    if "✅" in str(val):
                        return "color: #22c55e"
                    if "❌" in str(val):
                        return "color: #ef4444"
                    if "⚠️" in str(val):
                        return "color: #f59e0b"
                    return ""

                def _color_pnl(val):
                    try:
                        return "color: #22c55e" if float(val) >= 0 else "color: #ef4444"
                    except Exception:
                        return ""

                styled_bt = (
                    bt_result.trade_df.style
                    .applymap(_color_result, subset=["Ergebnis"])
                    .applymap(_color_pnl,    subset=["Rendite %", "P&L/Aktie", "Ann. %"])
                )
                st.dataframe(
                    styled_bt,
                    use_container_width=True,
                    hide_index=True,
                    height=400,
                    column_config={
                        "Kurs Einstieg":  st.column_config.NumberColumn(format="$%.2f"),
                        "Strike":         st.column_config.NumberColumn(format="$%.2f"),
                        "Prämie":         st.column_config.NumberColumn(format="$%.2f"),
                        "Kurs Verfall":   st.column_config.NumberColumn(format="$%.2f"),
                        "P&L/Aktie":      st.column_config.NumberColumn(format="$%.2f"),
                        "Rendite %":      st.column_config.NumberColumn(format="%.2f%%"),
                        "Ann. %":         st.column_config.NumberColumn(format="%.1f%%"),
                        "IV %":           st.column_config.NumberColumn(format="%.1f%%"),
                        "Delta":          st.column_config.NumberColumn(format="%.3f"),
                    },
                )

                # CSV-Export
                ex1, _ = st.columns([2, 10])
                with ex1:
                    st.download_button(
                        "📥 Trades exportieren",
                        bt_result.trade_df.to_csv(index=False),
                        f"backtest_{selected_ticker}_{bt_strategy.replace(' ','_')}.csv",
                        "text/csv", use_container_width=True
                    )

            # ── Hinweis zur Methodik ──────────────────────────────────────
            st.markdown("""
            <div style='background:#111;border:1px solid #1e1e1e;border-radius:8px;
                        padding:12px 16px;margin-top:12px;font-family:RedRose,sans-serif;
                        font-size:0.78rem;color:#444;line-height:1.7'>
                <b style='color:#555'>Methodik:</b>
                Einstieg bei aktivem SC Trend Signal · Strike via Black-Scholes Delta-Targeting ·
                Prämie = theoretischer B-S Preis (historische 20-Tage Volatilität) ·
                Ausstieg immer am Verfallstag · Keine Slippage / Kommissionen / Frühzuweisung ·
                Ergebnisse dienen der Orientierung, nicht als Handelsempfehlung.
            </div>
            """, unsafe_allow_html=True)
