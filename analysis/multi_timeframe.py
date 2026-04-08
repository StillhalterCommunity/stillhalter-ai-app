"""
Multi-Timeframe Technische Analyse.
Timeframes: 4H · 1D · 1W
Indikatoren: RSI, Stochastik, MACD, Stillhalter Trend Model
Erkennt: Crossovers, Level-Breaks, Trend-Alignment
"""

import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st
from dataclasses import dataclass, field
from typing import Optional, List, Dict


# ── Stillhalter Trend Model — Modi ────────────────────────────────────────────
TREND_MODES = {
    "Very Tight":  (2,  9),
    "Tight":       (4,  16),
    "Loose":       (6,  28),
    "Very Loose":  (13, 35),
}
DEFAULT_TREND_MODE = "Very Tight"


# ── Indicator Calculations ─────────────────────────────────────────────────────

def calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calc_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=1).mean()


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))


def calc_stoch(high: pd.Series, low: pd.Series, close: pd.Series,
               k_period: int = 14, smooth_k: int = 3, d_period: int = 3):
    ll = low.rolling(k_period).min()
    hh = high.rolling(k_period).max()
    stoch_raw = 100 * (close - ll) / (hh - ll + 1e-10)
    k = stoch_raw.rolling(smooth_k).mean()
    d = k.rolling(d_period).mean()
    return k, d


def calc_macd(close: pd.Series, fast: int = 10, slow: int = 35, signal: int = 5):
    """Stillhalter MACD Pro Parameter: 10/35/5 (statt Standard 12/26/9)."""
    ema_fast = calc_ema(close, fast)
    ema_slow = calc_ema(close, slow)
    macd = ema_fast - ema_slow
    sig  = calc_ema(macd, signal)
    hist = macd - sig
    return macd, sig, hist


# ── Crossover Detection ────────────────────────────────────────────────────────

def crossed_above(series: pd.Series, level: float, lookback: int = 5) -> bool:
    """
    Series hat 'level' in letzten 'lookback' Kerzen von unten gekreuzt.
    U9: lookback auf 5 erhöht für stabilere Signale.
    Zusätzlich: %K muss auch über %D liegen (Bestätigung).
    """
    if len(series) < lookback + 1:
        return False
    s = series.dropna().iloc[-(lookback + 1):]
    for i in range(len(s) - 1):
        if s.iloc[i] < level <= s.iloc[i + 1]:
            return True
    return False


def crossed_below(series: pd.Series, level: float, lookback: int = 5) -> bool:
    """Series hat 'level' in letzten 'lookback' Kerzen von oben gekreuzt."""
    if len(series) < lookback + 1:
        return False
    s = series.dropna().iloc[-(lookback + 1):]
    for i in range(len(s) - 1):
        if s.iloc[i] > level >= s.iloc[i + 1]:
            return True
    return False


def stoch_cross_above_with_confirm(
    stoch_k: pd.Series, stoch_d: pd.Series,
    level: float = 20.0, lookback: int = 5
) -> bool:
    """
    U9: Stochastik kreuzt 'level' aufwärts UND %K > %D (Bestätigung).
    Verhindert Fehlsignale wenn %K wieder sofort fällt.
    """
    basic = crossed_above(stoch_k, level, lookback)
    if not basic:
        return False
    # Bestätigung: aktuell %K > %D
    try:
        return float(stoch_k.dropna().iloc[-1]) > float(stoch_d.dropna().iloc[-1])
    except Exception:
        return basic


def stoch_cross_below_with_confirm(
    stoch_k: pd.Series, stoch_d: pd.Series,
    level: float = 80.0, lookback: int = 5
) -> bool:
    """U9: Stochastik kreuzt 'level' abwärts UND %K < %D (Bestätigung)."""
    basic = crossed_below(stoch_k, level, lookback)
    if not basic:
        return False
    try:
        return float(stoch_k.dropna().iloc[-1]) < float(stoch_d.dropna().iloc[-1])
    except Exception:
        return basic


