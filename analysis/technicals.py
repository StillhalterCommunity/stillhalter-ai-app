"""
Technische Indikatoren: Trend, MACD, Stochastik, Trendkanäle, Support/Resistance.
Kompatibel mit TradingView Standard-Einstellungen.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional, List


@dataclass
class TechSignal:
    trend: str          # "bullish" | "bearish" | "neutral"
    trend_score: float  # 0-100 (100 = stark bullish)
    macd_signal: str    # "bullish" | "bearish" | "neutral"
    stoch_signal: str   # "bullish" | "bearish" | "oversold" | "overbought"
    stoch_k: float
    stoch_d: float
    support_levels: List[float]
    resistance_levels: List[float]
    channel_upper: Optional[float]
    channel_lower: Optional[float]
    channel_mid: Optional[float]
    above_sma50: bool
    above_sma200: bool
    summary: str        # kurze Textbeschreibung


def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=1).mean()


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calculate_macd(close: pd.Series, fast=12, slow=26, signal=9) -> tuple[pd.Series, pd.Series, pd.Series]:
    """MACD Linie, Signal Linie, Histogramm (TV-Standard 12,26,9)."""
    ema_fast = calculate_ema(close, fast)
    ema_slow = calculate_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calculate_stochastic(high: pd.Series, low: pd.Series, close: pd.Series,
                          k_period=14, d_period=3, smooth_k=3) -> tuple[pd.Series, pd.Series]:
    """Stochastik Oszillator (TV-Standard 14,3,3)."""
    lowest_low = low.rolling(window=k_period).min()
    highest_high = high.rolling(window=k_period).max()

    stoch_raw = 100 * (close - lowest_low) / (highest_high - lowest_low + 1e-10)
    stoch_k = stoch_raw.rolling(window=smooth_k).mean()  # geglättet
    stoch_d = stoch_k.rolling(window=d_period).mean()

    return stoch_k, stoch_d


def calculate_linear_regression_channel(close: pd.Series, period: int = 50,
                                         std_mult: float = 2.0) -> tuple[float, float, float]:
    """
    Linearer Regressions-Kanal.
    Gibt zurück: (upper_band, mid_line, lower_band) für den letzten Datenpunkt.
    """
    if len(close) < period:
        period = len(close)

    y = close.iloc[-period:].values
    x = np.arange(period)

    # Lineare Regression
    coeffs = np.polyfit(x, y, 1)
    fitted = np.polyval(coeffs, x)

    # Standardabweichung der Residuen
    residuals = y - fitted
    std = np.std(residuals)

    mid = float(fitted[-1])
    upper = float(fitted[-1] + std_mult * std)
    lower = float(fitted[-1] - std_mult * std)

    return upper, mid, lower


def find_support_resistance(high: pd.Series, low: pd.Series, close: pd.Series,
                             lookback: int = 60, n_levels: int = 3) -> tuple[list[float], list[float]]:
    """
    Findet Unterstützungs- und Widerstandsniveaus über Pivot Points.
    """
    if len(close) < lookback:
        lookback = len(close)

    recent_high = high.iloc[-lookback:]
    recent_low = low.iloc[-lookback:]
    current_price = float(close.iloc[-1])

    # Lokale Hochs und Tiefs finden (Pivot Points)
    support_candidates = []
    resistance_candidates = []

    window = 5
    for i in range(window, len(recent_low) - window):
        # Lokales Tief
        if recent_low.iloc[i] == recent_low.iloc[i-window:i+window+1].min():
            level = float(recent_low.iloc[i])
            if level < current_price:
                support_candidates.append(level)

        # Lokales Hoch
        if recent_high.iloc[i] == recent_high.iloc[i-window:i+window+1].max():
            level = float(recent_high.iloc[i])
            if level > current_price:
                resistance_candidates.append(level)

    # Cluster benachbarter Levels
    def cluster_levels(levels: list[float], threshold_pct: float = 0.015) -> list[float]:
        if not levels:
            return []
        levels = sorted(levels)
        clustered = [levels[0]]
        for lvl in levels[1:]:
            if abs(lvl - clustered[-1]) / clustered[-1] > threshold_pct:
                clustered.append(lvl)
        return clustered

    supports = cluster_levels(support_candidates)[-n_levels:]
    resistances = cluster_levels(resistance_candidates)[:n_levels]

    return supports, resistances


def get_trend_score(close: pd.Series) -> tuple[float, str]:
    """
    Berechnet einen Trend-Score 0-100 basierend auf:
    - Preis vs SMA50/200
    - SMA50 vs SMA200 (Golden/Death Cross)
    - Kursentwicklung letzte 20 Tage
    """
    if len(close) < 10:
        return 50.0, "neutral"

    score = 50.0
    current = float(close.iloc[-1])

    # SMA50
    sma50 = float(calculate_sma(close, 50).iloc[-1])
    # SMA200
    sma200 = float(calculate_sma(close, min(200, len(close))).iloc[-1])

    if current > sma50:
        score += 15
    else:
        score -= 15

    if current > sma200:
        score += 15
    else:
        score -= 15

    if sma50 > sma200:
        score += 10  # Golden Cross Konstellation
    else:
        score -= 10  # Death Cross Konstellation

    # Momentum letzte 20 Tage
    if len(close) >= 20:
        perf_20d = (current / float(close.iloc[-20]) - 1) * 100
        if perf_20d > 5:
            score += 10
        elif perf_20d > 0:
            score += 5
        elif perf_20d < -5:
            score -= 10
        else:
            score -= 5

    score = max(0, min(100, score))

    if score >= 65:
        trend = "bullish"
    elif score <= 35:
        trend = "bearish"
    else:
        trend = "neutral"

    return score, trend


def analyze_technicals(df: pd.DataFrame) -> Optional[TechSignal]:
    """
    Hauptfunktion: Berechnet alle technischen Signale aus OHLCV-Daten.
    """
    if df is None or df.empty or len(df) < 20:
        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    current_price = float(close.iloc[-1])

    # ── MACD ──────────────────────────────────────────────────────────────
    macd_line, signal_line, histogram = calculate_macd(close)
    macd_val = float(macd_line.iloc[-1])
    macd_sig = float(signal_line.iloc[-1])
    macd_hist = float(histogram.iloc[-1])
    macd_hist_prev = float(histogram.iloc[-2]) if len(histogram) >= 2 else 0

    if macd_val > macd_sig and macd_hist > macd_hist_prev:
        macd_signal = "bullish"
    elif macd_val < macd_sig and macd_hist < macd_hist_prev:
        macd_signal = "bearish"
    else:
        macd_signal = "neutral"

    # ── Stochastik ────────────────────────────────────────────────────────
    stoch_k, stoch_d = calculate_stochastic(high, low, close)
    k_val = float(stoch_k.iloc[-1]) if not np.isnan(stoch_k.iloc[-1]) else 50.0
    d_val = float(stoch_d.iloc[-1]) if not np.isnan(stoch_d.iloc[-1]) else 50.0

    if k_val < 20:
        stoch_signal = "oversold"
    elif k_val > 80:
        stoch_signal = "overbought"
    elif k_val > d_val:
        stoch_signal = "bullish"
    else:
        stoch_signal = "bearish"

    # ── Trend ─────────────────────────────────────────────────────────────
    trend_score, trend = get_trend_score(close)

    sma50 = float(calculate_sma(close, 50).iloc[-1])
    sma200 = float(calculate_sma(close, min(200, len(close))).iloc[-1])

    # ── Trendkanal ────────────────────────────────────────────────────────
    try:
        ch_upper, ch_mid, ch_lower = calculate_linear_regression_channel(close, period=50)
    except Exception:
        ch_upper = ch_mid = ch_lower = None

    # ── Support / Resistance ──────────────────────────────────────────────
    try:
        supports, resistances = find_support_resistance(high, low, close)
    except Exception:
        supports, resistances = [], []

    # ── Zusammenfassung ───────────────────────────────────────────────────
    parts = []
    if trend == "bullish":
        parts.append("Aufwärtstrend")
    elif trend == "bearish":
        parts.append("Abwärtstrend")
    else:
        parts.append("Seitwärtstrend")

    if macd_signal == "bullish":
        parts.append("MACD bullish")
    elif macd_signal == "bearish":
        parts.append("MACD bearish")

    if stoch_signal == "oversold":
        parts.append("Stoch überverkauft")
    elif stoch_signal == "overbought":
        parts.append("Stoch überkauft")

    summary = " | ".join(parts)

    return TechSignal(
        trend=trend,
        trend_score=trend_score,
        macd_signal=macd_signal,
        stoch_signal=stoch_signal,
        stoch_k=k_val,
        stoch_d=d_val,
        support_levels=supports,
        resistance_levels=resistances,
        channel_upper=ch_upper,
        channel_lower=ch_lower,
        channel_mid=ch_mid,
        above_sma50=current_price > sma50,
        above_sma200=current_price > sma200,
        summary=summary,
    )
