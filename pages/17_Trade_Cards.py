"""
Stillhalter AI App — Trade Cards
Generiert WhatsApp-fertige Trading-Ideen im exakten Format.
"""

import streamlit as st
import pandas as pd
import pickle
import os
import re
import requests
import xml.etree.ElementTree as ET
import email.utils as _eutils
from datetime import datetime, timedelta, date

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
) -> str:
    """Generiert den kompletten WhatsApp-Text einer Trade Card."""

    premium_total  = round(premium * 100)
    dte_safe       = max(dte, 1)
    ann_rendite    = rendite_lz * 365 / dte_safe
    otm_pct        = abs((price_now - strike) / price_now * 100) if price_now > 0 else 0
    assign_prob    = round(abs(delta) * 100)
    cash_reserve   = int(strike * 100)

    # Roll-Potenzial: 1-Sigma wöchentliche Bewegung (IV × Kurs × √(7/365))
    roll_usd = 0.0
    if price_now > 0 and iv > 0:
        roll_usd = price_now * (iv / 100) * (7 / 365) ** 0.5

    # Absicherungs-Zeilen strukturiert aufbauen
    absi_lines = []
    if trend_note:
        absi_lines.append(f"  • {trend_note}")
    absi_lines.append(
        f"  • Delta {delta:.2f} — Einbuchungsrisiko {'konservativ (≤20%)' if assign_prob <= 20 else 'moderat' if assign_prob <= 35 else 'erhöht'}"
    )
    if iv > 15:
        absi_lines.append("  • Rollbar (IV ausreichend hoch)")
    absi_lines.append(f"  • Cash Reserve: USD {cash_reserve:,} pro Kontrakt einplanen".replace(",", "."))

    ta_block = "\n".join(ta_lines) if ta_lines else "  • Keine TA-Daten"

    roll_line = ""
    if roll_usd > 0:
        roll_line = (
            f"\n🔄 Roll-Potenzial: ±USD {_fmt_num(roll_usd)} pro Woche "
            f"(1σ bei IV {iv:.0f}%)\n"
            f"   → Rollbar auf Strike -{_fmt_num(roll_usd)} nach einer Woche möglich"
        )

    sektor_str  = sektor.upper() if sektor else "–"
    crv_str     = f"{crv:.0f}" if crv else "–"
    company_str = f"\n🏢 {company_name}" if company_name else ""

    lines = [
        "Aus Sicht der Technischen Analyse finde ich folgende Optionen spannend:",
        "",
        f"🔔 Trading Idee | {ticker} {trade_exp} @{strike:.0f} {option_type} verkaufen",
        "",
        f"💰 Prämie: {_fmt_num(premium)} USD | {premium_total} USD gesamt (1x Kontrakt)",
        f"📈 Rendite: ~{_fmt_num(ann_rendite, 1)}% p.a. / {_fmt_num(rendite_lz)}% Laufzeit ({dte}T)",
        f"📉 Strategie: {strategie}",
        f"🎯 Strike: USD {strike:.2f} ({_fmt_num(otm_pct, 1)}% OTM)",
        f"📅 Laufzeit: {trade_exp} ({dte} Tage)",
        f"⚡ Einbuchungswahrscheinlichkeit: ~{assign_prob}% (Delta {delta:.2f})",
        "",
        f"📊 Technische Analyse (1D):",
        ta_block,
        roll_line,
        f"🛡️ Absicherung:",
        "\n".join(absi_lines),
        "",
        f"⭐ CRV Score: {crv_str}  ·  IV: {iv:.0f}%  ·  Sektor: {sektor_str}",
        company_str,
        "",
        f"📰 Aktuelle News {ticker}:",
        news_text,
        "",
        f"📋 Hintergrund:",
        background,
    ]
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════════════════
# UI
# ══════════════════════════════════════════════════════════════════════════════

h1, h2 = st.columns([1, 6])
with h1:
    st.markdown(get_logo_html("white", 36), unsafe_allow_html=True)
