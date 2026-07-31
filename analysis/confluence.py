"""
Stillhalter Confluence — Python-Port des TradingView-Indikators (v0.9).

Identische Logik wie pine/stillhalter_confluence.pine (dort gegeneinander
validiert): Trend Model (EMA 2/9) + MACD Pro (10/35/5, Hist-Nulldurchgang)
+ Dual Stochastic (14,3,3 bricht 20/80, während 35,10,5 überverkauft/-kauft),
Konfluenz-Fenster (Ereignis zählt, solange frisch UND Zustand gilt).

confluence_now(df, win)   → Scores/Zustände der LETZTEN Kerze
confluence_for(ticker, tf) → holt Kursdaten der Zeitebene (4h/1D/1W) und
                             bewertet die aktuelle Lage (gecacht).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st


def _since(evt: pd.Series) -> pd.Series:
    idx = np.arange(len(evt))
    last = pd.Series(np.where(evt.values, idx, np.nan), index=evt.index).ffill()
    return pd.Series(idx, index=evt.index) - last


def confluence_now(df: pd.DataFrame, win: int = 3,
                   os_level: int = 20, ob_level: int = 80) -> dict:
    """Bewertet die letzte Kerze. Erwartet Spalten High/Low/Close.
    Rückgabe: buy_score/sell_score (0–3), Komponenten-Flags, frische Trigger."""
    if df is None or len(df) < 40:
        return {}
    c, h, l = df["Close"], df["High"], df["Low"]

    # Trend Model (Very Tight 2/9)
    ef = c.ewm(span=2, adjust=False).mean()
    es = c.ewm(span=9, adjust=False).mean()
    bull, bear = ef > es, ef < es
    t_buy_evt  = bull & ~bull.shift(1).fillna(False)
    t_sell_evt = bear & ~bear.shift(1).fillna(False)

    # MACD Pro 10/35/5
    macd = c.ewm(span=10, adjust=False).mean() - c.ewm(span=35, adjust=False).mean()
    hist = macd - macd.ewm(span=5, adjust=False).mean()
    m_buy_evt  = (hist > 0) & (hist.shift(1) <= 0)
    m_sell_evt = (hist < 0) & (hist.shift(1) >= 0)

    # Dual Stochastic
    def _k(length, smooth):
        ll = l.rolling(length).min()
        hh = h.rolling(length).max()
        return (100 * (c - ll) / (hh - ll)).rolling(smooth).mean()
    k1, k2 = _k(14, 3), _k(35, 10)
    s_buy_evt  = (k1 > os_level) & (k1.shift(1) <= os_level) & (k2 < os_level)
    s_sell_evt = (k1 < ob_level) & (k1.shift(1) >= ob_level) & (k2 > ob_level)

    t_b = bool((bull & (_since(t_buy_evt) < win)).iloc[-1])
    m_b = bool(((hist > 0) & (_since(m_buy_evt) < win)).iloc[-1])
    s_b = bool((_since(s_buy_evt) < win).iloc[-1])
    t_s = bool((bear & (_since(t_sell_evt) < win)).iloc[-1])
    m_s = bool(((hist < 0) & (_since(m_sell_evt) < win)).iloc[-1])
    s_s = bool((_since(s_sell_evt) < win).iloc[-1])

    return {
        "buy_score":  int(t_b) + int(m_b) + int(s_b),
        "sell_score": int(t_s) + int(m_s) + int(s_s),
        "trend_buy": t_b, "macd_buy": m_b, "stoch_buy": s_b,
        "trend_sell": t_s, "macd_sell": m_s, "stoch_sell": s_s,
        "fresh_buy_evt":  bool((t_buy_evt | m_buy_evt | s_buy_evt).iloc[-max(1, win):].any()),
        "fresh_sell_evt": bool((t_sell_evt | m_sell_evt | s_sell_evt).iloc[-max(1, win):].any()),
    }


@st.cache_data(ttl=900, show_spinner=False)
def confluence_for(ticker: str, tf: str = "1D", win: int = 3) -> dict:
    """Confluence-Lage eines Tickers auf einer Zeitebene ('4h'|'1D'|'1W')."""
    try:
        from analysis.multi_timeframe import _fetch_tf_data, _resample_to_4h
        if tf == "4h":
            df = _resample_to_4h(_fetch_tf_data(ticker, "1h", "60d"))
        elif tf == "1W":
            df = _fetch_tf_data(ticker, "1wk", "5y")
        else:
            df = _fetch_tf_data(ticker, "1d", "2y")
        if df is None or df.empty:
            return {}
        return confluence_now(df, win=win)
    except Exception:
        return {}


def ampel(score: int) -> str:
    return "🟢" * min(score, 3) + "⚪" * max(0, 3 - score)
