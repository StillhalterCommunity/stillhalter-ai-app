"""
Stillhalter AI App — Sentiment Analyse
Chris Camillo Social Arbitrage: Virale Trends automatisch entdecken →
Produkte identifizieren → Aktien mappen → Einpreisung bewerten.
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
# BRAND → TICKER DATENBANK
# ══════════════════════════════════════════════════════════════════════════════
BRAND_TICKER: dict[str, str | None] = {
    # ── Consumer Tech ─────────────────────────────────────────────────────────
    "apple":        "AAPL",  "iphone":     "AAPL",  "airpods":  "AAPL",
    "apple watch":  "AAPL",  "macbook":    "AAPL",  "ipad":     "AAPL",
    "nvidia":       "NVDA",  "geforce":    "NVDA",  "rtx":      "NVDA",
    "amd":          "AMD",   "ryzen":      "AMD",   "radeon":   "AMD",
    "intel":        "INTC",
    "meta":         "META",  "instagram":  "META",  "quest":    "META",
    "google":       "GOOGL", "pixel":      "GOOGL", "gemini":   "GOOGL",
    "microsoft":    "MSFT",  "xbox":       "MSFT",  "copilot":  "MSFT",
    "sony":         "SONY",  "playstation":"SONY",  "ps5":      "SONY",
    "nintendo":     "NTDOY", "switch":     "NTDOY",
    "amazon":       "AMZN",  "prime video":"AMZN",  "kindle":   "AMZN",
    "netflix":      "NFLX",
    "spotify":      "SPOT",
    "arm":          "ARM",
    "palantir":     "PLTR",
    # ── Elektromobilität ──────────────────────────────────────────────────────
    "tesla":        "TSLA",  "model y":    "TSLA",  "model 3":  "TSLA",
    "cybertruck":   "TSLA",
    "rivian":       "RIVN",
    "lucid":        "LCID",
    # ── Getränke ──────────────────────────────────────────────────────────────
    "celsius":      "CELH",  "celsius energy": "CELH",
    "monster energy":"MNST", "monster":    "MNST",
    "dutch bros":   "BROS",
    "starbucks":    "SBUX",
    "coca-cola":    "KO",    "coke":       "KO",
    "pepsi":        "PEP",
    # ── Food ──────────────────────────────────────────────────────────────────
    "chipotle":     "CMG",
    "mcdonald":     "MCD",   "mcdonalds":  "MCD",
    "domino":       "DPZ",   "dominos":    "DPZ",
    "shake shack":  "SHAK",
    "wingstop":     "WING",
    "yum brands":   "YUM",   "taco bell":  "YUM",   "kfc": "YUM",
    # ── Gesundheit / GLP-1 ────────────────────────────────────────────────────
    "ozempic":      "NVO",   "wegovy":     "NVO",   "semaglutide": "NVO",
    "mounjaro":     "LLY",   "tirzepatide":"LLY",   "zepbound": "LLY",
    "hims":         "HIMS",
    # ── Mode / Sport ──────────────────────────────────────────────────────────
    "nike":         "NKE",   "air max":    "NKE",   "jordan":   "NKE",
    "adidas":       "ADDYY",
    "lululemon":    "LULU",  "lulu":       "LULU",
    "on running":   "ONON",  "on cloud":   "ONON",
    "hoka":         "DECK",  "ugg":        "DECK",
    "skechers":     "SKX",
    "under armour": "UAA",
    # ── Home / Lifestyle ──────────────────────────────────────────────────────
    "stanley":      "SWK",   "stanley cup":"SWK",   "stanley tumbler": "SWK",
    "yeti":         "YETI",
    "peloton":      "PTON",
    "traeger":      "COOK",
    # ── Einzelhandel ──────────────────────────────────────────────────────────
    "costco":       "COST",
    "target":       "TGT",
    "walmart":      "WMT",
    "home depot":   "HD",
    # ── Reise / Mobility ──────────────────────────────────────────────────────
    "airbnb":       "ABNB",
    "uber":         "UBER",
    "lyft":         "LYFT",
    "booking":      "BKNG",
    # ── Fintech ───────────────────────────────────────────────────────────────
    "coinbase":     "COIN",
    "robinhood":    "HOOD",
    "affirm":       "AFRM",
    # ── Entertainment ─────────────────────────────────────────────────────────
    "disney":       "DIS",   "disney+":    "DIS",
    "warner":       "WBD",
    # ── Snowflake / Cloud ─────────────────────────────────────────────────────
    "snowflake":    "SNOW",
    "salesforce":   "CRM",
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
    "just got mine", "finally arrived", "worth every penny",
]
BEARISH_KEYWORDS = [
    "returning", "returned", "disappointed", "terrible", "broken", "defective",
    "recall", "recalled", "lawsuit", "avoid", "stay away", "worst ever",
    "waste of money", "overpriced", "switching away", "stopped using",
    "don't buy", "regret", "refund", "dangerous", "overrated",
]

# ── Subreddits für Consumer-Trend-Entdeckung ──────────────────────────────────
CONSUMER_SUBREDDITS = [
    "all",
    "BuyItForLife", "Frugal", "Deals",
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
        return df[0].tolist()[:25]
    except Exception:
        return []


@st.cache_data(ttl=900, show_spinner=False)
def _reddit_scan(subreddits: tuple[str, ...], min_score: int) -> list[dict]:
    """Scannt Reddit-Posts auf Produkt-Erwähnungen (nur Titel + Text, kein API-Key)."""
    import requests
    posts: list[dict] = []
    seen: set[str] = set()
    for sub in subreddits:
        try:
            url = f"https://www.reddit.com/r/{sub}/hot.json?limit=30"
            r = requests.get(url, headers={"User-Agent": "StillhalterApp/2.0"}, timeout=10)
            if r.status_code != 200:
                continue
            for child in r.json().get("data", {}).get("children", []):
                p = child.get("data", {})
                pid = p.get("id", "")
                if pid in seen or p.get("score", 0) < min_score:
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
def _reddit_comments(post_id: str, limit: int = 30) -> list[str]:
    """Lädt die Top-Kommentare eines Reddit-Posts."""
    import requests
    try:
        url = f"https://www.reddit.com/comments/{post_id}.json?limit={limit}&depth=1"
        r = requests.get(url, headers={"User-Agent": "StillhalterApp/2.0"}, timeout=10)
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
        cur    = float(hist["Close"].iloc[-1])
        p30    = float(hist["Close"].iloc[max(-22, -len(hist))])
        p90    = float(hist["Close"].iloc[0])
        r30    = (cur - p30) / p30 * 100
        r90    = (cur - p90) / p90 * 100

        if r90 > 35:
            label, color = "Stark eingepreist", "#ef4444"
            hint = f"Aktie +{r90:.0f}% in 90 Tagen — Markt kennt den Trend bereits"
        elif r90 > 15:
            label, color = "Teilweise eingepreist", "#f59e0b"
            hint = f"Aktie +{r90:.0f}% in 90 Tagen — Trend bereits bekannt, noch Upside möglich"
        elif r90 > 0:
            label, color = "Kaum eingepreist ✅", "#22c55e"
            hint = f"Aktie nur +{r90:.0f}% in 90 Tagen — Trend noch nicht reflektiert"
        elif r90 > -15:
            label, color = "Nicht eingepreist ✅", "#22c55e"
            hint = f"Aktie seitwärts/fallend trotz Trend — frühes Signal"
        else:
            label, color = "Gegenläufig 📉", "#8b5cf6"
            hint = f"Aktie -{abs(r90):.0f}% trotz Trend — Konträr-Signal prüfen"

        return {
            "price": cur, "r30": r30, "r90": r90,
            "label": label, "color": color, "hint": hint,
        }
    except Exception:
        return {}


def _aggregate_brands(posts: list[dict], trending_google: list[str]) -> list[dict]:
    """Aggregiert Marken-Erwähnungen und berechnet Trend-Score."""
    from collections import defaultdict
    brand_data: dict[str, dict] = defaultdict(lambda: {
        "posts": [], "subreddits": set(), "bull": 0, "bear": 0,
        "google": False, "reddit_score_sum": 0,
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

    # Google Trends ergänzen
    for term in trending_google:
        term_lower = term.lower()
        for brand in BRAND_TICKER:
            if brand in term_lower or term_lower in brand:
                brand_data[brand]["google"] = True

    # Ticker zuordnen + Score berechnen
    results = []
    for brand, bd in brand_data.items():
        ticker = BRAND_TICKER.get(brand)
        n_posts = len(bd["posts"])
        total_sig = bd["bull"] + bd["bear"]
        net_sentiment = (bd["bull"] - bd["bear"]) / max(total_sig, 1) * 100 if total_sig > 0 else 0
        trend_score = (
            n_posts * 10
            + bd["reddit_score_sum"] / 1000
            + bd["bull"] * 5
            + (20 if bd["google"] else 0)
        )
        results.append({
            "brand":          brand,
            "ticker":         ticker,
            "n_posts":        n_posts,
            "subreddits":     sorted(bd["subreddits"]),
            "bull":           bd["bull"],
            "bear":           bd["bear"],
            "net_sentiment":  round(net_sentiment, 1),
            "google":         bd["google"],
            "trend_score":    round(trend_score, 1),
            "top_posts":      sorted(bd["posts"], key=lambda x: x["score"], reverse=True)[:5],
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
        'Reddit · Google Trends · Produkt→Aktie → Einpreisung</div>',
        unsafe_allow_html=True,
    )
st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── Erklärung ──────────────────────────────────────────────────────────────────
with st.expander("💡 **Wie funktioniert die Sentiment Analyse?**", expanded=False):
    st.markdown("""
    **Chris Camillo** investiert nach der **„Social Arbitrage"** Methode:
    Erkenne Produkt-Trends auf Social Media, **bevor** die Wall Street davon weiß.

    **Der Ablauf dieser App:**

    | Schritt | Was passiert |
    |---|---|
    | 1️⃣ Scan | Reddit Hot-Posts + Google Trending Searches werden automatisch ausgewertet |
    | 2️⃣ Extrakt | App findet Marken- und Produkt-Erwähnungen in Titeln und Posts |
    | 3️⃣ Mapping | Jedes Produkt wird einer börsennotierten Aktie zugeordnet |
    | 4️⃣ Einpreisung | Kursperformance zeigt, ob der Markt den Trend schon kennt |

    **Bullish-Signale** (Chris Camillo sucht genau das):
    > *"sold out", "obsessed", "can't find it", "everywhere", "waiting list"*

    **Kaum eingepreist** = früher Einstieg möglich → Aktie noch nicht gestiegen
    **Stark eingepreist** = Trend bekannt, Upside begrenzt → eher vermeiden

    💡 **Tipp:** Beste Signale kommen von Produkten, die offline/im echten Leben
    viral gehen — während die Aktie noch seitwärts läuft.
    """)

# ── Scan-Einstellungen ─────────────────────────────────────────────────────────
with st.expander("⚙️ Scan-Einstellungen", expanded=False):
    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        selected_subs = st.multiselect(
            "Reddit Subreddits",
            CONSUMER_SUBREDDITS,
            default=["all", "BuyItForLife", "fitness", "femalefashionadvice", "gaming"],
            help="Welche Subreddits sollen nach Trend-Produkten gescannt werden?",
        )
    with sc2:
        min_score = st.number_input(
            "Min. Reddit Upvotes", 50, 10000, 200, step=50,
            help="Nur Posts mit mindestens dieser Anzahl Upvotes werden berücksichtigt",
        )
    with sc3:
        trends_country = st.selectbox(
            "Google Trends Land",
            ["united_states", "germany", "united_kingdom", "canada", "australia"],
            help="Für welches Land sollen Google Trending Searches geladen werden?",
        )

# ── Scan-Button ────────────────────────────────────────────────────────────────
st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
scan_col, info_col = st.columns([2, 5])
with scan_col:
    scan_btn = st.button(
        "🔍 Trending Produkte scannen",
        type="primary",
        use_container_width=True,
        help="Scannt Reddit + Google Trends und findet virale Produkte",
    )
with info_col:
    st.markdown(
        "<div style='padding-top:8px;font-size:0.78rem;color:#555'>"
        "Scannt Reddit Hot-Posts + Google Trending Searches automatisch · "
        "Ergebnisse werden 15 Min. gecacht · Kein API-Key nötig"
        "</div>",
        unsafe_allow_html=True,
    )

if not scan_btn and "sentiment_results" not in st.session_state:
    st.info(
        "👆 **'Trending Produkte scannen'** klicken — App findet automatisch, "
        "welche Produkte gerade viral gehen und welche Aktien davon profitieren.",
        icon="🧭",
    )
    st.stop()

# ── Scan ausführen ─────────────────────────────────────────────────────────────
if scan_btn or "sentiment_results" not in st.session_state:
    _progress = st.progress(0, text="Verbinde mit Reddit …")
    reddit_posts = _reddit_scan(
        tuple(selected_subs if selected_subs else ["all", "BuyItForLife"]),
        min_score,
    )
    _progress.progress(50, text="Lade Google Trends …")
    google_trends = _google_trending(trends_country)
    _progress.progress(80, text="Aggregiere Ergebnisse …")
    results = _aggregate_brands(reddit_posts, google_trends)
    _progress.progress(100, text="Fertig!")
    _progress.empty()

    st.session_state["sentiment_results"]      = results
    st.session_state["sentiment_google"]       = google_trends
    st.session_state["sentiment_reddit_count"] = len(reddit_posts)
    st.session_state["sentiment_scan_time"]    = datetime.now().strftime("%H:%M")

results        = st.session_state["sentiment_results"]
google_trends  = st.session_state["sentiment_google"]
reddit_count   = st.session_state["sentiment_reddit_count"]
scan_time      = st.session_state["sentiment_scan_time"]

# ── Scan-Info ──────────────────────────────────────────────────────────────────
st.markdown(
    f"<div style='font-size:0.75rem;color:#333;margin-bottom:12px'>"
    f"✅ Scan um {scan_time} · "
    f"{reddit_count} Reddit-Posts analysiert · "
    f"{len(google_trends)} Google Trends · "
    f"{len(results)} Trend-Produkte gefunden"
    f"</div>",
    unsafe_allow_html=True,
)

if not results:
    st.warning(
        "Keine Trend-Produkte gefunden. Bitte Subreddits oder Min. Upvotes anpassen "
        "und erneut scannen.",
        icon="⚠️",
    )
    st.stop()

# ── Google Trends Sidebar ──────────────────────────────────────────────────────
if google_trends:
    with st.expander(f"📈 Google Trending Searches ({len(google_trends)} Begriffe)", expanded=False):
        gt_cols = st.columns(4)
        for i, term in enumerate(google_trends):
            matched = [b for b in BRAND_TICKER if b in term.lower() or term.lower() in b]
            badge = f" → **{BRAND_TICKER[matched[0]]}**" if matched else ""
            gt_cols[i % 4].markdown(f"· {term}{badge}")

# ══════════════════════════════════════════════════════════════════════════════
# ERGEBNISSE — TREND-KARTEN
# ══════════════════════════════════════════════════════════════════════════════
st.markdown(
    "<div style='font-size:1.0rem;font-weight:700;color:#f0f0f0;margin:16px 0 10px'>"
    "📦 Entdeckte Trend-Produkte",
    unsafe_allow_html=True,
)

for i, item in enumerate(results[:20]):
    brand   = item["brand"].title()
    ticker  = item["ticker"]
    score   = item["trend_score"]
    nsubs   = len(item["subreddits"])
    bull    = item["bull"]
    bear    = item["bear"]
    net     = item["net_sentiment"]
    google  = item["google"]

    # Sentiment-Label
    if net >= 40:
        sent_label, sent_color = "🚀 Stark Bullish", "#22c55e"
    elif net >= 10:
        sent_label, sent_color = "📈 Bullish", "#86efac"
    elif net >= -10:
        sent_label, sent_color = "➡️ Neutral", "#f59e0b"
    else:
        sent_label, sent_color = "📉 Bearish", "#ef4444"

    # Stock-Daten (gecacht)
    sinfo: dict = {}
    if ticker:
        sinfo = _stock_info(ticker)

    # Card HTML
    price_badge = ""
    if sinfo:
        r90_color = "#22c55e" if sinfo["r90"] >= 0 else "#ef4444"
        r90_sign  = "+" if sinfo["r90"] >= 0 else ""
        price_badge = (
            f'<span style="background:#111;border:1px solid #333;border-radius:20px;'
            f'padding:2px 10px;font-size:0.78rem;color:#f0f0f0;margin-left:8px">'
            f'${sinfo["price"]:.2f}'
            f' <span style="color:{r90_color}">{r90_sign}{sinfo["r90"]:.0f}%</span>'
            f'<span style="color:#444;font-size:0.68rem"> 90T</span>'
            f'</span>'
        )

    ticker_badge = (
        f'<span style="background:#d4a843;color:#000;font-weight:700;font-size:0.75rem;'
        f'padding:2px 8px;border-radius:12px;margin-left:6px">{ticker}</span>'
        if ticker else
        '<span style="color:#444;font-size:0.75rem;margin-left:6px">kein Ticker</span>'
    )
    google_badge = (
        '<span style="background:#1a3a1a;color:#22c55e;font-size:0.7rem;'
        'padding:1px 7px;border-radius:10px;margin-left:6px">📈 Google Trending</span>'
        if google else ""
    )

    pricing_html = ""
    if sinfo:
        pricing_html = (
            f'<div style="font-size:0.75rem;margin-top:6px">'
            f'<span style="color:{sinfo["color"]};font-weight:600">'
            f'Eingepreist: {sinfo["label"]}</span>'
            f' <span style="color:#444">— {sinfo["hint"]}</span>'
            f'</div>'
        )

    subs_html = " · ".join(f"r/{s}" for s in item["subreddits"][:6])
    top_posts  = item["top_posts"]

    with st.expander(
        f"{'🔥' if score > 50 else '📦'} {brand}  {ticker or ''}  "
        f"{'📈 Google' if google else ''}  "
        f"· Score {score:.0f} · {item['n_posts']} Posts · {nsubs} Subreddits",
        expanded=False,
    ):
        # Header-Zeile
        st.markdown(
            f'<div style="display:flex;align-items:center;flex-wrap:wrap;gap:4px;'
            f'margin-bottom:8px">'
            f'<span style="font-size:1.05rem;font-weight:700;color:#f0f0f0">{brand}</span>'
            f'{ticker_badge}{price_badge}{google_badge}'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Metriken-Zeile
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Reddit Posts", item["n_posts"])
        m2.metric("Subreddits", nsubs)
        m3.metric("Bullish Signale", bull)
        m4.metric("Sentiment Score", f"{net:+.0f}")

        # Pricing-In
        if sinfo:
            r30c = "#22c55e" if sinfo["r30"] >= 0 else "#ef4444"
            r90c = "#22c55e" if sinfo["r90"] >= 0 else "#ef4444"
            st.markdown(
                f'<div style="background:#0a0a0a;border:1px solid {sinfo["color"]}33;'
                f'border-left:3px solid {sinfo["color"]};border-radius:8px;'
                f'padding:10px 14px;margin:8px 0">'
                f'<div style="font-size:0.85rem;font-weight:700;color:{sinfo["color"]};'
                f'margin-bottom:4px">Einpreisung: {sinfo["label"]}</div>'
                f'<div style="font-size:0.78rem;color:#888">{sinfo["hint"]}</div>'
                f'<div style="font-size:0.75rem;color:#555;margin-top:4px">'
                f'30 Tage: <span style="color:{r30c}">{sinfo["r30"]:+.1f}%</span>'
                f' &nbsp;|&nbsp; '
                f'90 Tage: <span style="color:{r90c}">{sinfo["r90"]:+.1f}%</span>'
                f'</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div style="font-size:0.78rem;color:#555;margin:4px 0">'
                'Keine Börsendaten (kein Ticker zugeordnet oder Markt geschlossen)'
                '</div>',
                unsafe_allow_html=True,
            )

        # Quellen-Info
        st.markdown(
            f'<div style="font-size:0.75rem;color:#444;margin-bottom:8px">'
            f'Gefunden in: {subs_html}</div>',
            unsafe_allow_html=True,
        )

        # Reddit Posts
        if top_posts:
            st.markdown("**📰 Gefundene Posts:**")
            for p in top_posts[:4]:
                # Schlüsselwörter hervorheben
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

                st.markdown(
                    f'<div style="background:#0e0e0e;border:1px solid #1e1e1e;'
                    f'border-radius:8px;padding:8px 12px;margin-bottom:5px">'
                    f'<div style="font-size:0.82rem;color:#d0d0d0">{title_hl}</div>'
                    f'<div style="font-size:0.72rem;color:#444;margin-top:3px">'
                    f'r/{p["subreddit"]} · ▲ {p["score"]:,} · '
                    f'💬 {p["comments"]} · '
                    f'<a href="{p["url"]}" target="_blank" '
                    f'style="color:#d4a843;text-decoration:none">→ Reddit</a>'
                    f'</div></div>',
                    unsafe_allow_html=True,
                )

        # Kommentare laden (on-demand)
        if top_posts:
            best_post = top_posts[0]
            if st.button(
                f"💬 Top-Kommentare von r/{best_post['subreddit']} laden",
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
                            f'<div style="font-size:0.78rem;margin:6px 0">'
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
        st.markdown("<div style='height:6px'></div>", unsafe_allow_html=True)
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

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    f'<div style="font-size:0.72rem;color:#333;text-align:center">'
    f'Datenquellen: Reddit JSON-API (kein Key) · Google Trends (pytrends) · '
    f'Kursdaten: Yahoo Finance · Scan: {scan_time}'
    f'</div>',
    unsafe_allow_html=True,
)
