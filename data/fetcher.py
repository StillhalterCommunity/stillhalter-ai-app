"""
Yahoo Finance Daten-Fetcher mit Caching.
Holt Options Chains, Kurshistorie, Stock-Info, Fundamentaldaten, News.
"""

import yfinance as yf
import pandas as pd
import numpy as np
import streamlit as st
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import pytz


# ── Marktzeiten ──────────────────────────────────────────────────────────────

def is_market_open() -> bool:
    """Prüft ob US-Markt aktuell geöffnet ist (Mon–Fri 9:30–16:00 ET)."""
    et = pytz.timezone("America/New_York")
    now = datetime.now(et)
    if now.weekday() >= 5:
        return False
    market_open = now.replace(hour=9, minute=30, second=0, microsecond=0)
    market_close = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return market_open <= now <= market_close


def market_status_text() -> str:
    et = pytz.timezone("America/New_York")
    now = datetime.now(et)
    if is_market_open():
        return f"🟢 Markt geöffnet (ET {now.strftime('%H:%M')})"
    else:
        return f"🔴 Markt geschlossen (ET {now.strftime('%H:%M')}) — Preise evtl. veraltet"


# ── Kurshistorie ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_price_history(ticker: str, period: str = "1y") -> pd.DataFrame:
    """Holt OHLCV-Daten für technische Analyse."""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=period)
        if df.empty:
            return pd.DataFrame()
        df.index = pd.to_datetime(df.index)
        return df[["Open", "High", "Low", "Close", "Volume"]].copy()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def fetch_stock_info(ticker: str) -> dict:
    """Holt aktuellen Kurs + Basisinfos."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        hist = stock.history(period="2d")
        current_price = float(hist["Close"].iloc[-1]) if not hist.empty else None
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else info.get("previousClose")
        return {
            "ticker": ticker,
            "name": info.get("longName", info.get("shortName", ticker)),
            "price": current_price,
            "prev_close": prev_close,
            "market_cap": info.get("marketCap"),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "beta": info.get("beta"),
            "avg_volume": info.get("averageVolume"),
            "country": info.get("country", ""),
            "website": info.get("website", ""),
            "description": info.get("longBusinessSummary", ""),
        }
    except Exception:
        return {"ticker": ticker, "name": ticker, "price": None}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_fundamentals(ticker: str) -> dict:
    """Holt Fundamentaldaten: P/E, EPS, Wachstum, PEG, Dividende, Earnings, News."""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info

        # Earnings-Datum
        earnings_date = None
        try:
            cal = stock.calendar
            if cal is not None and not (isinstance(cal, pd.DataFrame) and cal.empty):
                if isinstance(cal, dict) and "Earnings Date" in cal:
                    dates = cal["Earnings Date"]
                    if dates:
                        earnings_date = dates[0] if isinstance(dates, list) else dates
                elif isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.columns:
                    earnings_date = cal["Earnings Date"].iloc[0]
        except Exception:
            pass

        # News
        news = []
        try:
            raw_news = stock.news or []
            for item in raw_news[:8]:
                news.append({
                    "title": item.get("title", ""),
                    "publisher": item.get("publisher", ""),
                    "link": item.get("link", ""),
                    "time": datetime.fromtimestamp(item.get("providerPublishTime", 0)).strftime("%d.%m.%Y %H:%M")
                    if item.get("providerPublishTime") else "",
                })
        except Exception:
            pass

        # PEG manuell berechnen falls nicht vorhanden
        pe = info.get("trailingPE")
        growth = info.get("earningsGrowth")
        peg = info.get("pegRatio")
        if peg is None and pe and growth and growth > 0:
            peg = pe / (growth * 100)

        return {
            # Bewertung
            "pe_trailing": info.get("trailingPE"),
            "pe_forward": info.get("forwardPE"),
            "eps_trailing": info.get("trailingEps"),
            "eps_forward": info.get("forwardEps"),
            "price_to_book": info.get("priceToBook"),
            "price_to_sales": info.get("priceToSalesTrailing12Months"),
            # Wachstum
            "earnings_growth_qoq": info.get("earningsQuarterlyGrowth"),
            "earnings_growth_yoy": info.get("earningsGrowth"),
            "revenue_growth": info.get("revenueGrowth"),
            "eps_growth_next_year": info.get("earningsGrowth"),  # Proxy
            # PEG
            "peg_ratio": peg,
            # Dividende
            "dividend_yield": info.get("dividendYield"),
            "dividend_rate": info.get("dividendRate"),
            "payout_ratio": info.get("payoutRatio"),
            # Finanzkraft
            "debt_to_equity": info.get("debtToEquity"),
            "current_ratio": info.get("currentRatio"),
            "return_on_equity": info.get("returnOnEquity"),
            "profit_margin": info.get("profitMargins"),
            "free_cashflow": info.get("freeCashflow"),
            # Earnings + News
            "earnings_date": earnings_date,
            "news": news,
            # 52W
            "week_52_high": info.get("fiftyTwoWeekHigh"),
            "week_52_low": info.get("fiftyTwoWeekLow"),
            "target_price": info.get("targetMeanPrice"),
            "analyst_rating": info.get("recommendationKey", "").upper(),
            "num_analysts": info.get("numberOfAnalystOpinions"),
        }
    except Exception as e:
        return {"news": [], "earnings_date": None}


# ── Options Chain ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=900, show_spinner=False)
def fetch_options_chain(ticker: str) -> tuple:
    """
    Holt vollständige Options Chain.
    Gibt zurück: (puts_df, calls_df, expirations_list)
    Funktioniert auch außerhalb der Börsenzeiten (nutzt lastPrice als Fallback).
    """
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options
        if not expirations:
            return pd.DataFrame(), pd.DataFrame(), []

        all_puts, all_calls = [], []

        for exp in expirations:
            try:
                chain = stock.option_chain(exp)

                puts = chain.puts.copy()
                if not puts.empty:
                    puts["expiration"] = exp
                    puts["option_type"] = "put"
                    # Off-Hours Fix: Verwende lastPrice wenn bid+ask = 0
                    puts = _fix_off_hours_prices(puts)
                    all_puts.append(puts)

                calls = chain.calls.copy()
                if not calls.empty:
                    calls["expiration"] = exp
                    calls["option_type"] = "call"
                    calls = _fix_off_hours_prices(calls)
                    all_calls.append(calls)
            except Exception:
                continue

        puts_df = pd.concat(all_puts, ignore_index=True) if all_puts else pd.DataFrame()
        calls_df = pd.concat(all_calls, ignore_index=True) if all_calls else pd.DataFrame()

        return puts_df, calls_df, list(expirations)

    except Exception:
        return pd.DataFrame(), pd.DataFrame(), []


def _fix_off_hours_prices(df: pd.DataFrame) -> pd.DataFrame:
    """
    Außerhalb der Börsenzeiten sind bid/ask oft 0.
    Nutze lastPrice als Fallback, damit Optionen trotzdem angezeigt werden.
    """
    df = df.copy()
    if "bid" not in df.columns:
        df["bid"] = 0.0
    if "ask" not in df.columns:
        df["ask"] = 0.0
    if "lastPrice" not in df.columns:
        df["lastPrice"] = 0.0

    df["bid"] = pd.to_numeric(df["bid"], errors="coerce").fillna(0)
    df["ask"] = pd.to_numeric(df["ask"], errors="coerce").fillna(0)
    df["lastPrice"] = pd.to_numeric(df["lastPrice"], errors="coerce").fillna(0)

    # Berechne mid_price direkt hier
    def safe_mid(row):
        b, a, last = row["bid"], row["ask"], row["lastPrice"]
        if b > 0 and a > 0 and a > b:
            return (b + a) / 2
        elif last > 0:
            return last
        elif a > 0:
            return a
        return 0.0

    df["mid_price"] = df.apply(safe_mid, axis=1)
    return df


@st.cache_data(ttl=1800, show_spinner=False)
def fetch_batch_prices(tickers: tuple) -> Dict[str, Optional[float]]:
    """Holt aktuelle Kurse für mehrere Ticker auf einmal."""
    try:
        data = yf.download(list(tickers), period="2d", progress=False, auto_adjust=True)
        prices = {}
        if isinstance(data.columns, pd.MultiIndex):
            close = data["Close"]
            for t in tickers:
                if t in close.columns:
                    prices[t] = float(close[t].dropna().iloc[-1]) if not close[t].dropna().empty else None
                else:
                    prices[t] = None
        else:
            prices[tickers[0]] = float(data["Close"].dropna().iloc[-1]) if not data["Close"].dropna().empty else None
        return prices
    except Exception:
        return {t: None for t in tickers}


def calculate_dte(expiration_str: str) -> int:
    """Berechnet Days to Expiration ab heute."""
    try:
        exp_date = datetime.strptime(expiration_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        return max(0, (exp_date - today).days)
    except Exception:
        return 0
