"""
Stillhalter AI App — Market Intelligence Hub
Mando-Minutes-Style: schnell scannen, selektiv klicken.
Watchlist-Aktien zuerst · X/Twitter · Märkte · Makro
"""

import streamlit as st
import requests
import xml.etree.ElementTree as ET
import yfinance as yf
import re
from datetime import datetime, timezone
from typing import Optional, Dict, List, Tuple
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

st.set_page_config(
    page_title="Marktanalyse / News · Stillhalter AI App",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

# Extra CSS für kompakten Feed-Style
st.markdown("""
<style>
.feed-item { transition: background 0.15s; }
.feed-item:hover { background: #141414 !important; }
</style>
""", unsafe_allow_html=True)

from data.watchlist import WATCHLIST, ALL_TICKERS, SECTOR_ICONS

# ══════════════════════════════════════════════════════════════════════════════
# KONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════

TWITTER_ACCOUNTS = [
    # ── Breaking / Flow ──────────────────────────────────────────────────────
    {"handle": "DeItaone",        "icon": "⚡", "color": "#f59e0b", "label": "Breaking"},
    {"handle": "unusual_whales",  "icon": "🐳", "color": "#3b82f6", "label": "Flow"},
    {"handle": "optionmillionrs", "icon": "📈", "color": "#f97316", "label": "Options"},
    {"handle": "marketfeed",      "icon": "📡", "color": "#6366f1", "label": "Flow"},
    # ── Makro / Research ─────────────────────────────────────────────────────
    {"handle": "elerianm",        "icon": "🌍", "color": "#8b5cf6", "label": "Makro"},
    {"handle": "SentimenTrader",  "icon": "📊", "color": "#06b6d4", "label": "Sentiment"},
    {"handle": "RenMacLLC",       "icon": "🔬", "color": "#10b981", "label": "Research"},
    {"handle": "TruthGundlach",   "icon": "💎", "color": "#d4a843", "label": "Bonds"},
    {"handle": "tomergreenblatt", "icon": "🧠", "color": "#a78bfa", "label": "Value"},
    {"handle": "fundstrat",       "icon": "🎯", "color": "#22d3ee", "label": "Strategie"},
    # ── Konträr / Alternatives ───────────────────────────────────────────────
    {"handle": "zerohedge",       "icon": "🦅", "color": "#ef4444", "label": "Konträr"},
    {"handle": "ReformedBroker",  "icon": "🏦", "color": "#34d399", "label": "Wall St."},
    # ── Tech / Einzelwerte ───────────────────────────────────────────────────
    {"handle": "chamath",         "icon": "🚀", "color": "#ec4899", "label": "Tech/VC"},
    {"handle": "BernieSandwich",  "icon": "🍔", "color": "#fb923c", "label": "Retail"},
    {"handle": "TreysTrades",     "icon": "📉", "color": "#fbbf24", "label": "Retail"},
]

SECTOR_SEARCH = {
    "1. TECHNOLOGIE (TECHNOLOGY)":
        "technology stocks AI chips semiconductors NVDA AMD MSFT AAPL",
    "2. GESUNDHEITSWESEN (HEALTHCARE)":
        "healthcare pharma biotech FDA approval LLY JNJ MRK",
    "3. FINANZDIENSTLEISTUNGEN (FINANCIAL)":
        "banking financial stocks JPM Goldman Fed rates BAC GS",
    "4. BASISKONSUMGÜTER (CONSUMER STAPLES)":
        "consumer staples stocks WMT KO PG MCD dividend",
    "5. ENERGIE (ENERGY)":
        "oil energy stocks OPEC crude XOM CVX COP BP",
    "6. INDUSTRIE (INDUSTRIALS)":
        "industrial defense aerospace Boeing Lockheed CAT GE",
    "7. IMMOBILIEN (REITS)":
        "REIT real estate interest rates housing DLR AMT",
    "8. TELEKOMMUNIKATION (COMMUNICATION SERVICES)":
        "media social streaming Meta Netflix Google advertising",
    "9. VERBRAUCHSGÜTER (CONSUMER DISCRETONARY)":
        "consumer Amazon Tesla retail spending AMZN NFLX UBER",
    "10. VERSORGER (UTILITIES)":
        "utility electricity grid nuclear clean energy NEE DUK",
    "11. GRUNDSTOFFE (BASIC MATERIALS)":
        "materials gold silver copper mining NEM FCX commodities",
}

# Kategorie → Farbe
CAT_COLOR = {
    "watchlist": "#d4a843",
    "twitter":   "#1d9bf0",
    "boerse":    "#22c55e",
    "geo":       "#ef4444",
    "makro":     "#3b82f6",
}

# Schlagwort-Tags für jede Nachricht
KEYWORD_TAGS: List[Tuple[List[str], str]] = [
    (["earnings beat", "beat estimates", "beats estimates", "topped estimates", "topped analyst"], "📊 Beat"),
    (["earnings miss", "missed estimates", "misses estimates", "below estimates"],                 "📊 Miss"),
    (["guidance raised", "raises guidance", "raised outlook", "raised its outlook"],              "📈 Guidance ↑"),
    (["guidance lowered", "cuts guidance", "lowers guidance", "lowered outlook"],                 "📉 Guidance ↓"),
    (["fda approved", "fda approval", "approved by fda", "approval granted"],                    "💊 FDA ✓"),
    (["fda rejected", "complete response letter", "fda refuses"],                                "💊 FDA ✗"),
    (["merger", "acquisition", "acquired by", "takeover", "buyout"],                             "🤝 M&A"),
    (["share repurchase", "buyback", "repurchases shares"],                                      "🔄 Buyback"),
    (["ipo", "initial public offering", "goes public", "debut"],                                 "🆕 IPO"),
    (["rate cut", "cuts rates", "zinssenkung"],                                                  "🏦 Zinssenkung"),
    (["rate hike", "raises rates", "zinserhöhung"],                                              "🏦 Zinserhöhung"),
    (["fomc", "federal reserve", "powell"],                                                      "🏦 Fed"),
    (["consumer price index", "cpi report"],                                                     "📊 CPI"),
    (["pce", "personal consumption expenditure"],                                                "📊 PCE"),
    (["inflation"],                                                                              "📊 Inflation"),
    (["nonfarm payroll", "jobs report", "payrolls"],                                             "👷 Jobs"),
    (["gross domestic product", "gdp growth", "gdp shrinks"],                                   "📉 BIP"),
    (["pmi", "ism manufacturing"],                                                               "🏭 PMI"),
    (["artificial intelligence", "ai model", "generative ai", "large language"],                 "🤖 KI"),
    (["semiconductor", "chip shortage", "gpu demand"],                                           "💾 Chips"),
    (["crude oil", "oil price", "opec", "brent crude", "wti"],                                  "🛢️ Öl"),
    (["ukraine", "russia"],                                                                      "⚔️ Ukraine"),
    (["iran", "nuclear"],                                                                        "☢️ Iran"),
    (["china", "taiwan"],                                                                        "🌏 China/Taiwan"),
    (["middle east", "israel", "hamas", "hezbollah"],                                            "🌍 Nahost"),
    (["vix spike", "vix surges", "vix jumps"],                                                   "📊 VIX ↑"),
    (["implied volatility", "vix"],                                                              "📊 Volatilität"),
    (["short squeeze", "short covering"],                                                        "⚡ Short Squeeze"),
    (["unusual options", "dark pool", "options flow"],                                           "🐳 Flow"),
    (["dividend cut", "suspends dividend", "eliminates dividend"],                               "💰 Div. ↓"),
    (["dividend", "dividende"],                                                                  "💰 Dividende"),
    (["upgrade", "outperform", "buy rating", "price target raised"],                             "⬆️ Upgrade"),
    (["downgrade", "underperform", "sell rating", "price target cut"],                           "⬇️ Downgrade"),
    (["layoffs", "job cuts", "workforce reduction", "restructuring"],                            "✂️ Stellenabbau"),
    (["bitcoin", "crypto", "ethereum", "blockchain"],                                            "₿ Crypto"),
    (["recession", "economic slowdown", "contraction"],                                          "📉 Rezession"),
    (["all-time high", "record high", "new high"],                                               "🏆 Rekordhoch"),
    (["bankruptcy", "chapter 11", "files for bankruptcy"],                                       "⚠️ Insolvenz"),
    (["stock split", "share split"],                                                             "✂️ Split"),
    (["sanctions", "embargo"],                                                                   "🚫 Sanktionen"),
    (["earnings", "quarterly results"],                                                          "📅 Earnings"),
]

POSITIVE_SIGNALS = ["beat", "beats", "surge", "surges", "rises", "gains", "upgraded",
                    "approval", "approved", "buyback", "raised guidance", "record high",
                    "tops", "rallies", "jumps", "soars", "climbs", "outperforms"]
NEGATIVE_SIGNALS = ["miss", "misses", "falls", "drops", "downgraded", "rejected",
                    "cuts guidance", "layoffs", "job cuts", "bankruptcy", "slumps",
                    "plunges", "recession", "missed", "below expectations", "warns"]

# ══════════════════════════════════════════════════════════════════════════════
# RELEVANZ-ENGINE
# ══════════════════════════════════════════════════════════════════════════════

RELEVANCE_RULES: List[Tuple[List[str], str]] = [
    # ── FOMC / FED ────────────────────────────────────────────────────────────
    (["fomc meeting", "fed meeting", "federal open market"],
     "FOMC-Tag: IV steigt 1–3 Tage vorher → kein neuer Entry; nach Entscheid IV-Crush als Prämiengewinn nutzen"),
    (["rate cut", "zinssenkung", "cuts rates"],
     "Zinssenkung: Wachstumswerte (Tech) steigen, Dividendentitel attraktiver → bullisches Umfeld für Short-Puts"),
    (["rate hike", "zinserhöhung", "raises rates"],
     "Zinserhöhung: Druck auf REITs, Utilities, Wachstumsaktien → Strike-Wahl tiefer ansetzen"),
    (["powell speech", "powell says", "powell warns"],
     "Powell-Aussagen bewegen Markt sofort: hawkish Ton → Sells; dovish Ton → Rallye — IV kurz danach beobachten"),
    (["fomc", "federal reserve", "fed decision"],
     "Fed-Entscheid beeinflusst alle zinssensitiven Sektoren und VIX → Event-IV bis Bekanntgabe abwarten"),

    # ── INFLATION / MAKRO-DATEN ───────────────────────────────────────────────
    (["cpi report", "inflation data", "consumer price index"],
     "CPI-Überraschung > 0,2%: VIX-Spike möglich → Covered Calls unter Druck, Short-Puts prüfen"),
    (["pce", "personal consumption expenditure"],
     "PCE = Feds bevorzugtes Inflationsmaß → direkter Einfluss auf Zinserwartungen & Anleihe-Yields"),
    (["inflation", "inflationsdaten", "inflationsrate"],
     "Inflationsdaten bestimmen Fed-Kurs → zinssensitive Sektoren (Utilities, REITs, Financials) reagieren stark"),
    (["nonfarm payroll", "jobs report", "payrolls"],
     "Jobs-Report: Starker Markt → Fed hawkisch → Anleihe-Yields steigen → Wachstumsaktien (NVDA, MSFT) unter Druck"),
    (["gdp", "gross domestic product", "wirtschaftswachstum"],
     "BIP-Überraschung: positiv = bullisches Regime für Short-Puts; negativ = defensivere Strikes wählen"),
    (["pmi", "ism manufacturing", "einkaufsmanager"],
     "PMI < 50 = Kontraktion: Industrieaktien (CAT, GE, BA) erhöhtes Gap-Risiko → Positionen enger absichern"),
    (["consumer confidence", "verbrauchervertrauen", "consumer sentiment"],
     "Konsumklima beeinflusst Retail & Konsumgüter (AMZN, WMT, MCD) → sektorspezifisch auf Richtung prüfen"),
    (["recession", "rezession", "economic slowdown"],
     "Rezessionsangst: Risk-off-Modus → Cash erhöhen, defensive Strikes, Covered Calls bevorzugen"),

    # ── EARNINGS ─────────────────────────────────────────────────────────────
    (["earnings beat", "beat expectations", "topped estimates", "beats estimates"],
     "Earnings Beat + stabiler Kurs: Short-Put profitiert vom IV-Crush → Zeitwertgewinn realisiert"),
    (["earnings miss", "missed estimates", "below expectations", "misses estimates"],
     "Earnings Miss: Gap-Down möglich → offene Short-Puts sofort auf Margin & Risiko prüfen"),
    (["guidance raised", "raised outlook", "raises guidance", "erhöht prognose"],
     "Guidance-Anhebung = bullisches Signal → nach IV-Normalisierung Call-Spread oder Short-Put erwägen"),
    (["guidance lowered", "cuts guidance", "lowers outlook", "senkt prognose"],
     "Guidance-Senkung: Markt straft oft stärker als Earnings → Short-Calls meiden, Short-Puts absichern"),
    (["earnings", "quarterly results", "q1 results", "q2 results", "q3 results", "q4 results"],
     "Earnings-Event: IV steigt 5–10 Tage vorher, fällt nach Bekanntgabe → Entry-Timing entscheidend"),

    # ── GEOPOLITIK ────────────────────────────────────────────────────────────
    (["iran", "nuclear deal", "iran nuclear"],
     "Iran-Eskalation → Ölpreis + VIX steigen; Energie-Calls (XOM, CVX) werden teurer"),
    (["ukraine", "russia", "russland"],
     "Ukraine/Russland: Energiepreise & Rohstoffe volatil → Defensive Sektoren (Utilities, Healthcare) attraktiver"),
    (["taiwan", "china tensions", "south china sea"],
     "Taiwan/China-Risiko direkt für Chip-Sektor: NVDA, TSM, ASML-Positionen absichern oder reduzieren"),
    (["middle east", "naher osten", "israel", "hamas", "hezbollah"],
     "Nahost-Eskalation: Öl + VIX steigen → breite Markt-Hedges relevant, Prämien nutzen"),
    (["sanction", "sanctions", "embargo"],
     "Sanktionen treffen Rohstoff- und Energiemärkte → Sektorrotation in defensive Titel wahrscheinlich"),
    (["war", "military", "troops", "combat"],
     "Militärische Eskalation: Risk-off; VIX > 25 = Optionsprämien deutlich teurer → Stillhalter profitieren"),

    # ── VOLATILITÄT ───────────────────────────────────────────────────────────
    (["vix spike", "vix surges", "vix jumps", "fear gauge spikes"],
     "VIX-Spike: Prämien explodieren → ideales Stillhalter-Umfeld, aber Gap-Risiko berücksichtigen"),
    (["iv crush", "implied volatility crush"],
     "IV-Crush nach Event: Zeitwertgewinn = Kernstrategie des Stillhalters → Position halten oder rollen"),
    (["implied volatility", "iv spike", "iv elevated"],
     "Erhöhte IV = höhere Prämien beim Verkauf → besseres Risiko/Ertrag-Verhältnis für neue Entries"),
    (["vix", "volatility index"],
     "VIX-Level: < 15 = günstige Prämien (Buy-Side hat Vorteil), > 25 = teuer → Stillhalter profitieren"),

    # ── SEKTOREN / EINZELAKTIEN ───────────────────────────────────────────────
    (["oil price", "crude oil", "brent crude", "wti crude", "opec"],
     "Ölpreis-Bewegung direkt für Energie-Watchlist: XOM, CVX, COP, BP, SHEL → IV und Strike neu bewerten"),
    (["nvidia", "nvda", "gpu demand", "ai chips"],
     "NVDA: hohe IV durch Tech-Schwankungen = attraktive Prämien; aber starke Moves um Earnings beachten"),
    (["apple", "aapl", "iphone", "app store"],
     "AAPL: defensiver Tech mit moderater IV → geeignet für Covered Calls und konservative Short-Puts"),
    (["meta ", "facebook", "instagram", "ad revenue"],
     "META: Ad-Revenue-Zyklus treibt Kurs → Earnings-Plays und Covered Calls nach IV-Spike beliebt"),
    (["amazon", "aws", "amzn"],
     "AMZN: AWS-Marge + Retail → starke Earnings-Moves; IV vor Bekanntgabe prüfen"),
    (["microsoft", "msft", "azure", "copilot"],
     "MSFT: defensiver KI-Play mit stetigem Wachstum → Short-Puts mit höherem Strike attraktiv"),
    (["semiconductor", "chip", "semiconductor stocks"],
     "Chip-Sektor (NVDA, AMD, TSM, ASML): zyklisch + geopolitisch exponiert → IV oft elevated"),
    (["fda approval", "fda approved", "drug approval"],
     "FDA-Approval: Kurs-Sprung möglich → Stillhalter-Einstieg erst nach IV-Normalisierung sinnvoll"),
    (["fda", "clinical trial", "phase 3", "biotech"],
     "FDA-Event = binäres Risiko: IV explodiert 1–2 Wochen vorher; danach 40–70% Crush → kein offener Entry"),
    (["merger", "acquisition", "takeover bid", "buyout"],
     "M&A: Zielaktie springt → Short-Puts werden wertlos, Short-Calls gefährdet; Acquirer oft unter Druck"),
    (["buyback", "share repurchase", "aktienrückkauf"],
     "Aktienrückkauf = Kurs-Support von unten → Short-Puts profitieren; Kurs-Floor erhöht sich"),
    (["dividend cut", "dividende gestrichen", "suspends dividend"],
     "Dividenden-Kürzung: Kursrückgang wahrscheinlich → offene Short-Puts auf Risiko prüfen"),
    (["dividend", "dividende", "ex-dividend", "ex-div"],
     "Ex-Dividend: Kurs fällt um Dividendenbetrag → Call-Prämie sinkt entsprechend; Timing beachten"),

    # ── FLOW & SENTIMENT ─────────────────────────────────────────────────────
    (["unusual options activity", "unusual call", "unusual put"],
     "Ungewöhnlicher Options-Flow: Insiderhinweis auf Richtungserwartung → Strike-Bereich beobachten"),
    (["dark pool", "block trade", "institutional buying"],
     "Institutioneller Dark-Pool-Flow: große Käufe/Verkäufe vor Bewegung → Richtungsindikator"),
    (["put call ratio", "put/call", "options flow"],
     "Put/Call-Ratio > 1,2 = Angst (contrarian bullisch); < 0,6 = Gier (contrarian bärisch)"),
    (["short squeeze", "short covering"],
     "Short Squeeze: Kurs steigt schnell → offene Short-Calls mit Verlustrisiko; Delta-Hedge prüfen"),
    (["retail investors", "meme stock", "reddit", "wallstreetbets"],
     "Retail-Druck: erhöhte IV + unberechenbare Moves → Stillhalter-Positionen reduzieren oder enger absichern"),
    (["hedge fund", "13f", "institutional ownership"],
     "Institutionelle 13F-Positionierung = mittelfristiger Richtungshinweis für Basiswerte"),

    # ── BONDS / ZINSEN ────────────────────────────────────────────────────────
    (["yield curve", "inverted yield", "2-10 spread"],
     "Invertierte Zinskurve = Rezessionswarnung → defensivere Sektoren bevorzugen, Strikes nach unten anpassen"),
    (["10-year yield", "10y treasury", "bund yield"],
     "10Y-Yield steigt → Druck auf Wachstumsaktien (NVDA, MSFT, AMZN); REITs und Utilities fallen"),
    (["treasury", "bonds sell off", "bond market"],
     "Bond-Sell-off: steigende Yields = Gegenwind für zinssensitive Aktien in der Watchlist"),
    (["credit spread", "junk bonds", "high yield spread"],
     "Ausgeweitete Credit Spreads = Risikoaversion → defensivere Strikes wählen, Margin-Puffer erhöhen"),
    (["gundlach"],
     "Gundlach = Bond-Experte: seine Zinseinschätzung direkt relevant für REIT-, Utility- und Financial-Positionen"),
]

FALLBACK = "Marktrelevant — beobachten ob IV oder Trendrichtung in Watchlist-Aktien beeinflusst wird"


def _relevance(title: str, desc: str = "", ticker: str = "") -> str:
    """Findet die spezifischste Regel (längster Keyword-Match gewinnt)."""
    t = (title + " " + desc + " " + ticker).lower()
    best_expl, best_len = None, 0
    for kws, expl in RELEVANCE_RULES:
        for k in kws:
            if k in t and len(k) > best_len:
                best_len = len(k)
                best_expl = expl
    return best_expl or FALLBACK


# ══════════════════════════════════════════════════════════════════════════════
# HILFSFUNKTIONEN
# ══════════════════════════════════════════════════════════════════════════════

_EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)


