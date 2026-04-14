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
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from analysis.greeks import enrich_options_with_greeks
from analysis.technicals import analyze_technicals, TechSignal
from data.fetcher import (
    fetch_options_chain, fetch_price_history,
    fetch_stock_info, calculate_dte,
    fetch_iv_rank, fetch_earnings_date
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


# ── Short Strangle Scan ───────────────────────────────────────────────────────

def _mid(row) -> float:
    """Midprice NUR aus Bid/Ask — gibt 0 zurück wenn kein echter Markt."""
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    if bid > 0 and ask > 0 and ask >= bid:
        return (bid + ask) / 2
    return 0.0   # kein gültiger Markt → wird später herausgefiltert


def _spread_pct(row) -> float:
    """Spread in % des Midpreises. NaN wenn kein Markt."""
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    if bid > 0 and ask > 0 and ask >= bid:
        mid = (bid + ask) / 2
        return (ask - bid) / mid * 100 if mid > 0 else 999.0
    return 999.0


def scan_strangle(
    ticker: str,
    dte_min: int = 14,
    dte_max: int = 60,
    iv_min: float = 0.30,
    premium_min: float = 0.10,
    min_oi: int = 5,
    otm_min: float = 10.0,
    otm_max: float = 50.0,
    max_spread_pct: float = 60.0,    # max. Bid/Ask-Spread in % des Midpreises
) -> pd.DataFrame:
    """
    Scannt Short-Strangle-Kombinationen: SHORT PUT + SHORT CALL auf gleichem Verfallstag.
    Beide Strikes mind. otm_min% OTM. Gibt kombinierte Metriken zurück.
    Ideal: hohe IV, weite Strikes, noch ausreichende Prämie.
    """
    try:
        puts_df, calls_df, expirations = fetch_options_chain(
            ticker, dte_min=dte_min, dte_max=dte_max, max_expiries=6
        )
        if not expirations or puts_df is None or calls_df is None:
            return pd.DataFrame()

        stock_info = fetch_stock_info(ticker)
        current_price = stock_info.get("price")
        if not current_price or current_price <= 0:
            return pd.DataFrame()

        sector = get_sector_for_ticker(ticker)
        sector_short = (sector.split(".", 1)[-1].strip().split("(")[0].strip()
                        if "." in sector else sector)

        # Technische Analyse (für Trend-Info)
        trend_str = ""
        try:
            hist = fetch_price_history(ticker, period="6mo")
            if hist is not None and not hist.empty:
                tech = analyze_technicals(hist)
                if tech:
                    m = {"bullish": "↑ Aufwärtstrend", "bearish": "↓ Abwärtstrend",
                         "neutral": "→ Seitwärts"}
                    trend_str = m.get(tech.trend, "")
        except Exception:
            pass

        # IV Rank
        iv_rank_str = "–"
        try:
            ivd = fetch_iv_rank(ticker)
            ivr = ivd.get("iv_rank")
            iv_rank_str = f"{ivr:.0f}" if ivr is not None else "–"
        except Exception:
            pass

        # Earnings
        earnings_str = ""
        try:
            edate = fetch_earnings_date(ticker)
            if edate and calculate_dte(edate) >= 0:
                earnings_str = edate
        except Exception:
            pass

        # Für jeden Verfallstag: bestes PUT + CALL Paar finden
        results = []
        for expiry in expirations:
            dte_val = calculate_dte(expiry)
            if dte_val < dte_min or dte_val > dte_max:
                continue

            # Puts für diesen Verfall
            p_exp = puts_df[puts_df["expiration"] == expiry].copy() if "expiration" in puts_df.columns else pd.DataFrame()
            c_exp = calls_df[calls_df["expiration"] == expiry].copy() if "expiration" in calls_df.columns else pd.DataFrame()

            if p_exp.empty or c_exp.empty:
                continue

            # Bid/Ask validieren + Mid-Price berechnen (nur echter Markt)
            for col in ("bid", "ask", "lastPrice"):
                for df_ in (p_exp, c_exp):
                    if col in df_.columns:
                        df_[col] = pd.to_numeric(df_[col], errors="coerce").fillna(0.0)
                    else:
                        df_[col] = 0.0

            p_exp["_has_market"] = (p_exp["bid"] > 0) & (p_exp["ask"] > 0) & (p_exp["ask"] >= p_exp["bid"])
            c_exp["_has_market"] = (c_exp["bid"] > 0) & (c_exp["ask"] > 0) & (c_exp["ask"] >= c_exp["bid"])

            # Mid-Price NUR aus Bid/Ask — kein lastPrice-Fallback
            p_exp["mid_price"] = np.where(p_exp["_has_market"], (p_exp["bid"] + p_exp["ask"]) / 2, 0.0)
            c_exp["mid_price"] = np.where(c_exp["_has_market"], (c_exp["bid"] + c_exp["ask"]) / 2, 0.0)

            # Spread %
            p_exp["_spread_pct"] = np.where(
                p_exp["_has_market"] & (p_exp["mid_price"] > 0),
                (p_exp["ask"] - p_exp["bid"]) / p_exp["mid_price"] * 100, 999.0)
            c_exp["_spread_pct"] = np.where(
                c_exp["_has_market"] & (c_exp["mid_price"] > 0),
                (c_exp["ask"] - c_exp["bid"]) / c_exp["mid_price"] * 100, 999.0)

            # OTM% berechnen
            p_exp["otm_pct"] = ((current_price - p_exp["strike"].astype(float)) / current_price * 100).clip(lower=0)
            c_exp["otm_pct"] = ((c_exp["strike"].astype(float) - current_price) / current_price * 100).clip(lower=0)

            # Sparse-Market-Erkennung (wenn <20% echte Bid/Ask → Warnung aber kein Fallback)
            p_sparse = p_exp["_has_market"].mean() < 0.20
            c_sparse = c_exp["_has_market"].mean() < 0.20

            # Filter anwenden — immer Bid UND Ask erforderlich
            def _apply_filters(df_, sparse: bool) -> pd.DataFrame:
                iv_col = df_.get("impliedVolatility", pd.Series([1.0]*len(df_), index=df_.index)).fillna(0)
                oi_col = df_.get("openInterest",      pd.Series([min_oi]*len(df_), index=df_.index)).fillna(0)
                mask = (
                    df_["_has_market"] &                         # Bid UND Ask vorhanden
                    (df_["_spread_pct"] <= max_spread_pct) &     # Spread nicht zu groß
                    (df_["otm_pct"] >= otm_min) &
                    (df_["otm_pct"] <= otm_max) &
                    (df_["mid_price"] >= premium_min) &
                    (iv_col >= iv_min) &
                    (oi_col >= min_oi)
                )
                return df_[mask]

            p_filt = _apply_filters(p_exp, p_sparse)
            c_filt = _apply_filters(c_exp, c_sparse)

            if p_filt.empty or c_filt.empty:
                continue

            # Greeks berechnen
            p_filt = enrich_options_with_greeks(p_filt, current_price, "put")
            c_filt = enrich_options_with_greeks(c_filt, current_price, "call")

            if p_filt.empty or c_filt.empty:
                continue

            # Bestes Paar: höchste Gesamt-Prämie mit möglichst symmetrischem Delta
            # → kombiniere jeweils das beste Put + beste Call (nach Prämie/OTM)
            best_put  = p_filt.sort_values("mid_price", ascending=False).iloc[0]
            best_call = c_filt.sort_values("mid_price", ascending=False).iloc[0]

            put_strike   = float(best_put["strike"])
            call_strike  = float(best_call["strike"])
            put_premium  = float(best_put["mid_price"])
            call_premium = float(best_call["mid_price"])
            put_otm      = float(best_put["otm_pct"])
            call_otm     = float(best_call["otm_pct"])
            put_delta    = float(best_put.get("delta", -0.15))
            call_delta   = float(best_call.get("delta", 0.15))
            put_iv       = float(best_put.get("impliedVolatility", iv_min))
            call_iv      = float(best_call.get("impliedVolatility", iv_min))
            avg_iv       = (put_iv + call_iv) / 2
            combined_prem = put_premium + call_premium
            net_delta    = put_delta + call_delta     # nahe 0 = neutral
            breakeven_low  = put_strike  - combined_prem
            breakeven_high = call_strike + combined_prem
            total_range_pct = (call_strike - put_strike) / current_price * 100
            combined_yield  = (combined_prem / current_price) * 100   # auf Kurs
            annual_yield    = combined_yield * (365 / max(1, dte_val))

            # CRV für Strangle: Rendite × √(Range) / (|net_delta| + 0.1)
            crv = (annual_yield * np.sqrt(1 + total_range_pct / 2)) / (abs(net_delta) + 0.10)

            earn_warn = ""
            if earnings_str:
                earn_dte = calculate_dte(earnings_str)
                if 0 <= earn_dte <= dte_val:
                    earn_warn = f"⚠️ {earnings_str}"

            results.append({
                "Ticker":           ticker,
                "Sektor":           sector_short,
                "Kurs":             round(current_price, 2),
                "Strike PUT":       round(put_strike, 2),
                "Strike CALL":      round(call_strike, 2),
                "Strike":           round((put_strike + call_strike) / 2, 2),  # für Sortierung
                "OTM% PUT":         round(put_otm, 1),
                "OTM% CALL":        round(call_otm, 1),
                "Range %":          round(total_range_pct, 1),
                "Verfall":          expiry,
                "DTE":              dte_val,
                "Prämie PUT":       round(put_premium, 2),
                "Prämie CALL":      round(call_premium, 2),
                "Prämie gesamt":    round(combined_prem, 2),
                "Prämie":           round(combined_prem, 2),  # Kompatibilität
                "Rendite ann. %":   round(annual_yield, 1),
                "Rendite % Laufzeit": round(combined_yield, 2),
                "Rendite %/Tag":    round(combined_yield / max(1, dte_val), 4),
                "Prämie/Tag":       round(combined_prem / max(1, dte_val), 3),
                "Delta PUT":        round(put_delta, 3),
                "Delta CALL":       round(call_delta, 3),
                "Delta":            round(net_delta, 3),
                "IV %":             round(avg_iv * 100, 1),
                "IV Rank":          iv_rank_str,
                "Break-even Low":   round(breakeven_low, 2),
                "Break-even High":  round(breakeven_high, 2),
                "Trend":            trend_str,
                "Trend-Score":      0,
                "CRV Score":        round(crv, 2),
                "⚠️ Earnings":      earn_warn,
            })

        if not results:
            return pd.DataFrame()
        return pd.DataFrame(results).sort_values("CRV Score", ascending=False)

    except Exception:
        return pd.DataFrame()


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
    require_valid_market: bool = True,
    max_spread_pct: float = 999.0,
) -> pd.DataFrame:
    """
    Scannt einen einzelnen Ticker und gibt gefilterte Optionen mit CRV zurück.
    Für Short Strangle → delegiert an scan_strangle().
    """
    if strategy == "Short Strangle":
        return scan_strangle(
            ticker,
            dte_min=dte_min, dte_max=dte_max,
            iv_min=iv_min, premium_min=premium_min,
            min_oi=min_oi, otm_min=otm_min, otm_max=otm_max,
            max_spread_pct=max_spread_pct,
        )

    try:
        puts_df, calls_df, expirations = fetch_options_chain(
            ticker, dte_min=dte_min, dte_max=dte_max, max_expiries=6
        )

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

        # ── Bid/Ask-Validierung ────────────────────────────────────────────────
        # Sicherere Konvertierung aller Preisspalten
        for col in ("bid", "ask", "lastPrice"):
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
            else:
                df[col] = 0.0

        # Flag: hat echten zweiteiligen Markt (Bid UND Ask vorhanden)
        df["_has_market"] = (df["bid"] > 0) & (df["ask"] > 0) & (df["ask"] >= df["bid"])

        # mid_price: NUR aus Bid/Ask wenn vorhanden, sonst lastPrice (nur Off-Hours)
        df["mid_price"] = np.where(
            df["_has_market"],
            (df["bid"] + df["ask"]) / 2,
            df["lastPrice"]
        )

        # Kursquelle-Label für Anzeige
        df["_price_source"] = np.where(df["_has_market"], "Mid", "Last")

        # Spread-Berechnung (nur wenn echter Markt, sonst NaN)
        df["_spread_pct"] = np.where(
            df["_has_market"] & (df["mid_price"] > 0),
            (df["ask"] - df["bid"]) / df["mid_price"] * 100,
            np.nan
        )

        # Basis-Berechnungen
        df["dte"] = df["expiration"].apply(calculate_dte)

        if opt_type == "put":
            df["otm_pct"] = (
                (current_price - df["strike"].astype(float)) / current_price * 100
            ).clip(lower=0)
        else:
            df["otm_pct"] = (
                (df["strike"].astype(float) - current_price) / current_price * 100
            ).clip(lower=0)

        # ── Basis-Filter ───────────────────────────────────────────────────────
        mask = (
            (df["dte"] >= dte_min) & (df["dte"] <= dte_max) &
            (df["mid_price"] >= premium_min) &
            (df["otm_pct"] >= otm_min) & (df["otm_pct"] <= otm_max)
        )
        if "openInterest" in df.columns:
            mask &= df["openInterest"].fillna(0) >= min_oi
        if "impliedVolatility" in df.columns:
            mask &= df["impliedVolatility"].fillna(0) >= iv_min

        # ── Liquiditäts-Filter ────────────────────────────────────────────────
        bid_ask_rate = df["_has_market"].mean() if len(df) > 0 else 0.0
        sparse_market = bid_ask_rate < 0.20

        if require_valid_market:
            if not sparse_market:
                # Normalmodus: nur echte Bid/Ask-Optionen
                mask &= df["_has_market"]
                # Mid-Preis NUR aus Bid/Ask
                df["mid_price"] = np.where(df["_has_market"],
                                            (df["bid"] + df["ask"]) / 2, 0.0)
            else:
                # Sparse-Markt: lastPrice als Fallback erlauben, aber Mid bevorzugen
                mask &= (df["_has_market"] | (df["lastPrice"] > 0))
                df["mid_price"] = np.where(
                    df["_has_market"],
                    (df["bid"] + df["ask"]) / 2,  # echter Markt → Mid
                    df["lastPrice"]                 # Fallback → Last
                )

        # Spread-Filter: immer anwenden (nur auf Optionen mit echtem Markt)
        if max_spread_pct < 999.0:
            valid_spread = df["_spread_pct"].notna() & (df["_spread_pct"] <= max_spread_pct)
            no_spread    = df["_spread_pct"].isna()
            mask &= (valid_spread | no_spread)

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

        # IV Rank (non-blocking — gibt leeres Dict zurück wenn Fehler)
        iv_rank_data = {}
        try:
            iv_rank_data = fetch_iv_rank(ticker)
        except Exception:
            pass
        iv_rank_val = iv_rank_data.get("iv_rank")
        iv_pctile   = iv_rank_data.get("iv_percentile")
        iv_rank_str = (f"{iv_rank_val:.0f}" if iv_rank_val is not None else "–")

        # Earnings-Warnung (U1): Datum holen und prüfen ob innerhalb Laufzeit
        earnings_str = ""
        try:
            earn_date_str = fetch_earnings_date(ticker)
            if earn_date_str:
                earn_dte = calculate_dte(earn_date_str)
                if earn_dte >= 0:
                    earnings_str = earn_date_str
        except Exception:
            pass

        # Spread-Qualität: direkt aus vorberechneter _spread_pct Spalte
        spread_pct_col = df["_spread_pct"].values if "_spread_pct" in df.columns else np.full(len(df), np.nan)

        # Liquiditäts-Label (🟢🟡🔴) — einheitlich mit Einzelanalyse
        def _liq_label(r) -> str:
            sp  = r.get("_spread_pct", np.nan)
            oi  = int(r.get("openInterest", 0) or 0)
            vol = int(r.get("volume", 0) or 0)
            if pd.isna(sp) or sp >= 999:
                return "🔴"
            if sp <= 15 and oi >= 50:
                return "🟢"
            if sp <= 40 and oi >= 10:
                return "🟡"
            return "🔴"

        liq_col = df.apply(_liq_label, axis=1)

        # Earnings-Warnung je Option
        def _earn_warn(dte_val):
            if not earnings_str:
                return ""
            earn_dte = calculate_dte(earnings_str)
            if 0 <= earn_dte <= dte_val:
                return f"⚠️ {earnings_str}"
            return ""

        # Output aufbauen
        result = pd.DataFrame({
            "Liq.":     liq_col,
            "Ticker":   ticker,
            "Sektor":   sector_short,
            "Kurs":     round(current_price, 2),
            "Strike":   df["strike"].round(2),
            "OTM %":    df["otm_pct"].round(1),
            "Verfall":  df["expiration"],
            "DTE":      df["dte"].astype(int),
            "Prämie":   df["mid_price"].round(2),
            "Bid":      df["bid"].round(2) if "bid" in df.columns else pd.Series(float("nan"), index=df.index),
            "Ask":      df["ask"].round(2) if "ask" in df.columns else pd.Series(float("nan"), index=df.index),
            "Kursquelle":        df["_price_source"] if "_price_source" in df.columns else "Mid",
            "Spread %":          pd.Series(spread_pct_col, index=df.index).round(1),
            "Prämie/Tag":        df["premium_per_day"].round(3),
            "Rendite ann. %":    df["annual_yield_pct"].round(1),
            "Rendite % Laufzeit": df["yield_laufzeit_pct"].round(2),
            "Rendite %/Tag":     df["yield_per_day_pct"].round(4),
            "Delta":    df["delta"].round(3),
            "Theta/Tag": df["theta"].round(3) if "theta" in df.columns else pd.Series(float("nan"), index=df.index),
            "IV %":     (df["impliedVolatility"] * 100).round(1) if "impliedVolatility" in df.columns else 0,
            "IV Rank":  iv_rank_str,
            "OI":       df["openInterest"].fillna(0).astype(int) if "openInterest" in df.columns else 0,
            "Volumen":  df["volume"].fillna(0).astype(int) if "volume" in df.columns else 0,
            "Trend":    trend_str,
            "Trend-Score": round(trend_score, 0),
            "CRV Score": df["crv_score"],
            "⚠️ Earnings": df["dte"].apply(_earn_warn),
        })

        return result.sort_values("CRV Score", ascending=False)

    except Exception as e:
        return pd.DataFrame()


