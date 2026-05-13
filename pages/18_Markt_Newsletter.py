"""
Stillhalter AI App — Markt Newsletter
Täglicher Börsennewsletter: 11 Sektoren · Fundamentals · TA · Optionsempfehlung.

Quellen: Yahoo Finance RSS · yfinance News · MarketWatch · CNN Fear & Greed
TA:      Stillhalter Trend Model (1M · 1W · 1D) · Dual Stochastik · MACD Pro
"""

from __future__ import annotations
import os
import pickle
import streamlit as st
import pandas as pd
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Markt Newsletter · Stillhalter AI App",
    page_icon="📰",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

from data.fetcher import fetch_stock_info, fetch_fundamentals, fetch_price_history
from analysis.multi_timeframe import analyze_multi_timeframe
from analysis.batch_screener import scan_ticker

# ══════════════════════════════════════════════════════════════════════════════
# SEKTOREN — 11 GICS Sektoren mit je 3 Leit-Aktien
# ══════════════════════════════════════════════════════════════════════════════
SECTORS: dict[str, dict] = {
    "💻 Technology": {
        "etf": "XLK", "color": "#3b82f6",
        "stocks": ["AAPL", "MSFT", "NVDA"],
        "rss": "https://finance.yahoo.com/rss/headline?s=XLK",
        "description": "KI-Boom, Halbleiter & Cloud-Infrastruktur bestimmen den Sektor.",
    },
    "🏥 Healthcare": {
        "etf": "XLV", "color": "#22c55e",
        "stocks": ["LLY", "UNH", "JNJ"],
        "rss": "https://finance.yahoo.com/rss/headline?s=XLV",
        "description": "GLP-1-Medikamente, Biotech-Zulassungen & Versicherungsmargen im Fokus.",
    },
    "🏦 Financials": {
        "etf": "XLF", "color": "#f59e0b",
        "stocks": ["JPM", "BAC", "V"],
        "rss": "https://finance.yahoo.com/rss/headline?s=XLF",
        "description": "Zinsumfeld, Kreditqualität & Regulierung treiben die Banken.",
    },
    "🛍️ Consumer Discret.": {
        "etf": "XLY", "color": "#ec4899",
        "stocks": ["AMZN", "TSLA", "HD"],
        "rss": "https://finance.yahoo.com/rss/headline?s=XLY",
        "description": "E-Commerce, Elektro-Autos & Wohnbau-Nachfrage als Treiber.",
    },
    "🛒 Consumer Staples": {
        "etf": "XLP", "color": "#84cc16",
        "stocks": ["PG", "KO", "WMT"],
        "rss": "https://finance.yahoo.com/rss/headline?s=XLP",
        "description": "Defensive Qualität: Markenstärke & Pricing Power in Inflation.",
    },
    "⚡ Energy": {
        "etf": "XLE", "color": "#f97316",
        "stocks": ["XOM", "CVX", "COP"],
        "rss": "https://finance.yahoo.com/rss/headline?s=XLE",
        "description": "Ölpreis, OPEC+ Entscheidungen & Übergang zu Erneuerbaren.",
    },
    "⚙️ Industrials": {
        "etf": "XLI", "color": "#6b7280",
        "stocks": ["CAT", "GE", "UPS"],
        "rss": "https://finance.yahoo.com/rss/headline?s=XLI",
        "description": "Reshoring-Trend, Infrastruktur-Investitionen & Rüstungsausgaben.",
    },
    "🪨 Materials": {
        "etf": "XLB", "color": "#a78bfa",
        "stocks": ["LIN", "NEM", "FCX"],
        "rss": "https://finance.yahoo.com/rss/headline?s=XLB",
        "description": "Kupfer als KI-Indikator, Gold als Safe-Haven & Chemie-Margen.",
    },
    "📡 Communication": {
        "etf": "XLC", "color": "#06b6d4",
        "stocks": ["META", "GOOGL", "NFLX"],
        "rss": "https://finance.yahoo.com/rss/headline?s=XLC",
        "description": "Social Media, Streaming & digitale Werbemärkte im Wettbewerb.",
    },
    "🏠 Real Estate": {
        "etf": "XLRE", "color": "#ef4444",
        "stocks": ["AMT", "PLD", "O"],
        "rss": "https://finance.yahoo.com/rss/headline?s=XLRE",
        "description": "Zinssensitivste Branche: REITs unter Fed-Einfluss.",
    },
    "🔌 Utilities": {
        "etf": "XLU", "color": "#64748b",
        "stocks": ["NEE", "DUK", "SO"],
        "rss": "https://finance.yahoo.com/rss/headline?s=XLU",
        "description": "Energiewende & KI-Datenzentren treiben Strombedarf.",
    },
}

# ── Zusätzliche globale News-Quellen (RSS) ───────────────────────────────────
GLOBAL_RSS_SOURCES = [
    ("Yahoo Finance Top", "https://finance.yahoo.com/rss/topfinstories"),
    ("MarketWatch",       "https://feeds.marketwatch.com/marketwatch/marketpulse/"),
    ("MarketWatch Top",   "https://feeds.marketwatch.com/marketwatch/topstories/"),
]

# Je Sektor auch Stock-spezifische RSS-Feeds
def _stock_rss_url(ticker: str) -> str:
    return f"https://finance.yahoo.com/rss/headline?s={ticker}"

# Twitter/X Accounts (kein kostenloser API-Zugang mehr)
TWITTER_ACCOUNTS = (
    "@WSJmarkets · @business (Bloomberg) · @CNBC · @ReutersBiz · "
    "@elerianm (El-Erian) · @LizAnnSonders (Schwab) · @zerohedge · @FinancialTimes"
)