def line_crossed_above(series_a: pd.Series, series_b: pd.Series, lookback: int = 5) -> bool:
    """Series A hat Series B von unten gekreuzt (bullishes Cross)."""
    if len(series_a) < lookback + 1 or len(series_b) < lookback + 1:
        return False
    a = series_a.dropna().reset_index(drop=True)
    b = series_b.dropna().reset_index(drop=True)
    min_len = min(len(a), len(b), lookback + 1)
    a = a.iloc[-min_len:]
    b = b.iloc[-min_len:]
    for i in range(len(a) - 1):
        if a.iloc[i] <= b.iloc[i] and a.iloc[i + 1] > b.iloc[i + 1]:
            return True
    return False


def line_crossed_below(series_a: pd.Series, series_b: pd.Series, lookback: int = 5) -> bool:
    """Series A hat Series B von oben gekreuzt (bearishes Cross)."""
    if len(series_a) < lookback + 1 or len(series_b) < lookback + 1:
        return False
    a = series_a.dropna().reset_index(drop=True)
    b = series_b.dropna().reset_index(drop=True)
    min_len = min(len(a), len(b), lookback + 1)
    a = a.iloc[-min_len:]
    b = b.iloc[-min_len:]
    for i in range(len(a) - 1):
        if a.iloc[i] >= b.iloc[i] and a.iloc[i + 1] < b.iloc[i + 1]:
            return True
    return False


# ── Single Timeframe Signal ────────────────────────────────────────────────────

@dataclass
class TFSignal:
    timeframe: str          # "4H" | "1D" | "1W"

    # RSI
    rsi: float = 0.0
    rsi_bullish: bool = False        # RSI > 50
    rsi_bearish: bool = False        # RSI < 50
    rsi_cross_30_up: bool = False    # kreuzt 30 aufwärts
    rsi_cross_70_down: bool = False  # kreuzt 70 abwärts
    rsi_oversold: bool = False       # < 30
    rsi_overbought: bool = False     # > 70

    # Schnelle Stochastik (14,3,3) — Primärsignal
    stoch_k: float = 0.0
    stoch_d: float = 0.0
    stoch_bullish: bool = False
    stoch_bearish: bool = False
    stoch_cross_20_up: bool = False
    stoch_cross_80_down: bool = False
    stoch_oversold: bool = False
    stoch_overbought: bool = False
    stoch_ready_buy: bool = False     # %K < 20 UND %K kreuzt %D aufwärts (stärkstes Signal)
    stoch_ready_sell: bool = False    # %K > 80 UND %K kreuzt %D abwärts

    # Langsame Stochastik (35,10,5) — Bestätigung
    stoch_slow_k: float = 0.0
    stoch_slow_d: float = 0.0
    stoch_slow_oversold: bool = False
    stoch_slow_overbought: bool = False
    stoch_slow_ready_buy: bool = False
    stoch_slow_ready_sell: bool = False

    # Dual-Bestätigung
    stoch_both_oversold: bool = False   # Beide überverkauft → stärkstes Kaufsignal
    stoch_both_overbought: bool = False # Beide überkauft → stärkstes Verkaufssignal

    # MACD
    macd_val: float = 0.0
    macd_sig: float = 0.0
    macd_hist: float = 0.0
    macd_bullish: bool = False        # MACD > Signal
    macd_bearish: bool = False        # MACD < Signal
    macd_cross_bullish: bool = False  # MACD kreuzt Signal aufwärts (neg→pos)
    macd_cross_bearish: bool = False  # MACD kreuzt Signal abwärts (pos→neg)
    macd_above_zero: bool = False     # MACD Linie > 0

    # Stillhalter Trend Model (interne Feldnamen bleiben ema_* für Kompatibilität)
    ema2: float = 0.0
    ema9: float = 0.0
    ema_bullish: bool = False         # SC Trend bullish (FastEMA > SlowEMA)
    ema_bearish: bool = False         # SC Trend bearish (FastEMA < SlowEMA)
    ema_cross_bullish: bool = False   # Kaufsignal (Cross aufwärts)
    ema_cross_bearish: bool = False   # Verkaufssignal (Cross abwärts)

    # Gesamt-Richtung
    direction: str = "neutral"       # "bullish" | "bearish" | "neutral"
    score: float = 0.0               # 0-100


