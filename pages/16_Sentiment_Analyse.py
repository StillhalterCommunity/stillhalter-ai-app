"""
Stillhalter AI App — Sentiment Analyse v2
Chris Camillo Social Arbitrage: Virale Trends automatisch entdecken →
Produkte identifizieren → Aktien mappen → Einpreisung bewerten.

Quellen: Reddit (hot/rising/new) · Google Trends · StockTwits · Product Hunt · Hacker News
"""

from __future__ import annotations
import re
import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(
    page_title="Sentiment Analyse · Stillhalter AI App",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

# ══════════════════════════════════════════════════════════════════════════════
# BRAND → TICKER DATENBANK (erweitert)
# ══════════════════════════════════════════════════════════════════════════════
BRAND_TICKER: dict[str, str | None] = {
    # ── Consumer Tech ─────────────────────────────────────────────────────────
    "apple":        "AAPL",  "iphone":       "AAPL",  "airpods":    "AAPL",
    "apple watch":  "AAPL",  "macbook":      "AAPL",  "ipad":       "AAPL",
    "vision pro":   "AAPL",  "apple vision": "AAPL",
    "nvidia":       "NVDA",  "geforce":      "NVDA",  "rtx":        "NVDA",
    "blackwell":    "NVDA",  "h100":         "NVDA",  "b200":       "NVDA",
    "amd":          "AMD",   "ryzen":        "AMD",   "radeon":     "AMD",
    "intel":        "INTC",
    "meta":         "META",  "instagram":    "META",  "quest":      "META",
    "threads":      "META",  "ray-ban meta": "META",
    "google":       "GOOGL", "pixel":        "GOOGL", "gemini":     "GOOGL",
    "waymo":        "GOOGL", "google maps":  "GOOGL",
    "microsoft":    "MSFT",  "xbox":         "MSFT",  "copilot":    "MSFT",
    "azure":        "MSFT",  "github":       "MSFT",  "surface":    "MSFT",
    "sony":         "SONY",  "playstation":  "SONY",  "ps5":        "SONY",
    "nintendo":     "NTDOY", "switch":       "NTDOY",
    "amazon":       "AMZN",  "prime video":  "AMZN",  "kindle":     "AMZN",
    "aws":          "AMZN",  "alexa":        "AMZN",  "ring":       "AMZN",
    "netflix":      "NFLX",
    "spotify":      "SPOT",
    "arm":          "ARM",
    "palantir":     "PLTR",
    "openai":       None,    "chatgpt":      "MSFT",  "gpt-4":      "MSFT",
    "claude":       None,    "anthropic":    None,
    "perplexity":   None,
    "cursor":       None,
    "snowflake":    "SNOW",
    "salesforce":   "CRM",
    "servicenow":   "NOW",
    "datadog":      "DDOG",
    "crowdstrike":  "CRWD",
    "palo alto":    "PANW",
    "fortinet":     "FTNT",
    # ── Elektromobilität ──────────────────────────────────────────────────────
    "tesla":        "TSLA",  "model y":      "TSLA",  "model 3":    "TSLA",
    "cybertruck":   "TSLA",  "powerwall":    "TSLA",
    "rivian":       "RIVN",
    "lucid":        "LCID",
    "nio":          "NIO",
    "xpeng":        "XPEV",
    "byd":          "BYDDY",
    "ford":         "F",     "ford lightning":"F",    "mustang mach-e": "F",
    "gm":           "GM",    "chevy":        "GM",    "ultium":     "GM",
    # ── Getränke ──────────────────────────────────────────────────────────────
    "celsius":      "CELH",  "celsius energy":"CELH",
    "monster energy":"MNST", "monster":      "MNST",
    "dutch bros":   "BROS",
    "starbucks":    "SBUX",
    "coca-cola":    "KO",    "coke":         "KO",    "fairlife":   "KO",
    "pepsi":        "PEP",   "gatorade":     "PEP",   "lipton":     "PEP",
    "redbull":      None,
    "liquid death": None,
    "ag1":          None,    "athletic greens": None,
    # ── Food ──────────────────────────────────────────────────────────────────
    "chipotle":     "CMG",
    "mcdonald":     "MCD",   "mcdonalds":    "MCD",
    "domino":       "DPZ",   "dominos":      "DPZ",
    "shake shack":  "SHAK",
    "wingstop":     "WING",
    "yum brands":   "YUM",   "taco bell":    "YUM",   "kfc":        "YUM",
    "sweetgreen":   "SG",
    "cava":         "CAVA",
    "toast":        "TOST",  # Restaurant POS
    "instacart":    "CART",
    "doordash":     "DASH",
    "uber eats":    "UBER",
    # ── Gesundheit / GLP-1 / Fitness ─────────────────────────────────────────
    "ozempic":      "NVO",   "wegovy":       "NVO",   "semaglutide":"NVO",
    "mounjaro":     "LLY",   "tirzepatide":  "LLY",   "zepbound":   "LLY",
    "hims":         "HIMS",  "hims & hers":  "HIMS",
    "ro pharmacy":  None,
    "dexcom":       "DXCM",
    "insulet":      "PODD",  "omnipod":      "PODD",
    "garmin":       "GRMN",
    "whoop":        None,
    "oura":         None,    "oura ring":    None,
    "eight sleep":  None,
    "theragun":     "AFTR",  "therabody":    "AFTR",
    # ── Mode / Sport / Outdoor ────────────────────────────────────────────────
    "nike":         "NKE",   "air max":      "NKE",   "jordan":     "NKE",
    "adidas":       "ADDYY",
    "lululemon":    "LULU",  "lulu":         "LULU",  "align":      "LULU",
    "on running":   "ONON",  "on cloud":     "ONON",
    "hoka":         "DECK",  "ugg":          "DECK",  "teva":       "DECK",
    "skechers":     "SKX",
    "under armour": "UAA",
    "arcteryx":     "ADDYY",
    "patagonia":    None,
    "columbia":     "COLM",
    "brooks":       "BRKS",
    "new balance":  None,
    # ── Home / Lifestyle ──────────────────────────────────────────────────────
    "stanley":      "SWK",   "stanley cup":  "SWK",   "stanley tumbler": "SWK",
    "yeti":         "YETI",
    "peloton":      "PTON",
    "traeger":      "COOK",
    "dyson":        None,
    "roomba":       "IRB",
    "instant pot":  None,
    "nespresso":    None,
    "vitamix":      None,
    # ── Einzelhandel ──────────────────────────────────────────────────────────
    "costco":       "COST",
    "target":       "TGT",
    "walmart":      "WMT",
    "home depot":   "HD",
    "lowes":        "LOW",
    "tjmaxx":       "TJX",   "marshalls":    "TJX",
    "ross":         "ROST",
    "dollar general":"DG",
    "five below":   "FIVE",
    "shein":        None,
    "temu":         "PDD",   "pinduoduo":    "PDD",
    "shopify":      "SHOP",
    # ── Reise / Mobility ──────────────────────────────────────────────────────
    "airbnb":       "ABNB",
    "uber":         "UBER",
    "lyft":         "LYFT",
    "booking":      "BKNG",
    "expedia":      "EXPE",
    "delta":        "DAL",
    "united":       "UAL",
    "royal caribbean":"RCL",
    "carnival":     "CCL",
    # ── Fintech / Crypto ──────────────────────────────────────────────────────
    "coinbase":     "COIN",
    "robinhood":    "HOOD",
    "affirm":       "AFRM",
    "klarna":       None,
    "stripe":       None,
    "bitcoin":      "MSTR",  "btc":          "MSTR",
    "ethereum":     "COIN",  "eth":          "COIN",
    "blackrock bitcoin":"IBIT",
    # ── Entertainment / Media ─────────────────────────────────────────────────
    "disney":       "DIS",   "disney+":      "DIS",
    "warner":       "WBD",
    "roblox":       "RBLX",
    "unity":        "U",
    "epic games":   None,
    "take-two":     "TTWO",  "gta":          "TTWO",  "gta 6":      "TTWO",
    "activision":   "MSFT",  "call of duty": "MSFT",
    "ea":           "EA",    "ea sports":    "EA",
    # ── AI / Infrastructure ────────────────────────────────────────────────────
    "supermicro":   "SMCI",
    "marvell":      "MRVL",
    "broadcom":     "AVGO",
    "tsmc":         "TSM",
    "asml":         "ASML",
    "applied materials": "AMAT",
    "lam research": "LRCX",
}

# ── Bullish Demand-Signale ─────────────────────────────────────────────────────
BULLISH_KEYWORDS = [
    "sold out", "selling out", "obsessed", "addicted", "can't stop", "cant stop",
    "can't find", "cant find", "impossible to find", "viral", "trending",
    "everywhere", "amazing", "incredible", "game changer", "must have",
    "need this", "love this", "waiting list", "backorder", "pre-order",
    "blew up", "blowing up", "everyone has", "best purchase", "changed my life",
    "buying more", "shortage", "overwhelming", "selling fast", "hooked",
    "restocking", "10/10", "absolutely love", "can't believe how good",
    "just got mine", "finally arrived", "worth every penny", "underrated",
    "hidden gem", "life changing", "highly recommend", "best ever", "goat",
    "tier list", "top tier", "slept on", "criminally underrated",
    "fire", "hits different", "bussin", "no cap", "slay", "chef's kiss",
]
BEARISH_KEYWORDS = [
    "returning", "returned", "disappointed", "terrible", "broken", "defective",
    "recall", "recalled", "lawsuit", "avoid", "stay away", "worst ever",
    "waste of money", "overpriced", "switching away", "stopped using",
    "don't buy", "regret", "refund", "dangerous", "overrated", "scam",
    "garbage", "trash", "horrible", "fake", "knockoff",
]

# ── Subreddits (Early-Trend-Fokus) ────────────────────────────────────────────
SUBREDDITS_EARLY = [
    # Frühe Trend-Erkennung
    "all", "popular",
    "BuyItForLife", "Frugal", "Deals", "Flipping",
    "TikTokCringe", "tiktoktrends",
    "mildlyinteresting", "nottheonion",
    # Shopping / Consumer
    "amazonreviews", "ProductReviews", "onebag", "minimalism",
    "BeFrugal", "ShoppingDeals",
    # Sport / Fitness / Health
    "fitness", "running", "Wellbeing", "bodybuilding", "xxfitness",
    "loseit", "keto", "intermittentfasting", "veganfitness",
    "ultrarunning", "cycling", "swimming",
    # Fashion / Lifestyle
    "femalefashionadvice", "malefashionadvice", "streetwear", "sneakers",
    "frugalmalefashion", "rawdenim", "weddingplanning",
    # Food / Drink
    "EatCheapAndHealthy", "MealPrepSunday", "veganrecipes", "cocktails",
    "Coffee", "tea", "boba",
    # Tech / Gaming
    "gaming", "pcmasterrace", "hardware", "techsupport",
    "nvidia", "amd", "apple", "android",
    # Finance / Investing
    "personalfinance", "investing", "wallstreetbets", "stocks",
    # Home
    "homeimprovement", "DIY", "IKEA", "malelivingspace",
]

SUBREDDITS_CLASSIC = [
    "all", "BuyItForLife", "Frugal", "Deals",
    "fitness", "running", "bodybuilding",
    "femalefashionadvice", "malefashionadvice", "streetwear", "sneakers",
    "EatCheapAndHealthy", "loseit", "keto",
    "gaming", "pcmasterrace", "hardware",
    "personalfinance", "investing",
    "homeimprovement", "DIY",
]

# ══════════════════════════════════════════════════════════════════════════════
# DATEN-FUNKTIONEN
# ══════════════════════════════════════════════════════════════════════════════

def _find_brands(text: str) -> list[str]:
    """Findet Marken-Erwähnungen in einem Text."""
    text_lower = text.lower()
    return [brand for brand in BRAND_TICKER if brand in text_lower]


@st.cache_data(ttl=1800, show_spinner=False)
def _google_trending(country: str = "united_states") -> list[str]:
    """Aktuelle Google Trending Searches (pytrends)."""
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="en-US", tz=360, timeout=(10, 30))
        df = pt.trending_searches(pn=country)
        return df[0].tolist()[:30]
    except Exception:
        return []


