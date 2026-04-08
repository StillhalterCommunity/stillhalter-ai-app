"""
Stillhalter AI App — Trend Signal Scanner
Stillhalter Trend Indikator (STI) Multi-Timeframe Confluence.
NOW: Cross gerade erst passiert (letzte geschlossene Kerze).
GET READY: STI nähert sich einem Cross — Einstieg steht bevor.
"""

import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
import math
import os
import pickle
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(
    page_title="Trend Signale · Stillhalter AI App",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)

from data.universes import get_universe_tickers, UNIVERSE_OPTIONS
from data.watchlist import ALL_TICKERS

SIGNAL_CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "trend_signal_cache.pkl")

# ══════════════════════════════════════════════════════════════════════════════
# INDIKATOREN
# ══════════════════════════════════════════════════════════════════════════════

def _calc_ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()

def _calc_stoch(df: pd.DataFrame, k=14, smooth_k=3) -> Optional[float]:
    """Schnelle Stochastik %K (14,3,3). Gibt geglättetes %K zurück."""
    try:
        if df is None or len(df) < k + smooth_k + 5:
            return None
        low_min  = df["Low"].rolling(k).min()
        high_max = df["High"].rolling(k).max()
        raw_k    = 100 * (df["Close"] - low_min) / (high_max - low_min)
        stoch_k  = raw_k.rolling(smooth_k).mean()
        val = float(stoch_k.iloc[-1])
        return val if not math.isnan(val) else None
    except Exception:
        return None

# ══════════════════════════════════════════════════════════════════════════════
# STI (Stillhalter Trend Indikator) — Schnelle & langsame Trendlinie
# ══════════════════════════════════════════════════════════════════════════════

def _analyze_tf(df: pd.DataFrame, lookback: int = 3) -> Dict:
    """STI Analyse eines Timeframes. Erkennt Cross + Konvergenz."""
    empty = {
        "direction": 0, "fresh_cross": False, "cross_dir": None,
        "candles_ago": 0, "quality": 0.0, "ema_fast": None, "ema_slow": None,
        "gap_pct": None, "converging": False, "cross_price": None,
    }
    if df is None or len(df) < 15:
        return empty

    close = df["Close"].dropna()
    if len(close) < 15:
        return empty

    ema_fast = _calc_ema(close, 2)   # STI Fast Line
    ema_slow = _calc_ema(close, 9)   # STI Slow Line

    direction = 1 if ema_fast.iloc[-1] > ema_slow.iloc[-1] else -1
    gap       = float(ema_fast.iloc[-1] - ema_slow.iloc[-1])
    gap_pct   = abs(gap) / float(close.iloc[-1]) * 100 if float(close.iloc[-1]) > 0 else None

    # Konvergenz: nähert sich STI Fast dem STI Slow?
    gap_5_ago = float(ema_fast.iloc[-5] - ema_slow.iloc[-5]) if len(ema_fast) >= 5 else gap
    converging = (direction == -1 and gap > gap_5_ago) or (direction == 1 and gap < gap_5_ago)

    result = {
        "direction":  direction,
        "fresh_cross": False,
        "cross_dir":   None,
        "candles_ago": 0,
        "quality":     0.0,
        "ema_fast":    round(float(ema_fast.iloc[-1]), 4),
        "ema_slow":    round(float(ema_slow.iloc[-1]), 4),
        "close":       round(float(close.iloc[-1]), 4),
        "gap_pct":     round(gap_pct, 3) if gap_pct is not None else None,
        "converging":  converging,
        "cross_price": None,
    }

    # Cross-Erkennung in letzten `lookback` geschlossenen Kerzen
    for i in range(1, min(lookback + 1, len(ema_fast) - 1)):
        p_f = float(ema_fast.iloc[-(i + 1)])
        p_s = float(ema_slow.iloc[-(i + 1)])
        c_f = float(ema_fast.iloc[-i])
        c_s = float(ema_slow.iloc[-i])
        bull = p_f <= p_s and c_f > c_s
        bear = p_f >= p_s and c_f < c_s
        if bull or bear:
            result["fresh_cross"] = True
            result["cross_dir"]   = "bullish" if bull else "bearish"
            result["candles_ago"] = i
            result["cross_price"] = round(float(close.iloc[-i]), 4)
            if "Open" in df.columns and "High" in df.columns:
                try:
                    body = abs(float(df["Close"].iloc[-i]) - float(df["Open"].iloc[-i]))
                    rng  = float(df["High"].iloc[-i]) - float(df["Low"].iloc[-i])
                    result["quality"] = body / rng if rng > 0 else 0.5
                except Exception:
                    result["quality"] = 0.5
            break

    return result


@st.cache_data(ttl=14400, show_spinner=False)
def _fetch_all_tf(ticker: str) -> Dict:
    """Lädt alle Timeframes + Stochastik für einen Ticker."""
    try:
        t = yf.Ticker(ticker)

        h1 = t.history(period="60d", interval="1h")
        h4 = pd.DataFrame()
        if h1 is not None and len(h1) > 20:
            h4 = h1.resample("4h").agg(
                {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
            ).dropna()

        d1 = t.history(period="2y",  interval="1d")
        w1 = t.history(period="5y",  interval="1wk")
        mo = t.history(period="10y", interval="1mo")

        price = float(d1["Close"].iloc[-1]) if d1 is not None and not d1.empty else None

        vol_ratio = None
        if d1 is not None and len(d1) >= 21:
            avg_vol   = d1["Volume"].iloc[-21:-1].mean()
            vol_ratio = float(d1["Volume"].iloc[-1]) / avg_vol if avg_vol > 0 else None

        stoch_daily = _calc_stoch(d1) if d1 is not None else None

        return {
            "ticker": ticker, "price": price,
            "4H": h4, "1D": d1, "1W": w1, "1M": mo,
            "vol_ratio": vol_ratio, "stoch_daily": stoch_daily,
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}

# ══════════════════════════════════════════════════════════════════════════════
# NOW-SIGNAL: Cross muss IN DER LETZTEN KERZE passiert sein
# ══════════════════════════════════════════════════════════════════════════════

def _score_ticker(ticker: str, data: Optional[Dict] = None) -> Optional[Dict]:
    """
    NOW-Signal: STI-Cross muss auf dem führenden Timeframe in der letzten
    geschlossenen Kerze passiert sein (candles_ago == 1). Sonst kein Signal.
    """
    try:
        if data is None:
            data = _fetch_all_tf(ticker)
        if "error" in data or data.get("price") is None:
            return None

        tf_map = {"1M": data["1M"], "1W": data["1W"], "1D": data["1D"], "4H": data["4H"]}
        # lookback=3 damit Richtungsinfo korrekt ist, aber Leading TF muss candles_ago==1 haben
        tf_res = {tf: _analyze_tf(df, lookback=3) for tf, df in tf_map.items()}

        weights    = {"1M": 2, "1W": 2, "1D": 1, "4H": 1}
        score      = sum(tf_res[tf]["direction"] * w for tf, w in weights.items())
        signal_dir = "bullish" if score > 0 else "bearish" if score < 0 else "neutral"

        if signal_dir == "neutral" or abs(score) < 4:
            return None

        # Führendes TF: FRISCHESTER Cross (candles_ago == 1 = jetzt gerade!)
        leading_tf = None
        for tf in ["1M", "1W", "1D", "4H"]:
            r = tf_res[tf]
            if r["fresh_cross"] and r["cross_dir"] == signal_dir and r["candles_ago"] == 1:
                leading_tf = tf
                break

        if leading_tf is None:
            return None   # Kein frischer Cross gerade eben → kein NOW-Signal

        # Kerzenkörper-Qualität
        signal_quality = tf_res[leading_tf].get("quality", 0.0)
        if signal_quality < 0.35:
            return None

        # Stochastik-Filter (14,3,3)
        stoch = data.get("stoch_daily")
        if stoch is not None:
            if signal_dir == "bullish" and stoch > 82:
                return None   # Überkauft
            if signal_dir == "bearish" and stoch < 18:
                return None   # Überverkauft

        stoch_ok = (
            (signal_dir == "bullish" and stoch is not None and 30 <= stoch <= 75) or
            (signal_dir == "bearish" and stoch is not None and 25 <= stoch <= 70)
        )

        vol_ratio  = data.get("vol_ratio")
        vol_rating = "stark" if (vol_ratio or 0) >= 1.5 else "ok" if (vol_ratio or 0) >= 1.1 else "schwach"

        return {
            "ticker":       ticker,
            "price":        data["price"],
            "score":        score,
            "signal_dir":   signal_dir,
            "leading_tf":   leading_tf,
            "tf_details":   tf_res,
            "vol_ratio":    round(vol_ratio, 2) if vol_ratio else None,
            "vol_rating":   vol_rating,
            "stoch":        round(stoch, 1) if stoch else None,
            "stoch_ok":     stoch_ok,
            "signal_quality": round(signal_quality, 2),
            "signal_type":  "now",
        }
    except Exception:
        return None

# ══════════════════════════════════════════════════════════════════════════════
# GET READY: STI Fast nähert sich STI Slow — Cross steht bevor
# ══════════════════════════════════════════════════════════════════════════════

def _score_approaching(ticker: str, data: Optional[Dict] = None) -> Optional[Dict]:
    """
    GET READY: Höhere TFs bereits aligned, aber der Trigger-TF hat noch keinen Cross.
    STI Fast und Slow konvergieren — Einstieg steht kurz bevor.
    """
    try:
        if data is None:
            data = _fetch_all_tf(ticker)
        if "error" in data or data.get("price") is None:
            return None

        tf_map = {"1M": data["1M"], "1W": data["1W"], "1D": data["1D"], "4H": data["4H"]}
        tf_res = {tf: _analyze_tf(df, lookback=3) for tf, df in tf_map.items()}

        weights = {"1M": 2, "1W": 2, "1D": 1, "4H": 1}

        # Höhere TF-Richtung bestimmen (ohne 4H/1D)
        upper_score = tf_res["1M"]["direction"] * 2 + tf_res["1W"]["direction"] * 2
        if abs(upper_score) < 3:
            return None   # Monat + Woche nicht aligned

        expected_dir = "bullish" if upper_score > 0 else "bearish"

        # Trigger-TF: Daily oder 4H noch nicht gekreuzt,
        # aber STI Fast nähert sich STI Slow (konvergiert)
        trigger_tf = None
        gap_pct    = None
        for tf in ["1D", "4H"]:
            r = tf_res[tf]
            # Richtung noch GEGEN den erwarteten Trend (noch kein Cross)
            is_opposite = r["direction"] != (1 if expected_dir == "bullish" else -1)
            if is_opposite and r.get("converging") and r.get("gap_pct") is not None:
                if r["gap_pct"] < 1.5:   # STI Fast/Slow < 1.5% auseinander
                    trigger_tf = tf
                    gap_pct    = r["gap_pct"]
                    break

        if trigger_tf is None:
            return None

        # Gesamtscore wenn Cross passieren würde
        hypothetical_tf_res = dict(tf_res)
        hypothetical_tf_res[trigger_tf] = dict(tf_res[trigger_tf])
        hypothetical_tf_res[trigger_tf]["direction"] = 1 if expected_dir == "bullish" else -1
        hyp_score = sum(hypothetical_tf_res[tf]["direction"] * w for tf, w in weights.items())
        if abs(hyp_score) < 4:
            return None

        stoch    = data.get("stoch_daily")
        stoch_ok = (
            (expected_dir == "bullish" and stoch is not None and stoch <= 75) or
            (expected_dir == "bearish" and stoch is not None and stoch >= 25)
        )

        return {
            "ticker":       ticker,
            "price":        data["price"],
            "score":        hyp_score,           # potentieller Score nach Cross
            "signal_dir":   expected_dir,
            "leading_tf":   trigger_tf,
            "tf_details":   tf_res,
            "gap_pct":      round(gap_pct, 3),
            "vol_ratio":    round(data["vol_ratio"], 2) if data.get("vol_ratio") else None,
            "stoch":        round(stoch, 1) if stoch else None,
            "stoch_ok":     stoch_ok,
            "signal_quality": 0.0,
            "signal_type":  "approaching",
        }
    except Exception:
        return None

# ══════════════════════════════════════════════════════════════════════════════
# HISTORISCHER BACKTEST
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=86400, show_spinner=False)
def backtest_setup(ticker: str, leading_tf: str, direction: str) -> Dict:
    """
    Vereinfachter Backtest: findet alle historischen STI-Cross-Instanzen
    auf dem Daily-Chart und misst die Kurs-Entwicklung danach.
    Gibt Win-Rate und Ø-Return zurück.
    """
    empty = {"n_trades": 0}
    # Fester Horizont: 20 Handelstage (~1 Monat) für alle Timeframes.
    # Kürzere Fenster liefern zu wenige Samples und sind statistisch weniger belastbar.
    # 5y Tages-Daten → typisch 80–150 Signale → ausreichend für verlässliche Statistik.
    fwd = 20

    try:
        t    = yf.Ticker(ticker)
        hist = t.history(period="10y", interval="1d")  # 10 Jahre für mehr Samples
        if hist is None or len(hist) < 60:
            return empty

        close    = hist["Close"].dropna()
        ema_fast = _calc_ema(close, 2)
        ema_slow = _calc_ema(close, 9)

        wins, losses, returns = [], [], []

        for i in range(10, len(close) - fwd):
            pf = float(ema_fast.iloc[i - 1])
            ps = float(ema_slow.iloc[i - 1])
            cf = float(ema_fast.iloc[i])
            cs = float(ema_slow.iloc[i])

            bull = pf <= ps and cf > cs
            bear = pf >= ps and cf < cs

            if (direction == "bullish" and bull) or (direction == "bearish" and bear):
                entry = float(close.iloc[i])
                exit_ = float(close.iloc[min(i + fwd, len(close) - 1)])
                ret   = (exit_ - entry) / entry * 100
                if direction == "bearish":
                    ret = -ret
                returns.append(ret)
                (wins if ret > 0 else losses).append(ret)

        n = len(returns)
        if n == 0:
            return empty

        win_rate = len(wins) / n * 100

        # Ø Gewinn-Move: nur die gewinnenden Setups (kein Verzerrungseffekt durch Verlierer)
        avg_win_stock = round(sum(wins) / len(wins), 1) if wins else 0.0

        # Option-Gewinn-Schätzung für Gewinner (ATM-Option Hebel ~10×, max 300%)
        option_wins = [min(r * 10, 300) for r in wins]
        avg_opt_win = round(sum(option_wins) / len(option_wins), 0) if option_wins else 0.0

        # Erwartungswert (EV) = Gewinnwahrscheinlichkeit × Ø Optionsgewinn − Verlustwahrsch. × 100
        # Bei vollem Prämienverlust im Verlustfall
        wr_frac = win_rate / 100
        ev = round(wr_frac * avg_opt_win - (1 - wr_frac) * 100, 0)

        return {
            "n_trades":       n,
            "win_rate":       round(win_rate, 0),
            "avg_win_stock":  avg_win_stock,
            "max_return":     round(max(returns), 1),
            "min_return":     round(min(returns), 1),
            "forward_days":   fwd,
            "avg_opt_win":    avg_opt_win,
            "ev":             ev,
        }
    except Exception:
        return empty