# ── Rate-Limiter für parallele Anfragen ───────────────────────────────────────
_PARALLEL_WORKERS = 8        # Gleichzeitige Anfragen (Yahoo Finance verträgt ~10)
_RATE_LIMITER     = threading.Semaphore(_PARALLEL_WORKERS)
_REQUEST_DELAY    = 0.05     # Sekunden zwischen Anfragen pro Thread (war 0.15)


def _scan_single(ticker: str, scan_kwargs: dict) -> tuple:
    """Wrapper für Thread-Pool: gibt (ticker, DataFrame) zurück."""
    with _RATE_LIMITER:
        result = scan_ticker(ticker, **scan_kwargs)
        time.sleep(_REQUEST_DELAY)
    return ticker, result


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
    require_valid_market: bool = True,
    max_spread_pct: float = 999.0,
    progress_callback: Optional[Callable] = None,
    result_callback: Optional[Callable] = None,
) -> pd.DataFrame:
    """
    Scannt eine Liste von Tickern PARALLEL (bis zu 8 gleichzeitig)
    und gibt die besten Optionen nach CRV zurück.

    progress_callback(current, total, ticker) — Fortschritt (Zähler + Name)
    result_callback(ticker, df)              — wird bei JEDEM Treffer sofort
                                               aufgerufen → Live-Anzeige möglich
    """
    all_results = []
    total = len(tickers)
    completed = 0

    scan_kwargs = dict(
        strategy=strategy, delta_min=delta_min, delta_max=delta_max,
        dte_min=dte_min, dte_max=dte_max, iv_min=iv_min,
        premium_min=premium_min, min_oi=min_oi,
        otm_min=otm_min, otm_max=otm_max,
        require_valid_market=require_valid_market,
        max_spread_pct=max_spread_pct,
    )

    with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as executor:
        futures = {
            executor.submit(_scan_single, ticker, scan_kwargs): ticker
            for ticker in tickers
        }
        for future in as_completed(futures):
            try:
                ticker, df = future.result(timeout=30)
            except Exception:
                ticker = futures[future]
                df = pd.DataFrame()

            completed += 1

            if not df.empty:
                partial = df.head(max_results_per_ticker)
                all_results.append(partial)
                # ── Live-Callback: sofort melden (Fehler nie den Scan brechen lassen) ──
                if result_callback:
                    try:
                        result_callback(ticker, partial)
                    except Exception:
                        pass

            if progress_callback:
                try:
                    progress_callback(completed, total, ticker)
                except Exception:
                    pass

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