@dataclass
class MultiTFResult:
    ticker: str
    tf_4h: Optional[TFSignal] = None
    tf_1d: Optional[TFSignal] = None
    tf_1w: Optional[TFSignal] = None
    tf_1m: Optional[TFSignal] = None   # Monatsebene (Stillhalter Trend Model)

    # Alignment (4H · 1D · 1W)
    alignment_score: float = 0.0     # 0-100: wie gut stimmen alle TFs überein
    alignment_direction: str = "neutral"
    aligned_bullish: bool = False    # Alle 3 TFs bullish
    aligned_bearish: bool = False    # Alle 3 TFs bearish
    partially_aligned: bool = False  # Mind. 2/3 TFs gleiche Richtung

    # Stillhalter Trend Model — Trendstärke (alle 4 Timeframes)
    # Anzahl Timeframes mit aktivem Aufwärtstrend (0-4)
    ema_bull_count: int = 0
    ema_bear_count: int = 0
    ema_trend_label: str = "Neutral"   # "Stark Aufwärts" | "Aufwärts" | "Neutral" | "Abwärts" | "Stark Abwärts"
    ema_trend_pct: float = 0.0         # 0-100 für Progress-Bar

    # Crossover-Bestätigungen (mind. 2 TFs zeigen dasselbe Signal)
    confirmed_rsi_oversold: bool = False
    confirmed_stoch_cross_up: bool = False
    confirmed_macd_bullish_cross: bool = False
    confirmed_ema_bullish: bool = False

    confirmed_rsi_overbought: bool = False
    confirmed_stoch_cross_down: bool = False
    confirmed_macd_bearish_cross: bool = False
    confirmed_ema_bearish: bool = False

    error: str = ""


# ── Data Fetching ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_tf_data(ticker: str, interval: str, period: str) -> pd.DataFrame:
    """Holt OHLCV für einen Ticker auf einem Timeframe."""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval=interval)
        if df.empty:
            return pd.DataFrame()
        return df[["Open", "High", "Low", "Close", "Volume"]].copy()
    except Exception:
        return pd.DataFrame()


def _resample_to_4h(df_1h: pd.DataFrame) -> pd.DataFrame:
    """Resampled 1H-Daten auf 4H-Kerzen."""
    if df_1h.empty:
        return pd.DataFrame()
    df = df_1h.copy()
    df.index = pd.to_datetime(df.index)
    resampled = df.resample("4h").agg({
        "Open": "first", "High": "max", "Low": "min",
        "Close": "last", "Volume": "sum"
    }).dropna()
    return resampled


# ── Single TF Analysis ────────────────────────────────────────────────────────