# ══════════════════════════════════════════════════════════════════════════════
# IV-BEWERTUNG
# ══════════════════════════════════════════════════════════════════════════════

def _assess_iv(data_1d: pd.DataFrame, current_iv: Optional[float]) -> Dict:
    """Vergleicht aktuelle IV mit Historischer Volatilität (20 Tage)."""
    if data_1d is None or len(data_1d) < 25:
        return {"rating": "unbekannt", "iv": current_iv, "hist_vol_20": None, "ratio": None}

    ret       = data_1d["Close"].pct_change().dropna()
    hist_vol  = float(ret.tail(20).std() * math.sqrt(252) * 100)

    if current_iv is None:
        return {"rating": "unbekannt", "iv": None, "hist_vol_20": round(hist_vol, 1), "ratio": None}

    ratio = current_iv / hist_vol if hist_vol > 0 else None
    if ratio is None:    rating = "unbekannt"
    elif ratio < 0.85:   rating = "sehr günstig"
    elif ratio < 1.10:   rating = "günstig"
    elif ratio < 1.40:   rating = "normal"
    elif ratio < 1.80:   rating = "erhöht"
    else:                rating = "teuer"

    return {
        "rating":       rating,
        "iv":           round(current_iv, 1),
        "hist_vol_20":  round(hist_vol, 1),
        "ratio":        round(ratio, 2) if ratio else None,
    }

# ══════════════════════════════════════════════════════════════════════════════
# WIDERSTÄNDE & UNTERSTÜTZUNGEN (Swing-Highs / Swing-Lows)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def _get_sr_levels(ticker: str, price: float) -> Dict:
    """
    Berechnet Widerstands- und Unterstützungszonen via Swing-Highs/-Lows
    aus dem 1-Jahres-Daily-Chart. Clustert nahegelegene Level (< 1.5% Abstand).
    Gibt die 4 nächsten Widerstände oberhalb und Unterstützungen unterhalb zurück.
    """
    empty: Dict = {"support": [], "resistance": []}
    try:
        t    = yf.Ticker(ticker)
        hist = t.history(period="1y", interval="1d")
        if hist is None or len(hist) < 20:
            return empty

        highs  = hist["High"].values.astype(float)
        lows   = hist["Low"].values.astype(float)
        window = 5
        res_raw: List[float] = []
        sup_raw: List[float] = []

        for i in range(window, len(highs) - window):
            if highs[i] == max(highs[i - window: i + window + 1]):
                res_raw.append(round(highs[i], 2))
            if lows[i] == min(lows[i - window: i + window + 1]):
                sup_raw.append(round(lows[i], 2))

        def _cluster(levels: List[float], pct: float = 0.015) -> List[float]:
            if not levels:
                return []
            levels = sorted(levels)
            out: List[float] = []
            grp = [levels[0]]
            for lv in levels[1:]:
                if abs(lv - grp[-1]) / grp[-1] < pct:
                    grp.append(lv)
                else:
                    out.append(round(sum(grp) / len(grp), 2))
                    grp = [lv]
            out.append(round(sum(grp) / len(grp), 2))
            return out

        res_cl = _cluster(res_raw)
        sup_cl = _cluster(sup_raw)

        res_above = sorted([r for r in res_cl if r > price * 1.003])[:4]
        sup_below = sorted([s for s in sup_cl if s < price * 0.997], reverse=True)[:4]

        return {"support": sup_below, "resistance": res_above}
    except Exception:
        return empty


