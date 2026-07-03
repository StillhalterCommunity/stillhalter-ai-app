"""
Stillhalter AI App — Trade Cards
Generiert WhatsApp-fertige Trading-Ideen im exakten Format.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
import pickle
import os
import re
import json
import uuid
import requests
import xml.etree.ElementTree as ET
import email.utils as _eutils
from datetime import datetime, timedelta, date
from urllib.parse import urlencode

st.set_page_config(
    page_title="Trade Cards · Stillhalter AI App",
    page_icon="📤",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

from data.fetcher import fetch_stock_info, fetch_fundamentals, fetch_price_history

# ── Konstanten ─────────────────────────────────────────────────────────────────
_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "last_scan_cache.pkl"
)
# Trades persistent ablegen: auf dem Volume (STILLHALTER_DATA_DIR), damit sie
# Neustarts überleben und so lange verfolgbar bleiben, wie sie laufen.
_TRADES_DIR = os.environ.get("STILLHALTER_DATA_DIR", "").strip()
if _TRADES_DIR:
    MANUAL_TRADES_PATH = os.path.join(_TRADES_DIR, "manual_trades.json")
else:
    MANUAL_TRADES_PATH = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "manual_trades.json"
    )

_DISCLAIMER = """\
Bitte bei höherem Risiko immer an Take Profit und Absicherung denken!

Höheres Risiko = Hohe Implizierte Volatilität der Aktie, anstehende Earnings oder News, VIX steigend, übergeordneter Trend des Marktes bzw. der Aktie gegenläufig zu Trade usw.

Take Profit = Position schließen bei 50% unrealisiertem Gewinn (Laufzeit > 7 Tage) bzw. 70% unrealisiertem Gewinn (Laufzeit < 3 Tage) usw.

