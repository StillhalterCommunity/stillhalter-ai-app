"""
Stillhalter AI App — Rechtliches
Datenschutzerklärung · Haftungsausschluss · Impressum
"""

import streamlit as st

st.set_page_config(
    page_title="Rechtliches · Stillhalter AI App",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

# ── Header ────────────────────────────────────────────────────────────────────
h1, h2 = st.columns([1, 6])
with h1:
    st.html(get_logo_html("white", 36))
with h2:
    st.html("""
    <div style='padding-top:4px'>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.8rem;
                    color:#f0f0f0;letter-spacing:0.04em'>RECHTLICHES</div>
        <div style='font-family:RedRose,sans-serif;font-weight:300;font-size:0.8rem;
                    color:#666;text-transform:uppercase;letter-spacing:0.12em;margin-top:2px'>
            Datenschutz · Haftungsausschluss · Impressum
        </div>
    </div>
    """)

st.html('<div class="gold-line"></div>')

tab_ds, tab_haft, tab_imp = st.tabs(["🔒 Datenschutz", "⚠️ Haftungsausschluss", "📋 Impressum"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1: DATENSCHUTZ
# ══════════════════════════════════════════════════════════════════════════════
with tab_ds:
    st.markdown("""
## Datenschutzerklärung

**Verantwortlicher im Sinne der DSGVO:**
Stillhalter Community
(Kontakt siehe Impressum)

---

### 1. Erhobene Daten

Die Stillhalter AI App erhebt und verarbeitet folgende Daten:

- **Zugangsdaten:** Bei der Anmeldung wird das verwendete Passwort (enthält den Nutzernamen) sowie Datum und Uhrzeit des Zugriffs protokolliert.
- **Nutzungsdaten:** Seitenaufrufe und Verweildauer werden intern für Betriebszwecke erfasst.
- **Börsendaten:** Alle Kursdaten werden in Echtzeit von Yahoo Finance abgerufen. Es werden keine persönlichen Finanzdaten des Nutzers gespeichert.

### 2. Zweck der Datenverarbeitung

Die Protokollierung des Logins dient ausschließlich:
- der Zugangskontrolle (nur autorisierte Beta-Nutzer),
- der internen Nutzungsanalyse zur Verbesserung der Plattform.

### 3. Datenweitergabe

Erhobene Daten werden **nicht** an Dritte weitergegeben. Yahoo Finance verarbeitet Datenanfragen gemäß eigener Datenschutzrichtlinie (yahoo.com/privacy).

### 4. Speicherdauer

Login-Protokolle werden für maximal **90 Tage** gespeichert und danach automatisch gelöscht.

### 5. Rechte der Nutzer

Als Nutzer hast du das Recht auf:
- **Auskunft** über gespeicherte Daten
- **Löschung** deiner Daten auf Anfrage
- **Widerspruch** gegen die Verarbeitung

Anfragen richten an den Verantwortlichen (siehe Impressum).

### 6. Cookies und lokale Speicherung

Die App verwendet ausschließlich technisch notwendige Sitzungsdaten (Session State) im Browser-Speicher, die beim Schließen des Browsers gelöscht werden. Es werden keine Tracking-Cookies gesetzt.

### 7. Externe Dienste

- **Yahoo Finance API:** Kursdaten werden von Yahoo Finance abgerufen. Keine personenbezogenen Daten werden übermittelt.
- **Streamlit / Railway:** Hosting-Dienst. Serverprotokolle können IP-Adressen temporär speichern.

---
*Zuletzt aktualisiert: April 2025*
""")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2: HAFTUNGSAUSSCHLUSS
# ══════════════════════════════════════════════════════════════════════════════
with tab_haft:
    st.html("""
<div style='background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.3);
            border-radius:10px;padding:16px 20px;margin-bottom:20px'>
    <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1rem;
                color:#ef4444;margin-bottom:6px'>⚠️ Wichtiger Hinweis</div>
    <div style='font-family:RedRose,sans-serif;font-size:0.88rem;color:#ccc;line-height:1.7'>
        Die Stillhalter AI App ist ein <strong>Analyse- und Bildungswerkzeug</strong>,
        kein Finanzberatungsprodukt. Alle Informationen dienen ausschließlich zur
        allgemeinen Information und stellen <strong>keine Anlageberatung</strong> dar.
    </div>
</div>
""")

    st.markdown("""
## Haftungsausschluss

### 1. Keine Anlageberatung

Alle auf dieser Plattform angezeigten Informationen, Analysen, Signale, Scores und Empfehlungen dienen **ausschließlich zu Informations- und Bildungszwecken**. Sie stellen keine:
- Anlageberatung im Sinne des Wertpapierhandelsgesetzes (WpHG)
- Vermögensberatung oder Vermögensverwaltung
- Handelsempfehlung oder Aufforderung zum Kauf/Verkauf von Wertpapieren

dar.

### 2. Risikohinweis Optionshandel

Der Handel mit Optionen und anderen Derivaten ist mit **erheblichen Risiken** verbunden:

- Optionen können wertlos verfallen — der eingesetzte Kapitalbetrag (Prämie) kann vollständig verloren gehen.
- Bei ungedeckten Positionen (z. B. Naked Puts) können Verluste über den eingesetzten Betrag hinausgehen.
- Vergangene Performance von Signalen, Indikatoren oder Strategien ist **kein verlässlicher Indikator** für zukünftige Ergebnisse.
- Jeder Anleger trägt das volle Risiko seiner Handelsentscheidungen selbst.

### 3. Haftungsbeschränkung

Die Stillhalter Community und der Betreiber dieser Plattform übernehmen **keinerlei Haftung** für:
- Verluste, die durch die Nutzung der bereitgestellten Informationen entstehen
- Fehlerhafte, unvollständige oder veraltete Daten (Datenquelle: Yahoo Finance)
- Technische Ausfälle, Datenverluste oder Unterbrechungen des Dienstes
- Entscheidungen, die auf Basis der Plattform getroffen wurden

### 4. Datenqualität

Alle Kursdaten, Optionsketten, IV-Werte und Fundamentaldaten stammen von Yahoo Finance und können:
- Verzögerungen von bis zu 15–20 Minuten aufweisen
- Unvollständig oder fehlerhaft sein
- Außerhalb der Marktzeiten auf historischen Werten basieren

Die Korrektheit der Daten wird nicht garantiert.

### 5. Keine Lizenzierung

Diese Plattform ist nicht von der BaFin (Bundesanstalt für Finanzdienstleistungsaufsicht)
oder einer anderen Aufsichtsbehörde lizenziert oder reguliert.

---

**Durch die Nutzung der Plattform erklärst du, diesen Haftungsausschluss gelesen, verstanden und akzeptiert zu haben.**

---
*Zuletzt aktualisiert: April 2025 · Es gilt deutsches Recht*
""")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3: IMPRESSUM
# ══════════════════════════════════════════════════════════════════════════════
with tab_imp:
    st.markdown("""
## Impressum

### Angaben gemäß § 5 TMG

**Stillhalter Community**
Betreiber der Stillhalter AI App

*(Vollständige Adresse wird vor dem offiziellen Launch ergänzt)*

---

### Kontakt

**E-Mail:** kontakt@stillhalter-community.de *(Platzhalter — bitte anpassen)*

---

### Verantwortlich für den Inhalt nach § 55 Abs. 2 RStV

*(Name und Anschrift des Verantwortlichen — bitte vor Launch ergänzen)*

---

### Urheberrecht

Die auf dieser Plattform verwendeten Inhalte, Texte, Grafiken und Algorithmen
(insbesondere **Stillhalter Trend Model®**, **Stillhalter MACD Pro**, **Stillhalter Dual Stochastik**)
sind urheberrechtlich geschützt.

Die Vervielfältigung, Bearbeitung, Verbreitung und jede Art der Verwertung außerhalb
der Grenzen des Urheberrechts bedürfen der schriftlichen Zustimmung des Betreibers.

---

### Haftung für Links

Diese Seite enthält Links zu externen Webseiten (z. B. Yahoo Finance). Für die Inhalte
externer Links wird keine Haftung übernommen. Die verlinkten Seiten wurden zum Zeitpunkt
der Verlinkung auf mögliche Rechtsverstöße überprüft.

---

### Streitschlichtung

Die EU-Kommission stellt eine Plattform zur Online-Streitbeilegung (OS) bereit:
https://ec.europa.eu/consumers/odr

Wir sind nicht bereit oder verpflichtet, an Streitbeilegungsverfahren vor einer
Verbraucherschlichtungsstelle teilzunehmen.

---
*Stand: April 2025*
""")

    st.html("""
<div style='background:#111;border:1px solid #1e1e1e;border-radius:8px;
            padding:14px 18px;margin-top:16px;font-family:RedRose,sans-serif;
            font-size:0.8rem;color:#555;line-height:1.6'>
    <strong style='color:#666'>Hinweis:</strong> Dieses Impressum ist ein Entwurf für die Beta-Phase.
    Vor dem öffentlichen Launch müssen vollständige Pflichtangaben (Name, Adresse, ggf. USt-IdNr.)
    gemäß § 5 TMG ergänzt werden.
</div>
""")