def _to_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


def _sort_key(item: Dict) -> datetime:
    dt = item.get("dt")
    return _EPOCH if dt is None else _to_utc(dt)


def _age_hours(item: Dict) -> float:
    """Alter des Artikels in Stunden. None-Datum → sehr alt (9999h)."""
    dt = item.get("dt")
    if dt is None:
        return 9999.0
    try:
        return (datetime.now(timezone.utc) - _to_utc(dt)).total_seconds() / 3600
    except Exception:
        return 9999.0


def _is_fresh(item: Dict, max_hours: float = 168.0) -> bool:
    """True wenn Artikel jünger als max_hours (Standard: 7 Tage)."""
    return _age_hours(item) <= max_hours


def _rel_time(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    try:
        delta = int((datetime.now(timezone.utc) - _to_utc(dt)).total_seconds())
        if delta < 60:     return "jetzt"
        if delta < 3600:   return f"{delta//60}m"
        if delta < 86400:  return f"{delta//3600}h"
        if delta < 172800: return "gestern"
        return _to_utc(dt).strftime("%d.%m.")
    except Exception:
        return ""


def _clean(text: str, maxlen: int = 200) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text)).strip()[:maxlen]


def _parse_date(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return parsedate_to_datetime(s)
    except Exception:
        pass
    for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z",
                "%a, %d %b %Y %H:%M:%S %Z"]:
        try:
            return datetime.strptime(s.strip(), fmt)
        except Exception:
            continue
    return None


