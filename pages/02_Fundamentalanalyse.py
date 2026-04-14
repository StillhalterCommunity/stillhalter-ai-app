from __future__ import annotations
"""
Stillhalter AI App — Value Aktien Scanner
Bewertet die Watchlist nach Qualität als Value-Aktie für Stillhalter-Strategien.
Datenquelle: Yahoo Finance via yfinance
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

st.set_page_config(
    page_title="Fundamentalanalyse · Stillhalter AI App",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

from data.watchlist import WATCHLIST, SECTOR_ICONS, ALL_TICKERS, get_sector_for_ticker
import yfinance as yf


# ── Value Score Berechnung ─────────────────────────────────────────────────────

import math

def _to_float(val) -> float | None:
    """Konvertiert Yahoo Finance Werte sicher zu float. Filtert NaN, inf, Strings."""
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _score_peg(peg) -> float:
    """PEG Ratio → Score 0–100. PEG < 1 = top."""
    if peg is None or peg <= 0:
        return 40.0   # Neutral wenn nicht verfügbar
    if peg <= 0.5:   return 100.0
    if peg <= 0.8:   return 90.0
    if peg <= 1.0:   return 78.0
    if peg <= 1.5:   return 60.0
    if peg <= 2.0:   return 40.0
    if peg <= 3.0:   return 20.0
    return 5.0

def _score_forward_pe(fpe) -> float:
    """Forward P/E → Score 0–100. Niedrig = besser."""
    if fpe is None or fpe <= 0:
        return 40.0
    if fpe <= 10:    return 100.0
    if fpe <= 15:    return 85.0
    if fpe <= 20:    return 70.0
    if fpe <= 25:    return 55.0
    if fpe <= 30:    return 40.0
    if fpe <= 40:    return 25.0
    return 10.0

def _score_growth(growth_pct) -> float:
    """Earnings Growth (%) → Score 0–100. Hoch = besser."""
    if growth_pct is None:
        return 40.0
    if growth_pct >= 30:  return 100.0
    if growth_pct >= 20:  return 88.0
    if growth_pct >= 15:  return 75.0
    if growth_pct >= 10:  return 62.0
    if growth_pct >= 5:   return 50.0
    if growth_pct >= 0:   return 35.0
    return 15.0   # Negatives Wachstum

def _score_roe(roe_pct) -> float:
    """Return on Equity → Score 0–100."""
    if roe_pct is None:
        return 40.0
    if roe_pct >= 25:  return 100.0
    if roe_pct >= 20:  return 85.0
    if roe_pct >= 15:  return 70.0
    if roe_pct >= 10:  return 55.0
    if roe_pct >= 5:   return 40.0
    if roe_pct >= 0:   return 25.0
    return 10.0

def _score_debt(de_ratio) -> float:
    """Debt/Equity → Score 0–100. Niedrig = gesünder."""
    if de_ratio is None:
        return 50.0
    if de_ratio <= 0.1:   return 100.0
    if de_ratio <= 0.3:   return 85.0
    if de_ratio <= 0.5:   return 70.0
    if de_ratio <= 1.0:   return 55.0
    if de_ratio <= 2.0:   return 35.0
    if de_ratio <= 3.0:   return 20.0
    return 5.0

def _score_analyst(rec_mean) -> float:
    """
    Analyst Mean Recommendation: 1.0=Strong Buy … 5.0=Strong Sell.
    → Score 0–100.
    """
    if rec_mean is None:
        return 50.0
    # Invertieren: 1 = 100, 3 = 50, 5 = 0
    return max(0, min(100, (5.0 - rec_mean) / 4.0 * 100))

def _score_margin(op_margin_pct) -> float:
    """Operating Margin → Score 0–100."""
    if op_margin_pct is None:
        return 40.0
    if op_margin_pct >= 30:  return 100.0
    if op_margin_pct >= 20:  return 85.0
    if op_margin_pct >= 15:  return 70.0
    if op_margin_pct >= 10:  return 55.0
    if op_margin_pct >= 5:   return 40.0
    if op_margin_pct >= 0:   return 25.0
    return 10.0


def calculate_value_score(info: dict) -> dict:
    """
    Berechnet einen gewichteten Value-Score (0–100) aus Fundamental-Daten.

    Gewichtung:
      PEG Ratio         30%  — Kern-Kennzahl: Wachstum vs. Bewertung
      Earnings Growth   25%  — Erwartetes Gewinnwachstum
      Forward P/E       20%  — Aktuelle Bewertung
      Return on Equity  10%  — Kapitalrendite (Qualität)
      Analyst Konsensus 10%  — Marktmeinung
      Debt/Equity        5%  — Finanzielle Gesundheit

    Risikoklasse:
      A: Score ≥ 75  — hohe Qualität, stabile Basis
      B: Score 55–74 — solide, akzeptabel
      C: Score < 55  — spekulativer
    """
    pe_trail   = _to_float(info.get("trailingPE"))
    pe_fwd     = _to_float(info.get("forwardPE"))
    peg        = _to_float(info.get("pegRatio"))
    eg_yoy     = _to_float(info.get("earningsGrowth"))          # yoy annualisiert (dezimal)
    eg_qrt     = _to_float(info.get("earningsQuarterlyGrowth"))  # quarterly yoy (dezimal)
    rev_growth = _to_float(info.get("revenueGrowth"))
    roe        = _to_float(info.get("returnOnEquity"))
    de_ratio   = _to_float(info.get("debtToEquity"))
    fcf        = _to_float(info.get("freeCashflow"))
    op_margin  = _to_float(info.get("operatingMargins"))
    rec_mean   = _to_float(info.get("recommendationMean"))
    target     = _to_float(info.get("targetMeanPrice"))
    price      = _to_float(info.get("currentPrice")) or _to_float(info.get("regularMarketPrice"))
    mktcap     = info.get("marketCap")
    # EPS-basiertes Wachstum als weiterer Fallback
    eps_curr   = _to_float(info.get("epsCurrentYear")) or _to_float(info.get("trailingEps"))
    eps_fwd    = _to_float(info.get("epsForward"))

    # ── Earnings Growth ─────────────────────────────────────────────────────
    # Priorität: earningsGrowth (annualisiert) → quarterly → EPS-Vergleich
    eg_use = None
    if eg_yoy is not None:
        eg_use = eg_yoy * 100
    elif eg_qrt is not None:
        eg_use = eg_qrt * 100
    elif eps_curr and eps_fwd and eps_curr != 0:
        # Forward EPS vs. trailing EPS als Proxy
        eg_use = (eps_fwd - eps_curr) / abs(eps_curr) * 100

    # ── PEG berechnen wenn nicht direkt verfügbar ───────────────────────────
    # PEG = ForwardPE / EarningsGrowth%
    # Nur sinnvoll bei positivem Wachstum
    if peg is None and pe_fwd and pe_fwd > 0 and eg_use and eg_use > 0:
        peg = pe_fwd / eg_use

    # Upside Potential
    upside_pct = None
    if target and price and price > 0:
        upside_pct = (target - price) / price * 100

    # Scores berechnen
    s_peg    = _score_peg(peg)
    s_fpe    = _score_forward_pe(pe_fwd)
    s_growth = _score_growth(eg_use)
    s_roe    = _score_roe(roe * 100 if roe else None)
    s_debt   = _score_debt(de_ratio / 100 if de_ratio else None)
    s_analyst = _score_analyst(rec_mean)

    # Gewichteter Gesamt-Score
    total = (
        s_peg    * 0.30 +
        s_growth * 0.25 +
        s_fpe    * 0.20 +
        s_roe    * 0.10 +
        s_analyst * 0.10 +
        s_debt   * 0.05
    )
    total = round(total, 1)

    # Risikoklasse (A/B/C) — analog zu IV-Klassen im Options-Scanner
    if total >= 75:
        grade = "A"
        grade_label = "A — Top Quality"
        grade_color = "#22c55e"
    elif total >= 55:
        grade = "B"
        grade_label = "B — Solide"
        grade_color = "#f59e0b"
    else:
        grade = "C"
        grade_label = "C — Spekulativ"
        grade_color = "#ef4444"

    # PEG Bewertungsampel
    if peg and 0 < peg <= 1.0:
        peg_label = f"✅ {peg:.2f} (günstig)"
    elif peg and peg <= 2.0:
        peg_label = f"🟡 {peg:.2f} (fair)"
    elif peg:
        peg_label = f"🔴 {peg:.2f} (teuer)"
    else:
        peg_label = "–"

    # FCF positiv?
    fcf_label = "✅ positiv" if fcf and fcf > 0 else ("❌ negativ" if fcf and fcf < 0 else "–")

    return {
        "value_score":   total,
        "grade":         grade,
        "grade_label":   grade_label,
        "grade_color":   grade_color,
        "score_peg":     round(s_peg, 1),
        "score_growth":  round(s_growth, 1),
        "score_fpe":     round(s_fpe, 1),
        "score_roe":     round(s_roe, 1),
        "score_analyst": round(s_analyst, 1),
        "score_debt":    round(s_debt, 1),
        # Rohwerte
        "pe_trailing":   round(pe_trail, 1) if pe_trail else None,
        "pe_forward":    round(pe_fwd, 1)   if pe_fwd   else None,
        "peg_ratio":     round(peg, 2)       if peg      else None,
        "peg_label":     peg_label,
        "earnings_growth_pct": round(eg_use, 1) if eg_use else None,
        "revenue_growth_pct":  round(rev_growth * 100, 1) if rev_growth else None,
        "roe_pct":       round(roe * 100, 1) if roe else None,
        "de_ratio":      round(de_ratio / 100, 2) if de_ratio else None,
        "op_margin_pct": round(op_margin * 100, 1) if op_margin else None,
        "fcf_label":     fcf_label,
        "analyst_rec":   round(rec_mean, 2)  if rec_mean else None,
        "analyst_target": round(target, 2)   if target   else None,
        "upside_pct":    round(upside_pct, 1) if upside_pct else None,
        "mktcap":        mktcap,
        "price":         price,
    }


@st.cache_data(ttl=7200, show_spinner=False)
def fetch_value_data(ticker: str) -> dict:
    """Holt Fundamental-Daten via yfinance und berechnet Value Score."""
    try:
        stock = yf.Ticker(ticker)
        info  = stock.info
        if not info or "symbol" not in info:
            return {"error": "Keine Daten"}
        result = calculate_value_score(info)
        result["name"]      = info.get("shortName") or info.get("longName") or ticker
        result["sector_yf"] = info.get("sector", "")
        result["industry"]  = info.get("industry", "")
        result["ticker"]    = ticker

        # ── Historische Volatilität (HV30) als IV-Proxy ─────────────────────
        # Annualisierte 30-Tage-Standardabweichung der Log-Returns
        try:
            hist = stock.history(period="2mo", auto_adjust=True)
            if len(hist) >= 20:
                log_ret = np.log(hist["Close"] / hist["Close"].shift(1)).dropna()
                hv30 = float(log_ret.tail(30).std() * np.sqrt(252) * 100)
                result["iv_pct"] = round(hv30, 1)
                if hv30 < 30:
                    result["iv_class"] = "Low IV"
                    result["iv_color"] = "#22c55e"
                elif hv30 < 60:
                    result["iv_class"] = "Mid IV"
                    result["iv_color"] = "#f59e0b"
                else:
                    result["iv_class"] = "High IV"
                    result["iv_color"] = "#ef4444"
            else:
                result["iv_pct"]   = None
                result["iv_class"] = "–"
                result["iv_color"] = "#555"
        except Exception:
            result["iv_pct"]   = None
            result["iv_class"] = "–"
            result["iv_color"] = "#555"

        return result
    except Exception as e:
        return {"error": str(e), "ticker": ticker}


def _rec_text(rec_mean) -> str:
    if rec_mean is None: return "–"
    if rec_mean <= 1.5:  return "🟢 Strong Buy"
    if rec_mean <= 2.2:  return "🟢 Buy"
    if rec_mean <= 2.8:  return "🟡 Hold"
    if rec_mean <= 3.5:  return "🟠 Underperform"
    return "🔴 Sell"


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
                    color:#f0f0f0;letter-spacing:0.04em'>FUNDAMENTALANALYSE</div>
        <div style='font-family:RedRose,sans-serif;font-weight:300;font-size:0.8rem;
                    color:#666;text-transform:uppercase;letter-spacing:0.12em;margin-top:2px'>
            Watchlist · Fundamentalanalyse · Value-Qualität · PEG Ratio
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)
st.markdown("""
<div style='font-family:RedRose,sans-serif;font-size:0.85rem;color:#555;
            line-height:1.7;margin:10px 0 16px'>
    Bewertet alle Aktien deiner Watchlist nach ihrer Qualität als <b style='color:#d4a843'>Value-Aktie</b> für
    Stillhalter-Strategien. Ziel: <b>hohes Gewinnwachstum bei fairer Bewertung</b> (niedriges PEG Ratio).
    Daten via Yahoo Finance.