Absicherung = Option passend zu Trendrichtung wählen, mehr Abstand zum Strike nehmen, Spreads nutzen (mit Long Position als Hedge), sichere Delta-Auswahl, längere Optionslaufzeit mit ggfs. Stop Loss, Option sollte "gut zu rollen" sein, Cash Reserve zum Reparieren vorhanden usw."""


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _load_scan_cache() -> dict | None:
    try:
        with open(_CACHE_PATH, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


def _fmt_expiry_trade(expiry) -> tuple[str, str, int]:
    """Gibt (trading_notation, german_date, dte_days) zurück."""
    try:
        d        = pd.to_datetime(expiry)
        trade_str  = d.strftime("%b") + str(d.day) + " " + d.strftime("'%y")
        german_str = d.strftime("%d.%m.%Y")
        dte        = max(0, (d.date() - date.today()).days)
        return trade_str, german_str, dte
    except Exception:
        return str(expiry), str(expiry), 0


def _ath_pct(ticker: str, strike: float) -> float | None:
    """Prozentuale Differenz zwischen ATH (2 Jahre) und Strike."""
    try:
        hist = fetch_price_history(ticker, period="2y")
        if hist.empty:
            return None
        ath = float(hist["Close"].max())
        if ath <= 0:
            return None
        return (ath - strike) / ath * 100
    except Exception:
        return None


def _fmt_num(val: float, decimals: int = 2) -> str:
    """Deutsche Zahlenformatierung: 4.11 → '4,11'"""
    fmt = f"{{:.{decimals}f}}"
    return fmt.format(val).replace(".", ",")


def _get_strategy_type(row: pd.Series) -> tuple[str, str]:
    """Gibt (option_type_str, strategie_str) zurück."""
    strat = str(row.get("Strategie", "Short PUT")).lower()
    if "strangle" in strat:
        return "PUT/CALL", "Short Strangle"
    elif "call" in strat:
        return "CALL", "Short CALL"
    else:
        return "PUT", "Short PUT"


def _get_sr_level(ticker: str, option_type: str, strike: float) -> str:
    """Berechnet Support (PUT) oder Widerstand (CALL) aus 1-Jahres-Preishistorie."""
    try:
        hist = fetch_price_history(ticker, period="1y")
        if hist.empty:
            return ""
        price_now = float(hist["Close"].iloc[-1])

        if "PUT" in option_type.upper():
            # Support: höchster Wert aus 52-W-Tief und 3-Monats-Tief
            low_52w   = float(hist["Low"].min())
            low_3m    = float(hist.tail(63)["Low"].min())
            support   = max(low_52w, low_3m)           # nächste Unterstützung (höher = näher)
            if support >= strike:                       # Support über dem Strike wäre irrelevant
                support = low_52w
            pct_below = (price_now - support) / price_now * 100
            return (
                "Unterstützung bei $" + f"{support:.0f}"
                + " (" + f"{pct_below:.1f}" + "% unter Kurs)"
                + " schützt den Strike"
            )
        else:
            # Resistance: 52-Wochen-Hoch
            high_52w     = float(hist["High"].max())
            pct_above    = (high_52w - price_now) / price_now * 100
            return (
                "Widerstand bei $" + f"{high_52w:.0f}"
                + " (ATH/52W-Hoch, +" + f"{pct_above:.1f}" + "% über Kurs)"
                + " begrenzt Aufwärtsrisiko"
            )
    except Exception:
        return ""


def _build_trend_note(row: pd.Series, otm_pct: float, sr_note: str = "") -> str:
    """Generiert automatisch die Absicherungs-Zeile inkl. Support/Widerstand."""
    otm_str  = _fmt_num(abs(otm_pct), 1)
    parts    = []

    # Support/Widerstand zuerst — das ist die wichtigste Information
    if sr_note:
        parts.append(sr_note)

    # Trend aus TA-Spalten
    sc_trend = str(row.get("SC Trend(1D)", "")).lower()
    macd     = str(row.get("MACD(1D)", "")).lower()

    if "bull" in sc_trend or "↑" in sc_trend:
        parts.append("Aufwärtstrend")
    elif "bear" in sc_trend or "↓" in sc_trend:
        parts.append("⚠️ Abwärtstrend — erhöhte Vorsicht")
    else:
        parts.append("neutrale Marktlage")

    parts.append(f"Strike {otm_str}% OTM")

    if "bull" in macd or "cross" in macd:
        parts.append("MACD bullish")

    earnings = str(row.get("⚠️ Earnings", "")).strip()
    if earnings:
        parts.append(f"⚠️ Earnings: {earnings}")

    return " · ".join(parts)


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_ticker_news_rss(ticker: str, n: int = 5, max_age_hours: int = 48) -> list[dict]:
    """Holt aktuelle News via Yahoo Finance RSS (max. max_age_hours alt)."""
    url    = f"https://finance.yahoo.com/rss/headline?s={ticker}"
    cutoff = datetime.utcnow() - timedelta(hours=max_age_hours)
    items  = []
    try:
        r = requests.get(url, timeout=8, headers={"User-Agent": "StillhalterApp/3.0"})
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        for item in root.findall(".//item"):
            title   = (item.findtext("title")   or "").strip()
            link    = (item.findtext("link")    or "").strip()
            pubdate = (item.findtext("pubDate") or "").strip()
            if not title:
                continue
            pub_dt: datetime | None = None
            if pubdate:
                try:
                    t = _eutils.parsedate(pubdate)
                    if t:
                        pub_dt = datetime(*t[:6])
                except Exception:
                    pass
            if pub_dt and pub_dt < cutoff:
                continue
            age_str = ""
            if pub_dt:
                age_h = int((datetime.utcnow() - pub_dt).total_seconds() / 3600)
                age_str = ("gerade" if age_h < 1
                           else f"vor {age_h} Std." if age_h < 24
                           else "gestern")
            items.append({"title": title, "link": link,
                          "pub_dt": pub_dt, "age": age_str})
        items.sort(key=lambda x: x.get("pub_dt") or datetime.min, reverse=True)
    except Exception:
        pass
    return items[:n]


def _format_news_text(items: list[dict]) -> str:
    """Formatiert RSS-News-Liste als Text für die Trade Card."""
    if not items:
        return "Keine aktuellen News in den letzten 48 Stunden."
    lines = []
    for it in items:
        age = f" [{it['age']}]" if it.get("age") else ""
        lines.append(f"→ {it['title']}{age}")
    return "\n".join(lines)


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_stock_data(ticker: str) -> dict:
    info  = fetch_stock_info(ticker)
    fund  = fetch_fundamentals(ticker)
    return {"info": info, "fund": fund}


def _translate_de(text: str) -> str:
    """Übersetzt englischen Text auf Deutsch via Google Translate (kostenlos)."""
    if not text or len(text) < 10:
        return text
    try:
        r = requests.get(
            "https://translate.googleapis.com/translate_a/single",
            params={"client": "gtx", "sl": "en", "tl": "de", "dt": "t", "q": text[:500]},
            timeout=6, headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code == 200:
            data = r.json()
            translated = "".join(
                p[0] for p in data[0] if isinstance(p, list) and p and p[0]
            )
            return translated.strip() or text
    except Exception:
        pass
    return text


def _ta_zeilen(row: pd.Series) -> list[str]:
    """Extrahiert TA-Signale aus dem Scan-Ergebnis als lesbare Zeilen."""
    lines = []

    # SC Trend
    trend = str(row.get("SC Trend(1D)", "")).lower()
    if "↑cross" in trend or "cross" in trend and "bull" in trend:
        lines.append("  • ↑ Kaufsignal (Trend-Cross bullish)")
    elif "↑" in trend or "bull" in trend:
        lines.append("  • ↑ Aufwärtstrend")
    elif "↓cross" in trend or "cross" in trend and "bear" in trend:
        lines.append("  • ↓ Verkaufssignal (Trend-Cross bearish)")
    elif "↓" in trend or "bear" in trend:
        lines.append("  • ↓ Abwärtstrend")

    # MACD
    macd = str(row.get("MACD(1D)", "")).lower()
    if "↑cross" in macd or ("cross" in macd and "bull" in macd):
        lines.append("  • MACD Pro: Bullish Cross ✅")
    elif "↓cross" in macd or ("cross" in macd and "bear" in macd):
        lines.append("  • MACD Pro: Bearish Cross ⚠️")
    elif "bull" in macd:
        lines.append("  • MACD Pro: bullish")
    elif "bear" in macd:
        lines.append("  • MACD Pro: bearish")
    else:
        lines.append("  • MACD Pro: neutral")

    # Stochastik
    stoch_raw = str(row.get("Stoch(1D)", ""))
    try:
        stoch_val = float(re.search(r"\d+", stoch_raw).group())
        if stoch_val < 20:
            lines.append(f"  • Dual Stoch: überverkauft ✅ ({stoch_val:.0f})")
        elif stoch_val > 80:
            lines.append(f"  • Dual Stoch: überkauft ⚠️ ({stoch_val:.0f})")
        else:
            lines.append(f"  • Dual Stoch: neutral ({stoch_val:.0f})")
    except Exception:
        pass

    # RSI
    rsi_raw = str(row.get("RSI(1D)", ""))
    try:
        rsi_val = float(re.search(r"\d+", rsi_raw).group())
        lines.append(f"  • RSI {rsi_val:.0f}")
    except Exception:
        pass

    return lines


def _pct_str(v) -> str:
    """Formatiert Dezimal-Wachstum als %-String: 0.15 → '+15%'."""
    try:
        p = float(v) * 100
        return f"+{_fmt_num(p, 0)}%" if p >= 0 else f"{_fmt_num(p, 0)}%"
    except Exception:
        return "–"


def _strike_dte_reason(
    strike: float, price_now: float, delta: float,
    dte: int, iv: float, otm_pct: float,
) -> str:
    """Erklärt in 2–3 Sätzen warum Strike und Laufzeit so gewählt wurden."""
    abs_d = abs(delta)
    parts = []

    # Strike-Begründung
    if abs_d <= 0.20:
        parts.append(
            f"Strike ${strike:.0f} liegt {_fmt_num(otm_pct, 1)}% unter dem aktuellen Kurs "
            f"(Delta {delta:.2f}) — konservativ, niedriges Einbuchungsrisiko."
        )
    elif abs_d <= 0.35:
        parts.append(
            f"Strike ${strike:.0f} liegt {_fmt_num(otm_pct, 1)}% unter dem aktuellen Kurs "
            f"(Delta {delta:.2f}) — moderate Balance aus attraktiver Prämie und Sicherheitsabstand."
        )
    else:
        parts.append(
            f"Strike ${strike:.0f} liegt {_fmt_num(otm_pct, 1)}% unter dem aktuellen Kurs "
            f"(Delta {delta:.2f}) — aggressiv nahe ATM für maximale Prämie, nur bei starkem Aufwärtstrend sinnvoll."
        )

    # Laufzeit-Begründung
    if dte <= 10:
        parts.append(
            f"Laufzeit {dte} Tage (Wochenoption): täglicher Theta-Abbau am höchsten — "
            "maximale annualisierte Rendite bei kurzer Kapitalbindung."
        )
    elif dte <= 45:
        parts.append(
            f"Laufzeit {dte} Tage (Monatsoption): optimales Theta-Fenster zwischen "
            "Zeitwertrendite und ausreichender Rollingflexibilität."
        )
    else:
        parts.append(
            f"Laufzeit {dte} Tage (Quartalsoption): höhere absolute Prämie durch längere IV-Zeitprämie, "
            "mehr Puffer für Kurskorrekturen."
        )

    # IV-Kontext
    if iv > 40:
        parts.append(f"IV {iv:.0f}% ist überdurchschnittlich hoch — Prämie deutlich über Normalwert.")
    elif iv > 25:
        parts.append(f"IV {iv:.0f}% im normalen Bereich — faire Prämie für das Risiko.")
    elif iv > 0:
        parts.append(f"IV {iv:.0f}% gering — Strike nahe am Kurs gewählt, um ausreichend Prämie zu erzielen.")

    return "\n".join(f"  {p}" for p in parts)


def _crv_reason(
    crv: float, delta: float, iv: float,
    rendite_lz: float, dte: int, otm_pct: float,
) -> str:
    """Kurze Begründung warum diese Option den besten CRV hat."""
    ann = rendite_lz * 365 / max(dte, 1)
    abs_d = abs(delta)
    reasons = [
        f"~{_fmt_num(ann, 1)}% p.a. bei {_fmt_num(otm_pct, 1)}% OTM (Delta {delta:.2f})"
    ]
    if iv > 35:
        reasons.append(f"erhöhte IV ({iv:.0f}%) hebt Prämie überproportional an")
    elif iv > 20:
        reasons.append(f"IV {iv:.0f}% liefert faire Zeitwertprämie")
    if abs_d <= 0.25:
        reasons.append("konservatives Delta verbessert Chance/Risiko-Verhältnis")
    elif abs_d > 0.35:
        reasons.append("höheres Delta liefert aggressive Prämie bei Trendunterstützung")
    return f"  CRV Score {crv:.0f}: " + " · ".join(reasons)


def _covered_call_reco(
    row: pd.Series, price_now: float, dte: int, iv: float,
) -> str:
    """Empfiehlt Covered Call wenn TA auf mehreren TFs bullish ist."""
    if price_now <= 0:
        return ""

    sc        = str(row.get("SC Trend(1D)", "")).lower()
    macd      = str(row.get("MACD(1D)",    "")).lower()
    stoch_raw = str(row.get("Stoch(1D)",   ""))

    bullish = 0
    signals = []
    if "bull" in sc or "↑" in sc:
        bullish += 1
        signals.append("SC Trend ↑")
    if "bull" in macd or "↑cross" in macd:
        bullish += 1
        signals.append("MACD bullish")
    try:
        sv = float(re.search(r"\d+", stoch_raw).group())
        if sv < 60:
            bullish += 1
            signals.append(f"Stoch {sv:.0f} (nicht überkauft)")
    except Exception:
        pass

    if bullish < 2:
        return ""

    # Strike-Vorschläge auf sinnvollen Abstand runden
    step = 5 if price_now >= 100 else 2.5 if price_now >= 30 else 1
    atm_strike = round(price_now / step) * step
    otm_strike = round((price_now * 1.035) / step) * step

    if bullish >= 3:
        empfehlung = (
            f"OTM Call ${otm_strike:.0f} empfohlen bei starkem Aufwärtstrend "
            f"({', '.join(signals)}) — Prämie kassieren + Kursgewinn bis ${otm_strike:.0f} mitnehmen."
        )
    else:
        empfehlung = (
            f"ATM Call ${atm_strike:.0f} empfohlen bei moderatem Aufwärtstrend "
            f"({', '.join(signals)}) — maximale Zeitwertrendite, Kursgewinn begrenzt."
        )

    return "\n".join([
        "",
        "💡 Covered Call Alternative (Aufwärtstrend erkannt):",
        f"  Aktie kaufen bei ~${price_now:.2f}",
        f"  → ATM ${atm_strike:.0f} CALL verkaufen: maximale Prämie "
        f"| Kursgewinn bis ${atm_strike:.0f}",
        f"  → OTM ${otm_strike:.0f} CALL verkaufen: kleinere Prämie "
        f"| Kursgewinn bis ${otm_strike:.0f} (+{(otm_strike/price_now-1)*100:.1f}%)",
        f"  ✅ {empfehlung}",
    ])


def _funda_compact(fund: dict, price_now: float) -> str:
    """Kompakte 2-Zeilen Fundamentalübersicht."""
    f = fund or {}

    def _fv(key, dec=1, prefix="", suffix="", mul=1.0):
        v = f.get(key)
        try:
            return f"{prefix}{_fmt_num(float(v) * mul, dec)}{suffix}"
        except Exception:
            return "–"

    pe_t   = _fv("pe_trailing", 1)
    pe_f   = _fv("pe_forward",  1)
    peg    = f.get("peg_ratio")
    g_yoy  = f.get("earnings_growth_yoy")
    eps_f  = f.get("eps_forward")
    g_next = f.get("eps_growth_next_year")
    target = f.get("target_price")
    rating = f.get("analyst_rating", "")
    n_ana  = f.get("num_analysts", "")

    # Zeile 1: Bewertung
    l1_parts = [f"KGV {pe_t} / Fwd {pe_f}"]
    if peg is not None:
        try:
            pv = float(peg)
            sym = "✅" if pv < 1.0 else "⚠️" if pv > 2.0 else ""
            l1_parts.append(f"PEG {_fmt_num(pv, 2)}{sym}")
        except Exception:
            pass
    if g_yoy is not None:
        l1_parts.append(f"EPS-Wachstum {_pct_str(g_yoy)} (YoY)")
    line1 = "  • " + "  |  ".join(l1_parts)

    # Zeile 2: DCF + Analystenziel
    l2_parts = []
    if eps_f and g_next:
        try:
            dcf = float(eps_f) * (8.5 + 2 * float(g_next) * 100)
            if dcf > 0 and price_now > 0:
                m   = (dcf - price_now) / price_now * 100
                sym = "✅" if m > 0 else "⚠️"
                l2_parts.append(
                    f"DCF ~${dcf:.0f} ({'+' if m >= 0 else ''}{m:.0f}% z. Kurs) {sym}"
                )
        except Exception:
            pass
    if target:
        try:
            t = float(target)
            up = (t - price_now) / price_now * 100 if price_now > 0 else 0
            ana = f"{n_ana} Analysten · " if n_ana else ""
            l2_parts.append(
                f"Ziel ${t:.0f} ({'+' if up >= 0 else ''}{up:.0f}%) — {ana}{rating}"
            )
        except Exception:
            pass
    line2 = ("  • " + "  |  ".join(l2_parts)) if l2_parts else ""

    return "\n".join(x for x in [line1, line2] if x) or "  • Keine Fundamentaldaten verfügbar"


def _build_card_text(
    ticker: str,
    trade_exp: str,
    strike: float,
    option_type: str,
    premium: float,
    rendite_lz: float,
    strategie: str,
    ath_dist: float | None,
    german_exp: str,
    dte: int,
    trend_note: str,
    background: str,
    news_text: str,
    delta: float = 0.0,
    iv: float = 0.0,
    crv: float = 0.0,
    sektor: str = "",
    company_name: str = "",
    ta_lines: list[str] | None = None,
    price_now: float = 0.0,
    fund: dict | None = None,
    covered_call: str = "",
) -> str:
    """Generiert den kompletten WhatsApp-Text einer Trade Card."""

    premium_total = round(premium * 100)
    dte_safe      = max(dte, 1)
    ann_rendite   = rendite_lz * 365 / dte_safe
    otm_pct       = abs((price_now - strike) / price_now * 100) if price_now > 0 else 0
    assign_prob   = round(abs(delta) * 100)
    cash_reserve  = int(strike * 100)

    # Roll-Potenzial: 1σ wöchentliche Bewegung
    roll_usd   = 0.0
    new_strike = strike
    if price_now > 0 and iv > 0:
        roll_usd   = price_now * (iv / 100) * (7 / 365) ** 0.5
        new_strike = strike - roll_usd

    # ── Erklärungsblöcke ────────────────────────────────────────────────────
    ta_block       = "\n".join(ta_lines) if ta_lines else "  • Keine TA-Daten"
    funda_text     = _funda_compact(fund or {}, price_now)
    crv_text       = _crv_reason(crv, delta, iv, rendite_lz, dte, otm_pct)
    strike_dte_txt = _strike_dte_reason(strike, price_now, delta, dte, iv, otm_pct)

    # ── Risikomanagement ────────────────────────────────────────────────────
    risk_lines = []

    # Absicherung
    if trend_note:
        risk_lines.append(f"  • {trend_note}")
    risk_lines.append(
        f"  • Delta {delta:.2f} — Einbuchungsrisiko "
        f"{'konservativ ≤20%' if assign_prob <= 20 else 'moderat 21–35%' if assign_prob <= 35 else 'erhöht >35%'}"
    )
    if iv > 15:
        risk_lines.append("  • Rollbar (IV ausreichend hoch ✅)")
    risk_lines.append(
        f"  • Cash Reserve: USD {cash_reserve:,} pro Kontrakt einplanen".replace(",", ".")
    )
    if roll_usd > 0:
        risk_lines.append(
            f"  • Roll-Potenzial: ±USD {_fmt_num(roll_usd)} / Woche (1σ IV {iv:.0f}%)"
            f" → Strike auf ~${new_strike:.0f} rollbar"
        )

    risk_lines += [
        "",
        f"  Plan A ✅  Take Profit bei {70 if dte < 14 else 50}% Gewinn schließen",
        f"  Plan B 🔄  Strike bedroht → auf nächsten Verfall rollen, Strike ~${new_strike:.0f}",
        f"  Plan C 🆘  Einbuchung akzeptieren → Covered Call ${strike * 1.05:.0f} schreiben",
    ]

    sektor_str  = sektor.upper() if sektor else "–"
    crv_str     = f"{crv:.0f}" if crv else "–"
    company_str = f"🏢 {company_name}" if company_name else ""
    price_str   = f"${price_now:.2f}" if price_now > 0 else "–"

    lines = [
        "Aus Sicht der Technischen Analyse finde ich folgende Optionen spannend:",
        "",
        f"🔔 Trading Idee | {ticker} {trade_exp} @{strike:.0f} {option_type} verkaufen",
        f"💵 Kurs aktuell: {price_str}  ·  Strike ${strike:.0f} ({_fmt_num(otm_pct, 1)}% OTM)",
        "",
        f"💰 Prämie: {_fmt_num(premium)} USD | {premium_total} USD (1 Kontrakt)",
        f"📈 Rendite: ~{_fmt_num(ann_rendite, 1)}% p.a. / {_fmt_num(rendite_lz)}% Laufzeit ({dte}T)",
        f"📉 Strategie: {strategie}",
        f"⚡ Einbuchungsrisiko: ~{assign_prob}% (Delta {delta:.2f})",
        "",
        "💡 Warum diese Option?",
        crv_text,
        "",
        "🎯 Strike & Laufzeit:",
        strike_dte_txt,
        "",
        "📊 Technische Analyse (1D):",
        ta_block,
        "",
        "📐 Fundamentals:",
        funda_text,
        "",
        "🛡️ Risikomanagement:",
        "\n".join(risk_lines),
        covered_call,
        "",
        f"⭐ CRV {crv_str}  ·  IV {iv:.0f}%  ·  Sektor {sektor_str}",
        company_str,
        "",
        f"📰 News {ticker}:",
        news_text,
        "",
        "📋 Hintergrund:",
        background,
    ]
    return "\n".join(x for x in lines if x is not None)


# ══════════════════════════════════════════════════════════════════════════════
# MANUELLER TRADE-EINTRAG — Hilfsfunktionen
# ══════════════════════════════════════════════════════════════════════════════

def _strike_str(s) -> str:
    """Schlichter Strike fürs OptionStrat-Format: 230 → '230', 222.5 → '222.5'."""
    return f"{float(s):g}"


@st.cache_data(ttl=1800, show_spinner=False)
def _snap_contract(ticker: str, expiry, strike: float, option_type: str):
    """Rastet (Verfall, Strike) auf einen echten handelbaren Kontrakt ein."""
    try:
        from data.massive_fetcher import nearest_contract
        return nearest_contract(ticker, expiry, strike, option_type)
    except Exception:
        return None, None


def _optionstrat_url_manual(
    ticker: str, strike: float, expiry, is_call: bool,
    is_strangle: bool = False, call_strike: float = 0.0, call_expiry=None,
) -> str:
    """OptionStrat-URL im echten Format (schlichter Strike, x100 beim CC);
    Verfall + Strike werden auf einen existierenden Kontrakt eingerastet."""
    try:
        t = ticker.upper()
        if is_strangle and call_strike > 0:
            pe, ps = _snap_contract(t, expiry, strike, "put")
            ce, cs = _snap_contract(t, call_expiry if call_expiry else expiry, call_strike, "call")
            if not pe:
                return ""
            pexp = pd.to_datetime(pe).strftime("%y%m%d")
            cexp = pd.to_datetime(ce or pe).strftime("%y%m%d")
            return (
                f"https://optionstrat.com/build/short-strangle/{t}"
                f"/-.{t}{pexp}P{_strike_str(ps)},-.{t}{cexp}C{_strike_str(cs)}"
            )
        if is_call:
            ce, cs = _snap_contract(t, expiry, strike, "call")
            if not ce:
                return ""
            exp = pd.to_datetime(ce).strftime("%y%m%d")
            return (
                f"https://optionstrat.com/build/covered-call/{t}"
                f"/{t}x100,-.{t}{exp}C{_strike_str(cs)}"
            )
        pe, ps = _snap_contract(t, expiry, strike, "put")
        if not pe:
            return ""
        exp = pd.to_datetime(pe).strftime("%y%m%d")
        return f"https://optionstrat.com/build/cash-secured-put/{t}/-.{t}{exp}P{_strike_str(ps)}"
    except Exception:
        return ""


def _load_manual_trades() -> list:
    if not os.path.exists(MANUAL_TRADES_PATH):
        return []
    try:
        with open(MANUAL_TRADES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_manual_trade(trade: dict) -> None:
    trades = _load_manual_trades()
    trades = [t for t in trades if t.get("trade_id") != trade.get("trade_id")]
    trades.append(trade)
    with open(MANUAL_TRADES_PATH, "w", encoding="utf-8") as f:
        json.dump(trades, f, ensure_ascii=False, indent=2)


def _gen_trade_id(ticker: str, strategy: str) -> str:
    date_str = datetime.now().strftime("%Y%m%d")
    strat_short = "CC" if "Call" in strategy else "STR" if "Strangle" in strategy else "CSP"
    uid = re.sub(r"[^A-Z0-9]", "", str(uuid.uuid4()).upper())[:4]
    return f"{ticker}-{date_str}-{strat_short}-{uid}"


@st.cache_data(ttl=300, show_spinner=False)
def _fetch_option_quote(ticker: str, expiry, strike: float, strategy: str,
                        call_strike: float = 0.0, call_expiry=None) -> dict | None:
    """
    Holt Prämie (Mid, sonst Last), Delta und IV für den exakten Kontrakt von Polygon.
    Wählt je Leg das nächstliegende verfügbare Verfallsdatum + Strike.
    Short Strangle: Put-Leg @ strike/expiry + Call-Leg @ call_strike/call_expiry.
      → Gesamtprämie + Gesamt-Delta (Summe beider Legs), IV = Mittel beider Legs.
    Gibt None zurück wenn keine Daten verfügbar.
    """
    try:
        from data.fetcher import _massive_enabled
        if not _massive_enabled():
            return None
        from data.massive_fetcher import get_available_expirations, get_options_chain
    except Exception:
        return None

    exp_dates = []
    for e in get_available_expirations(ticker):
        try:
            exp_dates.append(pd.to_datetime(e).date())
        except Exception:
            pass
    if not exp_dates:
        return None

    def _nearest_exp(target):
        try:
            td = pd.to_datetime(target).date()
        except Exception:
            return None
        return min(exp_dates, key=lambda d: abs((d - td).days)).strftime("%Y-%m-%d")

    def _leg(exp_str: str, opt_type: str, k: float):
        if not exp_str:
            return None
        df = get_options_chain(ticker, exp_str, opt_type)
        if df is None or df.empty:
            return None
        idx = (df["strike"].astype(float) - k).abs().idxmin()
        row = df.loc[idx]
        prem = float(row.get("mid_price") or 0) or float(row.get("lastPrice") or 0)
        return {
            "premium": round(prem, 2),
            "delta":   round(float(row.get("delta") or 0), 2),
            "iv_pct":  round(float(row.get("impliedVolatility") or 0) * 100),
            "strike":  float(row["strike"]),
            "expiry":  exp_str,
        }

    is_call     = "Call" in strategy
    is_strangle = "Strangle" in strategy

    if is_strangle:
        put_leg  = _leg(_nearest_exp(expiry), "put", strike)
        call_leg = _leg(_nearest_exp(call_expiry or expiry), "call", call_strike) if call_strike > 0 else None
        if not put_leg and not call_leg:
            return None
        total_prem  = (put_leg["premium"] if put_leg else 0) + (call_leg["premium"] if call_leg else 0)
        total_delta = (put_leg["delta"]   if put_leg else 0) + (call_leg["delta"]   if call_leg else 0)
        ivs = [l["iv_pct"] for l in (put_leg, call_leg) if l]
        return {
            "premium": round(total_prem, 2),
            "delta":   round(total_delta, 2),
            "iv_pct":  round(sum(ivs) / len(ivs)) if ivs else 0,
            "found_expiry":      put_leg["expiry"]  if put_leg  else "",
            "found_call_expiry": call_leg["expiry"] if call_leg else "",
            "found_strike":      put_leg["strike"]  if put_leg  else 0.0,
            "found_call_strike": call_leg["strike"] if call_leg else 0.0,
        }

    leg = _leg(_nearest_exp(expiry), "call" if is_call else "put", strike)
    if not leg:
        return None
    return {
        "premium": leg["premium"], "delta": leg["delta"], "iv_pct": leg["iv_pct"],
        "found_expiry": leg["expiry"], "found_strike": leg["strike"],
    }


def _fetch_manual_ticker_data(ticker: str) -> dict:
    """Holt Kurs, TA-Signale, Fundamentals und News für manuellen Input."""
    result = {
        "price": 0.0, "company": ticker,
        "trend_str": "", "macd_str": "", "stoch_str": "", "ema_str": "",
        "trend_simple": "", "macd_desc": "", "stoch_desc": "",
        "rsi": None, "support_near": None, "resistance_near": None,
        "fund": {}, "news": [], "description": "",
    }
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        result["price"] = float(
            info.get("currentPrice") or info.get("regularMarketPrice")
            or info.get("previousClose") or 0
        )
        result["company"] = info.get("shortName") or info.get("longName") or ticker
        result["description"] = (info.get("longBusinessSummary") or "").strip()
    except Exception:
        pass
    try:
        from analysis.technicals import analyze_technicals
        hist = fetch_price_history(ticker, period="6mo")
        if hist is not None and not hist.empty:
            tech = analyze_technicals(hist)
            if tech:
                trend_map = {
                    "bullish": "↑ Aufwärtstrend",
                    "bearish": "↓ Abwärtstrend",
                    "neutral": "→ Seitwärts",
                }
                result["trend_str"] = trend_map.get(tech.trend, "")
                # Stillhalter Trend Model (EMA 2/9 "Very Tight" — 1:1 wie Pine-Code).
                # NICHT der generische SMA50/200-Trend aus tech.trend!
                try:
                    from analysis.technicals import calculate_ema as _cema
                    _ef = _cema(hist["Close"], 2)
                    _es = _cema(hist["Close"], 9)
                    _efv = float(_ef.iloc[-1]); _esv = float(_es.iloc[-1])
                    _gap = (_efv - _esv) / _esv * 100 if _esv else 0.0
                    if _gap > 0.1:
                        result["trend_simple"] = "Aufwärtstrend"
                    elif _gap < -0.1:
                        result["trend_simple"] = "Abwärtstrend"
                    else:
                        result["trend_simple"] = "Seitwärtstrend"
                except Exception:
                    result["trend_simple"] = {
                        "bullish": "Aufwärtstrend", "bearish": "Abwärtstrend",
                        "neutral": "Seitwärtstrend",
                    }.get(tech.trend, "Seitwärtstrend")
                if tech.above_sma50 and tech.above_sma200:
                    result["ema_str"] = "MA50 > MA200 (bullisch)"
                elif tech.above_sma50:
                    result["ema_str"] = "Über MA50, unter MA200"
                elif tech.above_sma200:
                    result["ema_str"] = "Unter MA50, über MA200"
                else:
                    result["ema_str"] = "Unter MA50 & MA200 (bärisch)"
                if tech.sc_macd:
                    macd_map = {
                        "strong_bull": "MACD Pro: STARK bullisch ⬆⬆",
                        "bull":        "MACD Pro: bullisch ⬆",
                        "neutral":     "MACD Pro: neutral",
                        "bear":        "MACD Pro: bearisch ⬇",
                        "strong_bear": "MACD Pro: STARK bearisch ⬇⬇",
                    }
                    result["macd_str"] = macd_map.get(tech.sc_macd.signal_strength, "")
                    # Detaillierte Histogramm-Beschreibung: Farbe + Richtung + verdeckte Stärke/Schwäche
                    _h = tech.sc_macd.hist
                    if _h is not None and len(_h) >= 2:
                        _h_now  = float(_h.iloc[-1])
                        _h_prev = float(_h.iloc[-2])
                        _inc = _h_now > _h_prev
                        if _h_now >= 0:
                            if _inc:
                                result["macd_desc"] = "grünes Histogramm, zunehmend → verdeckte Stärke"
                            else:
                                result["macd_desc"] = "grünes Histogramm, abnehmend → verdeckte Schwäche"
                        else:
                            if _inc:
                                result["macd_desc"] = "rotes Histogramm, erholend → noch Schwäche"
                            else:
                                result["macd_desc"] = "rotes Histogramm, abnehmend → verdeckte Schwäche"
                if tech.dual_stoch:
                    stoch_map = {
                        "strong_buy":  "Dual Stoch: stark überverkauft ✅✅",
                        "buy":         "Dual Stoch: überverkauft ✅",
                        "neutral":     "",
                        "sell":        "Dual Stoch: überkauft ⚠️",
                        "strong_sell": "Dual Stoch: stark überkauft ❌",
                    }
                    result["stoch_str"] = stoch_map.get(tech.dual_stoch.signal_strength, "")
                    # Schnelle + langsame Stochastik einzeln (überverkauft / neutral / überkauft)
                    def _stoch_stat(k: float) -> str:
                        if k < 20:  return "überverkauft"
                        if k > 80:  return "überkauft"
                        return "neutral"
                    _ds = tech.dual_stoch
                    result["stoch_desc"] = (
                        f"schnelle {_stoch_stat(_ds.fast_k)}, langsame {_stoch_stat(_ds.slow_k)}"
                    )
                if tech.support_levels:
                    below = [s for s in tech.support_levels if s < result["price"]]
                    if below:
                        result["support_near"] = max(below)
                if tech.resistance_levels:
                    above = [r for r in tech.resistance_levels if r > result["price"]]
                    if above:
                        result["resistance_near"] = min(above)
                close = hist["Close"]
                dc = close.diff()
                g = dc.clip(lower=0)
                lo = (-dc).clip(lower=0)
                ag = g.ewm(alpha=1 / 14, adjust=False).mean()
                al = lo.ewm(alpha=1 / 14, adjust=False).mean()
                rs = ag / al.replace(0, 1e-10)
                result["rsi"] = float((100 - (100 / (1 + rs))).iloc[-1])
    except Exception:
        pass
    try:
        result["fund"] = fetch_fundamentals(ticker) or {}
    except Exception:
        pass
    try:
        result["news"] = _fetch_ticker_news_rss(ticker, n=3)
    except Exception:
        pass
    return result


@st.cache_data(ttl=1800, show_spinner=False)
def _tf_color_dots(ticker: str) -> dict:
    """Farbpunkte (🟢/🟡/🔴) je Indikator und Zeitebene (4h, 1d) via Multi-Timeframe.
    Trend/MACD: bull🟢/bear🔴 · Stochastik (schnell/langsam): überverkauft🟢/überkauft🔴/neutral🟡."""
    out = {"trend":      {"4h": "⚪", "1d": "⚪"},
           "macd":       {"4h": "⚪", "1d": "⚪"},
           "stoch_fast": {"4h": "⚪", "1d": "⚪"},
           "stoch_slow": {"4h": "⚪", "1d": "⚪"}}
    try:
        from analysis.multi_timeframe import analyze_multi_timeframe
        m = analyze_multi_timeframe(ticker)
        for key, sig in (("4h", m.tf_4h), ("1d", m.tf_1d)):
            if not sig:
                continue
            out["trend"][key] = "🟢" if getattr(sig, "ema_bullish", False) else "🔴"
            out["macd"][key]  = "🟢" if getattr(sig, "macd_bullish", False) else "🔴"
            _fo = getattr(sig, "stoch_oversold", False)
            _fob = getattr(sig, "stoch_overbought", False)
            out["stoch_fast"][key] = "🟢" if _fo else ("🔴" if _fob else "🟡")
            _so = getattr(sig, "stoch_slow_oversold", False)
            _sob = getattr(sig, "stoch_slow_overbought", False)
            out["stoch_slow"][key] = "🟢" if _so else ("🔴" if _sob else "🟡")
    except Exception:
        pass
    return out


def _build_tracking_url(app_url: str, trade_id: str) -> str:
    """Kurze Tracking-URL — nur die Trade-ID. Der Trade Monitor lädt den
    vollständigen Trade aus dem persistenten Speicher (Volume) und hebt ihn hervor."""
    from urllib.parse import quote
    return f"{app_url}/20_Trade_Monitor?trade_id={quote(trade_id)}"


def _build_whatsapp_short_manual(
    class_label: str, ticker: str, company: str, strategy: str,
    strike: float, german_exp: str, expiry_short: str, dte: int,
    premium: float, delta: float, iv_pct: float, price_now: float,
    trend_simple: str, macd_desc: str, stoch_desc: str,
    optionstrat_url: str, tracking_url: str, post_ts: str,
    support_near=None, ath_price_dist=None,
    company_sentence: str = "", news_line: str = "",
    funda: dict | None = None,
    tf_colors: dict | None = None,
) -> str:
    is_call = "Call" in strategy
    otm_pct = abs((price_now - strike) / price_now * 100) if price_now > 0 else 0
    praemie_usd = round(premium * 100)
    assign_pct = round(abs(delta) * 100)
    capital_basis = price_now if is_call and price_now > 0 else (strike if strike > 0 else 1)
    rend_lz  = premium / capital_basis * 100
    rend_ann = rend_lz * 365 / max(dte, 1)
    _risk_label = "Ausübungsrisiko" if is_call else "Einbuchungsrisiko"
    tf = tf_colors or {}
    fd = funda or {}

    def _dots(key: str) -> str:
        c = tf.get(key, {})
        return f"4h {c.get('4h', '⚪')} · 1T {c.get('1d', '⚪')}"

    L = []
    # ── Kopf (fett) + Stand ───────────────────────────────────────────────────
    L.append(
        f"*🔔 Trading-Idee: {strategy}  {ticker}  {expiry_short}  "
        f"{strike:g} USD @ {_fmt_num(premium)} USD*"
    )
    L.append(f"🕐 Stand: Stillhalter AI | {post_ts}")
    L.append("")
    # ── Option ────────────────────────────────────────────────────────────────
    L.append("*Option*")
    L.append(f"🏢 Aktie: {company} ({ticker})")
    L.append(f"💵 Kurs: ${price_now:.2f}")
    L.append(f"🎯 Strike: ${strike:g}")
    L.append(f"📅 Verfall: {german_exp} ({dte} Tage)")
    if is_call and price_now > 0:
        L.append(f"🛒 Aktienkauf: 100 × ${price_now:.2f} = ${price_now * 100:,.0f} USD")
    _is_strangle = "Strangle" in strategy
    _prem_note = " (Put + Call zusammen)" if _is_strangle else ""
    L.append(f"💰 Prämie: {_fmt_num(premium)} USD ({praemie_usd} USD gesamt){_prem_note}")
    L.append(f"📈 Rendite (Prämie): {_fmt_num(rend_lz)}% für {dte} Tage (~{_fmt_num(rend_ann, 1)}% p.a.)")
    if is_call and price_now > 0 and strike > price_now:
        # Covered Call: zusätzlich die Kurschance bis zum Strike
        _upside = (strike - price_now) / price_now * 100
        _max_ret = (premium + (strike - price_now)) / price_now * 100
        _max_ann = _max_ret * 365 / max(dte, 1)
        L.append(f"🚀 Upside bis Strike: {_fmt_num(_upside)}%")
        L.append(f"🎯 Max-Rendite bei Ausübung: {_fmt_num(_max_ret)}% (~{_fmt_num(_max_ann, 1)}% p.a.)")
    elif (not is_call) and (not _is_strangle) and strike > 0 and price_now > 0:
        # Short PUT: Rabatt — effektiver Einbuchungspreis (Strike − Prämie) vs. Kurs
        _eff = strike - premium
        _disc = (price_now - _eff) / price_now * 100
        L.append(f"🏷️ Rabatt bei Einbuchung: {_fmt_num(_disc)}% (effektiv ${_eff:g} statt ${price_now:.2f})")
    L.append("")
    # ── Absicherung ───────────────────────────────────────────────────────────
    L.append("*Absicherung*")
    L.append(f"📐 OTM: {_fmt_num(otm_pct, 1)}%")
    if support_near and strike > 0:
        if support_near >= strike:
            _sd = (support_near - strike) / strike * 100
            L.append(f"🛟 Support: ${support_near:.2f} ({_fmt_num(_sd, 1)}% über Strike)")
        else:
            _sd = (strike - support_near) / strike * 100
            L.append(f"🛟 Support: ${support_near:.2f} ({_fmt_num(_sd, 1)}% unter Strike)")
    if ath_price_dist is not None:
        L.append(f"⛰️ ATH: -{_fmt_num(ath_price_dist, 1)}%")
    L.append(f"⚠️ Risiko: ~{assign_pct}% (Delta {delta:.2f})")
    L.append("")
    # ── Fundamentalanalyse (aktuelles Jahr · nächstes Jahr/Forward) ───────────
    def _fv(v, suf=""):
        return f"{_fmt_num(v, 1)}{suf}" if v is not None else "–"
    L.append("*Fundamentalanalyse*")
    L.append(f"🌱 EPS: {_fv(fd.get('eps_cur'), '%')} (akt. Jahr) · "
             f"EPS(e): {_fv(fd.get('eps_fwd'), '%')} (nächstes Jahr)")
    L.append(f"💰 KGV: {_fv(fd.get('kgv'))} (akt.) · KGV(e): {_fv(fd.get('kgv_e'))} (forward)")
    L.append(f"⚖️ PEG: {_fv(fd.get('peg'))} (akt.) · PEG(e): {_fv(fd.get('peg_e'))} (forward)")
    L.append("")
    # ── Chart (nur 4h/1T-Farbpunkte) ──────────────────────────────────────────
    L.append("*Chart*")
    L.append(f"📈 Trend: {_dots('trend')}")
    L.append(f"〰️ MACD: {_dots('macd')}")
    L.append(f"⚡ Stochastik (schnell): {_dots('stoch_fast')}")
    L.append(f"🐌 Stochastik (langsam): {_dots('stoch_slow')}")
    L.append("")
    # ── Visualisierung + Live-Tracking ────────────────────────────────────────
    L.append("*Visualisierung*")
    L.append(f"📊 {optionstrat_url}")
    L.append("")
    L.append("*Live-Tracking*")
    L.append(f"📡 {tracking_url}")
    L.append("")
    L.append("⚠️ Keine Finanzberatung, nur reine Finanzbildung und meine eigenen Trades! "
             "Handeln auf eigenes Risiko!")
    return "\n".join(L)


def _build_whatsapp_compact(
    class_label: str, ticker: str, strategy: str, expiry_short: str,
    strike: float, premium: float, post_ts: str, optionstrat_url: str,
) -> str:
    """Kurzversion: Kopf mit IV-Farbpunkt (🟢 Low / 🟡 Mid / 🔴 High) + OptionStrat-Link."""
    dot = {"A": "🟢", "B": "🟡", "C": "🔴"}.get(class_label, "⚪")
    return (
        f"*🔔 Trading-Ideen:\n"
        f"{dot} {strategy}  {ticker}  {expiry_short}  "
        f"{strike:g} USD @ {_fmt_num(premium)} USD* "
        f"(Stillhalter AI | {post_ts})\n"
        f"{optionstrat_url}"
    )


def _sec(key: str, default: str = "") -> str:
    """Liest einen Wert aus Streamlit-Secrets oder Umgebungsvariablen."""
    try:
        return str(st.secrets.get(key, os.environ.get(key, default)))
    except Exception:
        return os.environ.get(key, default)


def _text_to_html(text: str) -> str:
    """Wandelt einen WhatsApp-Textpost in HTML für Circle: *fett* → <strong>,
    Zeilenumbrüche → <br>, URLs → klickbare Links."""
    import html as _h, re as _re
    out = []
    for line in text.split("\n"):
        esc = _h.escape(line)
        esc = _re.sub(r"\*(.+?)\*", r"<strong>\1</strong>", esc)
        esc = _re.sub(r"(https?://[^\s]+)", r'<a href="\1">\1</a>', esc)
        out.append(esc)
    return "<br>\n".join(out)


def _to_circle_text(text: str) -> str:
    """Wandelt einen WhatsApp-Post in Circle-taugliches Format zum Einfügen:
    *fett* (WhatsApp) → **fett** (Markdown — Circles Editor wandelt das beim
    Einfügen/Tippen in echtes Fett um). Rest bleibt unverändert."""
    import re as _re
    return _re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"**\1**", text)


def _build_combined_short(gen: dict, circle_url: str, post_ts: str) -> str:
    """WhatsApp-Sammel-Kurzpost: alle Trades kompakt + EIN Circle-Link zur Langversion.
    post_ts = aktueller Zeitstempel (Berlin) im Kopf."""
    dots   = {"A": "🟢", "B": "🟡", "C": "🔴"}
    iv_lbl = {"A": "Low IV", "B": "Mid IV", "C": "High IV"}
    L = [f"*🔔 Trading-Ideen — Stillhalter AI | {post_ts}*", ""]
    for cls, d in gen.items():
        L.append(
            f"{dots.get(cls, '⚪')} {iv_lbl.get(cls, '')}: {d['strategy']}  {d['ticker']}  "
            f"{d['expiry_short']}  {d['strike']:g} USD @ {_fmt_num(d['premium'])} USD"
        )
        L.append(f"📊 {d['optionstrat_url']}")
        L.append("")
    if circle_url:
        L.append("📋 Volle Analyse für alle Trades (nur Masterclass):")
        L.append(f"🌐 {circle_url}")
        L.append("")
    L.append("⚠️ Keine Finanzberatung, nur reine Finanzbildung und meine eigenen Trades! "
             "Handeln auf eigenes Risiko!")
    return "\n".join(L)


def _next_friday(min_days: int = 1) -> date:
    """Nächster Freitag ab heute (Optionen verfallen freitags)."""
    d = date.today()
    ahead = (4 - d.weekday()) % 7   # Freitag = 4
    if ahead < min_days:
        ahead += 7
    return d + timedelta(days=ahead)


# ── Sprach-/Text-Parser: "Apple Short Put 285 nächster Freitag" → Formularfelder ──
_TICKER_ALIASES = {
    "apple": "AAPL", "tesla": "TSLA", "amazon": "AMZN", "microsoft": "MSFT",
    "google": "GOOG", "alphabet": "GOOG", "nvidia": "NVDA", "meta": "META",
    "facebook": "META", "netflix": "NFLX", "amd": "AMD", "intel": "INTC",
    "palantir": "PLTR", "coinbase": "COIN", "qualcomm": "QCOM", "broadcom": "AVGO",
    "disney": "DIS", "boeing": "BA", "visa": "V", "mastercard": "MA",
    "paypal": "PYPL", "walmart": "WMT", "coca cola": "KO", "coca-cola": "KO",
    "pfizer": "PFE", "exxon": "XOM", "chevron": "CVX", "honeywell": "HON",
    "caterpillar": "CAT", "starbucks": "SBUX", "nike": "NKE", "alibaba": "BABA",
    "uber": "UBER", "shopify": "SHOP", "salesforce": "CRM", "oracle": "ORCL",
    "adobe": "ADBE", "micron": "MU", "robinhood": "HOOD", "reddit": "RDDT",
}


def _third_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    offset = (4 - d.weekday()) % 7
    return d + timedelta(days=offset + 14)   # 3. Freitag (Monatsverfall)


def _parse_expiry_text(low: str) -> date:
    import re
    _MONTHS = {"januar":1,"jan":1,"februar":2,"feb":2,"märz":3,"maerz":3,"mar":3,"april":4,"apr":4,
               "mai":5,"juni":6,"jun":6,"juli":7,"jul":7,"august":8,"aug":8,"september":9,"sep":9,
               "oktober":10,"okt":10,"november":11,"nov":11,"dezember":12,"dez":12}
    # explizites Datum TT.MM(.JJJJ)
    m = re.search(r"\b(\d{1,2})\.(\d{1,2})\.?(\d{2,4})?", low)
    if m:
        dd, mm = int(m.group(1)), int(m.group(2))
        yy = m.group(3)
        year = (2000 + int(yy)) if (yy and len(yy) == 2) else (int(yy) if yy else date.today().year)
        try:
            cand = date(year, mm, dd)
            if cand < date.today():
                cand = date(year + 1, mm, dd)
            return cand
        except Exception:
            pass
    # "in X tagen"
    m = re.search(r"in\s+(\d{1,3})\s*tag", low)
    if m:
        return date.today() + timedelta(days=int(m.group(1)))
    # Monatsname → 3. Freitag (Monatsverfall)
    for name, mm in _MONTHS.items():
        if re.search(rf"\b{name}\b", low):
            y = date.today().year
            tf = _third_friday(y, mm)
            if tf < date.today():
                tf = _third_friday(y + 1, mm)
            return tf
    # Default: nächster Freitag (auch bei "freitag"/"next friday")
    return _next_friday()


def _parse_trade_segment(seg: str, all_tickers: set) -> dict | None:
    import re
    s = seg.strip()
    low = s.lower()
    if not low:
        return None
    # Strategie
    if "strangle" in low:
        strat = "Short Strangle"
    elif "covered call" in low or ("call" in low and "put" not in low):
        strat = "Covered Call"
    else:
        strat = "Short PUT"
    # Ticker: 1) Symbol das in der Watchlist ist  2) Firmenname-Alias
    ticker = ""
    for tok in re.findall(r"\b[A-Za-z]{1,5}\b", s):
        if tok.upper() in all_tickers:
            ticker = tok.upper()
            break
    if not ticker:
        for name, tk in _TICKER_ALIASES.items():
            if name in low:
                ticker = tk
                break
    # Zahlen + Kontext: Strike / Prämie
    strike = 0.0
    m = re.search(r"strike\s*\$?\s*(\d+(?:[.,]\d+)?)", low)
    if m:
        strike = float(m.group(1).replace(",", "."))
    premium = 0.0
    m = re.search(r"(?:prämie|praemie|premium|@|für|fuer)\s*\$?\s*(\d+(?:[.,]\d+)?)", low)
    if m:
        premium = float(m.group(1).replace(",", "."))
    # Falls kein expliziter Strike: größte „strike-artige" Zahl (>10), die nicht die Prämie ist
    if strike <= 0:
        cands = [float(x.replace(",", ".")) for x in re.findall(r"\b(\d+(?:[.,]\d+)?)\b", low)]
        cands = [c for c in cands if c > 10 and c != premium]
        if cands:
            strike = max(cands)
    expiry = _parse_expiry_text(low)
    if not ticker and strike <= 0:
        return None
    return {"ticker": ticker, "strategy": strat, "strike": strike,
            "premium": premium, "expiry": expiry}


def _parse_trade_text(text: str) -> list:
    """Zerlegt diktierten/eingegebenen Text in bis zu 3 Trades (A/B/C)."""
    import re
    try:
        from data.watchlist import ALL_TICKERS
        all_t = {t.upper() for t in ALL_TICKERS}
    except Exception:
        all_t = set()
    # Trenner: Zeilenumbruch, ' und ', ';'
    segments = re.split(r"\n|;|\bund\b", text)
    out = []
    for seg in segments:
        parsed = _parse_trade_segment(seg, all_t)
        if parsed:
            out.append(parsed)
        if len(out) >= 3:
            break
    return out


def _voice_fill_cb():
    """Füllt das Class-A/B/C-Formular aus dem diktierten Text (on_click)."""
    text = st.session_state.get("m_voice_text", "")
    trades = _parse_trade_text(text)
    if not trades:
        st.session_state["m_voice_msg"] = "⚠️ Konnte keinen Trade erkennen — bitte Ticker + Strike nennen."
        return
    for i, tr in enumerate(trades):
        cls = ["A", "B", "C"][i]
        st.session_state[f"m_{cls}_ticker"]   = tr["ticker"]
        st.session_state[f"m_{cls}_strategy"] = tr["strategy"]
        st.session_state[f"m_{cls}_strike"]   = float(tr["strike"])
        st.session_state[f"m_{cls}_expiry"]   = tr["expiry"]
        if tr["premium"] > 0:
            st.session_state[f"m_{cls}_premium"] = float(tr["premium"])
    _names = ", ".join(f"{['A','B','C'][i]}: {t['ticker']} {t['strategy']} {t['strike']:g}"
                       for i, t in enumerate(trades))
    st.session_state["m_voice_msg"] = f"✓ {len(trades)} Trade(s) erkannt → {_names}"


def _autofill_cb(cls, ticker, strike, strat, call_strike, call_expiry, expiry):
    """on_click-Callback für 'Optionsdaten holen'. Läuft VOR dem Rerun, damit
    nicht mitten im Skript st.rerun() aufgerufen wird (sonst verlieren noch
    nicht gerenderte Spalten ihren Widget-Zustand)."""
    if not (ticker and strike > 0):
        st.session_state[f"m_{cls}_fill_msg"] = "⚠️ Erst Ticker + Strike eingeben"
        return
    q = _fetch_option_quote(ticker, expiry, strike, strat, call_strike, call_expiry)
    if not q:
        st.session_state[f"m_{cls}_fill_msg"] = "⚠️ Keine Optionsdaten gefunden"
        return
    st.session_state[f"m_{cls}_premium"] = float(q["premium"])
    st.session_state[f"m_{cls}_delta"]   = float(q["delta"])
    st.session_state[f"m_{cls}_iv"]      = float(q["iv_pct"])
    if "Strangle" in strat:
        st.session_state[f"m_{cls}_fill_msg"] = (
            f"✓ PUT ${q['found_strike']:.0f} / CALL ${q.get('found_call_strike', 0):.0f} "
            f"· Σ-Prämie {q['premium']:.2f}$ · Σ-Delta {q['delta']:.2f}"
        )
    else:
        st.session_state[f"m_{cls}_fill_msg"] = (
            f"✓ Strike ${q['found_strike']:.0f} · Verfall {q['found_expiry']}"
        )


def _build_circle_suffix(
    optionstrat_url: str, tracking_url: str, post_ts: str, class_label: str,
) -> str:
    class_header = {
        "A": "🟢 CLASS A — Konservativ (Low IV)",
        "B": "🟡 CLASS B — Ausgewogen (Mid IV)",
        "C": "🔴 CLASS C — Aggressiv (High IV)",
    }.get(class_label, f"Class {class_label}")
    return (
        f"\n\n{'─' * 32}\n"
        f"🔗 Links & Tracking\n\n"
        f"  📡 Live-Tracking (bis Verfall):\n"
        f"     {tracking_url}\n\n"
        f"  📊 OptionStrat-Analyse:\n"
        f"     {optionstrat_url}\n\n"
        f"  ⏱️ Post erstellt: {post_ts}\n"
        f"  {class_header}"
    )


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════

h1, h2 = st.columns([1, 6])
with h1:
    st.markdown(get_logo_html("auto", 36), unsafe_allow_html=True)
with h2:
    st.markdown(
        '<div class="sc-page-title">📤 Trade Cards</div>'
        '<div class="sc-page-subtitle">'
        'Option eingeben → WhatsApp + Circle Post · Live-Tracking bis Verfall</div>',
        unsafe_allow_html=True,
    )
st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# Live-Tracking-Link zeigt auf die Railway-App (dort liegt Seite 20_Trade_Monitor).
# Reihenfolge: APP_URL-Secret > Railway-Standard-URL.
_DEFAULT_APP_URL = "https://stillhalter-ai.up.railway.app"
_APP_URL = ""
try:
    _APP_URL = (st.secrets.get("APP_URL", "") or "").strip()
except Exception:
    pass
if not _APP_URL:
    _APP_URL = _DEFAULT_APP_URL

tab1, tab2 = st.tabs(["✏️ Manuell eingeben", "📊 Aus Scanner"])

# ════════════════════════════════════════════════════════════════════════════════
# TAB 1 — MANUELL EINGEBEN
# ════════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown("Trage **Class A** (Konservativ), **Class B** (Ausgewogen) und/oder **Class C** (Aggressiv) ein — mindestens eine Klasse:")

    # ── Sprach-/Text-Eingabe (z.B. via Wispr Flow diktieren) ──────────────────
    with st.expander("🎤 Per Sprache/Text befüllen (diktieren)", expanded=False):
        st.caption("Diktiere (z.B. mit Wispr Flow) oder tippe — ein Trade pro Zeile "
                   "oder mit 'und' getrennt. Beispiel: "
                   "Apple Short Put 285 nächster Freitag und Tesla Covered Call 460 Juli")
        st.text_area("Trade(s) beschreiben", key="m_voice_text", height=90,
                     placeholder="Apple Short Put Strike 285 nächster Freitag, Prämie 2\n"
                                 "Tesla Covered Call 460 Juli")
        st.button("📝 Formular füllen", key="m_voice_fill", on_click=_voice_fill_cb)
        _vmsg = st.session_state.get("m_voice_msg", "")
        if _vmsg:
            _vc = "#22c55e" if _vmsg.startswith("✓") else "#f59e0b"
            st.html(f"<div style='font-size:0.78rem;color:{_vc}'>{_vmsg}</div>")
        st.caption("Danach pro Klasse 'Optionsdaten holen' klicken → echte Prämie/Delta/IV.")

    col_a, col_b, col_c = st.columns(3, gap="small")
    _CLASS_DEFS = [
        ("A", "🟢 Class A — Konservativ", "#22c55e", col_a),
        ("B", "🟡 Class B — Ausgewogen",  "#d4a843", col_b),
        ("C", "🔴 Class C — Aggressiv",   "#ef4444", col_c),
    ]

    # Defaults für Prämie/Delta/IV (damit Auto-Fill sie via Session State setzen kann)
    for _c in ["A", "B", "C"]:
        st.session_state.setdefault(f"m_{_c}_premium", 0.0)
        st.session_state.setdefault(f"m_{_c}_delta", -0.20)
        st.session_state.setdefault(f"m_{_c}_iv", 25.0)

    m_inputs: dict = {}
    for cls, cls_label, cls_color, col in _CLASS_DEFS:
        with col:
            st.html(
                f"<div style='font-weight:700;color:{cls_color};font-family:RedRose,sans-serif;"
                f"font-size:0.9rem;margin-bottom:6px'>{cls_label}</div>"
            )
            ticker_v  = st.text_input("Ticker", key=f"m_{cls}_ticker", placeholder="AAPL").upper().strip()
            strat_v   = st.selectbox(
                "Strategie", ["Short PUT", "Covered Call", "Short Strangle"],
                key=f"m_{cls}_strategy",
            )
            is_strangle_v = "Strangle" in strat_v
            call_strike_v = 0.0
            call_expiry_v = None
            if is_strangle_v:
                # Short Strangle: PUT + CALL je mit eigenem Strike UND Verfall (4 Felder)
                _sk1, _sk2 = st.columns(2)
                with _sk1:
                    strike_v = st.number_input(
                        "PUT Strike ($)", min_value=0.0, step=1.0, format="%.2f",
                        key=f"m_{cls}_strike",
                    )
                with _sk2:
                    call_strike_v = st.number_input(
                        "CALL Strike ($)", min_value=0.0, step=1.0, format="%.2f",
                        key=f"m_{cls}_call_strike",
                    )
                _ex1, _ex2 = st.columns(2)
                with _ex1:
                    expiry_v = st.date_input(
                        "PUT Verfall", value=_next_friday(),
                        min_value=date.today(), key=f"m_{cls}_expiry",
                    )
                with _ex2:
                    call_expiry_v = st.date_input(
                        "CALL Verfall", value=_next_friday(),
                        min_value=date.today(), key=f"m_{cls}_call_expiry",
                    )
            else:
                strike_v = st.number_input(
                    "Strike ($)", min_value=0.0, step=1.0, format="%.2f", key=f"m_{cls}_strike",
                )
                expiry_v = st.date_input(
                    "Verfall", value=_next_friday(),
                    min_value=date.today(), key=f"m_{cls}_expiry",
                )

            # ── Auto-Fill aus Massive/Polygon (on_click → kein Daten­verlust) ──
            st.button(
                "🔍 Optionsdaten holen", key=f"m_{cls}_autofill",
                use_container_width=True,
                help="Holt Prämie, Delta & IV automatisch von Massive/Polygon",
                on_click=_autofill_cb,
                args=(cls, ticker_v, strike_v, strat_v, call_strike_v, call_expiry_v, expiry_v),
            )
            _fill_msg = st.session_state.get(f"m_{cls}_fill_msg", "")
            if _fill_msg:
                _msg_color = "#22c55e" if _fill_msg.startswith("✓") else "#f59e0b"
                st.html(f"<div style='font-size:0.7rem;color:{_msg_color};margin:-4px 0 4px'>{_fill_msg}</div>")

            _prem_label  = "Gesamtprämie (USD)" if is_strangle_v else "Prämie (USD)"
            _delta_label = "Gesamt-Delta" if is_strangle_v else "Delta"
            premium_v = st.number_input(
                _prem_label, min_value=0.0, step=0.05, format="%.2f", key=f"m_{cls}_premium",
            )
            dc, dv = st.columns(2)
            with dc:
                delta_v = st.number_input(
                    _delta_label, min_value=-2.0, max_value=2.0,
                    step=0.01, format="%.2f", key=f"m_{cls}_delta",
                )
            with dv:
                iv_v = st.number_input(
                    "IV %", min_value=0.0, step=1.0, format="%.0f",
                    key=f"m_{cls}_iv",
                )
            # ── Live-Rendite auf Laufzeit (Vorschau) ──────────────────────────
            if strike_v > 0 and premium_v > 0:
                _dte_p = max(1, (expiry_v - date.today()).days)
                _rl_p  = premium_v / strike_v * 100
                _ra_p  = _rl_p * 365 / _dte_p
                st.html(
                    f"<div style='font-size:0.74rem;color:#22c55e;font-weight:600;margin:-2px 0 4px'>"
                    f"📈 Rendite: {_fmt_num(_rl_p)}% auf {_dte_p}T "
                    f"<span style='color:#888;font-weight:400'>(~{_fmt_num(_ra_p, 0)}% p.a.)</span></div>"
                )
            m_inputs[cls] = {
                "ticker": ticker_v, "strategy": strat_v, "strike": strike_v,
                "expiry": expiry_v, "call_strike": call_strike_v,
                "call_expiry": call_expiry_v,
                "premium": premium_v, "delta": delta_v, "iv_pct": iv_v,
            }

    st.markdown("---")
    _eff_app_url = st.text_input(
        "🔗 App-URL (für Live-Tracking Link)",
        value=_APP_URL,
        key="m_app_url",
        help="Base-URL der Stillhalter AI App — der Tracking-Link öffnet dort Seite "
             "20_Trade_Monitor. Standard: Railway-App. Später ggf. eigene Domain eintragen.",
    ).strip().rstrip("/") or _APP_URL

    st.markdown("---")

    # Steuerung: ob generierte Trades in den Trade Monitor (Live-Tracking) wandern.
    st.checkbox(
        "📡 In Trade Monitor übernehmen (live verfolgen)",
        value=True, key="m_into_monitor",
        help="Wenn aktiv, werden die generierten Trades zum Live-Tracking in den "
             "Trade Monitor übernommen. Zum reinen Posten ohne Tracking abwählen.",
    )

    if st.button("🚀 Posts generieren", type="primary",
                 use_container_width=True, key="btn_gen_manual"):
        _active_classes = [
            cls for cls in ["A", "B", "C"]
            if m_inputs[cls]["ticker"] and m_inputs[cls]["strike"] > 0 and m_inputs[cls]["premium"] > 0
        ]
        # Angefangene, aber unvollständige Klassen sammeln (für klaren Hinweis)
        _skipped = []
        for _c in ["A", "B", "C"]:
            if _c in _active_classes:
                continue
            _inp = m_inputs[_c]
            if _inp["ticker"] or _inp["strike"] > 0 or _inp["premium"] > 0:
                _miss = [n for n, ok in [
                    ("Ticker", bool(_inp["ticker"])),
                    ("Strike", _inp["strike"] > 0),
                    ("Prämie", _inp["premium"] > 0),
                ] if not ok]
                _skipped.append(f"Class {_c} (fehlt: {', '.join(_miss)})")
        if not _active_classes:
            st.error("⚠️ Mindestens eine Klasse (Ticker + Strike + Prämie) muss ausgefüllt sein.")
        else:
            _generated: dict = {}
            for cls in _active_classes:
                inp = m_inputs[cls]
                with st.spinner(f"⏳ Marktdaten für {inp['ticker']} (Class {cls})…"):
                    tdata = _fetch_manual_ticker_data(inp["ticker"])

                ticker   = inp["ticker"]
                strategy = inp["strategy"]
                strike   = inp["strike"]
                expiry   = inp["expiry"]
                premium  = inp["premium"]
                delta    = inp["delta"]
                iv_pct   = inp["iv_pct"]
                is_call     = "Call" in strategy
                is_strangle = "Strangle" in strategy
                call_strike = inp.get("call_strike", 0.0)
                call_expiry = inp.get("call_expiry") or expiry
                price_now   = tdata.get("price", 0.0)
                company     = tdata.get("company", ticker)

                # Auf echten Kontrakt einrasten (Verfall + Strike), damit Card,
                # OptionStrat-Link und Tracking konsistent sind. Existiert der
                # gewählte Verfall/Strike nicht, wird der nächste genommen.
                try:
                    from data.massive_fetcher import nearest_contract
                    _ne, _ns = nearest_contract(ticker, expiry, strike, "call" if is_call else "put")
                    if _ne and _ns:
                        expiry, strike = _ne, _ns
                    if is_strangle and call_strike > 0:
                        _nce, _ncs = nearest_contract(ticker, call_expiry, call_strike, "call")
                        if _nce and _ncs:
                            call_expiry, call_strike = _nce, _ncs
                except Exception:
                    pass

                try:
                    d_exp = pd.to_datetime(expiry)
                    expiry_display = d_exp.strftime("%b") + str(d_exp.day) + " '" + d_exp.strftime("%y")
                    german_exp     = d_exp.strftime("%d.%m.%Y")
                    dte            = max(0, (d_exp.date() - date.today()).days)
                except Exception:
                    expiry_display = str(expiry)
                    german_exp     = str(expiry)
                    dte            = 0

                optionstrat_url = _optionstrat_url_manual(
                    ticker, strike, expiry, is_call, is_strangle, call_strike, call_expiry
                )
                trade_id     = _gen_trade_id(ticker, strategy)
                tracking_url = _build_tracking_url(_eff_app_url, trade_id)
                # Zeitstempel in Berliner Zeit
                try:
                    import pytz as _pytz
                    _now_berlin = datetime.now(_pytz.timezone("Europe/Berlin"))
                except Exception:
                    _now_berlin = datetime.now()
                post_ts      = _now_berlin.strftime("%d.%m.%Y · %H:%M Uhr")

                # Nur in den Trade Monitor übernehmen, wenn der Nutzer es wünscht.
                if st.session_state.get("m_into_monitor", True):
                    _save_manual_trade({
                        "trade_id": trade_id, "class": cls, "ticker": ticker,
                        "company": company, "strategy": strategy,
                        "strike": strike, "call_strike": call_strike,
                        "expiry": str(expiry), "call_expiry": str(call_expiry),
                        "premium": premium, "delta": delta, "iv_pct": iv_pct,
                        "price_at_entry": price_now,
                        "created_at": datetime.now().isoformat(),
                        "post_ts": post_ts,
                        "optionstrat_url": optionstrat_url,
                        "tracking_url": tracking_url,
                        "status": "AKTIV",
                    })

                # ── Zusatzdaten für den Post: ATH-Distanz, Unternehmenssatz, News-Zeile
                _ath_price_dist = None
                try:
                    _hist2 = fetch_price_history(ticker, period="2y")
                    if _hist2 is not None and not _hist2.empty:
                        _ath = float(_hist2["Close"].max())
                        if _ath > 0 and price_now > 0:
                            _ath_price_dist = (_ath - price_now) / _ath * 100
                except Exception:
                    pass

                _desc = (tdata.get("description") or "").strip()
                if _desc:
                    _sentence = _translate_de(_desc.split(". ")[0].strip()[:180])
                    _company_sentence = _sentence.rstrip(".") + "."
                else:
                    _company_sentence = ""

                _news_items = tdata.get("news", []) or []
                if _news_items:
                    _nt = (_news_items[0].get("title") or "").strip()
                    _news_line = _translate_de(_nt[:140]) if _nt else ""
                else:
                    _news_line = ""

                # Fundamental-Kennzahlen einzeln: Gewinnwachstum, KGV, FW KGV
                _fund = tdata.get("fund", {}) or {}
                def _ffloat(v):
                    try:
                        return float(v) if v is not None else None
                    except Exception:
                        return None
                _eg     = _ffloat(_fund.get("earnings_growth_yoy"))
                _pe_t   = _ffloat(_fund.get("pe_trailing"))
                _pe_f   = _ffloat(_fund.get("pe_forward"))
                _eps_tr = _ffloat(_fund.get("eps_trailing"))
                _eps_fw = _ffloat(_fund.get("eps_forward"))
                _peg    = _ffloat(_fund.get("peg_ratio"))
                # EPS-Wachstum: aktuell (YoY) + nächstes Jahr (Forward-EPS vs. Trailing-EPS)
                _eps_cur = _eg * 100 if _eg is not None else None
                _eps_fwd = (((_eps_fw - _eps_tr) / abs(_eps_tr)) * 100
                            if (_eps_tr and _eps_fw and _eps_tr != 0) else None)
                # PEG forward: Forward-KGV / Forward-EPS-Wachstum
                _peg_e = (_pe_f / _eps_fwd) if (_pe_f and _eps_fwd and _eps_fwd > 0) else None
                _funda = {
                    "eps_cur": _eps_cur, "eps_fwd": _eps_fwd,
                    "kgv": _pe_t, "kgv_e": _pe_f,
                    "peg": _peg, "peg_e": _peg_e,
                }

                # Multi-Timeframe-Farbpunkte (4h / 1T) für die Technik
                _tf_colors = _tf_color_dots(ticker)

                # Langversion
                wa_long = _build_whatsapp_short_manual(
                    class_label=cls, ticker=ticker, company=company,
                    strategy=strategy, strike=strike, german_exp=german_exp,
                    expiry_short=expiry_display, dte=dte,
                    premium=premium, delta=delta, iv_pct=iv_pct,
                    price_now=price_now,
                    trend_simple=tdata.get("trend_simple", ""),
                    macd_desc=tdata.get("macd_desc", ""),
                    stoch_desc=tdata.get("stoch_desc", ""),
                    optionstrat_url=optionstrat_url,
                    tracking_url=tracking_url,
                    post_ts=post_ts,
                    support_near=tdata.get("support_near"),
                    ath_price_dist=_ath_price_dist,
                    company_sentence=_company_sentence,
                    news_line=_news_line,
                    funda=_funda,
                    tf_colors=_tf_colors,
                )
                # Kurzversion
                wa_compact = _build_whatsapp_compact(
                    cls, ticker, strategy, expiry_display, strike, premium,
                    post_ts, optionstrat_url,
                )

                # Circle Detailpost
                mock_row = pd.Series({
                    "SC Trend(1D)": tdata.get("trend_str", ""),
                    "MACD(1D)":     tdata.get("macd_str", ""),
                    "Stoch(1D)":    "",
                    "RSI(1D)":      f"{tdata['rsi']:.0f}" if tdata.get("rsi") else "",
                    "⚠️ Earnings":  "",
                })
                ta_lines_built = _ta_zeilen(mock_row)
                sr_note        = _get_sr_level(ticker, "PUT" if not is_call else "CALL", strike)
                otm_pct_val    = abs((price_now - strike) / price_now * 100) if price_now > 0 else 0
                trend_note_txt = (
                    tdata.get("trend_str", "") +
                    f" · Strike {_fmt_num(otm_pct_val, 1)}% OTM" +
                    (f" · {sr_note}" if sr_note else "")
                )
                bg_desc  = tdata.get("description", "")
                bg_text  = _translate_de(bg_desc[:400]) if bg_desc else f"{company} ist ein börsennotiertes Unternehmen."
                news_txt = _format_news_text(tdata.get("news", []))
                rend_lz_val = premium / strike * 100 if strike > 0 else 0

                circle_base = _build_card_text(
                    ticker=ticker, trade_exp=expiry_display, strike=strike,
                    option_type="PUT" if not is_call else "CALL",
                    premium=premium, rendite_lz=rend_lz_val, strategie=strategy,
                    ath_dist=_ath_pct(ticker, strike), german_exp=german_exp,
                    dte=dte, trend_note=trend_note_txt, background=bg_text,
                    news_text=news_txt, delta=delta, iv=iv_pct, crv=0.0,
                    sektor="", company_name=company, ta_lines=ta_lines_built,
                    price_now=price_now, fund=tdata.get("fund", {}), covered_call="",
                )
                circle_post = circle_base + _build_circle_suffix(
                    optionstrat_url, tracking_url, post_ts, cls
                )

                _generated[cls] = {
                    "ticker": ticker, "wa_compact": wa_compact, "wa_long": wa_long,
                    "circle": circle_post, "trade_id": trade_id,
                    # Felder für den Sammel-Kurzpost
                    "strategy": strategy, "expiry_short": expiry_display,
                    "strike": strike, "premium": premium,
                    "optionstrat_url": optionstrat_url,
                }

            st.session_state["m_generated"] = _generated
            st.session_state["m_post_ts"] = post_ts
            st.session_state.pop("m_circle_url", None)   # alten Circle-Link verwerfen
            st.success(f"✅ {len(_generated)} Trade(s) generiert ({', '.join(_generated.keys())}) "
                       "— für Live-Tracking gespeichert")
            if _skipped:
                st.warning("⚠️ Übersprungen: " + " · ".join(_skipped))

    # Display generated posts
    if "m_generated" in st.session_state and st.session_state["m_generated"]:
        gen = st.session_state["m_generated"]

        st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)
        st.markdown("## 📱 Kurzversion (für schnelles Teilen)")
        sc_tabs = st.tabs([f"Class {cls} · {d['ticker']}" for cls, d in gen.items()])
        for (cls, d), stab in zip(gen.items(), sc_tabs):
            with stab:
                st.code(d["wa_compact"], language="text")

        st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)
        st.markdown("## 📋 Langversion (Detail-Post)")
        lg_tabs = st.tabs([f"Class {cls} · {d['ticker']}" for cls, d in gen.items()])
        for (cls, d), ltab in zip(gen.items(), lg_tabs):
            with ltab:
                st.code(d["wa_long"], language="text")

        st.markdown(f"### 📤 Alle {len(gen)} zusammen (Langversion)")
        combined_long = f"\n\n{'─' * 30}\n\n".join(d["wa_long"] for d in gen.values())
        st.code(combined_long, language="text")

        # ── Circle-Version zum manuellen Kopieren ─────────────────────────────
        # WhatsApp-*fett* wirkt auf Circle nicht — hier als **Markdown-Fett**,
        # das Circles Editor beim Einfügen in echtes Fett umwandelt.
        st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)
        st.markdown("## 🌐 Circle-Version (kopieren & einfügen)")
        st.caption(
            "Formatierung für Circle: **fett** statt WhatsApp-*fett*. "
            "Text kopieren → in den Circle-Editor einfügen → Fett wird automatisch übernommen."
        )
        ci_tabs = st.tabs([f"Class {cls} · {d['ticker']}" for cls, d in gen.items()]
                          + [f"Alle {len(gen)} zusammen"])
        for (cls, d), ctab in zip(gen.items(), ci_tabs[:-1]):
            with ctab:
                st.code(_to_circle_text(d["wa_long"]), language="text")
        with ci_tabs[-1]:
            st.code(_to_circle_text(combined_long), language="text")

        # ── Circle-Sammelpost (Masterclass) + WhatsApp-Sammel-Kurzpost ────────
        st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)
        st.markdown("## 🌐 Auf Circle posten (Masterclass) → WhatsApp")

        _ci_token = _sec("CIRCLE_API_TOKEN")
        _ci_space = int(_sec("CIRCLE_SPACE_MASTERCLASS", "0") or 0)
        _ci_ok = bool(_ci_token and _ci_space)

        if not _ci_ok:
            st.info(
                "🔒 Circle-Auto-Post inaktiv. Setze in Railway/Secrets: "
                "`CIRCLE_API_TOKEN` (dein Admin-API-Token) und "
                "`CIRCLE_SPACE_MASTERCLASS` (Space-ID des Masterclass-Bereichs). "
                "Solange kannst du die Langversion oben manuell auf Circle posten."
            )
        else:
            def _berlin_now() -> str:
                try:
                    import pytz as _p
                    return datetime.now(_p.timezone("Europe/Berlin")).strftime("%d.%m.%Y · %H:%M Uhr")
                except Exception:
                    return datetime.now().strftime("%d.%m.%Y · %H:%M Uhr")
            if st.button("🌐 Sammelpost auf Circle erstellen", type="primary",
                         key="btn_circle_post",
                         help="Postet alle Trades als EINEN Detail-Post in den Masterclass-Space "
                              "und baut daraus den WhatsApp-Sammelpost mit Circle-Link."):
                _title = f"Trading-Ideen {datetime.now().strftime('%d.%m.%Y')} — {len(gen)} Setups"
                _html_body = "\n<hr>\n".join(_text_to_html(d["wa_long"]) for d in gen.values())
                try:
                    from pipeline.publishers import CirclePublisher
                    _pub = CirclePublisher(token=_ci_token, space_ids={"masterclass": _ci_space})
                    with st.spinner("⏳ Poste auf Circle…"):
                        _url = _pub.create_post("masterclass", _title, _html_body)
                    if _url:
                        st.session_state["m_circle_url"] = _url
                        st.session_state["m_circle_ts"]  = _berlin_now()   # Zeit = jetzt (Posting)
                        st.success(f"✅ Auf Circle (Masterclass) gepostet: {_url}")
                    else:
                        st.warning("Circle hat keine URL zurückgegeben — bitte im Space prüfen.")
                except Exception as _e:
                    st.error(f"⚠️ Circle-Fehler: {_e}")

            _circle_url = st.session_state.get("m_circle_url", "")
            if _circle_url:
                _ts = st.session_state.get("m_circle_ts") or _berlin_now()
                st.markdown("### 📱 WhatsApp-Sammelpost (mit Circle-Link) — auf WhatsApp kopieren")
                st.code(_build_combined_short(gen, _circle_url, _ts), language="text")


# ════════════════════════════════════════════════════════════════════════════════
# TAB 2 — AUS SCANNER
# ════════════════════════════════════════════════════════════════════════════════
with tab2:
    # ── Cache laden ──────────────────────────────────────────────────────────
    cached = _load_scan_cache()

    if cached is None or cached.get("results") is None or cached["results"].empty:
        st.warning(
            "**Kein Scan-Ergebnis vorhanden.**\n\n"
            "Bitte zuerst im **Watchlist Scanner** oder **Top 9 Trading Ideen** einen Scan durchführen. "
            "Die besten Ergebnisse werden hier automatisch geladen.",
            icon="⚠️",
        )
        if st.button("➜ Zum Watchlist Scanner", type="primary", key="btn_to_scanner_t2"):
            st.switch_page("pages/04_Watchlist_Scanner.py")
    else:
        df_all: pd.DataFrame = cached["results"].copy()
        scan_strategy = cached.get("strategy", "Cash Covered Put")
        scan_ts = cached.get("timestamp")
        scan_age = ""
        if scan_ts:
            age_min = int((datetime.now() - scan_ts).total_seconds() / 60)
            scan_age = f" · vor {age_min} Min." if age_min < 60 else f" · {scan_ts.strftime('%d.%m. %H:%M')}"

        st.info(
            f"📊 **{len(df_all)} Optionen** aus letztem Scan — Strategie: **{scan_strategy}**{scan_age}  \n"
            f"Die besten Ergebnisse nach CRV Score werden unten als Trade Card aufbereitet.",
            icon="✅",
        )

        # ── Einstellungen ────────────────────────────────────────────────────
        with st.expander("⚙️ **Einstellungen**", expanded=False):
            s1, s2, s3 = st.columns(3)
            with s1:
                n_cards = st.number_input("Anzahl Trade Cards", 1, 5, 3, key="t2_n_cards")
            with s2:
                sort_col = st.selectbox(
                    "Sortierung",
                    [c for c in ["CRV Score", "Konvergenz", "Rendite % Laufzeit", "Rendite %/Tag"]
                     if c in df_all.columns],
                    key="t2_sort",
                )
            with s3:
                news_count = st.number_input("News-Zeilen pro Trade", 1, 6, 3, key="t2_news")

        # Top N nach gewählter Sortierung
        _df_sorted = df_all.sort_values(sort_col, ascending=False).drop_duplicates(subset=["Ticker"])
        if "Delta" in _df_sorted.columns:
            _df_sorted = _df_sorted[_df_sorted["Delta"].abs() >= 0.10]
        top_df = _df_sorted.head(int(n_cards)).reset_index(drop=True)

        st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

        # ── Karten ───────────────────────────────────────────────────────────
        all_card_texts: list = []

        for idx, row in top_df.iterrows():
            ticker   = row.get("Ticker", "")
            strike   = float(row.get("Strike", 0))
            expiry   = row.get("Verfall", "")
            premium  = float(row.get("Prämie", 0))
            rendite  = float(row.get("Rendite % Laufzeit", 0))
            otm_pct  = float(row.get("OTM %", 0))
            crv      = float(row.get("CRV Score", 0)) if "CRV Score" in row else 0.0

            option_type, strategie     = _get_strategy_type(row)
            trade_exp, german_exp, dte = _fmt_expiry_trade(expiry)
            sr_note                    = _get_sr_level(ticker, option_type, strike)
            trend_note_auto            = _build_trend_note(row, otm_pct, sr_note)

            rank_icon = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][idx]

            with st.expander(
                f"{rank_icon} **{ticker}** — {trade_exp} @{strike:.0f} {option_type} · "
                f"Prämie {_fmt_num(premium)} USD · {dte} Tage · CRV {crv:.0f}",
                expanded=(idx == 0),
            ):
                with st.spinner(f"Lade Daten & News für {ticker}…"):
                    stock_data  = _cached_stock_data(ticker)
                    info        = stock_data["info"]
                    rss_items   = _fetch_ticker_news_rss(ticker, n=int(news_count))

                company_name = info.get("name", ticker)
                eng_desc     = (info.get("description") or "").strip()
                fund_data    = stock_data["fund"]
                news_auto    = _format_news_text(rss_items)
                ath_pct_val  = _ath_pct(ticker, strike)

                delta_raw   = float(row.get("Delta", 0.0))
                iv_raw      = float(row.get("IV %", 0.0))
                sektor_raw  = str(row.get("Sektor", ""))
                price_now_raw = float(info.get("price") or info.get("currentPrice") or 0.0)
                if price_now_raw <= 0 and otm_pct > 0:
                    price_now_raw = strike / (1 - otm_pct / 100)
                ta_lines_built    = _ta_zeilen(row)
                covered_call_text = _covered_call_reco(row, price_now_raw, dte, iv_raw)

                col_left, col_right = st.columns([3, 2])

                with col_left:
                    st.markdown(f"**📋 {company_name} ({ticker})**")
                    st.markdown(
                        "<div style='font-size:0.78rem;color:#666;margin-bottom:2px'>"
                        "Hintergrund-Text (bearbeiten → auf Deutsch, 2–3 Sätze)</div>",
                        unsafe_allow_html=True,
                    )
                    default_bg = _translate_de(eng_desc[:400]) if eng_desc else f"{company_name} ist ein börsennotiertes Unternehmen."
                    background = st.text_area(
                        "Hintergrund", value=default_bg, height=110,
                        key=f"bg_{ticker}_{idx}", label_visibility="collapsed",
                    )
                    st.markdown(
                        "<div style='font-size:0.78rem;color:#666;margin-top:8px;margin-bottom:2px'>"
                        "News (bearbeiten)</div>",
                        unsafe_allow_html=True,
                    )
                    news_text = st.text_area(
                        "News", value=news_auto, height=90,
                        key=f"news_{ticker}_{idx}", label_visibility="collapsed",
                    )
                    st.markdown(
                        "<div style='font-size:0.78rem;color:#666;margin-top:8px;margin-bottom:2px'>"
                        "Absicherungs-Zeile (bearbeiten)</div>",
                        unsafe_allow_html=True,
                    )
                    trend_note = st.text_input(
                        "Absicherung", value=trend_note_auto,
                        key=f"trend_{ticker}_{idx}", label_visibility="collapsed",
                    )

                with col_right:
                    st.markdown("**📊 Trade-Details**")
                    ath_label = f"{_fmt_num(ath_pct_val, 0)}% unter ATH" if ath_pct_val else "–"
                    ann_r = rendite * 365 / max(dte, 1)

                    def _fd(key, dec=1, mul=1.0, prefix="", suffix="", _fd=fund_data):
                        v = _fd.get(key)
                        try:
                            return f"{prefix}{_fmt_num(float(v) * mul, dec)}{suffix}"
                        except Exception:
                            return "–"

                    st.markdown(f"""