def _analyze_tf(df: pd.DataFrame, tf_name: str, lookback: int = 3,
                fast_len: int = 2, slow_len: int = 9) -> Optional[TFSignal]:
    """Analysiert einen einzelnen Timeframe."""
    if df is None or df.empty or len(df) < 20:
        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    sig = TFSignal(timeframe=tf_name)

    # ── RSI ──────────────────────────────────────────────────────────────
    rsi = calc_rsi(close, 14)
    if len(rsi.dropna()) < 2:
        return None

    sig.rsi = float(rsi.iloc[-1])
    sig.rsi_bullish = sig.rsi > 50
    sig.rsi_bearish = sig.rsi < 50
    sig.rsi_oversold = sig.rsi < 30
    sig.rsi_overbought = sig.rsi > 70
    sig.rsi_cross_30_up = crossed_above(rsi, 30, lookback)
    sig.rsi_cross_70_down = crossed_below(rsi, 70, lookback)

    # ── Dual Stochastic (Stillhalter AI App) ───────────────────────────
    # Schnell: 14,3,3
    k, d = calc_stoch(high, low, close, k_period=14, smooth_k=3, d_period=3)
    if len(k.dropna()) < 2:
        return None

    sig.stoch_k = float(k.iloc[-1]) if not np.isnan(k.iloc[-1]) else 50.0
    sig.stoch_d = float(d.iloc[-1]) if not np.isnan(d.iloc[-1]) else 50.0
    sig.stoch_bullish    = sig.stoch_k > sig.stoch_d
    sig.stoch_bearish    = sig.stoch_k < sig.stoch_d
    sig.stoch_oversold   = sig.stoch_k < 20
    sig.stoch_overbought = sig.stoch_k > 80
    sig.stoch_cross_20_up   = stoch_cross_above_with_confirm(k, d, 20.0, lookback)
    sig.stoch_cross_80_down = stoch_cross_below_with_confirm(k, d, 80.0, lookback)
    # readyBuy: %K < 20 UND %K kreuzt %D aufwärts
    sig.stoch_ready_buy  = sig.stoch_oversold  and line_crossed_above(k, d, lookback)
    sig.stoch_ready_sell = sig.stoch_overbought and line_crossed_below(k, d, lookback)

    # Langsam: 35,10,5
    ks, ds = calc_stoch(high, low, close, k_period=35, smooth_k=10, d_period=5)
    if len(ks.dropna()) >= 2:
        sig.stoch_slow_k         = float(ks.iloc[-1]) if not np.isnan(ks.iloc[-1]) else 50.0
        sig.stoch_slow_d         = float(ds.iloc[-1]) if not np.isnan(ds.iloc[-1]) else 50.0
        sig.stoch_slow_oversold  = sig.stoch_slow_k < 20
        sig.stoch_slow_overbought= sig.stoch_slow_k > 80
        sig.stoch_slow_ready_buy = sig.stoch_slow_oversold  and line_crossed_above(ks, ds, lookback)
        sig.stoch_slow_ready_sell= sig.stoch_slow_overbought and line_crossed_below(ks, ds, lookback)

    # Dual-Bestätigung
    sig.stoch_both_oversold   = sig.stoch_oversold   and sig.stoch_slow_oversold
    sig.stoch_both_overbought = sig.stoch_overbought and sig.stoch_slow_overbought

    # ── MACD ─────────────────────────────────────────────────────────────
    macd, macd_signal, hist = calc_macd(close)
    if len(macd.dropna()) < 2:
        return None

    sig.macd_val = float(macd.iloc[-1])
    sig.macd_sig = float(macd_signal.iloc[-1])
    sig.macd_hist = float(hist.iloc[-1])
    sig.macd_bullish = sig.macd_val > sig.macd_sig
    sig.macd_bearish = sig.macd_val < sig.macd_sig
    sig.macd_above_zero = sig.macd_val > 0
    sig.macd_cross_bullish = line_crossed_above(macd, macd_signal, lookback)
    sig.macd_cross_bearish = line_crossed_below(macd, macd_signal, lookback)

    # ── Stillhalter Trend Model ──────────────────────────────────────────
    ema2 = calc_ema(close, fast_len)
    ema9 = calc_ema(close, slow_len)

    sig.ema2 = float(ema2.iloc[-1])
    sig.ema9 = float(ema9.iloc[-1])
    sig.ema_bullish = sig.ema2 > sig.ema9
    sig.ema_bearish = sig.ema2 < sig.ema9
    sig.ema_cross_bullish = line_crossed_above(ema2, ema9, lookback)
    sig.ema_cross_bearish = line_crossed_below(ema2, ema9, lookback)

    # ── Gesamt-Score ─────────────────────────────────────────────────────
    bull_pts = sum([
        sig.rsi_bullish, sig.stoch_bullish, sig.macd_bullish,
        sig.ema_bullish, sig.macd_above_zero,
    ])
    bear_pts = sum([
        sig.rsi_bearish, sig.stoch_bearish, sig.macd_bearish, sig.ema_bearish,
    ])

    score = (bull_pts / 5) * 100
    sig.score = score

    if score >= 60:
        sig.direction = "bullish"
    elif score <= 40:
        sig.direction = "bearish"
    else:
        sig.direction = "neutral"

    return sig


# ── Multi-TF Analysis ─────────────────────────────────────────────────────────

