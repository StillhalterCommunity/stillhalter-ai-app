"""
Technische Indikatoren — Stillhalter AI App Dashboard
Enthält: SC Trend Model, Dual Stochastic, MACD, Trendkanal, S/R-Levels.
Alle Berechnungen TV-kompatibel (Pine Script Logik 1:1 portiert).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Optional, List, Tuple


# ── Dual Stochastic Dataclass ──────────────────────────────────────────────────
@dataclass
class DualStochResult:
    """
    Stillhalter AI App — Dual Stochastic (Pine Script portiert).
    Schnell: 14,3,3  |  Langsam: 35,10,5
    """
    # Aktuelle Werte
    fast_k: float = 50.0          # Schneller %K (14,3,3)
    fast_d: float = 50.0          # Schneller %D
    slow_k: float = 50.0          # Langsamer %K (35,10,5)
    slow_d: float = 50.0          # Langsamer %D

    # ── Schnelle Stochastik Signale ────────────────────────────────────────
    fast_buy: bool = False         # crossover(%K, 20) — kreuzt 20 aufwärts
    fast_sell: bool = False        # crossunder(%K, 80) — kreuzt 80 abwärts
    fast_ready_buy: bool = False   # %K < 20 UND crossover(%K, %D) — stärkstes Kaufsignal
    fast_ready_sell: bool = False  # %K > 80 UND crossunder(%K, %D) — stärkstes Verkaufssignal
    fast_oversold: bool = False    # %K < 20
    fast_overbought: bool = False  # %K > 80

    # ── Langsame Stochastik Signale ────────────────────────────────────────
    slow_buy: bool = False         # crossover(%K, 20)
    slow_sell: bool = False        # crossunder(%K, 80)
    slow_ready_buy: bool = False   # %K < 20 UND crossover(%K, %D)
    slow_ready_sell: bool = False  # %K > 80 UND crossunder(%K, %D)
    slow_oversold: bool = False    # %K < 20
    slow_overbought: bool = False  # %K > 80

    # ── Kombiniertes Signal ────────────────────────────────────────────────
    both_oversold: bool = False    # Beide überverkauft → stärkstes Einstiegssignal
    both_overbought: bool = False  # Beide überkauft → stärkstes Ausstiegssignal
    signal_strength: str = "neutral"  # "strong_buy"|"buy"|"neutral"|"sell"|"strong_sell"

    # Zeitreihen (für Chart)
    fast_k_series: Optional[pd.Series] = field(default=None, repr=False)
    fast_d_series: Optional[pd.Series] = field(default=None, repr=False)
    slow_k_series: Optional[pd.Series] = field(default=None, repr=False)
    slow_d_series: Optional[pd.Series] = field(default=None, repr=False)


@dataclass
class TechSignal:
    trend: str                         # "bullish" | "bearish" | "neutral"
    trend_score: float                 # 0–100
    macd_signal: str                   # "bullish" | "bearish" | "neutral"
    stoch_signal: str                  # legacy — aus schneller Stochastik
    stoch_k: float                     # legacy — schnelle %K
    stoch_d: float                     # legacy — schnelle %D
    dual_stoch: Optional[DualStochResult]
    sc_macd: Optional["StillhalterMACDResult"]   # Stillhalter MACD Pro
    support_levels: List[float]
    resistance_levels: List[float]
    channel_upper: Optional[float]
    channel_lower: Optional[float]
    channel_mid: Optional[float]
    above_sma50: bool
    above_sma200: bool
    summary: str


# ── Basis-Berechnungen ─────────────────────────────────────────────────────────

def calculate_sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=1).mean()


def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calculate_macd(
    close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Standard MACD — Fallback für Legacy-Aufrufe."""
    ema_fast  = calculate_ema(close, fast)
    ema_slow  = calculate_ema(close, slow)
    macd_line = ema_fast - ema_slow
    sig_line  = calculate_ema(macd_line, signal)
    return macd_line, sig_line, macd_line - sig_line


# ── Wilder's RMA (ta.rma in Pine Script) ──────────────────────────────────────
def _wilder_ma(series: pd.Series, period: int) -> pd.Series:
    """Wilder's Smoothing = ta.rma() in Pine Script. alpha = 1/period."""
    return series.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


