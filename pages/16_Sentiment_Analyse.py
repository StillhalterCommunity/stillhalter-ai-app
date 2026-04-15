"""
Stillhalter AI App — Sentiment Analyse
Chris Camillo Social Arbitrage: Virale Trends → Börsenchancen
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

# ── Signal-Keywords (Chris Camillo Demand-Signale) ────────────────────────────
BULLISH_KEYWORDS = [
    "sold out", "selling out", "sell out", "obsessed", "addicted",
    "can't stop", "cant stop", "can't find", "cant find", "impossible to find",
    "viral", "trending", "everywhere", "amazing", "incredible", "insane",
    "game changer", "game-changer", "must have", "need this", "love this",
    "waiting list", "wait list", "back order", "backorder", "pre-order", "preorder",
    "shipped", "just got", "unboxing", "recommend", "life changing", "worth it",
    "everyone is", "everyone has", "blew up", "blowing up", "can't believe",
    "cant believe", "mind blown", "10/10", "absolutely love", "buying more",
    "restocking", "shortage", "overwhelming demand", "popular", "selling fast",
    "so good", "best purchase", "changed my life", "hooked",
    "ausverkauft", "überall", "alle kaufen", "süchtig", "empfehle",
    "ausgezeichnet", "begeistert",
]

BEARISH_KEYWORDS = [
    "returning", "returned", "return it", "disappointed", "disappointing",
    "terrible", "broken", "defective", "defect", "recall", "recalled",
    "lawsuit", "sued", "scandal", "avoid", "stay away", "worst",
    "waste of money", "overpriced", "cancelled", "cancel", "switching to",
    "moved to", "stopped using", "don't buy", "dont buy", "regret",
    "refund", "complaint", "dangerous", "unsafe", "inferior", "overrated",
    "not worth", "cheaply made", "quality issues", "falling apart",
    "enttäuscht", "zurückgeben", "schlecht", "kaputt", "vermeiden",
    "rückruf", "klage", "überteuert",
]

# ── Preset-Ideen (Chris Camillo Stil) ────────────────────────────────────────
PRESET_IDEAS = [
    {"emoji": "🥤", "topic": "Celsius Energy Drink", "ticker": "CELH"},
    {"emoji": "☕", "topic": "Stanley Cup Tumbler",   "ticker": "SWK"},
    {"emoji": "🎮", "topic": "NVIDIA RTX GPU",        "ticker": "NVDA"},
    {"emoji": "🧘", "topic": "Lululemon Leggings",    "ticker": "LULU"},
    {"emoji": "💊", "topic": "Ozempic Weight Loss",   "ticker": "NVO"},
    {"emoji": "👟", "topic": "On Running Shoes",      "ticker": "ONON"},
    {"emoji": "🌮", "topic": "Chipotle Mexican Grill","ticker": "CMG"},
    {"emoji": "🚗", "topic": "Tesla Cybertruck",      "ticker": "TSLA"},
]

# ── Daten-Funktionen ──────────────────────────────────────────────────────────

@st.cache_data(ttl=900, show_spinner=False)
def _fetch_reddit(query: str, limit: int = 40) -> list[dict]:
    """Reddit via öffentlichem JSON-API — kein API-Key nötig."""
    import requests
    try:
        url = (
            f"https://www.reddit.com/search.json"
            f"?q={requests.utils.quote(query)}&sort=hot&limit={limit}&t=week"
        )
        r = requests.get(url, headers={"User-Agent": "StillhalterApp/2.0"}, timeout=12)
        if r.status_code != 200:
            return []
        posts = []
        for child in r.json().get("data", {}).get("children", []):
            p = child.get("data", {})
            posts.append({
                "title":        p.get("title", ""),
                "text":         p.get("selftext", "")[:600],
                "score":        p.get("score", 0),
                "comments":     p.get("num_comments", 0),
                "subreddit":    p.get("subreddit", ""),
                "url":          "https://reddit.com" + p.get("permalink", ""),
                "upvote_ratio": p.get("upvote_ratio", 0.5),
                "created":      datetime.utcfromtimestamp(
                                    p.get("created_utc", 0)).strftime("%d.%m.%Y"),
            })
        return sorted(posts, key=lambda x: x["score"], reverse=True)
    except Exception:
        return []


@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_google_trends(keyword: str) -> tuple[pd.DataFrame, dict]:
    """Google Trends via pytrends — liefert Interesse + verwandte Suchanfragen."""
    try:
        from pytrends.request import TrendReq
        pt = TrendReq(hl="de-DE", tz=60, timeout=(10, 30))
        pt.build_payload([keyword], timeframe="now 30-d")
        interest = pt.interest_over_time()
        related_raw = pt.related_queries()
        related: dict = {}
        if keyword in related_raw:
            top = related_raw[keyword].get("top")
            if top is not None and not top.empty:
                related["top"] = top.head(10).to_dict("records")
            rising = related_raw[keyword].get("rising")
            if rising is not None and not rising.empty:
                related["rising"] = rising.head(10).to_dict("records")
        return interest, related
    except ImportError:
        return pd.DataFrame(), {"error": "pytrends nicht installiert"}
    except Exception as e:
        return pd.DataFrame(), {"error": str(e)}


@st.cache_data(ttl=900, show_spinner=False)
def _fetch_nitter(query: str) -> list[dict]:
    """X/Twitter-Posts via Nitter RSS (öffentliche Instanzen, kein Account)."""
    try:
        import feedparser
    except ImportError:
        return [{"error": "feedparser nicht installiert"}]

    INSTANCES = [
        "https://nitter.privacydev.net",
        "https://nitter.poast.org",
        "https://nitter.1d4.us",
        "https://nitter.tiekoetter.com",
        "https://nitter.adminforge.de",
    ]
    encoded = query.replace(" ", "+")
    for inst in INSTANCES:
        try:
            feed = feedparser.parse(
                f"{inst}/search/rss?q={encoded}&f=tweets",
                request_headers={"User-Agent": "StillhalterApp/2.0"},
            )
            if feed.entries:
                return [
                    {
                        "text": re.sub(r"<[^>]+>", "", e.get("summary", ""))[:400],
                        "link": e.get("link", ""),
                        "date": e.get("published", ""),
                    }
                    for e in feed.entries[:30]
                ]
        except Exception:
            continue
    return []


@st.cache_data(ttl=1800, show_spinner=False)
def _fetch_yt_comments(video_url: str) -> list[str]:
    """YouTube-Kommentare via youtube-comment-downloader (kein API-Key)."""
    try:
        from youtube_comment_downloader import YoutubeCommentDownloader
        dl = YoutubeCommentDownloader()
        comments = []
        for i, c in enumerate(dl.get_comments_from_url(video_url, sort_by=0)):
            comments.append(c.get("text", ""))
            if i >= 199:
                break
        return comments
    except ImportError:
        return ["__IMPORT_ERROR__"]
    except Exception as e:
        return [f"__ERROR__: {e}"]


def _analyze_sentiment(texts: list[str]) -> dict:
    """Berechnet Bullish/Bearish-Score aus einer Liste von Texten."""
    all_text = " ".join(texts).lower()

    bull_found: list[tuple[str, int]] = []
    bear_found: list[tuple[str, int]] = []

    for kw in BULLISH_KEYWORDS:
        count = all_text.count(kw.lower())
        if count > 0:
            bull_found.append((kw, count))
    for kw in BEARISH_KEYWORDS:
        count = all_text.count(kw.lower())
        if count > 0:
            bear_found.append((kw, count))

    bull_score = sum(c for _, c in bull_found)
    bear_score = sum(c for _, c in bear_found)
    total = bull_score + bear_score

    net = (bull_score - bear_score) / max(total, 1) * 100

    if net >= 40:
        label, color, icon = "Stark Bullish",  "#22c55e", "🚀"
    elif net >= 15:
        label, color, icon = "Bullish",        "#86efac", "📈"
    elif net >= -15:
        label, color, icon = "Neutral",        "#f59e0b", "➡️"
    elif net >= -40:
        label, color, icon = "Bearish",        "#f87171", "📉"
    else:
        label, color, icon = "Stark Bearish",  "#ef4444", "💥"

    return {
        "bull_score":  bull_score,
        "bear_score":  bear_score,
        "net_score":   round(net, 1),
        "label":       label,
        "color":       color,
        "icon":        icon,
        "bull_found":  sorted(bull_found, key=lambda x: x[1], reverse=True)[:8],
        "bear_found":  sorted(bear_found, key=lambda x: x[1], reverse=True)[:8],
        "total_texts": len(texts),
    }


def _highlight(text: str, kw_list: list[str], color: str) -> str:
    """Hebt Schlüsselwörter in einem Text farbig hervor (HTML)."""
    for kw in sorted(kw_list, key=len, reverse=True):
        pattern = re.compile(re.escape(kw), re.IGNORECASE)
        text = pattern.sub(
            f'<span style="background:{color}22;color:{color};'
            f'border-radius:3px;padding:0 2px;font-weight:600">{kw}</span>',
            text,
        )
    return text


# ── Header ─────────────────────────────────────────────────────────────────────
h1, h2 = st.columns([1, 6])
with h1:
    st.markdown(get_logo_html("white", 36), unsafe_allow_html=True)
with h2:
    st.markdown(
        '<div class="sc-page-title">Sentiment Analyse</div>'
        '<div class="sc-page-subtitle">Chris Camillo Social Arbitrage · '
        'Virale Trends → Börsenchancen · Reddit · Google Trends · X/Twitter · YouTube</div>',
        unsafe_allow_html=True,
    )
st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── Erklärung ──────────────────────────────────────────────────────────────────
with st.expander("💡 **Was ist Chris Camillo Social Arbitrage?**", expanded=False):
    st.markdown("""
    **Chris Camillo** ist einer der erfolgreichsten Privatanleger, der mit **„Social Arbitrage"**
    über 20 Jahre eine Rendite von >3.000% erzielte — ohne Bloomberg-Terminal oder Insider-Info.

    **Die Kernidee:**
    > *„Ich investiere in Dinge, die ich im echten Leben beobachte —
    > bevor die Wall Street sie entdeckt."*

    **Was er sucht:**
    - 🔥 Produkte, über die alle reden — aber die Börse noch nichts weiß
    - 🛒 **„Sold out"**, **„Can't find it"**, **„Obsessed"** = echte Nachfrage-Signale
    - 📱 Viraler Social-Media-Content mit echter emotionaler Reaktion
    - 🏭 **Supply-Chain-Gewinner**: Nicht nur das Endprodukt, auch Zulieferer

    **Vorgehen:**
    1. Trend-Thema eingeben (z.B. *"Stanley Cup"*, *"Celsius Energy"*, *"Ozempic"*)
    2. App scannt Reddit, Google Trends & X/Twitter auf Social-Signale
    3. Signal-Score zeigt Bullish/Bearish-Trend
    4. Ticker zuweisen → Aktie weiter analysieren im Watchlist Scanner
    """)

# ── Quick-Presets ──────────────────────────────────────────────────────────────
st.markdown(
    "<div style='font-size:0.78rem;color:#666;margin:10px 0 6px 0'>"
    "📌 <b>Schnell-Ideen</b> — beliebte Trend-Themen mit einem Klick laden:</div>",
    unsafe_allow_html=True,
)
preset_cols = st.columns(len(PRESET_IDEAS))
for i, p in enumerate(PRESET_IDEAS):
    with preset_cols[i]:
        if st.button(
            f"{p['emoji']} {p['topic'].split()[0]}",
            use_container_width=True,
            help=f"{p['topic']} · Ticker: {p['ticker']}",
            key=f"preset_{i}",
        ):
            st.session_state["sent_topic"]  = p["topic"]
            st.session_state["sent_ticker"] = p["ticker"]
            st.rerun()

# ── Eingabe ────────────────────────────────────────────────────────────────────
st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
col_topic, col_ticker, col_btn = st.columns([4, 2, 1])
with col_topic:
    topic = st.text_input(
        "Trend-Thema",
        value=st.session_state.get("sent_topic", ""),
        placeholder="z.B. Celsius Energy Drink, Stanley Cup, Ozempic …",
        help="Produkt, Marke oder Trend-Begriff — wird auf Reddit, Google & Twitter gesucht",
    )
with col_ticker:
    ticker = st.text_input(
        "Börsen-Ticker (optional)",
        value=st.session_state.get("sent_ticker", ""),
        placeholder="z.B. CELH, NVDA, LULU",
        help="Zugehörige Aktie — für direkten Link zum Watchlist Scanner",
    ).upper().strip()
with col_btn:
    st.markdown("<div style='height:28px'></div>", unsafe_allow_html=True)
    scan_btn = st.button("🔍 Analysieren", type="primary", use_container_width=True)

if not topic:
    st.info(
        "👆 **Thema eingeben** oder oben ein Schnell-Preset wählen — "
        "dann startet die Social-Sentiment-Analyse.",
        icon="🧭",
    )
    st.stop()

# ── Analyse starten ────────────────────────────────────────────────────────────
st.markdown(f"<div style='height:4px'></div>", unsafe_allow_html=True)

tab_trends, tab_reddit, tab_twitter, tab_yt = st.tabs([
    "📈 Google Trends",
    "🟠 Reddit",
    "🐦 X / Twitter",
    "📺 YouTube",
])

# Daten parallel laden (alle gecacht)
with st.spinner(f"Scanne Social Media für **{topic}** …"):
    reddit_posts = _fetch_reddit(topic)
    trends_df, trends_related = _fetch_google_trends(topic)
    tweets = _fetch_nitter(topic)

# Alle Texte für Gesamt-Sentiment sammeln
all_texts: list[str] = []
for p in reddit_posts:
    all_texts.append(p["title"] + " " + p.get("text", ""))
for t in tweets:
    if isinstance(t, dict) and "text" in t:
        all_texts.append(t["text"])
if not trends_df.empty and topic in trends_df.columns:
    # Trends-Score als Proxy für Interesse
    last_val = int(trends_df[topic].iloc[-1]) if len(trends_df) > 0 else 0
    if last_val > 70:
        all_texts.append(" ".join(["trending viral everywhere"] * 3))

sentiment = _analyze_sentiment(all_texts)

# ── Signal-Card (immer sichtbar) ───────────────────────────────────────────────
s = sentiment
bar_pct_bull = min(100, s["bull_score"])
bar_pct_bear = min(100, s["bear_score"])
total_bar = max(s["bull_score"] + s["bear_score"], 1)
bull_bar_w = int(s["bull_score"] / total_bar * 100)
bear_bar_w = 100 - bull_bar_w

ticker_badge = (
    f'<a href="?page=04_Watchlist_Scanner" target="_self" '
    f'style="background:#d4a843;color:#000;font-size:0.78rem;'
    f'font-weight:700;padding:3px 10px;border-radius:20px;'
    f'text-decoration:none;margin-left:12px">→ {ticker} scannen</a>'
    if ticker else ""
)

st.markdown(f"""
<div style='background:#111;border:1px solid #1e1e1e;border-top:3px solid {s["color"]};
            border-radius:14px;padding:20px 24px;margin:12px 0'>
  <div style='display:flex;align-items:center;margin-bottom:12px'>
    <span style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.2rem;
                 color:{s["color"]}'>{s["icon"]} {s["label"]}</span>
    <span style='font-family:RedRose,sans-serif;font-size:0.8rem;color:#555;margin-left:16px'>
      Score: <b style='color:#f0f0f0'>{s["net_score"]:+.0f}</b>
      &nbsp;·&nbsp; {s["total_texts"]} Quellen analysiert
      &nbsp;·&nbsp; {s["bull_score"]} Bullish-Treffer · {s["bear_score"]} Bearish-Treffer
    </span>
    {ticker_badge}
  </div>
  <div style='display:flex;height:8px;border-radius:4px;overflow:hidden;margin-bottom:12px'>
    <div style='width:{bull_bar_w}%;background:#22c55e'></div>
    <div style='width:{bear_bar_w}%;background:#ef4444'></div>
  </div>
  <div style='display:flex;gap:32px'>
    <div>
      <div style='font-size:0.72rem;color:#22c55e;text-transform:uppercase;
                  letter-spacing:0.1em;margin-bottom:4px'>🚀 Bullish Signale</div>
      <div style='font-size:0.82rem;color:#aaa'>
        {" &nbsp;·&nbsp; ".join(
            f'<b style="color:#22c55e">{kw}</b> <span style="color:#555">×{n}</span>'
            for kw, n in s["bull_found"][:5]
        ) or '<span style="color:#444">keine gefunden</span>'}
      </div>
    </div>
    <div>
      <div style='font-size:0.72rem;color:#ef4444;text-transform:uppercase;
                  letter-spacing:0.1em;margin-bottom:4px'>💥 Bearish Signale</div>
      <div style='font-size:0.82rem;color:#aaa'>
        {" &nbsp;·&nbsp; ".join(
            f'<b style="color:#ef4444">{kw}</b> <span style="color:#555">×{n}</span>'
            for kw, n in s["bear_found"][:5]
        ) or '<span style="color:#444">keine gefunden</span>'}
      </div>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — GOOGLE TRENDS