# ══════════════════════════════════════════════════════════════════════════════
# DATEN-FUNKTIONEN
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=900, show_spinner=False)
def _market_overview() -> dict:
    """S&P500, NASDAQ, DOW, VIX, Gold, Silber, Anleihen."""
    import yfinance as yf
    symbols = {
        "S&P 500":  "^GSPC",
        "NASDAQ":   "^IXIC",
        "DOW":      "^DJI",
        "VIX":      "^VIX",
        "Gold":     "GLD",
        "Silber":   "SLV",
        "Bonds":    "TLT",
    }
    result = {}
    for name, sym in symbols.items():
        try:
            hist = yf.Ticker(sym).history(period="2d")
            if len(hist) >= 2:
                prev = float(hist["Close"].iloc[-2])
                curr = float(hist["Close"].iloc[-1])
                chg  = (curr - prev) / prev * 100
                result[name] = {"price": curr, "chg": chg, "symbol": sym}
            elif len(hist) == 1:
                result[name] = {"price": float(hist["Close"].iloc[-1]), "chg": 0.0, "symbol": sym}
        except Exception:
            result[name] = {"price": None, "chg": 0.0, "symbol": sym}
    return result


@st.cache_data(ttl=1800, show_spinner=False)
def _fear_greed() -> dict:
    """CNN Fear & Greed Index (undokumentierte API)."""
    try:
        r = requests.get(
            "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
            timeout=8,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if r.status_code == 200:
            data = r.json()
            score = data.get("fear_and_greed", {}).get("score", 50)
            rating = data.get("fear_and_greed", {}).get("rating", "Neutral")
            return {"score": round(float(score), 0), "rating": rating}
    except Exception:
        pass
    return {"score": None, "rating": "Nicht verfügbar"}


@st.cache_data(ttl=1800, show_spinner=False)
def _sector_etf_perf(etf: str) -> dict:
    """Tages- & Wochenperformance eines Sektor-ETFs."""
    import yfinance as yf
    try:
        hist = yf.Ticker(etf).history(period="6d")
        if len(hist) < 2:
            return {}
        curr = float(hist["Close"].iloc[-1])
        prev = float(hist["Close"].iloc[-2])
        d1   = (curr - prev) / prev * 100
        w1   = (curr - float(hist["Close"].iloc[0])) / float(hist["Close"].iloc[0]) * 100
        return {"price": curr, "1d": d1, "1w": w1}
    except Exception:
        return {}


@st.cache_data(ttl=600, show_spinner=False)
def _rss_news(url: str, max_items: int = 5) -> list[dict]:
    """Parsed einen RSS-Feed und gibt die neuesten Artikel zurück."""
    try:
        r = requests.get(url, timeout=10, headers={"User-Agent": "StillhalterApp/3.0"})
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.content)
        items = []
        for item in root.findall(".//item")[:max_items]:
            title   = (item.findtext("title") or "").strip()
            link    = (item.findtext("link") or "").strip()
            pubdate = (item.findtext("pubDate") or "").strip()
            if title:
                items.append({"title": title, "link": link, "date": pubdate})
        return items
    except Exception:
        return []


@st.cache_data(ttl=600, show_spinner=False)
def _global_news(max_per_source: int = 4) -> list[dict]:
    """Holt Top-Finanznews aus mehreren RSS-Quellen."""
    all_items: list[dict] = []
    seen: set[str] = set()
    for source_name, url in GLOBAL_RSS_SOURCES:
        try:
            r = requests.get(url, timeout=8, headers={"User-Agent": "StillhalterApp/3.0"})
            if r.status_code != 200:
                continue
            root = ET.fromstring(r.content)
            count = 0
            for item in root.findall(".//item"):
                title = (item.findtext("title") or "").strip()
                link  = (item.findtext("link") or "").strip()
                if title and title not in seen:
                    seen.add(title)
                    all_items.append({"title": title, "link": link, "source": source_name})
                    count += 1
                    if count >= max_per_source:
                        break
        except Exception:
            continue
    return all_items


@st.cache_data(ttl=900, show_spinner=False)
def _quick_price(ticker: str) -> dict:
    """Schneller Preis-Abruf für Sektorübersicht (kein TA)."""
    info  = fetch_stock_info(ticker)
    price = info.get("price")
    prev  = info.get("prev_close")
    chg   = ((price / prev) - 1) * 100 if price and prev else None
    news_raw = fetch_fundamentals(ticker).get("news", [])
    top_news = [
        {"title": n.get("title", ""), "link": n.get("link", ""), "publisher": n.get("publisher", "")}
        for n in news_raw[:3] if n.get("title")
    ]
    return {
        "ticker": ticker,
        "name":   info.get("name", ticker),
        "price":  price,
        "chg":    chg,
        "news":   top_news,
    }


@st.cache_data(ttl=1800, show_spinner=False)
def _stock_analysis(ticker: str) -> dict:
    """Vollanalyse einer Aktie: Info + Fundamentals + TA + Valuation."""
    info  = fetch_stock_info(ticker)
    fund  = fetch_fundamentals(ticker)

    price = info.get("price")
    name  = info.get("name", ticker)

    # ── Technische Analyse (1M · 1W · 1D) ─────────────────────────────────
    mtf = analyze_multi_timeframe(ticker)

    def _tf_signal(tf) -> str:
        if tf is None:
            return "–"
        if tf.ema_bullish and tf.macd_bullish:
            return "🟢 Bullish"
        elif tf.ema_bearish and tf.macd_bearish:
            return "🔴 Bearish"
        elif tf.ema_bullish or tf.macd_bullish:
            return "🟡 Leicht bullish"
        elif tf.ema_bearish or tf.macd_bearish:
            return "🟠 Leicht bearish"
        return "⚪ Neutral"

    ta_monthly  = _tf_signal(mtf.tf_1m)
    ta_weekly   = _tf_signal(mtf.tf_1w)
    ta_daily    = _tf_signal(mtf.tf_1d)
    ta_align    = mtf.alignment_score
    ta_dir      = mtf.alignment_direction

    # ── Valuation Heuristik ────────────────────────────────────────────────
    pe  = fund.get("pe_fwd") or fund.get("pe")
    peg = fund.get("peg_ratio")
    eps_growth = fund.get("eps_growth_next_year")

    if pe:
        if pe < 15:
            val_label, val_color = "Unterbewertet ✅", "#22c55e"
        elif pe < 22:
            val_label, val_color = "Fair bewertet 🟡", "#f59e0b"
        elif pe < 35:
            val_label, val_color = "Leicht überbewertet ⚠️", "#f97316"
        else:
            val_label, val_color = "Überbewertet ❌", "#ef4444"
        # PEG-Korrektur: schnell wachsende Firmen dürfen höheres KGV haben
        if peg and peg < 1.5:
            val_label = "Fair bewertet (PEG ok) 🟡"
            val_color = "#f59e0b"
    else:
        val_label, val_color = "Keine KGV-Daten", "#555"

    # ── Analyst Rating ─────────────────────────────────────────────────────
    rating     = (fund.get("analyst_rating") or "–").upper()
    n_analysts = fund.get("num_analysts") or "?"
    target     = fund.get("target_price")
    upside     = ((target / price) - 1) * 100 if target and price else None

    # ── News ────────────────────────────────────────────────────────────────
    news_raw = fund.get("news", [])
    news     = [
        {"title": n.get("title",""), "link": n.get("link",""), "publisher": n.get("publisher","")}
        for n in news_raw[:4]
        if n.get("title")
    ]

    return {
        "ticker":      ticker,
        "name":        name,
        "price":       price,
        "info":        info,
        "fund":        fund,
        "pe":          pe,
        "peg":         peg,
        "eps_growth":  eps_growth,
        "val_label":   val_label,
        "val_color":   val_color,
        "rating":      rating,
        "n_analysts":  n_analysts,
        "target":      target,
        "upside":      upside,
        "ta_monthly":  ta_monthly,
        "ta_weekly":   ta_weekly,
        "ta_daily":    ta_daily,
        "ta_align":    ta_align,
        "ta_dir":      ta_dir,
        "news":        news,
        "mtf":         mtf,
    }


