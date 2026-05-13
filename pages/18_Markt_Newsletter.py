"""
Stillhalter AI App — Markt Newsletter
Täglicher Börsennewsletter: 11 Sektoren · Fundamentals · TA · Optionsempfehlung.

Quellen: Yahoo Finance RSS · yfinance News · MarketWatch · CNN Fear & Greed
TA:      Stillhalter Trend Model (1M · 1W · 1D) · Dual Stochastik · MACD Pro
"""

from __future__ import annotations
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

# ── Twitter/X Accounts für schnelle News (via RSS-Proxy) ──────────────────────
TWITTER_RSS_NOTE = (
    "**📌 Schnellste Quellen (manuell beobachten):** "
    "@WSJmarkets · @business (Bloomberg) · @CNBC · @ReutersBiz · "
    "@elerianm (Mohamed El-Erian) · @LizAnnSonders (Schwab) · "
    "@zerohedge · @FinancialTimes — "
    "Twitter/X-API erfordert kostenpflichtigen Zugang ($100/Mo), "
    "daher hier RSS-basierte News."
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
        r = requests.get(
            url,
            timeout=10,
            headers={"User-Agent": "StillhalterApp/3.0"},
        )
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
        f'11 Sektoren · Fundamentals · TA (1M · 1W · 1D) · Optionsempfehlung · '
        f'{now_str}</div>',
        unsafe_allow_html=True,
    )
st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── Einstellungen ──────────────────────────────────────────────────────────────
with st.expander("⚙️ **Einstellungen**", expanded=False):
    cfg1, cfg2, cfg3 = st.columns(3)
    with cfg1:
        nl_strategy = st.selectbox(
            "Optionsstrategie",
            ["Cash Covered Put", "Covered Call", "Short Strangle"],
            help="Welche Strategie soll für die Optionsempfehlungen genutzt werden?",
        )
    with cfg2:
        show_options_toggle = st.checkbox(
            "Optionsempfehlungen laden",
            value=True,
            help="Deaktivieren für schnelleres Laden (ohne Optionsdaten)",
        )
    with cfg3:
        n_stocks = st.slider("Aktien pro Sektor", 1, 3, 2)
    st.markdown(
        f"> ℹ️ {TWITTER_RSS_NOTE}",
        unsafe_allow_html=True,
    )

# ══════════════════════════════════════════════════════════════════════════════
# MARKTÜBERBLICK
# ══════════════════════════════════════════════════════════════════════════════
with st.spinner("Lade Marktdaten..."):
    mkt   = _market_overview()
    fg    = _fear_greed()

st.markdown("### 🌍 Marktüberblick")

# Indices
idx_names = ["S&P 500", "NASDAQ", "DOW", "VIX"]
idx_cols  = st.columns(len(idx_names) + 3)
for i, name in enumerate(idx_names):
    d = mkt.get(name, {})
    p = d.get("price")
    c = d.get("chg")
    cc = _chg_color(c)
    delta_str = f"{'+' if c and c>=0 else ''}{_fmt(c,2)}%" if c is not None else None
    idx_cols[i].metric(name, _fmt(p, 2 if name != "VIX" else 1), delta_str)

# Rohstoffe
for j, name in enumerate(["Gold", "Silber", "Bonds"]):
    d = mkt.get(name, {})
    p = d.get("price")
    c = d.get("chg")
    delta_str = f"{'+' if c and c>=0 else ''}{_fmt(c,2)}%" if c is not None else None
    idx_cols[len(idx_names) + j].metric(name, _fmt(p, 2), delta_str)

# Fear & Greed
fg_score  = fg.get("score")
fg_rating = fg.get("rating", "–")
if fg_score is not None:
    fg_color = (
        "#22c55e" if fg_score >= 60 else
        "#ef4444" if fg_score <= 30 else "#f59e0b"
    )
    st.markdown(
        f"<div style='display:inline-block;padding:4px 14px;background:rgba(255,255,255,0.05);"
        f"border-radius:20px;border:1px solid {fg_color};font-size:0.85rem;margin-top:4px'>"
        f"😨 <b>Fear &amp; Greed:</b> "
        f"<span style='color:{fg_color};font-weight:700'>{fg_score:.0f} — {fg_rating}</span></div>",
        unsafe_allow_html=True,
    )
else:
    st.caption("Fear & Greed: nicht verfügbar")

# VIX Einschätzung
vix_val = mkt.get("VIX", {}).get("price")
if vix_val:
    if vix_val < 15:
        vix_note = "🟢 VIX niedrig — Optionsprämien gering, Markt entspannt"
    elif vix_val < 20:
        vix_note = "🟡 VIX normal — gute Prämienumgebung"
    elif vix_val < 30:
        vix_note = "🟠 VIX erhöht — höhere Prämien, aber höheres Risiko"
    else:
        vix_note = "🔴 VIX hoch — Prämien sehr attraktiv, aber erhöhte Marktvolatilität!"
    st.caption(vix_note)

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# 11 SEKTOREN ALS TABS
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("### 📊 Sektoren — Analyse & Optionsempfehlungen")