def _sr_html(
    ticker: str,
    price: float,
    signal_dir: str,
    iv: Optional[float] = None,
    dte: Optional[int] = None,
    strike: Optional[float] = None,
    premium: Optional[float] = None,
) -> str:
    """
    Preis-Leiter mit drei klar getrennten Ebenen:
      1) S/R-Levels   — echte Widerstände & Unterstützungen aus Kurshistorie
      2) Gewinn-Ziele — 2:1 (MIN) / 3:1 (BASE) / 4:1 (BEST) basierend auf Strike & Prämie
      3) IV-Reichweite — was ist in DTE Tagen statistisch möglich (1σ ≈ 68% Wahrscheinlichkeit)
    """
    bullish = signal_dir == "bullish"

    # ── 1) Echte S/R-Level aus Kurshistorie ───────────────────────────────────
    sr       = _get_sr_levels(ticker, price)
    res_list = sr.get("resistance", [])   # aufsteigend: res_list[0] = nächster W
    sup_list = sr.get("support",    [])   # absteigend: sup_list[0] = nächste U

    # ── 2) Gewinn-Ziele aus Optionspreis ──────────────────────────────────────
    # Formel: CALL @K, Prämie P
    #   Option bei Verfall wert 3P → Kurs = K + 3P  (Einnahme 2P = 2:1)
    #   Option bei Verfall wert 4P → Kurs = K + 4P  (Einnahme 3P = 3:1)
    #   Option bei Verfall wert 5P → Kurs = K + 5P  (Einnahme 4P = 4:1)
    # PUT umgekehrt (K - nP)
    ziel_2to1: Optional[float] = None
    ziel_3to1: Optional[float] = None
    ziel_4to1: Optional[float] = None
    if strike and premium and premium > 0:
        if bullish:
            ziel_2to1 = round(strike + 3 * premium, 2)
            ziel_3to1 = round(strike + 4 * premium, 2)
            ziel_4to1 = round(strike + 5 * premium, 2)
        else:
            ziel_2to1 = round(strike - 3 * premium, 2)
            ziel_3to1 = round(strike - 4 * premium, 2)
            ziel_4to1 = round(strike - 5 * premium, 2)

    # ── 3) IV-Reichweite (1σ-Erwartung) ──────────────────────────────────────
    # 1σ-Move = Kurs × IV × √(DTE/365)
    # Interpretation: In DTE Tagen bleibt der Kurs mit ~68% Wahrscheinlichkeit
    #                 innerhalb ±1σ vom aktuellen Niveau.
    sigma_move: Optional[float] = None
    iv_upper: Optional[float] = None
    iv_lower: Optional[float] = None
    if iv and iv > 0 and dte and dte > 0:
        move       = price * (iv / 100) * math.sqrt(dte / 365)
        sigma_move = round(move, 2)
        iv_upper   = round(price + move, 2)
        iv_lower   = round(price - move, 2)

    # Fallback wenn gar keine Daten
    if not res_list and not sup_list and ziel_2to1 is None and sigma_move is None:
        return (
            "<div style='background:#111;border:1px solid #1e1e1e;border-radius:10px;"
            "padding:14px;height:100%;display:flex;align-items:center;justify-content:center'>"
            "<span style='color:#333;font-size:0.78rem;font-family:sans-serif'>"
            "Keine Daten verfügbar</span></div>"
        )

    # ── Zeilen-Helper ──────────────────────────────────────────────────────────
    def _sr_row(val: float, label: str, color: str, alpha_idx: int) -> str:
        """S/R-Level Zeile — subtil, kein Ziel-Styling."""
        pct    = round((val - price) / price * 100, 1)
        sign   = "+" if pct >= 0 else ""
        alphas = ["dd", "99", "66", "44"]
        a      = alphas[min(alpha_idx, 3)]
        fw     = "700" if alpha_idx == 0 else "400"
        return (
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"padding:4px 10px;margin-bottom:1px;border-radius:4px;"
            f"background:#0c0c0c;border-left:3px solid {color}{a}'>"
            f"<div style='display:flex;align-items:center;gap:7px'>"
            f"<span style='font-size:0.6rem;color:{color}{a};font-family:sans-serif;"
            f"min-width:24px'>{label}</span>"
            f"<span style='font-family:monospace;font-size:0.85rem;font-weight:{fw};"
            f"color:{color}{a}'>{val:.2f}</span>"
            f"</div>"
            f"<span style='font-size:0.68rem;color:{color}{a}'>{sign}{pct:.1f}%</span>"
            f"</div>"
        )

    def _ziel_row(val: float, ratio: str, label: str, color: str, bg: str) -> str:
        """Gewinn-Ziel Zeile — prominent, klar als ZIEL gekennzeichnet."""
        pct  = round((val - price) / price * 100, 1)
        sign = "+" if pct >= 0 else ""
        return (
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"padding:6px 10px;margin-bottom:2px;border-radius:5px;"
            f"background:{bg};border:2px dashed {color}'>"
            f"<div style='display:flex;align-items:center;gap:7px'>"
            f"<span style='font-size:0.62rem;background:{color}22;color:{color};"
            f"border-radius:3px;padding:1px 6px;font-family:sans-serif;font-weight:700;"
            f"white-space:nowrap'>ZIEL {ratio}</span>"
            f"<span style='font-family:monospace;font-size:0.92rem;font-weight:800;"
            f"color:{color}'>{val:.2f}</span>"
            f"<span style='font-size:0.6rem;color:{color}99;font-family:sans-serif'>{label}</span>"
            f"</div>"
            f"<span style='font-size:0.8rem;font-weight:800;color:{color}'>"
            f"{sign}{pct:.1f}%</span>"
            f"</div>"
        )

    price_row = (
        f"<div style='display:flex;align-items:center;justify-content:space-between;"
        f"padding:7px 12px;margin:6px 0;background:#1a1205;"
        f"border:2px solid #d4a843;border-radius:6px'>"
        f"<div style='display:flex;align-items:center;gap:8px'>"
        f"<span style='color:#d4a843;font-size:0.82rem'>◀</span>"
        f"<span style='font-family:monospace;font-size:1.05rem;font-weight:900;"
        f"color:#d4a843'>{price:.2f}</span></div>"
        f"<span style='font-size:0.65rem;color:#666;font-family:sans-serif'>"
        f"Aktueller Kurs</span></div>"
    )

    # ── IV-Reichweite Banner ───────────────────────────────────────────────────
    iv_banner = ""
    if sigma_move and dte:
        up_pct = round(sigma_move / price * 100, 1)
        iv_dir = f"+{up_pct:.1f}% / −{up_pct:.1f}%"
        iv_banner = (
            f"<div style='background:#050d1a;border:1px solid #1e3a5f;"
            f"border-radius:6px;padding:6px 10px;margin-bottom:8px;"
            f"display:flex;justify-content:space-between;align-items:center'>"
            f"<div style='font-size:0.62rem;color:#3b82f6;font-family:sans-serif'>"
            f"📐 <b>IV-Reichweite</b> in {dte} Tagen (1σ · 68% Wkt.)</div>"
            f"<div style='text-align:right'>"
            f"<span style='font-family:monospace;font-size:0.78rem;color:#60a5fa'>"
            f"±{sigma_move:.2f} USD</span>"
            f"<span style='font-size:0.6rem;color:#3b82f688;margin-left:5px'>{iv_dir}</span>"
            f"</div></div>"
        )

    # ── Leiter zusammenbauen ──────────────────────────────────────────────────
    rows: List[str] = []

    if bullish:
        # Alle Levels OBERHALB des Kurses sammeln & sortieren (höchste zuerst)
        above: List[Tuple[float, str]] = []

        # S/R Widerstände
        for i, r in enumerate(res_list):
            above.append((r, f"sr_res_{i}"))

        # Gewinn-Ziele
        if ziel_4to1 is not None:
            above.append((ziel_4to1, "z4"))
        if ziel_3to1 is not None:
            above.append((ziel_3to1, "z3"))
        if ziel_2to1 is not None:
            above.append((ziel_2to1, "z2"))

        above.sort(key=lambda x: x[0], reverse=True)

        for val, typ in above:
            if typ.startswith("sr_res_"):
                i = int(typ.split("_")[-1])
                rows.append(_sr_row(val, f"W{i+1}", "#ef4444", i))
            elif typ == "z4":
                rows.append(_ziel_row(val, "4:1", "BEST", "#f59e0b", "#130d00"))
            elif typ == "z3":
                rows.append(_ziel_row(val, "3:1", "BASE", "#22c55e", "#061008"))
            elif typ == "z2":
                rows.append(_ziel_row(val, "2:1", "MIN",  "#6b7280", "#0d0d0d"))

        rows.append(price_row)

        # Unterstützungen unterhalb
        for i, s in enumerate(sup_list):
            rows.append(_sr_row(s, f"U{i+1}", "#22c55e", i))

    else:  # bearish
        # Widerstände oben
        for i, r in enumerate(reversed(res_list)):
            rows.append(_sr_row(r, f"W{len(res_list) - i}", "#ef4444", len(res_list) - 1 - i))

        rows.append(price_row)

        # Alle Levels UNTERHALB sammeln & sortieren (höchste zuerst → nächste Put-Ziele oben)
        below: List[Tuple[float, str]] = []

        for i, s in enumerate(sup_list):
            below.append((s, f"sr_sup_{i}"))

        if ziel_2to1 is not None:
            below.append((ziel_2to1, "z2"))
        if ziel_3to1 is not None:
            below.append((ziel_3to1, "z3"))
        if ziel_4to1 is not None:
            below.append((ziel_4to1, "z4"))

        below.sort(key=lambda x: x[0], reverse=True)

        for val, typ in below:
            if typ.startswith("sr_sup_"):
                i = int(typ.split("_")[-1])
                rows.append(_sr_row(val, f"U{i+1}", "#22c55e", i))
            elif typ == "z2":
                rows.append(_ziel_row(val, "2:1", "MIN",  "#6b7280", "#0d0d0d"))
            elif typ == "z3":
                rows.append(_ziel_row(val, "3:1", "BASE", "#22c55e", "#061008"))
            elif typ == "z4":
                rows.append(_ziel_row(val, "4:1", "BEST", "#f59e0b", "#130d00"))

    # ── Positions-Balken (U1 → W1) ────────────────────────────────────────────
    pos_bar_html = ""
    if res_list and sup_list:
        nr, ns  = res_list[0], sup_list[0]
        zone    = nr - ns
        pos_pct = max(3, min(97, (price - ns) / zone * 100)) if zone > 0 else 50
        bar_fg  = "#22c55e1a" if bullish else "#ef44441a"

        def _bar_mk(val: float, col: str, w: int = 2) -> str:
            tp = max(1, min(99, (val - ns) / zone * 100)) if zone > 0 else 50
            return (
                f"<div style='position:absolute;top:-3px;left:calc({tp:.0f}% - {w//2}px);"
                f"width:{w}px;height:14px;background:{col};border-radius:1px'></div>"
            )

        mk = ""
        if ziel_4to1 and ns <= ziel_4to1 <= nr:
            mk += _bar_mk(ziel_4to1, "#f59e0b", 3)
        if ziel_3to1 and ns <= ziel_3to1 <= nr:
            mk += _bar_mk(ziel_3to1, "#22c55e", 2)
        if ziel_2to1 and ns <= ziel_2to1 <= nr:
            mk += _bar_mk(ziel_2to1, "#888", 2)
        if iv_upper and ns <= iv_upper <= nr:
            mk += _bar_mk(iv_upper, "#3b82f666", 1)
        if iv_lower and ns <= iv_lower <= nr:
            mk += _bar_mk(iv_lower, "#3b82f666", 1)

        pos_bar_html = (
            f"<div style='margin-bottom:10px'>"
            f"<div style='display:flex;justify-content:space-between;font-size:0.58rem;"
            f"color:#444;font-family:sans-serif;margin-bottom:3px'>"
            f"<span style='color:#22c55e88'>U1 {ns:.2f}</span>"
            f"<span style='color:#ef444488'>W1 {nr:.2f}</span></div>"
            f"<div style='background:#1a1a1a;border-radius:4px;height:8px;"
            f"position:relative;overflow:visible'>"
            f"<div style='width:{pos_pct:.0f}%;height:100%;background:{bar_fg};"
            f"border-radius:4px'></div>"
            + mk +
            f"<div style='position:absolute;top:-3px;left:calc({pos_pct:.0f}% - 2px);"
            f"width:4px;height:14px;background:#d4a843;border-radius:2px'></div>"
            f"</div>"
            f"<div style='display:flex;gap:10px;margin-top:4px;font-family:sans-serif;"
            f"flex-wrap:wrap'>"
            f"<span style='font-size:0.58rem;color:#555'>Kurs bei {pos_pct:.0f}%</span>"
            + (f"<span style='font-size:0.58rem;color:#f59e0b'>── 4:1 BEST</span>" if ziel_4to1 and ns <= ziel_4to1 <= nr else "")
            + (f"<span style='font-size:0.58rem;color:#22c55e'>── 3:1 BASE</span>" if ziel_3to1 and ns <= ziel_3to1 <= nr else "")
            + (f"<span style='font-size:0.58rem;color:#3b82f666'>── 1σ</span>" if iv_upper and ns <= iv_upper <= nr else "")
            + f"</div></div>"
        )

    # ── Legende ───────────────────────────────────────────────────────────────
    legend_parts = []
    if strike and premium:
        legend_parts.append(f"Strike {strike:.0f} · Prämie {premium:.2f}")
    if iv:
        legend_parts.append(f"IV {iv:.0f}%")
    if dte:
        legend_parts.append(f"DTE {dte}")
    legend_note = (
        "W1–W4 = Widerstände · U1–U4 = Unterstützungen (aus 1J-Chart) · "
        "ZIEL = Gewinn-Vielfaches der Prämie"
    )
    legend_html = (
        f"<div style='font-size:0.58rem;color:#333;font-family:sans-serif;"
        f"margin-top:8px;padding-top:6px;border-top:1px solid #1a1a1a;line-height:1.8'>"
        + (" &nbsp;·&nbsp; ".join(legend_parts) + "<br>" if legend_parts else "")
        + legend_note
        + "</div>"
    )

    return (
        f"<div style='background:#111;border:1px solid #1e1e1e;border-radius:10px;"
        f"padding:14px;height:100%'>"
        f"<div style='font-size:0.62rem;color:#555;text-transform:uppercase;"
        f"letter-spacing:0.08em;font-family:sans-serif;margin-bottom:8px'>"
        f"📊 Widerstände · Unterstützungen · Ziele</div>"
        + iv_banner
        + pos_bar_html
        + "".join(rows)
        + legend_html
        + "</div>"
    )