@st.cache_data(ttl=3600, show_spinner=False)
def _best_option(ticker: str, dte_min: int, dte_max: int, strategy: str = "Cash Covered Put") -> dict | None:
    """Bestes Option-Setup für einen DTE-Bereich."""
    try:
        df = scan_ticker(
            ticker=ticker,
            strategy=strategy,
            delta_min=-0.35,
            delta_max=-0.05,
            dte_min=dte_min,
            dte_max=dte_max,
            iv_min=0.0,
            premium_min=0.01,
            min_oi=1,
            otm_min=0.0,
            otm_max=40.0,
            require_valid_market=False,
            max_spread_pct=999.0,
        )
        if df.empty:
            return None
        row = df.iloc[0]
        return {
            "strike":   float(row.get("Strike", 0)),
            "expiry":   row.get("Verfall", ""),
            "dte":      int(row.get("DTE", 0)),
            "premium":  float(row.get("Prämie", 0)),
            "rendite":  float(row.get("Rendite % Laufzeit", 0)),
            "crv":      float(row.get("CRV Score", 0)),
            "otm":      float(row.get("OTM %", 0)),
            "delta":    float(row.get("Delta", 0)),
            "iv":       float(row.get("IV %", 0)),
        }
    except Exception:
        return None


def _fmt(val, dec=2, suffix="") -> str:
    if val is None:
        return "–"
    try:
        s = f"{val:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{s}{suffix}"
    except Exception:
        return str(val)


def _chg_color(chg: float | None) -> str:
    if chg is None:
        return "#888"
    return "#22c55e" if chg >= 0 else "#ef4444"


def _chg_icon(chg: float | None) -> str:
    if chg is None:
        return ""
    return "▲" if chg >= 0 else "▼"


# ══════════════════════════════════════════════════════════════════════════════
# UI KOMPONENTEN
# ══════════════════════════════════════════════════════════════════════════════

def _render_option_row(label: str, opt: dict | None) -> str:
    """Rendert eine Optionszeile als Markdown."""
    if opt is None:
        return f"**{label}:** keine Optionen gefunden"
    try:
        exp = pd.to_datetime(opt["expiry"])
        exp_str = exp.strftime("%d.%m.%Y")
    except Exception:
        exp_str = str(opt["expiry"])
    prem_total = round(opt["premium"] * 100)
    return (
        f"**{label}:** Strike ${opt['strike']:.0f} · Verfall {exp_str} · "
        f"Prämie **${_fmt(opt['premium'])}** ({prem_total} USD/Kontrakt) · "
        f"Rendite **{_fmt(opt['rendite'])} %** · OTM {_fmt(opt['otm'],1)}% · "
        f"Δ {opt['delta']:.2f} · IV {_fmt(opt['iv'],0)}% · CRV {opt['crv']:.0f}"
    )


