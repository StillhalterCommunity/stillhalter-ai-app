"""
Black-Scholes Greeks Berechnung.
Wird verwendet wenn yfinance keine Greeks liefert.
"""

import numpy as np
from scipy.stats import norm


RISK_FREE_RATE = 0.05  # aktueller risikofreier Zinssatz (ca. US T-Bill)


def _d1_d2(S: float, K: float, T: float, r: float, sigma: float) -> tuple[float, float]:
    """Berechnet d1 und d2 für Black-Scholes."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0, 0.0
    d1 = (np.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * np.sqrt(T))
    d2 = d1 - sigma * np.sqrt(T)
    return d1, d2


def bs_delta(S: float, K: float, T: float, sigma: float, option_type: str = "put") -> float:
    """
    Black-Scholes Delta.
    S: aktueller Kurs
    K: Strike
    T: Zeit bis Verfall in Jahren
    sigma: Implied Volatility (als Dezimalzahl, z.B. 0.30 = 30%)
    """
    r = RISK_FREE_RATE
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    if d1 == 0 and d2 == 0:
        return 0.0

    if option_type == "call":
        return float(norm.cdf(d1))
    else:  # put
        return float(norm.cdf(d1) - 1)


def bs_theta(S: float, K: float, T: float, sigma: float, option_type: str = "put") -> float:
    """
    Black-Scholes Theta pro Tag (negativer Wert = Zeitwertverlust).
    """
    if T <= 0:
        return 0.0
    r = RISK_FREE_RATE
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    if d1 == 0 and d2 == 0:
        return 0.0

    theta_per_year = -(S * norm.pdf(d1) * sigma) / (2 * np.sqrt(T))

    if option_type == "call":
        theta_per_year -= r * K * np.exp(-r * T) * norm.cdf(d2)
    else:  # put
        theta_per_year += r * K * np.exp(-r * T) * norm.cdf(-d2)

    return float(theta_per_year / 365)


def bs_gamma(S: float, K: float, T: float, sigma: float) -> float:
    """Black-Scholes Gamma (gleich für Put und Call)."""
    if T <= 0:
        return 0.0
    r = RISK_FREE_RATE
    d1, _ = _d1_d2(S, K, T, r, sigma)
    return float(norm.pdf(d1) / (S * sigma * np.sqrt(T)))


def bs_vega(S: float, K: float, T: float, sigma: float) -> float:
    """Black-Scholes Vega (1% IV-Änderung)."""
    if T <= 0:
        return 0.0
    r = RISK_FREE_RATE
    d1, _ = _d1_d2(S, K, T, r, sigma)
    return float(S * norm.pdf(d1) * np.sqrt(T) / 100)  # per 1% IV


def bs_price(S: float, K: float, T: float, sigma: float, option_type: str = "put") -> float:
    """Theoretischer Black-Scholes Preis."""
    if T <= 0:
        return max(0, K - S) if option_type == "put" else max(0, S - K)
    r = RISK_FREE_RATE
    d1, d2 = _d1_d2(S, K, T, r, sigma)
    if d1 == 0 and d2 == 0:
        return 0.0

    if option_type == "call":
        return float(S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2))
    else:
        return float(K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))


def _solve_iv(price: float, S: float, K: float, T: float,
              option_type: str = "put", r: float = RISK_FREE_RATE) -> float:
    """
    Berechnet Implied Volatility aus dem Marktpreis (Brent-Solver).
    Gibt 0.30 als Fallback zurück wenn keine Lösung gefunden wird.
    """
    if T <= 0 or price <= 0 or S <= 0 or K <= 0:
        return 0.30
    intrinsic = max(0.0, K - S) if option_type == "put" else max(0.0, S - K)
    if price <= intrinsic + 1e-6:
        return 0.001
    try:
        from scipy.optimize import brentq
        def objective(sigma):
            return bs_price(S, K, T, sigma, option_type) - price
        # IV zwischen 0.5% und 500%
        lo, hi = 0.005, 5.0
        if objective(lo) * objective(hi) > 0:
            return 0.30  # kein Vorzeichenwechsel → kein Schnittpunkt
        return float(brentq(objective, lo, hi, xtol=1e-5, maxiter=100))
    except Exception:
        return 0.30


def _yahoo_iv_valid(sigma: float, price: float, S: float, K: float, T: float,
                    option_type: str) -> bool:
    """
    Prüft ob Yahoo-IV plausibel ist: BS-Preis mit dieser IV muss innerhalb
    50% des echten Preises liegen. Yahoo liefert oft Placeholder-IVs (0.03, 0.06...).
    """
    if sigma <= 0.01 or sigma > 4.0 or price <= 0 or T <= 0:
        return False
    try:
        theo = bs_price(S, K, T, sigma, option_type)
        return abs(theo - price) / max(price, 0.01) < 0.50
    except Exception:
        return False


def enrich_options_with_greeks(df, current_price: float, option_type: str = "put") -> object:
    """
    Ergänzt einen Options-DataFrame um berechnete Greeks.
    IV-Strategie:
      1. Yahoo-IV verwenden wenn plausibel (BS-Preis ≈ Marktpreis ± 50%)
      2. Sonst: IV aus mid_price / lastPrice zurückrechnen (IV-Solver)
      3. Fallback: 0.30 (30%)
    """
    import pandas as pd

    if df.empty or current_price is None or current_price <= 0:
        return df

    df = df.copy()

    # DTE in Jahren für BS
    from data.fetcher import calculate_dte
    df["dte"] = df["expiration"].apply(calculate_dte)
    df["T"] = df["dte"] / 365.0

    iv_col = "impliedVolatility" if "impliedVolatility" in df.columns else None
    deltas, thetas, gammas, vegas, ivs_used = [], [], [], [], []

    for _, row in df.iterrows():
        K = float(row.get("strike", 0))
        T = float(row.get("T", 0))
        yahoo_iv = float(row.get("impliedVolatility", 0.0)) if iv_col else 0.0

        # Marktpreis für IV-Solver (mid_price bevorzugt, dann lastPrice)
        mkt_price = float(row.get("mid_price", 0.0) or row.get("lastPrice", 0.0))

        # IV bestimmen
        if _yahoo_iv_valid(yahoo_iv, mkt_price, current_price, K, T, option_type):
            sigma = yahoo_iv          # Yahoo-IV ist plausibel
        elif mkt_price > 0 and T > 0:
            sigma = _solve_iv(mkt_price, current_price, K, T, option_type)
        else:
            sigma = 0.30              # letzter Fallback

        sigma = max(0.01, min(sigma, 4.0))  # Clip

        deltas.append(bs_delta(current_price, K, T, sigma, option_type))
        thetas.append(bs_theta(current_price, K, T, sigma, option_type))
        gammas.append(bs_gamma(current_price, K, T, sigma))
        vegas.append(bs_vega(current_price, K, T, sigma))
        ivs_used.append(sigma)

    df["delta"] = deltas
    df["theta"] = thetas
    df["gamma"] = gammas
    df["vega"] = vegas
    df["iv_used"] = ivs_used   # tatsächlich verwendete IV (für Debugging)

    return df
