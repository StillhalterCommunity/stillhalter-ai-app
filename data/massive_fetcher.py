"""
Massive.com (ehem. Polygon.io) Daten-Adapter — Stillhalter AI App
==================================================================
Drop-in-Ersatz für Yahoo Finance Optionsdaten.
Liefert echte Echtzeit-Bid/Ask und korrekte IVs → kein IV-Solver nötig.

Setup:
  1. Account auf massive.com erstellen
  2. API-Key in Streamlit Secrets oder .env eintragen:
       MASSIVE_API_KEY = "dein_key_hier"
  3. In fetcher.py: USE_MASSIVE = True setzen

API-Kompatibilität:
  - api.polygon.io und api.massive.com sind identisch (Rebrand Okt 2025)
  - Bestehende Polygon-Keys funktionieren weiterhin
"""

from __future__ import annotations

import os
import time
import logging
from datetime import datetime, date
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

# ── Konfiguration ─────────────────────────────────────────────────────────────

_BASE_URL = "https://api.polygon.io"   # api.massive.com wäre identisch
_TIMEOUT  = 10   # Sekunden
_MAX_RETRIES = 2


def _get_api_key() -> str:
    """
    Liest API-Key aus Streamlit Secrets oder Umgebungsvariable.
    Reihenfolge: st.secrets → MASSIVE_API_KEY → POLYGON_API_KEY (Legacy)
    """
    # Streamlit Secrets (bevorzugt für Deployment)
    try:
        import streamlit as st
        key = st.secrets.get("MASSIVE_API_KEY") or st.secrets.get("POLYGON_API_KEY")
        if key:
            return key
    except Exception:
        pass

    # Umgebungsvariable (lokal / .env)
    key = os.environ.get("MASSIVE_API_KEY") or os.environ.get("POLYGON_API_KEY")
    if key:
        return key

    return ""


def _get(endpoint: str, params: dict | None = None) -> dict:
    """Führt einen GET-Request gegen die Massive/Polygon API aus."""
    api_key = _get_api_key()
    if not api_key:
        raise ValueError(
            "Kein Massive/Polygon API-Key gefunden. "
            "Bitte MASSIVE_API_KEY in Streamlit Secrets oder Umgebungsvariable setzen."
        )

    url = f"{_BASE_URL}{endpoint}"
    p = {"apiKey": api_key}
    if params:
        p.update(params)

    for attempt in range(_MAX_RETRIES + 1):
        try:
            resp = requests.get(url, params=p, timeout=_TIMEOUT)
            if resp.status_code == 429:
                # Rate limit — kurz warten
                time.sleep(1.5)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            if attempt == _MAX_RETRIES:
                raise
            time.sleep(0.5)
    return {}


# ── Aktienkurs ────────────────────────────────────────────────────────────────

def get_current_price(ticker: str) -> Optional[float]:
    """
    Aktueller Kurs via Massive/Polygon Snapshot.
    Fällt auf Previous Close zurück wenn Markt geschlossen.
    """
    try:
        data = _get(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker.upper()}")
        snap = data.get("ticker", {})
        day = snap.get("day", {})
        last = snap.get("lastTrade", {})
        return (
            float(last.get("p", 0))
            or float(day.get("c", 0))    # Close des Tages
            or float(snap.get("prevDay", {}).get("c", 0))
        ) or None
    except Exception as e:
        logger.warning("Massive get_current_price(%s): %s", ticker, e)
        return None


def get_price_history(
    ticker: str,
    days: int = 60,
    interval: str = "day",  # "minute", "hour", "day", "week"
) -> pd.DataFrame:
    """
    Kurshistorie als DataFrame (open, high, low, close, volume).
    """
    from_date = (date.today() - pd.Timedelta(days=days)).strftime("%Y-%m-%d")
    to_date   = date.today().strftime("%Y-%m-%d")

    multiplier_map = {"minute": 1, "hour": 1, "day": 1, "week": 1}
    mult = multiplier_map.get(interval, 1)

    try:
        data = _get(
            f"/v2/aggs/ticker/{ticker.upper()}/range/{mult}/{interval}"
            f"/{from_date}/{to_date}",
            params={"adjusted": "true", "sort": "asc", "limit": 5000},
        )
        results = data.get("results", [])
        if not results:
            return pd.DataFrame()

        df = pd.DataFrame(results)
        df["date"] = pd.to_datetime(df["t"], unit="ms")
        df = df.rename(columns={
            "o": "open", "h": "high", "l": "low",
            "c": "close", "v": "volume", "vw": "vwap",
        })
        return df[["date", "open", "high", "low", "close", "volume"]].set_index("date")
    except Exception as e:
        logger.warning("Massive get_price_history(%s): %s", ticker, e)
        return pd.DataFrame()


# ── Options-Chain ─────────────────────────────────────────────────────────────

def _expiry_str_to_date(exp: str) -> str:
    """Konvertiert 'YYYY-MM-DD' → bleibt, oder 'YYYYMMDD' → 'YYYY-MM-DD'."""
    if len(exp) == 8 and "-" not in exp:
        return f"{exp[:4]}-{exp[4:6]}-{exp[6:]}"
    return exp


