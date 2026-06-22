# Stillhalter AI — Gesamt-Briefing (zum Einfügen in Claude Chat)

Eine einzige Datei mit allem: Projektüberblick, alle Seiten 0–20 im Detail,
Automatisierungsziel (Paperclip + Obsidian) und das Agenten-Konzept.

---

## 1. Projektüberblick

Ich betreibe eine deutschsprachige Optionshandels-Community (Masterclass auf Circle)
und habe dafür eine Web-App gebaut: ein **Streamlit-Multipage-Dashboard** (Python) für
Stillhalter-/Optionsstrategien (Cash Secured Puts, Covered Calls, Short Strangles).

**Tech-Stack & Deployment**
- Python / Streamlit, 21 Seiten (siehe unten)
- Deployment auf **Railway** (Auto-Deploy aus GitHub `main`), persistentes **Volume**
  für Caches (`STILLHALTER_DATA_DIR=/data`)
- Repo: `StillhalterCommunity/stillhalter-ai-app` · Live: `stillhalter-ai.up.railway.app`

**Datenquellen**
- **Optionsdaten** (Bid/Ask, IV, Greeks): Massive/Polygon API (Plan deckt nur Optionen ab)
- **Aktien** (Kurse, Historie, Fundamentaldaten): yfinance
- Persistenter Disk-Cache + täglicher Morgen-Prefetch

**Kern-Workflows (heute teils manuell angestoßen)**
1. **Watchlist-Scanner** sucht passende Optionen → Ergebnis persistent → speist „Top 9".
2. **Trade Cards**: fertige Community-Posts (Kurz-/Langversion) inkl. Auto-Fill der
   Optionsdaten, OptionStrat-Links, Indikatoren; **Auto-Posting nach Circle**; Spracheingabe.
3. **Trade Monitor**: verfolgt laufende Trades visuell bis zum Verfall.

---

## 2. Die Seiten 0–20 im Detail

**0 · Startseite (`app.py`)** — Login, Daten-Preload (alle 15 Min), Navigation,
Theme-Umschaltung (dunkel/hell), Cache-/Neustart-Steuerung, Speicher-Diagnose.
*Hook: Health-/Status-Quelle.*

**1 · Marktanalyse / News** — Schneller Markt-Intelligence-Hub: Watchlist-Aktien,
X/Twitter, Märkte, Makro. *Hook: Input für Newsletter & Research.*

**2 · Fundamentalanalyse** — Watchlist-Screening nach Market Cap, KGV/Forward-KGV, PEG.
*Hook: Vorfilter für den Scanner.*