# ══════════════════════════════════════════════════════════════════════════════
# OPTIONS-EMPFEHLUNG
# ══════════════════════════════════════════════════════════════════════════════

_DTE_MAP = {"1M": 120, "1W": 70, "1D": 40, "4H": 21}

@st.cache_data(ttl=3600, show_spinner=False)
def get_option_rec(ticker: str, direction: str, leading_tf: str, price: float) -> Dict:
    opt_type   = "CALL" if direction == "bullish" else "PUT"
    target_dte = _DTE_MAP.get(leading_tf, 45)
    target_date = date.today() + timedelta(days=target_dte)

    base = {
        "type": opt_type, "strike": None, "expiry": None, "dte": target_dte,
        "premium": None, "bid": None, "ask": None, "iv": None, "hist_vol_20": None,
        "iv_rating": "unbekannt", "iv_ratio": None,
        "open_interest": None, "spread_pct": None,
        "liquidity": "unbekannt", "earnings": None,
        "spread_alt": None,
        "strategy": "Long " + opt_type,
    }

    try:
        stk  = yf.Ticker(ticker)
        exps = stk.options or []
        valid = []
        for exp in exps:
            try:
                d = datetime.strptime(exp, "%Y-%m-%d").date()
                days_out = (d - date.today()).days
                if days_out >= max(14, target_dte - 15):
                    valid.append((exp, abs((d - target_date).days)))
            except Exception:
                pass

        if not valid:
            return base

        best_exp   = min(valid, key=lambda x: x[1])[0]
        actual_dte = (datetime.strptime(best_exp, "%Y-%m-%d").date() - date.today()).days
        base["expiry"] = best_exp
        base["dte"]    = actual_dte

        chain = stk.option_chain(best_exp)
        opts  = chain.calls if opt_type == "CALL" else chain.puts
        if opts is None or opts.empty:
            return base

        opts = opts.copy()
        opts["dist"] = (opts["strike"] - price).abs()
        atm_row = opts.sort_values("dist").iloc[0]

        strike     = float(atm_row["strike"])
        bid        = float(atm_row.get("bid", 0) or 0)
        ask        = float(atm_row.get("ask", 0) or 0)
        last       = float(atm_row.get("lastPrice", 0) or 0)
        iv_raw     = float(atm_row.get("impliedVolatility", 0) or 0)
        oi         = int(atm_row.get("openInterest", 0) or 0)

        mid        = round((bid + ask) / 2, 2) if (bid > 0 and ask > 0) else round(last, 2)
        spread_pct = round((ask - bid) / mid * 100, 1) if mid > 0 else 99.0

        d1      = stk.history(period="1y", interval="1d")
        iv_data = _assess_iv(d1, iv_raw * 100 if iv_raw > 0 else None)

        if oi >= 200 and spread_pct <= 8:    liquidity = "sehr gut"
        elif oi >= 50 and spread_pct <= 15:  liquidity = "gut"
        elif oi >= 10:                       liquidity = "mittel"
        else:                                liquidity = "schlecht"

        base.update({
            "strike":       strike,
            "premium":      mid,
            "bid":          bid,
            "ask":          ask,
            "iv":           round(iv_raw * 100, 1),
            "hist_vol_20":  iv_data.get("hist_vol_20"),
            "iv_rating":    iv_data.get("rating", "unbekannt"),
            "iv_ratio":     iv_data.get("ratio"),
            "open_interest": oi,
            "spread_pct":   spread_pct,
            "liquidity":    liquidity,
        })

        # Spread-Alternative bei hoher IV
        iv_ratio = iv_data.get("ratio") or 0
        if iv_ratio >= 1.40 and mid and mid > 0:
            otm_s   = round((price * (1.07 if direction == "bullish" else 0.93)) / 5) * 5
            otm_row = opts.iloc[(opts["strike"] - otm_s).abs().argsort()[:1]]
            if not otm_row.empty:
                ob  = float(otm_row.get("bid", pd.Series([0])).iloc[0] or 0)
                oa  = float(otm_row.get("ask", pd.Series([0])).iloc[0] or 0)
                om  = round((ob + oa) / 2, 2) if ob > 0 else 0
                nd  = round(mid - om, 2)
                sn  = "Bull Call Spread" if direction == "bullish" else "Bear Put Spread"
                base["spread_alt"] = {
                    "name":       sn,
                    "buy_strike": strike,
                    "sell_strike": float(otm_row["strike"].iloc[0]),
                    "net_debit":  nd,
                    "max_profit": round(abs(float(otm_row["strike"].iloc[0]) - strike) - nd, 2),
                }

        if mid and mid > 0:
            base["strategy"] = (
                f"Long {opt_type} @{strike:.0f} — Halten solange STI-Trend auf "
                f"{_TF_LABELS.get(leading_tf,'')} intakt. Exit bei STI-Cross in Gegenrichtung."
            )

        return base
    except Exception:
        return base

# ══════════════════════════════════════════════════════════════════════════════
# MARKT-REGIME
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def _market_regime() -> Dict:
    regimes = {}
    for etf in ["SPY", "QQQ"]:
        try:
            t  = yf.Ticker(etf)
            d1 = t.history(period="1y",  interval="1d")
            w1 = t.history(period="3y",  interval="1wk")
            dr = _analyze_tf(d1)
            wr = _analyze_tf(w1)
            sc = dr["direction"] + wr["direction"]
            regimes[etf] = {
                "score":  sc,
                "daily":  dr["direction"],
                "weekly": wr["direction"],
                "regime": "bullish" if sc > 0 else "bearish" if sc < 0 else "neutral",
                "price":  float(d1["Close"].iloc[-1]) if d1 is not None and not d1.empty else None,
            }
        except Exception:
            regimes[etf] = {"regime": "unbekannt", "score": 0}
    return regimes

# ══════════════════════════════════════════════════════════════════════════════
# SCAN-ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def run_scan(tickers: List[str], progress_cb=None) -> Tuple[List[Dict], List[Dict]]:
    """Gibt (now_signals, approaching_signals) zurück."""
    now_signals  = []
    get_ready    = []
    done = 0
    total = len(tickers)

    def _worker(ticker):
        data       = _fetch_all_tf(ticker)
        sig_now    = _score_ticker(ticker, data)
        sig_ready  = _score_approaching(ticker, data)
        if sig_now:
            rec = get_option_rec(
                ticker=sig_now["ticker"], direction=sig_now["signal_dir"],
                leading_tf=sig_now["leading_tf"], price=sig_now["price"],
            )
            sig_now["option_rec"] = rec
        return sig_now, sig_ready

    with ThreadPoolExecutor(max_workers=12) as pool:
        futures = {pool.submit(_worker, t): t for t in tickers}
        for fut in as_completed(futures):
            done += 1
            if progress_cb:
                progress_cb(done / total)
            try:
                sn, sr = fut.result()
                if sn:
                    now_signals.append(sn)
                if sr and sr["ticker"] not in {s["ticker"] for s in now_signals}:
                    get_ready.append(sr)
            except Exception:
                pass

    now_signals.sort(key=lambda x: abs(x["score"]), reverse=True)
    get_ready.sort(key=lambda x: x.get("gap_pct", 99))  # kleinster Gap zuerst
    return now_signals, get_ready