def _render_stock_card(data: dict, strategy: str, show_options: bool) -> None:
    """Rendert eine komplette Aktien-Karte (Expander)."""
    ticker  = data["ticker"]
    name    = data["name"]
    price   = data["price"]
    info    = data["info"]
    fund    = data["fund"]

    # Kursänderung
    prev    = info.get("prev_close")
    chg_pct = ((price / prev) - 1) * 100 if price and prev else None
    cc      = _chg_color(chg_pct)
    ci      = _chg_icon(chg_pct)

    price_str  = f"${_fmt(price)}" if price else "–"
    chg_str    = f"{ci} {_fmt(abs(chg_pct), 1)}%" if chg_pct is not None else ""

    header_icon = (
        "🟢" if "bullish" in (data["ta_dir"] or "") else
        "🔴" if "bearish" in (data["ta_dir"] or "") else "🟡"
    )

    with st.expander(
        f"{header_icon} **{ticker}** — {name} · {price_str}  "
        f"({chg_str})  ·  TA: {data['ta_daily']}",
        expanded=False,
    ):
        left, right = st.columns([3, 2])

        with left:
            # ── Was macht die Firma? ───────────────────────────────────────
            desc = (info.get("description") or "").strip()
            if desc:
                st.markdown(
                    f"<div style='font-size:0.83rem;color:#bbb;margin-bottom:8px'>{desc[:280]}...</div>",
                    unsafe_allow_html=True,
                )

            # ── News ──────────────────────────────────────────────────────
            st.markdown("**📰 Aktuelle News**")
            news = data.get("news", [])
            if news:
                for n in news:
                    link  = n.get("link", "")
                    title = n.get("title", "")
                    pub   = n.get("publisher", "")
                    pub_str = f" _{pub}_" if pub else ""
                    if link:
                        st.markdown(f"→ [{title}]({link}){pub_str}")
                    else:
                        st.markdown(f"→ {title}{pub_str}")
            else:
                st.markdown("_Keine aktuellen News verfügbar._")

        with right:
            # ── Fundamentals ──────────────────────────────────────────────
            st.markdown("**💹 Fundamentals**")
            pe       = data["pe"]
            peg      = data["peg"]
            growth   = data["eps_growth"]
            target   = data["target"]
            upside   = data["upside"]
            rating   = data["rating"]
            n_an     = data["n_analysts"]
            market_cap = info.get("market_cap")
            beta       = info.get("beta")

            mcap_str = "–"
            if market_cap:
                if market_cap >= 1e12: mcap_str = f"${market_cap/1e12:.1f}T"
                elif market_cap >= 1e9: mcap_str = f"${market_cap/1e9:.1f}B"
                else: mcap_str = f"${market_cap/1e6:.0f}M"

            rows = []
            if pe:       rows.append(f"KGV (fwd): **{_fmt(pe, 1)}x**")
            if peg:      rows.append(f"PEG: **{_fmt(peg, 1)}x**")
            if growth:   rows.append(f"EPS-Wachstum: **{_fmt(growth*100, 0)}%**")
            if target:   rows.append(f"Kursziel: **${_fmt(target, 0)}** ({'+' if upside and upside>0 else ''}{_fmt(upside,0)}%)" if upside else f"Kursziel: **${_fmt(target,0)}**")
            rows.append(f"Analysten: **{rating}** ({n_an})")
            if beta:     rows.append(f"Beta: **{_fmt(beta, 1)}**")
            rows.append(f"Marktkapitalisierung: **{mcap_str}**")

            for r in rows:
                st.markdown(r)

            # Bewertungs-Badge
            val_label = data["val_label"]
            val_color = data["val_color"]
            st.markdown(
                f"<div style='margin-top:6px;padding:4px 10px;"
                f"background:rgba(255,255,255,0.05);border-radius:6px;"
                f"border-left:3px solid {val_color};font-size:0.82rem;color:{val_color}'>"
                f"📊 {val_label}</div>",
                unsafe_allow_html=True,
            )

        # ── Technische Analyse ─────────────────────────────────────────────────
        st.markdown("---")
        st.markdown("**📊 Technische Analyse — Stillhalter Trend Model · Stochastik · MACD**")
        ta1, ta2, ta3, ta4 = st.columns(4)
        ta1.markdown(f"🗓️ **Langfristig (1M)**\n\n{data['ta_monthly']}")
        ta2.markdown(f"📅 **Mittelfristig (1W)**\n\n{data['ta_weekly']}")
        ta3.markdown(f"📆 **Kurzfristig (1D)**\n\n{data['ta_daily']}")
        align_col = "#22c55e" if data["ta_dir"] == "bullish" else ("#ef4444" if data["ta_dir"] == "bearish" else "#f59e0b")
        ta4.markdown(
            f"🎯 **TF-Alignment**\n\n"
            f"<span style='color:{align_col};font-weight:700'>{data['ta_dir'].upper() if data['ta_dir'] else '–'}</span> "
            f"({data['ta_align']:.0f}/100)",
            unsafe_allow_html=True,
        )

        # ── Stochastik Details ─────────────────────────────────────────────
        mtf = data.get("mtf")
        if mtf:
            stoch_rows = []
            for tf_label, tf_obj in [("1D", mtf.tf_1d), ("1W", mtf.tf_1w), ("1M", mtf.tf_1m)]:
                if tf_obj:
                    sk  = tf_obj.stoch_k
                    rsi = tf_obj.rsi
                    hist_val = tf_obj.macd_hist
                    stoch_icon = "🟢 Überverkauft" if sk < 20 else ("🔴 Überkauft" if sk > 80 else "⚪ Neutral")
                    rsi_icon   = "🟢" if rsi < 30 else ("🔴" if rsi > 70 else "⚪")
                    macd_icon  = "📈" if tf_obj.macd_cross_bullish else ("📉" if tf_obj.macd_cross_bearish else ("▲" if hist_val > 0 else "▼"))
                    stoch_rows.append({
                        "TF": tf_label,
                        "Stoch %K": f"{sk:.0f} {stoch_icon}",
                        "RSI": f"{rsi:.0f} {rsi_icon}",
                        "MACD Hist.": f"{hist_val:+.4f} {macd_icon}",
                        "SC Trend": "↑ Bull" if tf_obj.ema_bullish else "↓ Bear",
                    })
            if stoch_rows:
                st.dataframe(pd.DataFrame(stoch_rows), hide_index=True, use_container_width=True, height=130)

        # ── Optionsempfehlungen ────────────────────────────────────────────
        if show_options:
            st.markdown("---")
            st.markdown(f"**💰 Optionsempfehlung — {strategy}**")
            opt_cols = st.columns(3)

            with st.spinner("Lade Optionen..."):
                opt_wk = _best_option(ticker, 3,   9,  strategy)
                opt_mo = _best_option(ticker, 20,  45, strategy)
                opt_qt = _best_option(ticker, 50, 100, strategy)

            with opt_cols[0]:
                st.markdown("**Woche (3–9 Tage)**")
                if opt_wk:
                    st.markdown(f"Strike **${opt_wk['strike']:.0f}**")
                    st.markdown(f"Prämie **${_fmt(opt_wk['premium'])}** ({round(opt_wk['premium']*100)} USD)")
                    st.markdown(f"Rendite **{_fmt(opt_wk['rendite'])} %**")
                    st.markdown(f"OTM **{_fmt(opt_wk['otm'],1)}%** · Δ {opt_wk['delta']:.2f}")
                else:
                    st.markdown("_Keine Wochenoption_")

            with opt_cols[1]:
                st.markdown("**Monat (20–45 Tage)**")
                if opt_mo:
                    st.markdown(f"Strike **${opt_mo['strike']:.0f}**")
                    st.markdown(f"Prämie **${_fmt(opt_mo['premium'])}** ({round(opt_mo['premium']*100)} USD)")
                    st.markdown(f"Rendite **{_fmt(opt_mo['rendite'])} %**")
                    st.markdown(f"OTM **{_fmt(opt_mo['otm'],1)}%** · Δ {opt_mo['delta']:.2f}")
                else:
                    st.markdown("_Keine Monatsoption_")

            with opt_cols[2]:
                st.markdown("**Quartal (50–100 Tage)**")
                if opt_qt:
                    st.markdown(f"Strike **${opt_qt['strike']:.0f}**")
                    st.markdown(f"Prämie **${_fmt(opt_qt['premium'])}** ({round(opt_qt['premium']*100)} USD)")
                    st.markdown(f"Rendite **{_fmt(opt_qt['rendite'])} %**")
                    st.markdown(f"OTM **{_fmt(opt_qt['otm'],1)}%** · Δ {opt_qt['delta']:.2f}")
                else:
                    st.markdown("_Keine Quartalsoption_")


