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
from typing import Optional, List, Dict, Tuple


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

    # ── Neue Umkehrindikatoren ─────────────────────────────────────────────
    # Preisdivergenz (RSI / MACD vs. Preis)
    div_bull_rsi: bool = False        # Bullische RSI-Divergenz (Preis ↓ aber RSI ↑)
    div_bear_rsi: bool = False        # Bärische RSI-Divergenz (Preis ↑ aber RSI ↓)
    div_bull_macd: bool = False       # Bullische MACD-Histogramm-Divergenz
    div_bear_macd: bool = False       # Bärische MACD-Histogramm-Divergenz
    div_strength: float = 0.0         # Stärke der Divergenz (0-100)

    # Volatilitäts-Squeeze (Bollinger Bands inside Keltner Channels)
    squeeze_active: bool = False      # BB innerhalb KC = Kompression
    squeeze_release_bull: bool = False # Squeeze löst sich auf mit bullischem Momentum
    squeeze_release_bear: bool = False # Squeeze löst sich auf mit bärischem Momentum
    squeeze_momentum: float = 0.0     # Momentum-Wert im Squeeze (pos=bull, neg=bear)

    # Volumen-Kapitulation (OBV-Divergenz + Klimax-Volumen)
    obv_bull_div: bool = False        # OBV steigt während Preis fällt (Akkumulation)
    obv_bear_div: bool = False        # OBV fällt während Preis steigt (Distribution)
    vol_climax_bull: bool = False     # Volumenspike an Tiefpunkt (Kapitulation nach unten)
    vol_climax_bear: bool = False     # Volumenspike an Hochpunkt (Kapitulation nach oben)
    vol_z_score: float = 0.0          # Volumen Z-Score (>2.0 = Klimax)

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


def _find_swing_lows(series: pd.Series, lookback: int = 5, n: int = 3) -> List[Tuple[int, float]]:
    """Findet die letzten N Swing-Tiefs (lokale Minima)."""
    vals = series.dropna().values
    result = []
    for i in range(lookback, len(vals) - lookback):
        window = vals[i - lookback: i + lookback + 1]
        if vals[i] == min(window):
            result.append((i, vals[i]))
    return result[-n:] if result else []


def _find_swing_highs(series: pd.Series, lookback: int = 5, n: int = 3) -> List[Tuple[int, float]]:
    """Findet die letzten N Swing-Hochs (lokale Maxima)."""
    vals = series.dropna().values
    result = []
    for i in range(lookback, len(vals) - lookback):
        window = vals[i - lookback: i + lookback + 1]
        if vals[i] == max(window):
            result.append((i, vals[i]))
    return result[-n:] if result else []


def _calc_divergence(close: pd.Series, indicator: pd.Series,
                     lookback: int = 5) -> Tuple[bool, bool, float]:
    """
    Erkennt bullische / bärische Divergenz zwischen Preis und Indikator.
    Gibt zurück: (bull_div, bear_div, strength 0-100)
    """
    if len(close) < 20 or len(indicator) < 20:
        return False, False, 0.0
    try:
        price_lows  = _find_swing_lows(close, lookback, 3)
        price_highs = _find_swing_highs(close, lookback, 3)
        ind_clean   = indicator.dropna().reset_index(drop=True)

        bull_div = False
        bear_div = False
        strength = 0.0

        # Bullische Divergenz: Preis tieferes Tief, Indikator höheres Tief
        if len(price_lows) >= 2:
            (i1, p1), (i2, p2) = price_lows[-2], price_lows[-1]
            if p2 < p1 and i2 < len(ind_clean) and i1 < len(ind_clean):
                ind1, ind2 = ind_clean.iloc[i1], ind_clean.iloc[i2]
                if ind2 > ind1:  # Indikator macht höheres Tief
                    bull_div = True
                    price_drop = (p1 - p2) / max(abs(p1), 1e-6)
                    ind_rise   = (ind2 - ind1) / max(abs(ind1), 1e-6)
                    strength   = min(100, (price_drop + ind_rise) * 200)

        # Bärische Divergenz: Preis höheres Hoch, Indikator niedrigeres Hoch
        if len(price_highs) >= 2:
            (j1, h1), (j2, h2) = price_highs[-2], price_highs[-1]
            if h2 > h1 and j2 < len(ind_clean) and j1 < len(ind_clean):
                ind1, ind2 = ind_clean.iloc[j1], ind_clean.iloc[j2]
                if ind2 < ind1:  # Indikator macht niedrigeres Hoch
                    bear_div = True
                    price_rise = (h2 - h1) / max(abs(h1), 1e-6)
                    ind_drop   = (ind1 - ind2) / max(abs(ind1), 1e-6)
                    strength   = min(100, (price_rise + ind_drop) * 200)

        return bull_div, bear_div, round(strength, 1)
    except Exception:
        return False, False, 0.0


