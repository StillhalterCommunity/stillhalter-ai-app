"""
Stillhalter Community Dashboard — Startseite
"""

import streamlit as st
import pandas as pd
import pickle
import os
from datetime import datetime

st.set_page_config(
    page_title="Stillhalter Community Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.theme import get_css, get_logo_html
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)

from data.fetcher import market_status_text, is_market_open

# ── Header ────────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.markdown(get_logo_html("white", 48), unsafe_allow_html=True)
with col_title:
    market_open = is_market_open()
    mkt_class = "market-open" if market_open else "market-closed"
    st.markdown(f"""
    <div style='padding-top:6px'>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:2rem;
                    color:#f0f0f0;letter-spacing:0.04em'>
            STILLHALTER COMMUNITY
        </div>
        <div style='font-family:RedRose,sans-serif;font-weight:300;font-size:0.8rem;
                    color:#666;text-transform:uppercase;letter-spacing:0.15em;margin-top:2px'>
            Options Trading Dashboard · <span class="{mkt_class}">{market_status_text()}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)
st.markdown("<br>", unsafe_allow_html=True)

# ── Navigation Cards ──────────────────────────────────────────────────────────
c1, c2 = st.columns(2, gap="large")

with c1:
    st.markdown("""
    <div style='background:#111;border:1px solid #1e1e1e;border-radius:14px;
                padding:28px 28px 24px;min-height:220px;
                border-top:3px solid #d4a843'>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.3rem;
                    color:#d4a843;letter-spacing:0.05em;margin-bottom:10px'>
            🔍 WATCHLIST SCANNER
        </div>
        <div style='font-family:RedRose,sans-serif;font-size:0.9rem;color:#888;
                    line-height:1.7'>
            Scannt alle <b style='color:#ccc'>225 Aktien</b> in 11 Sektoren nach den besten
            Stillhalter-Optionen — sortiert nach <b style='color:#ccc'>Chance-Risiko-Verhältnis (CRV)</b>.
        </div>
        <ul style='color:#666;font-size:0.85rem;margin-top:12px;line-height:1.8;
                   font-family:RedRose,sans-serif'>
            <li>Cash Covered Puts · Covered Calls</li>
            <li>Multi-Timeframe: RSI · Stochastik · MACD · Stillhalter Trend Model®</li>
            <li>CRV Score · Rendite % Laufzeit · Rendite %/Tag</li>
            <li>Bubble-Chart · CSV-Export</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.page_link("pages/1_Scanner.py", label="→ Zum Watchlist Scanner", icon="🔍")

with c2:
    st.markdown("""
    <div style='background:#111;border:1px solid #1e1e1e;border-radius:14px;
                padding:28px 28px 24px;min-height:220px;
                border-top:3px solid #555'>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.3rem;
                    color:#e0e0e0;letter-spacing:0.05em;margin-bottom:10px'>
            📊 EINZELANALYSE
        </div>
        <div style='font-family:RedRose,sans-serif;font-size:0.9rem;color:#888;
                    line-height:1.7'>
            Tiefenanalyse einer einzelnen Aktie mit vollständigen Options-Details,
            Chart und Fundamentaldaten.
        </div>
        <ul style='color:#666;font-size:0.85rem;margin-top:12px;line-height:1.8;
                   font-family:RedRose,sans-serif'>
            <li>Optionen mit Greeks · CRV · Payoff-Diagramm</li>
            <li>Chart: MACD · Stochastik · Trendkanal · S&R</li>
            <li>KGV · PEG · EPS-Wachstum · Fundamentals</li>
            <li>Earnings-Kalender · Aktuelle News</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<br>", unsafe_allow_html=True)
    st.page_link("pages/2_Analyse.py", label="→ Zur Einzelanalyse", icon="📊")

# ── Top 9 Trading Ideen ───────────────────────────────────────────────────────
st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)
st.markdown("""
<div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.4rem;
            color:#f0f0f0;letter-spacing:0.05em;margin:16px 0 4px 0'>
    🏆 TOP 9 TRADING IDEEN DES TAGES
</div>
<div style='font-family:RedRose,sans-serif;font-size:0.82rem;color:#555;
            text-transform:uppercase;letter-spacing:0.1em;margin-bottom:16px'>
    Risikoklasse A (IV 0–30%) · B (IV 30–60%) · C (IV >60%) · Top 3 pro Klasse nach CRV
</div>
""", unsafe_allow_html=True)

# Cache-Datei laden
CACHE_PATH = os.path.join(os.path.dirname(__file__), "data", "last_scan_cache.pkl")

def load_top9_cache():
    if not os.path.exists(CACHE_PATH):
        return None, None, None
    try:
        with open(CACHE_PATH, "rb") as f:
            data = pickle.load(f)
        return data.get("results"), data.get("timestamp"), data.get("strategy", "Cash Covered Put")
    except Exception:
        return None, None, None

def get_risk_class(iv_pct):
    if iv_pct <= 30:
        return "A"
    elif iv_pct <= 60:
        return "B"
    else:
        return "C"

cached_results, cached_ts, cached_strategy = load_top9_cache()

if cached_results is not None and not cached_results.empty:
    ts_str = cached_ts.strftime("%d.%m.%Y %H:%M") if cached_ts else "unbekannt"
    age_hours = (datetime.now() - cached_ts).total_seconds() / 3600 if cached_ts else 99
    freshness_color = "#22c55e" if age_hours < 4 else ("#f59e0b" if age_hours < 24 else "#ef4444")

    st.markdown(f"""
    <div style='font-size:0.78rem;color:#444;font-family:RedRose,sans-serif;margin-bottom:12px'>
        Letzte Berechnung: <span style='color:{freshness_color}'>{ts_str} Uhr</span>
        · Strategie: <span style='color:#888'>{cached_strategy}</span>
        · Quelle: Letzter Scanner-Lauf
        · <span style='color:#555'>Für aktuellere Daten → Scanner starten</span>
    </div>
    """, unsafe_allow_html=True)

    df = cached_results.copy()

    # Risikoklasse ermitteln
    if "IV %" in df.columns:
        df["_risk_class"] = df["IV %"].apply(get_risk_class)
    else:
        df["_risk_class"] = "B"

    CLASS_CONFIG = {
        "A": {
            "label": "LOW IV — Konservativ",
            "subtitle": "IV 0–30% · Geringes Risiko · Stabile Aktien (z.B. JNJ, MSFT, KO)",
            "color": "#22c55e",
            "border": "#0f3320",
            "bg": "#0a1a0f",
            "icon": "🟢",
        },
        "B": {
            "label": "MID IV — Ausgewogen",
            "subtitle": "IV 30–60% · Mittleres Risiko · Gute Prämien",
            "color": "#d4a843",
            "border": "#3a2f0a",
            "bg": "#1a1508",
            "icon": "🟡",
        },
        "C": {
            "label": "HIGH IV — Aggressiv",
            "subtitle": "IV >60% · Hohes Risiko · Sehr hohe Prämien",
            "color": "#ef4444",
            "border": "#3a1010",
            "bg": "#1a0a0a",
            "icon": "🔴",
        },
    }

    for cls in ["A", "B", "C"]:
        cfg = CLASS_CONFIG[cls]
        cls_df = df[df["_risk_class"] == cls].head(3)

        # st.html() statt st.markdown() — verhindert $-Zeichen als LaTeX-Delimiter (Streamlit 1.31+)
        st.html(f"""
        <div style='background:{cfg["bg"]};border:1px solid {cfg["border"]};
                    border-left:4px solid {cfg["color"]};border-radius:10px;
                    padding:12px 16px;margin-bottom:8px'>
            <span style='font-family:sans-serif;font-weight:700;
                         color:{cfg["color"]};font-size:1rem;letter-spacing:0.06em'>
                {cfg["icon"]} {cfg["label"]}
            </span>
            <span style='font-family:sans-serif;font-size:0.78rem;
                         color:#666;margin-left:12px'>{cfg["subtitle"]}</span>
        </div>
        """)

        if cls_df.empty:
            iv_range = {"A": "0–30%", "B": "30–60%", "C": ">60%"}[cls]
            st.html(f"""
            <div style='background:#0e0e0e;border:1px dashed #222;border-radius:8px;
                        padding:14px 18px;color:#444;font-family:sans-serif;
                        font-size:0.85rem;margin-bottom:16px;line-height:1.6'>
                <b style='color:#555'>Keine Optionen im {cfg["label"]} Bereich (IV {iv_range})</b><br>
                Im letzten Scan wurden keine Optionen mit dieser IV-Range gefunden.
                Tipp: Watchlist-Scanner neu starten oder IV-Filter anpassen.
            </div>
            """)
            continue

        cols = st.columns(3, gap="small")
        for idx, (col, (_, row)) in enumerate(zip(cols, cls_df.iterrows())):
            rank_icon = ["🥇", "🥈", "🥉"][idx]

            # Werte extrahieren
            ticker   = str(row.get("Ticker", ""))
            kurs     = float(row.get("Kurs", 0))
            strike   = float(row.get("Strike", 0))
            verfall  = str(row.get("Verfall", ""))
            dte      = int(row.get("DTE", 0))
            praemie  = float(row.get("Prämie", 0))
            crv      = float(row.get("CRV Score", 0))
            delta    = float(row.get("Delta", 0))
            iv       = float(row.get("IV %", 0))
            otm      = float(row.get("OTM %", 0))

            rend_lz  = float(row.get("Rendite % Laufzeit", praemie / strike * 100 if strike > 0 else 0))
            rend_ann = float(row.get("Rendite ann. %", 0))
            rend_tag = float(row.get("Rendite %/Tag", rend_lz / max(1, dte)))
            tf_align = str(row.get("TF-Align", "–"))
            trend    = str(row.get("Trend", ""))
            sektor   = str(row.get("Sektor", ""))

            trend_arrow = "↑" if "Aufwärts" in trend else ("↓" if "Abwärts" in trend else "→")
            trend_c = "#22c55e" if trend_arrow == "↑" else ("#ef4444" if trend_arrow == "↓" else "#f59e0b")

            # Kurs/Strike als Text ohne $-Zeichen am Anfang → kein LaTeX-Konflikt
            kurs_str   = f"USD {kurs:.2f}"
            strike_str = f"USD {strike:.2f}"

            with col:
                st.html(f"""
                <div style='background:#111;border:1px solid #1e1e1e;border-radius:12px;
                            padding:16px;border-top:2px solid {cfg["color"]};'>
                    <div style='display:flex;justify-content:space-between;align-items:center;
                                margin-bottom:10px'>
                        <span style='font-family:sans-serif;font-weight:700;
                                     font-size:1.3rem;color:#f0f0f0'>{rank_icon} {ticker}</span>
                        <span style='font-family:sans-serif;font-size:0.72rem;
                                     color:#555'>{sektor}</span>
                    </div>

                    <div style='display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px'>
                        <div style='background:#0e0e0e;border-radius:6px;padding:6px 10px'>
                            <div style='font-size:0.68rem;color:#555;text-transform:uppercase;
                                        letter-spacing:0.06em;font-family:sans-serif'>Kurs</div>
                            <div style='font-size:1rem;font-weight:600;color:#e0e0e0;
                                        font-family:sans-serif'>{kurs_str}</div>
                        </div>
                        <div style='background:#0e0e0e;border-radius:6px;padding:6px 10px'>
                            <div style='font-size:0.68rem;color:#555;text-transform:uppercase;
                                        letter-spacing:0.06em;font-family:sans-serif'>Strike</div>
                            <div style='font-size:1rem;font-weight:600;color:#e0e0e0;
                                        font-family:sans-serif'>{strike_str}</div>
                        </div>
                    </div>

                    <div style='background:#0a0f0a;border:1px solid #1a2a1a;border-radius:8px;
                                padding:8px 12px;margin-bottom:8px'>
                        <div style='display:flex;justify-content:space-between;margin-bottom:4px'>
                            <span style='font-size:0.72rem;color:#555;font-family:sans-serif'>
                                Rendite ann.</span>
                            <span style='font-size:0.95rem;font-weight:700;color:#22c55e;
                                         font-family:sans-serif'>{rend_ann:.1f}%</span>
                        </div>
                        <div style='display:flex;justify-content:space-between;margin-bottom:4px'>
                            <span style='font-size:0.72rem;color:#555;font-family:sans-serif'>
                                Rendite LZ ({dte}T)</span>
                            <span style='font-size:0.85rem;font-weight:600;color:#4ade80;
                                         font-family:sans-serif'>{rend_lz:.2f}%</span>
                        </div>
                        <div style='display:flex;justify-content:space-between'>
                            <span style='font-size:0.72rem;color:#555;font-family:sans-serif'>
                                Rendite/Tag</span>
                            <span style='font-size:0.85rem;font-weight:600;color:#86efac;
                                         font-family:sans-serif'>{rend_tag:.3f}%</span>
                        </div>
                    </div>

                    <div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;margin-bottom:8px'>
                        <div style='text-align:center;background:#0e0e0e;border-radius:6px;padding:5px'>
                            <div style='font-size:0.65rem;color:#444;font-family:sans-serif'>CRV</div>
                            <div style='font-size:0.9rem;font-weight:700;color:{cfg["color"]};
                                        font-family:sans-serif'>{crv:.0f}</div>
                        </div>
                        <div style='text-align:center;background:#0e0e0e;border-radius:6px;padding:5px'>
                            <div style='font-size:0.65rem;color:#444;font-family:sans-serif'>TF-Align</div>
                            <div style='font-size:0.9rem;font-weight:700;color:#60a5fa;
                                        font-family:sans-serif'>{tf_align}</div>
                        </div>
                        <div style='text-align:center;background:#0e0e0e;border-radius:6px;padding:5px'>
                            <div style='font-size:0.65rem;color:#444;font-family:sans-serif'>OTM</div>
                            <div style='font-size:0.9rem;font-weight:700;color:#e0e0e0;
                                        font-family:sans-serif'>{otm:.1f}%</div>
                        </div>
                    </div>

                    <div style='display:flex;justify-content:space-between;font-size:0.78rem;
                                color:#444;font-family:sans-serif;margin-top:4px'>
                        <span>&#916; {delta:.3f} · IV {iv:.0f}%</span>
                        <span style='color:{trend_c}'>{trend_arrow} {verfall}</span>
                    </div>
                </div>
                """)

        st.html("<div style='height:12px'></div>")

else:
    # Kein Cache → Hinweis
    st.markdown("""
    <div style='background:#111;border:1px dashed #222;border-radius:12px;
                padding:32px;text-align:center'>
        <div style='font-size:2.5rem;margin-bottom:12px'>🏆</div>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.1rem;
                    color:#555;letter-spacing:0.05em;margin-bottom:8px'>
            Noch kein Scan vorhanden
        </div>
        <div style='font-family:RedRose,sans-serif;font-size:0.88rem;color:#333;
                    line-height:1.7'>
            Die Top 9 werden automatisch aus dem letzten Scanner-Lauf befüllt.<br>
            Führe zuerst einen Watchlist-Scan durch → die Top 9 erscheinen hier automatisch.
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_btn, _ = st.columns([2, 8])
    with col_btn:
        st.page_link("pages/1_Scanner.py", label="→ Zum Watchlist Scanner", icon="🔍")

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style='text-align:center;font-family:RedRose,sans-serif;font-size:0.78rem;color:#333;
            letter-spacing:0.08em'>
    STILLHALTER COMMUNITY · Daten: Yahoo Finance ·
    Indikatoren: Black-Scholes · MACD (12,26,9) · Stochastik (14,3,3) · Stillhalter Trend Model® · RSI (14)
</div>
""", unsafe_allow_html=True)