# ══════════════════════════════════════════════════════════════════════════════
# FETCH-FUNKTIONEN
# ══════════════════════════════════════════════════════════════════════════════

_HDR = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"),
    "Accept": "application/rss+xml, application/xml, */*",
}


@st.cache_data(ttl=1800, show_spinner=False)
def _rss(url: str, n: int = 8, src: str = "") -> List[Dict]:
    out: List[Dict] = []
    try:
        r    = requests.get(url, headers=_HDR, timeout=8)
        root = ET.fromstring(r.content)
        ch   = root.find("channel")
        if ch is None:
            return out
        for item in ch.findall("item")[:n]:
            def _t(tag: str, el=item) -> str:
                e = el.find(tag)
                return (e.text or "").strip() if e is not None else ""
            title = _clean(_t("title"))
            desc  = _clean(_t("description"))
            link  = _t("link")
            dt    = _parse_date(_t("pubDate"))
            se    = item.find("source")
            source = se.text.strip() if (se is not None and se.text) else src
            if title:
                out.append({"title": title, "desc": desc,
                            "link": link, "source": source, "dt": dt})
    except Exception:
        pass
    return out


@st.cache_data(ttl=900, show_spinner=False)
def _stock_news(ticker: str) -> List[Dict]:
    out: List[Dict] = []
    try:
        for n in (yf.Ticker(ticker).news or [])[:5]:
            c = n.get("content") or {}
            if c:
                title  = c.get("title", "")
                desc   = _clean(c.get("summary") or c.get("description", ""))
                link   = (c.get("canonicalUrl") or {}).get("url", "")
                source = (c.get("provider") or {}).get("displayName", "")
                dt     = _parse_date(c.get("pubDate") or c.get("displayTime"))
            else:
                title  = n.get("title", "")
                desc   = ""
                link   = n.get("link", "")
                source = n.get("publisher", "")
                ts     = n.get("providerPublishTime")
                dt     = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
            if title:
                out.append({"title": title, "desc": desc,
                            "link": link, "source": source, "dt": dt,
                            "ticker": ticker})
    except Exception:
        pass
    return out


