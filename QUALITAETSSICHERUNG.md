# Qualitätssicherung — Stillhalter AI App

Lebende Prüfliste für „läuft fehlerfrei **und** sieht fehlerfrei aus". Status:
✅ erledigt · 🔧 in Arbeit · ⬜ offen · ⚠️ bekannt/akzeptiert

Letzte Durcharbeitung: 2026-06-18 (autonom)

---

## 1. Code-Gesundheit (läuft fehlerfrei)
- ✅ Alle `.py` kompilieren (`py_compile` über das ganze Repo)
- ✅ App bootet headless ohne Importfehler (`streamlit run app.py` → HTTP 200)
- 🔧 Jede Seite läuft ohne Laufzeitfehler — automatisiert über `AppTest`
      (beide Themes), siehe `/tmp/qa_pages.py`
- ⬜ Keine bare `except:`-Stellen, die Fehler verschlucken und Diagnose verhindern

## 2. Datenquellen & Scanner
- ✅ Optionen via Massive/Polygon, Aktien via yfinance (Plan deckt nur Optionen)
- ✅ Disk-Cache als Fallback, persistent im Volume (`STILLHALTER_DATA_DIR`)
- ✅ Short Strangle: Datums-/String-Vergleich gefixt (fand sonst 0)
- ✅ Short Strangle: lastPrice-Fallback bei geschlossenem Markt (Off-Hours)
- ✅ Scan-Last reduziert (Strangle max_expiries 6→3) + Hintergrund-Empfehlung
- ✅ Scan-Ergebnis persistent im Volume (Top9 baute auf uraltem Stand auf)
- ⬜ CSP / Covered Call / Strangle je ein echter Treffer-Gegencheck (Markt offen)
- ⬜ Scanner-Selbstheilung (Zombie nach Abbruch/Neustart) erneut verifizieren

## 3. Theming — dunkel (Schwarz/Gold)
- ✅ Standard-Theme, an `config.toml base="dark"` ausgerichtet → konsistent

## 4. Theming — hell (Weiß/Grün)
- ✅ Dropdowns lesbar (Portal/BaseWeb hart auf hell überschrieben)
- ✅ Eingabefelder: genau ein Rahmen, keine Doppelränder, Fokus-Glow
- ✅ Sidebar-Logo sichtbar (war weiß auf weiß)
- ✅ Checkboxen / Radios / Slider auf Grün statt dunkel/gold
- ✅ Multiselect-Chips
- 🔧 Seiten-HTML mit hartcodierten Dunkel-Farben (dunkle Karten auf weißem
      Grund / unsichtbarer Text) — Seiten theme-bewusst machen
- ⬜ DataFrames, Expander, Alerts, Metrics, Captions, Code-Blöcke quergeprüft

## 5. Kern-Features
- ✅ Trade Monitor Übersicht (app-native Karten, Zeit-Balken, Kurs↔Strike)
- ✅ OptionStrat-Links (Format + Snapping auf reale Kontrakte)
- ⬜ Trade Cards: Auto-Fill, Kurz/Lang, Circle-Sammelpost, Sprach-Parser
- ⬜ Top9: nutzt letzten persistenten Scan, Risiko-Klassen, Share-Text

## 6. Fehlerbehandlung & UX
- ⬜ Keine nackten Tracebacks für Endnutzer
- ⬜ Sinnvolle Meldungen bei fehlenden Daten / geschlossenem Markt
- ⬜ Keine endlosen Rerun-/Polling-Schleifen

---

### Befund-Log (was gefunden + behoben wurde)
- Short Strangle 0 Treffer: `expiration` (date) vs Verfalls-Liste (str) → normalisiert.
- Short Strangle 0 Treffer off-hours: kein lastPrice-Fallback → ergänzt.
- „macht nichts/weiße Seite": synchroner Vordergrund-Scan blockiert Worker → Last gesenkt + Hinweis.
- Top9 uralt: `last_scan_cache.pkl` im Code-Ordner UND im Git → Volume + aus Git entfernt.
- Helles Theme: Dropdowns schwarz/schwarz, Doppelränder, Logo unsichtbar → CSS überarbeitet.