@st.cache_data(ttl=1800, show_spinner=False)
def analyze_multi_timeframe(ticker: str, lookback: int = 3,
                             trend_mode: str = "Very Tight") -> MultiTFResult:
    """
    Hauptfunktion: Analysiert alle 4 Timeframes (4H, 1D, 1W, 1M) für einen Ticker.
    """
    result = MultiTFResult(ticker=ticker)
    fast_len, slow_len = TREND_MODES.get(trend_mode, (2, 9))

    try:
        # 4H: Fetch 1H → Resample
        df_1h = _fetch_tf_data(ticker, "1h", "60d")
        df_4h = _resample_to_4h(df_1h)
        result.tf_4h = _analyze_tf(df_4h, "4H", lookback, fast_len, slow_len)

        # 1D
        df_1d = _fetch_tf_data(ticker, "1d", "2y")
        result.tf_1d = _analyze_tf(df_1d, "1D", lookback, fast_len, slow_len)

        # 1W
        df_1w = _fetch_tf_data(ticker, "1wk", "5y")
        result.tf_1w = _analyze_tf(df_1w, "1W", lookback, fast_len, slow_len)

        # 1M (Monatsebene — primär für Stillhalter Trend Model Langfristtrend)
        df_1m = _fetch_tf_data(ticker, "1mo", "10y")
        result.tf_1m = _analyze_tf(df_1m, "1M", lookback, fast_len, slow_len)

    except Exception as e:
        result.error = str(e)
        return result

    # ── Alignment berechnen (4H · 1D · 1W) ───────────────────────────────
    tfs_core = [r for r in [result.tf_4h, result.tf_1d, result.tf_1w] if r is not None]
    if not tfs_core:
        return result

    n_bull = sum(1 for t in tfs_core if t.direction == "bullish")
    n_bear = sum(1 for t in tfs_core if t.direction == "bearish")
    n = len(tfs_core)

    # Gewichtung: 1W > 1D > 4H
    weights = {"4H": 0.25, "1D": 0.40, "1W": 0.35}
    weighted_score = sum(
        t.score * weights.get(t.timeframe, 0.33)
        for t in tfs_core
    )
    result.alignment_score = round(weighted_score, 1)

    if n_bull >= 2:
        result.alignment_direction = "bullish"
    elif n_bear >= 2:
        result.alignment_direction = "bearish"
    else:
        result.alignment_direction = "neutral"

    result.aligned_bullish = n_bull == n
    result.aligned_bearish = n_bear == n
    result.partially_aligned = n_bull >= 2 or n_bear >= 2

    # ── Stillhalter Trend Model — Trendstärke (alle 4 TFs inkl. 1M) ──────
    all_tfs = [r for r in [result.tf_4h, result.tf_1d, result.tf_1w, result.tf_1m] if r is not None]
    bull_count = sum(1 for t in all_tfs if t.ema_bullish)
    bear_count = sum(1 for t in all_tfs if t.ema_bearish)
    result.ema_bull_count = bull_count
    result.ema_bear_count = bear_count

    total_tfs = len(all_tfs) or 1
    if bull_count == total_tfs:
        result.ema_trend_label = "Stark Aufwärts"
        result.ema_trend_pct = 100.0
    elif bull_count >= total_tfs - 1 and bull_count > bear_count:
        result.ema_trend_label = "Aufwärts"
        result.ema_trend_pct = 75.0
    elif bear_count == total_tfs:
        result.ema_trend_label = "Stark Abwärts"
        result.ema_trend_pct = 0.0
    elif bear_count >= total_tfs - 1 and bear_count > bull_count:
        result.ema_trend_label = "Abwärts"
        result.ema_trend_pct = 25.0
    else:
        result.ema_trend_label = "Neutral / Gemischt"
        result.ema_trend_pct = 50.0

    # ── Cross-TF Signal-Bestätigungen ─────────────────────────────────────
    # Bullish
    result.confirmed_rsi_oversold = sum(
        1 for t in tfs_core if t.rsi_oversold or t.rsi_cross_30_up
    ) >= 2
    result.confirmed_stoch_cross_up = sum(
        1 for t in tfs_core if t.stoch_cross_20_up
    ) >= 2
    result.confirmed_macd_bullish_cross = sum(
        1 for t in tfs_core if t.macd_cross_bullish
    ) >= 2
    result.confirmed_ema_bullish = sum(
        1 for t in tfs_core if t.ema_bullish
    ) >= 2

    # Bearish
    result.confirmed_rsi_overbought = sum(
        1 for t in tfs_core if t.rsi_overbought or t.rsi_cross_70_down
    ) >= 2
    result.confirmed_stoch_cross_down = sum(
        1 for t in tfs_core if t.stoch_cross_80_down
    ) >= 2
    result.confirmed_macd_bearish_cross = sum(
        1 for t in tfs_core if t.macd_cross_bearish
    ) >= 2
    result.confirmed_ema_bearish = sum(
        1 for t in tfs_core if t.ema_bearish
    ) >= 2

    return result


