# Projekt: Stillhalter AI App + Automatisierung mit Paperclip & Obsidian

> Kurzüberblick zum Weitergeben (z. B. an Claude Chat), um Automatisierungen zu planen.

Ich betreibe eine deutschsprachige Optionshandels-Community (Masterclass auf Circle)
und habe dafür eine Web-App gebaut: ein **Streamlit-Multipage-Dashboard** (Python) für
Stillhalter-/Optionsstrategien (Cash Secured Puts, Covered Calls, Short Strangles).

## Tech-Stack & Deployment
- Python / Streamlit, ~21 Seiten (Marktanalyse, Fundamental-/Aktienanalyse,
  Watchlist-Scanner, Top-9-Ideen, Trade Cards, Trade Monitor, Signal Pipeline u. a.)
- Deployment auf **Railway** (Auto-Deploy aus GitHub `main`), persistentes **Volume**
  für Caches (`STILLHALTER_DATA_DIR=/data`)
- Repo: `StillhalterCommunity/stillhalter-ai-app` · Live: `stillhalter-ai.up.railway.app`

## Datenquellen
- **Optionsdaten** (Bid/Ask, IV, Greeks): Massive/Polygon API (Plan deckt nur Optionen ab)
- **Aktien** (Kurse, Historie, Fundamentaldaten): yfinance
- Persistenter Disk-Cache + täglicher Morgen-Prefetch

## Kern-Workflows (heute teils manuell angestoßen)
1. **Watchlist-Scanner** sucht passende Optionen (Vorder-/Hintergrund) → Ergebnis wird
   persistent gespeichert → speist die „Top 9 Trading-Ideen".
2. **Trade Cards**: erzeugt fertige Community-Posts (Kurz-/Langversion) inkl. Auto-Fill
   der Optionsdaten, OptionStrat-Links, Fundamental-/Chart-Indikatoren;
   **Auto-Posting nach Circle** über API; Eingabe auch per Spracheingabe
   (Wispr Flow → vorausgefülltes Formular).
3. **Trade Monitor**: verfolgt laufende Trades visuell (Zeit-Balken, Kurs↔Strike-Skala,
   Handlungsempfehlung).

## Ziel: Automatisierung mit Paperclip (paperclip.ing)
Paperclip ist eine open-source, self-hosted Plattform zum **Orchestrieren von KI-Agenten**
(Org-Chart aus Agenten, Ticket-System mit Audit-Trail, Heartbeat-Scheduling, Budgets pro
Agent, Freigabe-Gates, modell-agnostisch, per Extensions erweiterbar).

Ich möchte meine Stillhalter-Prozesse als Agenten-Tasks abbilden, sodass die Kette
**Scan → Trade-Idee bewerten → Trade Card erzeugen → posten → Trade Monitor** weitgehend
automatisch läuft und ich nicht jedes Element manuell bedienen muss. Beispiele:
- **Scanner-Agent**: startet morgens den Scan und legt Top-Ideen ab.
- **Redaktions-Agent**: baut daraus Trade Cards und postet (nach Freigabe-Gate) nach Circle.
- **Monitor-Agent**: überwacht laufende Trades und meldet Handlungsbedarf.

## Zusätzlich: Obsidian-Anbindung
Trades, Ideen und Notizen sollen automatisch als Markdown-Notizen in Obsidian landen
(Wissensbasis, Verlinkung, Rückblick).

## Fragen an Claude
1. Wie binde ich die bestehende Streamlit/Python-App auf Railway an Paperclip an — als
   Extension, über REST/Webhooks oder indem ich die Kernlogik (Scan, Trade-Card-Generierung,
   Posting) aus der App in separate, agent-aufrufbare Funktionen/Services herauslöse?
2. Welche Architektur empfiehlst du, damit Paperclip-Agenten diese Schritte als Tickets
   mit Freigabe-Gates ausführen (z. B. „posten erst nach meiner Bestätigung")?
3. Wie exportiere ich Scan-Ergebnisse, Trade Cards und Trade-Status automatisiert als
   Markdown nach Obsidian (Datei-Sync, Git, oder lokale Vault-Anbindung)?

## Technischer Startpunkt (Notiz)
Sinnvoller erster Schritt für die Anbindung: die Kernlogik (Scan / Trade-Card / Posting)
als **eigenständige, aufrufbare Funktionen bzw. einen kleinen API-Layer** verfügbar machen,
unabhängig von der Streamlit-UI. Dann können Paperclip-Agenten, Cronjobs und ein
Obsidian-Export dieselben Funktionen nutzen.
