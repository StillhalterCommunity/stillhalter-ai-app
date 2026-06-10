"""
Stillhalter AI — Signal-Engine
• evaluate_status()   : deterministische Status-Maschine (§2 der Spec)
• candidate_card_from_row() : Scan-Zeile → TradeCard-Entwurf
• signal_grade()      : CRV + Konvergenz + IV-Rank → A+…C
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Optional, Tuple

import pandas as pd

from data.trade_store import (
    Expression,
    ManagementRules,
    ModelEntry,
    SignalComponents,
    StatusEvent,
    TradeCard,
    new_trade_id,
)

# ── Status-Maschine (§2) ──────────────────────────────────────────────────────

_CLOSED = {"CLOSE", "CANCELLED", "EXPIRED", "REVIEWED"}


def evaluate_status(card: TradeCard, market: dict) -> Tuple[str, str]:
    """
    Berechnet neuen Status deterministisch aus Marktdaten.

    market = {
        "price":           float,  # aktueller Kurs des Underlyings
        "delta":           float,  # aktuelles |Delta| der Option
        "dte":             int,    # verbleibende Laufzeit in Tagen
        "option_price":    float,  # aktueller Optionspreis (Mid)
        "iv":              float,  # aktuelle IV 0–1
        "support_broken":  bool,   # True wenn Unterstützung gebrochen
    }
    Gibt (new_status, reason) zurück — reason="" wenn kein Wechsel.
    """
    s   = card.status
    m   = card.management
    abs_delta = abs(float(market.get("delta", 0)))
    dte       = int(market.get("dte", 0))

    # P/L berechnen (nur wenn Modell-Entry vorhanden)
    pnl_pct: Optional[float] = None
    if card.entry and card.entry.entry_credit > 0:
        cur = float(market.get("option_price", card.entry.entry_credit))
        pnl_pct = (card.entry.entry_credit - cur) / card.entry.entry_credit

    # ── Transitions ───────────────────────────────────────────────────────────
    if s == "NEU":
        if card.entry:
            return "AKTIV", "Modell-Entry vorhanden → aktiviert"

    if s == "AKTIV":
        if dte == 0 and abs_delta < 0.10:
            return "EXPIRED", "Option verfallen (OTM)"
        if pnl_pct is not None and pnl_pct >= m.take_profit_pct:
            return "CLOSE", f"Take Profit {pnl_pct*100:.0f}% ≥ {m.take_profit_pct*100:.0f}% erreicht"
        if abs_delta >= m.roll_delta * 0.85:
            return "WATCH", f"Delta {abs_delta:.2f} nähert sich Roll-Schwelle {m.roll_delta:.2f}"

    if s == "WATCH":
        if market.get("support_broken"):
            return "WARNING", "Support-Bruch — Strike bedroht"
        if abs_delta >= m.roll_delta:
            return "WARNING", f"Delta {abs_delta:.2f} ≥ Roll-Delta {m.roll_delta:.2f}"
        if abs_delta < m.roll_delta * 0.70:
            return "AKTIV", "Delta erholt — Entwarnung"

    if s == "WARNING":
        if dte <= m.roll_dte or abs_delta >= m.roll_delta:
            return "ROLL", (
                f"DTE {dte} ≤ {m.roll_dte} "
                f"oder Delta {abs_delta:.2f} ≥ {m.roll_delta:.2f}"
            )

    # Verfall OTM: alle offenen Status
    if dte == 0 and s not in _CLOSED and abs_delta < 0.10:
        return "EXPIRED", "Option wertlos verfallen"

    return s, ""   # kein Wechsel


def apply_status_change(card: TradeCard, new_status: str, reason: str) -> TradeCard:
    """Fügt StatusEvent hinzu und gibt neue (unveränderliche) Card zurück."""
    if new_status == card.status and not reason:
        return card
    event = StatusEvent(
        ts=datetime.now().isoformat(),
        status=new_status,
        note=reason,
    )
    return replace(
        card,
        status=new_status,
        status_history=[*card.status_history, event],
    )


# ── Signal-Grade ──────────────────────────────────────────────────────────────

def signal_grade(crv: float, convergence: float, iv_rank: float) -> str:
    """
    Berechnet Signal-Grade aus CRV-Score, Konvergenz-Score und IV-Rank.
    Gewichtung: CRV 40 % · Konvergenz 40 % · IV-Rank 20 %
    """
    score = (
        min(crv / 200, 1.0) * 40
        + min(convergence / 100, 1.0) * 40
        + min(iv_rank / 100, 1.0) * 20
    )
    if score >= 80: return "A+"
    if score >= 70: return "A"
    if score >= 60: return "A-"
    if score >= 50: return "B+"
    if score >= 40: return "B"
    if score >= 30: return "B-"
    return "C"


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def _risk_class(delta: float, otm_pct: float) -> str:
    abs_d = abs(delta)
    if abs_d <= 0.20 and otm_pct >= 7:
        return "defensiv"
    if abs_d <= 0.30 and otm_pct >= 4:
        return "balanced"
    return "opportunistisch"


def _view_from_ta(sc_trend: str, macd_str: str) -> str:
    sc = sc_trend.lower()
    mc = macd_str.lower()
    bull_t  = "bull" in sc or "↑" in sc
    bear_t  = "bear" in sc or "↓" in sc
    bull_m  = "bull" in mc or "↑cross" in mc
    if bull_t and bull_m:  return "bullisch"
    if bull_t:             return "bullisch-neutral"
    if bear_t:             return "bärisch-neutral"
    return "neutral"


def _laufzeit_bucket(dte: int) -> str:
    if dte <= 2:   return "1-2T"
    if dte <= 21:  return "7-21T"
    if dte <= 90:  return "1-3M"
    return "1-3J"


def _iv_rank_estimate(row: pd.Series) -> float:
    """Schätzt IV-Rank aus Row-Daten (0–100)."""
    iv_rank_raw = str(row.get("IV Rank", ""))
    try:
        if "H" in iv_rank_raw.upper(): return 80.0
        if "M" in iv_rank_raw.upper(): return 50.0
        if "L" in iv_rank_raw.upper(): return 25.0
        val = float(iv_rank_raw.replace("%", "").strip())
        return max(0.0, min(100.0, val))
    except Exception:
        iv_pct = float(row.get("IV %", 25))
        # Lineare Schätzung: 15 % → 0, 65 % → 100
        return max(0.0, min(100.0, (iv_pct - 15) * 2))


# ── Default Management ────────────────────────────────────────────────────────

DEFAULT_MGMT = ManagementRules(
    take_profit_pct=0.50,
    roll_dte=21,
    roll_delta=0.30,
    warning="Support-Bruch | IV-Spike > 50 % | Delta > 0.45",
    cancel="Signalverschlechterung oder Gap-Down > 5 %",
)


# ── Kandidaten-Karte aus Scan-Zeile ──────────────────────────────────────────

def candidate_card_from_row(row: pd.Series, thesis: str = "") -> TradeCard:
    """Erstellt einen vollständigen TradeCard-Entwurf aus einer Scan-Zeile."""
    ticker  = str(row.get("Ticker", ""))
    strike  = float(row.get("Strike", 0))
    dte     = int(row.get("DTE", 30))
    delta   = float(row.get("Delta", -0.20))
    iv_pct  = float(row.get("IV %", 25))
    otm_pct = float(row.get("OTM %", 5))
    premium = float(row.get("Prämie", 0))
    crv     = float(row.get("CRV Score", 0))
    conv    = float(row.get("Konvergenz", 0))
    expiry  = str(row.get("Verfall", ""))
    kurs    = float(row.get("Kurs", strike * 1.05))
    sektor  = str(row.get("Sektor", ""))
    sc_trend = str(row.get("SC Trend(1D)", ""))
    macd_str = str(row.get("MACD(1D)", ""))
    strat    = str(row.get("Strategie", "Cash Covered Put"))

    is_call = "call" in strat.lower()
    strategy_str   = "Cash-Secured Put" if not is_call else "Covered Call"
    strategy_short = "CCP"              if not is_call else "CC"
    right_char     = "P"                if not is_call else "C"

    iv_rank = _iv_rank_estimate(row)
    # IV/RV-Schätzung: IV / (0.6 × IV) = 1.67 als Näherung wenn RV nicht verfügbar
    iv_rv   = round(iv_pct / max(iv_pct * 0.6, 1), 2) if iv_pct > 0 else 1.0

    earnings_raw    = str(row.get("⚠️ Earnings", "")).strip()
    earnings_status = "vor_earnings" if earnings_raw else "clear"

    oi     = float(row.get("OI", 0))
    spread = float(row.get("Spread %", 100))
    if oi > 500 and spread < 5:   liq = "hoch"
    elif oi > 50 and spread < 20: liq = "mittel"
    else:                          liq = "niedrig"

    components = SignalComponents(
        iv_rank=round(iv_rank, 1),
        iv_rv=iv_rv,
        trend=(
            "+" if ("bull" in sc_trend.lower() or "↑" in sc_trend) else
            "-" if ("bear" in sc_trend.lower() or "↓" in sc_trend) else
            "0"
        ),
        macd=(
            "bestätigt" if "bull" in macd_str.lower() else
            "gegen"     if "bear" in macd_str.lower() else
            "neutral"
        ),
        earnings=earnings_status,
        liquiditaet=liq,
    )

    cash_reserve = int(strike * 100)
    view         = _view_from_ta(sc_trend, macd_str)

    # ── Expressions ──────────────────────────────────────────────────────────
    # Einsteiger: Cash-Secured Put / Covered Call
    expr_einsteiger = Expression(
        eignung="einsteiger",
        strategy=strategy_str,
        strike_anchor=(
            f"Short {'Put' if not is_call else 'Call'} ~{otm_pct:.1f}% OTM "
            f"bei ${strike:.0f} (Kurs ${kurs:.0f})"
        ),
        strikes=f"{strike:.0f}",
        dte=dte,
        kapitalbedarf=f"~${cash_reserve:,} Collateral".replace(",", "."),
        defined_risk=False,
        optionstrat_url=(
            f"https://optionstrat.com/build/short-{'put' if not is_call else 'call'}"
            f"/{ticker}/-{strike:.0f}{right_char}{expiry.replace('-','')}"
        ),
        min_vip=False,
    )

    # Fortgeschritten: Put/Call Credit Spread (definiertes Risiko)
    spread_width = max(5, round(strike * 0.025 / 5) * 5)
    long_strike  = strike - spread_width if not is_call else strike + spread_width
    max_risk     = round((spread_width - premium) * 100, 0)
    expr_fortg = Expression(
        eignung="fortgeschritten",
        strategy="Put Credit Spread" if not is_call else "Call Credit Spread",
        strike_anchor=f"Spread {strike:.0f}/{long_strike:.0f} — definiertes Risiko ✅",
        strikes=f"{strike:.0f}/{long_strike:.0f}",
        dte=dte,
        kapitalbedarf=f"Max. Risiko ~${max_risk:,.0f}".replace(",", "."),
        defined_risk=True,
        optionstrat_url=(
            f"https://optionstrat.com/build/"
            f"{'bull-put' if not is_call else 'bear-call'}-spread/{ticker}/"
            f"-{strike:.0f}{right_char}{expiry.replace('-','')}"
            f",+{long_strike:.0f}{right_char}{expiry.replace('-','')}"
        ),
        min_vip=False,
    )

    # Profi: Naked Short (nur VIP)
    expr_profi = Expression(
        eignung="profi",
        strategy=f"Short {'Put' if not is_call else 'Call'} (naked)",
        strike_anchor=f"Strike ${strike:.0f} ohne Hedge — erfordert hohes Margin",
        strikes=f"{strike:.0f}",
        dte=dte,
        kapitalbedarf=f"Margin ~${cash_reserve:,} (broker-abhängig)".replace(",", "."),
        defined_risk=False,
        optionstrat_url=expr_einsteiger.optionstrat_url,
        min_vip=True,
    )

    grade = signal_grade(crv, conv, iv_rank)

    auto_thesis = thesis or (
        f"{ticker} zeigt {'bullisches' if '+' in components.trend else 'neutrales'} "
        f"Setup mit IV-Rank {iv_rank:.0f}/100 — Prämie ${premium:.2f} "
        f"bei {otm_pct:.1f}% Sicherheitsabstand ({dte}T Laufzeit, "
        f"Sektor: {sektor or 'k.A.'})."
    )

    # Gamma-Risiko ultra-kurzer Laufzeiten: 1-2T nur VIP
    is_ultra_short = dte <= 2
    visibility = {
        "daily":       not is_ultra_short and not expr_einsteiger.min_vip,
        "masterclass": True,
        "vip":         True,
    }

    return TradeCard(
        trade_id=new_trade_id(ticker, strategy_short),
        ticker=ticker,
        view=view,
        risk_class=_risk_class(delta, otm_pct),
        laufzeit=_laufzeit_bucket(dte),
        signal_grade=grade,
        components=components,
        thesis=auto_thesis,
        expressions=[expr_einsteiger, expr_fortg, expr_profi],
        management=DEFAULT_MGMT,
        source="model",
        entry=None,
        status="NEU",
        status_history=[
            StatusEvent(
                ts=datetime.now().isoformat(),
                status="NEU",
                note="Kandidat aus Scan-Ergebnis",
            )
        ],
        visibility=visibility,
    )