def _calc_squeeze(close: pd.Series, high: pd.Series, low: pd.Series,
                  bb_period: int = 20, bb_mult: float = 2.0,
                  kc_period: int = 20, kc_mult: float = 1.5) -> Tuple[bool, bool, bool, float]:
    """
    TTM Squeeze: Bollinger Bands inside Keltner Channels.
    Gibt zurück: (squeeze_active, release_bull, release_bear, momentum)
    """
    if len(close) < max(bb_period, kc_period) + 5:
        return False, False, False, 0.0
    try:
        # Bollinger Bands
        bb_mid   = close.rolling(bb_period).mean()
        bb_std   = close.rolling(bb_period).std()
        bb_upper = bb_mid + bb_mult * bb_std
        bb_lower = bb_mid - bb_mult * bb_std

        # Keltner Channels (ATR-basiert)
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low  - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        kc_mid   = close.ewm(span=kc_period, adjust=False).mean()
        kc_atr   = tr.ewm(span=kc_period, adjust=False).mean()
        kc_upper = kc_mid + kc_mult * kc_atr
        kc_lower = kc_mid - kc_mult * kc_atr

        # Squeeze: BB innerhalb KC
        in_squeeze  = (bb_upper < kc_upper) & (bb_lower > kc_lower)
        curr_squeeze = bool(in_squeeze.iloc[-1])

        # Momentum: lineare Regression der Close-Preise (letzten bb_period Kerzen)
        y = close.iloc[-bb_period:].values
        x = np.arange(len(y))
        slope = float(np.polyfit(x, y, 1)[0]) if len(y) >= 2 else 0.0
        # Normalisierung
        price_scale = float(close.iloc[-1]) or 1.0
        momentum = slope / price_scale * 100  # in % pro Kerze

        # War vorher im Squeeze, jetzt nicht mehr → Release
        prev_squeeze = bool(in_squeeze.iloc[-2]) if len(in_squeeze) > 1 else curr_squeeze
        release = prev_squeeze and not curr_squeeze
        release_bull = release and momentum > 0
        release_bear = release and momentum < 0

        return curr_squeeze, release_bull, release_bear, round(momentum, 4)
    except Exception:
        return False, False, False, 0.0


def _calc_obv_volume(close: pd.Series, volume: pd.Series,
                     lookback: int = 20) -> Tuple[bool, bool, bool, bool, float]:
    """
    OBV-Divergenz + Klimax-Volumen.
    Gibt zurück: (obv_bull_div, obv_bear_div, vol_climax_bull, vol_climax_bear, vol_z_score)
    """
    if len(close) < lookback + 5 or len(volume) < lookback + 5:
        return False, False, False, False, 0.0
    try:
        # OBV berechnen
        direction = np.sign(close.diff().fillna(0))
        obv = (direction * volume).cumsum()

        # OBV-Divergenz (Preis vs. OBV Trend der letzten lookback Kerzen)
        close_vals = close.iloc[-lookback:].values
        obv_vals   = obv.iloc[-lookback:].values
        x = np.arange(lookback)
        close_slope = float(np.polyfit(x, close_vals, 1)[0])
        obv_slope   = float(np.polyfit(x, obv_vals,   1)[0])

        obv_bull_div = close_slope < 0 and obv_slope > 0   # Preis fällt, OBV steigt
        obv_bear_div = close_slope > 0 and obv_slope < 0   # Preis steigt, OBV fällt

        # Volumen Z-Score (aktuelle Kerze vs. Durchschnitt)
        vol_mean = float(volume.iloc[-lookback:].mean())
        vol_std  = float(volume.iloc[-lookback:].std()) or 1.0
        vol_curr = float(volume.iloc[-1])
        z = (vol_curr - vol_mean) / vol_std

        # Klimax-Volumen an Extremen (Preis nahe Swing-Hoch/-Tief)
        close_arr   = close.iloc[-lookback:].values
        price_range = max(close_arr) - min(close_arr)
        rel_pos     = (float(close.iloc[-1]) - min(close_arr)) / max(price_range, 1e-6)

        vol_climax_bull = z > 2.0 and rel_pos < 0.2   # Klimax-Volumen nahe Tief
        vol_climax_bear = z > 2.0 and rel_pos > 0.8   # Klimax-Volumen nahe Hoch

        return obv_bull_div, obv_bear_div, vol_climax_bull, vol_climax_bear, round(z, 2)
    except Exception:
        return False, False, False, False, 0.0


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

    # ── Preisdivergenz (RSI & MACD vs. Preis) ──────────────────────────────
    try:
        bull_div_rsi,  bear_div_rsi,  str_rsi  = _calc_divergence(close, rsi,  lookback)
        bull_div_macd, bear_div_macd, str_macd = _calc_divergence(close, hist, lookback)
        sig.div_bull_rsi  = bull_div_rsi
        sig.div_bear_rsi  = bear_div_rsi
        sig.div_bull_macd = bull_div_macd
        sig.div_bear_macd = bear_div_macd
        sig.div_strength  = round((str_rsi + str_macd) / 2, 1)
    except Exception:
        pass

    # ── Volatilitäts-Squeeze ──────────────────────────────────────────────
    try:
        sq_active, sq_bull, sq_bear, sq_mom = _calc_squeeze(close, high, low)
        sig.squeeze_active       = sq_active
        sig.squeeze_release_bull = sq_bull
        sig.squeeze_release_bear = sq_bear
        sig.squeeze_momentum     = sq_mom
    except Exception:
        pass

    # ── Volumen-Kapitulation ──────────────────────────────────────────────
    if "Volume" in df.columns:
        try:
            volume = df["Volume"]
            obv_bd, obv_brd, vc_bull, vc_bear, vz = _calc_obv_volume(close, volume)
            sig.obv_bull_div    = obv_bd
            sig.obv_bear_div    = obv_brd
            sig.vol_climax_bull = vc_bull
            sig.vol_climax_bear = vc_bear
            sig.vol_z_score     = vz
        except Exception:
            pass

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


