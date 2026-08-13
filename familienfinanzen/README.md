# 💶 Familien-Finanzen

Gemeinsamer Finanztracker für die Familie: alle Konten, Kreditkarten, Darlehen,
Budgets und Ausgaben an einem Ort — nutzbar am Handy und im Browser, von
mehreren Personen gleichzeitig.

## Starten

```bash
# aus dem Repo-Root
streamlit run familienfinanzen/Dashboard.py
```

Die App legt beim ersten Start automatisch eine SQLite-Datenbank an
(`familienfinanzen/finanzen.db`, per Umgebungsvariable `FINANZEN_DB` verschiebbar —
für Railway z. B. auf ein persistentes Volume legen).

Optionaler Zugriffsschutz: Umgebungsvariable `FINANZEN_PIN` setzen, dann fragt
die App vor jeder Sitzung nach dem PIN.

## Was die App kann

- **Dashboard** — Einnahmen, Ausgaben, Saldo, Nettovermögen, Schulden auf einen
  Blick; Ausgaben nach Kategorie; 12-Monats-Verlauf.
- **Budgets** — feste Gruppen: Lebenshaltung, Spaß & Freizeit, Investment,
  Anschaffungen, Privat Sophia, Privat Ich, Philippa. Ein Budget gilt ab einem
  Monat weiter, bis ein neues gesetzt wird.
- **Transaktionen** — manuell erfassen (Ausgabe/Einnahme/Umbuchung), direkt in
  der Tabelle kategorisieren und Personen zuordnen.
- **Konten & Schulden** — Girokonten, Tagesgeld, Kreditkarten, Depots,
  Kinderdepot (Philippa), Bargeld, Darlehen und Immobiliendarlehen mit Zins,
  Rate und Restschuld.
- **Import & Banking** — CSV-Import für jede Bank (mit Duplikat-Erkennung) und
  automatische Synchronisation per PSD2-Bankanbindung (siehe unten).

## Zugang zu Echtzeit-Konten und Kreditkarten — die Optionen

Seit PSD2 müssen alle europäischen Banken eine Schnittstelle für
**Kontoinformationsdienste (AIS)** anbieten. Man greift aber nicht direkt zu,
sondern über einen lizenzierten Anbieter — oder importiert manuell:

| Option | Kosten | Aufwand | Abdeckung |
|---|---|---|---|
| **GoCardless Bank Account Data** (früher Nordigen) | kostenlos (bis 50 Verbindungen) | gering | ~2.300 EU-Banken, inkl. dt. Banken, Amex u. v. m. |
| finAPI, Tink, Salt Edge (kommerzielle Aggregatoren) | ab ~100 €/Monat | mittel | sehr breit, eher für kommerzielle Produkte |
| FinTS/HBCI direkt (z. B. `python-fints`) | kostenlos | hoch (TAN-Verfahren!) | nur deutsche Banken, keine Kreditkarten-Portale |
| CSV-Export + Import | kostenlos | manuell, ~5 Min/Monat | jedes Konto |

**Empfehlung:** CSV-Import sofort nutzen, parallel GoCardless einrichten.
GoCardless ist der lizenzierte PSD2-Dienstleister — eure Bank-Zugangsdaten
bleiben bei der Bank, ihr gebt den Zugriff einmalig im eigenen Online-Banking
frei (gilt je nach Bank 90–180 Tage, dann einmal neu bestätigen). Die App
speichert nur lesend die Umsätze.

Einrichtung: kostenlosen Account auf https://bankaccountdata.gocardless.com
anlegen, Secret ID/Key erzeugen und als Umgebungsvariablen setzen:

```bash
export GOCARDLESS_SECRET_ID=…
export GOCARDLESS_SECRET_KEY=…
```

Danach führt die Seite **Import & Banking** durch: Bank wählen → Freigabelink
der Bank durchklicken → Bankkonten den lokalen Konten zuordnen → synchronisieren.

## Deployment als eigener Service (Railway)

Eigenen Service mit Start-Kommando anlegen:

```
streamlit run familienfinanzen/Dashboard.py --server.port=$PORT --server.address=0.0.0.0
```

Wichtig: `FINANZEN_DB` auf ein persistentes Volume zeigen lassen (z. B.
`/data/finanzen.db`), sonst ist die Datenbank nach jedem Deploy leer.
`FINANZEN_PIN` setzen, wenn die App öffentlich erreichbar ist.