with h2:
    st.markdown(
        '<div class="sc-page-title">📤 Trade Cards</div>'
        '<div class="sc-page-subtitle">'
        'WhatsApp-fertige Trading-Ideen — 1 Klick zum Kopieren</div>',
        unsafe_allow_html=True,
    )
st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── Cache laden ────────────────────────────────────────────────────────────────
cached = _load_scan_cache()

if cached is None or cached.get("results") is None or cached["results"].empty:
    st.warning(
        "**Kein Scan-Ergebnis vorhanden.**\n\n"
        "Bitte zuerst im **Watchlist Scanner** oder **Top 9 Trading Ideen** einen Scan durchführen. "
        "Die besten Ergebnisse werden hier automatisch geladen.",
        icon="⚠️",
    )
    if st.button("➜ Zum Watchlist Scanner", type="primary"):
        st.switch_page("pages/04_Watchlist_Scanner.py")
    st.stop()

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

# ── Einstellungen ──────────────────────────────────────────────────────────────
with st.expander("⚙️ **Einstellungen**", expanded=False):
    s1, s2, s3 = st.columns(3)
    with s1:
        n_cards = st.number_input("Anzahl Trade Cards", 1, 5, 3)
    with s2:
        sort_col = st.selectbox(
            "Sortierung",
            [c for c in ["CRV Score", "Konvergenz", "Rendite % Laufzeit", "Rendite %/Tag"] if c in df_all.columns],
        )
    with s3:
        news_count = st.number_input("News-Zeilen pro Trade", 1, 6, 3)

# Top N nach gewählter Sortierung — nur Optionen mit sinnvollem Delta
_df_sorted = df_all.sort_values(sort_col, ascending=False).drop_duplicates(subset=["Ticker"])
if "Delta" in _df_sorted.columns:
    _df_sorted = _df_sorted[_df_sorted["Delta"].abs() >= 0.10]
top_df = _df_sorted.head(int(n_cards)).reset_index(drop=True)

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── Karten ────────────────────────────────────────────────────────────────────
all_card_texts: list[str] = []

