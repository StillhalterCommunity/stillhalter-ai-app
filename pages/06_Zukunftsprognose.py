"""
Stillhalter AI App — Zukunftsprognose
Zukunftsprognose: Welche Aktien nähern sich einem Setup? Indikator-Proximity-Analyse.
Kein Machine Learning — reine Indikator-Proximity-Analyse.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from concurrent.futures import ThreadPoolExecutor, as_completed
import time
import threading
from typing import Optional, List

st.set_page_config(
    page_title="Zukunftsprognose · Stillhalter AI App",
    page_icon="🔭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)

from data.fetcher import fetch_price_history, fetch_earnings_date, calculate_dte
from analysis.technicals import analyze_technicals
from data.watchlist import WATCHLIST, ALL_TICKERS, get_sector_for_ticker, SECTOR_ICONS


# ══════════════════════════════════════════════════════════════════════════════
# RADAR SCORE ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def _rsi_series(close: pd.Series, period: int = 14) -> pd.Series:
    """RSI (14) als vollständige Serie — für Velocity-Berechnung."""
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_l = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs    = avg_g / avg_l.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def _slope(series: pd.Series, n: int = 5) -> float:
    """Lineare Steigung der letzten n Werte (Punkte/Tag)."""
    if len(series) < n:
        return 0.0
    y = series.iloc[-n:].values
    x = np.arange(n)
    try:
        return float(np.polyfit(x, y, 1)[0])
    except Exception:
        return 0.0


def _days_to_threshold(current: float, threshold: float, velocity: float) -> Optional[int]:
    """
    Schätzt Tage bis ein Indikator einen Schwellenwert erreicht.
    Gibt None zurück wenn Bewegung in falsche Richtung oder zu langsam.
    """
    if velocity == 0:
        return None
    diff = threshold - current
    if (diff > 0 and velocity <= 0) or (diff < 0 and velocity >= 0):
        return None
    days = diff / velocity
    if 1 <= days <= 30:
        return max(1, int(days))
    return None


def calculate_radar_score(ticker: str, setup_type: str = "auto") -> dict:
    """
    Berechnet Radar-Score (0–100) für einen Ticker.
    Misst wie nah alle Indikatoren an einem guten Stillhalter-Setup sind.

    Dimensionen (für Short PUT):
      RSI        30%  — Nähe zu Überverkauft-Zone
      Stochastik 25%  — Dual-Stoch Ready-Buy Annäherung
      MACD       20%  — Histogram dreht (bearisch→bullisch)
      Support    15%  — Preis nähert sich bekanntem Support
      Trend      10%  — Übergeordneter Trend noch intakt
    """
    empty = {
        "ticker": ticker, "radar_score": 0, "setup_type": "–",
        "days_est": None, "confidence": 0,
        "dim_scores": {}, "signals": [], "error": True,
    }

    try:
        hist = fetch_price_history(ticker, period="6mo")
        if hist is None or hist.empty or len(hist) < 30:
            return empty

        close = hist["Close"]
        high  = hist["High"]
        low   = hist["Low"]
        current_price = float(close.iloc[-1])

        tech = analyze_technicals(hist)
        if tech is None:
            return empty

        # ── RSI Proximity ───────────────────────────────────────────────────
        rsi       = _rsi_series(close)
        rsi_now   = float(rsi.iloc[-1])
        rsi_slope = _slope(rsi, 7)       # Punkte/Tag (negativ = fällt → Richtung 30)

        if rsi_now <= 25:
            rsi_score  = 100
            rsi_signal = f"RSI {rsi_now:.0f} — stark überverkauft ✅✅"
        elif rsi_now <= 35:
            rsi_score  = 90 - (rsi_now - 25) * 2
            rsi_signal = f"RSI {rsi_now:.0f} — überverkauft ✅"
        elif rsi_now <= 45:
            proximity  = (45 - rsi_now) / 10   # 0–1
            momentum   = max(0, -rsi_slope / 2)  # bonus wenn fallend
            rsi_score  = 55 + proximity * 30 + momentum * 15
            d = _days_to_threshold(rsi_now, 30, rsi_slope)
            rsi_signal = f"RSI {rsi_now:.0f} nähert sich 30" + (f" (~{d}T)" if d else "") + \
                         (" ↘" if rsi_slope < -0.3 else "")
        elif rsi_now <= 60:
            rsi_score  = max(0, 55 - (rsi_now - 45) * 3.5)
            rsi_signal = f"RSI {rsi_now:.0f} — neutral, kein Signal"
        else:
            rsi_score  = max(0, 10 - (rsi_now - 60) * 0.5)
            rsi_signal = f"RSI {rsi_now:.0f} — überkauft (ungünstig)"

        rsi_days = _days_to_threshold(rsi_now, 32, rsi_slope)

        # ── Dual Stochastik Proximity ───────────────────────────────────────
        fast_k     = float(tech.stoch_k)
        fast_d     = float(tech.stoch_d)
        stoch_slope = _slope(
            pd.Series([tech.stoch_k] * 5 + [fast_k]),  # näherungsweise
            5
        )
        # Besser: direkte Stoch-Serie berechnen
        try:
            lowest  = low.rolling(14).min()
            highest = high.rolling(14).max()
            raw_k   = (close - lowest) / (highest - lowest + 1e-10) * 100
            smooth_k = raw_k.rolling(3).mean()
            stoch_slope = _slope(smooth_k, 7)
        except Exception:
            stoch_slope = 0.0

        if fast_k <= 20:
            stoch_score  = 100
            stoch_signal = f"Stoch K {fast_k:.0f} — überverkauft ✅✅"
        elif fast_k <= 30:
            stoch_score  = 85 + (30 - fast_k) * 1.5
            stoch_signal = f"Stoch K {fast_k:.0f} — nähert sich Überverkauft ✅"
        elif fast_k <= 45:
            proximity   = (45 - fast_k) / 15
            momentum    = max(0, -stoch_slope / 3)
            stoch_score = 45 + proximity * 35 + momentum * 20
            d = _days_to_threshold(fast_k, 20, stoch_slope)
            stoch_signal = f"Stoch K {fast_k:.0f} fällt" + (f" (~{d}T bis Überverkauft)" if d else "")
        else:
            stoch_score  = max(0, 45 - (fast_k - 45) * 1.5)
            stoch_signal = f"Stoch K {fast_k:.0f} — noch zu hoch"

        # Bonus: Fast K unter Fast D (crossover imminent wenn beide niedrig)
        if fast_k < fast_d and fast_k < 50:
            stoch_score = min(100, stoch_score + 8)

        stoch_days = _days_to_threshold(fast_k, 20, stoch_slope)

        # ── MACD Momentum ──────────────────────────────────────────────────
        if tech.sc_macd and tech.sc_macd.hist is not None:
            h_series   = tech.sc_macd.hist
            h_now      = float(h_series.iloc[-1])
            h_slope    = _slope(h_series, 7)
            macd_val   = float(tech.sc_macd.macd_val)
            sig_val    = float(tech.sc_macd.signal_val)
            macd_gap   = macd_val - sig_val

            if h_now >= 0 and h_slope >= 0:
                macd_score  = 90
                macd_signal = f"MACD Hist. positiv & steigend ✅✅"
            elif h_now < 0 and h_slope > 0:
                # Dreht: wie nah an Null?
                d_to_zero = abs(h_now) / h_slope if h_slope > 0 else 99
                proximity = max(0, 1 - d_to_zero / 10)
                macd_score  = 55 + proximity * 40
                d = max(1, int(d_to_zero)) if d_to_zero < 20 else None
                macd_signal = f"MACD Hist. dreht aufwärts" + (f" (~{d}T bis Null)" if d else "")
            elif h_now >= 0 and h_slope < 0:
                macd_score  = 60
                macd_signal = f"MACD positiv aber nachlassend"
            else:
                macd_score  = max(0, 30 + h_slope * 5)
                macd_signal = f"MACD Hist. negativ & fällt"

            macd_days = (max(1, int(abs(h_now) / h_slope))
                         if h_slope > 0 and h_now < 0 and h_slope < 20
                         else None)
        else:
            macd_score  = 40
            macd_signal = "MACD — kein Signal"
            macd_days   = None

        # ── Support Proximity ───────────────────────────────────────────────
        price_slope = _slope(close, 10)   # USD/Tag (negativ = fällt → Support)

        if tech.support_levels:
            below = [s for s in tech.support_levels if s < current_price]
            if below:
                nearest = max(below)
                dist_pct = (current_price - nearest) / current_price * 100
                days_to_sup = _days_to_threshold(current_price, nearest, price_slope)

                if dist_pct <= 1.5:
                    sup_score  = 95
                    sup_signal = f"Kurs {dist_pct:.1f}% über Support USD {nearest:.2f} (sehr eng)"
                elif dist_pct <= 4:
                    sup_score  = 85
                    sup_signal = f"Kurs {dist_pct:.1f}% über Support {nearest:.2f} ✅"
                elif dist_pct <= 8:
                    sup_score  = 60 + (8 - dist_pct) * 5
                    sup_signal = f"Support {nearest:.2f} in {dist_pct:.1f}%" + \
                                 (f" (~{days_to_sup}T)" if days_to_sup else "")
                elif dist_pct <= 15:
                    sup_score  = max(20, 60 - dist_pct * 3)
                    sup_signal = f"Support {nearest:.2f} in {dist_pct:.1f}% — noch weit"
                else:
                    sup_score  = 10
                    sup_signal = f"Support weit entfernt ({dist_pct:.1f}%)"
            else:
                sup_score  = 25
                sup_signal = "Kein Support unter aktuellem Kurs"
        else:
            sup_score  = 30
            sup_signal = "Support nicht berechenbar"
            days_to_sup = None

        # ── Trend-Qualität ──────────────────────────────────────────────────
        trend_sc = float(tech.trend_score)

        if tech.trend == "bullish" and trend_sc >= 65:
            trend_score  = 95
            trend_signal = f"↑ Starker Aufwärtstrend (Score {trend_sc:.0f}) ✅"
        elif tech.trend == "bullish" and trend_sc >= 45:
            trend_score  = 75
            trend_signal = f"↑ Aufwärtstrend (Score {trend_sc:.0f})"
        elif tech.trend == "bullish" and trend_sc >= 30:
            trend_score  = 55
            trend_signal = f"↑ Aufwärtstrend schwächt ab (Score {trend_sc:.0f})"
        elif tech.trend == "neutral":
            trend_score  = 40
            trend_signal = f"→ Seitwärtstrend (Score {trend_sc:.0f})"
        else:
            trend_score  = max(5, 35 - (50 - trend_sc) * 0.5)
            trend_signal = f"↓ Abwärtstrend (Score {trend_sc:.0f}) — ungünstig für PUT"

        # ── Gewichteter Radar-Score ────────────────────────────────────────
        dim_scores = {
            "RSI":        round(rsi_score,   1),
            "Stochastik": round(stoch_score, 1),
            "MACD":       round(macd_score,  1),
            "Support":    round(sup_score,   1),
            "Trend":      round(trend_score, 1),
        }
        weights = {"RSI": 0.30, "Stochastik": 0.25, "MACD": 0.20, "Support": 0.15, "Trend": 0.10}
        radar_score = sum(dim_scores[k] * weights[k] for k in weights)

        # ── Setup-Typ bestimmen ────────────────────────────────────────────
        if setup_type == "auto":
            if tech.trend in ("bullish", "neutral"):
                best_setup = "Short PUT"
            else:
                best_setup = "Covered CALL"
        else:
            best_setup = setup_type

        # ── Estimated Days (Median der Einzel-Schätzungen) ─────────────────
        day_estimates = [d for d in [rsi_days, stoch_days, macd_days] if d is not None]
        if day_estimates:
            days_est = int(np.median(day_estimates))
            confidence = min(100, len(day_estimates) * 33)
        else:
            days_est   = None
            confidence = 0

        # ── Konvergenz-Check: Wie viele Signale konvergieren? ──────────────
        converging = sum([
            rsi_slope < -0.5 and rsi_now > 30,           # RSI fällt
            stoch_slope < -1 and fast_k > 20,             # Stoch fällt
            (tech.sc_macd.hist is not None and
             tech.sc_macd.hist.iloc[-1] < 0 and
             _slope(tech.sc_macd.hist, 7) > 0)
             if tech.sc_macd else False,                   # MACD dreht
            price_slope < 0 and bool(tech.support_levels), # Kurs fällt Richtung Support
        ])

        return {
            "ticker":      ticker,
            "radar_score": round(radar_score, 1),
            "setup_type":  best_setup,
            "days_est":    days_est,
            "confidence":  confidence,
            "converging":  converging,   # 0–4: wie viele Indikatoren gleichzeitig
            "dim_scores":  dim_scores,
            "signals": [
                rsi_signal,
                stoch_signal,
                macd_signal,
                sup_signal,
                trend_signal,
            ],
            "rsi_now":       round(rsi_now, 1),
            "fast_k":        round(fast_k, 1),
            "trend":         tech.trend,
            "trend_score":   round(trend_sc, 1),
            "current_price": round(current_price, 2),
            "error":         False,
        }

    except Exception as e:
        empty["error_msg"] = str(e)
        return empty


# ══════════════════════════════════════════════════════════════════════════════
# RADAR CHART (Spider / Polar)
# ══════════════════════════════════════════════════════════════════════════════

def make_radar_chart(results, title: str = "") -> go.Figure:
    """Erstellt einen Spinnen-Chart für bis zu 5 Aktien."""
    dims   = ["RSI", "Stochastik", "MACD", "Support", "Trend"]
    colors = ["#d4a843", "#22c55e", "#60a5fa", "#f97316", "#a78bfa",
              "#ef4444", "#ec4899", "#14b8a6"]

    fig = go.Figure()
    for i, res in enumerate(results[:8]):
        scores = [res["dim_scores"].get(d, 0) for d in dims]
        scores.append(scores[0])   # Kreis schließen
        color = colors[i % len(colors)]

        fig.add_trace(go.Scatterpolar(
            r=scores,
            theta=dims + [dims[0]],
            fill="toself",
            name=f"{res['ticker']} ({res['radar_score']:.0f})",
            line=dict(color=color, width=2),
            fillcolor=color.replace("#", "rgba(").rstrip(")") + ",0.08)"
            if color.startswith("#") else color,
            opacity=0.9,
        ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True, range=[0, 100],
                gridcolor="#1a1a1a", linecolor="#333",
                tickfont=dict(color="#555", size=9),
                tickvals=[20, 40, 60, 80, 100],
            ),
            angularaxis=dict(
                gridcolor="#1a1a1a", linecolor="#333",
                tickfont=dict(color="#aaa", size=11),
            ),
            bgcolor="#0c0c0c",
        ),
        paper_bgcolor="#0c0c0c",
        font=dict(color="#888", family="RedRose, sans-serif"),
        legend=dict(
            bgcolor="rgba(0,0,0,0.6)", bordercolor="#333",
            borderwidth=1, font=dict(color="#ccc", size=10),
        ),
        margin=dict(l=40, r=40, t=40, b=20),
        height=400,
        title=dict(text=title, font=dict(color="#d4a843", size=13)) if title else None,
    )
    return fig


def make_convergence_bar(results) -> go.Figure:
    """Balkendiagramm der Top-Radar-Scores mit Konvergenz-Info."""
    if not results:
        return go.Figure()

    top = sorted(results, key=lambda x: x["radar_score"], reverse=True)[:25]

    colors = []
    for r in top:
        sc = r["radar_score"]
        if sc >= 70:
            colors.append("#22c55e")
        elif sc >= 55:
            colors.append("#d4a843")
        elif sc >= 40:
            colors.append("#60a5fa")
        else:
            colors.append("#444")

    conv_text = [f"{'🔥' * r['converging']} {r['ticker']}" for r in top]

    fig = go.Figure(go.Bar(
        y=[r["ticker"] for r in top],
        x=[r["radar_score"] for r in top],
        orientation="h",
        marker_color=colors,
        text=[f"{r['radar_score']:.0f}" for r in top],
        textposition="outside",
        textfont=dict(color="#ccc", size=10),
        customdata=[[r["setup_type"], r.get("days_est", "–"),
                     r["converging"], r["trend"]] for r in top],
        hovertemplate=(
            "<b>%{y}</b><br>"
            "Radar Score: %{x:.1f}<br>"
            "Setup: %{customdata[0]}<br>"
            "Est. Tage: %{customdata[1]}<br>"
            "Konvergenz: %{customdata[2]}/4 Signale<br>"
            "Trend: %{customdata[3]}"
            "<extra></extra>"
        ),
    ))
    fig.add_vline(x=70, line_dash="dot", line_color="rgba(34,197,94,0.5)",
                  annotation_text="Bald bereit", annotation_font_color="#22c55e",
                  annotation_font_size=9)
    fig.add_vline(x=55, line_dash="dot", line_color="rgba(212,168,67,0.4)",
                  annotation_text="Im Aufbau", annotation_font_color="#d4a843",
                  annotation_font_size=9)
    fig.update_layout(
        height=max(300, len(top) * 22),
        paper_bgcolor="#0c0c0c", plot_bgcolor="#0c0c0c",
        font=dict(color="#888", size=10),
        xaxis=dict(range=[0, 110], gridcolor="#1a1a1a",
                   title=dict(text="Radar Score (0–100)", font=dict(color="#666"))),
        yaxis=dict(gridcolor="#111", autorange="reversed"),
        margin=dict(l=10, r=60, t=10, b=10),
        showlegend=False,
    )
    return fig


# ══════════════════════════════════════════════════════════════════════════════
# SEITE
# ══════════════════════════════════════════════════════════════════════════════

# Header
col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.markdown(get_logo_html("white", 40), unsafe_allow_html=True)
with col_title:
    st.markdown("""
    <div style='padding-top:4px'>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.8rem;
                    color:#f0f0f0;letter-spacing:0.04em'>🔭 ZUKUNFTSPROGNOSE</div>
        <div style='font-family:RedRose,sans-serif;font-weight:300;font-size:0.8rem;
                    color:#666;text-transform:uppercase;letter-spacing:0.12em;margin-top:2px'>
            Indikator-Proximity · Welche Aktien nähern sich einem Setup? · Extrapolation
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# Disclaimer
st.markdown("""
<div style='background:#1a1205;border:1px solid #3a2a05;border-left:4px solid #f59e0b;
            border-radius:8px;padding:10px 16px;font-family:sans-serif;font-size:0.8rem;
            color:#888;margin-bottom:16px'>
    📡 <b style='color:#f59e0b'>Kein Kurs-Prediction</b> — Die Zukunftsprognose misst wie nah
    <i>aktuelle Indikatoren</i> an einem guten Stillhalter-Setup sind und extrapoliert die
    aktuelle Bewegungsgeschwindigkeit. <b>Keine Garantie für zukünftige Kurs- oder
    Indikator-Entwicklungen.</b> Nur zur strategischen Planung.
</div>
""", unsafe_allow_html=True)