@st.cache_data(ttl=1800, show_spinner=False)
def _twitter(handle: str, n: int = 5) -> List[Dict]:
    items = _rss(f"https://nitter.net/{handle}/rss", n=n, src=f"@{handle}")
    for it in items:
        if not it["title"] or it["title"].startswith("RT by"):
            it["title"] = _clean(it.get("desc", ""), 160)
        it["handle"] = handle
    return items


@st.cache_data(ttl=3600, show_spinner=False)
def _earnings() -> List[Dict]:
    WATCH = ["AAPL","MSFT","NVDA","AMZN","GOOGL","META","TSLA","JPM","V","MA",
             "UNH","JNJ","PG","XOM","CVX","ABBV","LLY","MRK","BAC","WFC",
             "NFLX","AVGO","ORCL","CRM","ADBE","AMD","INTC","QCOM","MU","PLTR",
             "GS","MS","C","BLK","PYPL","COIN","KO","PEP","MCD"]
    results: List[Dict] = []

    def _check(t: str) -> Optional[Dict]:
        try:
            tk   = yf.Ticker(t)
            today = datetime.now().date()
            ed    = None
            eps   = None

            # Methode 1: calendar dict
            try:
                cal = tk.calendar
                if cal is not None:
                    if hasattr(cal, "to_dict"):
                        cal = cal.to_dict()
                    for k in ("Earnings Date", "Earnings Date "):
                        if k in cal:
                            v = cal[k]
                            ed = v[0] if isinstance(v, (list, tuple)) and v else v
                            if hasattr(ed, "to_pydatetime"):
                                ed = ed.to_pydatetime()
                            eps = cal.get("EPS Estimate")
                            break
            except Exception:
                pass

            # Methode 2: earnings_dates DataFrame
            if ed is None:
                try:
                    edf = tk.earnings_dates
                    if edf is not None and not edf.empty:
                        import pandas as pd
                        future = edf[edf.index >= pd.Timestamp(today)]
                        if not future.empty:
                            ed = future.index[0].to_pydatetime()
                            row = future.iloc[0]
                            eps = row.get("EPS Estimate") if hasattr(row, "get") else None
                except Exception:
                    pass

            # Methode 3: info dict next_earnings_date
            if ed is None:
                try:
                    info = tk.info or {}
                    nef  = info.get("nextFiscalYearEnd") or info.get("earningsTimestamp")
                    if nef:
                        import pandas as pd
                        ed = datetime.fromtimestamp(int(nef), tz=timezone.utc)
                except Exception:
                    pass

            if ed is None:
                return None
            if hasattr(ed, "date"):
                d = ed.date()
            else:
                d = ed
            days = (d - today).days
            if -1 <= days <= 14:
                try:
                    eps_val = float(eps) if eps is not None else None
                except Exception:
                    eps_val = None
                return {"ticker": t, "date": ed, "days": days, "eps": eps_val}
        except Exception:
            pass
        return None

    with ThreadPoolExecutor(max_workers=10) as pool:
        futs = {pool.submit(_check, t): t for t in WATCH}
        for f in as_completed(futs):
            try:
                r = f.result()
                if r:
                    results.append(r)
            except Exception:
                pass
    results.sort(key=lambda x: _to_utc(x["date"]) if isinstance(x["date"], datetime)
                 else _EPOCH)
    return results


# ══════════════════════════════════════════════════════════════════════════════
# FEED-ZEILE — kompaktes Mando-Minutes-Style Item
# ══════════════════════════════════════════════════════════════════════════════

def _relevance_score(title: str, desc: str = "", ticker: str = "") -> int:
    """Höherer Score = spezifischere Regel getroffen → für Relevanz-Sortierung."""
    t = (title + " " + desc + " " + ticker).lower()
    best = 0
    for kws, _ in RELEVANCE_RULES:
        for k in kws:
            if k in t:
                best = max(best, len(k))
    return best


def _find_affected_tickers(title: str, desc: str = "") -> List[str]:
    """Findet Watchlist-Ticker die im Artikel-Text vorkommen."""
    text = " " + (title + " " + desc).upper() + " "
    found = []
    for ticker in ALL_TICKERS:
        if (f" {ticker} " in text or f"({ticker})" in text
                or f":{ticker}" in text or f"/{ticker}" in text):
            found.append(ticker)
        if len(found) >= 6:
            break
    return found


def _extract_tags(title: str, desc: str = "") -> List[str]:
    """Extrahiert bis zu 4 Schlagwort-Tags aus Titel + Beschreibung."""
    t = (title + " " + desc).lower()
    tags: List[str] = []
    seen: set = set()
    for kws, label in KEYWORD_TAGS:
        for k in kws:
            if k in t and label not in seen:
                tags.append(label)
                seen.add(label)
                break
        if len(tags) >= 4:
            break
    return tags


def _impact_direction(title: str, desc: str = "") -> str:
    """Leitet Kursrichtungs-Indikator aus Titelsentiment ab."""
    t = (title + " " + desc).lower()
    pos = sum(1 for w in POSITIVE_SIGNALS if w in t)
    neg = sum(1 for w in NEGATIVE_SIGNALS if w in t)
    if pos > neg:   return "↑"
    if neg > pos:   return "↓"
    return "→"