_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "last_scan_cache.pkl"
)


def _load_scan_cache() -> dict | None:
    try:
        with open(_CACHE_PATH, "rb") as f:
            return pickle.load(f)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
h1, h2 = st.columns([1, 6])
with h1:
    st.markdown(get_logo_html("white", 36), unsafe_allow_html=True)
with h2:
    now_str = datetime.now().strftime("%A, %d. %B %Y · %H:%M Uhr")
    st.markdown(
        f'<div class="sc-page-title">📰 Markt Newsletter</div>'
        f'<div class="sc-page-subtitle">'
        f'Tägliches Börsen-Briefing · {now_str}</div>',
        unsafe_allow_html=True,
    )
st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── Einstellungen ──────────────────────────────────────────────────────────────
with st.expander("⚙️ Einstellungen", expanded=False):
    cfg1, cfg2, cfg3 = st.columns(3)
    with cfg1:
        nl_strategy = st.selectbox(
            "Optionsstrategie",
            ["Cash Covered Put", "Covered Call", "Short Strangle"],
        )
    with cfg2:
        n_news_items = st.slider("News pro Sektor", 2, 6, 4)
    with cfg3:
        n_stocks_deep = st.slider("Aktien im Deep Dive", 1, 3, 2)
    st.info(
        f"📌 **Quellen:** Yahoo Finance RSS · MarketWatch · yfinance News  \n"
        f"📌 **X/Twitter (manuell):** {TWITTER_ACCOUNTS}",
        icon="ℹ️",
    )

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 1 — MARKTÜBERBLICK (auto-load)
# ══════════════════════════════════════════════════════════════════════════════
with st.spinner("Lade Marktdaten…"):
    mkt = _market_overview()
    fg  = _fear_greed()

st.markdown("### 🌍 Marktüberblick")

idx_names = ["S&P 500", "NASDAQ", "DOW", "VIX"]
all_cols  = st.columns(len(idx_names) + 3)
for i, name in enumerate(idx_names):
    d = mkt.get(name, {})
    p, c = d.get("price"), d.get("chg")
    delta_str = f"{'+' if c and c>=0 else ''}{_fmt(c,2)}%" if c is not None else None
    all_cols[i].metric(name, _fmt(p, 2 if name != "VIX" else 1), delta_str)
for j, name in enumerate(["Gold", "Silber", "Bonds"]):
    d = mkt.get(name, {})
    p, c = d.get("price"), d.get("chg")
    delta_str = f"{'+' if c and c>=0 else ''}{_fmt(c,2)}%" if c is not None else None
    all_cols[len(idx_names) + j].metric(name, _fmt(p, 2), delta_str)

fg_score  = fg.get("score")
fg_rating = fg.get("rating", "–")
vix_val   = mkt.get("VIX", {}).get("price")

badges = []
if fg_score is not None:
    fc = "#22c55e" if fg_score >= 60 else "#ef4444" if fg_score <= 30 else "#f59e0b"
    badges.append(
        f"<span style='padding:3px 12px;border-radius:12px;border:1px solid {fc};"
        f"color:{fc};font-weight:700;font-size:0.82rem'>"
        f"😨 Fear &amp; Greed: {fg_score:.0f} — {fg_rating}</span>"
    )
vix_note = ""
if vix_val:
    if vix_val < 15:   vix_note, vc = "VIX niedrig — Prämienumgebung schwach", "#22c55e"
    elif vix_val < 20: vix_note, vc = "VIX normal — gute Prämienumgebung", "#f59e0b"
    elif vix_val < 30: vix_note, vc = "VIX erhöht — hohe Prämien, erhöhtes Risiko", "#f97316"
    else:              vix_note, vc = "VIX sehr hoch — Vorsicht bei Stillhalter-Trades!", "#ef4444"
    badges.append(
        f"<span style='padding:3px 12px;border-radius:12px;border:1px solid {vc};"
        f"color:{vc};font-size:0.82rem'>{vix_note}</span>"
    )
if badges:
    st.markdown(
        "<div style='margin:8px 0;display:flex;gap:10px;flex-wrap:wrap'>"
        + "".join(badges) + "</div>", unsafe_allow_html=True,
    )

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 2 — TOP-NEWS (globale Quellen, auto-load)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### 📰 Top-News")
st.caption("Quellen: Yahoo Finance · MarketWatch — automatisch aktualisiert alle 10 Min.")

with st.spinner("Lade globale News…"):
    global_news = _global_news(max_per_source=4)