# ══════════════════════════════════════════════════════════════════════════════
with tab_trends:
    if "error" in trends_related:
        st.warning(
            f"⚠️ Google Trends nicht verfügbar: {trends_related['error']}\n\n"
            "Bitte `pytrends` installieren: `pip install pytrends`",
            icon="⚠️",
        )
    elif trends_df.empty:
        st.info(
            "📊 Keine Google-Trends-Daten — evtl. Rate-Limit erreicht. "
            "Kurz warten und neu laden.",
            icon="📊",
        )
    else:
        import plotly.graph_objects as go

        col_trend = topic if topic in trends_df.columns else trends_df.columns[0]
        last_val  = int(trends_df[col_trend].iloc[-1])
        max_val   = int(trends_df[col_trend].max())
        avg_val   = int(trends_df[col_trend].mean())

        g1, g2, g3 = st.columns(3)
        with g1:
            st.metric("Aktuelles Interesse", f"{last_val}/100",
                      delta=f"{last_val - avg_val:+.0f} vs. Ø",
                      delta_color="normal")
        with g2:
            st.metric("Peak (30 Tage)", f"{max_val}/100")
        with g3:
            trend_dir = "↑ steigend" if last_val > avg_val else "↓ fallend"
            st.metric("Trend", trend_dir)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=trends_df.index,
            y=trends_df[col_trend],
            mode="lines",
            name="Google Interesse",
            line=dict(color="#d4a843", width=2),
            fill="tozeroy",
            fillcolor="rgba(212,168,67,0.08)",
        ))
        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor="#0e0e0e",
            plot_bgcolor="#0e0e0e",
            height=280,
            margin=dict(l=0, r=0, t=20, b=0),
            xaxis=dict(showgrid=False),
            yaxis=dict(showgrid=True, gridcolor="#1e1e1e", range=[0, 105]),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

        if trends_related:
            rc1, rc2 = st.columns(2)
            with rc1:
                if "top" in trends_related:
                    st.markdown("**🔝 Top verwandte Suchanfragen**")
                    for item in trends_related["top"]:
                        val = item.get("value", 0)
                        bar = int(val / 100 * 200) if val <= 100 else 200
                        st.markdown(
                            f'<div style="display:flex;align-items:center;gap:8px;'
                            f'margin-bottom:4px">'
                            f'<div style="width:120px;font-size:0.8rem;color:#ccc">'
                            f'{item["query"]}</div>'
                            f'<div style="flex:1;background:#1e1e1e;border-radius:3px;height:6px">'
                            f'<div style="width:{min(val,100)}%;background:#d4a843;'
                            f'height:6px;border-radius:3px"></div></div>'
                            f'<div style="font-size:0.75rem;color:#555;width:30px">{val}</div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )
            with rc2:
                if "rising" in trends_related:
                    st.markdown("**📈 Aufsteigende Suchanfragen**")
                    for item in trends_related["rising"]:
                        val_raw = item.get("value", 0)
                        label = f"+{val_raw}%" if val_raw < 5000 else "Breakout 🔥"
                        st.markdown(
                            f'<div style="font-size:0.8rem;color:#ccc;'
                            f'margin-bottom:4px">'
                            f'<b style="color:#22c55e">{item["query"]}</b>'
                            f' <span style="color:#555;font-size:0.72rem">'
                            f'{label}</span></div>',
                            unsafe_allow_html=True,
                        )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — REDDIT
# ══════════════════════════════════════════════════════════════════════════════
with tab_reddit:
    if not reddit_posts:
        st.info(
            f'Keine Reddit-Posts für **{topic}** gefunden. '
            'Reddit kann kurzzeitig nicht erreichbar sein — bitte kurz warten.',
            icon="🟠",
        )
    else:
        bull_kws = [kw for kw, _ in s["bull_found"]]
        bear_kws = [kw for kw, _ in s["bear_found"]]

        rc1, rc2, rc3 = st.columns(3)
        with rc1:
            st.metric("Posts gefunden", len(reddit_posts))
        with rc2:
            top_score = reddit_posts[0]["score"] if reddit_posts else 0
            st.metric("Top Upvotes", f"{top_score:,}")
        with rc3:
            subs = list({p["subreddit"] for p in reddit_posts})
            st.metric("Subreddits", len(subs))

        st.markdown(
            f"<div style='font-size:0.75rem;color:#555;margin-bottom:8px'>"
            f"Subreddits: {', '.join(f'r/{s}' for s in subs[:8])}</div>",
            unsafe_allow_html=True,
        )

        for p in reddit_posts[:15]:
            ratio_color = "#22c55e" if p["upvote_ratio"] > 0.75 else "#f59e0b"
            title_html  = _highlight(p["title"], bull_kws, "#22c55e")
            title_html  = _highlight(title_html, bear_kws, "#ef4444")
            text_html   = _highlight(p.get("text", ""), bull_kws, "#22c55e")
            text_html   = _highlight(text_html, bear_kws, "#ef4444")

            st.markdown(
                f'<div style="background:#111;border:1px solid #1e1e1e;border-radius:10px;'
                f'padding:12px 16px;margin-bottom:6px">'
                f'<div style="font-size:0.88rem;color:#f0f0f0;margin-bottom:4px">'
                f'{title_html}</div>'
                f'<div style="display:flex;gap:16px;font-size:0.74rem;color:#555;'
                f'margin-bottom:{6 if text_html.strip() else 0}px">'
                f'<span>r/{p["subreddit"]}</span>'
                f'<span>▲ {p["score"]:,}</span>'
                f'<span>💬 {p["comments"]}</span>'
                f'<span style="color:{ratio_color}">'
                f'{int(p["upvote_ratio"]*100)}% Upvotes</span>'
                f'<span>{p["created"]}</span>'
                f'<a href="{p["url"]}" target="_blank" '
                f'style="color:#d4a843;text-decoration:none">→ Reddit</a>'
                f'</div>'
                + (
                    f'<div style="font-size:0.78rem;color:#666;line-height:1.5">'
                    f'{text_html[:300]}{"…" if len(text_html) > 300 else ""}</div>'
                    if text_html.strip() else ""
                )
                + "</div>",
                unsafe_allow_html=True,
            )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — X / TWITTER (NITTER RSS)
# ══════════════════════════════════════════════════════════════════════════════
with tab_twitter:
    if not tweets:
        st.warning(
            "🐦 Keine Tweets gefunden — Nitter-Instanzen können zeitweise offline sein. "
            "Bitte `feedparser` installieren (`pip install feedparser`) und erneut versuchen.",
            icon="🐦",
        )
    elif len(tweets) == 1 and "error" in tweets[0]:
        st.warning(
            "🐦 feedparser nicht installiert.\n\n"
            "Bitte ausführen: `pip install feedparser`",
            icon="⚠️",
        )
    else:
        bull_kws = [kw for kw, _ in s["bull_found"]]
        bear_kws = [kw for kw, _ in s["bear_found"]]

        st.metric("Tweets gefunden", len(tweets))

        for t in tweets:
            if not isinstance(t, dict) or "text" not in t:
                continue
            text_html = _highlight(t["text"], bull_kws, "#22c55e")
            text_html = _highlight(text_html, bear_kws, "#ef4444")
            st.markdown(
                f'<div style="background:#111;border:1px solid #1e1e1e;border-radius:10px;'
                f'padding:10px 14px;margin-bottom:5px">'
                f'<div style="font-size:0.85rem;color:#e0e0e0;line-height:1.55">'
                f'{text_html}</div>'
                + (
                    f'<div style="font-size:0.72rem;color:#555;margin-top:4px">'
                    f'{t.get("date","")}'
                    + (
                        f' &nbsp;·&nbsp; <a href="{t["link"]}" target="_blank" '
                        f'style="color:#d4a843;text-decoration:none">→ X</a>'
                        if t.get("link") else ""
                    )
                    + "</div>"
                )
                + "</div>",
                unsafe_allow_html=True,
            )

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — YOUTUBE KOMMENTARE
# ══════════════════════════════════════════════════════════════════════════════
with tab_yt:
    st.markdown("""
    **YouTube Kommentar-Analyse**

    Paste eine YouTube-Video-URL — die App lädt die neuesten Kommentare
    und analysiert sie auf Bullish/Bearish-Signale (kein API-Key nötig).
    """)

    yt_url = st.text_input(
        "YouTube Video URL",
        placeholder="https://www.youtube.com/watch?v=...",
        help="z.B. ein virales Produkt-Review oder Haul-Video",
    )

    if yt_url and st.button("📺 Kommentare analysieren", type="primary"):
        with st.spinner("Lade YouTube-Kommentare …"):
            comments = _fetch_yt_comments(yt_url)

        if not comments:
            st.warning("Keine Kommentare gefunden oder Video geschützt.")
        elif comments[0] == "__IMPORT_ERROR__":
            st.error(
                "❌ `youtube-comment-downloader` nicht installiert.\n\n"
                "Bitte ausführen: `pip install youtube-comment-downloader`"
            )
        elif comments[0].startswith("__ERROR__"):
            st.error(f"❌ Fehler: {comments[0][9:]}")
        else:
            yt_sentiment = _analyze_sentiment(comments)
            ys = yt_sentiment

            st.markdown(
                f'<div style="background:#111;border:1px solid #1e1e1e;'
                f'border-top:3px solid {ys["color"]};border-radius:12px;'
                f'padding:16px 20px;margin:8px 0">'
                f'<b style="color:{ys["color"]};font-size:1.1rem">'
                f'{ys["icon"]} {ys["label"]}</b>'
                f'<span style="color:#555;font-size:0.8rem;margin-left:12px">'
                f'Score: {ys["net_score"]:+.0f} · {len(comments)} Kommentare</span>'
                f'</div>',
                unsafe_allow_html=True,
            )

            bull_kws = [kw for kw, _ in ys["bull_found"]]
            bear_kws = [kw for kw, _ in ys["bear_found"]]

            yt1, yt2 = st.columns(2)
            with yt1:
                st.markdown("**🚀 Bullish Signale**")
                for kw, n in ys["bull_found"]:
                    st.markdown(
                        f'<span style="color:#22c55e">{kw}</span> '
                        f'<span style="color:#555">×{n}</span>  ',
                        unsafe_allow_html=True,
                    )
            with yt2:
                st.markdown("**💥 Bearish Signale**")
                for kw, n in ys["bear_found"]:
                    st.markdown(
                        f'<span style="color:#ef4444">{kw}</span> '
                        f'<span style="color:#555">×{n}</span>  ',
                        unsafe_allow_html=True,
                    )

            st.markdown("**📝 Kommentar-Auszug**")
            for c in comments[:10]:
                c_html = _highlight(c, bull_kws, "#22c55e")
                c_html = _highlight(c_html, bear_kws, "#ef4444")
                st.markdown(
                    f'<div style="background:#111;border:1px solid #1e1e1e;'
                    f'border-radius:8px;padding:8px 12px;margin-bottom:4px;'
                    f'font-size:0.82rem;color:#ccc;line-height:1.5">'
                    f'{c_html}</div>',
                    unsafe_allow_html=True,
                )
    else:
        st.markdown("""
        **Wo finde ich geeignete Videos?**
        1. YouTube suchen: z.B. *"Celsius Energy Drink review 2024"*
        2. Video mit vielen Kommentaren auswählen (Produktreviews, Hauls, Unboxings)
        3. URL oben einfügen → Kommentare werden analysiert

        💡 **Tipp:** Videos mit 1.000+ Kommentaren liefern die besten Signale.
        """)

        # YouTube-Suchlink
        yt_search = topic.replace(" ", "+")
        st.markdown(
            f'🔗 [YouTube nach **{topic}** durchsuchen →](https://www.youtube.com/results?search_query={yt_search})',
        )

# ── Analyse-Info-Footer ────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    f'<div style="font-size:0.72rem;color:#333;text-align:center">'
    f'Datenquellen: Reddit (öffentliche JSON-API) · '
    f'Google Trends (pytrends) · X/Twitter (Nitter RSS) · '
    f'YouTube (youtube-comment-downloader) · '
    f'Zuletzt aktualisiert: {datetime.now().strftime("%H:%M")}'
    f'</div>',
    unsafe_allow_html=True,
)