# ── Best Convergence Score ─────────────────────────────────────────────────────

@dataclass
class ConvergenceResult:
    """
    Misst wie nah ein Ticker an einer idealen Konvergenz aller 7 Indikatoren ist.
    Short Put:  Stoch kreuzt 20↑ · RSI kreuzt 30↑ · EMA2 kreuzt EMA9↑ · MACD hist neg→pos
                + Marktstruktur-Analyse · Volatilitätskompression · Volumendynamik
    Short Call: Umgekehrt
    """
    strategy: str = "put"          # "put" | "call"

    # Gesamt-Score 0-100 (gewichteter Durchschnitt 1D 60% + 4H 40%)
    score: float = 0.0
    score_1d: float = 0.0
    score_4h: float = 0.0

    label: str = "–"               # "Perfekt" | "Sehr nah" | "Nah" | "Entfernt"
    bar: str = ""                  # visueller Balken "████░░░░░░"


def _proximity_put(tf: TFSignal) -> dict:
    """Berechnet Short Put Konvergenz-Teilscores für einen Timeframe (je 0-100)."""

    # ── Stochastik: ideal = %K kreuzt 20 aufwärts ─────────────────────────
    k = tf.stoch_k
    if tf.stoch_cross_20_up:
        stoch_s = 100
    elif k < 20 and tf.stoch_bullish:          # überverkauft + K dreht auf
        stoch_s = 88
    elif k < 20:                               # überverkauft, noch fallend
        stoch_s = 65
    elif k < 30:                               # gerade aus Überverkauft-Zone
        stoch_s = int(80 - (k - 20) * 3.5)    # 80 bei k=20 → 45 bei k=30
    elif k < 50:
        stoch_s = int(max(10, 40 - (k - 30) * 1.5))
    else:
        stoch_s = int(max(0, 10 - (k - 50) * 0.15))

    # ── RSI: ideal = kreuzt 30 aufwärts ───────────────────────────────────
    rsi = tf.rsi
    if tf.rsi_cross_30_up:
        rsi_s = 100
    elif rsi < 30:
        rsi_s = 72
    elif rsi < 40:
        rsi_s = int(max(30, 85 - (rsi - 30) * 5.5))  # 85→30
    elif rsi < 50:
        rsi_s = int(max(10, 30 - (rsi - 40) * 2))
    else:
        rsi_s = int(max(0, 10 - (rsi - 50) * 0.15))

    # ── EMA Trend: ideal = EMA2 kreuzt EMA9 aufwärts ──────────────────────
    if tf.ema_cross_bullish:
        ema_s = 100
    elif tf.ema_bullish:
        # Bereits bullish — noch ein frischer Aufwärtstrend (gut, aber nicht Ideal-Timing)
        ema_s = 58
    else:
        # EMA2 < EMA9 — wie weit weg vom Cross?
        ref = abs(tf.ema9) if tf.ema9 != 0 else 1.0
        gap_pct = abs(tf.ema9 - tf.ema2) / ref * 100
        ema_s = int(max(0, 75 - gap_pct * 4))

    # ── MACD Histogramm: ideal = dreht von negativ auf positiv ────────────
    hist = tf.macd_hist
    if tf.macd_cross_bullish:
        macd_s = 100
    elif hist > 0 and tf.macd_bullish:
        # Schon positiv — je kleiner das Histogramm, desto frischer der Cross
        ref = max(abs(tf.macd_val), 1e-6)
        freshness = max(0, 1 - hist / (ref * 2))
        macd_s = int(50 + freshness * 30)   # 50-80
    elif hist < 0:
        # Negativ aber wie nah an Null? (höher = besser)
        ref = max(abs(tf.macd_val), 1e-6)
        proximity = max(0, 1 - abs(hist) / (ref * 2.5))
        macd_s = int(proximity * 80)         # 0-80
    else:
        macd_s = 20

    # ── Preisdivergenz (bullisch = gut für Short Put) ──────────────────────
    if tf.div_bull_rsi and tf.div_bull_macd:
        div_s = min(100, 60 + tf.div_strength * 0.4)
    elif tf.div_bull_rsi or tf.div_bull_macd:
        div_s = min(100, 40 + tf.div_strength * 0.3)
    elif tf.div_bear_rsi or tf.div_bear_macd:
        div_s = 10   # falsche Richtung
    else:
        div_s = 25   # neutral

    # ── Squeeze (aktiver Squeeze + bullisches Release) ─────────────────────
    if tf.squeeze_release_bull:
        sq_s = 100
    elif tf.squeeze_active and tf.squeeze_momentum > 0:
        sq_s = 75     # Squeeze aktiv, Momentum bullisch (Ausbruch erwartet)
    elif tf.squeeze_active:
        sq_s = 50     # Squeeze aktiv, Richtung unklar
    elif tf.squeeze_release_bear:
        sq_s = 5
    else:
        sq_s = 20

    # ── Volumen-Kapitulation (bullisch) ────────────────────────────────────
    if tf.vol_climax_bull:
        vol_s = 100   # Kapitulationsvolumen an Tief = starkes Kaufsignal
    elif tf.obv_bull_div:
        vol_s = 75    # OBV steigt trotz fallendem Preis
    elif tf.vol_climax_bear or tf.obv_bear_div:
        vol_s = 10    # falsche Richtung
    else:
        vol_s = 30

    return {
        "stoch": stoch_s, "rsi": rsi_s, "ema": ema_s, "macd": macd_s,
        "div": div_s, "squeeze": sq_s, "volume": vol_s,
        # Gewichtung: klassische 4 = 55%, neue 3 = 45%
        "total": (stoch_s * 0.15 + rsi_s * 0.15 + ema_s * 0.13 + macd_s * 0.12 +
                  div_s * 0.18 + sq_s * 0.15 + vol_s * 0.12),
    }


