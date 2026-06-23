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

    authenticated = bool(st.session_state.get("authenticated", False))

    if allow_public:
        # Öffentliche Seite (Trade-Monitor-Tracking-Link): kein Login, kein
        # Wartungs-Block. Navigation NUR für eingeloggte Nutzer — ein anonymer
        # Besucher bleibt auf dieser Seite (keine Links in den Rest der App).
        show_nav = authenticated
    else:
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
        st.page_link("app.py",                              label="0 · Starte hier",         icon="🏠")
        st.page_link("pages/01_Marktanalyse_News.py",       label="1 · Marktanalyse / News", icon="📰")
        st.page_link("pages/02_Fundamentalanalyse.py",      label="2 · Fundamentalanalyse",  icon="💎")
        st.page_link("pages/03_Aktienanalyse.py",           label="3 · Aktienanalyse",       icon="📊")
        st.page_link("pages/04_Watchlist_Scanner.py",       label="4 · Watchlist Scanner",   icon="🔍")
        st.page_link("pages/05_Top9_Trading_Ideen.py",      label="5 · Top 9 Trading Ideen", icon="🏆")
        st.page_link("pages/06_Zukunftsprognose.py",        label="6 · Zukunftsprognose",    icon="🔭")
        st.page_link("pages/07_Trade_Management.py",        label="7 · Trade Management",    icon="⚖️")
        st.page_link("pages/08_Trend_Signale.py",           label="8 · Trend Signale",       icon="🎯")
        st.page_link("pages/09_Investoren_Check.py",        label="9 · Investoren Check",    icon="🦁")
        st.page_link("pages/10_Option_Olli_Chat.py",        label="10 · Option Olli Chat",   icon="🤖")
        st.page_link("pages/11_Prozess.py",                 label="11 · Prozess",            icon="📋")
        st.page_link("pages/12_IBKR_Integration.py",        label="12 · IBKR Integration",   icon="🔗")
        st.page_link("pages/13_Rechtliches.py",              label="13 · Datenschutz & Recht", icon="⚖️")
        st.page_link("pages/14_Order_Planung.py",            label="14 · Order-Planung",       icon="📋")
        st.page_link("pages/15_Datenquellen.py",             label="15 · Datenquellen",        icon="📡")
        st.page_link("pages/16_Sentiment_Analyse.py",        label="16 · Sentiment Analyse",   icon="🧭")
        st.page_link("pages/17_Trade_Cards.py",              label="17 · Trade Cards",          icon="📤")
        st.page_link("pages/18_Markt_Newsletter.py",         label="18 · Markt Newsletter",     icon="📰")
        st.page_link("pages/19_Signal_Pipeline.py",          label="19 · Signal Pipeline",      icon="🛰️")
        st.page_link("pages/20_Trade_Monitor.py",            label="20 · Trade Monitor",        icon="📡")
        st.html("<div style='border-top:1px solid #1e1e1e;margin:10px 0 4px 0'></div>")
        # Markt-Status Badge
        if market_open:
            st.html("<div style='font-family:RedRose,sans-serif;font-size:0.75rem;"
                    "color:#22c55e;padding:2px 0'>● Markt geöffnet</div>")
        else:
            st.html("<div style='font-family:RedRose,sans-serif;font-size:0.75rem;"
                    "color:#f59e0b;padding:2px 0'>● Markt geschlossen · Last Price</div>")
