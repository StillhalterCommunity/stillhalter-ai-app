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


def enrich_options_with_greeks(df, current_price: float, option_type: str = "put") -> object:
    """
    Ergänzt einen Options-DataFrame um berechnete Greeks.
    Nutzt IV aus yfinance falls vorhanden.
    """
    import pandas as pd

    if df.empty or current_price is None or current_price <= 0:
        return df

    df = df.copy()

    # DTE in Jahren für BS
    from data.fetcher import calculate_dte
    df["dte"] = df["expiration"].apply(calculate_dte)
    df["T"] = df["dte"] / 365.0

    # IV aus yfinance (als Dezimalzahl)
    iv_col = "impliedVolatility" if "impliedVolatility" in df.columns else None

    deltas, thetas, gammas, vegas = [], [], [], []

    for _, row in df.iterrows():
        K = float(row.get("strike", 0))
        T = float(row.get("T", 0))
        sigma = float(row.get("impliedVolatility", 0.30)) if iv_col else 0.30

        if sigma <= 0 or sigma > 5:
            sigma = 0.30  # Fallback bei ungültiger IV

        deltas.append(bs_delta(current_price, K, T, sigma, option_type))
        thetas.append(bs_theta(current_price, K, T, sigma, option_type))
        gammas.append(bs_gamma(current_price, K, T, sigma))
        vegas.append(bs_vega(current_price, K, T, sigma))

    df["delta"] = deltas
    df["theta"] = thetas
    df["gamma"] = gammas
    df["vega"] = vegas

    return df