| | |
|---|---|
| **Strategie** | {strategie} |
| **Strike** | ${strike:.0f} |
| **{option_type}-Verfall** | {german_exp} ({dte}T) |
| **Prämie** | {_fmt_num(premium)} USD |
| **Gesamt (1x)** | {round(premium*100)} USD |
| **Rendite p.a.** | ~{_fmt_num(ann_r, 1)}% |
| **Rendite LZ** | {_fmt_num(rendite)}% |
| **Delta** | {delta_raw:.2f} |
| **IV** | {iv_raw:.0f}% |
| **OTM** | {_fmt_num(otm_pct, 1)}% |
| **ATH-Abstand** | {ath_label} |
| **CRV Score** | {crv:.0f} |
| | |
| **EPS (TTM)** | {_fd("eps_trailing", 2, prefix="$")} |
| **EPS-Wachstum** | {_fd("earnings_growth_yoy", 1, mul=100, suffix="%")} |
| **KGV / Fwd** | {_fd("pe_trailing", 1)} / {_fd("pe_forward", 1)} |
| **PEG Ratio** | {_fd("peg_ratio", 2)} |
| **Analystenziel** | {_fd("target_price", 0, prefix="$")} |
""")

                card_text = _build_card_text(
                    ticker=ticker, trade_exp=trade_exp, strike=strike,
                    option_type=option_type, premium=premium, rendite_lz=rendite,
                    strategie=strategie, ath_dist=ath_pct_val, german_exp=german_exp,
                    dte=dte, trend_note=trend_note, background=background,
                    news_text=news_text, delta=delta_raw, iv=iv_raw, crv=crv,
                    sektor=sektor_raw, company_name=company_name,
                    ta_lines=ta_lines_built, price_now=price_now_raw,
                    fund=fund_data, covered_call=covered_call_text,
                )
                all_card_texts.append(card_text)
                st.markdown("---")
                st.markdown("**📱 WhatsApp Text — direkt kopieren:**")
                st.code(card_text, language="text")

        if all_card_texts:
            st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)
            st.markdown("### 📤 Alle Trade Cards + Disclaimer (eine Nachricht)")
            st.caption(
                "Diesen Block als eine komplette WhatsApp-Nachricht senden — "
                "alle Trade Ideas + Standard-Disclaimer am Ende."
            )
            combined = "\n\n" + ("─" * 30 + "\n\n").join(all_card_texts)
            combined += "\n\n" + "─" * 30 + "\n\n" + _DISCLAIMER
            st.code(combined, language="text")