@st.cache_data(ttl=900, show_spinner=False)
def _reddit_scan(
    subreddits: tuple[str, ...],
    min_score: int,
    sort_modes: tuple[str, ...] = ("hot",),
    limit: int = 30,
) -> list[dict]:
    """
    Scannt Reddit-Posts auf Produkt-Erwähnungen.
    sort_modes: "hot", "rising", "new", "top" (kombiniert für bessere Früherkennung)
    """
    import requests
    posts: list[dict] = []
    seen: set[str] = set()
    headers = {"User-Agent": "StillhalterApp/2.1"}

    for sub in subreddits:
        for sort in sort_modes:
            try:
                # Bei "new"/"rising" niedrigeren Score-Filter anwenden
                effective_min = max(1, min_score // 20) if sort in ("new", "rising") else min_score
                url = f"https://www.reddit.com/r/{sub}/{sort}.json?limit={limit}"
                r = requests.get(url, headers=headers, timeout=10)
                if r.status_code != 200:
                    continue
                for child in r.json().get("data", {}).get("children", []):
                    p = child.get("data", {})
                    pid = p.get("id", "")
                    if pid in seen or p.get("score", 0) < effective_min:
                        continue
                    seen.add(pid)
                    title = p.get("title", "")
                    text  = p.get("selftext", "")[:600]
                    combined = title + " " + text
                    brands = _find_brands(combined)
                    if not brands:
                        continue
                    bull = sum(1 for kw in BULLISH_KEYWORDS if kw in combined.lower())
                    bear = sum(1 for kw in BEARISH_KEYWORDS if kw in combined.lower())
                    posts.append({
                        "id":        pid,
                        "title":     title,
                        "score":     p.get("score", 0),
                        "comments":  p.get("num_comments", 0),
                        "subreddit": p.get("subreddit", sub),
                        "sort":      sort,
                        "url":       "https://reddit.com" + p.get("permalink", ""),
                        "brands":    brands,
                        "bull":      bull,
                        "bear":      bear,
                        "text":      text[:300],
                    })
            except Exception:
                continue
    return posts


@st.cache_data(ttl=600, show_spinner=False)
def _stocktwits_trending() -> list[dict]:
    """
    StockTwits Trending Tickers — zeigt welche Aktien gerade viral diskutiert werden.
    Kostenlose API, kein Key erforderlich.
    """
    import requests
    try:
        r = requests.get(
            "https://api.stocktwits.com/api/2/trending/symbols.json",
            timeout=10,
        )
        if r.status_code != 200:
            return []
        symbols = r.json().get("symbols", [])
        return [
            {
                "ticker":  s.get("symbol", ""),
                "title":   s.get("title", ""),
                "watchlist": s.get("watchlist_count", 0),
            }
            for s in symbols
        ]
    except Exception:
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def _product_hunt_feed() -> list[dict]:
    """
    Product Hunt RSS-Feed — neue virale Produkte/Startups.
    Kostenlos, kein API-Key nötig.
    """
    import requests, xml.etree.ElementTree as ET
    try:
        r = requests.get(
            "https://www.producthunt.com/feed",
            headers={"User-Agent": "StillhalterApp/2.1"},
            timeout=12,
        )
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = []
        for item in root.findall(".//item")[:20]:
            title = (item.findtext("title") or "").strip()
            desc  = (item.findtext("description") or "").strip()[:300]
            link  = (item.findtext("link") or "").strip()
            combined = title + " " + desc
            brands = _find_brands(combined)
            bull   = sum(1 for kw in BULLISH_KEYWORDS if kw in combined.lower())
            items.append({
                "title":  title,
                "desc":   desc,
                "link":   link,
                "brands": brands,
                "bull":   bull,
            })
        return items
    except Exception:
        return []


@st.cache_data(ttl=900, show_spinner=False)
def _hackernews_trending() -> list[dict]:
    """
    Hacker News Top Stories — Tech-Trend-Frühwarnung.
    Komplett kostenlos, offizielle Firebase-API.
    """
    import requests
    try:
        top_ids = requests.get(
            "https://hacker-news.firebaseio.com/v0/topstories.json",
            timeout=10,
        ).json()[:30]
        stories = []
        for sid in top_ids:
            try:
                s = requests.get(
                    f"https://hacker-news.firebaseio.com/v0/item/{sid}.json",
                    timeout=8,
                ).json()
                if not s or s.get("type") != "story":
                    continue
                title = s.get("title", "")
                url   = s.get("url", f"https://news.ycombinator.com/item?id={sid}")
                score = s.get("score", 0)
                brands = _find_brands(title)
                bull   = sum(1 for kw in BULLISH_KEYWORDS if kw in title.lower())
                stories.append({
                    "title":  title,
                    "url":    url,
                    "score":  score,
                    "brands": brands,
                    "bull":   bull,
                })
            except Exception:
                continue
        return stories
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def _reddit_comments(post_id: str, limit: int = 30) -> list[str]:
    """Lädt die Top-Kommentare eines Reddit-Posts."""
    import requests
    try:
        url = f"https://www.reddit.com/comments/{post_id}.json?limit={limit}&depth=1"
        r = requests.get(url, headers={"User-Agent": "StillhalterApp/2.1"}, timeout=10)
        if r.status_code != 200:
            return []
        comments = []
        for item in r.json():
            for child in item.get("data", {}).get("children", []):
                body = child.get("data", {}).get("body", "")
                if body and body != "[deleted]":
                    comments.append(body[:400])
        return comments[:30]
    except Exception:
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def _stock_info(ticker: str) -> dict:
    """Kurs + 30/90-Tage-Rendite via yfinance."""
    try:
        import yfinance as yf
        hist = yf.Ticker(ticker).history(period="3mo")
        if hist.empty or len(hist) < 5:
            return {}
        cur = float(hist["Close"].iloc[-1])
        p30 = float(hist["Close"].iloc[max(-22, -len(hist))])
        p90 = float(hist["Close"].iloc[0])
        r30 = (cur - p30) / p30 * 100
        r90 = (cur - p90) / p90 * 100

        if r90 > 35:
            label, color = "Stark eingepreist 🔴", "#ef4444"
            hint = f"Aktie +{r90:.0f}% in 90 Tagen — Markt kennt den Trend bereits"
        elif r90 > 15:
            label, color = "Teilweise eingepreist 🟡", "#f59e0b"
            hint = f"Aktie +{r90:.0f}% in 90 Tagen — Trend bekannt, noch Upside möglich"
        elif r90 > 0:
            label, color = "Kaum eingepreist ✅", "#22c55e"
            hint = f"Aktie nur +{r90:.0f}% — Trend noch nicht vollständig reflektiert"
        elif r90 > -15:
            label, color = "Nicht eingepreist ✅✅", "#22c55e"
            hint = f"Aktie seitwärts trotz Trend — frühes Signal!"
        else:
            label, color = "Gegenläufig 📉", "#8b5cf6"
            hint = f"Aktie -{abs(r90):.0f}% trotz Trend — Konträr-Signal prüfen"

        return {
            "price": cur, "r30": r30, "r90": r90,
            "label": label, "color": color, "hint": hint,
        }
    except Exception:
        return {}


def _aggregate_brands(
    posts: list[dict],
    trending_google: list[str],
    hn_stories: list[dict],
    ph_items: list[dict],
) -> list[dict]:
    """Aggregiert Marken-Erwähnungen aus allen Quellen und berechnet Trend-Score."""
    from collections import defaultdict
    brand_data: dict[str, dict] = defaultdict(lambda: {
        "posts": [], "subreddits": set(), "bull": 0, "bear": 0,
        "google": False, "hn": False, "ph": False,
        "reddit_score_sum": 0, "reddit_rising": 0,
    })

    # Reddit-Daten
    for post in posts:
        for brand in post["brands"]:
            bd = brand_data[brand]
            bd["posts"].append(post)
            bd["subreddits"].add(post["subreddit"])
            bd["bull"] += post["bull"]
            bd["bear"] += post["bear"]
            bd["reddit_score_sum"] += post["score"]
            if post.get("sort") in ("rising", "new"):
                bd["reddit_rising"] += 1

    # Google Trends ergänzen
    for term in trending_google:
        term_lower = term.lower()
        for brand in BRAND_TICKER:
            if brand in term_lower or term_lower in brand:
                brand_data[brand]["google"] = True

    # Hacker News ergänzen
    for story in hn_stories:
        for brand in story.get("brands", []):
            brand_data[brand]["hn"] = True
            if not any(p["title"] == story["title"] for p in brand_data[brand]["posts"]):
                brand_data[brand]["posts"].append({
                    "id": f"hn_{story.get('score',0)}",
                    "title": story["title"],
                    "score": story.get("score", 0),
                    "comments": 0,
                    "subreddit": "HackerNews",
                    "sort": "top",
                    "url": story.get("url", ""),
                    "brands": story["brands"],
                    "bull": story.get("bull", 0),
                    "bear": 0,
                    "text": "",
                })
            brand_data[brand]["bull"] += story.get("bull", 0)
            brand_data[brand]["reddit_score_sum"] += story.get("score", 0) * 2

    # Product Hunt ergänzen
    for item in ph_items:
        for brand in item.get("brands", []):
            brand_data[brand]["ph"] = True
            brand_data[brand]["bull"] += item.get("bull", 0) + 2  # PH = Bonus

    # Ticker zuordnen + Score berechnen
    results = []
    for brand, bd in brand_data.items():
        ticker = BRAND_TICKER.get(brand)
        n_posts = len(bd["posts"])
        if n_posts == 0:
            continue
        total_sig = bd["bull"] + bd["bear"]
        net_sentiment = (bd["bull"] - bd["bear"]) / max(total_sig, 1) * 100 if total_sig > 0 else 0
        trend_score = (
            n_posts * 10
            + bd["reddit_score_sum"] / 500
            + bd["bull"] * 5
            + bd["reddit_rising"] * 15          # Rising-Posts = stärkerer Bonus
            + (20 if bd["google"] else 0)
            + (15 if bd["hn"] else 0)
            + (10 if bd["ph"] else 0)
        )
        results.append({
            "brand":         brand,
            "ticker":        ticker,
            "n_posts":       n_posts,
            "subreddits":    sorted(bd["subreddits"]),
            "bull":          bd["bull"],
            "bear":          bd["bear"],
            "net_sentiment": round(net_sentiment, 1),
            "google":        bd["google"],
            "hn":            bd["hn"],
            "ph":            bd["ph"],
            "rising":        bd["reddit_rising"],
            "trend_score":   round(trend_score, 1),
            "top_posts":     sorted(bd["posts"], key=lambda x: x["score"], reverse=True)[:5],
        })
    return sorted(results, key=lambda x: x["trend_score"], reverse=True)


# ══════════════════════════════════════════════════════════════════════════════
# UI — HEADER
# ══════════════════════════════════════════════════════════════════════════════
h1, h2 = st.columns([1, 6])
with h1:
    st.markdown(get_logo_html("white", 36), unsafe_allow_html=True)
with h2:
    st.markdown(
        '<div class="sc-page-title">Sentiment Analyse</div>'
        '<div class="sc-page-subtitle">'
        'Chris Camillo Social Arbitrage · Virale Trends automatisch entdecken · '
        'Reddit · Google Trends · StockTwits · Product Hunt · Hacker News</div>',
        unsafe_allow_html=True,
    )
st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── Erklärung ──────────────────────────────────────────────────────────────────
with st.expander("💡 **Wie funktioniert die Sentiment Analyse? · Alle Datenquellen**", expanded=False):
    st.markdown("""
    **Chris Camillo** investiert nach der **„Social Arbitrage"** Methode:
    Erkenne Produkt-Trends auf Social Media, **bevor** die Wall Street davon weiß.

    ### Datenquellen im Überblick

    | Quelle | Was wird gescannt | Stärke |
    |--------|------------------|--------|
    | **Reddit Hot** | Beliebte Posts in Consumer-Subreddits | Bestätigte Trends, hohe Reichweite |
    | **Reddit Rising** | Posts die gerade an Upvotes gewinnen | **Frühe Signale!** Trend entsteht gerade |
    | **Reddit New** | Neueste Posts | Sehr frühe Signale, mehr Rauschen |
    | **Google Trends** | Trending Searches in Echtzeit | Massenmarkt-Nachfrage |
    | **StockTwits** | Trending Aktien der Community | Direkte Aktien-Momentum-Signale |
    | **Product Hunt** | Neu lansierte Produkte/Startups | Früheste Produktentdeckungen |
    | **Hacker News** | Tech-Community Top-Stories | Tech-Trends früh erkennen |

    ### Ablauf
    | Schritt | Was passiert |
    |---|---|
    | 1️⃣ Multi-Scan | Alle 7 Quellen werden gleichzeitig ausgewertet |
    | 2️⃣ Extrakt | App findet Marken- und Produkt-Erwähnungen |
    | 3️⃣ Mapping | Jedes Produkt wird einer börsennotierten Aktie zugeordnet |
    | 4️⃣ Einpreisung | Kursperformance zeigt, ob der Markt den Trend schon kennt |

    ### Beste Signale (Chris Camillo Methode)
    > *"sold out", "obsessed", "can't find it", "everywhere", "waiting list", "blew up"*

    **Kaum eingepreist + Bullish Sentiment = frühes Long-Signal** ✅
    **Stark eingepreist = Trend bekannt, Upside begrenzt** ⚠️

    ### Tipp: Early Detection Modus
    Aktiviere **Rising + New Posts** für früheste Trend-Signale — mehr Rauschen,
    aber Trends werden 2–5 Tage früher erkannt als über Hot-Posts.
    """)

# ── Tabs ───────────────────────────────────────────────────────────────────────
tab_auto, tab_manual, tab_stocktwits = st.tabs([
    "🔍 Auto-Scan (alle Quellen)",
    "🔎 Manuell suchen",
    "📊 StockTwits Trending",
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: AUTO-SCAN
# ══════════════════════════════════════════════════════════════════════════════
with tab_auto:

    # ── Scan-Einstellungen ─────────────────────────────────────────────────────
    with st.expander("⚙️ **Scan-Einstellungen**", expanded=True):
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            scan_mode = st.radio(
                "Scan-Modus",
                ["🎯 Klassisch (Hot)", "🚀 Early Detection (Hot + Rising)", "🔬 Maximale Breite (Hot + Rising + New)"],
                index=1,
                help="Early Detection findet Trends 2–5 Tage früher als Klassisch, aber mit mehr Rauschen",
            )
            if "Klassisch" in scan_mode:
                sort_modes = ("hot",)
                sub_list   = SUBREDDITS_CLASSIC
            elif "Early" in scan_mode:
                sort_modes = ("hot", "rising")
                sub_list   = SUBREDDITS_EARLY
            else:
                sort_modes = ("hot", "rising", "new")
                sub_list   = SUBREDDITS_EARLY

        with sc2:
            selected_subs = st.multiselect(
                "Subreddits",
                SUBREDDITS_EARLY,
                default=list(sub_list[:12]),
                help="Welche Subreddits sollen gescannt werden?",
            )
            min_score = st.number_input(
                "Min. Reddit Upvotes (Hot)", 5, 5000, 50, step=25,
                help="Nur Hot-Posts mit mindestens X Upvotes. Für Rising/New wird automatisch 1/20 angewendet.",
            )

        with sc3:
            trends_country = st.selectbox(
                "Google Trends Land",
                ["united_states", "germany", "united_kingdom", "canada", "australia"],
                help="Für welches Land sollen Google Trending Searches geladen werden?",
            )
            use_hn  = st.checkbox("🔶 Hacker News einbeziehen", value=True)
            use_ph  = st.checkbox("🔸 Product Hunt einbeziehen", value=True)

    # ── Scan-Button ─────────────────────────────────────────────────────────────
    scan_col, info_col = st.columns([2, 5])
    with scan_col:
        scan_btn = st.button(
            "🔍 Alle Quellen scannen",
            type="primary",
            use_container_width=True,
        )
    with info_col:
        st.markdown(
            "<div style='padding-top:8px;font-size:0.78rem;color:#555'>"
            "Reddit · Google Trends · StockTwits · Product Hunt · Hacker News "
            "· Kein API-Key · Ergebnisse 15 Min. gecacht"
            "</div>",
            unsafe_allow_html=True,
        )

    if not scan_btn and "sentiment_results" not in st.session_state:
        st.info(
            "👆 **'Alle Quellen scannen'** klicken — App scannt automatisch alle "
            "Social-Media-Quellen und findet virale Produkte mit Aktien-Ticker.",
            icon="🧭",
        )

    else:
        # ── Scan ausführen ─────────────────────────────────────────────────────
        if scan_btn or "sentiment_results" not in st.session_state:
            _progress = st.progress(0, text="📡 Scanne Reddit …")
            reddit_posts = _reddit_scan(
                tuple(selected_subs if selected_subs else ["all", "BuyItForLife"]),
                min_score,
                sort_modes=tuple(sort_modes),
            )
            _progress.progress(30, text="📈 Lade Google Trends …")
            google_trends = _google_trending(trends_country)
            _progress.progress(55, text="🔶 Hacker News …")
            hn_stories = _hackernews_trending() if use_hn else []
            _progress.progress(70, text="🔸 Product Hunt …")
            ph_items = _product_hunt_feed() if use_ph else []
            _progress.progress(90, text="🧮 Aggregiere Ergebnisse …")
            results = _aggregate_brands(reddit_posts, google_trends, hn_stories, ph_items)
            _progress.progress(100, text="✅ Fertig!")
            _progress.empty()

            st.session_state["sentiment_results"]      = results
            st.session_state["sentiment_google"]       = google_trends
            st.session_state["sentiment_reddit_count"] = len(reddit_posts)
            st.session_state["sentiment_hn_count"]     = len(hn_stories)
            st.session_state["sentiment_ph_count"]     = len(ph_items)
            st.session_state["sentiment_scan_time"]    = datetime.now().strftime("%H:%M")

        results       = st.session_state.get("sentiment_results", [])
        google_trends = st.session_state.get("sentiment_google", [])
        reddit_count  = st.session_state.get("sentiment_reddit_count", 0)
        hn_count      = st.session_state.get("sentiment_hn_count", 0)
        ph_count      = st.session_state.get("sentiment_ph_count", 0)
        scan_time     = st.session_state.get("sentiment_scan_time", "–")

        # ── Scan-Info ──────────────────────────────────────────────────────────
        mc = st.columns(5)
        mc[0].metric("Reddit Posts",   reddit_count)
        mc[1].metric("Google Trends",  len(google_trends))
        mc[2].metric("HN Stories",     hn_count)
        mc[3].metric("PH Launches",    ph_count)
        mc[4].metric("Trend-Produkte", len(results))

        if not results:
            st.warning(
                "**Keine Trend-Produkte gefunden.**\n\n"
                "**Mögliche Ursachen & Lösungen:**\n"
                "- 🔽 **Min. Upvotes senken** (aktuell zu hoch — versuche 10–50)\n"
                "- 📋 **Mehr Subreddits** hinzufügen (z.B. `all`, `popular`)\n"
                "- 🚀 **Early Detection Modus** aktivieren (Rising + New Posts)\n"
                "- ⏰ **Tageszeit**: Morgens (US-Zeit) gibt es mehr aktive Posts\n"
                "- 🔎 **Manuell suchen** (Tab 2) für gezieltes Trend-Tracking",
                icon="⚠️",
            )

        else:
            # ── Google Trends ──────────────────────────────────────────────────
            if google_trends:
                with st.expander(f"📈 Google Trending Searches ({len(google_trends)})", expanded=False):
                    gt_cols = st.columns(5)
                    for i, term in enumerate(google_trends):
                        matched = [b for b in BRAND_TICKER if b in term.lower() or term.lower() in b]
                        badge = f" → **{BRAND_TICKER[matched[0]]}**" if matched else ""
                        gt_cols[i % 5].markdown(f"· {term}{badge}")

            # ── Filter ────────────────────────────────────────────────────────
            f1, f2, f3 = st.columns([2, 2, 4])
            with f1:
                show_only_ticker = st.checkbox(
                    "Nur mit Aktien-Ticker",
                    value=True,
                    help="Nur Produkte anzeigen die einem börsennotierten Unternehmen zugeordnet sind",
                )
            with f2:
                show_only_bullish = st.checkbox(
                    "Nur Bullish-Signale",
                    value=False,
                    help="Nur Produkte mit positiver Stimmung (mehr Bull als Bear Keywords)",
                )
            with f3:
                show_only_not_priced = st.checkbox(
                    "Nur 'Kaum/Nicht eingepreist'",
                    value=False,
                    help="Nur Aktien anzeigen die noch nicht stark gestiegen sind (beste Einstiegs-Chance)",
                )

            filtered = results
            if show_only_ticker:
                filtered = [r for r in filtered if r["ticker"]]
            if show_only_bullish:
                filtered = [r for r in filtered if r["bull"] > r["bear"]]

            # Einpreisung laden wenn benötigt
            if show_only_not_priced:
                not_priced = []
                for r in filtered:
                    if r["ticker"]:
                        si = _stock_info(r["ticker"])
                        if si and si.get("r90", 999) <= 15:
                            not_priced.append(r)
                    else:
                        not_priced.append(r)
                filtered = not_priced

            st.markdown(
                f"<div style='font-size:0.78rem;color:#555;margin:8px 0'>"
                f"📦 <b>{len(filtered)}</b> Trend-Produkte · Scan {scan_time} Uhr"
                f"</div>",
                unsafe_allow_html=True,
            )

            # ── Ergebnis-Karten ────────────────────────────────────────────────
            for i, item in enumerate(filtered[:25]):
                brand  = item["brand"].title()
                ticker = item["ticker"]
                score  = item["trend_score"]
                nsubs  = len(item["subreddits"])
                bull   = item["bull"]
                bear   = item["bear"]
                net    = item["net_sentiment"]
                rising = item.get("rising", 0)

                # Quellen-Badges
                source_badges = []
                if item.get("google"):  source_badges.append("📈 Google")
                if item.get("hn"):      source_badges.append("🔶 HackerNews")
                if item.get("ph"):      source_badges.append("🔸 ProductHunt")
                if rising > 0:          source_badges.append(f"🚀 {rising}× Rising")

                # Stock-Daten
                sinfo: dict = _stock_info(ticker) if ticker else {}

                # Badge HTML
                ticker_badge = (
                    f'<span style="background:#d4a843;color:#000;font-weight:700;'
                    f'font-size:0.75rem;padding:2px 8px;border-radius:12px;margin-left:6px">'
                    f'{ticker}</span>'
                    if ticker else
                    '<span style="color:#444;font-size:0.75rem;margin-left:6px">kein Ticker</span>'
                )
                price_badge = ""
                if sinfo:
                    r90_color = "#22c55e" if sinfo["r90"] >= 0 else "#ef4444"
                    r90_sign  = "+" if sinfo["r90"] >= 0 else ""
                    price_badge = (
                        f'<span style="background:#111;border:1px solid #333;border-radius:20px;'
                        f'padding:2px 10px;font-size:0.78rem;color:#f0f0f0;margin-left:8px">'
                        f'${sinfo["price"]:.2f} '
                        f'<span style="color:{r90_color}">{r90_sign}{sinfo["r90"]:.0f}%</span>'
                        f'<span style="color:#444;font-size:0.68rem"> 90T</span>'
                        f'</span>'
                    )

                expander_icon = "🔥" if score > 60 else ("⚡" if rising > 0 else "📦")
                src_str = " · ".join(source_badges) if source_badges else ""

                with st.expander(
                    f"{expander_icon} {brand}  {ticker or ''}  "
                    f"{src_str}  · Score {score:.0f} · {item['n_posts']} Quellen",
                    expanded=False,
                ):
                    st.markdown(
                        f'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;'
                        f'margin-bottom:8px">'
                        f'<span style="font-size:1.05rem;font-weight:700;color:#f0f0f0">{brand}</span>'
                        f'{ticker_badge}{price_badge}'
                        + "".join(
                            f'<span style="background:#1a1a2a;color:#818cf8;font-size:0.7rem;'
                            f'padding:1px 7px;border-radius:10px;margin-left:4px">{b}</span>'
                            for b in source_badges
                        )
                        + f'</div>',
                        unsafe_allow_html=True,
                    )

                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("Quellen/Posts",    item["n_posts"])
                    m2.metric("Bullish Signale",  bull)
                    m3.metric("Bearish Signale",  bear)
                    m4.metric("Net Sentiment",    f"{net:+.0f}")

                    # Einpreisung
                    if sinfo:
                        r30c = "#22c55e" if sinfo["r30"] >= 0 else "#ef4444"
                        r90c = "#22c55e" if sinfo["r90"] >= 0 else "#ef4444"
                        st.markdown(
                            f'<div style="background:#0a0a0a;border:1px solid {sinfo["color"]}33;'
                            f'border-left:3px solid {sinfo["color"]};border-radius:8px;'
                            f'padding:10px 14px;margin:8px 0">'
                            f'<div style="font-size:0.85rem;font-weight:700;color:{sinfo["color"]};'
                            f'margin-bottom:4px">📊 Einpreisung: {sinfo["label"]}</div>'
                            f'<div style="font-size:0.78rem;color:#888">{sinfo["hint"]}</div>'
                            f'<div style="font-size:0.75rem;color:#555;margin-top:4px">'
                            f'30 Tage: <span style="color:{r30c}">{sinfo["r30"]:+.1f}%</span>'
                            f' &nbsp;|&nbsp; '
                            f'90 Tage: <span style="color:{r90c}">{sinfo["r90"]:+.1f}%</span>'
                            f'</div></div>',
                            unsafe_allow_html=True,
                        )

                    # Quellen
                    subs_html = " · ".join(f"r/{s}" if s != "HackerNews" else "HN" for s in item["subreddits"][:6])
                    st.markdown(
                        f'<div style="font-size:0.75rem;color:#444;margin-bottom:8px">'
                        f'Gefunden in: {subs_html}</div>',
                        unsafe_allow_html=True,
                    )

                    # Posts
                    top_posts = item["top_posts"]
                    if top_posts:
                        st.markdown("**📰 Quellen-Posts:**")
                        for p in top_posts[:4]:
                            title_hl = p["title"]
                            for kw in BULLISH_KEYWORDS:
                                if kw in title_hl.lower():
                                    title_hl = re.sub(
                                        re.escape(kw),
                                        f'<b style="color:#22c55e">{kw}</b>',
                                        title_hl, flags=re.IGNORECASE
                                    )
                            sub_label = p.get("subreddit", "")
                            sort_label = f" [{p.get('sort','hot')}]" if p.get("sort") != "hot" else ""
                            st.markdown(
                                f'<div style="background:#0e0e0e;border:1px solid #1e1e1e;'
                                f'border-radius:8px;padding:8px 12px;margin-bottom:5px">'
                                f'<div style="font-size:0.82rem;color:#d0d0d0">{title_hl}</div>'
                                f'<div style="font-size:0.72rem;color:#444;margin-top:3px">'
                                f'r/{sub_label}{sort_label} · ▲ {p["score"]:,} · 💬 {p["comments"]} · '
                                f'<a href="{p["url"]}" target="_blank" '
                                f'style="color:#d4a843;text-decoration:none">→ öffnen</a>'
                                f'</div></div>',
                                unsafe_allow_html=True,
                            )

                        # Kommentare on-demand
                        best_post = next((p for p in top_posts if not p["id"].startswith("hn_")), None)
                        if best_post:
                            if st.button(
                                f"💬 Top-Kommentare laden",
                                key=f"comments_{brand}_{i}",
                            ):
                                with st.spinner("Lade Kommentare …"):
                                    comments = _reddit_comments(best_post["id"])
                                if comments:
                                    bull_found = [kw for kw in BULLISH_KEYWORDS
                                                  if any(kw in c.lower() for c in comments)]
                                    bear_found = [kw for kw in BEARISH_KEYWORDS
                                                  if any(kw in c.lower() for c in comments)]
                                    if bull_found or bear_found:
                                        st.markdown(
                                            '<div style="font-size:0.78rem;margin:6px 0">'
                                            + "".join(
                                                f'<span style="background:#0a1a0a;color:#22c55e;'
                                                f'border-radius:4px;padding:1px 6px;margin:2px">{kw}</span>'
                                                for kw in bull_found
                                            )
                                            + "".join(
                                                f'<span style="background:#1a0a0a;color:#ef4444;'
                                                f'border-radius:4px;padding:1px 6px;margin:2px">{kw}</span>'
                                                for kw in bear_found
                                            )
                                            + "</div>",
                                            unsafe_allow_html=True,
                                        )
                                    for c in comments[:8]:
                                        st.markdown(
                                            f'<div style="background:#0e0e0e;border:1px solid #1a1a1a;'
                                            f'border-radius:6px;padding:7px 11px;margin-bottom:4px;'
                                            f'font-size:0.80rem;color:#bbb;line-height:1.5">{c}</div>',
                                            unsafe_allow_html=True,
                                        )

                    # Action Buttons
                    st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)
                    ab1, ab2, ab3 = st.columns(3)
                    if ticker:
                        with ab1:
                            if st.button(f"🔍 {ticker} im Scanner", key=f"scan_{brand}_{i}",
                                         use_container_width=True):
                                st.session_state["scan_ticker_prefill"] = ticker
                                st.switch_page("pages/04_Watchlist_Scanner.py")
                        with ab2:
                            if st.button(f"📊 {ticker} analysieren", key=f"anl_{brand}_{i}",
                                         use_container_width=True):
                                st.session_state["selected_ticker"] = ticker
                                st.switch_page("pages/03_Aktienanalyse.py")
                    with ab3 if ticker else ab1:
                        st.markdown(
                            f'<a href="https://finance.yahoo.com/quote/{ticker or ""}" '
                            f'target="_blank" style="display:block;text-align:center;'
                            f'background:#1a1a1a;border:1px solid #333;border-radius:8px;'
                            f'padding:5px;color:#d4a843;font-size:0.8rem;text-decoration:none">'
                            f'→ Yahoo Finance</a>' if ticker else "",
                            unsafe_allow_html=True,
                        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: MANUELL SUCHEN
# ══════════════════════════════════════════════════════════════════════════════
with tab_manual:
    st.markdown(
        "<div style='font-size:0.85rem;color:#888;margin-bottom:16px'>"
        "Gib einen Trend, ein Produkt oder eine Marke ein — App sucht Reddit nach "
        "aktuellen Posts und ordnet die passende Aktie zu."
        "</div>",
        unsafe_allow_html=True,
    )

    m_col1, m_col2 = st.columns([3, 1])
    with m_col1:
        manual_query = st.text_input(
            "Produkt / Trend / Marke suchen",
            placeholder="z.B. 'ozempic', 'on running', 'cybertruck', 'GLP-1', 'AI glasses' …",
            help="Freitext-Suche: App sucht Reddit nach Posts mit diesem Begriff",
        )
    with m_col2:
        manual_sort = st.selectbox(
            "Reddit sortieren nach",
            ["relevance", "new", "hot", "top"],
            index=0,
        )

    if manual_query and st.button("🔍 Suchen", type="primary"):
        import requests as _req

        @st.cache_data(ttl=300, show_spinner=False)
        def _reddit_search(query: str, sort: str) -> list[dict]:
            headers = {"User-Agent": "StillhalterApp/2.1"}
            posts = []
            try:
                url = f"https://www.reddit.com/search.json?q={query}&sort={sort}&limit=25&type=link"
                r = _req.get(url, headers=headers, timeout=12)
                if r.status_code == 200:
                    for child in r.json().get("data", {}).get("children", []):
                        p = child.get("data", {})
                        title = p.get("title", "")
                        text  = p.get("selftext", "")[:400]
                        combined = title + " " + text
                        brands = _find_brands(combined)
                        # Auch manuelle Query als Brand-Match prüfen
                        q_lower = query.lower()
                        for b, t in BRAND_TICKER.items():
                            if b in q_lower or q_lower in b:
                                if b not in brands:
                                    brands.append(b)
                        bull = sum(1 for kw in BULLISH_KEYWORDS if kw in combined.lower())
                        bear = sum(1 for kw in BEARISH_KEYWORDS if kw in combined.lower())
                        posts.append({
                            "id": p.get("id", ""),
                            "title": title,
                            "text": text[:200],
                            "score": p.get("score", 0),
                            "comments": p.get("num_comments", 0),
                            "subreddit": p.get("subreddit", ""),
                            "url": "https://reddit.com" + p.get("permalink", ""),
                            "brands": brands,
                            "bull": bull,
                            "bear": bear,
                            "sort": sort,
                        })
            except Exception:
                pass
            return posts

        with st.spinner(f"Suche Reddit nach '{manual_query}' …"):
            m_posts = _reddit_search(manual_query, manual_sort)

        if not m_posts:
            st.warning("Keine Ergebnisse. Versuche einen anderen Begriff oder Sort-Modus.")
        else:
            # Passende Ticker finden
            q_lower = manual_query.lower()
            direct_ticker = None
            for brand, tkr in BRAND_TICKER.items():
                if brand in q_lower or q_lower in brand:
                    direct_ticker = tkr
                    break

            # Metriken
            total_bull = sum(p["bull"] for p in m_posts)
            total_bear = sum(p["bear"] for p in m_posts)
            net_sent   = (total_bull - total_bear) / max(total_bull + total_bear, 1) * 100

            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Posts gefunden", len(m_posts))
            mc2.metric("Bullish Signale", total_bull)
            mc3.metric("Bearish Signale", total_bear)
            mc4.metric("Net Sentiment",   f"{net_sent:+.0f}%")

            # Ticker-Infos
            if direct_ticker:
                si = _stock_info(direct_ticker)
                if si:
                    r90c = "#22c55e" if si["r90"] >= 0 else "#ef4444"
                    st.markdown(
                        f'<div style="background:#0a0a0a;border:1px solid {si["color"]}44;'
                        f'border-left:3px solid {si["color"]};border-radius:10px;'
                        f'padding:12px 16px;margin:10px 0">'
                        f'<span style="background:#d4a843;color:#000;font-weight:700;'
                        f'font-size:0.85rem;padding:2px 10px;border-radius:12px">{direct_ticker}</span>'
                        f' <span style="font-size:0.85rem;color:#f0f0f0;margin-left:8px">'
                        f'${si["price"]:.2f}</span>'
                        f' <span style="color:{r90c};font-size:0.85rem">'
                        f'{si["r90"]:+.1f}% 90T</span>'
                        f'<div style="font-size:0.78rem;color:{si["color"]};margin-top:6px;font-weight:600">'
                        f'📊 Einpreisung: {si["label"]}</div>'
                        f'<div style="font-size:0.75rem;color:#666">{si["hint"]}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

            # Posts anzeigen
            st.markdown(f"**📰 {len(m_posts)} Reddit-Posts zu '{manual_query}':**")
            for p in m_posts[:15]:
                title_hl = p["title"]
                for kw in BULLISH_KEYWORDS:
                    if kw in title_hl.lower():
                        title_hl = re.sub(
                            re.escape(kw),
                            f'<b style="color:#22c55e">{kw}</b>',
                            title_hl, flags=re.IGNORECASE
                        )
                for kw in BEARISH_KEYWORDS:
                    if kw in title_hl.lower():
                        title_hl = re.sub(
                            re.escape(kw),
                            f'<b style="color:#ef4444">{kw}</b>',
                            title_hl, flags=re.IGNORECASE
                        )
                bull_dot = "🟢" if p["bull"] > 0 else ("🔴" if p["bear"] > 0 else "⚪")
                st.markdown(
                    f'<div style="background:#0e0e0e;border:1px solid #1e1e1e;'
                    f'border-radius:8px;padding:9px 13px;margin-bottom:5px">'
                    f'<div style="font-size:0.83rem;color:#d0d0d0">{bull_dot} {title_hl}</div>'
                    f'<div style="font-size:0.72rem;color:#444;margin-top:3px">'
                    f'r/{p["subreddit"]} · ▲ {p["score"]:,} · 💬 {p["comments"]} · '
                    f'<a href="{p["url"]}" target="_blank" '
                    f'style="color:#d4a843;text-decoration:none">→ öffnen</a>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: STOCKTWITS TRENDING
# ══════════════════════════════════════════════════════════════════════════════
with tab_stocktwits:
    st.markdown(
        "<div style='font-size:0.85rem;color:#888;margin-bottom:16px'>"
        "StockTwits zeigt welche Aktien die Community gerade am meisten diskutiert — "
        "direktes Momentum-Signal ohne Umweg über Produkte."
        "</div>",
        unsafe_allow_html=True,
    )

    if st.button("📊 StockTwits Trending laden", type="primary"):
        with st.spinner("Lade StockTwits Trending Tickers …"):
            st_tickers = _stocktwits_trending()
        st.session_state["stocktwits_data"] = st_tickers
        st.session_state["stocktwits_time"] = datetime.now().strftime("%H:%M")

    st_tickers = st.session_state.get("stocktwits_data", [])
    st_time    = st.session_state.get("stocktwits_time", "–")

    if not st_tickers:
        st.info(
            "👆 **'StockTwits Trending laden'** klicken — zeigt die meistdiskutierten "
            "Aktien der Trading-Community in Echtzeit.",
            icon="📊",
        )
    else:
        st.markdown(
            f"<div style='font-size:0.75rem;color:#444;margin-bottom:12px'>"
            f"✅ {len(st_tickers)} Trending Tickers · Stand {st_time} Uhr"
            f"</div>",
            unsafe_allow_html=True,
        )

        st_cols = st.columns(3)
        for i, sym in enumerate(st_tickers):
            ticker = sym.get("ticker", "")
            title  = sym.get("title", "")
            wl     = sym.get("watchlist", 0)
            if not ticker:
                continue

            sinfo = _stock_info(ticker)
            r90_str  = f"{sinfo['r90']:+.1f}%" if sinfo else "–"
            r90_col  = ("#22c55e" if sinfo.get("r90", 0) >= 0 else "#ef4444") if sinfo else "#888"
            price_str = f"${sinfo['price']:.2f}" if sinfo else "–"

            with st_cols[i % 3]:
                st.markdown(
                    f'<div style="background:#0e0e0e;border:1px solid #1e1e1e;'
                    f'border-radius:10px;padding:10px 14px;margin-bottom:8px">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center">'
                    f'<span style="background:#d4a843;color:#000;font-weight:700;'
                    f'font-size:0.9rem;padding:2px 10px;border-radius:10px">{ticker}</span>'
                    f'<span style="font-size:0.75rem;color:#444">👁 {wl:,}</span>'
                    f'</div>'
                    f'<div style="font-size:0.78rem;color:#888;margin-top:5px">{title}</div>'
                    f'<div style="font-size:0.85rem;color:#f0f0f0;margin-top:4px">'
                    f'{price_str} <span style="color:{r90_col}">{r90_str}</span>'
                    f' <span style="font-size:0.65rem;color:#444">90T</span></div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )

        # Sortierbare Tabelle
        if st_tickers:
            rows = []
            for sym in st_tickers:
                tkr = sym.get("ticker", "")
                si  = _stock_info(tkr) if tkr else {}
                rows.append({
                    "Ticker": tkr,
                    "Unternehmen": sym.get("title", ""),
                    "Watchlist": sym.get("watchlist", 0),
                    "Kurs": round(si.get("price", 0), 2) if si else None,
                    "30T %": round(si.get("r30", 0), 1) if si else None,
                    "90T %": round(si.get("r90", 0), 1) if si else None,
                    "Einpreisung": si.get("label", "–") if si else "–",
                })
            df_st = pd.DataFrame(rows)
            st.dataframe(
                df_st, use_container_width=True, hide_index=True, height=480,
                column_config={
                    "Watchlist": st.column_config.NumberColumn("👁 Watchlist", format="%d"),
                    "Kurs":      st.column_config.NumberColumn("Kurs", format="$%.2f"),
                    "30T %":     st.column_config.NumberColumn("30T %", format="%.1f%%"),
                    "90T %":     st.column_config.NumberColumn("90T %", format="%.1f%%"),
                },
            )

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    '<div style="font-size:0.72rem;color:#333;text-align:center">'
    'Quellen: Reddit JSON-API · Google Trends (pytrends) · StockTwits API · '
    'Product Hunt RSS · Hacker News Firebase API · Kursdaten: Yahoo Finance'
    '</div>',
    unsafe_allow_html=True,
)