def _feed_card(
    title: str, link: str, source: str, dt: Optional[datetime],
    cat_color: str, cat_label: str, summary: str, relevance: str,
    affected: List[str], tags: Optional[List[str]] = None, extra_badge: str = "",
) -> str:
    """Reichhaltige Karte: Tags · Headline · Summary · Options-Relevanz · Impact-Tickers."""
    tags = tags or []

    time_str  = _rel_time(dt)
    direction = _impact_direction(title, summary)
    dir_color = "#22c55e" if direction == "↑" else "#ef4444" if direction == "↓" else "#6b7280"

    # ── Meta-Zeile: Zeit · Quelle ──────────────────────────────────────────────
    meta_html = (
        f"<div style='display:flex;align-items:center;gap:8px;margin-bottom:6px'>"
        f"<span style='font-size:0.6rem;color:{cat_color};font-weight:700;"
        f"background:{cat_color}18;padding:1px 7px;border-radius:3px;"
        f"font-family:sans-serif'>{cat_label}</span>"
        + (f"<span style='font-size:0.62rem;color:#aaa;background:#1c1c1c;"
           f"padding:1px 6px;border-radius:3px;font-family:monospace;"
           f"font-weight:700'>{extra_badge}</span>" if extra_badge else "")
        + f"<span style='font-size:0.6rem;color:#444;font-family:monospace'>{time_str}</span>"
        + (f"<span style='margin-left:auto;font-size:0.62rem;color:#aaaaaa;"
           f"font-family:sans-serif;white-space:nowrap;font-style:italic'>{source}</span>" if source else "")
        + f"</div>"
    )

    # ── Schlagwort-Tags ────────────────────────────────────────────────────────
    tag_html = "".join(
        f"<span style='font-size:0.59rem;color:#9ca3af;background:#1a1a1a;"
        f"border:1px solid #2a2a2a;padding:2px 7px;border-radius:12px;"
        f"font-family:sans-serif;white-space:nowrap'>{tag}</span>"
        for tag in tags
    )
    tags_row = (f"<div style='display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px'>"
                f"{tag_html}</div>") if tag_html else ""

    # ── Kurzzusammenfassung ───────────────────────────────────────────────────
    sum_html = (f"<div style='font-size:0.77rem;color:#6b7280;line-height:1.55;"
                f"margin-bottom:9px;font-family:sans-serif'>{summary}</div>") if summary else ""

    # ── Options-Relevanz-Bar ──────────────────────────────────────────────────
    rel_html = (
        f"<div style='font-size:0.7rem;color:#8fa8c8;background:#0b111e;"
        f"border-left:3px solid {cat_color};padding:5px 10px;"
        f"border-radius:0 5px 5px 0;line-height:1.55;margin-bottom:8px'>"
        f"<span style='color:{cat_color};font-weight:700;margin-right:5px'>▸ Options:</span>"
        f"{relevance}</div>"
    ) if relevance else ""

    # ── Impact: Richtung + betroffene Tickers ────────────────────────────────
    if affected:
        ticker_pills = "".join(
            f"<span style='font-size:0.65rem;color:{dir_color};background:{dir_color}14;"
            f"border:1px solid {dir_color}44;padding:2px 9px;border-radius:12px;"
            f"font-family:monospace;font-weight:700'>{direction} {t}</span>"
            for t in affected
        )
        impact_html = (
            f"<div style='display:flex;flex-wrap:wrap;align-items:center;gap:5px'>"
            f"<span style='font-size:0.59rem;color:#444;font-family:sans-serif'>Impact:</span>"
            f"{ticker_pills}</div>"
        )
    else:
        impact_html = ""

    return (
        f"<div class='feed-item' style='border-bottom:1px solid #161616;"
        f"padding:14px 14px 12px;background:#0c0c0c'>"
        f"{meta_html}"
        f"{tags_row}"
        f"<a href='{link}' target='_blank' rel='noopener' style='text-decoration:none'>"
        f"<div style='font-size:0.91rem;font-weight:700;color:#e8e8e8;line-height:1.4;"
        f"margin-bottom:7px;font-family:sans-serif'>{title}</div>"
        f"</a>"
        f"{sum_html}"
        f"{rel_html}"
        f"{impact_html}"
        f"</div>"
    )


def _section_title(icon: str, label: str, color: str, count: int = 0) -> str:
    badge = (f"<span style='font-size:0.6rem;color:#555;font-family:sans-serif'>"
             f"{count} Items</span>") if count else ""
    return (
        f"<div style='display:flex;align-items:center;gap:8px;padding:10px 4px 8px;"
        f"border-bottom:2px solid {color}44;margin-bottom:2px'>"
        f"<span style='font-size:1.0rem'>{icon}</span>"
        f"<span style='font-size:0.88rem;font-weight:800;color:{color};"
        f"font-family:sans-serif'>{label}</span>"
        f"{badge}"
        f"</div>"
    )


# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
now_str = datetime.now().strftime("%d.%m.%Y %H:%M")

hcol1, hcol2 = st.columns([6, 1])
with hcol1:
    st.html(f"""
<div style='display:flex;align-items:center;gap:14px;padding-bottom:4px'>
  {get_logo_html(height=38)}
  <div style='border-left:1px solid #1e1e1e;height:34px'></div>
  <div>
    <span style='font-size:1.2rem;font-weight:800;color:#f0f0f0;font-family:sans-serif'>
      📡 Market Intelligence</span>
    <span style='font-size:0.65rem;color:#555;font-family:sans-serif;margin-left:10px'>
      Stillhalter AI App · {now_str} · stündlich aktualisiert</span>
  </div>
  <div style='margin-left:10px;background:#0a1a0a;border:1px solid #22c55e33;
       border-radius:6px;padding:3px 10px'>
    <span style='font-size:0.6rem;color:#22c55e'>🟢 LIVE</span>
  </div>
</div>
""")
with hcol2:
    if st.button("🔄 Refresh", key="refresh", use_container_width=True):
        # Aktuelle Auswahl sichern bevor Cache geleert wird
        for _k in ("sector", "mode", "extra_tickers", "tw_selected", "custom_tw_handles", "tw_ticker_filter"):
            if _k in st.session_state:
                st.session_state[f"_saved_{_k}"] = st.session_state[_k]
        st.cache_data.clear()
        # Gesicherte Werte wiederherstellen
        for _k in ("sector", "mode", "extra_tickers", "tw_selected", "custom_tw_handles", "tw_ticker_filter"):
            _saved = st.session_state.get(f"_saved_{_k}")
            if _saved is not None:
                st.session_state[_k] = _saved
        st.rerun()

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# FILTER-LEISTE
# ══════════════════════════════════════════════════════════════════════════════

# Session-State für eigene Twitter-Accounts
if "custom_tw_handles" not in st.session_state:
    st.session_state["custom_tw_handles"] = []

# tw_selected = Daten-Key (unabhängig vom Widget-Key)
all_tw_options = (
    [a["handle"] for a in TWITTER_ACCOUNTS]
    + st.session_state["custom_tw_handles"]
)
if "tw_selected" not in st.session_state:
    st.session_state["tw_selected"] = all_tw_options[:]
# Nur gültige Handles behalten (falls Options sich geändert haben)
tw_filter_current: List[str] = [
    h for h in st.session_state["tw_selected"] if h in all_tw_options
] or all_tw_options[:]

