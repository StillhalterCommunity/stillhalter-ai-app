"""
Value-Screening-Logik für die Fundamentalanalyse.
Ausgelagert aus pages/02_Fundamentalanalyse.py, damit der Morgen-Prefetch
(data/prefetch.py) dieselben Funktionen aufwärmen kann, ohne die Seite zu importieren.

Datenquelle: Yahoo Finance via yfinance (+ Disk-Cache als persistenter Speicher).
"""

from __future__ import annotations

import math
import numpy as np
import yfinance as yf
import streamlit as st

from data import _persistent_cache as _dc


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


def _compute_value_data(ticker: str) -> dict:
    """Holt Fundamental-Daten via yfinance und berechnet Value Score (Live-Fetch)."""
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


@st.cache_data(ttl=7200, show_spinner=False)
def fetch_value_data(ticker: str) -> dict:
    """
    Value-Daten für einen Ticker mit dreistufiger Persistenz:
      1. Frischer Disk-Cache (≤18h, z.B. vom Morgen-Prefetch) → sofort
      2. Live-Fetch via yfinance → Disk speichern
      3. Bei Fehler: ältester Disk-Stand als Notfall-Fallback
    """
    key = f"value_data_{ticker}"

    # 1. Frischer Disk-Cache (vom Prefetch oder vorherigem Lauf)
    cached = _dc.load(key, max_age_hours=18)
    if cached is not None and "error" not in cached:
        return cached

    # 2. Live-Fetch
    try:
        result = _compute_value_data(ticker)
        if "error" not in result:
            _dc.save(key, result, ttl_hours=24)
            return result
        # Live lieferte Fehler → Notfall-Fallback versuchen
        emergency = _dc.load_latest(key)
        return emergency if emergency is not None else result
    except Exception as e:
        emergency = _dc.load_latest(key)
        if emergency is not None:
            return emergency
        return {"error": str(e), "ticker": ticker}


def warm_value_data(ticker: str) -> bool:
    """
    Wärmt den Disk-Cache für einen Ticker auf (für den Morgen-Prefetch).
    Erzwingt einen Live-Fetch und speichert auf Disk. Gibt True bei Erfolg.
    """
    try:
        result = _compute_value_data(ticker)
        if "error" not in result:
            _dc.save(f"value_data_{ticker}", result, ttl_hours=24)
            return True
    except Exception:
        pass
    return False
