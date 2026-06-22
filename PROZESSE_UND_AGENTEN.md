# Stillhalter AI — Seiten 0–20 & Agenten-Konzept

Detailüberblick aller Programme/Seiten der App plus ein Konzept, wie KI-Agenten
(z. B. via Paperclip) diese Schritte automatisiert und zusammenarbeitend ausführen.

---

## Teil A — Die Seiten im Detail

### 0 · Startseite (`app.py`)
Login-Gate, Daten-Preload im Hintergrund (alle 15 Min), Navigation, Theme-Umschaltung
(dunkel/hell), Cache-/Neustart-Steuerung, Speicher-Diagnose (Volume aktiv?).
**Output:** Einstieg + „Top 9"-Vorschau. **Agenten-Hook:** Health-/Status-Quelle.

### 1 · Marktanalyse / News
Market-Intelligence-Hub im „Mando-Minutes"-Stil: schnell scannen, selektiv klicken.
Watchlist-Aktien zuerst, X/Twitter, Märkte, Makro.
**Output:** kuratierte News-/Marktlage. **Hook:** Input für Newsletter & Research.

### 2 · Fundamentalanalyse
Screening der Watchlist nach Fundamentaldaten (Market Cap, KGV/Forward-KGV, PEG …),
Filter + Tabelle.
**Output:** fundamental gefilterte Kandidaten. **Hook:** Vorfilter für den Scanner.

### 3 · Aktienanalyse (Einzelanalyse / „Stillhalter Analyzer")
Tiefenanalyse einer einzelnen Aktie: Optionsfilter, technische Zusammenfassung,
Greeks, Kennzahlen.
**Output:** Einzel-Setup-Bewertung. **Hook:** Detail-Check pro Kandidat.

### 4 · Watchlist Scanner
Herzstück: scannt ~225 Aktien nach passenden Optionen (CSP, Covered Call, Short
Strangle), Vorder-/Hintergrund-Scan, technische Vorfilter, CRV-Score, Off-Hours-Modus.
**Output:** Treffer-Tabelle, persistent gespeichert (Volume). **Hook:** Kern-Trigger.

### 5 · Top 9 Trading-Ideen
Verdichtet den letzten Scan zu den besten 3 Optionen je IV-Klasse (Low/Mid/High),
mit Risiko-Einordnung und Share-Text.
**Output:** Tages-Top-Ideen. **Hook:** Selektions-Output für die Redaktion.

### 6 · Zukunftsprognose
Indikator-Proximity-Analyse: welche Aktien nähern sich einem Setup (kein ML).
**Output:** „bald interessant"-Liste. **Hook:** Vorlauf-Pipeline / Watch-Kandidaten.

### 7 · Trade Management
Bewertet offene Positionen nach Stillhalter-Regeln; Import via CSV (IBKR Flex Query)
oder manuell.
**Output:** Handlungsempfehlungen für Bestand. **Hook:** Bestands-Überwachung.

### 8 · Trend Signale (STI)
Stillhalter Trend Indikator, Multi-Timeframe-Confluence: „NOW" (Cross gerade) vs.
„GET READY" (Cross steht bevor).
**Output:** Timing-Signale. **Hook:** Einstiegs-Timing für Research/Scanner.

### 9 · Investoren-Check
5 legendäre Hedge-Fund-Manager bewerten einen Trade nach ihren Prinzipien.
**Output:** qualitative Zweitmeinung. **Hook:** „Jury"-Bewertung im Research.

### 10 · Option-Olli Chat
KI-Coach für Plattform-/Strategiefragen (ohne proprietäre Indikator-Geheimnisse).
**Output:** Q&A. **Hook:** Member-Assistent auf Basis der Wissensbasis.

### 11 · Prozess
Visuelle Darstellung des App-Workflows (Daten → Entscheidung). Info-Seite.

### 12 · IBKR Integration (Guide)
Schritt-für-Schritt: Interactive Brokers via Flex Queries & TWS API anbinden.

### 13 · Rechtliches
Datenschutz, Haftungsausschluss, Impressum. Info-Seite.

### 14 · Order-Planung & IBKR-Freigabe
Orders werden in TWS als „Held" platziert (transmit=False); finale Freigabe in TWS
durch den Nutzer.
**Output:** vorbereitete Orders. **Hook:** Ausführungs-Stufe mit Mensch-Gate.

### 15 · Datenquellen
Übersicht & Test der Datenquellen (Yahoo Finance, Massive/Polygon), API-Status.
**Hook:** Health-Check der Daten-Agenten.

### 16 · Sentiment-Analyse (Social Arbitrage)
Virale Trends entdecken (Reddit, Google Trends, StockTwits, Product Hunt, HN) →
Produkte → Aktien mappen → Einpreisung bewerten.
**Output:** Trend-getriebene Kandidaten. **Hook:** alternativer Ideen-Strom.