# ══════════════════════════════════════════════════════════════════════════════
# UI HELPERS
# ══════════════════════════════════════════════════════════════════════════════

_TF_LABELS = {"1M": "Monat", "1W": "Woche", "1D": "Tag", "4H": "4H"}
_TF_COLORS = {"1M": "#a855f7", "1W": "#3b82f6", "1D": "#10b981", "4H": "#f59e0b"}
_TF_WEIGHTS = {"1M": 2, "1W": 2, "1D": 1, "4H": 1}


def _score_breakdown_html(tf_details: Dict, score: int, signal_dir: str) -> str:
    """Visualisiert wie der Score zustande kommt."""
    rows = []
    for tf in ["1M", "1W", "1D", "4H"]:
        r     = tf_details.get(tf, {})
        d     = r.get("direction", 0)
        w     = _TF_WEIGHTS[tf]
        pts   = d * w
        col   = _TF_COLORS[tf]
        fresh = r.get("fresh_cross") and r.get("cross_dir") == signal_dir
        ago   = r.get("candles_ago", 0)
        qual  = r.get("quality", 0)
        gap   = r.get("gap_pct")

        sti_label = "STI bullish ▲" if d > 0 else "STI bearish ▼"
        pts_col   = "#22c55e" if pts > 0 else "#ef4444" if pts < 0 else "#555"
        pts_str   = f"+{pts}" if pts >= 0 else str(pts)
        check     = "✅" if (d > 0) == (signal_dir == "bullish") else "✗"

        fresh_tag = ""
        if fresh:
            fresh_tag = (
                f"<span style='color:#fbbf24;font-size:0.68rem;margin-left:6px'>"
                f"🔔 Cross letzte {ago} Kerze{'n' if ago > 1 else ''} "
                f"(Kerzenstärke {qual:.0%})</span>"
            )
        elif gap is not None and abs(gap) < 1.5:
            fresh_tag = (
                f"<span style='color:#94a3b8;font-size:0.68rem;margin-left:6px'>"
                f"↔ Abstand {gap:.2f}% — Cross nähert sich</span>"
            )

        rows.append(
            f"<div style='display:flex;align-items:center;gap:8px;padding:4px 0;"
            f"border-bottom:1px solid #1a1a1a;font-family:sans-serif'>"
            f"<span style='color:{col};font-weight:700;font-size:0.75rem;min-width:38px'>"
            f"{_TF_LABELS[tf]}</span>"
            f"<span style='font-size:0.75rem;color:#aaa;flex:1'>{check} {sti_label}</span>"
            f"{fresh_tag}"
            f"<span style='font-size:0.85rem;font-weight:700;color:{pts_col};"
            f"min-width:24px;text-align:right'>{pts_str}</span>"
            f"</div>"
        )

    score_col = "#22c55e" if score > 0 else "#ef4444"
    score_lbl = f"+{score}" if score > 0 else str(score)

    return (
        f"<div style='background:#0e0e0e;border-radius:8px;padding:10px 12px'>"
        f"<div style='font-size:0.6rem;color:#555;text-transform:uppercase;"
        f"letter-spacing:0.08em;font-family:sans-serif;margin-bottom:6px'>"
        f"STI Score Berechnung</div>"
        + "".join(rows)
        + f"<div style='display:flex;justify-content:flex-end;margin-top:6px;"
          f"font-family:sans-serif'>"
          f"<span style='font-size:0.75rem;color:#555'>Gesamt:</span>&nbsp;"
          f"<span style='font-size:1.0rem;font-weight:900;color:{score_col}'>"
          f"{score_lbl}/6</span></div>"
        + f"</div>"
    )


def _backtest_html(bt: Dict, direction: str, fwd: int) -> str:
    """Visualisiert Backtest-Ergebnisse (nur positive Kennzahlen + Erwartungswert)."""
    if bt.get("n_trades", 0) == 0:
        return ""
    n    = bt["n_trades"]
    wr   = bt["win_rate"]
    wstk = bt.get("avg_win_stock", 0.0)   # Ø Kurs-Move bei Gewinnern
    opt  = bt.get("avg_opt_win",   0.0)   # Ø Option-Gewinn bei Gewinnern
    ev   = bt.get("ev",            0.0)   # Erwartungswert pro Trade

    wr_col  = "#22c55e" if wr >= 60 else "#f59e0b" if wr >= 45 else "#ef4444"
    wstk_col = "#22c55e" if wstk > 0 else "#555"
    opt_col  = "#22c55e" if opt  > 0 else "#555"
    ev_col   = "#22c55e" if ev   > 0 else "#ef4444"

    return (
        f"<div style='background:#0a0a1a;border:1px solid #1e1e3a;border-radius:8px;"
        f"padding:10px 12px;margin-top:8px'>"
        f"<div style='font-size:0.6rem;color:#555;text-transform:uppercase;"
        f"letter-spacing:0.08em;font-family:sans-serif;margin-bottom:6px'>"
        f"📊 Backtest: {n} Setups · 10J · Horizont {fwd}T</div>"
        f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:6px'>"
        # Trefferquote
        f"<div style='background:#0e0e0e;border-radius:6px;padding:5px 8px'>"
        f"<div style='font-size:0.6rem;color:#555;font-family:sans-serif'>Trefferquote</div>"
        f"<div style='font-size:1.0rem;font-weight:700;color:{wr_col};"
        f"font-family:sans-serif'>{wr:.0f}%</div></div>"
        # Ø Gewinn-Move (nur Gewinner)
        f"<div style='background:#0e0e0e;border-radius:6px;padding:5px 8px'>"
        f"<div style='font-size:0.6rem;color:#555;font-family:sans-serif'>Ø Gewinn-Move</div>"
        f"<div style='font-size:1.0rem;font-weight:700;color:{wstk_col};"
        f"font-family:sans-serif'>+{wstk:.1f}%</div></div>"
        f"</div>"
        # Erwartungswert (volle Breite)
        f"<div style='background:#0e0e0e;border-radius:6px;padding:6px 10px;"
        f"border:1px solid {ev_col}33'>"
        f"<div style='font-size:0.6rem;color:#555;font-family:sans-serif;margin-bottom:2px'>"
        f"Erwartungswert pro Trade (Schätzung*)</div>"
        f"<div style='font-size:1.1rem;font-weight:700;color:{ev_col};font-family:sans-serif'>"
        f"{'+' if ev >= 0 else ''}{ev:.0f}% auf Prämie</div>"
        f"</div>"
        f"<div style='font-size:0.6rem;color:#444;font-family:sans-serif;margin-top:5px'>"
        f"*Ø Optionsgewinn Gewinner: +{opt:.0f}% · Verluste: −100% · Δ≈0.55, Hebel ~10×. "
        f"Vergangene Performance ≠ Zukunft.</div>"
        f"</div>"
    )


def _iv_badge(rating: str) -> str:
    col_map = {
        "sehr günstig": "#22c55e", "günstig": "#86efac",
        "normal": "#f59e0b", "erhöht": "#f97316", "teuer": "#ef4444", "unbekannt": "#555",
    }
    col = col_map.get(rating, "#555")
    return (
        f"<span style='background:{col}22;border:1px solid {col};color:{col};"
        f"padding:2px 8px;border-radius:10px;font-size:0.72rem;font-weight:700;"
        f"font-family:sans-serif'>IV {rating}</span>"
    )

def _liq_badge(rating: str) -> str:
    col_map = {"sehr gut": "#22c55e", "gut": "#86efac", "mittel": "#f59e0b",
               "schlecht": "#ef4444", "unbekannt": "#555"}
    col = col_map.get(rating, "#555")
    return (
        f"<span style='background:{col}22;border:1px solid {col};color:{col};"
        f"padding:2px 8px;border-radius:10px;font-size:0.72rem;font-weight:700;"
        f"font-family:sans-serif'>Liq. {rating}</span>"
    )

# ══════════════════════════════════════════════════════════════════════════════
# SIGNAL-KARTE (NOW)
# ══════════════════════════════════════════════════════════════════════════════