def get_options_chain(
    ticker: str,
    expiration: str | None = None,   # "YYYY-MM-DD" oder None für alle
    option_type: str = "put",        # "put" oder "call"
    limit: int = 250,
) -> pd.DataFrame:
    """
    Options-Chain von Massive/Polygon mit echten Bid/Ask und IV.

    Liefert DataFrame mit Spalten:
      strike, expiration, bid, ask, mid_price, lastPrice,
      impliedVolatility, delta, gamma, theta, vega,
      openInterest, volume, contractSymbol
    """
    right = "P" if option_type == "put" else "C"

    params: dict = {
        "contract_type":           right,
        "limit":                   limit,
        "sort":                    "strike_price",
        "order":                   "asc",
        "as_of":                   date.today().strftime("%Y-%m-%d"),
    }
    if expiration:
        params["expiration_date"] = _expiry_str_to_date(expiration)

    try:
        data = _get(
            f"/v3/snapshot/options/{ticker.upper()}",
            params=params,
        )
    except Exception as e:
        logger.warning("Massive options chain(%s): %s", ticker, e)
        return pd.DataFrame()

    results = data.get("results", [])
    if not results:
        return pd.DataFrame()

    rows = []
    for item in results:
        details  = item.get("details", {})
        greeks   = item.get("greeks", {})
        day      = item.get("day", {})
        last_q   = item.get("last_quote", {})

        bid       = float(last_q.get("bid", 0) or 0)
        ask       = float(last_q.get("ask", 0) or 0)
        mid_price = (bid + ask) / 2 if bid > 0 and ask > 0 else 0.0
        last      = float(day.get("close", 0) or item.get("last_trade", {}).get("price", 0) or 0)

        rows.append({
            "contractSymbol":    details.get("ticker", ""),
            "strike":            float(details.get("strike_price", 0)),
            "expiration":        details.get("expiration_date", ""),
            "right":             details.get("contract_type", right),
            "bid":               bid,
            "ask":               ask,
            "mid_price":         mid_price if mid_price > 0 else last,
            "lastPrice":         last,
            "impliedVolatility": float(item.get("implied_volatility", 0) or 0),
            "delta":             float(greeks.get("delta", 0) or 0),
            "gamma":             float(greeks.get("gamma", 0) or 0),
            "theta":             float(greeks.get("theta", 0) or 0),
            "vega":              float(greeks.get("vega", 0) or 0),
            "openInterest":      int(item.get("open_interest", 0) or 0),
            "volume":            int(day.get("volume", 0) or 0),
        })

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["expiration"] = pd.to_datetime(df["expiration"]).dt.date
    return df.sort_values("strike").reset_index(drop=True)


def get_available_expirations(ticker: str) -> list[str]:
    """Gibt alle verfügbaren Verfallsdaten für einen Ticker zurück (YYYY-MM-DD)."""
    try:
        data = _get(
            "/v3/reference/options/contracts",
            params={
                "underlying_ticker": ticker.upper(),
                "expired": "false",
                "limit": 1000,
                "sort": "expiration_date",
                "order": "asc",
            },
        )
        results = data.get("results", [])
        dates = sorted(set(r["expiration_date"] for r in results if "expiration_date" in r))
        return dates
    except Exception as e:
        logger.warning("Massive expirations(%s): %s", ticker, e)
        return []


# ── Kompatibilitäts-Wrapper für bestehenden Code ──────────────────────────────

def fetch_options_massive(
    ticker: str,
    expiration: str,
    option_type: str = "put",
    current_price: float | None = None,
) -> pd.DataFrame:
    """
    Drop-in-Ersatz für fetch_options() in data/fetcher.py.
    Gibt den gleichen DataFrame-Stil zurück, den der Rest der App erwartet.
    Greeks kommen direkt von Massive → kein enrich_options_with_greeks() nötig.
    """
    df = get_options_chain(ticker, expiration, option_type)
    if df.empty:
        return df

    # Sicherstellen dass alle erwarteten Spalten vorhanden sind
    for col in ["bid", "ask", "mid_price", "lastPrice",
                "impliedVolatility", "delta", "gamma", "theta", "vega",
                "openInterest", "volume"]:
        if col not in df.columns:
            df[col] = 0.0

    # Negative Deltas für Puts normalisieren (Massive liefert negative Werte)
    if option_type == "put" and "delta" in df.columns:
        df["delta"] = df["delta"].abs() * -1   # sicherstellen: negativ

    return df


def is_api_key_configured() -> bool:
    """Schneller Check ob ein API-Key konfiguriert ist."""
    return bool(_get_api_key())


def test_api_connection() -> tuple[bool, str]:
    """
    Testet die Verbindung zur Massive/Polygon API.
    Returns (success, message).
    """
    if not _get_api_key():
        return False, "Kein API-Key konfiguriert. Bitte MASSIVE_API_KEY in Secrets setzen."
    try:
        data = _get("/v2/aggs/ticker/AAPL/prev")
        if data.get("resultsCount", 0) > 0:
            return True, "Verbindung erfolgreich — Echtzeit-Daten verfügbar"
        return False, f"API antwortet, aber keine Daten: {data.get('status')}"
    except ValueError as e:
        return False, str(e)
    except Exception as e:
        return False, f"Verbindungsfehler: {e}"