for idx, row in top_df.iterrows():
    ticker   = row.get("Ticker", "")
    strike   = float(row.get("Strike", 0))
    expiry   = row.get("Verfall", "")
    premium  = float(row.get("Prämie", 0))
    rendite  = float(row.get("Rendite % Laufzeit", 0))
    otm_pct  = float(row.get("OTM %", 0))
    crv      = float(row.get("CRV Score", 0)) if "CRV Score" in row else 0.0

    option_type, strategie       = _get_strategy_type(row)
    trade_exp, german_exp, dte   = _fmt_expiry_trade(expiry)
    sr_note                      = _get_sr_level(ticker, option_type, strike)
    trend_note_auto              = _build_trend_note(row, otm_pct, sr_note)

    rank_icon = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][idx]

    with st.expander(
        f"{rank_icon} **{ticker}** — {trade_exp} @{strike:.0f} {option_type} · "
        f"Prämie {_fmt_num(premium)} USD · {dte} Tage · CRV {crv:.0f}",
        expanded=(idx == 0),
    ):
        # ── Stock-Daten + News laden ───────────────────────────────────────
        with st.spinner(f"Lade Daten & News für {ticker}…"):
            stock_data  = _cached_stock_data(ticker)
            info        = stock_data["info"]
            rss_items   = _fetch_ticker_news_rss(ticker, n=int(news_count))

        company_name = info.get("name", ticker)
        eng_desc     = (info.get("description") or "").strip()
        news_auto    = _format_news_text(rss_items)
        ath_pct_val  = _ath_pct(ticker, strike)

        # ── Zusätzliche Felder aus der Scan-Row ───────────────────────────
        delta_raw   = float(row.get("Delta", 0.0))
        iv_raw      = float(row.get("IV %", 0.0))
        sektor_raw  = str(row.get("Sektor", ""))
        # Kurs-Schätzung: aus Info-Objekt oder OTM-Back-Rechnung
        price_now_raw = float(info.get("price") or info.get("currentPrice") or 0.0)
        if price_now_raw <= 0 and otm_pct > 0:
            price_now_raw = strike / (1 - otm_pct / 100)
        ta_lines_built = _ta_zeilen(row)

        # ── Editierbare Felder ─────────────────────────────────────────────
        col_left, col_right = st.columns([3, 2])

        with col_left:
            st.markdown(f"**📋 {company_name} ({ticker})**")

            st.markdown(
                "<div style='font-size:0.78rem;color:#666;margin-bottom:2px'>"
                "Hintergrund-Text (bearbeiten → auf Deutsch, 2–3 Sätze)</div>",
                unsafe_allow_html=True,
            )
            # Englischen Text übersetzen, bearbeitbar
            if eng_desc:
                default_bg = _translate_de(eng_desc[:400])
            else:
                default_bg = f"{company_name} ist ein börsennotiertes Unternehmen."
            background = st.text_area(
                "Hintergrund",
                value=default_bg,
                height=110,
                key=f"bg_{ticker}_{idx}",
                label_visibility="collapsed",
            )

            st.markdown(
                "<div style='font-size:0.78rem;color:#666;margin-top:8px;margin-bottom:2px'>"
                "News (bearbeiten)</div>",
                unsafe_allow_html=True,
            )
            news_text = st.text_area(
                "News",
                value=news_auto,
                height=90,
                key=f"news_{ticker}_{idx}",
                label_visibility="collapsed",
            )

            st.markdown(
                "<div style='font-size:0.78rem;color:#666;margin-top:8px;margin-bottom:2px'>"
                "Absicherungs-Zeile (bearbeiten)</div>",
                unsafe_allow_html=True,
            )
            trend_note = st.text_input(
                "Absicherung",
                value=trend_note_auto,
                key=f"trend_{ticker}_{idx}",
                label_visibility="collapsed",
            )

        with col_right:
            st.markdown("**📊 Trade-Details**")
            ath_label = f"{_fmt_num(ath_pct_val, 0)}% unter ATH" if ath_pct_val else "ATH nicht verfügbar"
            ann_r = rendite * 365 / max(dte, 1)
            st.markdown(f"""
| | |
|---|---|
| **Strategie** | {strategie} |
| **Strike** | ${strike:.0f} |
| **{option_type}-Verfall** | {german_exp} ({dte} Tage) |
| **Prämie** | {_fmt_num(premium)} USD |
| **Gesamt (1x)** | {round(premium*100)} USD |
| **Rendite p.a.** | ~{_fmt_num(ann_r, 1)} % |
| **Rendite LZ** | {_fmt_num(rendite)} % |
| **Delta** | {delta_raw:.2f} |
| **IV** | {iv_raw:.0f} % |
| **OTM** | {_fmt_num(otm_pct, 1)} % |
| **ATH-Abstand** | {ath_label} |
| **CRV Score** | {crv:.0f} |
""")

        # ── Generierter Text ───────────────────────────────────────────────
        card_text = _build_card_text(
            ticker=ticker,
            trade_exp=trade_exp,
            strike=strike,
            option_type=option_type,
            premium=premium,
            rendite_lz=rendite,
            strategie=strategie,
            ath_dist=ath_pct_val,
            german_exp=german_exp,
            dte=dte,
            trend_note=trend_note,
            background=background,
            news_text=news_text,
            delta=delta_raw,
            iv=iv_raw,
            crv=crv,
            sektor=sektor_raw,
            company_name=company_name,
            ta_lines=ta_lines_built,
            price_now=price_now_raw,
        )

        all_card_texts.append(card_text)

        st.markdown("---")
        st.markdown("**📱 WhatsApp Text — direkt kopieren:**")
        st.code(card_text, language="text")

# ══════════════════════════════════════════════════════════════════════════════
# ALLE KARTEN + DISCLAIMER ZUSAMMEN
# ══════════════════════════════════════════════════════════════════════════════
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
