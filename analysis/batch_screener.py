"""
Batch-Screener: Scannt mehrere Ticker gleichzeitig und berechnet
den Chance-Risiko-Verhältnis (CRV) Score für alle Optionen.
"""

import pandas as pd
import numpy as np
import time
import yfinance as yf
from typing import Optional, Callable, List
from dataclasses import dataclass

from analysis.greeks import enrich_options_with_greeks
from analysis.technicals import analyze_technicals, TechSignal
from data.fetcher import (
    fetch_options_chain, fetch_price_history,
    fetch_stock_info, calculate_dte
)
from data.watchlist import get_sector_for_ticker, SECTOR_ICONS


# ── CRV Score ─────────────────────────────────────────────────────────────────

def calculate_crv_score(
    premium: float,
    strike: float,
    current_price: float,
    delta: float,
    dte: int,
    option_type: str = "put",
) -> float:
    """
    Chance-Risiko-Verhältnis Score (0-100+).

    Chance:  Annualisierte Prämienrendite auf den Strike
    Risiko:  |Delta| = Wahrscheinlichkeit der Ausübung
    Puffer:  OTM% = Sicherheitsabstand zum aktuellen Kurs

    Formel: CRV = (annual_yield% * sqrt(1 + otm_pct)) / (|delta| + 0.05)
    """
    if strike <= 0 or current_price <= 0 or dte <= 0:
        return 0.0

    # Annualisierte Prämienrendite (auf Strike)
    annual_yield = (premium / strike) * (365 / dte) * 100

    # OTM% (Sicherheitsabstand)
    if option_type == "put":
        otm_pct = max(0, (current_price - strike) / current_price * 100)
    else:
        otm_pct = max(0, (strike - current_price) / current_price * 100)

    abs_delta = min(abs(delta), 0.99)

    # CRV Formel: hohe Rendite + großer Puffer + geringes Delta
    crv = (annual_yield * np.sqrt(1 + otm_pct)) / (abs_delta + 0.05)

    return round(crv, 2)


# ── Einzelner Ticker Scan ─────────────────────────────────────────────────────

def scan_ticker(
    ticker: str,
    strategy: str = "Cash Covered Put",
    delta_min: float = -0.35,
    delta_max: float = -0.05,
    dte_min: int = 14,
    dte_max: int = 60,
    iv_min: float = 0.15,
    premium_min: float = 0.05,
    min_oi: int = 5,
    otm_min: float = 3.0,
    otm_max: float = 25.0,
) -> pd.DataFrame:
    """
    Scannt einen einzelnen Ticker und gibt gefilterte Optionen mit CRV zurück.
    """
    try:
        puts_df, calls_df, expirations = fetch_options_chain(ticker)

        if not expirations:
            return pd.DataFrame()

        stock_info = fetch_stock_info(ticker)
        current_price = stock_info.get("price")

        if not current_price or current_price <= 0:
            return pd.DataFrame()

        opt_type = "call" if strategy == "Covered Call" else "put"
        raw_df = calls_df if strategy == "Covered Call" else puts_df

        if raw_df is None or raw_df.empty:
            return pd.DataFrame()

        df = raw_df.copy()

        # Basis-Berechnungen (mid_price kommt bereits aus fetcher._fix_off_hours_prices)
        df["dte"] = df["expiration"].apply(calculate_dte)
        if "mid_price" not in df.columns:
            df["mid_price"] = df.apply(
                lambda r: (float(r.get("bid", 0) or 0) + float(r.get("ask", 0) or 0)) / 2
                if float(r.get("bid", 0) or 0) > 0
                else float(r.get("lastPrice", 0) or 0),
                axis=1
            )

        if opt_type == "put":
            df["otm_pct"] = df.apply(
                lambda r: max(0, (current_price - float(r["strike"])) / current_price * 100), axis=1
            )
        else:
            df["otm_pct"] = df.apply(
                lambda r: max(0, (float(r["strike"]) - current_price) / current_price * 100), axis=1
            )

        # Basis-Filter (ohne Delta, der kommt nach Greeks)
        mask = (
            (df["dte"] >= dte_min) & (df["dte"] <= dte_max) &
            (df["mid_price"] >= premium_min) &
            (df["otm_pct"] >= otm_min) & (df["otm_pct"] <= otm_max)
        )
        if "openInterest" in df.columns:
            mask &= df["openInterest"].fillna(0) >= min_oi
        if "impliedVolatility" in df.columns:
            mask &= df["impliedVolatility"].fillna(0) >= iv_min

        df = df[mask].copy()

        if df.empty:
            return pd.DataFrame()

        # Greeks berechnen
        df = enrich_options_with_greeks(df, current_price, opt_type)

        # Delta-Filter
        if "delta" in df.columns:
            if opt_type == "put":
                delta_mask = (df["delta"] >= delta_min) & (df["delta"] <= delta_max)
            else:
                delta_mask = (df["delta"] >= abs(delta_min)) & (df["delta"] <= abs(delta_max))
            df = df[delta_mask].copy()

        if df.empty:
            return pd.DataFrame()

        # Technische Analyse (schnell, aus Cache)
        tech = None
        try:
            hist = fetch_price_history(ticker, period="6mo")
            if not hist.empty:
                tech = analyze_technicals(hist)
        except Exception:
            pass

        # CRV Score berechnen
        df["crv_score"] = df.apply(
            lambda r: calculate_crv_score(
                premium=float(r["mid_price"]),
                strike=float(r["strike"]),
                current_price=current_price,
                delta=float(r.get("delta", -0.20)),
                dte=int(r["dte"]),
                option_type=opt_type,
            ), axis=1
        )

        # Annualisierte Rendite
        df["annual_yield_pct"] = (df["mid_price"] / df["strike"]) * (365 / df["dte"].clip(1)) * 100
        df["premium_per_day"] = df["mid_price"] / df["dte"].clip(1)
        # Rendite auf Laufzeit (% auf Strike/eingesetztes Kapital)
        df["yield_laufzeit_pct"] = (df["mid_price"] / df["strike"]) * 100
        # Rendite pro Tag (% auf Strike)
        df["yield_per_day_pct"] = df["yield_laufzeit_pct"] / df["dte"].clip(1)

        # Sektor + Tech-Infos
        sector = get_sector_for_ticker(ticker)
        sector_short = sector.split(".", 1)[-1].strip().split("(")[0].strip() if "." in sector else sector

        trend_str = ""
        trend_score = 50.0
        if tech:
            trend_map = {"bullish": "↑ Aufwärtstrend", "bearish": "↓ Abwärtstrend", "neutral": "→ Seitwärts"}
            trend_str = trend_map.get(tech.trend, "")
            trend_score = tech.trend_score

        # Output aufbauen
        result = pd.DataFrame({
            "Ticker": ticker,
            "Sektor": sector_short,
            "Kurs": round(current_price, 2),
            "Strike": df["strike"].round(2),
            "Verfall": df["expiration"],
            "DTE": df["dte"].astype(int),
            "Prämie": df["mid_price"].round(2),
            "Prämie/Tag": df["premium_per_day"].round(3),
            "Rendite ann. %": df["annual_yield_pct"].round(1),
            "Rendite % Laufzeit": df["yield_laufzeit_pct"].round(2),
            "Rendite %/Tag": df["yield_per_day_pct"].round(4),
            "Delta": df["delta"].round(3),
            "IV %": (df["impliedVolatility"] * 100).round(1) if "impliedVolatility" in df.columns else 0,
            "OTM %": df["otm_pct"].round(1),
            "OI": df["openInterest"].fillna(0).astype(int) if "openInterest" in df.columns else 0,
            "Trend": trend_str,
            "Trend-Score": round(trend_score, 0),
            "CRV Score": df["crv_score"],
        })

        return result.sort_values("CRV Score", ascending=False)

    except Exception as e:
        return pd.DataFrame()