# ── FILTER-LEISTE: 2 Spalten, passend zu Content darunter ────────────────────
ctrl_left, ctrl_right = st.columns([1, 1], gap="medium")

with ctrl_left:
    # Sektor + Modus nebeneinander, dann Ticker-Input darunter
    cl1, cl2 = st.columns([2, 1.8])
    with cl1:
        sector_opts = ["Alle Sektoren"] + list(WATCHLIST.keys())
        sel_sector = st.selectbox(
            "Sektor",
            sector_opts,
            format_func=lambda s: (
                f"{SECTOR_ICONS.get(s, '📌')} {s.split('. ',1)[-1]}"
                if s != "Alle Sektoren" else "🌐 Alle Sektoren"
            ),
            key="sector",
            label_visibility="collapsed",
        )
    with cl2:
        mode = st.radio(
            "Modus",
            ["🏷️ Ticker-News", "🗂️ Sektor-News"],
            horizontal=True,
            key="mode",
            label_visibility="collapsed",
        )
    extra_ticker_input = st.text_input(
        "Eigene Ticker",
        placeholder="🏷️ Ticker: AAPL, TSLA, AMZN … (kommagetrennt — ersetzt Watchlist)",
        key="extra_tickers",
        label_visibility="collapsed",
        disabled=("🗂️" in mode),
    )

with ctrl_right:
    # Twitter-Accounts + Handle hinzufügen
    cr1, cr2, cr3 = st.columns([4.2, 1.8, 0.6])
    with cr1:
        # Widget-Key "tw_sel_widget" — getrennt vom Daten-Key "tw_selected"
        tw_filter = st.multiselect(
            "X-Accounts",
            all_tw_options,
            default=tw_filter_current,
            format_func=lambda h: next(
                (f"{a['icon']} @{h}" for a in TWITTER_ACCOUNTS if a["handle"] == h),
                f"🐦 @{h}",
            ),
            key="tw_sel_widget",
            label_visibility="collapsed",
        )
        # Auswahl sofort in Daten-Key zurückschreiben
        st.session_state["tw_selected"] = tw_filter
    with cr2:
        new_handle = st.text_input(
            "Handle",
            placeholder="🐦 @handle hinzufügen",
            key="new_tw_handle",
            label_visibility="collapsed",
        )
    with cr3:
        if st.button("➕", key="add_tw_btn", use_container_width=True):
            h = new_handle.strip().lstrip("@").strip()
            if h and h not in all_tw_options:
                st.session_state["custom_tw_handles"].append(h)
                # Neuen Handle zu Daten-Key hinzufügen (nicht Widget-Key)
                st.session_state["tw_selected"] = tw_filter_current + [h]
                st.rerun()
    # Ticker-Filter für Twitter
    tw_ticker_input = st.text_input(
        "X-Ticker-Filter",
        placeholder="🏷️ X-Posts filtern: AAPL, NVDA … (kommagetrennt)",
        key="tw_ticker_filter",
        label_visibility="collapsed",
    )

custom_extra_tickers = (
    [t.strip().upper() for t in extra_ticker_input.split(",") if t.strip()]
    if "🏷️" in mode else []
)

# Twitter-Ticker-Filter: welche Symbole sollen in X-Posts gesucht werden?
tw_ticker_symbols: List[str] = [
    t.strip().upper().lstrip("$")
    for t in tw_ticker_input.split(",")
    if t.strip()
]

# ══════════════════════════════════════════════════════════════════════════════
# ALLE DATEN PARALLEL LADEN
# ══════════════════════════════════════════════════════════════════════════════

# Watchlist-Tickers bestimmen
if sel_sector == "Alle Sektoren":
    sector_tickers = ALL_TICKERS[:12]
else:
    sector_tickers = WATCHLIST.get(sel_sector, [])[:10]

if "🏷️" in mode:
    tickers_to_load = custom_extra_tickers[:8] if custom_extra_tickers else sector_tickers[:8]
else:
    tickers_to_load = []

# Accounts für Parallel-Fetch
sel_accounts = [
    a for a in TWITTER_ACCOUNTS if a["handle"] in tw_filter_current
] + [
    {"handle": h, "icon": "🐦", "color": "#1d9bf0", "label": "X"}
    for h in st.session_state["custom_tw_handles"]
    if h in tw_filter_current
]

with st.spinner("Lade alle Feeds parallel…"):
    # ── Börsennews-Quellen ────────────────────────────────────────────────────
    BOERSE_FEEDS = [
        # Mainstream Finanz
        ("https://finance.yahoo.com/news/rssindex",                                              5, "Yahoo Finance"),
        ("https://feeds.marketwatch.com/marketwatch/topstories/",                                5, "MarketWatch"),
        ("https://www.investing.com/rss/news.rss",                                               5, "Investing.com"),
        ("https://feeds.a.dj.com/rss/RSSMarketsMain.xml",                                        4, "WSJ Markets"),
        ("https://www.cnbc.com/id/100003114/device/rss/rss.html",                                4, "CNBC Markets"),
        ("https://feeds.bloomberg.com/markets/news.rss",                                         4, "Bloomberg"),
        # Alternative / unabhängig
        ("https://www.zerohedge.com/fullrss2.xml",                                               4, "ZeroHedge"),
        ("https://thestreet.com/.rss/full",                                                      4, "TheStreet"),
        ("https://seekingalpha.com/feed.xml",                                                    4, "Seeking Alpha"),
        ("https://www.fool.com/feeds/index.aspx",                                                3, "Motley Fool"),
        # Google News Queries
        ("https://news.google.com/rss/search?q=stock+market+S%26P500+earnings+when:2d"
         "&hl=en-US&gl=US&ceid=US:en",                                                           6, "Google News"),
        ("https://news.google.com/rss/search?q=options+trading+IV+volatility+when:2d"
         "&hl=en-US&gl=US&ceid=US:en",                                                           4, "Google News"),
    ]

    # ── Geopolitik/Makro-Quellen ──────────────────────────────────────────────
    GEO_FEEDS = [
        # Mainstream
        ("https://feeds.bbci.co.uk/news/world/rss.xml",                                          5, "BBC World"),
        ("https://feeds.bbci.co.uk/news/business/rss.xml",                                       4, "BBC Business"),
        ("https://feeds.reuters.com/reuters/businessNews",                                        5, "Reuters Business"),
        ("https://feeds.reuters.com/Reuters/worldNews",                                           5, "Reuters World"),
        ("https://rss.nytimes.com/services/xml/rss/nyt/World.xml",                               4, "NYT World"),
        ("https://www.ft.com/?format=rss",                                                        4, "Financial Times"),
        # Alternative
        ("https://www.zerohedge.com/fullrss2.xml",                                               3, "ZeroHedge"),
        ("https://www.rt.com/rss/business/",                                                      3, "RT Business"),
        ("https://sputnikglobe.com/export/rss2/archive/index.xml",                                3, "Sputnik"),
        ("https://news.google.com/rss/search?q=geopolitics+economy+war+sanctions+when:2d"
         "&hl=en-US&gl=US&ceid=US:en",                                                           5, "Google News"),
        ("https://news.google.com/rss/search?q=fed+inflation+recession+rates+macro+when:2d"
         "&hl=en-US&gl=US&ceid=US:en",                                                           5, "Google News"),
        ("https://news.google.com/rss/search?q=oil+opec+energy+commodity+when:2d"
         "&hl=en-US&gl=US&ceid=US:en",                                                           4, "Google News"),
    ]

    with ThreadPoolExecutor(max_workers=30) as pool:
        # Stock news
        stk_futures = {pool.submit(_stock_news, t): t for t in tickers_to_load}
        # Twitter
        tw_futures  = {pool.submit(_twitter, a["handle"], 4): a["handle"]
                       for a in sel_accounts}
        # Börsennews — alle Quellen parallel
        boerse_futures = [pool.submit(_rss, url, n, src) for url, n, src in BOERSE_FEEDS]
        # Geo/Makro — alle Quellen parallel
        geo_futures    = [pool.submit(_rss, url, n, src) for url, n, src in GEO_FEEDS]
        earn_fut       = pool.submit(_earnings)

        # Sektor-News (Modus B) — Haupt + Fallback-Query
        if "🗂️" in mode:
            q_main = SECTOR_SEARCH.get(
                sel_sector, "S&P500 stock market sectors options trading"
            ) if sel_sector != "Alle Sektoren" else "S&P500 stock market sectors options trading"
            # Fallback: kürzere Query ohne Ticker-Namen
            q_short = sel_sector.split("(")[-1].rstrip(")").strip() + " stocks news" \
                      if sel_sector != "Alle Sektoren" else "stock market investing"
            base = "https://news.google.com/rss/search?hl=en-US&gl=US&ceid=US:en&q="
            sec_fut      = pool.submit(_rss, base + requests.utils.quote(q_main),  14, "Google News")
            sec_fut_back = pool.submit(_rss, base + requests.utils.quote(q_short),  8, "Google News")
        else:
            sec_fut      = None
            sec_fut_back = None

        # Ergebnisse sammeln
        stk_news: Dict[str, List[Dict]] = {}
        for f in as_completed(stk_futures):
            t = stk_futures[f]
            try:
                stk_news[t] = f.result()
            except Exception:
                stk_news[t] = []

        tw_posts: Dict[str, List[Dict]] = {}
        for f in as_completed(tw_futures):
            h = tw_futures[f]
            try:
                tw_posts[h] = f.result()
            except Exception:
                tw_posts[h] = []

        boerse_all: List[Dict] = []
        for f in boerse_futures:
            try:
                boerse_all.extend(f.result())
            except Exception:
                pass

        geo_all: List[Dict] = []
        for f in geo_futures:
            try:
                geo_all.extend(f.result())
            except Exception:
                pass

        earnings       = earn_fut.result()
        sec_items_main = sec_fut.result()      if sec_fut      else []
        sec_items_back = sec_fut_back.result() if sec_fut_back else []
        # Haupt + Fallback kombinieren, Duplikate werden in _enrich entfernt
        sec_items = sec_items_main + sec_items_back