# ── Filter-Matching ────────────────────────────────────────────────────────────

@dataclass
class TechFilterParams:
    # Stillhalter Trend Model
    ema_filter: str = "Alle"        # "Alle" | "SC Trend bullish ↑" | "SC Trend bearish ↓" | ...
    ema_timeframe: str = "1D"       # "4H" | "1D" | "1W" | "Alle TFs"

    # RSI
    rsi_filter: str = "Alle"
    # "Alle" | "< 30 (überverkauft)" | "> 70 (überkauft)" | "kreuzt 30 aufwärts" | "kreuzt 70 abwärts" | "bullish (>50)" | "bearish (<50)"
    rsi_timeframe: str = "1D"

    # Stochastik
    stoch_filter: str = "Alle"
    # "Alle" | "< 20 (überverkauft)" | "> 80 (überkauft)" | "kreuzt 20 aufwärts" | "kreuzt 80 abwärts" | "%K > %D" | "%K < %D"
    stoch_timeframe: str = "1D"

    # MACD
    macd_filter: str = "Alle"
    # "Alle" | "Bullish Cross (neg→pos)" | "Bearish Cross (pos→neg)" | "MACD > Signal" | "MACD < Signal" | "MACD > 0"
    macd_timeframe: str = "1D"

    # Multi-TF Alignment
    require_alignment: bool = False
    alignment_direction: str = "bullish"  # "bullish" | "bearish"
    min_aligned_tfs: int = 2              # mind. 2 von 3


