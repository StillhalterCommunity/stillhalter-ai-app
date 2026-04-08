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


def get_extended_hours_session() -> Optional[str]:
    """
    Gibt die aktuelle Extended-Hours-Session zurück.
    Pre-Market:  04:00–09:30 ET → 'pre'
    After-Hours: 16:00–20:00 ET → 'post'
    Wochenende:                  → None
    Markt offen:                 → None
    """
    et = pytz.timezone("America/New_York")
    now = datetime.now(et)
    if now.weekday() >= 5:
        return None
    h, m = now.hour, now.minute
    t = h * 60 + m
    if 4 * 60 <= t < 9 * 60 + 30:
        return "pre"
    if 16 * 60 <= t < 20 * 60:
        return "post"
    return None


@st.cache_data(ttl=120, show_spinner=False)
def fetch_extended_hours_price(ticker: str) -> dict:
    """
    Holt den vorbörslichen oder nachbörslichen Kurs via yfinance (1-Minuten-Daten).
    Gibt dict zurück mit: price, prev_close, change, change_pct, session, time_str
    Liefert leeres Dict wenn kein Extended-Hours-Handel läuft oder keine Daten.
    """
    session = get_extended_hours_session()
    if not session:
        return {}

    try:
        stock  = yf.Ticker(ticker)
        # 1-Minuten-Daten des heutigen Tages inkl. Pre/Post-Market
        hist   = stock.history(period="1d", interval="1m", prePost=True)

        if hist.empty:
            return {}

        et = pytz.timezone("America/New_York")
        hist.index = hist.index.tz_convert(et)
        now = datetime.now(et)

        if session == "pre":
            # Pre-Market: 04:00–09:29 ET
            session_start = now.replace(hour=4,  minute=0,  second=0, microsecond=0)
            session_end   = now.replace(hour=9,  minute=29, second=59, microsecond=0)
            label = "VORBÖRSLICH"
            label_color = "#a78bfa"   # lila
        else:
            # After-Hours: 16:00–20:00 ET
            session_start = now.replace(hour=16, minute=0,  second=0, microsecond=0)
            session_end   = now.replace(hour=20, minute=0,  second=59, microsecond=0)
            label = "NACHBÖRSLICH"
            label_color = "#60a5fa"   # blau

        mask = (hist.index >= session_start) & (hist.index <= session_end)
        session_data = hist[mask]

        if session_data.empty:
            return {}

        ext_price  = float(session_data["Close"].iloc[-1])
        ext_time   = session_data.index[-1].strftime("%H:%M ET")

        # Vortagesschluss (reguläre Session)
        reg_mask  = (hist.index >= now.replace(hour=9, minute=30, second=0, microsecond=0)) & \
                    (hist.index <  now.replace(hour=16, minute=0,  second=0, microsecond=0))
        reg_data  = hist[reg_mask]
        if not reg_data.empty:
            prev_close = float(reg_data["Close"].iloc[-1])
        else:
            # Fallback: letzter Tagesschluss aus 2-Tages-History
            d2 = stock.history(period="2d")
            prev_close = float(d2["Close"].iloc[-1]) if not d2.empty else ext_price

        change     = ext_price - prev_close
        change_pct = change / prev_close * 100 if prev_close else 0.0

        return {
            "price":      round(ext_price, 2),
            "prev_close": round(prev_close, 2),
            "change":     round(change, 2),
            "change_pct": round(change_pct, 2),
            "session":    session,
            "label":      label,
            "label_color": label_color,
            "time_str":   ext_time,
        }

    except Exception:
        return {}


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
def fetch_options_chain(
    ticker: str,
    dte_min: int = 0,
    dte_max: int = 120,
    max_expiries: int = 6,
) -> tuple:
    """
    Holt Options Chain — nur relevante Verfallsdaten im DTE-Fenster.
    Gibt zurück: (puts_df, calls_df, expirations_list)

    Optimierung: Statt alle 15-20 Verfallsdaten zu laden, werden nur
    die Dates im DTE-Bereich geholt (max max_expiries). Das spart
    70-80% der API-Calls und macht den Scan 4-6x schneller.
    """
    try:
        stock = yf.Ticker(ticker)
        expirations = stock.options          # Liste aller verfügbaren Verfallsdaten
        if not expirations:
            return pd.DataFrame(), pd.DataFrame(), []

        # ── Nur relevante Verfallsdaten filtern ──────────────────────────────
        today = datetime.today().date()
        relevant = []
        for exp in expirations:
            try:
                exp_date = datetime.strptime(exp, "%Y-%m-%d").date()
                days = (exp_date - today).days
                if dte_min <= days <= dte_max:
                    relevant.append(exp)
            except Exception:
                continue

        # Fallback: Wenn kein passendes Datum, nimm die ersten max_expiries
        if not relevant:
            relevant = list(expirations)[:max_expiries]
        else:
            relevant = relevant[:max_expiries]

        all_puts, all_calls = [], []

        for exp in relevant:
            try:
                chain = stock.option_chain(exp)

                puts = chain.puts.copy()
                if not puts.empty:
                    puts["expiration"] = exp
                    puts["option_type"] = "put"
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

        puts_df  = pd.concat(all_puts,  ignore_index=True) if all_puts  else pd.DataFrame()
        calls_df = pd.concat(all_calls, ignore_index=True) if all_calls else pd.DataFrame()

        return puts_df, calls_df, relevant

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