# ══════════════════════════════════════════════════════════════════════════════
# HILFSFUNKTION: Relevanz-Score auf Item setzen + dedup
# ══════════════════════════════════════════════════════════════════════════════

def _enrich(items: List[Dict], ticker_key: str = "",
            max_hours: float = 168.0) -> List[Dict]:
    """Score, Summary, Tags, Richtung und betroffene Tickers für jeden Artikel.
    Filtert Artikel älter als max_hours (Standard 7 Tage) heraus.
    Sortiert: Aktualität × Relevanz kombiniert — neue, relevante Artikel zuerst.
    """
    seen: set = set()
    out: List[Dict] = []
    for it in items:
        k = it.get("title", "")[:55].lower()
        if k in seen:
            continue
        seen.add(k)
        # Alters-Filter: zu alte Artikel komplett rauswerfen
        age = _age_hours(it)
        if age > max_hours:
            continue
        title = it.get("title", "")
        desc  = it.get("desc",  "")
        tkr   = it.get(ticker_key, "") if ticker_key else ""
        raw_desc = _clean(desc, 220)
        rel_score = _relevance_score(title, desc, tkr)
        # Aktualitäts-Bonus: jede Stunde weniger = +1 Punkt (max 72 Punkte Bonus)
        freshness_bonus = max(0, 72 - int(age))
        it["_score"]     = rel_score + freshness_bonus
        it["_relevance"] = _relevance(title, desc, tkr)
        it["_affected"]  = _find_affected_tickers(title, desc)
        it["_tags"]      = _extract_tags(title, desc)
        it["_direction"] = _impact_direction(title, desc)
        it["_summary"]   = raw_desc if raw_desc and raw_desc.lower()[:30] != title.lower()[:30] else ""
        out.append(it)
    out.sort(key=lambda x: (x["_score"], _sort_key(x)), reverse=True)
    return out


# ══════════════════════════════════════════════════════════════════════════════
# DATEN VORBEREITEN
# ══════════════════════════════════════════════════════════════════════════════

# Watchlist
all_stock_items: List[Dict] = []
if "🏷️" in mode and stk_news:
    for tkr, items in stk_news.items():
        for it in items:
            it["_ticker"] = tkr
            all_stock_items.append(it)
elif "🗂️" in mode and sec_items:
    all_stock_items = sec_items

# Watchlist / Sektor: stufenweiser Alters-Fallback 3d → 7d → 30d → alle
def _enrich_with_fallback(items: List[Dict], ticker_key: str = "") -> List[Dict]:
    for max_h in (72, 168, 720, 99999):
        result = _enrich(items, ticker_key=ticker_key, max_hours=max_h)
        if result:
            return result
    return []

enriched_watch = _enrich_with_fallback(all_stock_items, ticker_key="_ticker") if all_stock_items else []

# Börsennews: max 3 Tage
enriched_boerse = _enrich(boerse_all, max_hours=72)

# Geopolitik/Makro: max 3 Tage
enriched_geo = _enrich(geo_all, max_hours=72)

# Twitter
all_tweets: List[Dict] = []
for a in sel_accounts:
    acc_info = next((x for x in TWITTER_ACCOUNTS if x["handle"] == a["handle"]), a)
    for post in tw_posts.get(a["handle"], []):
        post["_acc"] = acc_info
        all_tweets.append(post)
enriched_tw = _enrich(all_tweets)

# ── Twitter Ticker-Filter ──────────────────────────────────────────────────
if tw_ticker_symbols:
    def _tweet_mentions(item: Dict, symbols: List[str]) -> bool:
        """Prüft ob ein Tweet einen der Ticker-Symbole nennt."""
        # 1. Bereits gefundene Affected-Tickers
        affected = item.get("_affected", [])
        for sym in symbols:
            if sym in affected:
                return True
        # 2. Volltext-Suche: $TICKER, (TICKER), :TICKER, oder als Wort
        text = " " + (item.get("title", "") + " " + item.get("desc", "")).upper() + " "
        for sym in symbols:
            if (f"${sym}" in text or f" {sym} " in text
                    or f"({sym})" in text or f":{sym}" in text):
                return True
        return False
    enriched_tw = [it for it in enriched_tw if _tweet_mentions(it, tw_ticker_symbols)]