# ── Batch Scanner ─────────────────────────────────────────────────────────────

def scan_watchlist(
    tickers: List[str],
    strategy: str = "Cash Covered Put",
    delta_min: float = -0.35,
    delta_max: float = -0.05,
    dte_min: int = 14,
    dte_max: int = 60,
    iv_min: float = 0.15,
    premium_min: float = 0.05,
    min_oi: int = 5,
    otm_min: float = 3.0,
    otm_max: float = 25.0,
    max_results_per_ticker: int = 3,
    progress_callback: Optional[Callable] = None,
) -> pd.DataFrame:
    """
    Scannt eine Liste von Tickern und gibt die besten Optionen nach CRV zurück.

    progress_callback(current, total, ticker) wird bei jedem Ticker aufgerufen.
    """
    all_results = []
    total = len(tickers)

    for i, ticker in enumerate(tickers):
        if progress_callback:
            progress_callback(i, total, ticker)

        df = scan_ticker(
            ticker=ticker,
            strategy=strategy,
            delta_min=delta_min,
            delta_max=delta_max,
            dte_min=dte_min,
            dte_max=dte_max,
            iv_min=iv_min,
            premium_min=premium_min,
            min_oi=min_oi,
            otm_min=otm_min,
            otm_max=otm_max,
        )

        if not df.empty:
            # Nur die besten N pro Ticker
            all_results.append(df.head(max_results_per_ticker))

        # Kurze Pause um Rate-Limiting zu vermeiden
        time.sleep(0.3)

    if progress_callback:
        progress_callback(total, total, "Fertig")

    if not all_results:
        return pd.DataFrame()

    combined = pd.concat(all_results, ignore_index=True)
    combined = combined.sort_values("CRV Score", ascending=False).reset_index(drop=True)

    # Rang hinzufügen
    combined.insert(0, "Rang", range(1, len(combined) + 1))

    # Ergebnisse für Top-9-Homepage speichern
    try:
        import pickle, datetime, os
        cache_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(cache_dir, exist_ok=True)
        cache_path = os.path.join(cache_dir, "last_scan_cache.pkl")
        with open(cache_path, "wb") as f:
            pickle.dump({
                "results": combined,
                "timestamp": datetime.datetime.now(),
                "strategy": strategy,
            }, f)
    except Exception:
        pass

    return combined
