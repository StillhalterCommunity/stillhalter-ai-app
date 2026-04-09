"""
Stillhalter AI App — Prozessdarstellung
Wie die App funktioniert: visueller Workflow von Daten bis zur Handelsentscheidung.
"""

import streamlit as st

st.set_page_config(
    page_title="So funktioniert's · Stillhalter AI App",
    page_icon="🗺️",
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
      🗺️ So funktioniert die Stillhalter App
    </div>
    <div style='font-size:0.8rem;color:#666;font-family:sans-serif'>
      Vom Rohdatum zur professionellen Handelsentscheidung — vollständig erklärt
    </div>
  </div>
</div>
""")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# INTRO
# ══════════════════════════════════════════════════════════════════════════════
st.html("""
<div style='background:linear-gradient(135deg,#0e0e1a 0%,#111118 100%);
     border:1px solid #1e1e3a;border-radius:14px;padding:24px 28px;margin-bottom:24px'>
  <div style='font-size:1.05rem;font-weight:700;color:#d4a843;font-family:sans-serif;
       margin-bottom:10px'>💡 Die Idee hinter der Stillhalter AI App</div>
  <div style='font-size:0.88rem;color:#aaa;font-family:sans-serif;line-height:1.7;
       max-width:900px'>
    Die App kombiniert <b style='color:#f0f0f0'>Marktdaten in Echtzeit</b>,
    <b style='color:#f0f0f0'>proprietäre Trendanalyse</b> und
    <b style='color:#f0f0f0'>Options-Expertise</b> zu einem durchgängigen Workflow —
    von der ersten Idee bis zur konkreten Handelsentscheidung.
    Jedes Modul liefert einen klar definierten Output, der als Input in das nächste fließt.
    So entsteht ein <b style='color:#d4a843'>systematischer, wiederholbarer Prozess</b>
    statt Bauchentscheidungen.
  </div>
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# LAYER 1: DATENQUELLEN
# ══════════════════════════════════════════════════════════════════════════════
st.html("""
<div style='font-family:sans-serif;margin-bottom:6px'>
  <span style='font-size:0.62rem;color:#555;text-transform:uppercase;
       letter-spacing:0.12em'>Schicht 1</span>
  <span style='font-size:1.1rem;font-weight:800;color:#3b82f6;margin-left:10px'>
    📡 Datenquellen & Rohdaten
  </span>
</div>
""")

col1, col2, col3, col4, col5 = st.columns(5)

DATA_CARDS = [
    ("📈", "#3b82f6", "Kursdaten", "Täglich · Echtzeit", [
        "Open, High, Low, Close",
        "Volumen & Umsatz",
        "Optionsketten (Bid/Ask)",
        "Implied Volatility (IV)",
        "Open Interest",
    ]),
    ("📰", "#06b6d4", "Nachrichten", "RSS · Web", [
        "Unternehmens-News",
        "Earnings-Termine",
        "Analystenmeinungen",
        "Sektor-Trends",
        "Marktkommentare",
    ]),
    ("📊", "#8b5cf6", "Finanzkennzahlen", "Fundamental", [
        "KGV, KBV, KUV",
        "Dividendenrendite",
        "Umsatzwachstum",
        "Free Cashflow",
        "Eigenkapitalrendite",
    ]),
    ("🕯️", "#10b981", "Charttechnik", "1J · 10J", [
        "Swing-Highs & Lows",
        "Trendlinien",
        "Unterstützungen",
        "Widerstände",
        "Volumen-Cluster",
    ]),
    ("🌍", "#f59e0b", "Markt-Regime", "SPY · QQQ", [
        "Übergeordneter Trend",
        "Monat/Woche Kontext",
        "Risk-On / Risk-Off",
        "Sektoren-Rotation",
        "VIX-Niveau",
    ]),
]

for col, (icon, color, title, subtitle, items) in zip(
    [col1, col2, col3, col4, col5], DATA_CARDS
):
    with col:
        items_html = "".join(
            f"<div style='font-size:0.72rem;color:#888;padding:2px 0;"
            f"border-bottom:1px solid #1a1a1a'>"
            f"<span style='color:{color};margin-right:5px'>·</span>{item}</div>"
            for item in items
        )
        st.html(f"""
<div style='background:#0e0e0e;border:1px solid #1e1e1e;border-top:3px solid {color};
     border-radius:10px;padding:14px;height:100%'>
  <div style='font-size:1.6rem;margin-bottom:4px'>{icon}</div>
  <div style='font-size:0.85rem;font-weight:700;color:{color};font-family:sans-serif;
       margin-bottom:2px'>{title}</div>
  <div style='font-size:0.65rem;color:#555;font-family:sans-serif;
       margin-bottom:8px;text-transform:uppercase;letter-spacing:0.06em'>{subtitle}</div>
  {items_html}
</div>
""")

# ARROW
st.html("""
<div style='text-align:center;font-size:1.8rem;color:#333;margin:10px 0;
     line-height:1'>⬇</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# LAYER 2: ANALYSE-ENGINE
# ══════════════════════════════════════════════════════════════════════════════
st.html("""
<div style='font-family:sans-serif;margin-bottom:6px'>
  <span style='font-size:0.62rem;color:#555;text-transform:uppercase;
       letter-spacing:0.12em'>Schicht 2</span>
  <span style='font-size:1.1rem;font-weight:800;color:#d4a843;margin-left:10px'>
    ⚙️ Proprietäre Analyse-Engine
  </span>
</div>
""")

engine_col1, engine_col2, engine_col3 = st.columns([1, 1, 1])

with engine_col1:
    st.html("""
<div style='background:linear-gradient(180deg,#0e100c 0%,#0c0c0c 100%);
     border:1px solid #22c55e33;border-radius:12px;padding:16px'>
  <div style='font-size:0.85rem;font-weight:700;color:#22c55e;font-family:sans-serif;
       margin-bottom:10px'>🔍 Scanner-Module</div>

  <div style='background:#0a0a0a;border-radius:8px;padding:10px;margin-bottom:8px;
       border-left:3px solid #22c55e'>
    <div style='font-size:0.78rem;font-weight:700;color:#f0f0f0;font-family:sans-serif'>
      Watchlist Scanner</div>
    <div style='font-size:0.7rem;color:#888;font-family:sans-serif;margin-top:3px'>
      Multi-Timeframe-Analyse aller Community-Watchlist-Titel.
      Erkennt Trendstärke, RSI-Signale und Momentum-Cluster.
    </div>
  </div>

  <div style='background:#0a0a0a;border-radius:8px;padding:10px;margin-bottom:8px;
       border-left:3px solid #10b981'>
    <div style='font-size:0.78rem;font-weight:700;color:#f0f0f0;font-family:sans-serif'>
      Value Scanner</div>
    <div style='font-size:0.7rem;color:#888;font-family:sans-serif;margin-top:3px'>
      Filtert nach fundamentalen Kriterien: unterbewertete Aktien
      mit solider Bilanz als Stillhalter-Kandidaten.
    </div>
  </div>

  <div style='background:#0a0a0a;border-radius:8px;padding:10px;
       border-left:3px solid #06b6d4'>
    <div style='font-size:0.78rem;font-weight:700;color:#f0f0f0;font-family:sans-serif'>
      Radar Scanner</div>
    <div style='font-size:0.7rem;color:#888;font-family:sans-serif;margin-top:3px'>
      Echtzeit-Überwachung auf Ausbrüche, Volumen-Anomalien
      und ungewöhnliche Options-Aktivität.
    </div>
  </div>
</div>
""")

with engine_col2:
    st.html("""
<div style='background:linear-gradient(180deg,#100e06 0%,#0c0c0c 100%);
     border:2px solid #d4a84355;border-radius:12px;padding:16px;
     box-shadow:0 0 30px #d4a84311'>
  <div style='font-size:0.85rem;font-weight:700;color:#d4a843;font-family:sans-serif;
       margin-bottom:4px'>⭐ STI — Stillhalter Trend Indikator</div>
  <div style='font-size:0.7rem;color:#888;font-family:sans-serif;margin-bottom:12px'>
    Das Herzstück der App — proprietäres Trendsystem
  </div>

  <div style='background:#0a0a0a;border-radius:8px;padding:10px;margin-bottom:8px'>
    <div style='font-size:0.72rem;color:#d4a843;font-weight:700;margin-bottom:4px'>
      Multi-Timeframe-Confluence</div>
    <div style='display:grid;grid-template-columns:1fr 1fr;gap:4px'>
      <div style='background:#111;border-radius:5px;padding:5px 8px;text-align:center'>
        <div style='font-size:0.62rem;color:#a855f7'>MONAT</div>
        <div style='font-size:0.75rem;font-weight:700;color:#ccc'>±2 Punkte</div>
      </div>
      <div style='background:#111;border-radius:5px;padding:5px 8px;text-align:center'>
        <div style='font-size:0.62rem;color:#3b82f6'>WOCHE</div>
        <div style='font-size:0.75rem;font-weight:700;color:#ccc'>±2 Punkte</div>
      </div>
      <div style='background:#111;border-radius:5px;padding:5px 8px;text-align:center'>
        <div style='font-size:0.62rem;color:#10b981'>TAG</div>
        <div style='font-size:0.75rem;font-weight:700;color:#ccc'>±1 Punkt</div>
      </div>
      <div style='background:#111;border-radius:5px;padding:5px 8px;text-align:center'>
        <div style='font-size:0.62rem;color:#f59e0b'>4 STUNDEN</div>
        <div style='font-size:0.75rem;font-weight:700;color:#ccc'>±1 Punkt</div>
      </div>
    </div>
  </div>

  <div style='background:#0a0a0a;border-radius:8px;padding:10px'>
    <div style='font-size:0.72rem;color:#d4a843;font-weight:700;margin-bottom:6px'>
      Signal-Klassifizierung</div>
    <div style='display:flex;gap:6px;flex-wrap:wrap'>
      <span style='background:#22c55e22;border:1px solid #22c55e;color:#22c55e;
           padding:3px 8px;border-radius:10px;font-size:0.68rem;font-weight:700'>
        🔔 NOW Bullish</span>
      <span style='background:#ef444422;border:1px solid #ef4444;color:#ef4444;
           padding:3px 8px;border-radius:10px;font-size:0.68rem;font-weight:700'>
        🔔 NOW Bearish</span>
      <span style='background:#f59e0b22;border:1px solid #f59e0b;color:#f59e0b;
           padding:3px 8px;border-radius:10px;font-size:0.68rem;font-weight:700'>
        ⚡ GET READY</span>
    </div>
  </div>
</div>
""")

with engine_col3:
    st.html("""
<div style='background:linear-gradient(180deg,#0e0e0e 0%,#0c0c0c 100%);
     border:1px solid #8b5cf633;border-radius:12px;padding:16px'>
  <div style='font-size:0.85rem;font-weight:700;color:#8b5cf6;font-family:sans-serif;
       margin-bottom:10px'>🧮 Berechnungs-Module</div>

  <div style='background:#0a0a0a;border-radius:8px;padding:10px;margin-bottom:8px;
       border-left:3px solid #8b5cf6'>
    <div style='font-size:0.78rem;font-weight:700;color:#f0f0f0;font-family:sans-serif'>
      Support / Resistance</div>
    <div style='font-size:0.7rem;color:#888;font-family:sans-serif;margin-top:3px'>
      Swing-Highs & Lows aus 1J-Daten, geclustert.
      Automatische Identifikation von Einstiegs- und Zielzonen.
    </div>
  </div>

  <div style='background:#0a0a0a;border-radius:8px;padding:10px;margin-bottom:8px;
       border-left:3px solid #ec4899'>
    <div style='font-size:0.78rem;font-weight:700;color:#f0f0f0;font-family:sans-serif'>
      IV-Analyse & 1σ Moves</div>
    <div style='font-size:0.7rem;color:#888;font-family:sans-serif;margin-top:3px'>
      Implied Volatility vs. historische Vola.
      Berechnung der statistisch erwarteten Preisbewegung.
    </div>
  </div>

  <div style='background:#0a0a0a;border-radius:8px;padding:10px;
       border-left:3px solid #f97316'>
    <div style='font-size:0.78rem;font-weight:700;color:#f0f0f0;font-family:sans-serif'>
      Gewinnverhältnis-Kalkulator</div>
    <div style='font-size:0.7rem;color:#888;font-family:sans-serif;margin-top:3px'>
      2:1 und 3:1 Zielzonen auf Basis von Strike & Prämie.
      Theta-Tracking für laufende Positionen.
    </div>
  </div>
</div>
""")

# ARROW
st.html("""
<div style='text-align:center;font-size:1.8rem;color:#333;margin:10px 0;
     line-height:1'>⬇</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# LAYER 3: MODULE OUTPUT
# ══════════════════════════════════════════════════════════════════════════════
st.html("""
<div style='font-family:sans-serif;margin-bottom:6px'>
  <span style='font-size:0.62rem;color:#555;text-transform:uppercase;
       letter-spacing:0.12em'>Schicht 3</span>
  <span style='font-size:1.1rem;font-weight:800;color:#22c55e;margin-left:10px'>
    🎯 Konkrete Outputs & Empfehlungen
  </span>
</div>
""")

out_col1, out_col2, out_col3, out_col4 = st.columns(4)

OUTPUTS = [
    ("🔔", "#22c55e", "Trend-Signale", "Seite 7", [
        ("Signal", "CALL/PUT + Ticker"),
        ("Score", "4–6/6 Konvergenz"),
        ("Strike", "ATM-Option vorgeschlagen"),
        ("Expiry", "DTE-optimiert"),
        ("S/R-Zone", "Einstieg + Ziel"),
        ("Backtest", "Win-Rate · EV"),
    ]),
    ("💡", "#d4a843", "Top-9 Ideen", "Seite 6", [
        ("Wochentop", "9 beste Setups"),
        ("Scoring", "Multi-Faktor"),
        ("Prämie", "Rendite vs. Risiko"),
        ("Kontext", "Markt-Regime"),
        ("Filter", "IV-Rating"),
        ("Ranking", "Priorität 1–9"),
    ]),
    ("📋", "#f97316", "Trade Management", "Seite 4", [
        ("Empfehlung", "Halten / Rollen / Einbuchen"),
        ("P&L", "Aktueller Stand"),
        ("Innerer Wert", "In USD"),
        ("Zeitwert", "Verfall-Tracking"),
        ("DTE", "Restlaufzeit"),
        ("Theta", "Tagesertrag"),
    ]),
    ("🔍", "#8b5cf6", "Analyse & Value", "Seiten 2–3·5", [
        ("Technisch", "Multi-TF Übersicht"),
        ("Fundamental", "KGV · FCF · Dividende"),
        ("Radar", "Anomalie-Erkennung"),
        ("IV-Rating", "Günstig / Normal / Teuer"),
        ("Earnings", "Terminwarnung"),
        ("Vergleich", "Peer-Analyse"),
    ]),
]

for col, (icon, color, title, page, items) in zip(
    [out_col1, out_col2, out_col3, out_col4], OUTPUTS
):
    with col:
        items_html = "".join(
            f"<div style='display:flex;justify-content:space-between;"
            f"padding:4px 0;border-bottom:1px solid #1a1a1a'>"
            f"<span style='font-size:0.7rem;color:#666'>{k}</span>"
            f"<span style='font-size:0.7rem;color:#ccc;font-weight:600'>{v}</span></div>"
            for k, v in items
        )
        st.html(f"""
<div style='background:#0e0e0e;border:1px solid {color}33;border-top:3px solid {color};
     border-radius:12px;padding:14px;height:100%'>
  <div style='display:flex;justify-content:space-between;align-items:center;
       margin-bottom:10px'>
    <div>
      <span style='font-size:1.4rem'>{icon}</span>
      <span style='font-size:0.88rem;font-weight:700;color:{color};
           font-family:sans-serif;margin-left:6px'>{title}</span>
    </div>
    <span style='font-size:0.62rem;background:{color}22;color:{color};
         padding:2px 6px;border-radius:8px;font-family:sans-serif'>{page}</span>
  </div>
  {items_html}
</div>
""")

# ARROW
st.html("""
<div style='text-align:center;font-size:1.8rem;color:#333;margin:10px 0;
     line-height:1'>⬇</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# LAYER 4: ENTSCHEIDUNG
# ══════════════════════════════════════════════════════════════════════════════
st.html("""
<div style='font-family:sans-serif;margin-bottom:6px'>
  <span style='font-size:0.62rem;color:#555;text-transform:uppercase;
       letter-spacing:0.12em'>Schicht 4</span>
  <span style='font-size:1.1rem;font-weight:800;color:#ef4444;margin-left:10px'>
    🧠 Handelsentscheidung & Ausführung
  </span>
</div>
""")

st.html("""
<div style='background:linear-gradient(135deg,#0e0e0e 0%,#111 100%);
     border:2px solid #d4a84344;border-radius:14px;padding:22px 28px;
     margin-bottom:16px'>
  <div style='display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:16px'>

    <div style='text-align:center;padding:16px;background:#0a0a0a;
         border-radius:10px;border:1px solid #22c55e33'>
      <div style='font-size:2rem;margin-bottom:6px'>✅</div>
      <div style='font-size:0.82rem;font-weight:700;color:#22c55e;font-family:sans-serif;
           margin-bottom:6px'>Trade eröffnen</div>
      <div style='font-size:0.7rem;color:#888;font-family:sans-serif;line-height:1.5'>
        STI-Score ≥ 5/6<br>IV günstig/normal<br>Gute Liquidität<br>S/R-Zone klar<br>
        Gewinnverhältnis 2:1+
      </div>
    </div>

    <div style='text-align:center;padding:16px;background:#0a0a0a;
         border-radius:10px;border:1px solid #f59e0b33'>
      <div style='font-size:2rem;margin-bottom:6px'>👁️</div>
      <div style='font-size:0.82rem;font-weight:700;color:#f59e0b;font-family:sans-serif;
           margin-bottom:6px'>Beobachten</div>
      <div style='font-size:0.7rem;color:#888;font-family:sans-serif;line-height:1.5'>
        Score 4/6<br>GET READY Signal<br>STI nähert sich Cross<br>Auf Bestätigung warten<br>
        Watchlist aufbauen
      </div>
    </div>

    <div style='text-align:center;padding:16px;background:#0a0a0a;
         border-radius:10px;border:1px solid #8b5cf633'>
      <div style='font-size:2rem;margin-bottom:6px'>🔄</div>
      <div style='font-size:0.82rem;font-weight:700;color:#8b5cf6;font-family:sans-serif;
           margin-bottom:6px'>Position rollen</div>
      <div style='font-size:0.7rem;color:#888;font-family:sans-serif;line-height:1.5'>
        DTE ≤ 21 Tage<br>ITM-Position<br>Trend noch intakt<br>Prämie vorhanden<br>
        Neue Laufzeit wählen
      </div>
    </div>

    <div style='text-align:center;padding:16px;background:#0a0a0a;
         border-radius:10px;border:1px solid #ef444433'>
      <div style='font-size:2rem;margin-bottom:6px'>🚪</div>
      <div style='font-size:0.82rem;font-weight:700;color:#ef4444;font-family:sans-serif;
           margin-bottom:6px'>Exit / Schließen</div>
      <div style='font-size:0.7rem;color:#888;font-family:sans-serif;line-height:1.5'>
        STI-Gegensignal<br>Zielzone erreicht<br>Earnings-Risiko<br>DTE ≤ 5 Tage<br>
        Stop-Loss ausgelöst
      </div>
    </div>

  </div>
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# GESAMTPROZESS FLOWCHART (vereinfacht)
# ══════════════════════════════════════════════════════════════════════════════
st.html("""
<div style='font-size:1.0rem;font-weight:700;color:#f0f0f0;font-family:sans-serif;
     margin-bottom:12px;margin-top:8px'>
  🔄 Der Gesamtprozess auf einen Blick
</div>
<div style='background:#0a0a0a;border:1px solid #1a1a1a;border-radius:12px;padding:20px;
     overflow-x:auto'>
  <div style='display:flex;align-items:center;gap:0;min-width:800px;
       font-family:sans-serif'>

    <!-- Step 1 -->
    <div style='flex:1;text-align:center;background:#0e1118;border:1px solid #3b82f6;
         border-radius:10px;padding:12px 8px'>
      <div style='font-size:1.3rem'>📡</div>
      <div style='font-size:0.72rem;font-weight:700;color:#3b82f6;margin-top:4px'>
        Marktdaten</div>
      <div style='font-size:0.62rem;color:#555;margin-top:3px'>yFinance<br>Echtzeit</div>
    </div>

    <div style='font-size:1.2rem;color:#333;padding:0 4px'>→</div>

    <!-- Step 2 -->
    <div style='flex:1;text-align:center;background:#100e18;border:1px solid #8b5cf6;
         border-radius:10px;padding:12px 8px'>
      <div style='font-size:1.3rem'>⚙️</div>
      <div style='font-size:0.72rem;font-weight:700;color:#8b5cf6;margin-top:4px'>
        STI Analyse</div>
      <div style='font-size:0.62rem;color:#555;margin-top:3px'>4 Timeframes<br>Score 0–6</div>
    </div>

    <div style='font-size:1.2rem;color:#333;padding:0 4px'>→</div>

    <!-- Step 3 -->
    <div style='flex:1;text-align:center;background:#100e08;border:1px solid #d4a843;
         border-radius:10px;padding:12px 8px'>
      <div style='font-size:1.3rem'>🔔</div>
      <div style='font-size:0.72rem;font-weight:700;color:#d4a843;margin-top:4px'>
        Signal</div>
      <div style='font-size:0.62rem;color:#555;margin-top:3px'>NOW / GET READY<br>Bull / Bear</div>
    </div>

    <div style='font-size:1.2rem;color:#333;padding:0 4px'>→</div>

    <!-- Step 4 -->
    <div style='flex:1;text-align:center;background:#0a100a;border:1px solid #22c55e;
         border-radius:10px;padding:12px 8px'>
      <div style='font-size:1.3rem'>🎯</div>
      <div style='font-size:0.72rem;font-weight:700;color:#22c55e;margin-top:4px'>
        S/R Zonen</div>
      <div style='font-size:0.62rem;color:#555;margin-top:3px'>Einstieg<br>Zielzone 2:1–3:1</div>
    </div>

    <div style='font-size:1.2rem;color:#333;padding:0 4px'>→</div>

    <!-- Step 5 -->
    <div style='flex:1;text-align:center;background:#0e0a08;border:1px solid #f97316;
         border-radius:10px;padding:12px 8px'>
      <div style='font-size:1.3rem'>📋</div>
      <div style='font-size:0.72rem;font-weight:700;color:#f97316;margin-top:4px'>
        Option wählen</div>
      <div style='font-size:0.62rem;color:#555;margin-top:3px'>ATM-Call/Put<br>IV · DTE · Prämie</div>
    </div>

    <div style='font-size:1.2rem;color:#333;padding:0 4px'>→</div>

    <!-- Step 6 -->
    <div style='flex:1;text-align:center;background:#0e0e0e;border:1px solid #555;
         border-radius:10px;padding:12px 8px'>
      <div style='font-size:1.3rem'>📈</div>
      <div style='font-size:0.72rem;font-weight:700;color:#ccc;margin-top:4px'>
        Trade öffnen</div>
      <div style='font-size:0.62rem;color:#555;margin-top:3px'>IBKR / Broker<br>Position erfassen</div>
    </div>

    <div style='font-size:1.2rem;color:#333;padding:0 4px'>→</div>

    <!-- Step 7 -->
    <div style='flex:1;text-align:center;background:#0a0a14;border:1px solid #ef4444;
         border-radius:10px;padding:12px 8px'>
      <div style='font-size:1.3rem'>🔄</div>
      <div style='font-size:0.72rem;font-weight:700;color:#ef4444;margin-top:4px'>
        Monitoring</div>
      <div style='font-size:0.62rem;color:#555;margin-top:3px'>Trade Management<br>STI-Exit-Signal</div>
    </div>

  </div>
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# USP / MEHRWERT
# ══════════════════════════════════════════════════════════════════════════════
st.divider()

st.html("""
<div style='font-size:1.0rem;font-weight:700;color:#f0f0f0;font-family:sans-serif;
     margin-bottom:12px'>
  🏆 Was die Stillhalter AI App einzigartig macht
</div>
""")

usp_col1, usp_col2, usp_col3 = st.columns(3)

USPS = [
    [
        ("🎯", "#22c55e", "Systemischer Ansatz",
         "Kein Bauchgefühl, kein Raten. Jeder Trade durchläuft denselben "
         "mehrstufigen Analyseprozess — reproduzierbar und konsequent."),
        ("📐", "#22c55e", "Klare Regelstruktur",
         "Einstieg, Haltedauer, Exit — alles klar definiert durch den STI. "
         "Emotionen spielen keine Rolle."),
    ],
    [
        ("⚡", "#d4a843", "Proprietäre Indikatoren",
         "Der STI (Stillhalter Trend Indikator) ist ein exklusiv entwickeltes "
         "Trendsystem, das speziell für Options-Trader optimiert wurde."),
        ("🧮", "#d4a843", "IV-basierte Zielzonen",
         "Statt pauschaler Rendite-Ziele werden Zielkurse aus Strike, Prämie "
         "und implizierter Volatilität berechnet — mathematisch präzise."),
    ],
    [
        ("📊", "#8b5cf6", "10-Jahres-Backtest",
         "Jedes Signal wird gegen 10 Jahre historischer Daten getestet. "
         "Win-Rate und Erwartungswert sind transparent einsehbar."),
        ("🔄", "#8b5cf6", "Vollständiger Lifecycle",
         "Von der Idee bis zum Exit — alles in einem Tool. "
         "Trade Management, Theta-Tracking, Rollen-Empfehlungen."),
    ],
]

for col, usps in zip([usp_col1, usp_col2, usp_col3], USPS):
    with col:
        for icon, color, title, text in usps:
            st.html(f"""
<div style='background:#0e0e0e;border:1px solid #1a1a1a;border-radius:10px;
     padding:14px;margin-bottom:10px;border-left:3px solid {color}'>
  <div style='display:flex;align-items:center;gap:8px;margin-bottom:6px'>
    <span style='font-size:1.2rem'>{icon}</span>
    <span style='font-size:0.82rem;font-weight:700;color:{color};
         font-family:sans-serif'>{title}</span>
  </div>
  <div style='font-size:0.75rem;color:#888;font-family:sans-serif;line-height:1.6'>
    {text}
  </div>
</div>
""")