</div>
""", unsafe_allow_html=True)

# ── Scan-Einstellungen ─────────────────────────────────────────────────────────
with st.expander("⚙️ **SCAN-EINSTELLUNGEN**", expanded=True):
    s1, s2, s3, s4, s5, s6 = st.columns(6)
    with s1:
        scan_sector = st.selectbox("Sektor",
            ["🌐 Alle Sektoren"] + list(WATCHLIST.keys()), key="vs_sector")
    with s2:
        min_score = st.number_input("Mind. Value Score", 0, 100, 0, 5,
            help="Filtert Aktien nach Mindest-Score (0–100)")
    with s3:
        grade_filter = st.multiselect("Qualitätsklasse",
            ["A — Top Quality", "B — Solide", "C — Spekulativ"],
            default=[], placeholder="Alle",
            help="A ≥ 75 · B 55–74 · C < 55")
    with s4:
        iv_class_filter = st.multiselect("IV-Klasse",
            ["Low IV", "Mid IV", "High IV"],
            default=[], placeholder="Alle",
            help="Low IV < 30% · Mid IV 30–60% · High IV > 60% (Volatilität = Prämien-Potenzial)")
    with s5:
        max_peg = st.number_input("Max. PEG Ratio", 0.0, 10.0, 0.0, 0.5, format="%.1f",
            help="0 = kein Filter. PEG < 1 = günstig bewertet relativ zum Wachstum")
    with s6:
        min_growth = st.number_input("Mind. Earnings Growth %", -50, 100, 0, 5,
            help="Mindest-Gewinnwachstum (YoY)")

sv1, sv2, _ = st.columns([2, 2, 8])
with sv1:
    scan_tickers = ALL_TICKERS if "Alle" in scan_sector else WATCHLIST.get(scan_sector, [])
    start_scan   = st.button(f"💎 Value-Scan starten ({len(scan_tickers)} Aktien)",
                             type="primary", use_container_width=True)
with sv2:
    if st.button("🗑️ Cache leeren", use_container_width=True):
        st.cache_data.clear()
        for k in ["vs_results"]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

if "vs_results" not in st.session_state:
    st.session_state.vs_results = None

# ── Scan ausführen ─────────────────────────────────────────────────────────────
if start_scan:
    progress_bar = st.progress(0.0)
    status_ph    = st.empty()
    live_ph      = st.empty()
    all_rows     = []
    total        = len(scan_tickers)

    def _fetch_one(ticker):
        data = fetch_value_data(ticker)
        time.sleep(0.05)
        return ticker, data

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_fetch_one, t): t for t in scan_tickers}
        done = 0
        for future in as_completed(futures):
            ticker = futures[future]
            done  += 1
            try:
                _, data = future.result(timeout=20)
                if "error" not in data:
                    sector = get_sector_for_ticker(ticker)
                    sector_short = sector.split(".", 1)[-1].strip().split("(")[0].strip() \
                                   if "." in sector else sector
                    all_rows.append({
                        "Ticker":         ticker,
                        "Name":           data.get("name", ticker),
                        "Sektor":         sector_short,
                        "⭐ Value Score": data["value_score"],
                        "Klasse":         data["grade_label"],
                        "IV %":           data.get("iv_pct"),
                        "IV Klasse":      data.get("iv_class", "–"),
                        "PEG":            data["peg_label"],
                        "KGV aktuell":    data["pe_trailing"],
                        "KGV erwartet":   data["pe_forward"],
                        "EPS Wachstum %": data["earnings_growth_pct"],
                        "Umsatz-Wachs. %":data["revenue_growth_pct"],
                        "ROE %":          data["roe_pct"],
                        "Op. Marge %":    data["op_margin_pct"],
                        "Schulden/EK":    data["de_ratio"],
                        "FCF":            data["fcf_label"],
                        "Analyst":        _rec_text(data.get("analyst_rec")),
                        "Kursziel ∅":     data["analyst_target"],
                        "Upside %":       data["upside_pct"],
                        "Kurs":           data["price"],
                        # Rohwerte für Filter
                        "_peg_raw":       data["peg_ratio"],
                        "_grade":         data["grade"],
                        "_iv_class":      data.get("iv_class", "–"),
                        "_iv_pct":        data.get("iv_pct"),
                        "_growth_raw":    data["earnings_growth_pct"],
                        "_pe_fwd_raw":    data["pe_forward"],
                        "_pe_trail_raw":  data["pe_trailing"],
                    })
            except Exception:
                pass

            # Fortschritt
            pct = done / total
            progress_bar.progress(pct)
            status_ph.markdown(
                f"**Analysiere:** `{ticker}` ({done}/{total}) · "
                f"**{len(all_rows)} Aktien** bewertet"
            )

            # Live-Vorschau alle 10 Ticker
            if all_rows and done % 10 == 0:
                preview = pd.DataFrame(all_rows).sort_values("⭐ Value Score", ascending=False)
                live_ph.dataframe(
                    preview[["Ticker","Name","Sektor","⭐ Value Score","Klasse","PEG",
                              "KGV erwartet","EPS Wachstum %"]].head(20),
                    use_container_width=True, hide_index=True, height=280,
                )

    progress_bar.progress(1.0)
    live_ph.empty()

    if all_rows:
        df = pd.DataFrame(all_rows)
        df = df.sort_values("⭐ Value Score", ascending=False).reset_index(drop=True)
        df.insert(0, "Rang", range(1, len(df) + 1))
        st.session_state.vs_results = df
        status_ph.markdown(f"✅ **Value-Scan abgeschlossen** — **{len(df)} Aktien** analysiert")
    else:
        status_ph.error("Keine Daten empfangen — Yahoo Finance Verbindung prüfen.")

# ── Ergebnisse anzeigen ────────────────────────────────────────────────────────
df = st.session_state.vs_results

if df is None:
    st.markdown("""
    <div style='text-align:center;padding:4rem 2rem;color:#333'>
        <div style='font-size:3rem'>💎</div>
        <div style='font-family:RedRose,sans-serif;font-size:1.1rem;margin-top:1rem;color:#555'>
            Scan starten um die Watchlist zu bewerten
        </div>
    </div>
    """, unsafe_allow_html=True)

elif df.empty:
    st.warning("Keine Aktien mit diesen Filterkriterien gefunden.")

else:
    # ── Post-Filter anwenden ───────────────────────────────────────────────
    view = df.copy()
    if min_score > 0:
        view = view[view["⭐ Value Score"] >= min_score]
    if grade_filter:
        view = view[view["Klasse"].isin(grade_filter)]
    if iv_class_filter:
        view = view[view["_iv_class"].isin(iv_class_filter)]
    if max_peg > 0:
        # Nur gültige (positive) PEG-Werte <= max_peg behalten
        # Negative PEG-Werte (ungültig, z.B. neg. Wachstum) werden ausgeschlossen
        # Tickers ohne PEG-Daten werden BEHALTEN (nicht bestraft)
        peg_col = pd.to_numeric(view["_peg_raw"], errors="coerce")
        view = view[peg_col.isna() | ((peg_col > 0) & (peg_col <= max_peg))]
    if min_growth != 0:
        # Wachstums-Filter: Tickers ohne Daten behalten
        growth_col = pd.to_numeric(view["_growth_raw"], errors="coerce")
        view = view[growth_col.isna() | (growth_col >= min_growth)]

    # ── KPI-Kacheln ───────────────────────────────────────────────────────
    n_a    = len(df[df["_grade"] == "A"])
    n_b    = len(df[df["_grade"] == "B"])
    n_c    = len(df[df["_grade"] == "C"])
    n_low  = len(df[df["_iv_class"] == "Low IV"])  if "_iv_class" in df.columns else 0
    n_mid  = len(df[df["_iv_class"] == "Mid IV"])  if "_iv_class" in df.columns else 0
    n_high = len(df[df["_iv_class"] == "High IV"]) if "_iv_class" in df.columns else 0
    avg_sc = df["⭐ Value Score"].mean()
    peg_valids = df["_peg_raw"].dropna()
    peg_u1 = len(peg_valids[peg_valids <= 1.0])

    km = st.columns(7)
    km[0].metric("Aktien analysiert",  len(df))
    km[1].metric("Klasse A (Top)",     n_a, help="Value Score ≥ 75")
    km[2].metric("Klasse B (Solide)",  n_b, help="Value Score 55–74")
    km[3].metric("Klasse C (Spekul.)", n_c, help="Value Score < 55")
    km[4].metric("Ø Value Score",      f"{avg_sc:.1f}")
    km[5].metric("PEG < 1 (günstig)",  peg_u1, help="Anzahl Aktien mit PEG < 1.0")
    km[6].metric("🟢 Low / 🟡 Mid / 🔴 High IV",
                 f"{n_low} / {n_mid} / {n_high}",
                 help="IV-Klassen (HV30): Low<30% · Mid 30–60% · High>60%")

    # IV-Klassen Banner (wie auf Startseite)
    st.html(f"""
    <div style='display:flex;gap:8px;margin:10px 0 4px 0'>
        <div style='background:#0a1a0f;border-left:3px solid #22c55e;border-radius:6px;
                    padding:5px 14px;font-family:sans-serif;font-size:0.8rem'>
            🟢 <b style='color:#22c55e'>Low IV</b>
            <span style='color:#555;margin-left:4px'>&lt;30% · Konservativ · {n_low} Aktien</span>
        </div>
        <div style='background:#1a1508;border-left:3px solid #f59e0b;border-radius:6px;
                    padding:5px 14px;font-family:sans-serif;font-size:0.8rem'>
            🟡 <b style='color:#f59e0b'>Mid IV</b>
            <span style='color:#555;margin-left:4px'>30–60% · Ausgewogen · {n_mid} Aktien</span>
        </div>
        <div style='background:#1a0a0a;border-left:3px solid #ef4444;border-radius:6px;
                    padding:5px 14px;font-family:sans-serif;font-size:0.8rem'>
            🔴 <b style='color:#ef4444'>High IV</b>
            <span style='color:#555;margin-left:4px'>&gt;60% · Aggressiv · {n_high} Aktien</span>
        </div>
        <div style='background:#111;border-left:3px solid #555;border-radius:6px;
                    padding:5px 14px;font-family:sans-serif;font-size:0.75rem;color:#444'>
            IV = 30-Tage hist. Volatilität (HV30) · Annualisiert · Proxy für Options-IV
        </div>
    </div>
    """)

    st.markdown('<div style="height:8px"></div>', unsafe_allow_html=True)

    # ── Info-Box: Was bedeutet der Value Score ─────────────────────────────
    with st.expander("ℹ️ **Was bedeutet der Value Score?**", expanded=False):
        ic1, ic2 = st.columns(2)
        with ic1:
            st.markdown("""
            **📐 Value Score Formel (gewichtet)**

            | Kennzahl | Gewicht | Bedeutung |
            |----------|---------|-----------|
            | **PEG Ratio** | 30% | P/E ÷ Wachstum — Kern-Kennzahl |
            | **Earnings Growth** | 25% | Erwartetes Gewinnwachstum |
            | **Forward P/E** | 20% | Aktuelle Bewertung |
            | **Return on Equity** | 10% | Kapitalrendite |
            | **Analyst Konsensus** | 10% | Buy/Hold/Sell Empfehlung |
            | **Debt/Equity** | 5% | Finanzielle Solidität |

            **Score 0–100** → höher = bessere Value-Qualität
            """)
        with ic2:
            st.markdown("""
            **💎 PEG Ratio erklärt**

            ```
            PEG = KGV (P/E) ÷ Earnings Growth %
            ```

            | PEG | Bewertung |
            |-----|-----------|
            | **< 0.5** | ✅✅ Stark unterbewertet |
            | **0.5 – 1.0** | ✅ Günstig bewertet |
            | **1.0 – 2.0** | 🟡 Fair bewertet |
            | **> 2.0** | 🔴 Teuer bewertet |
            | **> 3.0** | 🔴🔴 Stark überbewertet |

            → Ideal für Stillhalter: **PEG ≤ 1.0 + hohe Prämien** aus IV
            """)

    # ── Charts ────────────────────────────────────────────────────────────
    tab_table, tab_scatter, tab_bar = st.tabs([
        "📋 Tabelle", "📊 KGV vs. Wachstum", "🏆 Value Score Ranking"
    ])

    with tab_table:
        # Farbkodierung
        def _color_score(val):
            try:
                v = float(val)
                if v >= 75: return "color:#22c55e;font-weight:600"
                if v >= 55: return "color:#f59e0b;font-weight:600"
                return "color:#ef4444"
            except Exception:
                return ""

        def _color_grade(val):
            if "A" in str(val): return "color:#22c55e;font-weight:600"
            if "B" in str(val): return "color:#f59e0b"
            if "C" in str(val): return "color:#ef4444"
            return ""

        def _color_peg(val):
            if "✅" in str(val): return "color:#22c55e"
            if "🟡" in str(val): return "color:#f59e0b"
            if "🔴" in str(val): return "color:#ef4444"
            return ""

        def _color_upside(val):
            try:
                v = float(val)
                return "color:#22c55e" if v > 10 else ("color:#ef4444" if v < 0 else "")
            except Exception:
                return ""

        show_cols = [c for c in [
            "Rang", "Ticker", "Name", "Sektor",
            "⭐ Value Score", "Klasse", "IV %", "IV Klasse",
            "PEG", "KGV aktuell", "KGV erwartet",
            "EPS Wachstum %", "Umsatz-Wachs. %",
            "ROE %", "Op. Marge %", "Schulden/EK",
            "FCF", "Analyst", "Kursziel ∅", "Upside %", "Kurs"
        ] if c in view.columns]

        # Max-Wert-Highlighting
        max_vals = {}
        for col in ["⭐ Value Score", "EPS Wachstum %", "ROE %", "Upside %"]:
            if col in view.columns and view[col].notna().any():
                max_vals[col] = view[col].max()

        def highlight_row(row):
            styles = [""] * len(row)
            for i, col in enumerate(row.index):
                if col == "⭐ Value Score":
                    v = row[col]
                    if v == max_vals.get(col): styles[i] = "background-color:rgba(34,197,94,0.15)"
                    elif v >= 75: styles[i] = "color:#22c55e;font-weight:600"
                    elif v >= 55: styles[i] = "color:#f59e0b"
                    else: styles[i] = "color:#ef4444"
                elif col == "Klasse":
                    if "A" in str(row[col]): styles[i] = "color:#22c55e;font-weight:600"
                    elif "B" in str(row[col]): styles[i] = "color:#f59e0b"
                    else: styles[i] = "color:#ef4444"
                elif col == "IV Klasse":
                    v = str(row[col])
                    if "Low" in v:  styles[i] = "color:#22c55e"
                    elif "Mid" in v: styles[i] = "color:#f59e0b"
                    elif "High" in v: styles[i] = "color:#ef4444"
                elif col == "PEG":
                    if "✅" in str(row[col]): styles[i] = "color:#22c55e"
                    elif "🟡" in str(row[col]): styles[i] = "color:#f59e0b"
                    elif "🔴" in str(row[col]): styles[i] = "color:#ef4444"
                elif col == "Upside %" and pd.notna(row.get("Upside %")):
                    styles[i] = "color:#22c55e" if float(row[col]) > 10 else \
                                 ("color:#ef4444" if float(row[col]) < 0 else "")
                elif col == "EPS Wachstum %" and pd.notna(row.get("EPS Wachstum %")):
                    if row[col] == max_vals.get("EPS Wachstum %"):
                        styles[i] = "background-color:rgba(212,168,67,0.12)"
            return styles

        disp_view = view[show_cols].copy()
        styled = disp_view.style.apply(highlight_row, axis=1)

        st.dataframe(
            styled, use_container_width=True, hide_index=True, height=580,
            column_config={
                "Rang":            st.column_config.NumberColumn("Rang", width="small"),
                "Ticker":          st.column_config.TextColumn("Ticker", width="small"),
                "Name":            st.column_config.TextColumn("Unternehmen"),
                "⭐ Value Score":  st.column_config.ProgressColumn(
                                       "⭐ Score", min_value=0, max_value=100, format="%.1f"),
                "IV %":            st.column_config.NumberColumn("IV %", format="%.1f%%",
                                       help="30-Tage Hist. Volatilität (HV30), annualisiert"),
                "IV Klasse":       st.column_config.TextColumn("IV Klasse",
                                       help="Low<30% · Mid 30–60% · High>60%"),
                "KGV aktuell":     st.column_config.NumberColumn("KGV", format="%.1fx"),
                "KGV erwartet":    st.column_config.NumberColumn("KGV (fwd)", format="%.1fx"),
                "EPS Wachstum %":  st.column_config.NumberColumn("EPS Wachs. %", format="%.1f%%"),
                "Umsatz-Wachs. %": st.column_config.NumberColumn("Umsatz Wachs. %", format="%.1f%%"),
                "ROE %":           st.column_config.NumberColumn("ROE %", format="%.1f%%"),
                "Op. Marge %":     st.column_config.NumberColumn("Op. Marge", format="%.1f%%"),
                "Schulden/EK":     st.column_config.NumberColumn("D/E", format="%.2f"),
                "Kursziel ∅":      st.column_config.NumberColumn("Kursziel ∅", format="$%.2f"),
                "Upside %":        st.column_config.NumberColumn("Upside %", format="%.1f%%"),
                "Kurs":            st.column_config.NumberColumn("Kurs", format="$%.2f"),
            },
        )

        # CSV Export
        ex1, _ = st.columns([2, 10])
        with ex1:
            st.download_button(
                "📥 Exportieren (CSV)",
                view[show_cols].to_csv(index=False),
                f"value_scanner_{pd.Timestamp.now().strftime('%Y%m%d')}.csv",
                "text/csv", use_container_width=True,
            )

    with tab_scatter:
        # ── KGV vs. Wachstum Bubble-Chart ─────────────────────────────────
        # Achsen-Auswahl via Schalter
        sc_ctrl1, sc_ctrl2, sc_ctrl3, _ = st.columns([2, 2, 2, 6])
        with sc_ctrl1:
            x_mode = st.radio("X-Achse (KGV)", ["Erwartet (fwd)", "Aktuell (trailing)"],
                              index=0, key="scatter_x", horizontal=False)
        with sc_ctrl2:
            y_mode = st.radio("Y-Achse (Wachstum)", ["EPS Wachstum %", "Umsatz-Wachs. %"],
                              index=0, key="scatter_y", horizontal=False)
        with sc_ctrl3:
            color_mode = st.radio("Farbe nach", ["IV-Klasse", "Value-Klasse"],
                                  index=0, key="scatter_color", horizontal=False)

        x_col = "_pe_fwd_raw" if "Erwartet" in x_mode else "_pe_trail_raw"
        y_col = "_growth_raw" if "EPS" in y_mode else "Umsatz-Wachs. %"
        x_label = "KGV erwartet (Forward P/E)" if "Erwartet" in x_mode else "KGV aktuell (Trailing P/E)"
        y_label = "EPS Wachstum % (YoY)" if "EPS" in y_mode else "Umsatz-Wachstum % (YoY)"

        scatter_df = view.dropna(subset=[x_col, y_col]).copy()
        scatter_df = scatter_df[
            (scatter_df[x_col] > 0) & (scatter_df[x_col] < 80) &
            (scatter_df[y_col].abs() < 150)
        ]

        if scatter_df.empty:
            st.info("Zu wenig Daten für den Chart — KGV und Wachstum müssen verfügbar sein.")
        else:
            # Farb-Mapping
            if color_mode == "IV-Klasse":
                color_map = {"Low IV": "#22c55e", "Mid IV": "#f59e0b", "High IV": "#ef4444"}
                group_col = "_iv_class"
                group_labels = {"Low IV": "🟢 Low IV (<30%)",
                                 "Mid IV": "🟡 Mid IV (30–60%)",
                                 "High IV": "🔴 High IV (>60%)"}
            else:
                color_map = {"A": "#22c55e", "B": "#f59e0b", "C": "#ef4444"}
                group_col = "_grade"
                group_labels = {"A": "💎 Klasse A (≥75)", "B": "🥇 Klasse B (55–74)", "C": "🎯 Klasse C (<55)"}

            fig_sc = go.Figure()

            # ── PEG-Referenz-Diagonalen zeichnen ──────────────────────────
            # PEG = KGV / Wachstum → Wachstum = KGV / PEG
            # Auf X-Achse = KGV, Y-Achse = Wachstum:
            #   PEG=0.5 → y = x / 0.5 = 2x  (grüne Zone: Wachstum >> KGV)
            #   PEG=1.0 → y = x              (faire Bewertung: Diagonale)
            #   PEG=2.0 → y = x / 2          (orange Zone)
            x_range_ref = list(range(0, 85, 5))
            for peg_ref, dash, color_ref, label_ref in [
                (0.5, "dot",  "rgba(34,197,94,0.35)",  "PEG=0.5 ✅✅"),
                (1.0, "dash", "rgba(212,168,67,0.6)",  "PEG=1.0 (fair)"),
                (2.0, "dot",  "rgba(239,68,68,0.35)",  "PEG=2.0"),
            ]:
                y_ref = [x / peg_ref for x in x_range_ref]
                fig_sc.add_trace(go.Scatter(
                    x=x_range_ref, y=y_ref,
                    mode="lines",
                    name=label_ref,
                    line=dict(dash=dash, color=color_ref, width=1.5),
                    hoverinfo="skip",
                    showlegend=True,
                ))

            # Zone-Hintergrund: Grün links der PEG=1 Linie (unterbewertet)
            fig_sc.add_trace(go.Scatter(
                x=[0, 80, 80, 0], y=[0, 0, 80/0.5, 0],
                fill="toself",
                fillcolor="rgba(34,197,94,0.04)",
                line=dict(width=0),
                name="Günstige Zone (PEG<0.5)",
                hoverinfo="skip",
                showlegend=False,
            ))

            # ── Datenpunkte je Gruppe ──────────────────────────────────────
            for group_key, color in color_map.items():
                sub = scatter_df[scatter_df[group_col] == group_key]
                if sub.empty:
                    continue

                # PEG berechnen für Hover
                peg_hover = (sub[x_col] / sub[y_col].replace(0, float("nan"))).round(2)

                fig_sc.add_trace(go.Scatter(
                    x=sub[x_col],
                    y=sub[y_col],
                    mode="markers+text",
                    name=group_labels.get(group_key, group_key),
                    marker=dict(
                        color=color,
                        size=sub["⭐ Value Score"] / 7 + 8,
                        opacity=0.85,
                        line=dict(color="#000", width=0.8),
                    ),
                    text=sub["Ticker"],
                    textposition="top center",
                    textfont=dict(size=8, color="#aaa"),
                    customdata=np.stack([
                        sub["⭐ Value Score"],
                        sub["Klasse"],
                        sub["_iv_class"] if "_iv_class" in sub.columns else ["–"] * len(sub),
                        peg_hover.fillna(0),
                        sub["_peg_raw"].fillna(0),
                    ], axis=-1),
                    hovertemplate=(
                        "<b>%{text}</b><br>"
                        f"{x_label}: %{{x:.1f}}x<br>"
                        f"{y_label}: %{{y:.1f}}%<br>"
                        "PEG (berechnet): %{customdata[3]:.2f}<br>"
                        "PEG (Yahoo): %{customdata[4]:.2f}<br>"
                        "Value Score: %{customdata[0]:.1f}<br>"
                        "Value-Klasse: %{customdata[1]}<br>"
                        "IV-Klasse: %{customdata[2]}"
                        "<extra></extra>"
                    ),
                ))

            fig_sc.update_layout(
                height=540,
                paper_bgcolor="#0c0c0c", plot_bgcolor="#0c0c0c",
                font=dict(color="#888", family="RedRose, sans-serif", size=11),
                xaxis=dict(
                    title=dict(text=x_label, font=dict(color="#888")),
                    gridcolor="#1a1a1a", zeroline=False,
                    range=[0, min(80, scatter_df[x_col].quantile(0.97) * 1.1)],
                ),
                yaxis=dict(
                    title=dict(text=y_label, font=dict(color="#888")),
                    gridcolor="#1a1a1a", zeroline=True,
                    zerolinecolor="rgba(255,255,255,0.12)",
                ),
                legend=dict(
                    bgcolor="rgba(0,0,0,0.6)", bordercolor="#333",
                    borderwidth=1, font=dict(color="#ccc", size=10),
                    x=1.0, y=1.0, xanchor="right",
                ),
                margin=dict(l=20, r=160, t=20, b=20),
            )
            st.plotly_chart(fig_sc, use_container_width=True)
            st.caption(
                "📊 **KGV vs. Wachstum:** Ideal = **links oben** (niedriges KGV + hohes Wachstum). "
                "PEG=1-Linie (gestrichelt gold) = faire Bewertung. "
                "Darüber = unterbewertet, darunter = überbewertet. "
                "Blasengröße = Value Score."
            )

    with tab_bar:
        top30 = view.head(30)
        if top30.empty:
            st.info("Keine Daten verfügbar.")
        else:
            bar_colors = top30["_grade"].map(
                {"A": "#22c55e", "B": "#f59e0b", "C": "#ef4444"}
            ).fillna("#888").tolist()

            fig_bar = go.Figure(go.Bar(
                x=top30["Ticker"],
                y=top30["⭐ Value Score"],
                marker_color=bar_colors,
                text=top30["⭐ Value Score"].apply(lambda v: f"{v:.0f}"),
                textposition="outside",
                textfont=dict(color="#ccc", size=10),
                customdata=np.stack([
                    top30["Klasse"], top30["PEG"],
                    top30["EPS Wachstum %"].fillna(0),
                ], axis=-1),
                hovertemplate=(
                    "<b>%{x}</b><br>"
                    "Value Score: %{y:.1f}<br>"
                    "Klasse: %{customdata[0]}<br>"
                    "PEG: %{customdata[1]}<br>"
                    "EPS Wachstum: %{customdata[2]:.1f}%"
                    "<extra></extra>"
                ),
            ))
            fig_bar.add_hline(y=75, line_dash="dot",
                              line_color="rgba(34,197,94,0.4)",
                              annotation_text="A (≥75)", annotation_font_color="#22c55e",
                              annotation_font_size=10)
            fig_bar.add_hline(y=55, line_dash="dot",
                              line_color="rgba(245,158,11,0.4)",
                              annotation_text="B (≥55)", annotation_font_color="#f59e0b",
                              annotation_font_size=10)
            fig_bar.update_layout(
                height=400,
                paper_bgcolor="#0c0c0c", plot_bgcolor="#0c0c0c",
                font=dict(color="#888", family="RedRose, sans-serif", size=10),
                xaxis=dict(gridcolor="#1a1a1a"),
                yaxis=dict(title=dict(text="Value Score",
                                      font=dict(color="#888")),
                           gridcolor="#1a1a1a", range=[0, 110]),
                margin=dict(l=10, r=10, t=10, b=30),
                showlegend=False,
            )
            st.plotly_chart(fig_bar, use_container_width=True)

    # ── Top 3 je Klasse ────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("""
    <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.2rem;
                color:#d4a843;letter-spacing:0.05em;margin-bottom:12px'>
        🏆 TOP 3 JE QUALITÄTSKLASSE
    </div>
    """, unsafe_allow_html=True)

    cols_top = st.columns(3)
    for gi, (grade_key, grade_title, gcolor, gemoji) in enumerate([
        ("A", "KLASSE A — Top Quality",  "#22c55e", "💎"),
        ("B", "KLASSE B — Solide",       "#f59e0b", "🥇"),
        ("C", "KLASSE C — Spekulativ",   "#ef4444", "🎯"),
    ]):
        top3 = df[df["_grade"] == grade_key].head(3)
        with cols_top[gi]:
            st.markdown(f"""
            <div style='border-top:3px solid {gcolor};background:#0f0f0f;
                        border-radius:10px;padding:16px;margin-bottom:8px'>
                <div style='font-family:RedRose,sans-serif;font-weight:700;
                            font-size:0.85rem;color:{gcolor};letter-spacing:0.06em;
                            margin-bottom:12px'>{gemoji} {grade_title}</div>
            """, unsafe_allow_html=True)
            if top3.empty:
                st.caption("Keine Aktien in dieser Klasse.")
            for _, row in top3.iterrows():
                peg_disp = row.get("PEG", "–") or "–"
                eg = row.get("EPS Wachstum %")
                eg_str = f"{eg:.1f}%" if pd.notna(eg) and eg is not None else "–"
                fpe = row.get("KGV erwartet")
                fpe_str = f"{fpe:.1f}x" if pd.notna(fpe) and fpe is not None else "–"
                up = row.get("Upside %")
                up_str = f"+{up:.1f}%" if pd.notna(up) and up and up > 0 else (f"{up:.1f}%" if pd.notna(up) and up else "–")
                up_color = "#22c55e" if (up and up > 0) else "#ef4444"
                st.markdown(f"""
                <div style='background:#161616;border:1px solid #222;border-radius:8px;
                            padding:12px 14px;margin-bottom:8px'>
                    <div style='display:flex;justify-content:space-between;align-items:center;
                                margin-bottom:6px'>
                        <div style='font-family:RedRose,sans-serif;font-weight:700;
                                    font-size:1rem;color:#f0f0f0'>{row['Ticker']}</div>
                        <div style='font-family:RedRose,sans-serif;font-weight:700;
                                    font-size:1.1rem;color:{gcolor}'>{row['⭐ Value Score']:.0f}</div>
                    </div>
                    <div style='font-family:RedRose,sans-serif;font-size:0.72rem;
                                color:#666;margin-bottom:8px'>{row.get('Name','')}</div>
                    <div style='display:grid;grid-template-columns:1fr 1fr;gap:4px'>
                        <div style='font-size:0.75rem;color:#888'>PEG</div>
                        <div style='font-size:0.75rem;color:#ccc;text-align:right'>{peg_disp}</div>
                        <div style='font-size:0.75rem;color:#888'>KGV (fwd)</div>
                        <div style='font-size:0.75rem;color:#ccc;text-align:right'>{fpe_str}</div>
                        <div style='font-size:0.75rem;color:#888'>EPS Wachstum</div>
                        <div style='font-size:0.75rem;color:#22c55e;text-align:right'>{eg_str}</div>
                        <div style='font-size:0.75rem;color:#888'>Kursziel Upside</div>
                        <div style='font-size:0.75rem;color:{up_color};text-align:right'>{up_str}</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("</div>", unsafe_allow_html=True)