def matches_tech_filter(result: MultiTFResult, params: TechFilterParams) -> bool:
    """
    Prüft ob ein Ticker die technischen Filterkriterien erfüllt.
    Gibt True zurück wenn alle aktiven Filter erfüllt sind.
    """
    def get_tf(tf_name: str) -> Optional[TFSignal]:
        mapping = {"4H": result.tf_4h, "1D": result.tf_1d, "1W": result.tf_1w}
        return mapping.get(tf_name)

    def check_filter_on_tf(tf: Optional[TFSignal], filter_str: str, category: str) -> bool:
        if filter_str == "Alle" or tf is None:
            return True
        if category == "ema":
            return {
                # Neue Strings (Scanner UI)
                "SC Trend bullish ↑":            tf.ema_bullish,
                "SC Trend bearish ↓":            tf.ema_bearish,
                "Kaufsignal (Cross ↑)":          tf.ema_cross_bullish,
                "Verkaufssignal (Cross ↓)":      tf.ema_cross_bearish,
                # Legacy-Mapping für Rückwärtskompatibilität
                "EMA bullish (EMA2 > EMA9)":     tf.ema_bullish,
                "EMA bearish (EMA2 < EMA9)":     tf.ema_bearish,
                "EMA Cross Aufwärts":            tf.ema_cross_bullish,
                "EMA Cross Abwärts":             tf.ema_cross_bearish,
            }.get(filter_str, True)
        elif category == "rsi":
            return {
                "< 30 (überverkauft)":             tf.rsi_oversold,
                "> 70 (überkauft)":                tf.rsi_overbought,
                "Kreuzt 30 aufwärts ↑":            tf.rsi_cross_30_up,
                "Kreuzt 70 abwärts ↓":             tf.rsi_cross_70_down,
                "Bullish (RSI > 50)":              tf.rsi_bullish,
                "Bearish (RSI < 50)":              tf.rsi_bearish,
            }.get(filter_str, True)
        elif category == "stoch":
            return {
                "< 20 (überverkauft)":             tf.stoch_oversold,
                "> 80 (überkauft)":                tf.stoch_overbought,
                "Kreuzt 20 aufwärts ↑":            tf.stoch_cross_20_up,
                "Kreuzt 80 abwärts ↓":             tf.stoch_cross_80_down,
                "%K > %D (bullish)":               tf.stoch_bullish,
                "%K < %D (bearish)":               tf.stoch_bearish,
            }.get(filter_str, True)
        elif category == "macd":
            return {
                "Bullish Cross (neg → pos)":       tf.macd_cross_bullish,
                "Bearish Cross (pos → neg)":       tf.macd_cross_bearish,
                "MACD > Signal (bullish)":         tf.macd_bullish,
                "MACD < Signal (bearish)":         tf.macd_bearish,
                "MACD Linie > 0":                  tf.macd_above_zero,
            }.get(filter_str, True)
        return True

    # Stillhalter Trend Model Filter
    if params.ema_filter != "Alle":
        if params.ema_timeframe == "Alle TFs":
            tfs = [r for r in [result.tf_4h, result.tf_1d, result.tf_1w] if r]
            if not all(check_filter_on_tf(t, params.ema_filter, "ema") for t in tfs):
                return False
        else:
            tf = get_tf(params.ema_timeframe)
            if not check_filter_on_tf(tf, params.ema_filter, "ema"):
                return False

    # RSI Filter
    if params.rsi_filter != "Alle":
        if params.rsi_timeframe == "Alle TFs":
            tfs = [r for r in [result.tf_4h, result.tf_1d, result.tf_1w] if r]
            if not all(check_filter_on_tf(t, params.rsi_filter, "rsi") for t in tfs):
                return False
        else:
            tf = get_tf(params.rsi_timeframe)
            if not check_filter_on_tf(tf, params.rsi_filter, "rsi"):
                return False

    # Stochastik Filter
    if params.stoch_filter != "Alle":
        if params.stoch_timeframe == "Alle TFs":
            tfs = [r for r in [result.tf_4h, result.tf_1d, result.tf_1w] if r]
            if not all(check_filter_on_tf(t, params.stoch_filter, "stoch") for t in tfs):
                return False
        else:
            tf = get_tf(params.stoch_timeframe)
            if not check_filter_on_tf(tf, params.stoch_filter, "stoch"):
                return False

    # MACD Filter
    if params.macd_filter != "Alle":
        if params.macd_timeframe == "Alle TFs":
            tfs = [r for r in [result.tf_4h, result.tf_1d, result.tf_1w] if r]
            if not all(check_filter_on_tf(t, params.macd_filter, "macd") for t in tfs):
                return False
        else:
            tf = get_tf(params.macd_timeframe)
            if not check_filter_on_tf(tf, params.macd_filter, "macd"):
                return False

    # Multi-TF Alignment
    if params.require_alignment:
        tfs = [r for r in [result.tf_4h, result.tf_1d, result.tf_1w] if r]
        if params.alignment_direction == "bullish":
            aligned = sum(1 for t in tfs if t.direction == "bullish")
        else:
            aligned = sum(1 for t in tfs if t.direction == "bearish")
        if aligned < params.min_aligned_tfs:
            return False

    return True


