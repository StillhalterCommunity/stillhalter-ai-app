"""
Stillhalter AI App Dashboard — Startseite
Login-Gate + Daten-Preload + Navigation
"""

import streamlit as st
import uuid

st.set_page_config(
    page_title="Stillhalter AI App Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.theme import get_css, get_logo_html
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)

from data.auth import check_password, log_event

# ══════════════════════════════════════════════════════════════════════════════
# LOGIN GATE — muss vor allem anderen kommen
# ══════════════════════════════════════════════════════════════════════════════

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "auth_user" not in st.session_state:
    st.session_state.auth_user = ""
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]

if not st.session_state.authenticated:
    # Zentriertes Login-Fenster
    _, center, _ = st.columns([1, 2, 1])
    with center:
        st.html(f"""
<div style='text-align:center;margin:60px 0 32px 0'>
    {get_logo_html("white", 56)}
</div>
<div style='background:#111;border:1px solid #1e1e1e;border-top:3px solid #d4a843;
            border-radius:14px;padding:32px 36px;'>
    <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.4rem;
                color:#f0f0f0;letter-spacing:0.05em;margin-bottom:4px'>
        STILLHALTER AI APP
    </div>
    <div style='font-family:RedRose,sans-serif;font-size:0.78rem;color:#555;
                letter-spacing:0.1em;text-transform:uppercase;margin-bottom:24px'>
        Beta-Zugang · Bitte Passwort eingeben
    </div>
</div>
""")
        pw = st.text_input("Passwort", type="password", placeholder="Dein persönliches Passwort",
                           label_visibility="collapsed")
        col_btn, col_hint = st.columns([2, 3])
        with col_btn:
            login_btn = st.button("→ Einloggen", type="primary", use_container_width=True)
        with col_hint:
            st.caption("Passwort erhalten? Wende dich an die Stillhalter Community.")

        if login_btn or pw:
            username = check_password(pw)
            if username:
                st.session_state.authenticated = True
                st.session_state.auth_user = username
                log_event(username, "login", st.session_state.session_id)
                st.rerun()
            elif pw:
                st.error("Ungültiges Passwort — bitte prüfen oder Stillhalter Community kontaktieren.")
    st.stop()

# ── Ab hier: nur für eingeloggte Nutzer ──────────────────────────────────────
from ui.sidebar import render_sidebar

# ── Kompaktes Spacing: Card → Link-Footer nahtlos ────────────────────────────
st.markdown("""
<style>
[data-testid="stMain"] [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) {
    margin-top: -10px !important;
    margin-bottom: 8px !important;
}
[data-testid="stMain"] [data-testid="stPageLink"] > a {
    border-radius: 0 0 14px 14px !important;
    background: #0c0c0c !important;
    border: 1px solid #1e1e1e !important;
    border-top: none !important;
    padding: 9px 20px !important;
    font-size: 0.82rem !important;
    color: #555 !important;
    width: 100% !important;
    display: block !important;
    text-decoration: none !important;
    transition: color 0.15s, background 0.15s !important;
}
[data-testid="stMain"] [data-testid="stPageLink"] > a:hover {
    color: #d4a843 !important;
    background: #111 !important;
    text-decoration: none !important;
}
</style>
""", unsafe_allow_html=True)

from data.fetcher import (
    market_status_text, is_market_open,
    fetch_extended_hours_price, get_extended_hours_session,
    fetch_price_history, fetch_stock_info,
)
import data.background_scan as bg_scan

render_sidebar()