# ── IV Rank & IV Percentile ────────────────────────────────────────────────────

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_iv_rank(ticker: str) -> dict:
    """
    Berechnet IV Rank und IV Percentile aus 52-Wochen realisierter Volatilität.
    Nutzt 20-Tage Rolling HV als Proxy für historisches IV.

    IV Rank    = (aktuelle HV - 52w Tief) / (52w Hoch - 52w Tief) × 100
    IV Percentile = % der Tage, an denen HV unter aktuellem Wert lag
    """
    empty = {"iv_rank": None, "iv_percentile": None,
             "hv_current": None, "hv_52w_high": None, "hv_52w_low": None}
    try:
        hist = yf.Ticker(ticker).history(period="1y", interval="1d")
        if len(hist) < 40:
            return empty
        log_ret = np.log(hist["Close"] / hist["Close"].shift(1))
        hv_series = log_ret.rolling(20).std() * np.sqrt(252) * 100  # in %
        hv_series = hv_series.dropna()
        if hv_series.empty:
            return empty
        hv_now  = float(hv_series.iloc[-1])
        hv_high = float(hv_series.max())
        hv_low  = float(hv_series.min())
        iv_rank = ((hv_now - hv_low) / (hv_high - hv_low) * 100
                   if hv_high > hv_low else 50.0)
        iv_pctile = float((hv_series < hv_now).sum() / len(hv_series) * 100)
        return {
            "iv_rank":       round(iv_rank, 1),
            "iv_percentile": round(iv_pctile, 1),
            "hv_current":    round(hv_now, 1),
            "hv_52w_high":   round(hv_high, 1),
            "hv_52w_low":    round(hv_low, 1),
        }
    except Exception:
        return empty


# ── Earnings-Datum ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def fetch_earnings_date(ticker: str) -> Optional[str]:
    """Gibt das nächste Earnings-Datum als String 'YYYY-MM-DD' zurück."""
    try:
        cal = yf.Ticker(ticker).calendar
        if cal is None:
            return None
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date") or cal.get("earningsDate")
            if ed is None:
                return None
            if hasattr(ed, "__iter__") and not isinstance(ed, str):
                ed = list(ed)[0]
            return str(ed)[:10] if ed else None
        if isinstance(cal, pd.DataFrame) and "Earnings Date" in cal.columns:
            val = cal["Earnings Date"].iloc[0]
            return str(val)[:10]
        return None
    except Exception:
        return None