# ── ADX (14) ──────────────────────────────────────────────────────────────────
def calculate_adx(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    ADX + DI+/DI- nach Wilder (Pine: ta.rma).
    Gibt zurück: (adx, di_plus, di_minus)
    """
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low  - close.shift(1)).abs()
    tr  = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    h_diff = high  - high.shift(1)
    l_diff = low.shift(1) - low
    plus_dm  = h_diff.where((h_diff > l_diff) & (h_diff > 0), 0.0)
    minus_dm = l_diff.where((l_diff > h_diff) & (l_diff > 0), 0.0)

    s_tr     = _wilder_ma(tr,       period)
    s_plus   = _wilder_ma(plus_dm,  period)
    s_minus  = _wilder_ma(minus_dm, period)

    di_plus  = 100.0 * s_plus  / s_tr.replace(0, 1e-10)
    di_minus = 100.0 * s_minus / s_tr.replace(0, 1e-10)
    dx       = 100.0 * (di_plus - di_minus).abs() / (di_plus + di_minus).replace(0, 1e-10)
    adx      = _wilder_ma(dx, period)

    return adx, di_plus, di_minus


# ── Stillhalter MACD Pro Dataclass ────────────────────────────────────────────
@dataclass
class StillhalterMACDResult:
    """
    Stillhalter MACD Pro v0.9 — portiert aus Pine Script.
    Parameter: EMA 10/35/5 (statt Standard 12/26/9).
    """
    # Kerndaten
    macd:    Optional[pd.Series] = field(default=None, repr=False)
    signal:  Optional[pd.Series] = field(default=None, repr=False)
    hist:    Optional[pd.Series] = field(default=None, repr=False)
    hist_colors: Optional[List[str]] = field(default=None, repr=False)

    # Z-Score
    z_score:  Optional[pd.Series] = field(default=None, repr=False)
    z_colors: Optional[List[str]] = field(default=None, repr=False)

    # ADX
    adx:      Optional[pd.Series] = field(default=None, repr=False)
    di_plus:  Optional[pd.Series] = field(default=None, repr=False)
    di_minus: Optional[pd.Series] = field(default=None, repr=False)

    # Aktuelle Werte
    macd_val:   float = 0.0
    signal_val: float = 0.0
    hist_val:   float = 0.0
    adx_val:    float = 0.0
    z_val:      float = 0.0

    # Cross-Signale
    bull_cross:    bool = False   # MACD kreuzt Signal aufwärts
    bear_cross:    bool = False   # MACD kreuzt Signal abwärts
    bull_adx20:    bool = False   # Bull Cross + ADX > 20
    bear_adx20:    bool = False   # Bear Cross + ADX > 20
    bull_adx40:    bool = False   # Bull Cross + ADX > 40 (starkes Signal)
    bear_adx40:    bool = False   # Bear Cross + ADX > 40 (starkes Signal)

    # ADX-Crossover-Indizes (für Chart-Marker)
    bull_cross_20_idx: Optional[List[int]] = field(default=None, repr=False)
    bear_cross_20_idx: Optional[List[int]] = field(default=None, repr=False)
    bull_cross_40_idx: Optional[List[int]] = field(default=None, repr=False)
    bear_cross_40_idx: Optional[List[int]] = field(default=None, repr=False)

    signal_strength: str = "neutral"  # "strong_bull"|"bull"|"neutral"|"bear"|"strong_bear"


def calculate_stillhalter_macd(
    close: pd.Series,
    high: pd.Series,
    low: pd.Series,
    fast: int = 10,
    slow: int = 35,
    signal_period: int = 5,
    adx_period: int = 14,
    z_window: int = 20,
) -> StillhalterMACDResult:
    """
    Stillhalter MACD Pro — 1:1 Portierung aus Pine Script v0.9.

    Einstellungen (fest, wie im Original):
      MACD:   EMA(10) − EMA(35), Signal: EMA(5)
      ADX:    14 Perioden (Wilder's RMA)
      Z-Score: 20-Perioden Fenster auf Histogramm
    """
    result = StillhalterMACDResult()
    if len(close) < max(slow, adx_period) + 5:
        return result

    # ── MACD ──────────────────────────────────────────────────────────────
    fast_ema = calculate_ema(close, fast)
    slow_ema = calculate_ema(close, slow)
    macd     = fast_ema - slow_ema
    sig      = calculate_ema(macd, signal_period)
    hist     = macd - sig

    result.macd   = macd
    result.signal = sig
    result.hist   = hist

    # ── 4-Farb-Histogramm ─────────────────────────────────────────────────
    # Farben exakt aus Pine Script:
    #   pos & inc  → #26A69A (dunkel teal, Bull steigend)
    #   pos & dec  → #B2DFDB (hell teal, Bull fallend)
    #   neg & inc  → #FFCDD2 (hell rot, Bear erholend)
    #   neg & dec  → #FF5252 (dunkel rot, Bear fallend)
    colors = []
    h_vals = hist.values
    for i, h in enumerate(h_vals):
        h_prev = h_vals[i-1] if i > 0 else h
        inc = h > h_prev
        if h >= 0:
            colors.append("#26A69A" if inc else "#B2DFDB")
        else:
            colors.append("#FFCDD2" if inc else "#FF5252")
    result.hist_colors = colors

    # ── Z-Score ───────────────────────────────────────────────────────────
    mean_h = hist.rolling(z_window).mean()
    std_h  = hist.rolling(z_window).std()
    z      = (hist - mean_h) / std_h.replace(0, 1e-10)
    result.z_score = z

    # Z-Score Farben (6-stufig, nur bei |z|>2):
    # Positiv: >2 = #A5D6A7, >3 = #66BB6A, >4 = #1B5E20
    # Negativ: >2 = #FFCDD2, >3 = #EF5350, >4 = #B71C1C
    z_colors = []
    for zv in z.values:
        za = abs(zv) if not np.isnan(zv) else 0
        if za > 4:
            z_colors.append("#1B5E20" if zv > 0 else "#B71C1C")
        elif za > 3:
            z_colors.append("#66BB6A" if zv > 0 else "#EF5350")
        elif za > 2:
            z_colors.append("#A5D6A7" if zv > 0 else "#FFCDD2")
        else:
            z_colors.append(None)
    result.z_colors = z_colors

    # ── ADX ───────────────────────────────────────────────────────────────
    adx, di_plus, di_minus = calculate_adx(high, low, close, adx_period)
    result.adx      = adx
    result.di_plus  = di_plus
    result.di_minus = di_minus

    # ── Cross-Signale ──────────────────────────────────────────────────────
    def _crossover_bool(s: pd.Series, lookback: int = 3) -> bool:
        """Letzte Kerze hat Signal-Linie von unten gekreuzt."""
        diff = macd - sig
        d = diff.dropna()
        if len(d) < lookback + 1:
            return False
        for i in range(1, lookback + 1):
            if float(d.iloc[-i-1]) < 0 <= float(d.iloc[-i]):
                return True
        return False

    def _crossunder_bool(lookback: int = 3) -> bool:
        diff = macd - sig
        d = diff.dropna()
        if len(d) < lookback + 1:
            return False
        for i in range(1, lookback + 1):
            if float(d.iloc[-i-1]) > 0 >= float(d.iloc[-i]):
                return True
        return False

    bull_cross = _crossover_bool(macd)
    bear_cross = _crossunder_bool()
    adx_cur    = float(adx.dropna().iloc[-1]) if len(adx.dropna()) > 0 else 0.0

    result.bull_cross = bull_cross
    result.bear_cross = bear_cross
    result.adx_val    = round(adx_cur, 1)
    result.bull_adx20 = bull_cross and 20 < adx_cur <= 40
    result.bear_adx20 = bear_cross and 20 < adx_cur <= 40
    result.bull_adx40 = bull_cross and adx_cur > 40
    result.bear_adx40 = bear_cross and adx_cur > 40

    # Alle historischen Crossover-Indizes (für Chart-Marker)
    diff_s = (macd - sig).reset_index(drop=True)
    adx_s  = adx.reset_index(drop=True)

    b20, br20, b40, br40 = [], [], [], []
    for i in range(1, len(diff_s)):
        if np.isnan(diff_s.iloc[i]) or np.isnan(adx_s.iloc[i]):
            continue
        adx_i = float(adx_s.iloc[i])
        is_bull = float(diff_s.iloc[i-1]) < 0 <= float(diff_s.iloc[i])
        is_bear = float(diff_s.iloc[i-1]) > 0 >= float(diff_s.iloc[i])
        if is_bull:
            if adx_i > 40:
                b40.append(i)
            elif adx_i > 20:
                b20.append(i)
        if is_bear:
            if adx_i > 40:
                br40.append(i)
            elif adx_i > 20:
                br20.append(i)

    result.bull_cross_20_idx = b20
    result.bear_cross_20_idx = br20
    result.bull_cross_40_idx = b40
    result.bear_cross_40_idx = br40

    # ── Aktuelle Werte ─────────────────────────────────────────────────────
    def _last(s: pd.Series) -> float:
        v = s.dropna()
        return float(v.iloc[-1]) if len(v) > 0 else 0.0

    result.macd_val   = round(_last(macd), 4)
    result.signal_val = round(_last(sig), 4)
    result.hist_val   = round(_last(hist), 4)
    result.z_val      = round(_last(z), 2)

    # Signal Stärke
    z_last = result.z_val
    if bull_cross and adx_cur > 40:
        result.signal_strength = "strong_bull"
    elif bull_cross and adx_cur > 20:
        result.signal_strength = "bull"
    elif bear_cross and adx_cur > 40:
        result.signal_strength = "strong_bear"
    elif bear_cross and adx_cur > 20:
        result.signal_strength = "bear"
    elif result.hist_val > 0 and abs(z_last) > 2:
        result.signal_strength = "bull"
    elif result.hist_val < 0 and abs(z_last) > 2:
        result.signal_strength = "bear"
    else:
        result.signal_strength = "neutral"

    return result


def calculate_stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series,
    k_period: int = 14, d_period: int = 3, smooth_k: int = 3
) -> Tuple[pd.Series, pd.Series]:
    """Einzelne Stochastik — TV-kompatibel (ta.stoch → SMA-Glättung)."""
    ll        = low.rolling(window=k_period).min()
    hh        = high.rolling(window=k_period).max()
    raw       = 100.0 * (close - ll) / (hh - ll + 1e-10)
    k         = raw.rolling(window=smooth_k).mean()
    d         = k.rolling(window=d_period).mean()
    return k, d


def calculate_dual_stochastic(
    high: pd.Series, low: pd.Series, close: pd.Series,
    include_series: bool = True,
) -> DualStochResult:
    """
    Stillhalter AI App — Dual Stochastic
    Portiert aus dem Pine Script (1:1 Logik).

    Schnell: k_len=14, smooth_k=3, smooth_d=3
    Langsam: k_len=35, smooth_k=10, smooth_d=5
    """
    result = DualStochResult()
    if len(close) < 40:
        return result

    # ── Schnelle Stochastik (14,3,3) ──────────────────────────────────────
    k1, d1 = calculate_stochastic(high, low, close, k_period=14, smooth_k=3, d_period=3)

    # ── Langsame Stochastik (35,10,5) ─────────────────────────────────────
    k2, d2 = calculate_stochastic(high, low, close, k_period=35, smooth_k=10, d_period=5)

    # Aktuelle Werte
    def _last(s: pd.Series) -> float:
        v = s.dropna()
        return float(v.iloc[-1]) if len(v) > 0 else 50.0

    fk = _last(k1);  fd = _last(d1)
    sk = _last(k2);  sd = _last(d2)

    result.fast_k = round(fk, 2)
    result.fast_d = round(fd, 2)
    result.slow_k = round(sk, 2)
    result.slow_d = round(sd, 2)

    # ── Crossover-Erkennung (Pine: ta.crossover/ta.crossunder) ────────────
    def _crossover(series: pd.Series, level: float, lookback: int = 2) -> bool:
        """series kreuzt level VON UNTEN — innerhalb der letzten lookback Kerzen."""
        s = series.dropna()
        if len(s) < lookback + 1:
            return False
        for i in range(1, lookback + 1):
            prev = float(s.iloc[-i-1])
            curr = float(s.iloc[-i])
            if prev < level <= curr:
                return True
        return False

    def _crossunder(series: pd.Series, level: float, lookback: int = 2) -> bool:
        """series kreuzt level VON OBEN."""
        s = series.dropna()
        if len(s) < lookback + 1:
            return False
        for i in range(1, lookback + 1):
            prev = float(s.iloc[-i-1])
            curr = float(s.iloc[-i])
            if prev > level >= curr:
                return True
        return False

    def _k_crossover_d(k: pd.Series, d: pd.Series, lookback: int = 2) -> bool:
        k2_ = k.dropna(); d2_ = d.dropna()
        n = min(len(k2_), len(d2_))
        if n < lookback + 1:
            return False
        k2_ = k2_.iloc[-n:]; d2_ = d2_.iloc[-n:]
        for i in range(1, lookback + 1):
            if float(k2_.iloc[-i-1]) < float(d2_.iloc[-i-1]) and \
               float(k2_.iloc[-i])   >= float(d2_.iloc[-i]):
                return True
        return False

    def _k_crossunder_d(k: pd.Series, d: pd.Series, lookback: int = 2) -> bool:
        k2_ = k.dropna(); d2_ = d.dropna()
        n = min(len(k2_), len(d2_))
        if n < lookback + 1:
            return False
        k2_ = k2_.iloc[-n:]; d2_ = d2_.iloc[-n:]
        for i in range(1, lookback + 1):
            if float(k2_.iloc[-i-1]) > float(d2_.iloc[-i-1]) and \
               float(k2_.iloc[-i])   <= float(d2_.iloc[-i]):
                return True
        return False

    # ── Schnelle Signale ──────────────────────────────────────────────────
    result.fast_oversold   = fk < 20
    result.fast_overbought = fk > 80
    result.fast_buy        = _crossover(k1, 20.0)
    result.fast_sell       = _crossunder(k1, 80.0)
    # readyBuy: %K < 20 UND %K kreuzt %D aufwärts
    result.fast_ready_buy  = fk < 20 and _k_crossover_d(k1, d1)
    # readySell: %K > 80 UND %K kreuzt %D abwärts
    result.fast_ready_sell = fk > 80 and _k_crossunder_d(k1, d1)

    # ── Langsame Signale ──────────────────────────────────────────────────
    result.slow_oversold   = sk < 20
    result.slow_overbought = sk > 80
    result.slow_buy        = _crossover(k2, 20.0)
    result.slow_sell       = _crossunder(k2, 80.0)
    result.slow_ready_buy  = sk < 20 and _k_crossover_d(k2, d2)
    result.slow_ready_sell = sk > 80 and _k_crossunder_d(k2, d2)

    # ── Kombiniertes Signal ───────────────────────────────────────────────
    result.both_oversold   = result.fast_oversold  and result.slow_oversold
    result.both_overbought = result.fast_overbought and result.slow_overbought

    if result.fast_ready_buy and result.slow_ready_buy:
        result.signal_strength = "strong_buy"
    elif result.fast_ready_buy or result.slow_ready_buy:
        result.signal_strength = "buy"
    elif result.fast_ready_sell and result.slow_ready_sell:
        result.signal_strength = "strong_sell"
    elif result.fast_ready_sell or result.slow_ready_sell:
        result.signal_strength = "sell"
    elif result.both_oversold:
        result.signal_strength = "buy"
    elif result.both_overbought:
        result.signal_strength = "sell"
    elif result.fast_oversold:
        result.signal_strength = "buy"
    elif result.fast_overbought:
        result.signal_strength = "sell"
    else:
        result.signal_strength = "neutral"

    # ── Zeitreihen für Chart ───────────────────────────────────────────────
    if include_series:
        result.fast_k_series = k1
        result.fast_d_series = d1
        result.slow_k_series = k2
        result.slow_d_series = d2

    return result


# ── Regression / S&R ───────────────────────────────────────────────────────────

def calculate_linear_regression_channel(
    close: pd.Series, period: int = 50, std_mult: float = 2.0
) -> Tuple[float, float, float]:
    if len(close) < period:
        period = len(close)
    y       = close.iloc[-period:].values
    x       = np.arange(period)
    coeffs  = np.polyfit(x, y, 1)
    fitted  = np.polyval(coeffs, x)
    std     = float(np.std(y - fitted))
    mid     = float(fitted[-1])
    return mid + std_mult * std, mid, mid - std_mult * std


@dataclass
class SRLevel:
    """Ein S/R-Level mit Metadaten für die Chart-Darstellung."""
    price:        float
    level_type:   str    # "support" | "resistance"
    strength:     int    # 1–5 Sterne (Anzahl Berührungen / Quellen kombiniert)
    source:       str    # "pivot" | "volume" | "round" | "yearly" | "mixed"
    distance_pct: float  # Abstand zum aktuellen Kurs in %
    label:        str    # Fertig formatierter Label-Text


def _sr_cluster(items: List[Tuple[float, int]], thr: float = 0.015) -> List[Tuple[float, int]]:
    """Fasst Preis-Levels innerhalb thr% zusammen, summiert Stärke."""
    if not items:
        return []
    items = sorted(items, key=lambda x: x[0])
    clusters: List[List[Tuple[float, int]]] = [[items[0]]]
    for price, strength in items[1:]:
        if abs(price - clusters[-1][-1][0]) / (clusters[-1][-1][0] + 1e-10) <= thr:
            clusters[-1].append((price, strength))
        else:
            clusters.append([(price, strength)])
    result = []
    for cl in clusters:
        avg_p = sum(p for p, _ in cl) / len(cl)
        tot_s = min(sum(s for _, s in cl), 25)
        result.append((round(avg_p, 2), tot_s))
    return result


def find_support_resistance(
    high: pd.Series, low: pd.Series, close: pd.Series,
    volume: Optional[pd.Series] = None,
    lookback: int = 250,
    n_levels: int = 8,
) -> Tuple[List[float], List[float]]:
    """
    Verbesserte S/R-Erkennung mit 4 Methoden, sortiert nach Nähe zum Kurs.
    Gibt (supports, resistances) als Preislisten zurück.
    """
    sr = find_sr_levels_with_strength(high, low, close, volume, lookback, n_levels)
    supports    = sorted([x.price for x in sr if x.level_type == "support"],    reverse=True)
    resistances = sorted([x.price for x in sr if x.level_type == "resistance"])
    return supports, resistances


def find_sr_levels_with_strength(
    high: pd.Series, low: pd.Series, close: pd.Series,
    volume: Optional[pd.Series] = None,
    lookback: int = 250,
    n_levels: int = 8,
) -> List["SRLevel"]:
    """
    4-Methoden S/R mit Stärke-Score und Nähe-Sortierung:
      1. Pivot Highs/Lows  (Fenster 3, 5, 10 Kerzen)
      2. Volume Profile     (Preise mit höchstem Volumen)
      3. Runde Zahlen       (psychologische Levels)
      4. 52-Wochen Hoch/Tief
    """
    if len(close) < 20:
        return []

    lb   = min(lookback, len(close))
    h    = high.iloc[-lb:].reset_index(drop=True)
    l    = low.iloc[-lb:].reset_index(drop=True)
    c    = close.iloc[-lb:].reset_index(drop=True)
    vol  = volume.iloc[-lb:].reset_index(drop=True) if volume is not None \
           else pd.Series(1.0, index=c.index)
    curr = float(close.iloc[-1])

    raw: List[Tuple[float, int]] = []   # (price, raw_strength)

    # ── 1. Pivot Hochs/Tiefs (3 Fenstergrößen) ────────────────────────────
    for win in [3, 5, 10]:
        for i in range(win, len(l) - win):
            seg_l = l.iloc[max(0, i - win): i + win + 1]
            seg_h = h.iloc[max(0, i - win): i + win + 1]
            if float(l.iloc[i]) <= float(seg_l.min()):
                raw.append((float(l.iloc[i]), win))          # Support
            if float(h.iloc[i]) >= float(seg_h.max()):
                raw.append((float(h.iloc[i]), win))          # Resistance

    # ── 2. Volume Profile (Top-15 Preis-Bins nach Volumen) ────────────────
    if float(vol.sum()) > 0:
        p_min = float(l.min())
        p_max = float(h.max())
        n_bins = 80
        bin_sz = max((p_max - p_min) / n_bins, 0.01)
        vbp: dict = {}
        for i in range(len(c)):
            b = round(p_min + int((float(c.iloc[i]) - p_min) / bin_sz) * bin_sz, 2)
            vbp[b] = vbp.get(b, 0.0) + float(vol.iloc[i])
        for bp, _ in sorted(vbp.items(), key=lambda x: x[1], reverse=True)[:15]:
            raw.append((bp, 9))   # Hohe Basisstärke

    # ── 3. Runde / Psychologische Levels ──────────────────────────────────
    inc = (100 if curr >= 500 else 50 if curr >= 200 else
           25  if curr >= 100 else 10 if curr >= 50  else
           5   if curr >= 20  else 2.5 if curr >= 10 else 1)
    lo = (float(l.min()) // inc) * inc
    hi = float(h.max()) * 1.02
    v_ = lo
    while v_ <= hi:
        raw.append((round(v_, 2), 4))
        v_ = round(v_ + inc, 10)

    # ── 4. 52-Wochen Hoch/Tief ────────────────────────────────────────────
    y52_hi = float(h.tail(min(252, len(h))).max())
    y52_lo = float(l.tail(min(252, len(l))).min())
    raw.append((y52_hi, 7))
    raw.append((y52_lo, 7))

    # ── Clustering ────────────────────────────────────────────────────────
    clustered = _sr_cluster(raw, thr=0.012)

    # ── Filtern & Scoring ─────────────────────────────────────────────────
    result: List[SRLevel] = []
    for price, strength in clustered:
        dist_pct = abs(price - curr) / (curr + 1e-10) * 100
        if dist_pct < 0.15:       # Zu nah am Kurs (< 0.15%) ignorieren
            continue
        if dist_pct > 40:         # Zu weit weg (> 40%) ignorieren
            continue
        ltype   = "support" if price < curr else "resistance"
        stars   = min(5, max(1, strength // 4))
        src     = "mixed" if strength > 12 else "pivot+vol" if strength > 7 else "level"
        emoji   = "🟢" if ltype == "support" else "🔴"
        label   = f"{emoji} {'S' if ltype == 'support' else 'R'} ${price:.2f} {'★' * stars}"
        result.append(SRLevel(
            price=round(price, 2),
            level_type=ltype,
            strength=stars,
            source=src,
            distance_pct=round(dist_pct, 1),
            label=label,
        ))

    # Sortiert: Nächste Levels zuerst
    result.sort(key=lambda x: x.distance_pct)
    # Max n_levels Supports + n_levels Resistances
    sup = [x for x in result if x.level_type == "support"][:n_levels]
    res = [x for x in result if x.level_type == "resistance"][:n_levels]
    return sup + res


def get_trend_score(close: pd.Series) -> Tuple[float, str]:
    if len(close) < 10:
        return 50.0, "neutral"
    score   = 50.0
    current = float(close.iloc[-1])
    sma50   = float(calculate_sma(close, 50).iloc[-1])
    sma200  = float(calculate_sma(close, min(200, len(close))).iloc[-1])

    score += 15 if current > sma50  else -15
    score += 15 if current > sma200 else -15
    score += 10 if sma50   > sma200 else -10

    if len(close) >= 20:
        perf = (current / float(close.iloc[-20]) - 1) * 100
        score += 10 if perf > 5 else (5 if perf > 0 else (-10 if perf < -5 else -5))

    score = max(0.0, min(100.0, score))
    trend = "bullish" if score >= 65 else ("bearish" if score <= 35 else "neutral")
    return score, trend


# ── Haupt-Analyse ──────────────────────────────────────────────────────────────

def analyze_technicals(df: pd.DataFrame) -> Optional[TechSignal]:
    if df is None or df.empty or len(df) < 20:
        return None

    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]
    current_price = float(close.iloc[-1])

    # ── Stillhalter MACD Pro (10/35/5) ────────────────────────────────────
    sc_macd = calculate_stillhalter_macd(close, high, low)

    # Legacy macd_signal aus SC MACD
    if sc_macd.signal_strength in ("strong_bull", "bull"):
        macd_signal = "bullish"
    elif sc_macd.signal_strength in ("strong_bear", "bear"):
        macd_signal = "bearish"
    else:
        macd_signal = "neutral"

    # ── Dual Stochastic ────────────────────────────────────────────────────
    dual_stoch = calculate_dual_stochastic(high, low, close, include_series=True)
    fk = dual_stoch.fast_k
    fd = dual_stoch.fast_d

    # Legacy stoch_signal aus schneller Stochastik
    if dual_stoch.fast_ready_buy:
        stoch_signal = "oversold"
    elif dual_stoch.fast_ready_sell:
        stoch_signal = "overbought"
    elif fk > fd:
        stoch_signal = "bullish"
    else:
        stoch_signal = "bearish"

    # ── Trend ─────────────────────────────────────────────────────────────
    trend_score, trend = get_trend_score(close)
    sma50  = float(calculate_sma(close, 50).iloc[-1])
    sma200 = float(calculate_sma(close, min(200, len(close))).iloc[-1])

    # ── Trendkanal ────────────────────────────────────────────────────────
    try:
        ch_upper, ch_mid, ch_lower = calculate_linear_regression_channel(close)
    except Exception:
        ch_upper = ch_mid = ch_lower = None

    # ── Support / Resistance (mit Volume) ────────────────────────────────
    try:
        vol_series = df["Volume"] if "Volume" in df.columns else None
        supports, resistances = find_support_resistance(
            high, low, close, volume=vol_series, lookback=250, n_levels=8
        )
    except Exception:
        supports, resistances = [], []

    # ── Zusammenfassung ───────────────────────────────────────────────────
    parts = []
    parts.append({"bullish": "Aufwärtstrend", "bearish": "Abwärtstrend"}.get(trend, "Seitwärtstrend"))
    if macd_signal != "neutral":
        parts.append(f"MACD {macd_signal}")

    ss = dual_stoch.signal_strength
    if ss == "strong_buy":
        parts.append("Dual Stoch: STARK ÜBERVERKAUFT 🟢🟢")
    elif ss == "buy":
        parts.append("Dual Stoch: überverkauft 🟢")
    elif ss == "strong_sell":
        parts.append("Dual Stoch: STARK ÜBERKAUFT 🔴🔴")
    elif ss == "sell":
        parts.append("Dual Stoch: überkauft 🔴")

    # MACD-Stärke in Summary aufnehmen
    ms = sc_macd.signal_strength
    if ms == "strong_bull":
        parts.append(f"SC MACD Pro: STARK BULLISH 🟢🟢 (ADX {sc_macd.adx_val:.0f})")
    elif ms == "bull":
        parts.append(f"SC MACD Pro: bullish 🟢 (ADX {sc_macd.adx_val:.0f})")
    elif ms == "strong_bear":
        parts.append(f"SC MACD Pro: STARK BEARISH 🔴🔴 (ADX {sc_macd.adx_val:.0f})")
    elif ms == "bear":
        parts.append(f"SC MACD Pro: bearish 🔴 (ADX {sc_macd.adx_val:.0f})")

    return TechSignal(
        trend=trend,
        trend_score=trend_score,
        macd_signal=macd_signal,
        stoch_signal=stoch_signal,
        stoch_k=fk,
        stoch_d=fd,
        dual_stoch=dual_stoch,
        sc_macd=sc_macd,
        support_levels=supports,
        resistance_levels=resistances,
        channel_upper=ch_upper,
        channel_lower=ch_lower,
        channel_mid=ch_mid,
        above_sma50=current_price > sma50,
        above_sma200=current_price > sma200,
        summary=" | ".join(parts),
    )