# ── Header ────────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.html(get_logo_html("white", 48))
with col_title:
    market_open  = is_market_open()
    ext_session  = get_extended_hours_session()
    mkt_class    = "market-open" if market_open else "market-closed"

    ext_badge = ""
    if ext_session:
        spy_ext = fetch_extended_hours_price("SPY")
        if spy_ext:
            sign      = "+" if spy_ext["change_pct"] >= 0 else ""
            col_chg   = "#22c55e" if spy_ext["change_pct"] >= 0 else "#ef4444"
            lbl_color = spy_ext["label_color"]
            lbl_text  = spy_ext["label"]
            spy_price = spy_ext["price"]
            spy_chg   = spy_ext["change_pct"]
            spy_time  = spy_ext["time_str"]
            ext_badge = (
                f" &nbsp;·&nbsp; <span style='background:#1a1a2e;border:1px solid #333;"
                f"border-radius:4px;padding:1px 8px;font-size:0.75rem;"
                f"color:{lbl_color}'>{lbl_text}</span>"
                f" &nbsp;<span style='color:{col_chg};font-size:0.78rem'>"
                f"SPY {spy_price:.2f} ({sign}{spy_chg:.2f}%) · {spy_time}</span>"
            )

    user_name = st.session_state.get("auth_user", "")
    st.html(
        f"<div style='padding-top:6px'>"
        f"<div style='font-family:RedRose,sans-serif;font-weight:700;font-size:2rem;"
        f"color:#f0f0f0;letter-spacing:0.04em'>STILLHALTER AI APP</div>"
        f"<div style='font-family:RedRose,sans-serif;font-weight:300;font-size:0.8rem;"
        f"color:#666;text-transform:uppercase;letter-spacing:0.15em;margin-top:2px'>"
        f"Options Trading Dashboard &nbsp;·&nbsp; <span class='{mkt_class}'>{market_status_text()}</span>"
        f"{ext_badge}"
        f" &nbsp;·&nbsp; <span style='color:#d4a843'>👤 {user_name}</span>"
        f"</div></div>"
    )

st.html('<div class="gold-line"></div>')

# ── System-Steuerung ───────────────────────────────────────────────────────────
with st.expander("⚙️ System", expanded=False):
    sc1, sc2, sc3, sc4, _ = st.columns([2, 2, 2, 2, 4])
    with sc1:
        if st.button("🔄 App neu starten", use_container_width=True,
                     help="Startet die App komplett neu — behebt Hänger und Speicherfehler"):
            user = st.session_state.get("auth_user", "")
            sid  = st.session_state.get("session_id", "")
            log_event(user, "logout", sid)
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.cache_data.clear()
            st.rerun()
    with sc2:
        if st.button("🗑️ Cache leeren", use_container_width=True,
                     help="Löscht alle gecachten Börsendaten — erzwingt frischen Datenabruf"):
            st.cache_data.clear()
            st.success("✅ Cache geleert — Daten werden neu geladen")
    with sc3:
        if st.button("🔃 Seite aktualisieren", use_container_width=True,
                     help="Aktualisiert die aktuelle Seite"):
            st.rerun()
    with sc4:
        if st.button("🚪 Ausloggen", use_container_width=True,
                     help="Sitzung beenden"):
            user = st.session_state.get("auth_user", "")
            sid  = st.session_state.get("session_id", "")
            log_event(user, "logout", sid)
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

st.html("<div style='margin-top:8px'></div>")

# ══════════════════════════════════════════════════════════════════════════════
# DATEN-PRELOAD — läuft einmal beim ersten Besuch der Startseite
# ══════════════════════════════════════════════════════════════════════════════

_PRELOAD_KEY = "preload_done"
_PRELOAD_TICKERS = ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
                    "META", "TSLA", "JPM", "V", "JNJ", "UNH", "XOM", "WMT"]

if not st.session_state.get(_PRELOAD_KEY):
    header_ph    = st.empty()
    progress_bar = st.progress(0.0)
    status_txt   = st.empty()

    total = len(_PRELOAD_TICKERS)
    for i, ticker in enumerate(_PRELOAD_TICKERS):
        pct      = i / total
        pct_int  = int(pct * 100)
        progress_bar.progress(pct)
        header_ph.html(f"""
<div style='font-family:RedRose,sans-serif;font-weight:700;font-size:0.95rem;
            color:#d4a843;letter-spacing:0.08em;margin-bottom:4px'>
    ⚡ DATENIMPORT &nbsp;
    <span style='font-size:1.4rem;color:#f0f0f0'>{pct_int}%</span>
    <span style='font-size:0.75rem;color:#555;font-weight:300;margin-left:8px'>
        — Kerndaten werden vorgeladen
    </span>
</div>
""")
        status_txt.caption(f"Lade {ticker} … ({i+1}/{total})")
        try:
            fetch_price_history(ticker, period="1y")
            fetch_stock_info(ticker)
        except Exception:
            pass

    progress_bar.progress(1.0)
    header_ph.html("""
<div style='font-family:RedRose,sans-serif;font-weight:700;font-size:0.95rem;
            color:#22c55e;letter-spacing:0.08em;margin-bottom:4px'>
    ✅ DATENIMPORT &nbsp;
    <span style='font-size:1.4rem;color:#f0f0f0'>100%</span>
    <span style='font-size:0.75rem;color:#555;font-weight:300;margin-left:8px'>
        — App bereit
    </span>
</div>
""")
    status_txt.empty()
    st.session_state[_PRELOAD_KEY] = True

    import time
    time.sleep(1.0)
    header_ph.empty()
    progress_bar.empty()

