"""
Zentrale Sidebar-Navigation für alle Seiten der Stillhalter AI App.
Einbinden mit: from ui.sidebar import render_sidebar
"""

import streamlit as st
from ui.theme import get_logo_html


def render_sidebar():
    """Rendert die einheitliche Sidebar-Navigation auf jeder Seite."""
    with st.sidebar:
        st.html(get_logo_html("white", 28))
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
