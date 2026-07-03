"""
Zentrale Sidebar-Navigation für alle Seiten der Stillhalter AI App.
Einbinden mit: from ui.sidebar import render_sidebar
"""

import streamlit as st
from ui.theme import get_logo_html


def _show_maintenance_screen() -> None:
    """Zeigt Wartungsseite und stoppt die App."""
    st.set_page_config(page_title="Wartung · Stillhalter AI", page_icon="🔧", layout="centered")
    from ui.theme import get_logo_html, get_css
    st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
    st.html(f"""
<div style='text-align:center;padding:80px 40px 40px'>
    <div style='margin-bottom:32px'>{get_logo_html("auto", 56)}</div>
    <div style='background:#111;border:1px solid #1e1e1e;border-top:3px solid #d4a843;
                border-radius:14px;padding:40px 48px;max-width:520px;margin:0 auto'>
        <div style='font-size:2.5rem;margin-bottom:16px'>🔧</div>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.5rem;
                    color:#f0f0f0;letter-spacing:0.05em;margin-bottom:8px'>
            Wartung & Updates
        </div>
        <div style='font-family:RedRose,sans-serif;font-size:0.88rem;color:#888;
                    line-height:1.7;margin-bottom:24px'>
            Die Stillhalter AI App wird gerade weiterentwickelt und
            verbessert. Bitte versuche es in Kürze erneut.
        </div>
        <div style='background:#1a1a1a;border:1px solid #333;border-radius:8px;
                    padding:12px 18px;font-family:RedRose,sans-serif;
                    font-size:0.78rem;color:#555'>
            Bei Fragen wende dich an die<br>
            <span style='color:#d4a843'>Stillhalter Community</span>
        </div>
    </div>
</div>
""")
    st.stop()