st.html("<div style='margin-bottom:8px'></div>")

# ══════════════════════════════════════════════════════════════════════════════
# HINTERGRUND-SCAN STATUS — zeigt laufenden Scan auf der Startseite
# ══════════════════════════════════════════════════════════════════════════════
_bg = bg_scan.get_state()
if _bg["running"]:
    pct  = _bg["progress"]
    done = _bg["done"]
    tot  = _bg["total"]
    cur  = _bg["current"]
    st.html(f"""
<div style='background:rgba(212,168,67,0.08);border:1px solid rgba(212,168,67,0.3);
            border-radius:10px;padding:12px 18px;margin-bottom:4px'>
    <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:0.85rem;
                color:#d4a843;margin-bottom:6px'>
        🔍 WATCHLIST-SCAN LÄUFT IM HINTERGRUND
    </div>
    <div style='font-family:RedRose,sans-serif;font-size:0.8rem;color:#888'>
        Strategie: {_bg['strategy']} &nbsp;·&nbsp;
        Fortschritt: {done}/{tot} Aktien ({pct*100:.0f}%) &nbsp;·&nbsp;
        Aktuell: <strong style='color:#f0f0f0'>{cur}</strong>
        &nbsp;·&nbsp; Seite wechseln ist jederzeit möglich ✓
    </div>
</div>
""")
    st.progress(pct)
    # Auto-Refresh alle 3 Sekunden solange Scan läuft
    import time as _time
    _time.sleep(3)
    st.rerun()
elif _bg["finished_at"] and _bg["results"] is not None:
    res = _bg["results"]
    dur = (_bg["finished_at"] - _bg["started_at"]).total_seconds() if _bg["started_at"] else 0
    n   = len(res)
    nt  = res["Ticker"].nunique() if "Ticker" in res.columns else 0
    st.success(
        f"✅ Letzter Scan abgeschlossen: **{n} Optionen** aus **{nt} Aktien** "
        f"gefunden · Dauer: {dur:.0f}s · "
        f"Ergebnisse in **Watchlist Scanner** & **Top 9** verfügbar"
    )

# ── Karten-Helper ─────────────────────────────────────────────────────────────
def _card(num: str, title: str, desc: str, color: str, page: str, icon: str, label: str):
    st.html(f"""
    <div style='background:#111;border:1px solid #1e1e1e;border-top:3px solid {color};
                border-bottom:none;border-radius:14px 14px 0 0;padding:20px 22px 14px'>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.1rem;
                    color:{color};letter-spacing:0.05em;margin-bottom:6px'>
            {icon} {num} · {title}
        </div>
        <div style='font-family:RedRose,sans-serif;font-size:0.83rem;color:#666;line-height:1.65'>
            {desc}
        </div>
    </div>
""")
    st.page_link(page, label=f"→ {label}", icon=icon)


# ── Zeile 1 ───────────────────────────────────────────────────────────────────
c1, c2 = st.columns(2, gap="large")
with c1:
    _card("1", "MARKTANALYSE / NEWS",
          "Makro-Überblick · Fear &amp; Greed · Sektoren-Heatmap · Top-News &amp; Earnings",
          "#38bdf8", "pages/01_Marktanalyse_News.py", "📰", "Marktanalyse / News")
with c2:
    _card("2", "FUNDAMENTALANALYSE",
          "PEG · KGV · Wachstum · ROE — Value Score A/B/C für die gesamte Watchlist",
          "#22c55e", "pages/02_Fundamentalanalyse.py", "💎", "Fundamentalanalyse")