def _render_cards(enriched: List[Dict], cat_color: str, cat_label_default: str,
                  n: int = 8, twitter_mode: bool = False) -> str:
    """Rendert n Karten als HTML-String."""
    html = ""
    for it in enriched[:n]:
        if twitter_mode:
            acc   = it.get("_acc", {"icon": "🐦", "handle": "unknown",
                                    "color": "#1d9bf0", "label": "X"})
            raw   = it.get("title") or it.get("desc", "")
            title = (raw[:217] + "…") if len(raw) > 220 else raw
            desc  = it.get("desc", "")
            c_color, c_label, src = acc["color"], acc["label"], f"{acc['icon']} @{acc['handle']}"
            summ  = _clean(desc, 180) if desc[:30] != title[:30] else ""
        else:
            title   = it["title"]
            c_color = cat_color
            c_label = cat_label_default
            src     = it.get("source", "")
            summ    = it["_summary"]
            # Geo: Makro vs Geo Label
            if cat_label_default == "Geo":
                is_biz  = it.get("source", "") in ("BBC Business", "BBC Wirtschaft")
                c_color = CAT_COLOR["makro"] if is_biz else CAT_COLOR["geo"]
                c_label = "Makro" if is_biz else "Geo"

        html += _feed_card(
            title=title,
            link=it.get("link", "#"),
            source=src,
            dt=it.get("dt"),
            cat_color=c_color,
            cat_label=c_label,
            summary=summ,
            relevance=it["_relevance"],
            affected=it["_affected"],
            tags=it["_tags"],
            extra_badge=it.get("_ticker", "") if not twitter_mode else "",
        )
    return html


# ══════════════════════════════════════════════════════════════════════════════
# LAYOUT: ZEILE 1 — Watchlist (links) | Twitter mit Controls (rechts)
# ══════════════════════════════════════════════════════════════════════════════
col_watch, col_tw = st.columns([1, 1], gap="medium")

with col_watch:
    wlabel = (f"Watchlist · {sel_sector.split('. ',1)[-1][:25]}"
              if sel_sector != "Alle Sektoren" else "Watchlist · Top Tickers")
    w_html = _section_title("📊", wlabel, CAT_COLOR["watchlist"], len(enriched_watch[:8]))
    if enriched_watch:
        w_html += _render_cards(enriched_watch, CAT_COLOR["watchlist"], "Watchlist", n=8)
    elif all_stock_items:
        w_html += ("<div style='padding:20px 14px;color:#555;font-size:0.76rem;"
                   "font-family:sans-serif;line-height:1.6'>"
                   "⏳ Keine Nachrichten der letzten 7 Tage gefunden.<br>"
                   "Ältere Artikel werden ausgeblendet — bitte anderen Sektor oder Ticker wählen.</div>")
    else:
        w_html += ("<div style='padding:20px;text-align:center;color:#333;"
                   "font-size:0.76rem;font-family:sans-serif'>"
                   "Kein Sektor / Ticker ausgewählt</div>")
    st.html(f"<div style='background:#0c0c0c;border-radius:10px;overflow:hidden'>{w_html}</div>")

with col_tw:
    if tw_ticker_symbols:
        tw_section_label = f"X · {' · '.join(tw_ticker_symbols)}"
    else:
        tw_section_label = "Finanzprofis auf X"
    tw_html = _section_title("𝕏", tw_section_label,
                              CAT_COLOR["twitter"], len(enriched_tw[:8]))
    if enriched_tw:
        tw_html += _render_cards(enriched_tw, CAT_COLOR["twitter"], "X",
                                 n=8, twitter_mode=True)
    elif tw_ticker_symbols:
        syms_str = ", ".join(tw_ticker_symbols)
        tw_html += (f"<div style='padding:20px 14px;color:#555;font-size:0.76rem;"
                    f"font-family:sans-serif;line-height:1.6'>"
                    f"Keine Tweets zu <b style='color:#d4a843'>{syms_str}</b> gefunden.<br>"
                    f"Ticker-Filter entfernen oder andere Accounts auswählen.</div>")
    else:
        tw_html += ("<div style='padding:20px;text-align:center;color:#333;"
                    "font-size:0.76rem;font-family:sans-serif'>"
                    "Keine X-Accounts ausgewählt</div>")
    st.html(f"<div style='background:#0c0c0c;border-radius:10px;overflow:hidden'>{tw_html}</div>")

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# ZEILE 2 — Börsennews (links) | Geopolitik & Makro (rechts)
# ══════════════════════════════════════════════════════════════════════════════
col_boe, col_geo = st.columns([1, 1], gap="medium")

with col_boe:
    b_html = _section_title("📈", "Börsennews", CAT_COLOR["boerse"], len(enriched_boerse[:7]))
    b_html += _render_cards(enriched_boerse, CAT_COLOR["boerse"], "Börse", n=7)
    st.html(f"<div style='background:#0c0c0c;border-radius:10px;overflow:hidden'>{b_html}</div>")

with col_geo:
    g_html = _section_title("🌍", "Geopolitik & Wirtschaft", CAT_COLOR["geo"], len(enriched_geo[:7]))
    g_html += _render_cards(enriched_geo, CAT_COLOR["geo"], "Geo", n=7)
    st.html(f"<div style='background:#0c0c0c;border-radius:10px;overflow:hidden'>{g_html}</div>")

st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# ZEILE 3 — Earnings-Kalender (volle Breite)
# ══════════════════════════════════════════════════════════════════════════════
today = datetime.now().date()
earn_rows = _section_title("🗓️", "Earnings — nächste 14 Tage", "#8b5cf6", len(earnings))

if earnings:
    # 3-spaltige Grid-Darstellung
    cols_per_row = 3
    earn_rows += "<div style='display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:#111'>"
    for e in earnings:
        d = e["date"]
        if hasattr(d, "date"):
            d = d.date()
        days   = (d - today).days
        ticker = e["ticker"]

        if days < 0:    bc, bl = "#333",    "–"
        elif days == 0: bc, bl = "#f59e0b", "🔴 HEUTE"
        elif days == 1: bc, bl = "#ef4444", "morgen"
        elif days <= 5: bc, bl = "#f97316", f"in {days}T"
        else:           bc, bl = "#3b82f6", d.strftime("%d.%m.")

        eps = ""
        if e.get("eps"):
            try:
                eps = f"EPS ${float(e['eps']):.2f}"
            except Exception:
                pass

        earn_rows += (
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"padding:8px 12px;background:#0c0c0c;font-family:sans-serif'>"
            f"<span style='font-family:monospace;font-size:0.84rem;"
            f"font-weight:700;color:#d4a843'>{ticker}</span>"
            f"<span style='font-size:0.67rem;color:#555'>{eps}</span>"
            f"<span style='font-size:0.72rem;font-weight:700;color:{bc}'>{bl}</span>"
            f"</div>"
        )
    earn_rows += "</div>"
else:
    earn_rows += ("<div style='padding:14px;text-align:center;color:#333;"
                  "font-size:0.72rem'>Keine Earnings in 14 Tagen erkannt</div>")

st.html(f"<div style='background:#0c0c0c;border-radius:10px;overflow:hidden'>{earn_rows}</div>")

# ══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ══════════════════════════════════════════════════════════════════════════════
st.html("""
<div style='margin-top:12px;padding:8px 14px;background:#080808;border-radius:6px;
     display:flex;justify-content:space-between;flex-wrap:wrap;gap:4px'>
  <span style='font-size:0.6rem;color:#333;font-family:sans-serif'>
    Quellen: BBC News · Yahoo Finance · Google News RSS · nitter.net/X · yfinance
    · ⏱ Aktualisierung: News 30min · Stocks 15min · Earnings 1h
  </span>
  <span style='font-size:0.6rem;color:#222;font-family:sans-serif'>
    ⚠️ Keine Anlageberatung · Stillhalter AI App
  </span>
</div>
""")
