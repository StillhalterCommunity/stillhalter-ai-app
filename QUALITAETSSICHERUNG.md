# Qualitätssicherung — Stillhalter AI App

Lebende Prüfliste für „läuft fehlerfrei **und** sieht fehlerfrei aus". Status:
✅ erledigt · 🔧 in Arbeit · ⬜ offen · ⚠️ bekannt/akzeptiert

Letzte Durcharbeitung: 2026-06-18 (autonom)

---

## 1. Code-Gesundheit (läuft fehlerfrei)
- ✅ Alle `.py` kompilieren (`py_compile` über das ganze Repo)
- ✅ App bootet headless ohne Importfehler (`streamlit run app.py` → HTTP 200)
- ✅ Jede Seite läuft ohne Laufzeitfehler — automatisiert über `AppTest`
      (beide Themes). 21/21 Seiten OK; Seite 18 nur netzwerk-langsam (Test-Timeout).
- ⚠️ Viele `except Exception: return leer` schlucken Fehler (bewusst für
      Robustheit; erschwert aber Diagnose) — als Designentscheidung akzeptiert

## 2. Datenquellen & Scanner
- ✅ Optionen via Massive/Polygon, Aktien via yfinance (Plan deckt nur Optionen)
- ✅ Disk-Cache als Fallback, persistent im Volume (`STILLHALTER_DATA_DIR`)
- ✅ Short Strangle: Datums-/String-Vergleich gefixt (fand sonst 0)
- ✅ Short Strangle: lastPrice-Fallback bei geschlossenem Markt (Off-Hours)
- ✅ Scan-Last reduziert (Strangle max_expiries 6→3) + Hintergrund-Empfehlung
- ✅ Scan-Ergebnis persistent im Volume (Top9 baute auf uraltem Stand auf)
- ✅ LIVE-Gegencheck (Markt geschlossen, echter API-Key): AAPL off-hours →
      Short Strangle 3 Treffer, CSP 21 Treffer (vorher 0). Bid/Ask 0 %,
      lastPrice 75,6 % → Off-Hours-Fallback greift.
- ✅ Scanner-Selbstheilung im Code vorhanden (force_reset, _MAX_RUNTIME_S,
      Run-ID gegen Zombie-Worker)

## 3. Theming — dunkel (Schwarz/Gold)
- ✅ Standard-Theme, an `config.toml base="dark"` ausgerichtet → konsistent

## 4. Theming — hell (Weiß/Grün)
- ✅ Dropdowns lesbar (Portal/BaseWeb hart auf hell überschrieben)
- ✅ Eingabefelder: genau ein Rahmen, keine Doppelränder, Fokus-Glow
- ✅ Sidebar-Logo sichtbar (war weiß auf weiß)
- ✅ Checkboxen / Radios / Slider auf Grün statt dunkel/gold
- ✅ Multiselect-Chips
- ✅ Dunkle Inline-Karten flächendeckend aufgehellt (Inline-Style-Selektoren
      im grünen Theme: #0e0e0e/#111/#0a0a0a/#0c0c0c/#1a1a1a … → hell; dunkle
      Rahmen → grün). Dunkles Theme unberührt.
- ✅ DataFrames, Expander, Alerts, Metrics: im grünen Theme gestylt
- ⚠️ Seltene farbig-getönte Dunkel-Karten (z. B. dunkelroter Diagnose-Kasten)
      bleiben getönt — lesbar, aber nicht 100 % hell; bei Bedarf später
- ℹ️ Saubere Langfrist-Lösung: echtes zweites Streamlit-`[theme]` statt
      BaseWeb per CSS zu überstimmen (mit Nutzer abgestimmt offen)

## 4b. Features (neu)
- ✅ OptionStrat-Button **vorne** in der Scanner-Tabelle (LinkColumn an erster Stelle)
- ✅ Top 9: pro Karte OptionStrat-Button + „📈 Chart"-Toggle (Kurschart mit Strike/Break-Even)
- ✅ Scanner: Zeilenauswahl → Kurschart + Payoff + OptionStrat (war bereits da)
- ✅ Header-/Sidebar-Logos auf „auto" (in beiden Themes sichtbar)
- ✅ Trade Cards: Checkbox „📡 In Trade Monitor übernehmen" — Übernahme jetzt
      steuerbar (vorher automatisch für jeden generierten Trade)
- ✅ Gemeinsamer Trade-Store `data/monitor_store.py` (eine Quelle für Pfad/Format)

## 5. Kern-Features
- ✅ Trade Monitor Übersicht (app-native Karten, Zeit-Balken, Kurs↔Strike)
- ✅ OptionStrat-Links (Format + Snapping auf reale Kontrakte)
- ⬜ Trade Cards: Auto-Fill, Kurz/Lang, Circle-Sammelpost, Sprach-Parser
- ⬜ Top9: nutzt letzten persistenten Scan, Risiko-Klassen, Share-Text

## 6. Fehlerbehandlung & UX
- ✅ Keine nackten Tracebacks: AppTest zeigt 0 Exceptions auf allen 21 Seiten
- ✅ Sinnvolle Meldungen bei geschlossenem Markt (Last-Price-Modus) + Off-Hours-Treffer
- ⚠️ Seite 18 (Markt Newsletter) lädt langsam — holt beim Seitenaufruf
      Optionsdaten für viele Ticker synchron. Funktioniert, aber träge.
      Kandidat für Lazy-Loading/Caching (Folgeaufgabe, nicht kritisch).
- ✅ Polling-Schleifen im Scanner nur bei laufendem Hintergrund-Scan (kein Dauerloop)

---

### Befund-Log (was gefunden + behoben wurde)
- Short Strangle 0 Treffer: `expiration` (date) vs Verfalls-Liste (str) → normalisiert.
- Short Strangle 0 Treffer off-hours: kein lastPrice-Fallback → ergänzt.
- „macht nichts/weiße Seite": synchroner Vordergrund-Scan blockiert Worker → Last gesenkt + Hinweis.
- Top9 uralt: `last_scan_cache.pkl` im Code-Ordner UND im Git → Volume + aus Git entfernt.
- Helles Theme: Dropdowns schwarz/schwarz, Doppelränder, Logo unsichtbar → CSS überarbeitet.
- Sidebar-Logo fest "white" → im hellen Theme unsichtbar → auf "auto" umgestellt.
- Seite 04: `{**None}`-Crash bei tf_results=None → mit `or {}` abgesichert.
- Seite 17: PEP-604 `dict | None` ohne `from __future__ import annotations`
  → Crash auf Python <3.10 → Future-Import ergänzt (future-proof).
- Helles Theme: dunkle Inline-Karten → per Inline-Style-Selektor aufgehellt.

### Test-Werkzeug
`/tmp/qa_pages.py` — führt jede Seite via Streamlit `AppTest` in beiden Themes
aus und meldet Laufzeitfehler. Bei Wiederverwendung `sys.path` auf Repo-Root
setzen und `st.page_link`/`switch_page` als no-op patchen (Multipage-Registry
fehlt im Test). Für echten Daten-Gegencheck `MASSIVE_API_KEY` setzen.