**3 · Aktienanalyse („Stillhalter Analyzer")** — Tiefenanalyse einer Aktie: Optionsfilter,
technische Zusammenfassung, Greeks, Kennzahlen. *Hook: Detail-Check pro Kandidat.*

**4 · Watchlist Scanner** — Herzstück: ~225 Aktien nach CSP/Covered Call/Short Strangle
scannen, Vorder-/Hintergrund, technische Vorfilter, CRV-Score, Off-Hours-Modus; persistent
gespeichert. *Hook: Kern-Trigger.*

**5 · Top 9 Trading-Ideen** — Beste 3 Optionen je IV-Klasse (Low/Mid/High) aus dem letzten
Scan, mit Risiko-Einordnung + Share-Text. *Hook: Selektions-Output.*

**6 · Zukunftsprognose** — Indikator-Proximity: welche Aktien nähern sich einem Setup
(kein ML). *Hook: Vorlauf-Watchlist.*

**7 · Trade Management** — Bewertet offene Positionen nach Stillhalter-Regeln; CSV-Import
(IBKR Flex Query) oder manuell. *Hook: Bestands-Überwachung.*

**8 · Trend Signale (STI)** — Stillhalter Trend Indikator, Multi-Timeframe-Confluence:
„NOW" (Cross gerade) vs. „GET READY" (steht bevor). *Hook: Einstiegs-Timing.*

**9 · Investoren-Check** — 5 legendäre Hedge-Fund-Manager bewerten einen Trade nach ihren
Prinzipien. *Hook: qualitative „Jury".*

**10 · Option-Olli Chat** — KI-Coach für Plattform-/Strategiefragen (ohne proprietäre
Indikator-Geheimnisse). *Hook: Member-Assistent auf Wissensbasis.*

**11 · Prozess** — Visuelle Darstellung des App-Workflows (Info-Seite).

**12 · IBKR Integration** — Schritt-für-Schritt: Interactive Brokers via Flex Queries &
TWS API anbinden.

**13 · Rechtliches** — Datenschutz, Haftungsausschluss, Impressum.

**14 · Order-Planung & IBKR-Freigabe** — Orders als „Held" in TWS (transmit=False), finale
Freigabe in TWS durch den Nutzer. *Hook: Ausführung mit Mensch-Gate.*

**15 · Datenquellen** — Übersicht & Test der Datenquellen (Yahoo Finance, Massive/Polygon),
API-Status. *Hook: Daten-Health-Check.*

**16 · Sentiment-Analyse (Social Arbitrage)** — Virale Trends entdecken (Reddit, Google
Trends, StockTwits, Product Hunt, HN) → Produkte → Aktien mappen → Einpreisung bewerten.
*Hook: alternativer Ideen-Strom.*

**17 · Trade Cards** — Fertige Community-Posts (Kurz-/Langversion) inkl. Auto-Fill der
Optionsdaten, OptionStrat-Links, Fundamental-/Chart-Indikatoren; Spracheingabe;
Circle-Auto-Post. *Hook: Redaktions-Output.*

**18 · Markt-Newsletter** — Täglicher Börsennewsletter: 11 Sektoren, Fundamentals, TA,
Optionsempfehlung; Quellen Yahoo RSS, yfinance News, MarketWatch, Fear & Greed.
*Hook: Redaktions-Output (täglich).*

**19 · Signal Pipeline & Freigabe-Gate** — Scan-Kandidaten bewerten → als Trade Card
speichern → Status täglich prüfen → **Freigabe** → WhatsApp-Text + Circle-HTML-Vorschau →
senden/posten. *Hook: zentrales Mensch-Gate.*

**20 · Trade Monitor** — Live-Ticker für gespeicherte Trades bis zum Verfall: Zeit-Balken,
Kurs↔Strike-Skala, Verfall-%, Handlungsempfehlung. *Hook: Monitoring-Agent + Alerts.*

---

## 3. Ziel: Automatisierung mit Paperclip (paperclip.ing) & Obsidian

**Paperclip** ist eine open-source, self-hosted Plattform zum **Orchestrieren von
KI-Agenten** (Org-Chart aus Agenten, Ticket-System mit Audit-Trail, Heartbeat-Scheduling,
Budgets pro Agent, Freigabe-Gates, modell-agnostisch, per Extensions erweiterbar).

Ich möchte meine Stillhalter-Prozesse als Agenten-Tasks abbilden, sodass die Kette
**Scan → Trade-Idee bewerten → Trade Card erzeugen → posten → Trade Monitor** weitgehend
automatisch läuft und ich nicht jedes Element manuell bedienen muss. Zusätzlich soll eine
**Obsidian-Anbindung** Trades, Ideen und Notizen automatisch als Markdown-Notizen ablegen
(Wissensbasis, Verlinkung, Rückblick).

### Vorgeschlagene Agenten (Rollen)
1. **Daten-Agent** — morgens Daten ziehen (Prefetch), Quellen-Health prüfen (15, app.py).
2. **Scanner-Agent** — Scan starten (4), Top-9 ableiten (5).
3. **Research-Agent** — Kandidaten via Fundamental (2), Einzelanalyse (3), Trend/STI (8),
   Zukunftsprognose (6), Investoren-Check (9), Sentiment (16) bewerten → konsolidierte
   Empfehlung + Begründung.
4. **Redaktions-Agent** — Trade Cards (17) + Newsletter (18) als Entwürfe in die Signal
   Pipeline (19).
5. **Freigabe-Gate (Mensch = du)** — in der Signal Pipeline (19) freigeben („posten erst
   nach Bestätigung").
6. **Publishing-Agent** — nach Freigabe nach Circle posten / WhatsApp-Text (17/19).
7. **Monitor-Agent** — laufende Trades (20) + Bestand (7) überwachen, Alerts bei
   Handlungsbedarf (nah am Strike / im Geld / Verfall naht).
8. **Order-Agent (optional, mit Gate)** — Held-Orders in TWS vorbereiten (14/12),
   Auslösung durch dich.
9. **Wissens-Agent (Obsidian)** — jede Idee, jeden Trade, jede Entscheidung als
   Markdown-Notiz in den Vault (Frontmatter: Ticker, Strategie, Strike, Verfall, Status,
   CRV, Datum).
10. **Concierge/Chat-Agent** — Option-Olli (10) beantwortet Member-Fragen auf Basis der
    Wissensbasis.

### Zusammenarbeit — täglicher Ablauf (Heartbeat)
```
Morgens (Markt-Vorlauf)
  Daten-Agent  ──►  Scanner-Agent  ──►  Research-Agent
                                            │
                                            ▼
                                     Redaktions-Agent  (Trade Cards + Newsletter)
                                            │  (Entwürfe in Signal Pipeline)
                                            ▼
                                ┌── FREIGABE-GATE (du) ──┐
                                │                        │
                              freigegeben            verworfen
                                │                        │
                                ▼                        ▼
                         Publishing-Agent          (Archiv/Notiz)
                                │
                                ▼
        ─────────  Monitor-Agent (laufend, Intraday-Heartbeat)  ─────────
                                │  (Alerts bei Handlungsbedarf)
                                ▼
                        Order-Agent (optional, Mensch-Gate in TWS)

Querschnitt: Wissens-Agent protokolliert JEDEN Schritt nach Obsidian.
```

### Kontrolle behält der Mensch
- **Posten** nur nach deiner Bestätigung (Signal Pipeline, Seite 19).
- **Orders** nur als „Held" in TWS; finale Auslösung durch dich (Seite 14).
- Paperclip-**Budgets pro Agent** verhindern Kostenausreißer.

### Technischer Enabler (empfohlener erster Schritt)
Kernlogik aus der Streamlit-UI in **aufrufbare Funktionen / einen schlanken API-Layer**
herauslösen (Scan, Research-Bewertung, Trade-Card-Generierung, Posting, Monitoring,
Obsidian-Export). Dann nutzen Streamlit-UI, Paperclip-Agenten, Cronjobs und der
Obsidian-Export dieselbe Logik — die App bleibt „Schaltzentrale", Agenten übernehmen die
Routine. Scan-Ergebnisse, Trade Cards und Trade-Status liegen bereits persistent im Volume
und werden zu zentralen „Tabellen", auf die Agenten lesend/schreibend zugreifen.

---

## 4. Fragen an Claude
1. Wie binde ich die bestehende Streamlit/Python-App auf Railway an Paperclip an — als
   Extension, über REST/Webhooks oder durch Herauslösen der Kernlogik in agent-aufrufbare
   Funktionen/Services?
2. Welche Architektur empfiehlst du, damit Paperclip-Agenten die Schritte als Tickets mit
   Freigabe-Gates ausführen (z. B. „posten erst nach meiner Bestätigung")?
3. Wie exportiere ich Scan-Ergebnisse, Trade Cards und Trade-Status automatisiert als
   Markdown nach Obsidian (Datei-Sync, Git, oder lokale Vault-Anbindung)?
4. In welcher Reihenfolge baue ich die Agenten am besten auf (MVP zuerst)?