if global_news:
    for item in global_news[:10]:
        title  = item["title"]
        link   = item.get("link", "")
        source = item.get("source", "")
        src_badge = f" <span style='font-size:0.72rem;color:#666'>· {source}</span>" if source else ""
        if link:
            st.markdown(
                f"→ [{title}]({link}){src_badge}",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(f"→ {title}")
else:
    st.caption("Keine globalen News verfügbar — RSS-Quellen temporär nicht erreichbar.")

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 3 — SEKTOREN-NEWS (Hauptteil, auto-load)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### 📊 Sektoren-News")
st.caption(
    "11 Sektoren · RSS-News je ETF + Aktien-News je Sektor · "
    "Kurse und TA auf Knopfdruck im Deep Dive."
)

for sname, sector in SECTORS.items():
    etf   = sector["etf"]
    color = sector["color"]

    with st.spinner(f"Lade {sname}…"):
        etf_p    = _sector_etf_perf(etf)
        rss_etf  = _rss_news(sector["rss"], max_items=int(n_news_items))
        # Aktien-spezifische News (kurz, für die Top-2 Aktien)
        stock_items: list[dict] = []
        for t in sector["stocks"][:2]:
            pdata = _quick_price(t)
            stock_items.append(pdata)

    d1  = etf_p.get("1d")
    d7  = etf_p.get("1w")
    d1c = "#22c55e" if d1 and d1 >= 0 else "#ef4444"
    d7c = "#22c55e" if d7 and d7 >= 0 else "#ef4444"

    # Sektor-Header
    header_html = (
        f"<div style='padding:8px 14px;background:rgba(255,255,255,0.04);"
        f"border-radius:8px;border-left:4px solid {color};margin-bottom:8px;"
        f"display:flex;align-items:center;gap:16px'>"
        f"<span style='font-weight:700;color:{color};font-size:1rem'>{sname}</span>"
        f"<span style='font-size:0.8rem;color:#aaa'>{etf}</span>"
    )
    if d1 is not None:
        header_html += (
            f"<span style='font-size:0.82rem;color:{d1c};font-weight:600'>{d1:+.2f}% heute</span>"
            f"<span style='font-size:0.82rem;color:{d7c}'>{d7:+.2f}% Woche</span>"
        )
    header_html += (
        f"<span style='font-size:0.75rem;color:#555;margin-left:auto'>"
        f"{sector['description'][:55]}…</span></div>"
    )
    st.markdown(header_html, unsafe_allow_html=True)

    col_news, col_stocks = st.columns([3, 2])

    with col_news:
        # ETF-RSS-News
        if rss_etf:
            for item in rss_etf:
                title = item["title"]
                link  = item.get("link", "")
                if link:
                    st.markdown(f"→ [{title}]({link})")
                else:
                    st.markdown(f"→ {title}")
        else:
            st.caption("Keine RSS-News verfügbar.")

    with col_stocks:
        for pdata in stock_items:
            t    = pdata["ticker"]
            nm   = pdata["name"]
            p    = pdata["price"]
            chg  = pdata["chg"]
            news = pdata["news"]
            icon = "🟢" if chg and chg >= 0 else ("🔴" if chg and chg < 0 else "🟡")
            cc   = "#22c55e" if chg and chg >= 0 else "#ef4444"
            chg_s = (f"+{chg:.1f}%" if chg >= 0 else f"{chg:.1f}%") if chg is not None else "–"
            price_s = f"${p:.2f}" if p else "–"

            st.markdown(
                f"<div style='margin-bottom:10px;padding:8px 10px;"
                f"background:rgba(255,255,255,0.03);border-radius:6px;"
                f"border-left:2px solid {color}'>"
                f"<div style='font-weight:700;font-size:0.88rem'>"
                f"{icon} <span style='color:#e2c97e'>{t}</span> "
                f"<span style='color:{cc}'>{chg_s}</span> "
                f"<span style='color:#666;font-size:0.75rem'>{price_s}</span></div>"
                f"<div style='font-size:0.77rem;color:#888;margin-top:2px'>{nm}</div>"
                + (
                    "<div style='font-size:0.78rem;color:#aaa;margin-top:4px'>"
                    + "<br>".join(
                        ("→ <a href='" + n["link"] + "' style='color:#aaa;text-decoration:none'>"
                         + n["title"][:70] + "…</a>")
                        if n.get("link") else ("→ " + n["title"][:70])
                        for n in news[:2]
                    )
                    + "</div>"
                    if news else ""
                )
                + "</div>",
                unsafe_allow_html=True,
            )

    st.markdown(
        "<div style='border-top:1px solid rgba(255,255,255,0.06);margin:12px 0 16px 0'></div>",
        unsafe_allow_html=True,
    )

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 4 — QUICK CATCH-UP (auf Knopfdruck, News + TA)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### ⚡ Quick Catch-Up — Aktienanalyse")
st.caption("Aktien wählen → vollständige News, TA-Signal und kurzer Stillhalter-Take.")

all_tickers = [t for s in SECTORS.values() for t in s["stocks"]]
sector_map  = {t: sn for sn, s in SECTORS.items() for t in s["stocks"]}
default_sel = [list(SECTORS.values())[i]["stocks"][0] for i in range(len(SECTORS))]

qc1, qc2 = st.columns([5, 1])
with qc1:
    selected_tickers = st.multiselect(
        "Aktien für Quick Catch-Up",
        options=all_tickers,
        default=default_sel[:6],
        key="nl_qcu_stocks",
    )
with qc2:
    qcu_btn = st.button("🔄 Laden", type="primary", key="nl_qcu_btn", use_container_width=True)

show_opts_qcu = st.checkbox("Optionsempfehlung pro Aktie anzeigen", value=False, key="nl_qcu_opts")
nl_strategy   = st.selectbox("Strategie", ["Cash Covered Put", "Covered Call", "Short Strangle"], key="nl_strat")

if qcu_btn:
    st.session_state["nl_qcu_run"]   = True
    st.session_state["nl_qcu_cards"] = []

if st.session_state.get("nl_qcu_run") and selected_tickers:
    export_cards: list[dict] = []

    for ticker in selected_tickers:
        with st.spinner(f"Analysiere {ticker}…"):
            data = _stock_analysis(ticker)

        price   = data["price"]
        name    = data["name"]
        prev    = data["info"].get("prev_close")
        chg_pct = ((price / prev) - 1) * 100 if price and prev else None
        ta_dir  = data.get("ta_dir", "") or ""
        news    = data.get("news", [])
        val_lbl = data.get("val_label", "–")
        val_col = data.get("val_color", "#888")
        rating  = data.get("rating", "–")
        target  = data.get("target")
        upside  = data.get("upside")

        icon = "🟢" if "bullish" in ta_dir else ("🔴" if "bearish" in ta_dir else "🟡")
        cc   = _chg_color(chg_pct)
        chg_s = (f"+{chg_pct:.1f}%" if chg_pct >= 0 else f"{chg_pct:.1f}%") if chg_pct is not None else "–"
        price_s = f"${_fmt(price)}" if price else "–"
        sec_tag = sector_map.get(ticker, "")

        ta_line = (
            f"{data['ta_daily']} (1T) · {data['ta_weekly']} (1W) · {data['ta_monthly']} (1M)"
        )

        opt_text = ""
        if show_opts_qcu:
            opt = _best_option(ticker, 20, 45, nl_strategy)
            if opt:
                try:
                    exp_d = pd.to_datetime(opt["expiry"]).strftime("%d.%m.")
                except Exception:
                    exp_d = str(opt["expiry"])
                opt_text = (
                    f"Short PUT {exp_d} @${opt['strike']:.0f} · "
                    f"Prämie ${_fmt(opt['premium'])} ({round(opt['premium']*100)} USD) · "
                    f"Rendite {_fmt(opt['rendite'])} %"
                )

        # Karte rendern
        news_html = "".join(
            f"→ <a href='{n['link']}' target='_blank' style='color:#ccc;text-decoration:none'>"
            f"{n['title'][:100]}…</a> <span style='color:#555;font-size:0.72rem'>{n.get('publisher','')}</span><br>"
            if n.get("link") else f"→ {n['title'][:100]}<br>"
            for n in news[:4]
        ) or "<span style='color:#555'>Keine aktuellen News.</span>"

        fundamentals_html = ""
        if rating and rating != "–":
            fundamentals_html += f"Analysten: <b>{rating}</b>"
        if target:
            fundamentals_html += f" · Kursziel: <b>${target:.0f}</b>"
            if upside:
                fundamentals_html += f" ({'+' if upside>0 else ''}{upside:.0f}%)"

        st.markdown(
            f"<div style='border:1px solid rgba(255,255,255,0.1);border-radius:10px;"
            f"padding:14px 18px;margin:8px 0;background:rgba(255,255,255,0.03)'>"
            # Kopfzeile
            f"<div style='font-size:1rem;font-weight:700;margin-bottom:6px'>"
            f"{icon} <span style='color:#e2c97e'>{ticker}</span> {name} &nbsp;"
            f"<span style='color:{cc}'>{chg_s}</span> &nbsp;"
            f"<span style='font-size:0.75rem;color:#666'>{price_s} · {sec_tag}</span></div>"
            # TA + Bewertung
            f"<div style='font-size:0.78rem;color:#888;margin-bottom:6px'>"
            f"{ta_line} &nbsp;·&nbsp; "
            f"<span style='color:{val_col}'>{val_lbl}</span>"
            + (f" &nbsp;·&nbsp; {fundamentals_html}" if fundamentals_html else "")
            + "</div>"
            # News
            f"<div style='font-size:0.83rem;color:#ccc;line-height:1.6'>{news_html}</div>"
            # Stillhalter-Take
            + (
                f"<div style='font-size:0.82rem;color:#a8c5ff;margin-top:8px;padding-top:6px;"
                f"border-top:1px solid rgba(255,255,255,0.07)'>"
                f"👉 <b>Stillhalter-Take:</b> {opt_text}</div>"
                if opt_text else ""
            )
            + "</div>",
            unsafe_allow_html=True,
        )

        export_cards.append({
            "ticker": ticker, "name": name, "chg": chg_s, "icon": icon,
            "news": [n["title"] for n in news[:2]],
            "ta": ta_line, "val": val_lbl, "opt": opt_text,
        })

    st.session_state["nl_qcu_cards"] = export_cards

elif not st.session_state.get("nl_qcu_run"):
    st.info("👆 Aktien auswählen und **Laden** drücken.")

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 5 — DEEP DIVE (ein Sektor, volle Analyse)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### 🔍 Deep Dive — Einzelsektor")

dd1, dd2 = st.columns([4, 1])
with dd1:
    dd_sector = st.selectbox("Sektor", list(SECTORS.keys()), key="nl_dd_sector")
with dd2:
    dd_btn = st.button("🔍 Laden", type="primary", key="nl_dd_btn", use_container_width=True)

if dd_btn:
    sector  = SECTORS[dd_sector]
    etf     = sector["etf"]
    color   = sector["color"]
    etf_p   = _sector_etf_perf(etf)
    d1, d7  = etf_p.get("1d"), etf_p.get("1w")

    st.markdown(
        f"<div style='padding:10px 16px;background:rgba(255,255,255,0.04);"
        f"border-radius:8px;border-left:4px solid {color};margin-bottom:12px'>"
        f"<b style='color:{color}'>{dd_sector}</b> · {etf}"
        + (f" · <b>{d1:+.2f}%</b> heute · <b>{d7:+.2f}%</b> Woche" if d1 is not None else "")
        + f"<br><span style='font-size:0.83rem;color:#aaa'>{sector['description']}</span></div>",
        unsafe_allow_html=True,
    )
    rss_dd = _rss_news(sector["rss"], max_items=6)
    if rss_dd:
        st.markdown("**📡 Sektor-News (RSS)**")
        for item in rss_dd:
            link, title = item.get("link", ""), item["title"]
            st.markdown(f"→ [{title}]({link})" if link else f"→ {title}")
        st.markdown("---")

    for ticker in sector["stocks"][:int(n_stocks_deep)]:
        with st.spinner(f"Analysiere {ticker}…"):
            data = _stock_analysis(ticker)
        _render_stock_card(data, nl_strategy, show_options=True)
else:
    st.info("👆 Sektor auswählen und **Laden** drücken.")

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 6 — OPTIONSEMPFEHLUNGEN (knapp, aus Scan-Cache)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### 💰 Optionsempfehlungen")
st.caption("Top-Trades aus dem letzten Watchlist-Scan — kurz und knapp.")

cached = _load_scan_cache()
if cached and not cached.get("results", pd.DataFrame()).empty:
    df_tip     = cached["results"].copy()
    scan_ts    = cached.get("timestamp")
    scan_strat = cached.get("strategy", "–")
    age_str    = ""
    if scan_ts:
        age_min = int((datetime.now() - scan_ts).total_seconds() / 60)
        age_str = f" · vor {age_min} Min." if age_min < 60 else f" · {scan_ts.strftime('%d.%m. %H:%M')}"

    sort_col = next(
        (c for c in ["CRV Score", "Konvergenz", "Rendite % Laufzeit"] if c in df_tip.columns), None
    )
    top5 = (
        df_tip.sort_values(sort_col, ascending=False).drop_duplicates(subset=["Ticker"]).head(5)
        if sort_col else df_tip.head(5)
    )

    st.caption(f"Strategie: **{scan_strat}**{age_str}")

    disp_rows = []
    for _, row in top5.iterrows():
        try:
            exp_d = pd.to_datetime(row.get("Verfall", "")).strftime("%d.%m.%Y")
        except Exception:
            exp_d = str(row.get("Verfall", ""))
        disp_rows.append({
            "Ticker":    row.get("Ticker", ""),
            "Strategie": str(row.get("Strategie", "Short PUT")),
            "Strike":    f"${float(row.get('Strike', 0)):.0f}",
            "Verfall":   exp_d,
            "Prämie":    f"${_fmt(float(row.get('Prämie', 0)))}",
            "Rendite":   f"{_fmt(float(row.get('Rendite % Laufzeit', 0)))} %",
            "OTM":       f"{_fmt(float(row.get('OTM %', 0)), 1)} %",
            "CRV":       f"{float(row.get('CRV Score', 0)):.0f}" if "CRV Score" in row else "–",
        })

    st.dataframe(pd.DataFrame(disp_rows), hide_index=True, use_container_width=True)

    tc1, tc2 = st.columns(2)
    with tc1:
        if st.button("➜ Trade Cards öffnen", type="secondary"):
            st.switch_page("pages/17_Trade_Cards.py")
    with tc2:
        if st.button("➜ Watchlist Scanner", type="secondary"):
            st.switch_page("pages/04_Watchlist_Scanner.py")
else:
    st.info(
        "Kein Scan-Ergebnis — bitte zuerst einen Scan im **Watchlist Scanner** durchführen.",
        icon="ℹ️",
    )

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# SECTION 7 — EXPORT (Newsletter-Text)
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### 📤 Newsletter exportieren")
st.caption("Kompletten Newsletter als Text generieren — für WhatsApp, E-Mail oder Blog.")

if st.button("📋 Text generieren", type="primary", key="nl_export_btn"):
    today = datetime.now().strftime("%d.%m.%Y")
    L = [
        f"📰 STILLHALTER MARKT-NEWSLETTER — {today}",
        "Tägliches Börsen-Briefing · Stillhalter AI App",
        "",
        "═══════════════════════════════════",
        "🌍 MARKTÜBERBLICK",
        "═══════════════════════════════════",
    ]
    for nm in ["S&P 500", "NASDAQ", "DOW", "VIX", "Gold", "Silber"]:
        d = mkt.get(nm, {})
        p, c = d.get("price"), d.get("chg")
        if p:
            cs = f" ({'+' if c and c>=0 else ''}{c:.2f}%)" if c is not None else ""
            L.append(f"  {nm}: {p:.2f}{cs}")
    if fg_score:
        L.append(f"  Fear & Greed: {fg_score:.0f} — {fg_rating}")
    if vix_note:
        L.append(f"  {vix_note}")
    L.append("")

    # Globale Top-News
    if global_news:
        L += ["═══════════════════════════════════", "📰 TOP-NEWS", "═══════════════════════════════════"]
        for item in global_news[:6]:
            L.append(f"  → {item['title']}")
        L.append("")

    # Sektor-News
    L += ["═══════════════════════════════════", "📊 SEKTOREN-NEWS", "═══════════════════════════════════"]
    for sname, sector in SECTORS.items():
        etf_p = _sector_etf_perf(sector["etf"])
        d1 = etf_p.get("1d")
        d7 = etf_p.get("1w")
        rss_items = _rss_news(sector["rss"], max_items=3)
        L.append(
            f"\n{sname} ({sector['etf']})"
            + (f" · {d1:+.2f}% heute | {d7:+.2f}% Woche" if d1 is not None else "")
        )
        for item in rss_items:
            L.append(f"  → {item['title']}")

    L.append("")

    # Quick Catch-Up
    qcu_cards = st.session_state.get("nl_qcu_cards", [])
    if qcu_cards:
        L += ["═══════════════════════════════════", "⚡ QUICK CATCH-UP", "═══════════════════════════════════", ""]
        for c in qcu_cards:
            L.append(f"{c['icon']} {c['ticker']} {c['name']} ({c['chg']})")
            for headline in c.get("news", [])[:2]:
                L.append(f"  → {headline[:100]}")
            if c.get("opt"):
                L.append(f"  👉 Stillhalter-Take: {c['opt']}")
            L.append("")

    # Optionsempfehlungen
    if cached and not cached.get("results", pd.DataFrame()).empty:
        L += ["═══════════════════════════════════", "💰 OPTIONSEMPFEHLUNGEN", "═══════════════════════════════════"]
        for row in disp_rows:
            L.append(
                f"  {row['Ticker']} · {row['Strategie']} · Strike {row['Strike']} · "
                f"Verfall {row['Verfall']} · Prämie {row['Prämie']} · Rendite {row['Rendite']}"
            )
        L.append("")

    L += [
        "─────────────────────────────────────",
        "⚠️ Keine Anlageberatung — nur zu Bildungszwecken.",
        "Optionshandel birgt erhebliche Risiken.",
        f"Stillhalter AI App · {today}",
    ]

    st.code("\n".join(L), language="text")
    st.caption("💡 Kopier-Symbol oben rechts → direkt in WhatsApp einfügen.")