def _render_signal_card(sig: Dict, market_regime: Dict, show_backtest: bool = True) -> None:
    ticker     = sig["ticker"]
    price      = sig["price"]
    score      = sig["score"]
    sig_dir    = sig["signal_dir"]
    leading_tf = sig["leading_tf"]
    tf_det     = sig["tf_details"]
    rec        = sig.get("option_rec", {})
    stoch      = sig.get("stoch")
    vol_ratio  = sig.get("vol_ratio")
    is_now     = sig.get("signal_type") == "now"

    dir_color = "#22c55e" if sig_dir == "bullish" else "#ef4444"
    dir_icon  = "📈" if sig_dir == "bullish" else "📉"
    dir_label = "BULLISH → CALL kaufen" if sig_dir == "bullish" else "BEARISH → PUT kaufen"
    opt_type  = rec.get("type", "CALL" if sig_dir == "bullish" else "PUT")
    strike    = rec.get("strike")
    expiry    = rec.get("expiry")
    dte       = rec.get("dte")
    premium   = rec.get("premium")
    iv_rating = rec.get("iv_rating", "unbekannt")
    liquidity = rec.get("liquidity", "unbekannt")
    spread_alt = rec.get("spread_alt")

    spy_regime = market_regime.get("SPY", {}).get("regime", "neutral")
    market_warning = ""
    if sig_dir == "bullish" and spy_regime == "bearish":
        market_warning = "⚠️ SPY bearish — Call gegen Markttrend"
    elif sig_dir == "bearish" and spy_regime == "bullish":
        market_warning = "⚠️ SPY bullish — Put gegen Markttrend"

    exp_icon  = "🟢" if sig_dir == "bullish" else "🔴"
    exp_title = (
        f"{exp_icon} **{ticker}** · Score {'+' if score > 0 else ''}{score}/6 · "
        f"{opt_type} @{strike:.0f} · {dte}T"
        if strike else
        f"{exp_icon} **{ticker}** · Score {'+' if score > 0 else ''}{score}/6 · {dir_label}"
    )

    with st.expander(exp_title, expanded=(abs(score) == 6)):
        # 4-Spalten-Layout:
        # A: STI Score + Einstieg | B: S/R Preis-Leiter | C: Options-Empfehlung | D: Filter + Backtest
        ca, cb, cc, cd = st.columns([1.8, 2.2, 2, 1.8])

        leading_r   = tf_det.get(leading_tf, {})
        cross_price = leading_r.get("cross_price")
        entry_str   = f"USD {cross_price:.2f}" if cross_price else f"USD {price:.2f}"

        stoch_col = "#22c55e" if sig.get("stoch_ok") else "#f59e0b"
        stoch_str = f"{stoch:.1f}" if stoch is not None else "–"
        vol_str   = f"{vol_ratio:.1f}× Ø" if vol_ratio else "–"
        vol_col   = "#22c55e" if (vol_ratio or 0) >= 1.5 else ("#f59e0b" if (vol_ratio or 0) >= 1.0 else "#ef4444")

        # ── Spalte A: Ticker + STI Score + Einstieg ───────────────────────────
        with ca:
            st.html(
                f"<div style='background:#111;border:1px solid #1e1e1e;border-radius:10px;"
                f"padding:14px;border-top:3px solid {dir_color};height:100%'>"
                f"<div style='font-size:1.3rem;font-weight:900;color:{dir_color};"
                f"font-family:sans-serif;margin-bottom:2px'>{dir_icon} {ticker}</div>"
                f"<div style='font-size:0.78rem;color:#666;font-family:sans-serif;"
                f"margin-bottom:10px'>{dir_label}</div>"
                + _score_breakdown_html(tf_det, score, sig_dir) +
                f"<div style='background:#0e0e0e;border-radius:6px;padding:8px 10px;"
                f"margin-top:10px'>"
                f"<div style='font-size:0.6rem;color:#555;font-family:sans-serif;"
                f"text-transform:uppercase;letter-spacing:0.06em;margin-bottom:3px'>"
                f"Einstieg (Schlusskurs Signalkerze)</div>"
                f"<div style='font-size:1.05rem;font-weight:700;color:#d4a843;"
                f"font-family:monospace'>{entry_str}</div>"
                f"<div style='font-size:0.68rem;color:#555;font-family:sans-serif;margin-top:2px'>"
                f"{_TF_LABELS.get(leading_tf,'')} Kerze · kein SL/TP</div>"
                f"</div>"
                + (f"<div style='margin-top:8px;background:#2a1505;border:1px solid #f97316;"
                   f"border-radius:6px;padding:5px 10px;font-size:0.72rem;color:#f97316;"
                   f"font-family:sans-serif'>{market_warning}</div>" if market_warning else "")
                + f"</div>"
            )

        # ── Spalte B: Widerstände & Unterstützungen mit IV-Zielzonen ─────────
        with cb:
            st.html(_sr_html(
                ticker, price, sig_dir,
                iv=rec.get("iv"),
                dte=rec.get("dte"),
                strike=rec.get("strike"),
                premium=rec.get("premium"),
            ))

        # ── Spalte C: Options-Empfehlung ──────────────────────────────────────
        with cc:
            if premium and strike and expiry:
                earn_warn = rec.get("earnings_warning")
                trend_ok  = leading_r.get("direction", 0) == (1 if sig_dir == "bullish" else -1)
                trend_col = "#22c55e" if trend_ok else "#ef4444"
                trend_txt = (
                    f"STI {sig_dir} auf {_TF_LABELS.get(leading_tf,'')} ✅ Trend intakt"
                    if trend_ok else "⚠️ STI hat sich umgekehrt — Exit prüfen!"
                )

                primary_html = (
                    f"<div style='background:#0c0c0c;border:2px solid {dir_color};"
                    f"border-radius:10px;padding:14px;height:100%'>"
                    f"<div style='font-size:0.62rem;color:#555;text-transform:uppercase;"
                    f"letter-spacing:0.1em;font-family:sans-serif;margin-bottom:6px'>"
                    f"Empfohlene Option</div>"
                    f"<div style='font-size:1.5rem;font-weight:900;color:{dir_color};"
                    f"font-family:sans-serif'>{opt_type} @{strike:.0f}</div>"
                    f"<div style='font-size:0.85rem;color:#aaa;font-family:sans-serif'>"
                    f"Verfall {datetime.strptime(expiry,'%Y-%m-%d').strftime('%d.%m.%Y')} · {dte} Tage</div>"
                    f"<div style='margin-top:10px;display:grid;grid-template-columns:1fr 1fr;gap:6px'>"
                    f"<div style='background:#0e0e0e;border-radius:6px;padding:6px 10px'>"
                    f"<div style='font-size:0.6rem;color:#555;font-family:sans-serif'>"
                    f"Prämie (max. Verlust)</div>"
                    f"<div style='font-size:1.1rem;font-weight:700;color:#f0f0f0;font-family:sans-serif'>"
                    f"USD {premium:.2f}</div></div>"
                    f"<div style='background:#0e0e0e;border-radius:6px;padding:6px 10px'>"
                    f"<div style='font-size:0.6rem;color:#555;font-family:sans-serif'>"
                    f"IV / Hist.Vol (20T)</div>"
                    f"<div style='font-size:0.85rem;font-weight:600;color:#aaa;font-family:sans-serif'>"
                    f"{rec.get('iv','–')}% / {rec.get('hist_vol_20','–')}%</div></div>"
                    f"</div>"
                    f"<div style='margin-top:10px;background:#0c1a0c;border:1px solid #1a3a1a;"
                    f"border-radius:6px;padding:8px 10px'>"
                    f"<div style='font-size:0.6rem;color:#555;font-family:sans-serif;"
                    f"text-transform:uppercase;letter-spacing:0.06em;margin-bottom:3px'>"
                    f"Exit-Bedingung</div>"
                    f"<div style='font-size:0.78rem;color:{trend_col};font-family:sans-serif'>"
                    f"{trend_txt}</div>"
                    f"<div style='font-size:0.72rem;color:#555;font-family:sans-serif;margin-top:3px'>"
                    f"Halten solange STI-Trend intakt. Kein fester Take-Profit.</div>"
                    f"</div>"
                    f"<div style='margin-top:8px;display:flex;gap:6px;flex-wrap:wrap'>"
                    + _iv_badge(iv_rating) + _liq_badge(liquidity) +
                    f"</div>"
                    + (f"<div style='margin-top:8px;background:#3a0a0a;border:1px solid #ef4444;"
                       f"border-radius:6px;padding:5px 10px;font-size:0.72rem;color:#fca5a5;"
                       f"font-family:sans-serif'>⚠️ Earnings {rec.get('earnings')} — IV-Risiko!</div>"
                       if earn_warn else "")
                    + f"</div>"
                )

                spread_html = ""
                if spread_alt:
                    s = spread_alt
                    spread_html = (
                        f"<div style='margin-top:8px;background:#111;border:1px solid #f97316;"
                        f"border-radius:8px;padding:10px 12px'>"
                        f"<div style='font-size:0.62rem;color:#f97316;text-transform:uppercase;"
                        f"font-family:sans-serif;margin-bottom:4px'>"
                        f"📊 Alternative: {s['name']} (IV erhöht)</div>"
                        f"<div style='font-size:0.82rem;color:#aaa;font-family:sans-serif'>"
                        f"Kauf @{s['buy_strike']:.0f} · Verkauf @{s['sell_strike']:.0f} · "
                        f"Netto-Debit: <b style='color:#f0f0f0'>USD {s['net_debit']:.2f}</b> · "
                        f"Max Gewinn: <b style='color:#22c55e'>USD {s['max_profit']:.2f}</b></div>"
                        f"</div>"
                    )

                st.html(primary_html + spread_html)
            else:
                st.html(
                    f"<div style='background:#111;border:1px solid #1e1e1e;border-radius:10px;"
                    f"padding:14px;height:100%'>"
                    f"<div style='color:#555;font-size:0.82rem;font-family:sans-serif'>"
                    f"Keine Options-Daten — Ticker in TradingView prüfen.</div></div>"
                )

        # ── Spalte D: Stoch + Volumen + Backtest + Einstiegs-Hinweis ──────────
        with cd:
            bt_html = ""
            if show_backtest and is_now:
                bt = backtest_setup(ticker, leading_tf, sig_dir)
                bt_html = _backtest_html(bt, sig_dir, bt.get("forward_days", 10))

            entry_hint = (
                f"<div style='margin-top:8px;background:#1a1205;border:1px solid #3a2a05;"
                f"border-left:3px solid #d4a843;border-radius:6px;padding:8px 10px;"
                f"font-size:0.75rem;color:#d4a843;font-family:sans-serif'>"
                f"📌 <b>Einstieg:</b> Signalkerze geschlossen, dann kaufen.<br>"
                f"<span style='color:#888;font-size:0.68rem'>Exit: STI-Cross Gegenteil auf "
                f"{_TF_LABELS.get(leading_tf,'')}.</span></div>"
            )

            st.html(
                f"<div style='background:#111;border:1px solid #1e1e1e;border-radius:10px;"
                f"padding:14px;height:100%'>"
                f"<div style='font-size:0.6rem;color:#555;text-transform:uppercase;"
                f"letter-spacing:0.06em;font-family:sans-serif;margin-bottom:6px'>"
                f"Qualitäts-Filter</div>"
                f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:5px;margin-bottom:8px'>"
                f"<div style='background:#0e0e0e;border-radius:5px;padding:6px 8px'>"
                f"<div style='font-size:0.58rem;color:#555;font-family:sans-serif;margin-bottom:2px'>"
                f"Stoch. (14,3,3)</div>"
                f"<div style='font-size:0.95rem;font-weight:700;color:{stoch_col};"
                f"font-family:sans-serif'>{stoch_str}</div>"
                f"<div style='font-size:0.58rem;color:#444;font-family:sans-serif'>"
                f"{'OK ✓' if sig.get('stoch_ok') else 'Extrem'}</div></div>"
                f"<div style='background:#0e0e0e;border-radius:5px;padding:6px 8px'>"
                f"<div style='font-size:0.58rem;color:#555;font-family:sans-serif;margin-bottom:2px'>"
                f"Volumen</div>"
                f"<div style='font-size:0.95rem;font-weight:700;color:{vol_col};"
                f"font-family:sans-serif'>{vol_str}</div>"
                f"<div style='font-size:0.58rem;color:#444;font-family:sans-serif'>"
                f"{'stark ✓' if (vol_ratio or 0) >= 1.5 else 'ok' if (vol_ratio or 0) >= 1.0 else 'schwach'}"
                f"</div></div>"
                f"</div>"
                + bt_html
                + entry_hint
                + f"</div>"
            )