def _proximity_call(tf: TFSignal) -> dict:
    """Berechnet Short Call Konvergenz-Teilscores für einen Timeframe (je 0-100)."""

    # ── Stochastik: ideal = %K kreuzt 80 abwärts ──────────────────────────
    k = tf.stoch_k
    if tf.stoch_cross_80_down:
        stoch_s = 100
    elif k > 80 and tf.stoch_bearish:          # überkauft + K dreht ab
        stoch_s = 88
    elif k > 80:
        stoch_s = 65
    elif k > 70:
        stoch_s = int(80 - (80 - k) * 3.5)    # 80 bei k=80 → 45 bei k=70
    elif k > 50:
        stoch_s = int(max(10, 40 - (70 - k) * 1.5))
    else:
        stoch_s = int(max(0, 10 - (50 - k) * 0.15))

    # ── RSI: ideal = kreuzt 70 abwärts ────────────────────────────────────
    rsi = tf.rsi
    if tf.rsi_cross_70_down:
        rsi_s = 100
    elif rsi > 70:
        rsi_s = 72
    elif rsi > 60:
        rsi_s = int(max(30, 85 - (70 - rsi) * 5.5))
    elif rsi > 50:
        rsi_s = int(max(10, 30 - (60 - rsi) * 2))
    else:
        rsi_s = int(max(0, 10 - (50 - rsi) * 0.15))

    # ── EMA Trend: ideal = EMA2 kreuzt EMA9 abwärts ───────────────────────
    if tf.ema_cross_bearish:
        ema_s = 100
    elif tf.ema_bearish:
        ema_s = 58
    else:
        ref = abs(tf.ema9) if tf.ema9 != 0 else 1.0
        gap_pct = abs(tf.ema2 - tf.ema9) / ref * 100
        ema_s = int(max(0, 75 - gap_pct * 4))

    # ── MACD Histogramm: ideal = dreht von positiv auf negativ ────────────
    hist = tf.macd_hist
    if tf.macd_cross_bearish:
        macd_s = 100
    elif hist < 0 and tf.macd_bearish:
        ref = max(abs(tf.macd_val), 1e-6)
        freshness = max(0, 1 - abs(hist) / (ref * 2))
        macd_s = int(50 + freshness * 30)
    elif hist > 0:
        ref = max(abs(tf.macd_val), 1e-6)
        proximity = max(0, 1 - hist / (ref * 2.5))
        macd_s = int(proximity * 80)
    else:
        macd_s = 20

    # ── Preisdivergenz (bärisch = gut für Short Call) ─────────────────────
    if tf.div_bear_rsi and tf.div_bear_macd:
        div_s = min(100, 60 + tf.div_strength * 0.4)
    elif tf.div_bear_rsi or tf.div_bear_macd:
        div_s = min(100, 40 + tf.div_strength * 0.3)
    elif tf.div_bull_rsi or tf.div_bull_macd:
        div_s = 10   # falsche Richtung
    else:
        div_s = 25   # neutral

    # ── Squeeze (aktiver Squeeze + bärisches Release) ──────────────────────
    if tf.squeeze_release_bear:
        sq_s = 100
    elif tf.squeeze_active and tf.squeeze_momentum < 0:
        sq_s = 75     # Squeeze aktiv, Momentum bärisch (Ausbruch erwartet)
    elif tf.squeeze_active:
        sq_s = 50     # Squeeze aktiv, Richtung unklar
    elif tf.squeeze_release_bull:
        sq_s = 5
    else:
        sq_s = 20

    # ── Volumen-Kapitulation (bärisch) ────────────────────────────────────
    if tf.vol_climax_bear:
        vol_s = 100   # Kapitulationsvolumen an Hoch = starkes Verkaufssignal
    elif tf.obv_bear_div:
        vol_s = 75    # OBV fällt trotz steigendem Preis
    elif tf.vol_climax_bull or tf.obv_bull_div:
        vol_s = 10    # falsche Richtung
    else:
        vol_s = 30

    return {
        "stoch": stoch_s, "rsi": rsi_s, "ema": ema_s, "macd": macd_s,
        "div": div_s, "squeeze": sq_s, "volume": vol_s,
        # Gewichtung: klassische 4 = 55%, neue 3 = 45%
        "total": (stoch_s * 0.15 + rsi_s * 0.15 + ema_s * 0.13 + macd_s * 0.12 +
                  div_s * 0.18 + sq_s * 0.15 + vol_s * 0.12),
    }


