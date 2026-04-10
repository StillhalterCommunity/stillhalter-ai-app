"""
Stillhalter AI App — Datenquellen & API-Einstellungen
======================================================
Übersicht und Test der konfigurierten Datenquellen:
  - Yahoo Finance (kostenlos, 15 Min verzögert)
  - Massive.com / Polygon.io (Echtzeit, API-Key nötig)
"""

import streamlit as st

st.set_page_config(
    page_title="Datenquellen · Stillhalter AI App",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.html(f"""
<div style='display:flex;align-items:center;gap:16px;margin-bottom:8px'>
  {get_logo_html(height=44)}
  <div style='border-left:1px solid #222;height:40px;margin:0 4px'></div>
  <div>
    <div style='font-size:1.4rem;font-weight:800;color:#f0f0f0;font-family:sans-serif'>
      📡 Datenquellen
    </div>
    <div style='font-size:0.8rem;color:#666;font-family:sans-serif'>
      Yahoo Finance vs. Massive.com — Konfiguration und Verbindungstest
    </div>
  </div>
</div>
""")
st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# AKTIVE DATENQUELLE
# ══════════════════════════════════════════════════════════════════════════════
from data.fetcher import USE_MASSIVE, _massive_enabled

massive_active = _massive_enabled()
source_label   = "Massive.com (Echtzeit)" if massive_active else "Yahoo Finance (15 Min verzögert)"
source_color   = "#22c55e" if massive_active else "#f59e0b"
source_icon    = "✅" if massive_active else "⚠️"

st.html(f"""
<div style='background:#0e0e0e;border:2px solid {source_color};border-radius:12px;
     padding:18px 22px;margin-bottom:20px;display:flex;align-items:center;gap:16px'>
  <span style='font-size:2rem'>{source_icon}</span>
  <div>
    <div style='font-size:1.0rem;font-weight:700;color:{source_color};font-family:sans-serif'>
      Aktive Datenquelle: {source_label}
    </div>
    <div style='font-size:0.78rem;color:#888;margin-top:4px'>
      {"Echtzeit Bid/Ask, echte IV und Greeks direkt von der API" if massive_active
       else "Verzögerte Daten, Workarounds für IV und fehlende Bid/Ask aktiv"}
    </div>
  </div>
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# VERGLEICH
# ══════════════════════════════════════════════════════════════════════════════
col1, col2 = st.columns(2)

with col1:
    yf_border = "#22c55e" if not massive_active else "#333"
    st.html(f"""
<div style='background:#0e0e0e;border:1px solid {yf_border};border-radius:12px;
     padding:18px;height:100%'>
  <div style='font-size:0.95rem;font-weight:700;color:#f0f0f0;margin-bottom:12px'>
    📊 Yahoo Finance
    {"<span style='font-size:0.65rem;background:#1a1a0a;border:1px solid #f59e0b;color:#f59e0b;padding:2px 7px;border-radius:20px;margin-left:8px'>AKTIV</span>" if not massive_active else ""}
  </div>
  <div style='font-size:0.78rem;color:#aaa;line-height:1.9'>
    <div>💰 Kosten: <b style='color:#22c55e'>Kostenlos</b></div>
    <div>⏱ Verzögerung: <b style='color:#f59e0b'>15 Minuten</b></div>
    <div>📋 Bid/Ask: <b style='color:#ef4444'>~3% der Optionen</b></div>
    <div>🎯 IV: <b style='color:#ef4444'>Oft Placeholder-Werte</b></div>
    <div>📐 Greeks: <b style='color:#f59e0b'>Berechnet (Black-Scholes)</b></div>
    <div>🔄 Setup: <b style='color:#22c55e'>Kein Setup nötig</b></div>
    <div>🛡 Workarounds: <b style='color:#f59e0b'>IV-Solver aktiv</b></div>
  </div>
</div>
""")

with col2:
    ms_border = "#22c55e" if massive_active else "#333"
    st.html(f"""
<div style='background:#0e0e0e;border:1px solid {ms_border};border-radius:12px;
     padding:18px;height:100%'>
  <div style='font-size:0.95rem;font-weight:700;color:#f0f0f0;margin-bottom:12px'>
    ⚡ Massive.com (Polygon.io)
    {"<span style='font-size:0.65rem;background:#0a1a0a;border:1px solid #22c55e;color:#22c55e;padding:2px 7px;border-radius:20px;margin-left:8px'>AKTIV</span>" if massive_active else ""}
  </div>
  <div style='font-size:0.78rem;color:#aaa;line-height:1.9'>
    <div>💰 Kosten: <b style='color:#f59e0b'>ab $29/Monat</b></div>
    <div>⏱ Verzögerung: <b style='color:#22c55e'>Echtzeit</b></div>
    <div>📋 Bid/Ask: <b style='color:#22c55e'>Vollständig vorhanden</b></div>
    <div>🎯 IV: <b style='color:#22c55e'>Echte Markt-IV</b></div>
    <div>📐 Greeks: <b style='color:#22c55e'>Delta, Gamma, Theta, Vega direkt</b></div>
    <div>🔄 Setup: <b style='color:#f59e0b'>API-Key erforderlich</b></div>
    <div>🛡 Workarounds: <b style='color:#22c55e'>Keine nötig</b></div>
  </div>
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# MASSIVE.COM SETUP
# ══════════════════════════════════════════════════════════════════════════════
st.html("<div style='margin-top:24px'></div>")
with st.expander("⚙️ Massive.com einrichten", expanded=not massive_active):

    st.markdown("""
**Schritt 1 — Account erstellen**

Gehe auf [massive.com](https://massive.com) → Pricing → passenden Plan wählen.
Für persönliches Trading reicht der günstigste Plan mit Options + Real-time.

**Schritt 2 — API-Key holen**

Nach dem Login: Dashboard → API Keys → neuen Key erstellen.

**Schritt 3 — Key in Streamlit Secrets eintragen**

Erstelle (falls noch nicht vorhanden) die Datei `.streamlit/secrets.toml`:
""")

    st.code("""
# .streamlit/secrets.toml
MASSIVE_API_KEY = "dein_api_key_hier"

# Alternativ: Legacy Polygon-Key funktioniert auch
# POLYGON_API_KEY = "dein_polygon_key"
""", language="toml")

    st.markdown("""
**Schritt 4 — Massive in fetcher.py aktivieren**

In `data/fetcher.py` Zeile ändern:
""")
    st.code('USE_MASSIVE: bool = True  # war: False', language="python")

    st.markdown("""
**Schritt 5 — App neu starten**

Nach dem Neustart zeigt diese Seite "Aktive Datenquelle: Massive.com" in Grün.
""")

# ══════════════════════════════════════════════════════════════════════════════
# VERBINDUNGSTEST
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.html("""
<div style='font-size:1.0rem;font-weight:700;color:#f0f0f0;margin-bottom:12px'>
  🔍 Verbindungstest
</div>
""")

test_col, _ = st.columns([1, 3])
with test_col:
    test_btn = st.button("Massive.com testen", use_container_width=True)

if test_btn:
    try:
        from data.massive_fetcher import test_api_connection, get_current_price
        with st.spinner("Verbinde mit Massive.com API..."):
            ok, msg = test_api_connection()

        if ok:
            st.success(f"Verbindung OK: {msg}")

            # Live-Preistest
            with st.spinner("Teste Optionskette (AAPL)..."):
                from data.massive_fetcher import get_options_chain
                df = get_options_chain("AAPL", option_type="put", limit=10)

            if not df.empty:
                st.success(f"Options-Chain: {len(df)} Puts geladen, "
                           f"IV-Bereich: {df['impliedVolatility'].min():.1%}–"
                           f"{df['impliedVolatility'].max():.1%}, "
                           f"Delta-Bereich: {df['delta'].min():.2f}–{df['delta'].max():.2f}")
                st.dataframe(
                    df[["strike", "expiration", "bid", "ask", "impliedVolatility",
                         "delta", "theta", "openInterest"]].head(5),
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "impliedVolatility": st.column_config.NumberColumn("IV", format="%.1%"),
                        "delta": st.column_config.NumberColumn("Delta", format="%.3f"),
                        "theta": st.column_config.NumberColumn("Theta", format="%.4f"),
                    }
                )
            else:
                st.warning("API verbunden, aber keine Optionsdaten erhalten. "
                           "Plan unterstützt möglicherweise keine Options-Daten.")
        else:
            st.error(f"Verbindung fehlgeschlagen: {msg}")

    except ImportError:
        st.error("data/massive_fetcher.py nicht gefunden.")

# Yahoo Finance Test
st.markdown("")
yf_col, _ = st.columns([1, 3])
with yf_col:
    yf_btn = st.button("Yahoo Finance testen", use_container_width=True)

if yf_btn:
    with st.spinner("Teste Yahoo Finance..."):
        import yfinance as yf
        try:
            t = yf.Ticker("AAPL")
            chain = t.option_chain(t.options[0])
            n_puts = len(chain.puts)
            has_bid = (chain.puts["bid"] > 0).sum()
            st.success(
                f"Yahoo Finance verbunden: {n_puts} Puts, "
                f"davon {has_bid} ({has_bid/n_puts:.0%}) mit Bid/Ask. "
                f"IV-Beispiel: {chain.puts['impliedVolatility'].median():.1%}"
            )
        except Exception as e:
            st.error(f"Yahoo Finance Fehler: {e}")
