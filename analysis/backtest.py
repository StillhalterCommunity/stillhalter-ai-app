"""
Stillhalter Community — Options Backtest Engine
Simuliert historische Stillhalter-Strategien auf Basis des SC Trend Models.

Methodik:
  - Einstieg: SC Trend Signal (bullish/cross) aus historischen Daten
  - Strike: Berechnung über Black-Scholes Delta-Targeting + historische Volatilität
  - Prämie: Black-Scholes Theoretischer Preis zum Einstiegsdatum
  - Ausstieg: Verfall (DTE Tage) — Kurs > Strike → Gewinn | Kurs < Strike → Verlust
  - Keine echten historischen Optionspreise verfügbar → Simulation
"""

import numpy as np
import pandas as pd
from scipy.stats import norm
from dataclasses import dataclass, field
from typing import Optional, List
import streamlit as st
import yfinance as yf

from analysis.multi_timeframe import TREND_MODES, DEFAULT_TREND_MODE
from analysis.technicals import calculate_ema


# ── Black-Scholes Funktionen ───────────────────────────────────────────────────

def _bs_put_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes Preis für einen europäischen Put."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
    return max(float(price), 0.0)


def _bs_call_price(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes Preis für einen europäischen Call."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return max(float(price), 0.0)


def _put_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes Delta für Short Put (negativ)."""
    if T <= 0 or sigma <= 0:
        return -0.5
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d1) - 1)


def _call_delta(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """Black-Scholes Delta für Short Call (positiv)."""
    if T <= 0 or sigma <= 0:
        return 0.5
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    return float(norm.cdf(d1))


def _strike_from_delta(
    S: float, T: float, r: float, sigma: float,
    target_delta: float, option_type: str = "put"
) -> float:
    """
    Berechnet den Strike, der dem Ziel-Delta entspricht.
    Für Put: target_delta negativ (z.B. -0.25)
    Für Call: target_delta positiv (z.B. 0.25)
    """
    if sigma <= 0 or T <= 0:
        return S
    if option_type == "put":
        # N(-d1) = |target_delta|  →  d1 = N_inv(1 - |target_delta|)
        abs_d = abs(target_delta)
        d1_target = norm.ppf(1.0 - abs_d)
    else:
        # N(d1) = target_delta
        d1_target = norm.ppf(target_delta)

    # d1 = (ln(S/K) + (r + σ²/2)*T) / (σ*√T)
    # ln(S/K) = d1*σ*√T - (r + σ²/2)*T
    log_SK = d1_target * sigma * np.sqrt(T) - (r + 0.5 * sigma ** 2) * T
    K = S * np.exp(-log_SK)
    return round(float(K), 2)


def _hist_vol(close: pd.Series, window: int = 20) -> pd.Series:
    """Annualisierte historische Volatilität (20-Tage Fenster)."""
    log_ret = np.log(close / close.shift(1))
    return log_ret.rolling(window).std() * np.sqrt(252)


# ── Trade Dataclass ────────────────────────────────────────────────────────────

@dataclass
class BacktestTrade:
    entry_date: str
    expiry_date: str
    strategy: str           # "Cash Covered Put" | "Covered Call"
    stock_price_entry: float
    strike: float
    premium: float          # simulierter B-S Preis
    delta_entry: float
    iv_entry: float         # historische Vola zum Einstieg
    dte: int
    stock_price_expiry: float
    itm_at_expiry: bool     # True = In-the-money bei Verfall (Verlust)
    pnl_per_share: float    # P&L pro Aktie
    pnl_pct: float          # P&L als % des Strikes (eingesetztes Kapital)
    pnl_annualized: float   # Annualisiert
    result: str             # "Gewinn (verfallen)" | "Verlust (assignment)" | "Gewinn (teilw.)"
    trend_signal: str       # welches Signal zum Einstieg genutzt wurde


@dataclass
class BacktestResult:
    ticker: str
    strategy: str
    trend_mode: str
    signal_type: str
    target_delta: float
    dte: int
    period: str

    trades: List[BacktestTrade] = field(default_factory=list)
    n_trades: int = 0
    n_wins: int = 0
    n_losses: int = 0
    win_rate: float = 0.0

    total_return_pct: float = 0.0     # Summe aller Trade-Returns
    avg_return_pct: float = 0.0       # Ø Return pro Trade
    avg_win_pct: float = 0.0
    avg_loss_pct: float = 0.0
    best_trade_pct: float = 0.0
    worst_trade_pct: float = 0.0
    max_drawdown_pct: float = 0.0
    profit_factor: float = 0.0        # Summe Gewinne / Summe Verluste
    avg_annualized_pct: float = 0.0

    equity_curve: pd.Series = field(default_factory=pd.Series)
    trade_df: pd.DataFrame = field(default_factory=pd.DataFrame)
    error: str = ""


# ── Backtesting Engine ─────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def run_backtest(
    ticker: str,
    strategy: str = "Cash Covered Put",
    trend_mode: str = "Very Tight",
    signal_type: str = "SC Trend Cross ↑",
    target_delta: float = 0.25,
    dte: int = 30,
    period: str = "3y",
    risk_free_rate: float = 0.05,
    min_iv: float = 0.10,
) -> BacktestResult:
    """
    Backtestet eine Stillhalter-Strategie auf historischen Daten.

    signal_type: Wann wird ein Trade eröffnet?
      - "SC Trend Cross ↑"    : SC Trend wechselt von bearish → bullish (Kaufsignal)
      - "SC Trend bullish"    : SC Trend ist bullish (jede Kerze, max 1 Trade/Monat)
      - "RSI < 30 + SC Trend" : RSI überverkauft + SC Trend bullish
      - "Stoch Cross 20 ↑"    : Stochastik kreuzt 20 aufwärts
    """
    result = BacktestResult(
        ticker=ticker, strategy=strategy, trend_mode=trend_mode,
        signal_type=signal_type, target_delta=target_delta, dte=dte, period=period
    )

    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period, interval="1d")
        if df.empty or len(df) < 60:
            result.error = "Zu wenig historische Daten"
            return result
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df.index = pd.to_datetime(df.index).tz_localize(None)
    except Exception as e:
        result.error = f"Datenfehler: {e}"
        return result

    # ── Indikatoren berechnen ──────────────────────────────────────────────
    fast_len, slow_len = TREND_MODES.get(trend_mode, (2, 9))
    close = df["Close"]
    high  = df["High"]
    low   = df["Low"]

    fast_ema = calculate_ema(close, fast_len)
    slow_ema = calculate_ema(close, slow_len)
    sc_bullish = fast_ema > slow_ema                    # True = Aufwärtstrend
    sc_cross_up = sc_bullish & (~sc_bullish.shift(1).fillna(False))  # Crossover

    # RSI (14)
    delta_c = close.diff()
    gain = delta_c.clip(lower=0).ewm(alpha=1/14, min_periods=14).mean()
    loss = (-delta_c).clip(lower=0).ewm(alpha=1/14, min_periods=14).mean()
    rsi = 100 - 100 / (1 + gain / loss.replace(0, 1e-10))

    # Stochastik (14,3,3)
    ll = low.rolling(14).min()
    hh = high.rolling(14).max()
    stoch_k_raw = 100 * (close - ll) / (hh - ll + 1e-10)
    stoch_k = stoch_k_raw.rolling(3).mean()
    stoch_cross_20_up = (stoch_k >= 20) & (stoch_k.shift(1) < 20)

    # Historische Volatilität
    hvol = _hist_vol(close, 20).fillna(method="bfill").clip(lower=min_iv, upper=2.0)

    # ── Einstiegs-Signale bestimmen ────────────────────────────────────────
    if signal_type == "SC Trend Cross ↑":
        signal = sc_cross_up
    elif signal_type == "SC Trend bullish":
        # Maximal 1 Trade pro Monat (kein Signal wenn bereits im Trade)
        signal = sc_bullish
    elif signal_type == "RSI < 30 + SC Trend":
        signal = (rsi < 30) & sc_bullish
    elif signal_type == "Stoch Cross 20 ↑":
        signal = stoch_cross_20_up & sc_bullish
    else:
        signal = sc_cross_up

    # ── Trade-Simulation ───────────────────────────────────────────────────
    T_years = dte / 365.0
    opt_type = "call" if strategy == "Covered Call" else "put"
    # Vorzeichen des Deltas
    tgt_delta = target_delta if opt_type == "call" else -target_delta

    trades: List[BacktestTrade] = []
    last_trade_end_idx = -1  # Verhindert überlappende Trades

    dates_arr = df.index.tolist()

    for i, date in enumerate(dates_arr):
        if i < 20 or i >= len(dates_arr) - dte:
            continue
        if i <= last_trade_end_idx:
            continue
        if not bool(signal.iloc[i]):
            continue

        S = float(close.iloc[i])
        iv = float(hvol.iloc[i])
        if iv < min_iv:
            iv = min_iv

        # Strike berechnen
        K = _strike_from_delta(S, T_years, risk_free_rate, iv, tgt_delta, opt_type)

        # Theoretische Prämie (B-S)
        if opt_type == "put":
            premium = _bs_put_price(S, K, T_years, risk_free_rate, iv)
            actual_delta = _put_delta(S, K, T_years, risk_free_rate, iv)
        else:
            premium = _bs_call_price(S, K, T_years, risk_free_rate, iv)
            actual_delta = _call_delta(S, K, T_years, risk_free_rate, iv)

        if premium < 0.01:
            continue

        # Verfallsdatum suchen
        expiry_idx = i + dte
        if expiry_idx >= len(dates_arr):
            break
        expiry_date = dates_arr[expiry_idx]
        S_expiry = float(close.iloc[expiry_idx])

        # P&L berechnen
        if opt_type == "put":
            itm = S_expiry < K
            if not itm:
                # Option verfallen → volle Prämie
                pnl = premium
                res = "✅ Gewinn (verfallen)"
            else:
                # Assignment
                pnl = premium - (K - S_expiry)
                res = "❌ Verlust (Assignment)" if pnl < 0 else "⚠️ Gewinn (teilw.)"
        else:  # covered call
            itm = S_expiry > K
            if not itm:
                pnl = premium
                res = "✅ Gewinn (verfallen)"
            else:
                pnl = premium - (S_expiry - K)
                res = "❌ Verlust (Assignment)" if pnl < 0 else "⚠️ Gewinn (teilw.)"

        pnl_pct = (pnl / K) * 100
        pnl_ann = pnl_pct * (365 / dte)

        trades.append(BacktestTrade(
            entry_date=date.strftime("%Y-%m-%d"),
            expiry_date=expiry_date.strftime("%Y-%m-%d"),
            strategy=strategy,
            stock_price_entry=round(S, 2),
            strike=round(K, 2),
            premium=round(premium, 2),
            delta_entry=round(actual_delta, 3),
            iv_entry=round(iv * 100, 1),
            dte=dte,
            stock_price_expiry=round(S_expiry, 2),
            itm_at_expiry=itm,
            pnl_per_share=round(pnl, 2),
            pnl_pct=round(pnl_pct, 2),
            pnl_annualized=round(pnl_ann, 1),
            result=res,
            trend_signal=signal_type,
        ))
        last_trade_end_idx = expiry_idx

    if not trades:
        result.error = "Keine Trades generiert — Signal-Typ oder Zeitraum anpassen."
        return result

    # ── Statistiken berechnen ──────────────────────────────────────────────
    result.trades = trades
    result.n_trades = len(trades)
    result.n_wins = sum(1 for t in trades if t.pnl_per_share >= 0)
    result.n_losses = result.n_trades - result.n_wins
    result.win_rate = result.n_wins / result.n_trades * 100

    pnl_pcts = [t.pnl_pct for t in trades]
    result.total_return_pct = round(sum(pnl_pcts), 2)
    result.avg_return_pct   = round(np.mean(pnl_pcts), 2)
    result.best_trade_pct   = round(max(pnl_pcts), 2)
    result.worst_trade_pct  = round(min(pnl_pcts), 2)

    wins  = [p for p in pnl_pcts if p >= 0]
    losses = [p for p in pnl_pcts if p < 0]
    result.avg_win_pct  = round(np.mean(wins), 2)  if wins   else 0.0
    result.avg_loss_pct = round(np.mean(losses), 2) if losses else 0.0
    result.avg_annualized_pct = round(np.mean([t.pnl_annualized for t in trades]), 1)

    sum_wins   = sum(wins)
    sum_losses = abs(sum(losses)) or 1e-6
    result.profit_factor = round(sum_wins / sum_losses, 2)

    # Equity-Kurve (kumulierter Return)
    equity = pd.Series(
        data=[100.0] + [100.0 + sum(pnl_pcts[:i+1]) for i in range(len(pnl_pcts))],
        index=pd.to_datetime([trades[0].entry_date] + [t.expiry_date for t in trades]),
    )
    result.equity_curve = equity

    # Max Drawdown
    peak = equity.cummax()
    dd = (equity - peak) / peak * 100
    result.max_drawdown_pct = round(float(dd.min()), 2)

    # Trade-DataFrame
    result.trade_df = pd.DataFrame([{
        "Einstieg":    t.entry_date,
        "Verfall":     t.expiry_date,
        "Kurs Einstieg": t.stock_price_entry,
        "Strike":      t.strike,
        "Prämie":      t.premium,
        "Delta":       t.delta_entry,
        "IV %":        t.iv_entry,
        "Kurs Verfall": t.stock_price_expiry,
        "P&L/Aktie":   t.pnl_per_share,
        "Rendite %":   t.pnl_pct,
        "Ann. %":      t.pnl_annualized,
        "Ergebnis":    t.result,
    } for t in trades])

    result.n_trades = len(trades)
    return result