### 17 · Trade Cards
Erzeugt fertige Community-Posts (Kurz-/Langversion) inkl. Auto-Fill der Optionsdaten,
OptionStrat-Links, Fundamental-/Chart-Indikatoren; Spracheingabe; Circle-Auto-Post.
**Output:** publikationsfertige Posts. **Hook:** Redaktions-Output.

### 18 · Markt-Newsletter
Täglicher Börsennewsletter: 11 Sektoren, Fundamentals, TA, Optionsempfehlung;
Quellen Yahoo RSS, yfinance News, MarketWatch, Fear & Greed.
**Output:** Newsletter-Entwurf. **Hook:** Redaktions-Output (täglich).

### 19 · Signal Pipeline & Freigabe-Gate
Workflow: Scan-Kandidaten bewerten → als Trade Card speichern → Status täglich prüfen
→ **Freigabe** → WhatsApp-Text + Circle-HTML-Vorschau → senden/posten.
**Output:** kontrollierter Veröffentlichungs-Flow. **Hook:** zentrales Mensch-Gate.

### 20 · Trade Monitor
Live-Ticker für gespeicherte Trades bis zum Verfall: Zeit-Balken, Kurs↔Strike-Skala,
Verfall-%, Handlungsempfehlung.
**Output:** laufende Überwachung. **Hook:** Monitoring-Agent + Alerts.

---

## Teil B — Agenten-Konzept (Paperclip)

Idee: Die App-Logik wird von KI-Agenten als **Pipeline mit Freigabe-Gates** gefahren.
Paperclip orchestriert sie über Tickets, Heartbeat-Scheduling und Budgets.

### Vorgeschlagene Agenten (Rollen)
1. **Daten-Agent** — morgens Daten ziehen (Prefetch), Quellen-Health prüfen
   (Seiten 15, app.py). Liefert „Daten frisch"-Signal.
2. **Scanner-Agent** — startet den Scan (Seite 4), erzeugt Top-9 (Seite 5).
   Trigger: nach Daten-Agent. Output: Kandidatenliste.
3. **Research-Agent** — bewertet jeden Kandidaten via Fundamental (2), Einzelanalyse
   (3), Trend/STI (8), Zukunftsprognose (6), Investoren-Check (9), Sentiment (16) →
   konsolidierte Empfehlung + Begründung.
4. **Redaktions-Agent** — baut aus Top-Kandidaten Trade Cards (17) und den
   Newsletter (18); legt sie als Entwürfe in die Signal Pipeline (19).
5. **Freigabe-Gate (Mensch = du)** — in der Signal Pipeline (19) gibst du frei
   („posten erst nach Bestätigung"). Paperclip-Approval-Ticket.
6. **Publishing-Agent** — postet nach Freigabe nach Circle / bereitet WhatsApp-Text
   (17/19). Output: veröffentlichte Posts + Tracking-Links.
7. **Monitor-Agent** — überwacht laufende Trades (20) + Bestand (7), erkennt
   „nah am Strike / im Geld / Verfall naht" und meldet Handlungsbedarf.
8. **Order-Agent (optional, mit Gate)** — bereitet Held-Orders in TWS vor (14/12);
   Ausführung gibst du in TWS frei.
9. **Wissens-Agent (Obsidian)** — schreibt jede Idee, jeden Trade und jede
   Entscheidung als Markdown-Notiz in den Vault (verlinkt Ticker, Strategie, Datum).
10. **Concierge/Chat-Agent** — Option-Olli (10) beantwortet Member-Fragen auf Basis
    der Wissensbasis.

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

### Freigabe-Gates (Mensch behält Kontrolle)
- **Posten** nur nach deiner Bestätigung (Signal Pipeline, Seite 19).
- **Orders** nur als „Held" in TWS; finale Auslösung durch dich (Seite 14).
- Paperclip-Budgets pro Agent verhindern Kostenausreißer.

### Technischer Enabler (empfohlener erster Schritt)
Kernlogik aus der Streamlit-UI in **aufrufbare Funktionen / einen schlanken API-Layer**
herauslösen (Scan, Research-Bewertung, Trade-Card-Generierung, Posting, Monitoring,
Obsidian-Export). Dann nutzen Streamlit-UI, Paperclip-Agenten, Cronjobs und der
Obsidian-Export dieselbe Logik — die App bleibt die „Schaltzentrale", Agenten
übernehmen die Routine.

### Datenflüsse / Speicher
- Scan-Ergebnisse, Trade Cards, Trade-Status liegen bereits persistent im Volume.
- Diese werden zentrale „Tabellen", auf die Agenten lesend/schreibend zugreifen.
- Obsidian erhält pro Idee/Trade eine Markdown-Notiz (Frontmatter: Ticker, Strategie,
  Strike, Verfall, Status, CRV, Datum) → verlinkbare Wissensbasis & Rückblick.