def _render_approaching_card(sig: Dict) -> None:
    """Kompakte GET READY Karte."""
    ticker  = sig["ticker"]
    price   = sig["price"]
    score   = sig["score"]
    sig_dir = sig["signal_dir"]
    tf      = sig["leading_tf"]
    gap_pct = sig.get("gap_pct", 0)
    stoch   = sig.get("stoch")

    dir_color = "#22c55e" if sig_dir == "bullish" else "#ef4444"
    opt_type  = "CALL" if sig_dir == "bullish" else "PUT"

    # Gap-Fortschrittsbalken: wie nah ist der Cross?
    closeness = max(0, min(100, 100 - gap_pct * 20))  # 0%=weit, 100%=direkt am Cross
    bar_w     = int(closeness)
    bar_col   = "#22c55e" if closeness > 70 else "#f59e0b" if closeness > 40 else "#60a5fa"

    stoch_str = f"Stoch {stoch:.0f}" if stoch else ""

    st.html(
        f"<div style='background:#0e0e12;border:1px solid #2a2a3a;border-radius:10px;"
        f"padding:12px 16px;border-left:4px solid {dir_color}66'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;"
        f"margin-bottom:6px'>"
        f"<div>"
        f"<span style='font-size:1.0rem;font-weight:700;color:{dir_color};"
        f"font-family:sans-serif'>{ticker}</span>&nbsp;"
        f"<span style='font-size:0.75rem;color:#666;font-family:sans-serif'>"
        f"USD {price:.2f}</span>"
        f"</div>"
        f"<div style='display:flex;gap:6px;align-items:center'>"
        f"<span style='font-size:0.72rem;color:{dir_color};font-family:sans-serif;font-weight:700'>"
        f"{opt_type} wird vorbereitet</span>"
        f"<span style='font-size:0.72rem;color:#555;font-family:sans-serif'>"
        f"Pot. Score {'+' if score > 0 else ''}{score}/6</span>"
        f"</div></div>"
        f"<div style='font-size:0.72rem;color:#666;font-family:sans-serif;margin-bottom:6px'>"
        f"STI Fast nähert sich STI Slow auf {_TF_LABELS.get(tf,tf)} · "
        f"Abstand {gap_pct:.2f}% · {stoch_str}</div>"
        f"<div style='background:#1a1a1a;border-radius:4px;height:6px;overflow:hidden'>"
        f"<div style='width:{bar_w}%;height:100%;background:{bar_col};"
        f"border-radius:4px;transition:width 0.3s'></div></div>"
        f"<div style='display:flex;justify-content:space-between;margin-top:3px'>"
        f"<span style='font-size:0.62rem;color:#333;font-family:sans-serif'>weit</span>"
        f"<span style='font-size:0.62rem;color:{bar_col};font-family:sans-serif'>"
        f"Nähe zum Cross: {closeness:.0f}%</span>"
        f"<span style='font-size:0.62rem;color:#333;font-family:sans-serif'>Cross!</span>"
        f"</div></div>"
    )

# ══════════════════════════════════════════════════════════════════════════════
# SEITE
# ══════════════════════════════════════════════════════════════════════════════

col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.html(get_logo_html("white", 40))
with col_title:
    st.html(
        "<div style='padding-top:4px'>"
        "<div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.8rem;"
        "color:#f0f0f0;letter-spacing:0.04em'>TREND SIGNALE</div>"
        "<div style='font-family:RedRose,sans-serif;font-weight:300;font-size:0.8rem;"
        "color:#666;text-transform:uppercase;letter-spacing:0.12em;margin-top:2px'>"
        "Stillhalter Trend Indikator (STI) · Multi-Timeframe · NOW: Signal gerade passiert · "
        "GET READY: Signal steht bevor"
        "</div></div>"
    )

st.html('<div class="gold-line"></div>')

# ── Markt-Regime ──────────────────────────────────────────────────────────────
with st.spinner("Markt-Regime prüfen…"):
    regime = _market_regime()

spy = regime.get("SPY", {})
qqq = regime.get("QQQ", {})

def _regime_badge(name, data):
    r = data.get("regime", "neutral")
    c = "#22c55e" if r == "bullish" else "#ef4444" if r == "bearish" else "#888"
    d = "▲" if data.get("daily",  0) > 0 else "▼"
    w = "▲" if data.get("weekly", 0) > 0 else "▼"
    p = f"USD {data['price']:.2f}" if data.get("price") else ""
    return (
        f"<div style='background:#0e0e0e;border:1px solid #1e1e1e;border-radius:8px;"
        f"padding:8px 14px;display:inline-flex;align-items:center;gap:10px'>"
        f"<span style='font-weight:700;color:#aaa;font-family:sans-serif'>{name}</span>"
        f"<span style='font-size:0.9rem;color:#666;font-family:sans-serif'>{p}</span>"
        f"<span style='color:{c};font-weight:700;font-family:sans-serif'>{r.upper()}</span>"
        f"<span style='font-size:0.75rem;color:#555;font-family:sans-serif'>D:{d} W:{w}</span>"
        f"</div>"
    )

st.html(
    "<div style='display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap'>"
    "<div style='font-size:0.72rem;color:#555;font-family:sans-serif;"
    "align-self:center;text-transform:uppercase;letter-spacing:0.08em'>Markt-Regime:</div>"
    + _regime_badge("SPY", spy)
    + _regime_badge("QQQ", qqq)
    + "</div>"
)

# ── Steuerung ─────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns([3, 2, 2, 2])
with c1:
    universe_choice = st.selectbox(
        "Universum",
        ["Watchlist (Stillhalter AI App)", "Nasdaq 100 (101)", "S&P 500 (~400)", "Alle kombiniert"],
        key="ts_universe",
    )
with c2:
    dir_filter = st.selectbox(
        "Richtung",
        ["Beide", "Nur Bullish (Calls)", "Nur Bearish (Puts)"],
        key="ts_dir",
    )
with c3:
    score_min = st.selectbox(
        "Mindest-Score",
        options=[4, 5, 6],
        index=0,
        format_func=lambda x: f"Score ≥ {x}/6{'  🔥' if x == 6 else '  ✅' if x == 5 else ''}",
        key="ts_score_min",
        help="Filtert Signale nach STI-Gesamtscore. 6/6 = alle Timeframes aligned.",
    )
with c4:
    show_bt = st.checkbox("Backtest anzeigen", value=True, key="ts_backtest",
                          help="Historische Win-Rate aus vergleichbaren STI-Setups")

# ── STI & Score Erklärung ──────────────────────────────────────────────────────
with st.expander("❓  Was ist der STI-Score? · Wie funktioniert das System?", expanded=False):
    st.html("""
<div style='font-family:sans-serif;color:#ccc;line-height:1.6;padding:4px'>

<div style='font-size:0.85rem;font-weight:700;color:#d4a843;margin-bottom:8px'>
    🔍 Was ist der Stillhalter Trend Indikator (STI)?
</div>
<p style='font-size:0.8rem;color:#aaa;margin-bottom:12px'>
    Der STI besteht aus zwei proprietären Trendlinien:
    <b style='color:#f0f0f0'>STI Fast</b> reagiert sehr schnell auf Kursänderungen,
    <b style='color:#f0f0f0'>STI Slow</b> glättet den übergeordneten Trend.
    Wenn die schnelle Linie die langsame kreuzt, entsteht ein Trendwechsel-Signal.
</p>

<div style='font-size:0.85rem;font-weight:700;color:#d4a843;margin-bottom:8px'>
    📊 Wie wird der Score berechnet?
</div>
<div style='background:#0e0e0e;border-radius:8px;padding:12px;margin-bottom:12px;font-size:0.78rem'>
    <div style='display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr;gap:4px;
                font-weight:700;color:#555;margin-bottom:6px;text-transform:uppercase;font-size:0.65rem'>
        <span>Zeitrahmen</span><span>Gewicht</span><span>Bullish</span>
        <span>Bearish</span><span>Signal</span>
    </div>
    <div style='display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr;gap:4px;margin-bottom:3px'>
        <span style='color:#a855f7'>📅 Monat</span><span style='color:#888'>× 2</span>
        <span style='color:#22c55e'>+2</span><span style='color:#ef4444'>−2</span>
        <span style='color:#666;font-size:0.7rem'>Stärkster Trend</span>
    </div>
    <div style='display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr;gap:4px;margin-bottom:3px'>
        <span style='color:#3b82f6'>📅 Woche</span><span style='color:#888'>× 2</span>
        <span style='color:#22c55e'>+2</span><span style='color:#ef4444'>−2</span>
        <span style='color:#666;font-size:0.7rem'>Mittelfristiger Trend</span>
    </div>
    <div style='display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr;gap:4px;margin-bottom:3px'>
        <span style='color:#10b981'>📅 Tag</span><span style='color:#888'>× 1</span>
        <span style='color:#22c55e'>+1</span><span style='color:#ef4444'>−1</span>
        <span style='color:#666;font-size:0.7rem'>Kurz-/Mittelfristig</span>
    </div>
    <div style='display:grid;grid-template-columns:1fr 1fr 1fr 1fr 1fr;gap:4px'>
        <span style='color:#f59e0b'>⏱ 4H</span><span style='color:#888'>× 1</span>
        <span style='color:#22c55e'>+1</span><span style='color:#ef4444'>−1</span>
        <span style='color:#666;font-size:0.7rem'>Kurzfristiger Trigger</span>
    </div>
    <div style='border-top:1px solid #222;margin-top:8px;padding-top:6px;
                display:flex;justify-content:space-between'>
        <span style='color:#555'>Maximum:</span>
        <span><b style='color:#22c55e'>+6 (100% bullish)</b> &nbsp;bis&nbsp;
        <b style='color:#ef4444'>−6 (100% bearish)</b></span>
    </div>
</div>

<div style='font-size:0.85rem;font-weight:700;color:#d4a843;margin-bottom:8px'>
    🎯 Was bedeuten die Signal-Typen?
</div>
<div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;font-size:0.78rem;margin-bottom:12px'>
    <div style='background:#0a140a;border:1px solid #1a3a1a;border-radius:6px;padding:8px 10px'>
        <div style='color:#22c55e;font-weight:700;margin-bottom:4px'>🎯 NOW</div>
        <div style='color:#888'>STI-Cross passierte in der <b style='color:#aaa'>letzten
        geschlossenen Kerze</b> des führenden Timeframes. Jetzt handeln.</div>
    </div>
    <div style='background:#0e0e14;border:1px solid #2a2a4a;border-radius:6px;padding:8px 10px'>
        <div style='color:#60a5fa;font-weight:700;margin-bottom:4px'>⏳ GET READY</div>
        <div style='color:#888'>Monat + Woche aligned, aber Daily/4H noch nicht gekreuzt.
        STI Fast nähert sich STI Slow — Cross steht bevor.</div>
    </div>
</div>

<div style='font-size:0.85rem;font-weight:700;color:#d4a843;margin-bottom:8px'>
    📈 Weitere angezeigte Indikatoren
</div>
<div style='font-size:0.78rem;color:#888;display:grid;grid-template-columns:1fr 1fr;gap:6px'>
    <div>
        <b style='color:#aaa'>Stochastik (14,3,3)</b><br>
        Misst ob die Aktie überkauft (&gt;82) oder überverkauft (&lt;18) ist.
        Grün = günstiger Einstiegsbereich für die Signalrichtung.
    </div>
    <div>
        <b style='color:#aaa'>Volumen-Ratio</b><br>
        Aktuelles Volumen ÷ 20-Tage-Durchschnitt.
        Hohe Bestätigung ≥ 1.5× zeigt starke Marktbeteiligung am Signal.
    </div>
    <div>
        <b style='color:#aaa'>IV / Hist. Vol (20T)</b><br>
        Implizite Volatilität vs. historische Volatilität.
        Günstig wenn IV/HV &lt; 1.1 (Option preiswert), teuer wenn &gt; 1.8.
    </div>
    <div>
        <b style='color:#aaa'>Widerstände &amp; Unterstützungen</b><br>
        Swing-Highs/-Lows aus dem 1-Jahres-Chart (5-Kerzen-Fenster, geclustert).
        Nächster Widerstand = Zielzone für Calls, nächste Unterstützung = Zielzone für Puts.
    </div>
</div>

</div>
""")

