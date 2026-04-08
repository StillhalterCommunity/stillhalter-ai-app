"""
Stillhalter AI App — Options Analytics
Max Pain · Gamma Exposure (GEX) · Put/Call Ratio · IV Skew

Alle Berechnungen basieren auf der aktuellen Options Chain (yfinance).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from dataclasses import dataclass, field
from typing import Optional, List, Dict


# ── Datenklassen ───────────────────────────────────────────────────────────────

@dataclass
class OptionsAnalytics:
    ticker: str
    current_price: float = 0.0
    expiry: str = ""

    # Max Pain
    max_pain: float = 0.0            # Strike mit maximalem Käufer-Verlust
    max_pain_distance_pct: float = 0.0  # Abstand Kurs → Max Pain in %

    # Gamma Exposure
    gex_total: float = 0.0           # Gesamt-GEX (positiv = stabilisierend)
    gex_per_strike: Dict[float, float] = field(default_factory=dict)
    gex_largest_strike: float = 0.0  # Strike mit höchstem absoluten GEX
    gex_flip_level: float = 0.0      # Strike wo GEX von + nach - wechselt

    # Put/Call Ratio
    pcr_oi: float = 0.0              # OI-basiert
    pcr_volume: float = 0.0          # Volumen-basiert
    pcr_signal: str = "neutral"      # "fear" (PCR>1.5) | "greed" (PCR<0.5) | "neutral"

    # IV Skew
    iv_skew: float = 0.0             # IV(25Δ-Put) − IV(25Δ-Call) in %
    iv_atm: float = 0.0              # IV der ATM-Option in %
    iv_put_25d: float = 0.0          # IV des 25-Delta-Puts
    iv_call_25d: float = 0.0         # IV des 25-Delta-Calls
    skew_signal: str = "neutral"     # "put_skew" | "call_skew" | "neutral"

    # Zusammenfassung
    summary: str = ""
    error: str = ""

    # Rohdaten für Charts
    strikes_df: Optional[pd.DataFrame] = field(default=None, repr=False)


@dataclass
class IVRankResult:
    ticker: str
    iv_current: float = 0.0     # Aktuelle IV (aus Options Chain, %)
    iv_rank: float = 0.0        # IV Rank 0-100: Position im 52W-Bereich
    iv_percentile: float = 0.0  # IV Percentile: Anteil der Tage mit niedrigerer IV
    iv_52w_high: float = 0.0
    iv_52w_low: float = 0.0
    iv_signal: str = "neutral"  # "high_iv" (>50 Rank) | "low_iv" (<25 Rank) | "neutral"
    error: str = ""


# ── Max Pain ──────────────────────────────────────────────────────────────────

def calculate_max_pain(
    calls: pd.DataFrame, puts: pd.DataFrame, strikes: List[float]
) -> float:
    """
    Max Pain = Strike mit maximalem kombinierten Verlust aller Options-Käufer.

    Methode: Für jeden Strike als "Verfall-Preis" berechne:
      - Verlust aller Call-Käufer: Σ max(0, strike_call - test_strike) × OI
      - Verlust aller Put-Käufer:  Σ max(0, test_strike - strike_put) × OI
    Der Strike mit der größten Summe = Max Pain.
    """
    if calls.empty and puts.empty:
        return 0.0

    min_pain = float("inf")
    max_pain_strike = strikes[len(strikes) // 2] if strikes else 0.0

    call_data = [(float(row.get("strike", 0)), int(row.get("openInterest", 0) or 0))
                 for _, row in calls.iterrows()]
    put_data  = [(float(row.get("strike", 0)), int(row.get("openInterest", 0) or 0))
                 for _, row in puts.iterrows()]

    for test_strike in strikes:
        # Verlust der Call-Käufer (Call ist ITM wenn Kurs > Strike → verlieren alle Calls über test_strike)
        call_loss = sum(
            max(0.0, test_strike - s) * oi
            for s, oi in call_data
        )
        # Verlust der Put-Käufer (Put ist ITM wenn Kurs < Strike → verlieren alle Puts unter test_strike)
        put_loss = sum(
            max(0.0, s - test_strike) * oi
            for s, oi in put_data
        )
        total_pain = call_loss + put_loss

        if total_pain < min_pain:
            min_pain = total_pain
            max_pain_strike = test_strike

    return max_pain_strike


# ── Gamma Exposure ─────────────────────────────────────────────────────────────

def calculate_gex(
    calls: pd.DataFrame, puts: pd.DataFrame,
    current_price: float, strikes: List[float]
) -> Dict[float, float]:
    """
    Gamma Exposure (GEX) je Strike.

    GEX = Gamma × OI × 100 × S²
    Calls: +GEX (Dealer long Calls = short Gamma → stabilisierend wenn positiv)
    Puts:  −GEX (Dealer short Puts = long Gamma → destabilisierend wenn negativ)

    Vereinfacht: Wir nutzen die impliziten Gammas aus der Options Chain.
    Falls keine Gamma-Daten: Approximation über ATM-Nähe.
    """
    if current_price <= 0:
        return {}

    gex_map: Dict[float, float] = {}

    for _, row in calls.iterrows():
        s   = float(row.get("strike", 0) or 0)
        oi  = int(row.get("openInterest", 0) or 0)
        gam = float(row.get("gamma", 0) or 0)
        if s > 0 and oi > 0:
            if gam == 0:
                # Approximation: Gamma höher nahe ATM
                moneyness = abs(s - current_price) / current_price
                gam = max(0.001, 0.05 * np.exp(-0.5 * (moneyness / 0.02) ** 2))
            gex_map[s] = gex_map.get(s, 0.0) + gam * oi * 100 * current_price ** 2 / 1e6

    for _, row in puts.iterrows():
        s   = float(row.get("strike", 0) or 0)
        oi  = int(row.get("openInterest", 0) or 0)
        gam = float(row.get("gamma", 0) or 0)
        if s > 0 and oi > 0:
            if gam == 0:
                moneyness = abs(s - current_price) / current_price
                gam = max(0.001, 0.05 * np.exp(-0.5 * (moneyness / 0.02) ** 2))
            # Puts: Dealer sind typischerweise short Puts → negative GEX
            gex_map[s] = gex_map.get(s, 0.0) - gam * oi * 100 * current_price ** 2 / 1e6

    return gex_map


def find_gex_flip_level(gex_map: Dict[float, float], current_price: float) -> float:
    """
    GEX Flip Level: der Strike, wo kumulierter GEX das Vorzeichen wechselt.
    Unterhalb: negative GEX (Volatilität wird verstärkt).
    Oberhalb: positive GEX (Volatilität wird gedämpft).
    """
    if not gex_map:
        return current_price

    sorted_strikes = sorted(gex_map.keys())
    cumulative = 0.0
    flip = current_price

    for s in sorted_strikes:
        prev = cumulative
        cumulative += gex_map[s]
        if prev <= 0 <= cumulative or prev >= 0 >= cumulative:
            flip = s
            break

    return flip


# ── Put/Call Ratio ─────────────────────────────────────────────────────────────

def calculate_pcr(calls: pd.DataFrame, puts: pd.DataFrame) -> tuple:
    """PCR basierend auf Open Interest und Volumen."""
    call_oi  = int(calls["openInterest"].fillna(0).sum())
    put_oi   = int(puts["openInterest"].fillna(0).sum())
    call_vol = int(calls["volume"].fillna(0).sum())
    put_vol  = int(puts["volume"].fillna(0).sum())

    pcr_oi  = put_oi  / max(call_oi,  1)
    pcr_vol = put_vol / max(call_vol, 1)

    return round(pcr_oi, 2), round(pcr_vol, 2)


# ── IV Skew ────────────────────────────────────────────────────────────────────

def calculate_iv_skew(
    calls: pd.DataFrame, puts: pd.DataFrame,
    current_price: float,
    target_delta: float = 0.25
) -> tuple:
    """
    IV Skew: IV(25Δ Put) − IV(25Δ Call).
    Positiver Skew = Markt zahlt Prämie für Downside-Absicherung.

    Näherung: 25Δ-Put ≈ Strike bei ~90% des Kurses (abhängig von IV/DTE).
    Wir wählen den OTM-Strike nahe OTM%=10% als Proxy.
    """
    if current_price <= 0:
        return 0.0, 0.0, 0.0, 0.0

    def _nearest_iv(df: pd.DataFrame, target_strike: float) -> float:
        if df.empty:
            return 0.0
        df2 = df[df["impliedVolatility"].notna() & (df["impliedVolatility"] > 0)].copy()
        if df2.empty:
            return 0.0
        idx = (df2["strike"] - target_strike).abs().idxmin()
        iv  = float(df2.loc[idx, "impliedVolatility"])
        return round(iv * 100, 1)

    # ATM
    iv_atm = _nearest_iv(
        pd.concat([calls, puts]),
        current_price
    )

    # 25Δ-Put ≈ 90% des Kurses (grobe Näherung)
    put_target   = current_price * (1 - target_delta * 0.4)
    call_target  = current_price * (1 + target_delta * 0.4)

    iv_put  = _nearest_iv(puts,  put_target)
    iv_call = _nearest_iv(calls, call_target)
    iv_skew = round(iv_put - iv_call, 1)

    return iv_skew, iv_atm, iv_put, iv_call


# ── IV Rank & Percentile ───────────────────────────────────────────────────────

@st.cache_data(ttl=3600, show_spinner=False)
def calculate_iv_rank(ticker: str, current_iv: Optional[float] = None) -> IVRankResult:
    """
    IV Rank: Position der aktuellen IV im 52-Wochen-Bereich.
    IV Percentile: Anteil der Handelstage mit niedrigerer IV.

    IV Rank   = (IV_now − IV_52w_low) / (IV_52w_high − IV_52w_low) × 100
    IV %tile  = Anteil der Tage, an denen IV < IV_now war × 100
    """
    result = IVRankResult(ticker=ticker)
    try:
        stock = yf.Ticker(ticker)
        hist  = stock.history(period="1y", interval="1d")
        if hist.empty or len(hist) < 20:
            result.error = "Zu wenig Daten"
            return result

        # Historische Vola als IV-Proxy (30-Tage Realized Vol annualisiert)
        close = hist["Close"]
        log_ret = np.log(close / close.shift(1)).dropna()
        hvol_series = log_ret.rolling(20).std() * np.sqrt(252) * 100  # in %
        hvol_series = hvol_series.dropna()

        if hvol_series.empty:
            result.error = "Keine Vola-Daten"
            return result

        iv_now  = current_iv if current_iv and current_iv > 0 else float(hvol_series.iloc[-1])
        iv_high = float(hvol_series.max())
        iv_low  = float(hvol_series.min())

        result.iv_current    = round(iv_now, 1)
        result.iv_52w_high   = round(iv_high, 1)
        result.iv_52w_low    = round(iv_low, 1)
        result.iv_rank       = round((iv_now - iv_low) / max(iv_high - iv_low, 0.01) * 100, 1)
        result.iv_percentile = round(float((hvol_series < iv_now).mean() * 100), 1)

        if result.iv_rank > 50:
            result.iv_signal = "high_iv"    # Gute Zeit zum Verkaufen
        elif result.iv_rank < 25:
            result.iv_signal = "low_iv"     # Schlechte Prämien
        else:
            result.iv_signal = "neutral"

    except Exception as e:
        result.error = str(e)

    return result


# ── Haupt-Analyse ──────────────────────────────────────────────────────────────

@st.cache_data(ttl=900, show_spinner=False)
def analyze_options(ticker: str, expiry: Optional[str] = None) -> OptionsAnalytics:
    """
    Berechnet alle Options Analytics für einen Ticker.
    Nutzt die nächste verfügbare Expiry wenn keine angegeben.
    """
    result = OptionsAnalytics(ticker=ticker)
    try:
        stock = yf.Ticker(ticker)
        info  = stock.info
        result.current_price = float(info.get("regularMarketPrice") or
                                     info.get("currentPrice") or
                                     info.get("previousClose") or 0)

        # Expiry wählen
        expiries = stock.options
        if not expiries:
            result.error = "Keine Options-Daten"
            return result

        if expiry and expiry in expiries:
            use_expiry = expiry
        else:
            # Nächste verfügbare Expiry mit genug OI (mind. 30 Tage)
            import datetime
            today = datetime.date.today()
            candidates = [
                e for e in expiries
                if (pd.to_datetime(e).date() - today).days >= 14
            ]
            use_expiry = candidates[0] if candidates else expiries[0]

        result.expiry = use_expiry
        chain = stock.option_chain(use_expiry)
        calls = chain.calls.copy()
        puts  = chain.puts.copy()

        if calls.empty and puts.empty:
            result.error = "Leere Options Chain"
            return result

        S = result.current_price
        if S <= 0 and not calls.empty:
            S = float(calls["strike"].median())
            result.current_price = S

        # Strikes (±30% um aktuellen Kurs)
        all_strikes = sorted(set(
            list(calls["strike"].unique()) + list(puts["strike"].unique())
        ))
        strikes_filtered = [
            s for s in all_strikes
            if S * 0.70 <= s <= S * 1.30
        ]
        if not strikes_filtered:
            strikes_filtered = all_strikes

        # ── Max Pain ──────────────────────────────────────────────────────
        result.max_pain = calculate_max_pain(calls, puts, strikes_filtered)
        if S > 0 and result.max_pain > 0:
            result.max_pain_distance_pct = round(
                (result.max_pain - S) / S * 100, 2
            )

        # ── GEX ───────────────────────────────────────────────────────────
        gex_map = calculate_gex(calls, puts, S, strikes_filtered)
        result.gex_per_strike = gex_map
        result.gex_total = round(sum(gex_map.values()), 2)
        if gex_map:
            result.gex_largest_strike = max(gex_map, key=lambda k: abs(gex_map[k]))
            result.gex_flip_level = find_gex_flip_level(gex_map, S)

        # ── PCR ───────────────────────────────────────────────────────────
        result.pcr_oi, result.pcr_volume = calculate_pcr(calls, puts)
        if result.pcr_oi > 1.5:
            result.pcr_signal = "fear"       # Übergroße Angst → konträr bullish
        elif result.pcr_oi < 0.5:
            result.pcr_signal = "greed"      # Zu viel Gier → konträr bearish
        else:
            result.pcr_signal = "neutral"

        # ── IV Skew ───────────────────────────────────────────────────────
        result.iv_skew, result.iv_atm, result.iv_put_25d, result.iv_call_25d = \
            calculate_iv_skew(calls, puts, S)
        if result.iv_skew > 5:
            result.skew_signal = "put_skew"  # Puts teuer → Put verkaufen ist gut bepreist
        elif result.iv_skew < -5:
            result.skew_signal = "call_skew"
        else:
            result.skew_signal = "neutral"

        # ── Strikes DataFrame für Chart ───────────────────────────────────
        rows = []
        for s in strikes_filtered:
            c_row = calls[calls["strike"] == s].iloc[0] if not calls[calls["strike"] == s].empty else None
            p_row = puts[puts["strike"] == s].iloc[0]   if not puts[puts["strike"] == s].empty   else None
            rows.append({
                "Strike":   s,
                "Call OI":  int(c_row["openInterest"] or 0) if c_row is not None else 0,
                "Put OI":   int(p_row["openInterest"] or 0) if p_row is not None else 0,
                "Call Vol": int(c_row["volume"] or 0) if c_row is not None else 0,
                "Put Vol":  int(p_row["volume"] or 0) if p_row is not None else 0,
                "GEX":      round(gex_map.get(s, 0.0), 2),
            })
        result.strikes_df = pd.DataFrame(rows)

        # ── Zusammenfassung ───────────────────────────────────────────────
        parts = []
        if result.max_pain > 0:
            dir_mp = "↑" if result.max_pain > S else "↓"
            parts.append(f"Max Pain {dir_mp} ${result.max_pain:.2f} ({result.max_pain_distance_pct:+.1f}%)")
        if result.gex_total >= 0:
            parts.append(f"GEX positiv (+{result.gex_total:.0f}) → Markt gedämpft")
        else:
            parts.append(f"GEX negativ ({result.gex_total:.0f}) → Volatilität erhöht")

        pcr_txt = {"fear": "PCR hoch → Angst (konträr bullish)", "greed": "PCR niedrig → Gier (konträr bearish)"}.get(result.pcr_signal, f"PCR {result.pcr_oi:.2f} (neutral)")
        parts.append(pcr_txt)

        if result.skew_signal == "put_skew":
            parts.append(f"IV-Skew {result.iv_skew:+.1f}% → Puts teuer ✅ gut für Put-Verkauf")
        elif result.skew_signal == "call_skew":
            parts.append(f"IV-Skew {result.iv_skew:+.1f}% → Calls teuer ✅ gut für Call-Verkauf")

        result.summary = " · ".join(parts)

    except Exception as e:
        result.error = str(e)

    return result
