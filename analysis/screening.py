"""
Options Screening, Filterung und Scoring-Logik.
Berechnet den "Stillhalter-Score" für jede Option.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional
from analysis.greeks import enrich_options_with_greeks
from analysis.technicals import TechSignal
from data.fetcher import calculate_dte


@dataclass
class ScreeningParams:
    # Strategie
    strategy: str = "Cash Covered Put"  # "Cash Covered Put" | "Covered Call" | "Short Strangle"

    # Delta Filter
    delta_min: float = -0.35
    delta_max: float = -0.10

    # DTE Filter
    dte_min: int = 14
    dte_max: int = 60

    # IV Filter
    iv_min: float = 0.20   # 20%
    iv_max: float = 2.00   # 200%

    # Prämie Filter
    premium_min: float = 0.10  # mind. 10 Cent
    min_open_interest: int = 10
    min_volume: int = 0

    # Liquidität
    max_spread_pct: float = 60.0   # Max Bid/Ask Spread in % des Mid-Preises

    # Prämie/Tag Filter
    premium_per_day_min: float = 0.0

    # %-Rendite Filter
    rendite_pct_min: float = 0.0       # Min. Rendite auf Laufzeit (% des Strikes)
    rendite_ann_pct_min: float = 0.0   # Min. annualisierte Rendite %

    # Moneyness (% OTM)
    otm_min_pct: float = 0.0    # mind. X% aus dem Geld
    otm_max_pct: float = 20.0   # max. X% aus dem Geld

    # Scoring-Gewichtung
    weight_premium_per_day: float = 0.30
    weight_iv: float = 0.20
    weight_delta_quality: float = 0.20
    weight_trend: float = 0.15
    weight_liquidity: float = 0.15


def _mid_price(row: pd.Series) -> float:
    """
    Midpoint zwischen Bid und Ask — mit gestuftem Fallback:
      1. (bid + ask) / 2  wenn beide > 0 und ask >= bid
      2. bid              wenn nur Bid vorhanden (konservativ, kein Ask)
      3. ask * 0.85       wenn nur Ask vorhanden (Schätzung für illiquid)
      4. lastPrice        wenn kein Markt (Off-Hours oder kein Handel)
    """
    if "mid_price" in row.index and float(row.get("mid_price", 0) or 0) > 0:
        return float(row["mid_price"])
    bid  = float(row.get("bid",       0) or 0)
    ask  = float(row.get("ask",       0) or 0)
    last = float(row.get("lastPrice", 0) or 0)
    if bid > 0 and ask > 0 and ask >= bid:
        return (bid + ask) / 2
    if bid > 0 and ask == 0:
        return bid
    if bid == 0 and ask > 0:
        return ask * 0.85        # einseitiger Markt → konservative Schätzung
    if last > 0:
        return last              # letzter Handelskurs (Off-Hours)
    return 0.0


def _spread_pct(row: pd.Series) -> float:
    """
    Bid/Ask-Spread als % des Mid-Preises.
    Niedrig = liquide. Gibt 999 zurück wenn kein Markt vorhanden.
    """
    bid = float(row.get("bid", 0) or 0)
    ask = float(row.get("ask", 0) or 0)
    if bid > 0 and ask > 0 and ask >= bid:
        mid = (bid + ask) / 2
        return round((ask - bid) / mid * 100, 1) if mid > 0 else 999.0
    return 999.0   # kein zweiseitiger Markt


def _liquidity_label(spread: float, oi: int, volume: int) -> str:
    """Klassifiziert Liquidität: 🟢 Liquide / 🟡 OK / 🔴 Illiquide."""
    if spread <= 15 and oi >= 50:
        return "🟢"
    if spread <= 40 and oi >= 10:
        return "🟡"
    return "🔴"


def _price_source(row: pd.Series) -> str:
    """Kennzeichnet ob Mid, Bid-only oder Letztkurs verwendet wurde."""
    bid  = float(row.get("bid",  0) or 0)
    ask  = float(row.get("ask",  0) or 0)
    last = float(row.get("lastPrice", 0) or 0)
    if bid > 0 and ask > 0 and ask >= bid:
        return "Mid"
    if bid > 0 or ask > 0:
        return "Bid/Ask*"
    if last > 0:
        return "Letztkurs*"
    return "—"


def _otm_pct(strike: float, current_price: float, option_type: str) -> float:
    """Berechnet % aus dem Geld (positiv = OTM)."""
    if current_price <= 0:
        return 0.0
    if option_type == "put":
        return max(0, (current_price - strike) / current_price * 100)
    else:  # call
        return max(0, (strike - current_price) / current_price * 100)


def _delta_quality_score(delta: float, target_delta: float = -0.25) -> float:
    """Score 0-100 wie nah das Delta am Ziel-Delta ist."""
    dist = abs(delta - target_delta)
    return max(0, 100 - dist * 500)


def _liquidity_score(row: pd.Series) -> float:
    """Score 0-100: Open Interest + Volumen + Bid/Ask-Spread."""
    oi  = float(row.get("openInterest", 0) or 0)
    vol = float(row.get("volume", 0) or 0)
    spread = float(row.get("spread_pct", 999) or 999)

    # Spread: 0%=100 Punkte, 50%=50 Punkte, 100%+=0 Punkte
    spread_score = max(0.0, 100 - spread)
    oi_score     = min(100.0, oi / 5.0)
    vol_score    = min(100.0, vol / 2.0)

    return round(oi_score * 0.45 + vol_score * 0.25 + spread_score * 0.30, 1)


def screen_options(
    puts_df: pd.DataFrame,
    calls_df: pd.DataFrame,
    current_price: float,
    params: ScreeningParams,
    tech_signal: Optional[TechSignal] = None,
) -> pd.DataFrame:
    """
    Hauptfunktion: Filtert und bewertet Options basierend auf den Screening-Parametern.
    Gibt einen DataFrame mit Score und Highlights zurück.
    """

    if current_price is None or current_price <= 0:
        return pd.DataFrame()

    if params.strategy == "Covered Call":
        df = _prepare_options(calls_df, current_price, "call")
    elif params.strategy == "Short Strangle":
        return _screen_strangle(puts_df, calls_df, current_price, params, tech_signal)
    else:  # Cash Covered Put (default)
        df = _prepare_options(puts_df, current_price, "put")

    if df.empty:
        return pd.DataFrame()

    # Greeks berechnen
    opt_type = "call" if params.strategy == "Covered Call" else "put"
    df = enrich_options_with_greeks(df, current_price, opt_type)

    # Filter anwenden
    df = _apply_filters(df, current_price, params, opt_type)

    if df.empty:
        return pd.DataFrame()

    # Score berechnen
    df = _calculate_score(df, current_price, params, tech_signal, opt_type)

    return _format_output(df, current_price, opt_type)


def _prepare_options(df: pd.DataFrame, current_price: float, option_type: str) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    # mid_price: Fallback-Kette (Mid → Bid → Ask*0.85 → Last)
    df["mid_price"]    = df.apply(_mid_price, axis=1)
    df["spread_pct"]   = df.apply(_spread_pct, axis=1)
    df["price_source"] = df.apply(_price_source, axis=1)
    df["dte"]          = df["expiration"].apply(calculate_dte)
    df["otm_pct"]      = df.apply(
        lambda r: _otm_pct(float(r["strike"]), current_price, option_type), axis=1
    )
    if "impliedVolatility" in df.columns:
        df["iv_pct"] = df["impliedVolatility"].fillna(0.30) * 100
    else:
        df["iv_pct"] = pd.Series(30.0, index=df.index)
    return df


def _apply_filters(df: pd.DataFrame, current_price: float,
                   params: ScreeningParams, option_type: str) -> pd.DataFrame:
    """Wendet alle numerischen Filter an."""
    if df.empty:
        return df

    mask = pd.Series([True] * len(df), index=df.index)

    # DTE Filter
    mask &= (df["dte"] >= params.dte_min) & (df["dte"] <= params.dte_max)

    # IV Filter
    if "impliedVolatility" in df.columns:
        mask &= (df["impliedVolatility"] >= params.iv_min) & \
                (df["impliedVolatility"] <= params.iv_max)

    # Prämie Filter
    mask &= df["mid_price"] >= params.premium_min

    # Open Interest
    if "openInterest" in df.columns:
        mask &= df["openInterest"].fillna(0) >= params.min_open_interest

    # Volumen
    if "volume" in df.columns and params.min_volume > 0:
        mask &= df["volume"].fillna(0) >= params.min_volume

    # Spread-Filter (Liquidität): nur Optionen mit handelbarem Spread
    if "spread_pct" in df.columns:
        # Optionen ohne Markt (spread=999) werden NICHT gefiltert, aber gekennzeichnet
        # Nur explizit zu weite Spreads rausfiltern
        mask &= (df["spread_pct"] <= params.max_spread_pct) | (df["spread_pct"] >= 998)

    # OTM Filter
    mask &= (df["otm_pct"] >= params.otm_min_pct) & (df["otm_pct"] <= params.otm_max_pct)

    # Delta Filter (nach Greeks-Berechnung)
    if "delta" in df.columns:
        if option_type == "put":
            mask &= (df["delta"] >= params.delta_min) & (df["delta"] <= params.delta_max)
        else:
            mask &= (df["delta"] >= abs(params.delta_min)) & \
                    (df["delta"] <= abs(params.delta_max))

    # Prämie/Tag Filter
    if params.premium_per_day_min > 0:
        df["premium_per_day"] = df["mid_price"] / df["dte"].clip(lower=1)
        mask &= df["premium_per_day"] >= params.premium_per_day_min

    # %-Rendite auf Laufzeit Filter
    if params.rendite_pct_min > 0:
        rendite = df["mid_price"] / df["strike"] * 100
        mask &= rendite >= params.rendite_pct_min

    # Annualisierte Rendite Filter
    if params.rendite_ann_pct_min > 0:
        roi_ann = df["mid_price"] / df["strike"] * (365 / df["dte"].clip(lower=1)) * 100
        mask &= roi_ann >= params.rendite_ann_pct_min

    return df[mask].copy()


def _calculate_score(df: pd.DataFrame, current_price: float,
                     params: ScreeningParams, tech_signal: Optional[TechSignal],
                     option_type: str) -> pd.DataFrame:
    """Berechnet den Stillhalter-Score (0-100) für jede Option."""
    df = df.copy()

    # Prämie/Tag
    df["premium_per_day"] = df["mid_price"] / df["dte"].clip(lower=1)

    # ROI auf Basis des Strikes (annualisiert)
    df["roi_annualized"] = (df["mid_price"] / df["strike"]) * (365 / df["dte"].clip(lower=1)) * 100

    # Einzelscores
    # 1. Prämie/Tag Score (normalisiert auf Basis der gefilterten Daten)
    max_ppd = df["premium_per_day"].quantile(0.95) if len(df) > 5 else df["premium_per_day"].max()
    df["score_premium"] = (df["premium_per_day"] / max(max_ppd, 0.01) * 100).clip(0, 100)

    # 2. IV Score
    df["score_iv"] = (df["iv_pct"].clip(20, 100) - 20) / 80 * 100

    # 3. Delta Qualitäts-Score
    target_delta = -0.25 if option_type == "put" else 0.25
    df["score_delta"] = df["delta"].apply(lambda d: _delta_quality_score(d, target_delta))

    # 4. Trend Score
    trend_score = tech_signal.trend_score if tech_signal else 50.0
    if option_type == "put":
        df["score_trend"] = trend_score  # Puts: bullischer Trend ist besser
    else:
        df["score_trend"] = 100 - trend_score  # Calls: bearischer/neutraler Trend ist besser

    # 5. Liquiditäts-Score
    df["score_liquidity"] = df.apply(_liquidity_score, axis=1)

    # Gewichteter Gesamtscore
    df["score"] = (
        df["score_premium"] * params.weight_premium_per_day +
        df["score_iv"] * params.weight_iv +
        df["score_delta"] * params.weight_delta_quality +
        df["score_trend"] * params.weight_trend +
        df["score_liquidity"] * params.weight_liquidity
    ).round(1)

    return df


def _screen_strangle(puts_df: pd.DataFrame, calls_df: pd.DataFrame,
                     current_price: float, params: ScreeningParams,
                     tech_signal: Optional[TechSignal]) -> pd.DataFrame:
    """Screent Short Strangles: kombiniert OTM Put + OTM Call gleicher Expiry."""

    # Puts und Calls separat aufbereiten
    put_params = ScreeningParams(
        strategy="Cash Covered Put",
        delta_min=params.delta_min,
        delta_max=params.delta_max,
        dte_min=params.dte_min,
        dte_max=params.dte_max,
        iv_min=params.iv_min,
        premium_min=params.premium_min * 0.5,
        min_open_interest=params.min_open_interest,
    )
    call_params = ScreeningParams(
        strategy="Covered Call",
        delta_min=params.delta_min,
        delta_max=params.delta_max,
        dte_min=params.dte_min,
        dte_max=params.dte_max,
        iv_min=params.iv_min,
        premium_min=params.premium_min * 0.5,
        min_open_interest=params.min_open_interest,
    )

    puts_screened = screen_options(puts_df, calls_df, current_price, put_params, tech_signal)
    calls_screened = screen_options(puts_df, calls_df, current_price, call_params, tech_signal)

    if puts_screened.empty or calls_screened.empty:
        return pd.DataFrame()

    # Nach Expiry gruppieren und kombinieren
    strangles = []
    for exp in set(puts_screened["Verfall"].unique()) & set(calls_screened["Verfall"].unique()):
        exp_puts = puts_screened[puts_screened["Verfall"] == exp]
        exp_calls = calls_screened[calls_screened["Verfall"] == exp]

        for _, put_row in exp_puts.iterrows():
            for _, call_row in exp_calls.iterrows():
                put_strike = float(put_row["Strike"])
                call_strike = float(call_row["Strike"])
                if call_strike <= put_strike:
                    continue

                total_premium = float(put_row.get("Prämie", 0)) + float(call_row.get("Prämie", 0))
                dte = int(put_row.get("DTE", 0))
                width = call_strike - put_strike
                width_pct = width / current_price * 100

                # ── U10: Überarbeitetes Strangle-Scoring ─────────────────────────────
                # Credit-to-Width Ratio (CWR): Prämie / Breite (höher = besser)
                cwr = total_premium / width if width > 0 else 0
                cwr_pct = cwr * 100  # in % der Breite

                # Delta-Balance: idealer Weise |Put-Delta| ≈ |Call-Delta|
                try:
                    pd_abs = abs(float(str(put_row.get("Delta", "0.2")).replace("–", "-")))
                    cd_abs = abs(float(str(call_row.get("Delta", "0.2")).replace("–", "-")))
                    delta_balance = max(0, 100 - abs(pd_abs - cd_abs) * 500)
                except Exception:
                    pd_abs, cd_abs, delta_balance = 0.2, 0.2, 50.0

                # Annualisierte Gesamtrendite auf gebundenes Kapital
                # Für Short Strangle = Prämie / Breite * 365/DTE * 100
                ann_yield = cwr * (365 / max(dte, 1)) * 100

                # Sicherheitspuffer (Abstand Kurs zu den Strikes)
                put_buffer  = (current_price - put_strike) / current_price * 100
                call_buffer = (call_strike - current_price) / current_price * 100
                avg_buffer  = (put_buffer + call_buffer) / 2

                # CRV Score für Strangles
                crv_strangle = (ann_yield * np.sqrt(1 + avg_buffer / 10)) / ((pd_abs + cd_abs) / 2 + 0.05)

                # Gesamtscore: CWR % + Delta-Balance + Puffer
                total_score = (
                    min(cwr_pct * 10, 40) +         # max 40 Punkte (CWR)
                    delta_balance * 0.3 +            # max 30 Punkte (Balance)
                    min(avg_buffer * 2, 30)          # max 30 Punkte (Puffer)
                )

                strangles.append({
                    "Verfall": exp,
                    "DTE": dte,
                    "Put Strike": put_strike,
                    "Call Strike": call_strike,
                    "Breite": round(width, 2),
                    "Breite %": round(width_pct, 1),
                    "Put Prämie": round(float(put_row.get("Prämie", 0)), 2),
                    "Call Prämie": round(float(call_row.get("Prämie", 0)), 2),
                    "Gesamt-Prämie": round(total_premium, 2),
                    "CWR %": round(cwr_pct, 2),
                    "Ann. Rendite %": round(ann_yield, 1),
                    "Prämie/Tag": round(total_premium / max(1, dte), 3),
                    "Put Delta": round(pd_abs, 3),
                    "Call Delta": round(cd_abs, 3),
                    "Delta Balance": round(delta_balance, 0),
                    "Put Puffer %": round(put_buffer, 1),
                    "Call Puffer %": round(call_buffer, 1),
                    "IV Put %": put_row.get("IV %", ""),
                    "IV Call %": call_row.get("IV %", ""),
                    "Put OI": put_row.get("OI", ""),
                    "Call OI": call_row.get("OI", ""),
                    "CRV Score": round(crv_strangle, 1),
                    "Score": round(total_score, 1),
                })

    if not strangles:
        return pd.DataFrame()

    result = pd.DataFrame(strangles)
    result = result.sort_values("Score", ascending=False).reset_index(drop=True)
    return result


def _format_output(df: pd.DataFrame, current_price: float, option_type: str) -> pd.DataFrame:
    """Formatiert den Output-DataFrame für die UI."""
    if df.empty:
        return df

    df = df.copy()

    # Moneyness-Label
    def moneyness_label(row):
        otm = row.get("otm_pct", 0)
        if otm > 0.5:
            return f"OTM {otm:.1f}%"
        else:
            return "ATM"

    oi_col  = df["openInterest"].fillna(0).astype(int) if "openInterest" in df.columns else pd.Series(0, index=df.index)
    vol_col = df["volume"].fillna(0).astype(int)       if "volume"        in df.columns else pd.Series(0, index=df.index)

    # Rendite auf Laufzeit (% des Strikes = eingesetztes Kapital)
    rendite_laufzeit = (df["mid_price"] / df["strike"] * 100).round(2)
    roi_ann = df.get(
        "roi_annualized",
        (df["mid_price"] / df["strike"] * (365 / df["dte"].clip(lower=1)) * 100)
    ).round(1)

    # Liquiditäts-Label pro Zeile
    liq_label = df.apply(
        lambda r: _liquidity_label(
            r.get("spread_pct", 999),
            int(r.get("openInterest", 0) or 0),
            int(r.get("volume", 0) or 0),
        ), axis=1
    )

    rendite_per_day = (rendite_laufzeit / df["dte"].clip(lower=1)).round(4)

    output = pd.DataFrame({
        "Liq.": liq_label,
        "Strike": df["strike"].round(2),
        "Verfall": df["expiration"],
        "DTE": df["dte"].astype(int),
        "Bid": df["bid"].round(2)       if "bid" in df.columns else pd.Series(float("nan"), index=df.index),
        "Ask": df["ask"].round(2)       if "ask" in df.columns else pd.Series(float("nan"), index=df.index),
        "Prämie": df["mid_price"].round(2),
        "Kursquelle": df["price_source"] if "price_source" in df.columns else "Mid",
        "Spread %": df["spread_pct"].replace(999.0, float("nan")).round(1)
                    if "spread_pct" in df.columns else pd.Series(float("nan"), index=df.index),
        "Prämie/Tag": df.get("premium_per_day", df["mid_price"] / df["dte"].clip(1)).round(3),
        "Rendite % Laufzeit": rendite_laufzeit,
        "Rendite ann. %": roi_ann,
        "Rendite %/Tag": rendite_per_day,
        "Delta": df["delta"].round(3) if "delta" in df.columns else pd.Series(float("nan"), index=df.index),
        "Theta/Tag": df["theta"].round(3) if "theta" in df.columns else pd.Series(float("nan"), index=df.index),
        "IV %": (df["impliedVolatility"] * 100).round(1) if "impliedVolatility" in df.columns else pd.Series(float("nan"), index=df.index),
        "OTM %": df["otm_pct"].round(1),
        "OI": oi_col,
        "Volumen": vol_col,
        "Score": df["score"],
        "_highlight": df["score"] >= df["score"].quantile(0.75),
    })

    output = output.sort_values("Score", ascending=False).reset_index(drop=True)
    return output
