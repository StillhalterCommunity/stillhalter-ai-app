"""
Stillhalter AI App — Trade Cards
Generiert WhatsApp-fertige Trading-Ideen im exakten Format.
"""

import streamlit as st
import pandas as pd
import pickle
import os
from datetime import datetime

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


def _fmt_expiry_trade(expiry) -> tuple[str, str]:
    """Gibt (trading_notation, german_date) zurück. z.B. ("Mar20 '26", "20.03.2026")"""
    try:
        d = pd.to_datetime(expiry)
        month_abbr = d.strftime("%b")   # "Mar"
        day = str(d.day)                 # "20" (kein führendes 0)
        year = d.strftime("'%y")         # "'26"
        trade_str  = f"{month_abbr}{day} {year}"
        german_str = d.strftime("%d.%m.%Y")
        return trade_str, german_str
    except Exception:
        return str(expiry), str(expiry)


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


def _build_trend_note(row: pd.Series, otm_pct: float) -> str:
    """Generiert automatisch die Absicherungs-Zeile."""
    otm_str = _fmt_num(abs(otm_pct), 1)
    parts = []

    # Trend aus TA-Spalten wenn vorhanden
    sc_trend = str(row.get("SC Trend(1D)", "")).lower()
    macd     = str(row.get("MACD(1D)", "")).lower()
    rsi_val  = str(row.get("RSI(1D)", ""))

    if "bull" in sc_trend or "↑" in sc_trend:
        parts.append("Aktie im Aufwärtstrend")
    elif "bear" in sc_trend or "↓" in sc_trend:
        parts.append("Übergeordneter Abwärtstrend — erhöhte Vorsicht")
    else:
        parts.append("Neutrale Marktlage")

    parts.append(f"Strike mit {otm_str}% Abstand zum Aktienkurs")

    if "bull" in macd or "cross" in macd:
        parts.append("MACD bullish")

    earnings = str(row.get("⚠️ Earnings", "")).strip()
    if earnings:
        parts.append(f"⚠️ Earnings: {earnings}")

    return ", ".join(parts)


def _extract_news_headlines(fundamentals: dict, n: int = 3) -> str:
    """Extrahiert die Top-N News-Headlines als formatierten String."""
    news_list = fundamentals.get("news", [])
    if not news_list:
        return "Keine aktuellen News verfügbar."
    lines = []
    for item in news_list[:n]:
        title = item.get("title", "").strip()
        if title:
            lines.append(f"→ {title}")
    return "\n".join(lines) if lines else "Keine aktuellen News verfügbar."


@st.cache_data(ttl=3600, show_spinner=False)
def _cached_stock_data(ticker: str) -> dict:
    info  = fetch_stock_info(ticker)
    fund  = fetch_fundamentals(ticker)
    return {"info": info, "fund": fund}


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
    trend_note: str,
    background: str,
    news_text: str,
) -> str:
    """Generiert den kompletten WhatsApp-Text einer Trade Card."""

    premium_total = round(premium * 100)
    ath_str = f" (-{_fmt_num(ath_dist, 0)}% unten ATH)" if ath_dist else ""

    lines = [
        "Aus Sicht der Technischen Analyse finde ich folgende Optionen spannend:",
        "",
        f"🔔 Trading Idee | {ticker} {trade_exp} @{strike:.0f} {option_type} verkaufen",
        "",
        f"💰 Prämie: {_fmt_num(premium)} USD | {premium_total} USD gesamt (1x)",
        f"📈 Rendite: ~{_fmt_num(rendite_lz)} %",
        f"📉 Strategie: {strategie}",
        f"🎯 Strike: {strike:.0f} USD{ath_str}",
        f"📅 Laufzeit: {german_exp}",
        f"🛡️ Absicherung: {trend_note}",
        "",
        f"🔍 Underlying Background {ticker}:",
        background,
        "",
        f"📰 News {ticker}:",
        news_text,
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

# Top N nach gewählter Sortierung
top_df = (
    df_all
    .sort_values(sort_col, ascending=False)
    .drop_duplicates(subset=["Ticker"])
    .head(int(n_cards))
    .reset_index(drop=True)
)

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

    option_type, strategie = _get_strategy_type(row)
    trade_exp, german_exp  = _fmt_expiry_trade(expiry)
    trend_note_auto        = _build_trend_note(row, otm_pct)

    rank_icon = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"][idx]

    with st.expander(
        f"{rank_icon} **{ticker}** — {trade_exp} @{strike:.0f} {option_type} · Prämie {_fmt_num(premium)} USD · CRV {crv:.0f}",
        expanded=(idx == 0),
    ):
        # ── Stock-Daten laden ──────────────────────────────────────────────
        with st.spinner(f"Lade Daten für {ticker}..."):
            stock_data = _cached_stock_data(ticker)
            info  = stock_data["info"]
            fund  = stock_data["fund"]

        company_name = info.get("name", ticker)
        eng_desc     = (info.get("description") or "").strip()
        news_auto    = _extract_news_headlines(fund, int(news_count))
        ath_pct_val  = _ath_pct(ticker, strike)

        # ── Editierbare Felder ─────────────────────────────────────────────
        col_left, col_right = st.columns([3, 2])

        with col_left:
            st.markdown(f"**📋 {company_name} ({ticker})**")

            st.markdown(
                "<div style='font-size:0.78rem;color:#666;margin-bottom:2px'>"
                "Hintergrund-Text (bearbeiten → auf Deutsch, 2–3 Sätze)</div>",
                unsafe_allow_html=True,
            )
            # Englischer Text als Vorschlag, bearbeitbar
            default_bg = eng_desc[:600] if eng_desc else f"{company_name} ist ein börsennotiertes Unternehmen."
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
            st.markdown(f"""
| | |
|---|---|
| **Strategie** | {strategie} |
| **Strike** | ${strike:.0f} |
| **{option_type}-Verfall** | {german_exp} |
| **Prämie** | {_fmt_num(premium)} USD |
| **Gesamt (1x)** | {round(premium*100)} USD |
| **Rendite LZ** | {_fmt_num(rendite)} % |
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
            trend_note=trend_note,
            background=background,
            news_text=news_text,
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
