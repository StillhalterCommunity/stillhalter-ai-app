"""
Stillhalter AI App — Option-Olli KI-Assistent
Dein persönlicher Options-Coach. Beantwortet Fragen zur Plattform
ohne proprietäre Indikator-Geheimnisse preiszugeben.
"""

import streamlit as st
import re
import time
import io
from datetime import datetime

try:
    import pypdf
    _PYPDF_OK = True
except ImportError:
    _PYPDF_OK = False

st.set_page_config(
    page_title="Option-Olli · Stillhalter AI App",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

# ══════════════════════════════════════════════════════════════════════════════
# NDA — Muss beim ersten Besuch bestätigt werden
# ══════════════════════════════════════════════════════════════════════════════

if "olli_nda_accepted" not in st.session_state:
    st.session_state["olli_nda_accepted"] = False

if not st.session_state["olli_nda_accepted"]:
    st.html(f"""
<div style='display:flex;align-items:center;gap:16px;margin-bottom:24px'>
  {get_logo_html(height=44)}
  <div style='border-left:1px solid #222;height:40px;margin:0 4px'></div>
  <div style='font-size:1.4rem;font-weight:800;color:#f0f0f0;font-family:sans-serif'>
    🤖 Option-Olli · KI-Assistent
  </div>
</div>
""")

    st.html("""
<div style='background:linear-gradient(135deg,#0a0a14 0%,#0e0e1a 100%);
     border:2px solid #3b82f6;border-radius:16px;padding:28px 32px;max-width:760px;
     margin:40px auto'>

  <div style='text-align:center;margin-bottom:24px'>
    <div style='font-size:3rem;margin-bottom:8px'>🤝</div>
    <div style='font-size:1.3rem;font-weight:800;color:#f0f0f0;font-family:sans-serif;
         margin-bottom:6px'>Vertraulichkeitsvereinbarung (NDA)</div>
    <div style='font-size:0.85rem;color:#888;font-family:sans-serif'>
      Bitte lies und bestätige die folgende Vereinbarung vor der Nutzung
    </div>
  </div>

  <div style='background:#0a0a0a;border:1px solid #1e1e1e;border-radius:10px;
       padding:20px;margin-bottom:20px;font-family:sans-serif;font-size:0.82rem;
       color:#aaa;line-height:1.8;max-height:320px;overflow-y:auto'>

    <div style='font-weight:700;color:#f0f0f0;font-size:0.9rem;margin-bottom:12px'>
      NUTZUNGSVEREINBARUNG — Stillhalter AI App KI-Assistent "Option-Olli"
    </div>

    <div style='margin-bottom:12px'>
      <b style='color:#d4a843'>§ 1 Geheimhaltungspflicht</b><br>
      Der Nutzer bestätigt, dass alle vom KI-Assistenten "Option-Olli" bereitgestellten
      Informationen, Methoden, Strategien und Erkenntnisse streng vertraulich sind.
      Diese Inhalte dürfen nicht an Dritte weitergegeben, veröffentlicht, kopiert oder
      in irgendeiner Form reproduziert werden.
    </div>

    <div style='margin-bottom:12px'>
      <b style='color:#d4a843'>§ 2 Geistiges Eigentum</b><br>
      Die in dieser Anwendung verwendeten Methoden, Indikatoren, Algorithmen und
      Analysemodelle sind geistiges Eigentum der Stillhalter AI App.
      Jede Vervielfältigung oder Nutzung zur Entwicklung konkurrierender Produkte
      ist ausdrücklich untersagt und kann rechtliche Konsequenzen haben.
    </div>

    <div style='margin-bottom:12px'>
      <b style='color:#d4a843'>§ 3 Keine Anlageberatung</b><br>
      Alle Informationen des KI-Assistenten dienen ausschließlich zu Bildungszwecken
      und stellen keine Anlageberatung dar. Der Nutzer trägt die volle Verantwortung
      für seine Handelsentscheidungen. Vergangene Ergebnisse garantieren keine
      zukünftigen Gewinne.
    </div>

    <div style='margin-bottom:12px'>
      <b style='color:#d4a843'>§ 4 Mitgliedschaft erforderlich</b><br>
      Die Nutzung dieser Plattform ist ausschließlich aktiven Mitgliedern der
      Stillhalter AI App vorbehalten. Die Zugangsdaten sind personengebunden
      und dürfen nicht weitergegeben werden.
    </div>

    <div style='margin-bottom:12px'>
      <b style='color:#d4a843'>§ 5 Vertragsstrafe</b><br>
      Bei nachgewiesener Verletzung dieser Vereinbarung behält sich die Stillhalter
      Community vor, rechtliche Schritte einzuleiten und eine Vertragsstrafe von
      mindestens EUR 50.000 geltend zu machen.
    </div>

    <div style='color:#555;font-size:0.75rem;margin-top:16px;border-top:1px solid #1a1a1a;
         padding-top:12px'>
      Diese Vereinbarung gilt ab dem Zeitpunkt der Bestätigung und auf unbegrenzte Dauer.
      Es gilt deutsches Recht. Gerichtsstand ist der Sitz der Stillhalter AI App.
    </div>
  </div>

</div>
""")

    col_left, col_center, col_right = st.columns([1, 2, 1])
    with col_center:
        accept = st.checkbox(
            "✅ Ich habe die Vertraulichkeitsvereinbarung vollständig gelesen und stimme zu",
            key="nda_checkbox"
        )
        if accept:
            if st.button("🤖 Option-Olli starten", type="primary", use_container_width=True):
                st.session_state["olli_nda_accepted"] = True
                st.rerun()

    st.stop()

# ══════════════════════════════════════════════════════════════════════════════
# OPTION-OLLI WISSENSBASIS
# ══════════════════════════════════════════════════════════════════════════════

OLLI_KNOWLEDGE: list[tuple[list[str], str]] = [
    # ── Begrüßung ─────────────────────────────────────────────────────────────
    (["hallo", "hi", "hey", "guten morgen", "guten tag", "servus", "moin"],
     """Hallo! Ich bin **Option-Olli**, dein persönlicher KI-Assistent der Stillhalter AI App! 🤖

Ich bin hier, um dir alles über unsere Plattform zu erklären — von den Signalen über die Trade-Strategie bis zur Portfolioverwaltung. Stell mir einfach deine Fragen!

💡 **Was ich dir erklären kann:**
- Wie die Trend-Signale funktionieren und was sie bedeuten
- Wie du Optionen auswählst und bewertest
- Das Trade Management und Exit-Strategien
- Den gesamten Workflow der App
- Grundlagen des Optionshandels

Was möchtest du wissen?"""),

    # ── STI / Signale ─────────────────────────────────────────────────────────
    (["sti", "stillhalter trend indikator", "trend indikator", "was ist sti"],
     """Der **STI (Stillhalter Trend Indikator)** ist das Herzstück unserer Plattform. 🎯

Er analysiert gleichzeitig **4 Zeitebenen** und gibt für jede einen Trend-Punkt:
- **Monat** (±2 Punkte) — der übergeordnete Trend
- **Woche** (±2 Punkte) — der mittelfristige Trend
- **Tag** (±1 Punkt) — der kurzfristige Trend
- **4 Stunden** (±1 Punkt) — die Einstiegsbestätigung

Der Gesamt-Score reicht von **-6 bis +6**. Ein positiver Score = bullishes Bild, ein negativer = bearish.

**Was bedeuten die Signale?**
- 🔔 **NOW**: Der STI hat gerade einen Trendwechsel angezeigt — optimaler Einstiegszeitpunkt
- ⚡ **GET READY**: Der STI nähert sich einem Wechsel — vorbereitend beobachten

Je höher der Score (±5 oder ±6), desto mehr Zeitebenen sind aligned und desto stärker das Signal!"""),

    (["score", "wie hoch score", "was bedeutet score", "mindest score"],
     """Der **STI-Score** zeigt, wie viele Zeitebenen gleichgerichtet sind:

| Score | Bedeutung | Empfehlung |
|-------|-----------|------------|
| ±6/6  | 🔥 Alle Zeitebenen aligned | Starkes Signal — volle Positionsgröße |
| ±5/6  | ✅ Fast vollständig | Gutes Signal — normale Positionsgröße |
| ±4/6  | ⚠️ Mehrheit aligned | Vorsichtiger Einstieg — halbe Position |
| <±4   | 🚫 Gemischt | Warten auf besseres Setup |

Ich empfehle, **mindestens Score ±4** als Filter zu setzen — du kannst das in der Trend-Signale-Seite einstellen."""),

    (["now", "get ready", "signal typ", "unterschied now get ready"],
     """Gute Frage! Das ist ein wichtiger Unterschied:

🔔 **NOW-Signal**
- Der Trendwechsel ist **gerade passiert**
- Die optimale Einstiegskerze hat soeben geschlossen
- Handlungsbedarf: jetzt oder gar nicht
- Für direkte Einstiege

⚡ **GET READY-Signal**
- Der STI **nähert sich** einem Trendwechsel
- Der Cross steht unmittelbar bevor
- Du hast noch etwas Zeit zur Vorbereitung
- Strategie: Ticker auf Watchlist, Optionskette analysieren, auf NOW warten

In der Praxis: **GET READY** nutze ich, um die Hausaufgaben zu machen (Strike, DTE, Prämie prüfen). Dann bin ich sofort bereit, wenn das **NOW**-Signal kommt!"""),

    # ── Optionen Grundlagen ───────────────────────────────────────────────────
    (["call", "was ist call", "call option"],
     """Ein **Call** ist das Recht, eine Aktie zu einem festgelegten Preis (Strike) zu kaufen. 📈

**Wann kaufst du einen Call?**
- Du erwartest steigende Kurse (bullishes STI-Signal)
- Der Score ist positiv (z.B. +5 oder +6)

**Gewinnpotenzial:**
- Der Call gewinnt an Wert, wenn der Kurs über den Strike steigt
- Maximaler Verlust: die bezahlte Prämie (= was du für die Option zahlst)
- Maximaler Gewinn: theoretisch unbegrenzt

**Unser Ziel:**
- Gewinn : Prämie = 2:1 (MIN) · 3:1 (BASE) · 4:1 (BEST)
- Das heißt: der Gewinn soll 2–3× die bezahlte Prämie betragen
- Diese Zielzonen siehst du in der S/R-Leiter auf der Trend-Signale-Seite"""),

    (["put", "was ist put", "put option"],
     """Ein **Put** ist das Recht, eine Aktie zu einem festgelegten Preis (Strike) zu verkaufen. 📉

**Wann kaufst du einen Put?**
- Du erwartest fallende Kurse (bearishes STI-Signal)
- Der Score ist negativ (z.B. -5 oder -6)

**Gewinnpotenzial:**
- Der Put gewinnt an Wert, wenn der Kurs unter den Strike fällt
- Maximaler Verlust: die bezahlte Prämie
- Unser Ziel: Gewinn : Prämie = 2:1 (MIN) · 3:1 (BASE) · 4:1 (BEST)

**Achtung:** Wir kaufen hier Optionen (Long Calls/Puts), keine Stillhalter-Positionen!
Das ist ein wichtiger Unterschied — wir sind nicht der Verkäufer der Option."""),

    (["prämie", "premium", "optionspreis", "was kostet option"],
     """Die **Prämie** ist der Preis, den du für eine Option zahlst — und gleichzeitig dein maximales Verlustrisiko. 💰

**Wie viel Prämie ist angemessen?**
Die App berechnet automatisch die ATM-Option (at-the-money, Strike ≈ aktueller Kurs) für dich.

**Unsere Gewinnverhältnis-Formel:**
- **2:1 MIN**: Gewinn = 2× Prämie → Option bei Verfall wert: 3× Prämie (Minimum-Ziel)
- **3:1 BASE**: Gewinn = 3× Prämie → Option bei Verfall wert: 4× Prämie (Standard-Ziel)
- **4:1 BEST**: Gewinn = 4× Prämie → Option bei Verfall wert: 5× Prämie (Optimum)

**Beispiel CALL:**
- Strike: $200, Prämie: $5
- ZIEL 2:1 MIN:  $200 + 3×$5 = **$215**  (Minimum, sofort sichern)
- ZIEL 3:1 BASE: $200 + 4×$5 = **$220**  (Standard-Exit)
- ZIEL 4:1 BEST: $200 + 5×$5 = **$225**  (nur bei sehr starkem Trend halten)

Diese Zielkurse siehst du in der Preis-Leiter auf der Trend-Signale-Seite.
Die **IV-Reichweite** (blaues Band) zeigt dir, was statistisch in der Optionslaufzeit möglich ist."""),

    (["dte", "laufzeit", "restlaufzeit", "wie lange"],
     """**DTE** steht für *Days to Expiration* — die Restlaufzeit der Option in Tagen.

**Empfehlungen je nach Signal-Timeframe:**
| Signal-TF | Empfohlene DTE | Begründung |
|-----------|----------------|------------|
| Monatschart | ~120T | Langer Trend braucht Zeit |
| Wochenchart | ~70T | 2–3 Monate Spielraum |
| Tageschart | ~40T | 4–6 Wochen |
| 4H-Chart | ~21T | Kurzfristige Bewegung |

**Goldene Regel:** Kaufe immer **mehr DTE als du brauchst!**
Wenn deine Thesis in 3 Wochen aufgeht, brauche mindestens 45T DTE.
So vermeidest du, dass Zeitwertverfall (Theta) deinen Gewinn auffrisst.

**Theta** ist dein Feind — je näher am Verfall, desto schneller verliert die Option Zeitwert!"""),

    (["iv", "implied volatility", "implizierte volatilität", "was ist iv"],
     """**IV** (Implied Volatility) ist die vom Markt erwartete Schwankungsbreite einer Aktie.

**Warum ist IV für uns wichtig?**
1. **Preis der Option**: Hohe IV = teure Optionen, niedrige IV = günstige Optionen
2. **Erwartete Bewegung**: 1σ-Move = Kurs × (IV/100) × √(DTE/365)
3. **Einstiegsqualität**: Wir bevorzugen Optionen mit "günstiger" oder "normaler" IV

**IV-Rating in der App:**
- 🟢 **sehr günstig / günstig**: Option ist relativ billig — idealer Zeitpunkt
- 🟡 **normal**: Faire Bewertung — ok
- 🔴 **erhöht / teuer**: Option ist teuer — möglicherweise Spread statt Long Option erwägen

**1σ-Linie**: In der S/R-Leiter siehst du eine blaue gestrichelte Linie — das ist die statistisch
erwartete Bewegung innerhalb der Laufzeit. Ein gutes Ziel liegt innerhalb dieser Reichweite!"""),

    # ── S/R Levels ────────────────────────────────────────────────────────────
    (["support", "widerstand", "unterstützung", "sr level", "s/r", "preisleiter", "preis-leiter"],
     """Die **Preis-Leiter** in der Trend-Signale-Seite zeigt drei Ebenen klar getrennt: 📊

**1. Echte S/R-Level** (aus 1 Jahr Kurshistorie):
- **W1, W2, W3, W4** = Widerstände oberhalb des Kurses (rot) — wo der Kurs auf Verkaufsdruck treffen könnte
- **U1, U2, U3, U4** = Unterstützungen unterhalb (grün) — wo der Kurs Halt finden könnte
- Diese sind KEINE Ziele! Sie beschreiben die Kursstruktur.

**2. Gewinn-Ziele** (basierend auf deiner Option):
- 🎯 **ZIEL 2:1 MIN**: Mindest-Ziel — bei Gewinn = 2× Prämie sofort sichern
- ✅ **ZIEL 3:1 BASE**: Standard-Ziel — Gewinn = 3× Prämie
- 🏆 **ZIEL 4:1 BEST**: Optimum — nur bei sehr starkem Trend halten

**3. IV-Reichweite** (blaues Banner oben):
- Zeigt, wie weit sich der Kurs statistisch in der Optionslaufzeit bewegen kann
- 1σ = 68% Wahrscheinlichkeit, innerhalb dieser Spanne zu bleiben
- Gibt dir ein Gefühl, welche ZIELE realistisch erreichbar sind

**Strategie:**
- Schau ob dein ZIEL 3:1 innerhalb der IV-Reichweite liegt — wenn ja: realistisch!
- Vergleiche ZIEL mit W1/U1 — liegt ein Widerstand VOR dem Ziel? Dann könnte es schwer werden."""),

    # ── Trade Management ──────────────────────────────────────────────────────
    (["trade management", "position verwalten", "wo eingeben", "wie einbuchen"],
     """Das **Trade Management** (Seite 4) ist dein Cockpit für laufende Positionen! 🎛️

**So funktioniert es:**
1. Trade eintragen: Ticker, Typ (CALL/PUT), Strike, Verfall, Prämie
2. Die App holt automatisch den aktuellen Optionspreis
3. Du siehst sofort: P&L, DTE, Empfehlung

**Was die App automatisch berechnet:**
- 📊 **P&L**: Aktueller Gewinn/Verlust in USD und %
- ⏳ **Innerer Wert**: Wie viel ist die Option "real" wert (ITM-Anteil)?
- 🕐 **Zeitwert-Saldo**: Wie viel Zeitwert ist noch übrig?
- 🎯 **Empfehlung**: Halten / Rollen / Einbuchen / Exit

**Empfehlungs-Logik:**
- ✅ **Halten**: Trend intakt, DTE ausreichend
- 🔄 **Rollen**: DTE ≤ 21 Tage, Position noch sinnvoll
- 📦 **Einbuchen**: PUT stark ITM mit attraktivem Strike
- 🚪 **Exit prüfen**: STI dreht gegen die Position"""),

    (["rollen", "was ist rollen", "roll"],
     """**Rollen** bedeutet, eine auslaufende Option durch eine neue mit spätererem Verfall zu ersetzen. 🔄

**Wann rollen?**
- DTE ≤ 21 Tage (die App empfiehlt es automatisch ab dieser Schwelle)
- Der Trend ist noch intakt (STI noch in gleicher Richtung)
- Die Option ist noch nicht am Ziel

**Wie funktioniert das in der Praxis?**
1. Aktuelle Option schließen (verkaufen)
2. Neue Option mit gleichem Strike, aber späterem Verfall kaufen
3. Die Differenz der Prämien ist dein Netto-Aufwand

**Wann NICHT rollen?**
- STI hat sich umgekehrt (Gegentrend)
- Option ist tief ITM und Einbuchen wäre besser
- DTE noch > 21 Tage — Gegenbewegung erst abwarten!"""),

    (["exit", "wann verkaufen", "wann schließen", "stop loss"],
     """Die **Exit-Strategie** ist genauso wichtig wie der Einstieg! 🚪

**Exit-Signale in der App:**
1. 🔴 **STI dreht um** (Gegentrend-Signal) → sofort schließen
2. 🎯 **Ziel erreicht** (2:1 oder 3:1 Zone) → Gewinne sichern
3. ⏳ **DTE ≤ 5 Tage** → Immer schließen (Gamma-Risiko!)
4. 📅 **Earnings-Warnung** → Vor dem Termin schließen (IV-Crush)

**Gewinn-Sicherung:**
- Bei 2:1 Gewinn: mindestens die Hälfte der Position schließen
- Den Rest laufen lassen auf 3:1 oder STI-Exit
- **Niemals** bis zum Verfall halten (außer deep ITM)

**Stop-Loss:**
- Ich empfehle mental: -50% der Prämie als maximaler Verlust
- Das bedeutet: 1 Verlust wird durch 1 Gewinn (2:1) mehr als ausgeglichen"""),

    # ── Backtest ──────────────────────────────────────────────────────────────
    (["backtest", "win rate", "trefferquote", "historisch"],
     """Der **Backtest** in der App analysiert 10 Jahre historische Daten für jedes Signal! 📈

**Was der Backtest misst:**
- Alle historischen STI-Crossovers der gleichen Art
- Gemessen wird die Kurs-Performance 20 Handelstage danach
- Ergebnis: **Win-Rate** (Trefferquote) und **Erwartungswert**

**Was du siehst:**
- **Trefferquote**: Wie oft war der Kurs nach 20 Tagen in der richtigen Richtung?
- **Ø Gewinn-Move**: Durchschnittliche Kursbewegung bei Gewinn-Trades
- **Erwartungswert (EV)**: Statistischer Ertrag pro Trade auf die Prämie

**Interpretation:**
- EV > 0: Statistisch vorteilhafter Trade
- EV < 0 (rot): Vorsicht — historisch schwache Konstellation
- Win-Rate ≥ 60%: Starkes Signal
- Win-Rate < 50%: Skeptisch sein

**Wichtig:** Vergangene Performance ist kein Garant für die Zukunft!
Der Backtest ist ein zusätzliches Filter-Kriterium, kein Versprechen."""),

    # ── Investoren-Check ──────────────────────────────────────────────────────
    (["buffett", "munger", "dalio", "ackman", "simons", "investoren check", "hedge fund"],
     """Der **Investoren-Check** (Seite 9) prüft deinen Trade nach den Philosophien von 5 Legenden! 🧠

**Die 5 Investoren:**
- 🎩 **Warren Buffett** — Value, Burggraben, langfristige Qualität
- 📚 **Charlie Munger** — Mentale Modelle, Circle of Competence, Simplizität
- 🌊 **Ray Dalio** — Makro-Trends, Risk Parity, Diversifikation
- 🦁 **Bill Ackman** — Hochkonzentrierte Wetten, Aktivismus, Katalysator
- 🤖 **Jim Simons** — Quantitativ, Statistik, Erwartungswert, Muster

**Wie nutze ich es?**
1. Trade-Details eingeben (Ticker, Strike, DTE, Prämie)
2. STI-Score und Marktregime aus der Trend-Signale-Seite übertragen
3. Die 5 Investoren geben ihre "Zustimmung" in %

Wenn alle 5 zustimmen (≥70%) — sehr starkes Setup! Wenn alle ablehnen — Trade kritisch überdenken.

**Hinweis:** Das ist ein Bildungs-Tool basierend auf bekannten Investmentprinzipien, keine echte Beratung!"""),

    # ── IBKR ─────────────────────────────────────────────────────────────────
    (["ibkr", "interactive brokers", "tws", "flex query", "anbindung broker"],
     """Die **IBKR-Integration** (Seite 11) erklärt, wie du dein Portfolio direkt in die App importierst!

**Es gibt zwei Methoden:**

🔌 **Methode 1: Flex Queries (empfohlen)**
- Einfachste Variante — kein Code nötig
- IBKR generiert automatisch CSV/XML mit deinen Positionen
- Die App liest die Datei ein und zeigt alles im Trade Management

📡 **Methode 2: TWS API (fortgeschritten)**
- Echtzeit-Daten direkt aus dem laufenden TWS
- Erfordert Python-Kenntnisse und API-Einrichtung
- Volle Automatisierung möglich

**Für Anfänger empfehle ich Flex Queries** — der gesamte Prozess dauert ~15 Minuten beim ersten Mal.
Schau dir die Schritt-für-Schritt-Anleitung auf Seite 11 an!"""),

    # ── Prozess / Workflow ────────────────────────────────────────────────────
    (["wie funktioniert", "workflow", "prozess", "schritt für schritt", "anfangen"],
     """Hier ist der empfohlene **Workflow** mit der Stillhalter AI App:

**1️⃣ Markt-Überblick** (täglich, 2 Min.)
→ Seite 1 (Scanner): Wie steht der Markt? SPY/QQQ Regime?

**2️⃣ Signal-Suche** (täglich, 5 Min.)
→ Seite 7 (Trend Signale): Neue NOW-Signale mit Score ≥ 5?

**3️⃣ Setup analysieren** (bei Signal, 10 Min.)
→ S/R-Leiter: Wo ist das 2:1 / 3:1 Ziel?
→ IV-Rating: Option günstig oder teuer?
→ Backtest: Ist der EV positiv?
→ Investoren-Check (Seite 9): Würden die Profis mitmachen?

**4️⃣ Option auswählen** (5 Min.)
→ ATM-Option mit passendem DTE (≥ 2× erwartete Haltedauer)
→ Prämie notieren, Gewinnverhältnis prüfen

**5️⃣ Trade eintragen** (1 Min.)
→ Seite 4 (Trade Management): Position erfassen

**6️⃣ Täglich überwachen** (2 Min./Trade)
→ Empfehlung prüfen: Halten / Exit-Signal?"""),

    # ── Fehler / Unbekannt ────────────────────────────────────────────────────
    (["indikator formel", "ema", "wie berechnet", "quellcode", "algorithmus", "geheimnis"],
     """Das ist eine sehr spezifische Frage zu unseren proprietären Methoden! 🔒

Die genauen mathematischen Details unserer Indikatoren und Algorithmen sind
Betriebsgeheimnis der Stillhalter AI App — das ist es, was unsere Plattform
einzigartig macht.

Was ich dir sagen kann:
- Der STI basiert auf **Trendlinien** (Fast & Slow), die Crossover-Signale generieren
- Die Stärke liegt in der **Multi-Timeframe-Confluence** — nicht in einem einzelnen Wert
- Alle Parameter wurden über Jahre empirisch optimiert

**Für weitere Infos:** Kontaktiere das Stillhalter AI App Team direkt.
Für die Nutzung der App brauchst du die Formel nicht — die Ergebnisse sprechen für sich! 😊"""),
]

# ══════════════════════════════════════════════════════════════════════════════
# ANTWORT-ENGINE
# ══════════════════════════════════════════════════════════════════════════════

def _extract_pdf_text(file_bytes: bytes) -> str:
    """Extrahiert Text aus einem PDF via pypdf."""
    if not _PYPDF_OK:
        return ""
    try:
        reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        pages_text = []
        for page in reader.pages:
            t = page.extract_text()
            if t:
                pages_text.append(t.strip())
        return "\n\n".join(pages_text)
    except Exception as e:
        return f"[Fehler beim Lesen: {e}]"


def _chunk_text(text: str, chunk_size: int = 500, overlap: int = 80) -> list[str]:
    """Teilt langen Text in überlappende Chunks auf."""
    words = text.split()
    chunks = []
    step = max(1, chunk_size - overlap)
    for i in range(0, len(words), step):
        chunk = " ".join(words[i:i + chunk_size])
        if chunk.strip():
            chunks.append(chunk)
    return chunks


def _find_answer(user_input: str) -> str:
    """Findet die beste Antwort auf die Nutzerfrage.
    Durchsucht zuerst die integrierte Wissensbasis, dann hochgeladene Dokumente.
    """
    q = user_input.lower().strip()
    q = re.sub(r"[?!.,;:]", "", q)
    query_words = [w for w in q.split() if len(w) > 2]

    # 1) Integrierte Keyword-Suche
    best_score = 0
    best_answer = None
    for keywords, answer in OLLI_KNOWLEDGE:
        score = sum(len(kw) for kw in keywords if kw in q)
        if score > best_score:
            best_score = score
            best_answer = answer

    if best_answer and best_score >= 3:
        return best_answer

    # 2) Hochgeladene Dokumente durchsuchen
    uploaded_chunks = st.session_state.get("olli_doc_chunks", [])
    if uploaded_chunks and query_words:
        chunk_scores = []
        for chunk_info in uploaded_chunks:
            text_lower = chunk_info["text"].lower()
            score = sum(1 for w in query_words if w in text_lower)
            # Bonus für längere Wörter (spezifischere Begriffe)
            score += sum(len(w) * 0.1 for w in query_words if len(w) > 5 and w in text_lower)
            chunk_scores.append((score, chunk_info))

        chunk_scores.sort(key=lambda x: x[0], reverse=True)
        top_score, top_chunk = chunk_scores[0]

        if top_score >= 1:
            # Kontext: bis zu 3 beste Chunks zusammenführen
            context_chunks = [c["text"] for s, c in chunk_scores[:3] if s >= 1]
            context = "\n\n---\n\n".join(context_chunks)
            doc_name = top_chunk["source"]

            return (
                f"📄 **Aus deinem Dokument: _{doc_name}_**\n\n"
                + context[:2000]
                + ("\n\n_[…Dokument enthält mehr Text]_" if len(context) > 2000 else "")
            )

    # 3) Fallback (integriert, niedrig-scored)
    if best_answer:
        return best_answer

    return """Hmm, das ist eine interessante Frage! Ich bin mir nicht ganz sicher, was du meinst. 🤔

Lass mich dir ein paar Themen anbieten, bei denen ich helfen kann:

- **STI-Signal**: Was bedeutet ein NOW oder GET READY Signal?
- **Optionen**: Wann CALL, wann PUT? Wie wähle ich Strike und DTE?
- **IV-Kursziele**: Wie finde ich gute Einstiegs- und Ausstiegspunkte?
- **Trade Management**: Wie verwalte ich laufende Positionen?
- **Backtest**: Wie interpretiere ich Win-Rate und Erwartungswert?
- **Workflow**: Wie nutze ich die App Schritt für Schritt?

Oder **lade ein PDF / Transkript hoch** — dann kann ich direkt aus deinen eigenen Unterlagen antworten! 📄

Stell mir einfach eine konkretere Frage — ich helfe gerne! 😊"""

# ══════════════════════════════════════════════════════════════════════════════
# CHAT UI
# ══════════════════════════════════════════════════════════════════════════════

# Header
st.html(f"""
<div style='display:flex;align-items:center;gap:16px;margin-bottom:4px'>
  {get_logo_html(height=44)}
  <div style='border-left:1px solid #222;height:40px;margin:0 4px'></div>
  <div>
    <div style='font-size:1.4rem;font-weight:800;color:#f0f0f0;font-family:sans-serif'>
      🤖 Option-Olli — Dein KI-Assistent
    </div>
    <div style='font-size:0.8rem;color:#666;font-family:sans-serif'>
      Stell mir alles über die Stillhalter AI App — ich bin 24/7 für dich da!
    </div>
  </div>
</div>
""")

# Olli Avatar Intro
st.html("""
<div style='background:linear-gradient(135deg,#0a0a18 0%,#0e0e1a 100%);
     border:1px solid #3b82f633;border-radius:12px;padding:14px 18px;
     display:flex;align-items:center;gap:16px;margin-bottom:12px'>
  <div style='font-size:3.5rem;line-height:1'>🤖</div>
  <div>
    <div style='font-size:0.95rem;font-weight:700;color:#3b82f6;font-family:sans-serif;
         margin-bottom:2px'>Option-Olli ist online ✅</div>
    <div style='font-size:0.78rem;color:#888;font-family:sans-serif;line-height:1.5'>
      Ich beantworte alle Fragen zur Stillhalter AI App — von den Signalen über
      Strategien bis zum Trade Management. Was möchtest du wissen?
    </div>
  </div>
</div>
""")

# Session State initialisieren
if "olli_messages" not in st.session_state:
    st.session_state["olli_messages"] = []
if "olli_doc_chunks" not in st.session_state:
    st.session_state["olli_doc_chunks"] = []
if "olli_doc_names" not in st.session_state:
    st.session_state["olli_doc_names"] = []

# ── Wissens-Upload ────────────────────────────────────────────────────────────
with st.expander(
    f"📚 Wissens-Upload — PDFs & Transkripte"
    f"{'  ·  ' + str(len(st.session_state['olli_doc_names'])) + ' Dokument(e) geladen' if st.session_state['olli_doc_names'] else ''}",
    expanded=False
):
    st.markdown(
        "<div style='font-size:0.8rem;color:#888;font-family:sans-serif;margin-bottom:8px'>"
        "Lade PDFs, Transkripte oder Textdateien hoch — Option-Olli durchsucht sie automatisch "
        "und antwortet direkt aus deinen Unterlagen."
        "</div>",
        unsafe_allow_html=True
    )

    up1, up2 = st.columns([3, 1])
    with up1:
        uploaded_files = st.file_uploader(
            "PDF, TXT oder MD hochladen",
            type=["pdf", "txt", "md"],
            accept_multiple_files=True,
            key="olli_uploader",
            label_visibility="collapsed",
        )
    with up2:
        if st.button("🗑️ Alle Docs löschen", use_container_width=True,
                     key="olli_clear_docs",
                     help="Löscht alle hochgeladenen Dokumente aus dem Speicher"):
            st.session_state["olli_doc_chunks"] = []
            st.session_state["olli_doc_names"] = []
            st.rerun()

    if uploaded_files:
        new_count = 0
        for uf in uploaded_files:
            if uf.name in st.session_state["olli_doc_names"]:
                continue  # bereits geladen
            with st.spinner(f"📄 Verarbeite {uf.name}…"):
                raw_bytes = uf.read()
                if uf.type == "application/pdf" or uf.name.lower().endswith(".pdf"):
                    if not _PYPDF_OK:
                        st.error("pypdf nicht verfügbar — PDF-Extraktion nicht möglich.")
                        continue
                    text = _extract_pdf_text(raw_bytes)
                else:
                    # TXT / MD
                    text = raw_bytes.decode("utf-8", errors="replace")

                if not text or text.startswith("[Fehler"):
                    st.warning(f"⚠️ Konnte keinen Text aus {uf.name} extrahieren.")
                    continue

                chunks = _chunk_text(text)
                for chunk in chunks:
                    st.session_state["olli_doc_chunks"].append({
                        "source": uf.name,
                        "text": chunk,
                    })
                st.session_state["olli_doc_names"].append(uf.name)
                new_count += 1
                st.success(f"✅ **{uf.name}** — {len(chunks)} Textblöcke extrahiert ({len(text):,} Zeichen)")

        if new_count > 0:
            st.rerun()

    # Geladene Docs anzeigen
    if st.session_state["olli_doc_names"]:
        st.markdown(
            "<div style='font-size:0.72rem;color:#555;font-family:sans-serif;"
            "margin-top:6px;border-top:1px solid #1a1a1a;padding-top:8px'>"
            "<b style='color:#888'>Geladene Dokumente:</b> "
            + " &nbsp;·&nbsp; ".join(
                f"<span style='color:#d4a843'>📄 {n}</span>"
                for n in st.session_state["olli_doc_names"]
            )
            + "</div>",
            unsafe_allow_html=True
        )

# Vorschläge (Schnell-Fragen)
st.html("""
<div style='font-size:0.65rem;color:#555;text-transform:uppercase;
     letter-spacing:0.08em;font-family:sans-serif;margin-bottom:6px'>
  Schnell-Fragen
</div>
""")

quick_cols = st.columns(5)
QUICK_QUESTIONS = [
    "Was ist der STI?",
    "Wann CALL vs PUT?",
    "Wie exit ich einen Trade?",
    "Was bedeutet GET READY?",
    "Wie nutze ich den Backtest?",
]

for i, (qcol, qq) in enumerate(zip(quick_cols, QUICK_QUESTIONS)):
    with qcol:
        if st.button(qq, key=f"quick_{i}", use_container_width=True):
            st.session_state["olli_messages"].append({"role": "user", "content": qq})
            answer = _find_answer(qq)
            st.session_state["olli_messages"].append({"role": "olli", "content": answer})
            st.rerun()

st.markdown("---")

# Chat-Verlauf anzeigen
chat_container = st.container()
with chat_container:
    for msg in st.session_state["olli_messages"]:
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(msg["content"])
        else:
            with st.chat_message("assistant", avatar="🤖"):
                st.markdown(msg["content"])

# Eingabe
if user_q := st.chat_input("Stell Option-Olli eine Frage…"):
    st.session_state["olli_messages"].append({"role": "user", "content": user_q})
    with st.chat_message("user"):
        st.markdown(user_q)

    with st.chat_message("assistant", avatar="🤖"):
        with st.spinner("Option-Olli denkt…"):
            time.sleep(0.4)  # kurze Denkpause für natürlicheren UX
            answer = _find_answer(user_q)
        st.markdown(answer)

    st.session_state["olli_messages"].append({"role": "olli", "content": answer})

# Reset-Button
if st.session_state["olli_messages"]:
    st.markdown("")
    if st.button("🗑️ Chat leeren", key="olli_clear"):
        st.session_state["olli_messages"] = []
        st.rerun()

# Footer
st.html("""
<div style='margin-top:24px;padding-top:12px;border-top:1px solid #1a1a1a;
     font-size:0.65rem;color:#444;font-family:sans-serif;line-height:1.6'>
  🔒 <b>Vertraulich:</b> Alle Inhalte unterliegen der bestätigten Nutzungsvereinbarung.
  Option-Olli gibt keine Anlageberatung. Alle Angaben sind Bildungsinhalte.
  Vergangene Performance ist kein Garant für zukünftige Ergebnisse.
</div>
""")