def render_sidebar(allow_public: bool = False):
    """
    Rendert die einheitliche Sidebar-Navigation auf jeder Seite.

    allow_public=True: Seite ist absichtlich ohne Login erreichbar (z.B. der
    öffentliche Trade-Monitor-Tracking-Link). Der Wartungsmodus-Block wird dann
    übersprungen, damit geteilte Links jederzeit funktionieren.
    """
    from data.fetcher import is_market_open, market_status_text
    from data.maintenance import is_maintenance, is_admin
    from data.auth import is_monitor_only

    authenticated = bool(st.session_state.get("authenticated", False))
    monitor_only  = authenticated and is_monitor_only(st.session_state.get("auth_user", ""))

    if allow_public:
        # Öffentliche Seite (Trade-Monitor-Tracking-Link): kein Login, kein
        # Wartungs-Block. Navigation NUR für eingeloggte Nutzer — ein anonymer
        # Besucher bleibt auf dieser Seite (keine Links in den Rest der App).
        show_nav = authenticated
    else:
        # Gast-Zugang (z. B. Passwort 0000): darf NUR den Trade Monitor nutzen.
        # Auf jeder anderen Seite → Sperr-Hinweis + Weiterleitung anbieten.
        if monitor_only:
            with st.sidebar:
                st.html(get_logo_html("auto", 28))
            st.html("""
<div style='text-align:center;padding:60px 30px'>
  <div style='font-size:3rem'>🔒</div>
  <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.3rem;margin:8px 0'>
    Dieser Bereich ist gesperrt
  </div>
  <div style='font-family:RedRose,sans-serif;font-size:0.9rem;color:#888;line-height:1.7'>
    Dein Zugang umfasst den <b>Trade Monitor</b> (Live-Tracking).<br>
    Vollzugang zur Stillhalter AI gibt es über die Stillhalter Community.
  </div>
</div>
""")
            st.page_link("pages/20_Trade_Monitor.py", label="→ Zum Trade Monitor", icon="📡")
            st.stop()
        # Normale Seite: Login wird wie immer NUR auf der Startseite (app.py)
        # erzwungen. Eingeloggte Nutzer navigieren hier frei (kein Login-Popup).
        if is_maintenance() and not is_admin(st.session_state.get("auth_user", "")):
            _show_maintenance_screen()
        show_nav = True

    market_open = is_market_open()
    with st.sidebar:
        # "auto" → dunkles Logo im hellen (grünen) Theme, helles im dunklen Theme.
        # Vorher fest "white" → im hellen Theme weiß auf fast-weiß = unsichtbar.
        st.html(get_logo_html("auto", 28))
        if not show_nav:
            # Anonymer Besucher auf öffentlicher Seite → keine Navigation
            st.html("<div style='font-family:RedRose,sans-serif;font-size:0.7rem;"
                    "color:#555;margin-top:10px'>Live-Tracking</div>")
            return
        st.html("""
        <div style='font-family:RedRose,sans-serif;font-size:0.65rem;color:#555;
                    text-transform:uppercase;letter-spacing:0.12em;
                    margin:10px 0 8px 0;padding-bottom:6px;
                    border-bottom:1px solid #1e1e1e'>
            Navigation
        </div>
        """)
        _PAGES = [
            ("app.py",                          "0 · Starte hier",          "🏠"),
            ("pages/01_Marktanalyse_News.py",   "1 · Marktanalyse / News",  "📰"),
            ("pages/02_Fundamentalanalyse.py",  "2 · Fundamentalanalyse",   "💎"),
            ("pages/03_Aktienanalyse.py",       "3 · Aktienanalyse",        "📊"),
            ("pages/04_Watchlist_Scanner.py",   "4 · Watchlist Scanner",    "🔍"),
            ("pages/05_Top9_Trading_Ideen.py",  "5 · Top 9 Trading Ideen",  "🏆"),
            ("pages/06_Zukunftsprognose.py",    "6 · Zukunftsprognose",     "🔭"),
            ("pages/07_Trade_Management.py",    "7 · Trade Management",     "⚖️"),
            ("pages/08_Trend_Signale.py",       "8 · Trend Signale",        "🎯"),
            ("pages/09_Investoren_Check.py",    "9 · Investoren Check",     "🦁"),
            ("pages/10_Option_Olli_Chat.py",    "10 · Option Olli Chat",    "🤖"),
            ("pages/11_Prozess.py",             "11 · Prozess",             "📋"),
            ("pages/12_IBKR_Integration.py",    "12 · IBKR Integration",    "🔗"),
            ("pages/13_Rechtliches.py",         "13 · Datenschutz & Recht", "⚖️"),
            ("pages/14_Order_Planung.py",       "14 · Order-Planung",       "📋"),
            ("pages/15_Datenquellen.py",        "15 · Datenquellen",        "📡"),
            ("pages/16_Sentiment_Analyse.py",   "16 · Sentiment Analyse",   "🧭"),
            ("pages/17_Trade_Cards.py",         "17 · Trade Cards",         "📤"),
            ("pages/18_Markt_Newsletter.py",    "18 · Markt Newsletter",    "📰"),
            ("pages/19_Signal_Pipeline.py",     "19 · Signal Pipeline",     "🛰️"),
            ("pages/20_Trade_Monitor.py",       "20 · Trade Monitor",       "📡"),
            ("pages/21_Research.py",            "21 · Research",            "🔬"),
        ]
        _GUEST_ALLOWED = {"pages/20_Trade_Monitor.py"}
        for _path, _label, _icon in _PAGES:
            if monitor_only and _path not in _GUEST_ALLOWED:
                # Vorschau mit Schloss — sichtbar, aber nicht klickbar
                st.html(
                    f"<div style='font-family:RedRose,sans-serif;font-size:0.82rem;"
                    f"color:#666;padding:4px 8px;opacity:0.75' "
                    f"title='Vollzugang über die Stillhalter Community'>"
                    f"🔒 {_icon} {_label}</div>"
                )
            else:
                st.page_link(_path, label=_label, icon=_icon)
        if monitor_only:
            st.html(
                "<div style='font-family:RedRose,sans-serif;font-size:0.68rem;"
                "color:#888;margin-top:8px;line-height:1.5'>"
                "🔒 Gesperrte Bereiche — Vollzugang über die<br>"
                "<b>Stillhalter Community</b></div>"
            )
        st.html("<div style='border-top:1px solid #1e1e1e;margin:10px 0 4px 0'></div>")
        # Markt-Status Badge
        if market_open:
            st.html("<div style='font-family:RedRose,sans-serif;font-size:0.75rem;"
                    "color:#22c55e;padding:2px 0'>● Markt geöffnet</div>")
        else:
            st.html("<div style='font-family:RedRose,sans-serif;font-size:0.75rem;"
                    "color:#f59e0b;padding:2px 0'>● Markt geschlossen · Last Price</div>")