# ── Zeile 2 ───────────────────────────────────────────────────────────────────
c3, c4 = st.columns(2, gap="large")
with c3:
    _card("3", "AKTIENANALYSE",
          "Tiefenanalyse: Optionen · Greeks · CRV · Chart · MACD · Stochastik · Fundamentals",
          "#9ca3af", "pages/03_Aktienanalyse.py", "📊", "Aktienanalyse")
with c4:
    _card("4", "WATCHLIST SCANNER",
          "225 Aktien · CRV-Score · Cash Covered Puts · Covered Calls · Bubble-Chart · CSV",
          "#d4a843", "pages/04_Watchlist_Scanner.py", "🔍", "Watchlist Scanner")

st.html('<div class="gold-line" style="margin:18px 0"></div>')

# ── Zeile 3 ───────────────────────────────────────────────────────────────────
c5, c6 = st.columns(2, gap="large")
with c5:
    _card("5", "TOP 9 TRADING IDEEN",
          "Top 3 pro IV-Klasse (Low/Mid/High) · TA-Begründung · Absicherungs-Ampel",
          "#d4a843", "pages/05_Top9_Trading_Ideen.py", "🏆", "Top 9 Trading Ideen")
with c6:
    _card("6", "ZUKUNFTSPROGNOSE",
          "Welche Aktien nähern sich einem Setup? · Indikator-Proximity · Konvergenz-Score",
          "#60a5fa", "pages/06_Zukunftsprognose.py", "🔭", "Zukunftsprognose")

# ── Zeile 4 ───────────────────────────────────────────────────────────────────
c7, c8 = st.columns(2, gap="large")
with c7:
    _card("7", "TRADE MANAGEMENT",
          "Offene Positionen bewerten · P&amp;L · Empfehlungen · IBKR Live-Import",
          "#a78bfa", "pages/07_Trade_Management.py", "⚖️", "Trade Management")
with c8:
    _card("8", "TREND SIGNALE",
          "EMA 2/9 Multi-Timeframe · Score ≥ 4/6 · Call/Put-Empfehlung mit Strike &amp; Prämie",
          "#f59e0b", "pages/08_Trend_Signale.py", "🎯", "Trend Signale")

st.html('<div class="gold-line" style="margin:18px 0"></div>')

# ── Zeile 5 ───────────────────────────────────────────────────────────────────
c9, c10 = st.columns(2, gap="large")
with c9:
    _card("9", "INVESTOREN CHECK",
          "Buffett · Lynch · Graham — Bewertung nach legendären Investoren-Kriterien",
          "#fb923c", "pages/09_Investoren_Check.py", "🦁", "Investoren Check")
with c10:
    _card("10", "OPTION OLLI CHAT",
          "KI-Assistent für Optionsstrategien · Persönliches Coaching · Wissens-Upload",
          "#e879f9", "pages/10_Option_Olli_Chat.py", "🤖", "Option Olli Chat")

# ── Zeile 6 ───────────────────────────────────────────────────────────────────
c11, c12 = st.columns(2, gap="large")
with c11:
    _card("11", "PROZESS",
          "Handelsregeln · Checklisten · Schritt-für-Schritt Stillhalter-Prozess",
          "#6b7280", "pages/11_Prozess.py", "📋", "Prozess")
with c12:
    _card("12", "IBKR INTEGRATION",
          "Interactive Brokers Live-Verbindung · Portfolio-Import · Automatische Positionserkennung",
          "#34d399", "pages/12_IBKR_Integration.py", "🔗", "IBKR Integration")

# ── Zeile 7: Rechtliches ─────────────────────────────────────────────────────
c13, _ = st.columns(2, gap="large")
with c13:
    _card("13", "DATENSCHUTZ & RECHTLICHES",
          "Datenschutzerklärung · Haftungsausschluss · Impressum",
          "#475569", "pages/13_Rechtliches.py", "⚖️", "Datenschutz & Rechtliches")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.html("""
<div style='text-align:center;font-family:RedRose,sans-serif;font-size:0.78rem;color:#333;
            letter-spacing:0.08em'>
    STILLHALTER AI APP · Daten: Yahoo Finance ·
    Stillhalter MACD Pro · Stillhalter Dual Stochastik · Stillhalter Trend Model®
    &nbsp;·&nbsp;
    <a href='pages/13_Rechtliches.py' style='color:#444;text-decoration:none'>
        Datenschutz &amp; Impressum
    </a>
</div>
""")