def stillhalter_trend_html(result: MultiTFResult) -> str:
    """
    Rendert eine kompakte HTML-Übersicht der Stillhalter Trend Model Trendstärke
    über alle 4 Timeframes (4H · 1D · 1W · 1M).
    """
    tf_map = {
        "4H":  result.tf_4h,
        "1T":  result.tf_1d,
        "1W":  result.tf_1w,
        "1M":  result.tf_1m,
    }

    dot_color = {"bullish": "#22c55e", "bearish": "#ef4444", "neutral": "#555555"}
    label_color = {"bullish": "#22c55e", "bearish": "#ef4444", "neutral": "#888888"}

    dots_html = ""
    for tf_label, tf in tf_map.items():
        if tf is None:
            dots_html += f'<span style="color:#333;margin-right:14px">●&nbsp;<span style="font-size:0.78rem;color:#333">{tf_label}</span></span>'
        else:
            direction = "bullish" if tf.ema_bullish else "bearish"
            arrow = "↑" if tf.ema_bullish else "↓"
            col = dot_color[direction]
            dots_html += (
                f'<span style="color:{col};margin-right:14px;white-space:nowrap">'
                f'● {arrow}&nbsp;<span style="font-size:0.78rem;color:{col}">{tf_label}</span>'
                f'</span>'
            )

    # Gesamt-Label
    label = result.ema_trend_label
    pct = result.ema_trend_pct
    if pct >= 90:
        lc = "#22c55e"
    elif pct >= 60:
        lc = "#86efac"
    elif pct <= 10:
        lc = "#ef4444"
    elif pct <= 40:
        lc = "#fca5a5"
    else:
        lc = "#f59e0b"

    bull = result.ema_bull_count
    total = (result.ema_bull_count + result.ema_bear_count) or 4

    return f"""
    <div style="background:#111;border:1px solid #1e1e1e;border-radius:10px;padding:12px 16px;margin-bottom:8px">
        <div style="font-family:'RedRose',sans-serif;font-size:0.75rem;
                    color:#666;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:6px">
            Stillhalter Trend Model® &nbsp;·&nbsp; Trendstärke über alle Zeitebenen
        </div>
        <div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:8px">
            {dots_html}
        </div>
        <div style="display:flex;align-items:center;gap:10px">
            <div style="flex:1;background:#1a1a1a;border-radius:4px;height:6px;overflow:hidden">
                <div style="width:{pct}%;height:100%;background:{lc};border-radius:4px;transition:width 0.4s"></div>
            </div>
            <span style="font-family:'RedRose',sans-serif;font-weight:700;
                         font-size:0.88rem;color:{lc};white-space:nowrap">
                {label} ({bull}/{total})
            </span>
        </div>
    </div>"""


# Keep legacy alias for backwards compatibility
def ema_trend_strength_html(result: MultiTFResult) -> str:
    """Legacy alias — use stillhalter_trend_html instead."""
    return stillhalter_trend_html(result)


def format_signal_badge(value: bool, label_true: str, label_false: str = "") -> str:
    if value:
        return f'<span class="tag tag-green">{label_true}</span>'
    elif label_false:
        return f'<span class="tag tag-red">{label_false}</span>'
    return f'<span class="tag tag-gray">–</span>'


def tf_summary_row(tf: Optional[TFSignal]) -> dict:
    """Gibt einen kompakten Dict für die UI zurück."""
    if tf is None:
        return {k: "–" for k in ["TF", "RSI", "Stoch %K", "MACD", "SC Trend", "Richtung"]}
    dir_icon = {"bullish": "↑ Bullish", "bearish": "↓ Bearish", "neutral": "→ Neutral"}.get(tf.direction, "–")
    return {
        "TF": tf.timeframe,
        "RSI": f"{tf.rsi:.0f}{'⬆' if tf.rsi_cross_30_up else '⬇' if tf.rsi_cross_70_down else ''}",
        "Stoch %K": f"{tf.stoch_k:.0f}{'⬆' if tf.stoch_cross_20_up else '⬇' if tf.stoch_cross_80_down else ''}",
        "MACD": "↑ Cross" if tf.macd_cross_bullish else ("↓ Cross" if tf.macd_cross_bearish else ("Bull" if tf.macd_bullish else "Bear")),
        "SC Trend": "↑ Cross" if tf.ema_cross_bullish else ("↓ Cross" if tf.ema_cross_bearish else ("Bull" if tf.ema_bullish else "Bear")),
        "Score": f"{tf.score:.0f}",
        "Richtung": dir_icon,
    }