def calc_convergence_score(mtf: MultiTFResult, strategy: str = "put") -> ConvergenceResult:
    """
    Berechnet den Best-Convergence-Score für einen Ticker.

    strategy = "put"  → Short Put Setup (Indikatoren nähern sich Oversold-Umkehr an)
    strategy = "call" → Short Call Setup (Indikatoren nähern sich Overbought-Umkehr an)

    Score 0-100:
      80-100 = Perfekte Konvergenz (alle Indikatoren nahe am Idealwert)
      60-79  = Sehr nah (3-4 Indikatoren konvergieren)
      40-59  = Nah (2 Indikatoren konvergieren)
      0-39   = Noch entfernt
    """
    proximity_fn = _proximity_put if strategy == "put" else _proximity_call

    zero = {"stoch": 0, "rsi": 0, "ema": 0, "macd": 0, "div": 0, "squeeze": 0, "volume": 0, "total": 0}

    s_1d = proximity_fn(mtf.tf_1d) if mtf.tf_1d else zero
    s_4h = proximity_fn(mtf.tf_4h) if mtf.tf_4h else s_1d  # fallback auf 1D wenn kein 4H

    score_1d = round(s_1d["total"], 1)
    score_4h = round(s_4h["total"], 1)
    combined = round(score_1d * 0.60 + score_4h * 0.40, 1)

    # Label
    if combined >= 78:
        label = "🟢 Perfekt"
    elif combined >= 60:
        label = "🟡 Sehr nah"
    elif combined >= 40:
        label = "🟠 Nah"
    else:
        label = "🔴 Entfernt"

    # Visueller Balken (10 Blöcke)
    filled = round(combined / 10)
    bar = "█" * filled + "░" * (10 - filled)

    return ConvergenceResult(
        strategy=strategy,
        score=combined, score_1d=score_1d, score_4h=score_4h,
        label=label, bar=bar,
    )


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