sector_names = list(SECTORS.keys())
tabs = st.tabs(sector_names)

for tab, sector_name in zip(tabs, sector_names):
    sector = SECTORS[sector_name]
    etf    = sector["etf"]
    color  = sector["color"]
    stocks = sector["stocks"][:int(n_stocks)]

    with tab:
        # ── Sektor-Header ────────────────────────────────────────────────────
        etf_perf = _sector_etf_perf(etf)
        perf_1d  = etf_perf.get("1d")
        perf_1w  = etf_perf.get("1w")
        etf_price = etf_perf.get("price")

        hc1, hc2 = st.columns([5, 2])
        with hc1:
            st.markdown(
                f"<div style='padding:8px 14px;background:rgba(255,255,255,0.04);"
                f"border-radius:8px;border-left:4px solid {color};margin-bottom:12px'>"
                f"<b style='color:{color}'>{etf}</b> · "
                f"{sector['description']}</div>",
                unsafe_allow_html=True,
            )
        with hc2:
            mc1, mc2, mc3 = st.columns(3)
            mc1.metric(f"{etf}", _fmt(etf_price,2,"$") if etf_price else "–")
            mc2.metric("Heute", f"{_fmt(perf_1d,2)}%" if perf_1d is not None else "–",
                       delta=f"{perf_1d:+.2f}%" if perf_1d is not None else None)
            mc3.metric("1 Woche", f"{_fmt(perf_1w,2)}%" if perf_1w is not None else "–",
                       delta=f"{perf_1w:+.2f}%" if perf_1w is not None else None)

        # ── Sektor-News (RSS) ────────────────────────────────────────────────
        rss_news = _rss_news(sector["rss"], max_items=4)
        if rss_news:
            with st.expander(f"📡 Sektor-News ({etf})", expanded=False):
                for item in rss_news:
                    title = item["title"]
                    link  = item.get("link", "")
                    if link:
                        st.markdown(f"→ [{title}]({link})")
                    else:
                        st.markdown(f"→ {title}")

        # ── Aktien-Karten ────────────────────────────────────────────────────
        for ticker in stocks:
            with st.spinner(f"Analysiere {ticker}..."):
                data = _stock_analysis(ticker)
            _render_stock_card(data, nl_strategy, show_options_toggle)

# ══════════════════════════════════════════════════════════════════════════════
# NEWSLETTER EXPORT
# ══════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)
with st.expander("📤 **Newsletter Export** — Komplett-Zusammenfassung für WhatsApp/Email", expanded=False):
    st.markdown(
        "Der Export generiert eine Text-Zusammenfassung des Marktüberblicks "
        "und aller Sektoren — bereit zum Kopieren in WhatsApp oder Email-Newsletter."
    )

    if st.button("📋 Zusammenfassung generieren", type="primary"):
        lines = [
            f"📰 STILLHALTER MARKT NEWSLETTER — {datetime.now().strftime('%d.%m.%Y')}",
            "",
            "═══ MARKTÜBERBLICK ═══",
        ]
        for name in ["S&P 500", "NASDAQ", "DOW", "VIX", "Gold", "Silber"]:
            d = mkt.get(name, {})
            p = d.get("price")
            c = d.get("chg")
            if p:
                chg_s = f" ({'+' if c and c>=0 else ''}{c:.2f}%)" if c is not None else ""
                lines.append(f"  {name}: {p:.2f}{chg_s}")
        if fg_score:
            lines.append(f"  Fear & Greed: {fg_score:.0f} — {fg_rating}")
        lines.append("")

        for sector_name, sector in SECTORS.items():
            lines.append(f"═══ {sector_name.upper()} ═══")
            etf_p = _sector_etf_perf(sector["etf"])
            if etf_p.get("1d") is not None:
                lines.append(f"  {sector['etf']}: {etf_p.get('1d',0):+.2f}% heute")
            for ticker in sector["stocks"][:2]:
                data = _stock_analysis(ticker)
                p    = data.get("price")
                name = data.get("name", ticker)
                lines.append(f"\n  📌 {ticker} — {name}")
                if p:
                    prev  = data["info"].get("prev_close")
                    chg_  = ((p/prev)-1)*100 if prev and p else None
                    lines.append(f"     Kurs: ${p:.2f}" + (f" ({chg_:+.1f}%)" if chg_ else ""))
                lines.append(f"     TA: {data['ta_daily']} (1D) · {data['ta_weekly']} (1W)")
                lines.append(f"     Bewertung: {data['val_label']}")
                if data["news"]:
                    lines.append(f"     News: {data['news'][0]['title'][:80]}")
                opt = _best_option(ticker, 20, 45, nl_strategy)
                if opt:
                    lines.append(
                        f"     Option (Monat): Strike ${opt['strike']:.0f} · "
                        f"Prämie ${opt['premium']:.2f} · {opt['rendite']:.1f}% Rendite"
                    )
            lines.append("")

        newsletter_text = "\n".join(lines)
        st.code(newsletter_text, language="text")
        st.caption("💡 Tipp: Oben rechts im Code-Block auf das Kopier-Symbol klicken → direkt in WhatsApp einfügen.")