# ── Konzept-Erklärung ──────────────────────────────────────────────────────────
with st.expander("💡 **Wie funktioniert die Zukunftsprognose?**", expanded=False):
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        **Radar Score (0–100)** misst die Nähe zu einem Short PUT Setup:

        | Dimension | Gewicht | Bedeutung |
        |-----------|---------|-----------|
        | **RSI** | 30% | Nähe zur Überverkauft-Zone (< 30) |
        | **Stochastik** | 25% | Fast K nähert sich 20 |
        | **MACD** | 20% | Histogram dreht von negativ nach positiv |
        | **Support** | 15% | Kurs nähert sich bekanntem S/R-Level |
        | **Trend** | 10% | Übergeordneter Aufwärtstrend intakt |

        **Score-Interpretation:**
        - 🟢 **≥ 70** — Bald bereit, genau beobachten
        - 🟡 **55–69** — Im Aufbau, auf Watchlist setzen
        - 🔵 **40–54** — Noch zu früh
        - ⚪ **< 40** — Kein Setup in Sicht
        """)
    with c2:
        st.markdown("""
        **Konvergenz-Score 🔥** zeigt wie viele Indikatoren
        *gleichzeitig* in die richtige Richtung laufen:

        | 🔥 | Bedeutung |
        |----|-----------|
        | 🔥🔥🔥🔥 | Alle 4 Indikatoren konvergieren — starkes Setup |
        | 🔥🔥🔥 | 3 von 4 konvergieren — gut |
        | 🔥🔥 | 2 konvergieren — beobachten |
        | 🔥 | Nur 1 Signal — noch nicht bereit |

        **"Est. Tage"** = Extrapolation der aktuellen
        Bewegungsgeschwindigkeit bis zum Setup-Niveau.
        Hohe Unsicherheit — als grobe Orientierung verwenden.

        **Wichtig:** Radar-Score hoch ≠ Trade-Signal.
        Warte auf Bestätigung durch Echtzeit-Scanner!
        """)

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── Scan-Einstellungen ─────────────────────────────────────────────────────────
sc1, sc2, sc3, sc4, sc5 = st.columns(5)
with sc1:
    scan_sector = st.selectbox("Sektor",
        ["🌐 Alle Sektoren"] + list(WATCHLIST.keys()), key="radar_sector")
with sc2:
    setup_filter = st.selectbox("Setup-Typ",
        ["Auto (Trend-basiert)", "Short PUT", "Covered CALL"], key="radar_setup")
with sc3:
    min_radar = st.number_input("Mind. Radar Score", 0, 100, 0, 5, key="radar_min",
        help="0 = alle anzeigen · ≥ 55 = interessant · ≥ 70 = bald bereit")
with sc4:
    min_conv = st.selectbox("Min. Konvergenz", ["Alle", "🔥 1+", "🔥🔥 2+", "🔥🔥🔥 3+"],
        key="radar_conv", help="Wie viele Indikatoren müssen gleichzeitig konvergieren")
with sc5:
    max_days = st.number_input("Max. Est. Tage (0=alle)", 0, 30, 0, 1, key="radar_days",
        help="Filtert nach geschätzter Tage bis Setup (0 = kein Filter)")

# Tickers bestimmen
if "Alle" in scan_sector:
    scan_tickers = ALL_TICKERS
else:
    scan_tickers = WATCHLIST.get(scan_sector, [])

min_conv_n = {"Alle": 0, "🔥 1+": 1, "🔥🔥 2+": 2, "🔥🔥🔥 3+": 3}.get(min_conv, 0)
setup_arg  = "auto" if "Auto" in setup_filter else setup_filter

btn_c1, btn_c2, btn_c3, _ = st.columns([2, 2, 2, 6])
with btn_c1:
    start_scan = st.button(f"📡 Radar-Scan ({len(scan_tickers)} Aktien)",
                           type="primary", use_container_width=True)
with btn_c2:
    if st.button("🗑️ Cache leeren", use_container_width=True):
        st.cache_data.clear()
        if "radar_results" in st.session_state:
            del st.session_state["radar_results"]
        st.rerun()
with btn_c3:
    show_top_n = st.number_input("Top N anzeigen", 5, 50, 15, 5, key="radar_top_n",
                                  label_visibility="collapsed")

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

if "radar_results" not in st.session_state:
    st.session_state.radar_results = []

# ── Scan ausführen ─────────────────────────────────────────────────────────────
if start_scan:
    st.session_state.radar_results = []
    progress_ph = st.progress(0.0)
    status_ph   = st.empty()
    live_ph     = st.empty()

    all_results = []
    total       = len(scan_tickers)
    completed   = 0
    lock        = threading.Lock()

    def _scan_one(ticker):
        res = calculate_radar_score(ticker, setup_arg)
        time.sleep(0.05)
        return res

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_scan_one, t): t for t in scan_tickers}

        for future in as_completed(futures):
            ticker_done = futures[future]
            try:
                res = future.result(timeout=25)
                if not res.get("error", True):
                    with lock:
                        all_results.append(res)
            except Exception:
                pass

            with lock:
                completed += 1
            pct = completed / total
            progress_ph.progress(pct)

            # Live-Vorschau der Top-10 alle 10 Ticker
            if completed % 10 == 0 or completed == total:
                with lock:
                    preview = sorted(all_results,
                                     key=lambda x: x["radar_score"], reverse=True)[:10]
                status_ph.markdown(
                    f"📡 **Radar-Scan:** {completed}/{total} analysiert · "
                    f"**{len(all_results)} Ergebnisse** · "
                    f"Top: {preview[0]['ticker']} ({preview[0]['radar_score']:.0f})"
                    if preview else f"📡 **Radar-Scan:** {completed}/{total}…"
                )
                if preview:
                    live_df = pd.DataFrame([{
                        "Ticker":    r["ticker"],
                        "Radar":     r["radar_score"],
                        "Setup":     r["setup_type"],
                        "Est. Tage": r["days_est"] or "–",
                        "🔥 Konv.":  "🔥" * r["converging"],
                        "Trend":     r["trend"],
                        "RSI":       r["rsi_now"],
                        "Stoch K":   r["fast_k"],
                    } for r in preview])
                    live_ph.dataframe(live_df, use_container_width=True,
                                      hide_index=True, height=260)

    progress_ph.progress(1.0)
    live_ph.empty()
    status_ph.markdown(f"✅ **Scan abgeschlossen** — {len(all_results)} Aktien analysiert")
    st.session_state.radar_results = all_results

# ── Ergebnisse anzeigen ────────────────────────────────────────────────────────
results = st.session_state.radar_results

if not results:
    st.markdown("""
    <div style='text-align:center;padding:4rem 2rem;color:#333'>
        <div style='font-size:3rem'>📡</div>
        <div style='font-family:RedRose,sans-serif;font-size:1.1rem;margin-top:1rem;color:#555'>
            Scan starten um die Watchlist zu analysieren
        </div>
        <div style='font-family:RedRose,sans-serif;font-size:0.85rem;margin-top:0.5rem;color:#333'>
            Die Zukunftsprognose misst wie nah Aktien einem guten Setup sind —
            nicht ob sie bereits handelbar sind.
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    # Filter anwenden
    view = [r for r in results if not r.get("error", True)]
    if min_radar > 0:
        view = [r for r in view if r["radar_score"] >= min_radar]
    if min_conv_n > 0:
        view = [r for r in view if r["converging"] >= min_conv_n]
    if max_days > 0:
        view = [r for r in view if r["days_est"] is not None and r["days_est"] <= max_days]

    view_sorted = sorted(view, key=lambda x: x["radar_score"], reverse=True)
    top_n       = int(show_top_n)

    # ── KPI ───────────────────────────────────────────────────────────────────
    n_ready    = sum(1 for r in view if r["radar_score"] >= 70)
    n_building = sum(1 for r in view if 55 <= r["radar_score"] < 70)
    n_early    = sum(1 for r in view if r["radar_score"] < 55)
    n_conv3    = sum(1 for r in view if r["converging"] >= 3)

    km = st.columns(5)
    km[0].metric("Analysiert",      len(results))
    km[1].metric("🟢 Bald bereit",  n_ready,    help="Radar Score ≥ 70")
    km[2].metric("🟡 Im Aufbau",    n_building, help="Radar Score 55–69")
    km[3].metric("⚪ Zu früh",      n_early,    help="Radar Score < 55")
    km[4].metric("🔥🔥🔥 Multi-Konv.", n_conv3, help="3+ Indikatoren konvergieren")

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    # ── Tabs ──────────────────────────────────────────────────────────────────
    tab_cards, tab_bar, tab_radar, tab_table = st.tabs([
        "🃏 Karten", "📊 Ranking", "🕸️ Radar-Chart", "📋 Tabelle"
    ])

    # ── KARTEN ────────────────────────────────────────────────────────────────
    with tab_cards:
        if not view_sorted:
            st.info("Keine Aktien mit diesen Filterkriterien.")
        else:
            for i in range(0, min(top_n, len(view_sorted)), 3):
                chunk = view_sorted[i:i+3]
                cols  = st.columns(3, gap="small")
                for col, res in zip(cols, chunk):
                    sc      = res["radar_score"]
                    conv    = res["converging"]
                    days    = res["days_est"]
                    signals = res["signals"]
                    setup   = res["setup_type"]
                    ticker  = res["ticker"]
                    sektor  = get_sector_for_ticker(ticker)
                    sektor_s = sektor.split(".", 1)[-1].strip().split("(")[0].strip() \
                               if "." in sektor else sektor

                    # Score-Farbe
                    if sc >= 70:
                        sc_color = "#22c55e"
                        sc_label = "🟢 Bald bereit"
                        sc_bg    = "#0a1a0f"
                        sc_border= "#0f3320"
                    elif sc >= 55:
                        sc_color = "#d4a843"
                        sc_label = "🟡 Im Aufbau"
                        sc_bg    = "#1a1508"
                        sc_border= "#3a2f0a"
                    elif sc >= 40:
                        sc_color = "#60a5fa"
                        sc_label = "🔵 Beobachten"
                        sc_bg    = "#0a0f1a"
                        sc_border= "#0f2040"
                    else:
                        sc_color = "#555"
                        sc_label = "⚪ Zu früh"
                        sc_bg    = "#0e0e0e"
                        sc_border= "#222"

                    # Dimension-Bars (Mini-Progress)
                    dim_bars = ""
                    for dim, val in res["dim_scores"].items():
                        bar_col = "#22c55e" if val >= 70 else ("#f59e0b" if val >= 45 else "#555")
                        dim_bars += (
                            f"<div style='display:flex;align-items:center;gap:6px;margin:2px 0'>"
                            f"<span style='font-size:0.62rem;color:#555;font-family:sans-serif;"
                            f"width:65px;flex-shrink:0'>{dim}</span>"
                            f"<div style='flex:1;background:#1a1a1a;border-radius:3px;height:5px'>"
                            f"<div style='width:{val:.0f}%;background:{bar_col};height:5px;"
                            f"border-radius:3px'></div></div>"
                            f"<span style='font-size:0.6rem;color:{bar_col};font-family:sans-serif;"
                            f"width:28px;text-align:right'>{val:.0f}</span>"
                            f"</div>"
                        )

                    # Signal-Liste (max 3)
                    sig_html = "".join(
                        f"<div style='font-size:0.7rem;color:#888;font-family:sans-serif;"
                        f"padding:2px 0;border-bottom:1px solid #111;line-height:1.3'>"
                        f"{s}</div>"
                        for s in signals[:3]
                    )

                    days_html = (
                        f"<span style='color:#a78bfa'>~{days}T bis Setup</span>"
                        if days else "<span style='color:#444'>–</span>"
                    )

                    conv_html = "🔥" * conv + (
                        "<span style='color:#333;font-size:0.7rem'> (kein Impuls)</span>"
                        if conv == 0 else ""
                    )

                    with col:
                        st.html(f"""
                        <div style='background:{sc_bg};border:1px solid {sc_border};
                                    border-radius:12px;padding:14px;
                                    border-top:3px solid {sc_color};margin-bottom:4px'>

                            <!-- Header -->
                            <div style='display:flex;justify-content:space-between;
                                        align-items:flex-start;margin-bottom:10px'>
                                <div>
                                    <div style='font-size:1.1rem;font-weight:700;color:#f0f0f0;
                                                font-family:sans-serif'>{ticker}</div>
                                    <div style='font-size:0.72rem;color:#555;
                                                font-family:sans-serif'>{sektor_s}</div>
                                </div>
                                <div style='text-align:right'>
                                    <div style='font-size:1.6rem;font-weight:900;
                                                color:{sc_color};font-family:sans-serif;
                                                line-height:1'>{sc:.0f}</div>
                                    <div style='font-size:0.65rem;color:{sc_color};
                                                font-family:sans-serif'>{sc_label}</div>
                                </div>
                            </div>

                            <!-- Setup + Konvergenz -->
                            <div style='display:flex;justify-content:space-between;
                                        margin-bottom:10px'>
                                <span style='background:#111;border-radius:5px;padding:3px 8px;
                                             font-size:0.72rem;color:#d4a843;font-family:sans-serif'>
                                    {setup}</span>
                                <span style='font-size:0.85rem'>{conv_html}</span>
                            </div>

                            <!-- Dimension Bars -->
                            <div style='margin-bottom:10px'>{dim_bars}</div>

                            <!-- Signale -->
                            <div style='margin-bottom:8px'>{sig_html}</div>

                            <!-- Footer -->
                            <div style='display:flex;justify-content:space-between;
                                        font-family:sans-serif;font-size:0.72rem;color:#555'>
                                <span>RSI {res['rsi_now']:.0f} · Stoch {res['fast_k']:.0f}</span>
                                {days_html}
                            </div>
                        </div>
                        """)

    # ── RANKING BAR ───────────────────────────────────────────────────────────
    with tab_bar:
        fig_bar = make_convergence_bar(view_sorted)
        st.plotly_chart(fig_bar, use_container_width=True)
        st.caption(
            "🔥 = Konvergenz-Score (wie viele Indikatoren gleichzeitig in Richtung Setup laufen). "
            "Grün ≥ 70 · Gold 55–69 · Blau 40–54"
        )

    # ── RADAR CHART ───────────────────────────────────────────────────────────
    with tab_radar:
        top5 = view_sorted[:5]
        if not top5:
            st.info("Keine Daten für Radar-Chart.")
        else:
            st.markdown("**Top 5 Aktien im Vergleich** — Spinnen-Chart je Indikator-Dimension:")
            fig_radar = make_radar_chart(top5, f"Radar-Vergleich Top 5 · {scan_sector}")
            st.plotly_chart(fig_radar, use_container_width=True)
            st.caption(
                "Außen = Indikator nah am Setup-Level (Score 100). "
                "Innen = weit entfernt. Ideal: gleichmäßig großes Polygon."
            )

            # Einzelne Radar-Charts für Top 3
            if len(view_sorted) >= 3:
                st.markdown("---")
                st.markdown("**Einzel-Analyse Top 3:**")
                r3c = st.columns(3)
                for col, res in zip(r3c, view_sorted[:3]):
                    fig_single = make_radar_chart([res])
                    fig_single.update_layout(height=280, margin=dict(l=20, r=20, t=30, b=10),
                                             showlegend=False)
                    with col:
                        st.markdown(f"**{res['ticker']}** — Score {res['radar_score']:.0f}")
                        st.plotly_chart(fig_single, use_container_width=True)

    # ── TABELLE ───────────────────────────────────────────────────────────────
    with tab_table:
        table_rows = []
        for res in view_sorted:
            sektor_t = get_sector_for_ticker(res["ticker"])
            sektor_t = sektor_t.split(".", 1)[-1].strip().split("(")[0].strip() \
                       if "." in sektor_t else sektor_t
            table_rows.append({
                "Ticker":       res["ticker"],
                "Sektor":       sektor_t,
                "Radar Score":  res["radar_score"],
                "Status":       "🟢 Bald bereit" if res["radar_score"] >= 70
                                else ("🟡 Im Aufbau" if res["radar_score"] >= 55
                                else ("🔵 Beobachten" if res["radar_score"] >= 40
                                else "⚪ Zu früh")),
                "Setup":        res["setup_type"],
                "Est. Tage":    res["days_est"],
                "🔥 Konv.":     res["converging"],
                "RSI":          res["rsi_now"],
                "Stoch K":      res["fast_k"],
                "Trend":        res["trend"],
                "Trend Score":  res["trend_score"],
                "Kurs":         res["current_price"],
                "RSI Score":    res["dim_scores"].get("RSI", 0),
                "Stoch Score":  res["dim_scores"].get("Stochastik", 0),
                "MACD Score":   res["dim_scores"].get("MACD", 0),
                "Sup. Score":   res["dim_scores"].get("Support", 0),
            })

        tbl = pd.DataFrame(table_rows)
        if not tbl.empty:
            st.dataframe(
                tbl, use_container_width=True, hide_index=True, height=520,
                column_config={
                    "Radar Score":  st.column_config.ProgressColumn(
                                        "Radar Score", min_value=0, max_value=100, format="%.1f"),
                    "🔥 Konv.":    st.column_config.NumberColumn("🔥 Konv.", format="%d/4"),
                    "RSI":          st.column_config.NumberColumn("RSI", format="%.1f"),
                    "Stoch K":      st.column_config.NumberColumn("Stoch K", format="%.1f"),
                    "Kurs":         st.column_config.NumberColumn("Kurs", format="$%.2f"),
                    "Est. Tage":    st.column_config.NumberColumn("Est. Tage", format="%d T"),
                },
            )

            # Export
            ex_c, _ = st.columns([2, 10])
            with ex_c:
                st.download_button(
                    "📥 Export (CSV)",
                    tbl.to_csv(index=False),
                    f"radar_scan_{pd.Timestamp.now().strftime('%Y%m%d_%H%M')}.csv",
                    "text/csv",
                    use_container_width=True,
                )