if universe_choice.startswith("Watchlist"):
    tickers_to_scan = list(dict.fromkeys(ALL_TICKERS))
elif universe_choice.startswith("Nasdaq"):
    tickers_to_scan = get_universe_tickers("Nasdaq 100")
elif universe_choice.startswith("S&P"):
    tickers_to_scan = get_universe_tickers("S&P 500")
else:
    tickers_to_scan = list(dict.fromkeys(
        ALL_TICKERS + get_universe_tickers("Nasdaq 100") + get_universe_tickers("S&P 500")
    ))

# ── Scan-Button + Cache ───────────────────────────────────────────────────────
col_btn1, col_btn2, col_info = st.columns([2, 2, 8])
with col_btn1:
    run_btn = st.button("🎯 Scan starten", type="primary", use_container_width=True)
with col_btn2:
    if st.button("🔄 Cache leeren", use_container_width=True):
        if os.path.exists(SIGNAL_CACHE_PATH):
            os.remove(SIGNAL_CACHE_PATH)
        st.rerun()

cached_now      = []
cached_ready    = []
cache_ts        = None

if os.path.exists(SIGNAL_CACHE_PATH):
    try:
        with open(SIGNAL_CACHE_PATH, "rb") as f:
            cached = pickle.load(f)
        if cached.get("universe") == universe_choice:
            cached_now   = cached.get("now_signals",   [])
            cached_ready = cached.get("approaching",   [])
            cache_ts     = cached.get("timestamp")
    except Exception:
        pass

if cache_ts:
    age_min = int((datetime.now() - cache_ts).total_seconds() / 60)
    with col_info:
        st.html(
            f"<div style='font-size:0.75rem;color:#555;font-family:sans-serif;padding-top:8px'>"
            f"💾 Cache {cache_ts.strftime('%d.%m. %H:%M')} · {age_min} min alt · "
            f"{len(cached_now)} NOW · {len(cached_ready)} GET READY</div>"
        )

if run_btn:
    prog = st.progress(0.0)
    stat = st.empty()
    stat.markdown(f"Scanne **{len(tickers_to_scan)} Ticker**…")

    now_signals, approaching = run_scan(tickers_to_scan, progress_cb=lambda p: prog.progress(p))

    prog.empty()
    stat.markdown(
        f"✅ **{len(now_signals)} NOW-Signale** · **{len(approaching)} GET READY**"
    )

    try:
        with open(SIGNAL_CACHE_PATH, "wb") as f:
            pickle.dump({
                "now_signals": now_signals, "approaching": approaching,
                "timestamp": datetime.now(), "universe": universe_choice,
            }, f)
    except Exception:
        pass

    cached_now   = now_signals
    cached_ready = approaching

# ── Richtungs- & Score-Filter ─────────────────────────────────────────────────
def _apply_filters(signals: List[Dict]) -> List[Dict]:
    result = signals
    # Richtungsfilter
    if dir_filter == "Nur Bullish (Calls)":
        result = [s for s in result if s["signal_dir"] == "bullish"]
    elif dir_filter == "Nur Bearish (Puts)":
        result = [s for s in result if s["signal_dir"] == "bearish"]
    # Score-Filter
    result = [s for s in result if abs(s.get("score", 0)) >= score_min]
    return result

now_display   = _apply_filters(cached_now)
ready_display = _apply_filters(cached_ready)

# ══════════════════════════════════════════════════════════════════════════════
# GET READY SEKTION
# ══════════════════════════════════════════════════════════════════════════════

if ready_display:
    st.html(
        "<div style='background:#0e0e14;border:1px solid #2a2a4a;border-radius:12px;"
        "padding:14px 18px;margin-bottom:16px'>"
        "<div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.1rem;"
        "color:#60a5fa;letter-spacing:0.04em;margin-bottom:4px'>"
        "⏳ GET READY — Einstieg steht bevor</div>"
        "<div style='font-size:0.78rem;color:#555;font-family:sans-serif'>"
        "STI Fast nähert sich STI Slow — höhere Timeframes bereits ausgerichtet. "
        "Bereit halten für das Signal."
        "</div></div>"
    )
    cols = st.columns(min(3, len(ready_display)))
    for i, sig in enumerate(ready_display[:9]):
        with cols[i % 3]:
            _render_approaching_card(sig)
    st.markdown("---")

# ══════════════════════════════════════════════════════════════════════════════
# NOW SEKTION
# ══════════════════════════════════════════════════════════════════════════════

if now_display:
    bull = sum(1 for s in now_display if s["signal_dir"] == "bullish")
    bear = sum(1 for s in now_display if s["signal_dir"] == "bearish")

    st.html(
        "<div style='background:#0a140a;border:1px solid #1a3a1a;border-radius:12px;"
        "padding:14px 18px;margin-bottom:16px'>"
        "<div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.1rem;"
        "color:#22c55e;letter-spacing:0.04em;margin-bottom:4px'>"
        f"🎯 NOW — {len(now_display)} Signale (STI-Cross letzte Kerze)</div>"
        "<div style='font-size:0.78rem;color:#555;font-family:sans-serif'>"
        "Nur Signale wo der STI-Cross in der LETZTEN geschlossenen Kerze stattfand. "
        "Jetzt handeln oder Schlusskurs der Signalkerze abwarten."
        "</div></div>"
    )

    km = st.columns(4)
    km[0].metric("NOW Signale",     len(now_display))
    km[1].metric("📈 Calls",        bull)
    km[2].metric("📉 Puts",         bear)
    km[3].metric("Universum",       f"{len(tickers_to_scan)} Ticker")

    st.html(
        "<div style='background:#1a1205;border:1px solid #3a2a05;border-left:4px solid #d4a843;"
        "border-radius:8px;padding:10px 16px;font-family:sans-serif;font-size:0.8rem;"
        "color:#888;margin:12px 0'>"
        "📌 <b style='color:#d4a843'>Einstieg:</b> Signalkerze muss geschlossen sein. "
        "Dann Option kaufen. Position max. <b>1–2% des Portfolios</b> (Prämie = max. Verlust). "
        "<b>Kein fester Take-Profit</b> — Exit nur wenn STI auf Signal-Timeframe in Gegenrichtung kreuzt."
        "</div>"
    )

    for sig in now_display:
        _render_signal_card(sig, regime, show_backtest=show_bt)

elif run_btn or (cached_now is not None and cache_ts):
    st.html(
        "<div style='background:#0e0e0e;border:1px solid #1e1e1e;border-radius:10px;"
        "padding:40px;text-align:center;font-family:sans-serif'>"
        "<div style='font-size:1.5rem;margin-bottom:8px'>🎯</div>"
        "<div style='color:#888;font-size:0.9rem'>"
        "Heute kein frischer STI-Cross auf allen Timeframes — das ist gut. "
        "Das System wartet auf den präzisen Einstiegsmoment.<br>"
        "GET READY zeigt wo der Cross sich nähert.</div>"
        "</div>"
    )
else:
    st.html(
        "<div style='background:#0e0e0e;border:1px solid #1e1e1e;border-radius:10px;"
        "padding:40px;text-align:center;font-family:sans-serif'>"
        "<div style='font-size:2rem;margin-bottom:8px'>🎯</div>"
        "<div style='color:#888;font-size:0.9rem'>Universum wählen und "
        "<b>'Scan starten'</b> klicken.</div>"
        "</div>"
    )
