"""Umsätze importieren: per CSV-Export der Bank oder automatisch per PSD2-Bankanbindung."""

from datetime import date, timedelta

import streamlit as st

import bank_sync
import csv_import
import db
import ui

ui.page("Import & Banking", "🔄")
db.init_db()

st.title("🔄 Import & Banking")

acc = db.accounts()
tab_csv, tab_bank = st.tabs(["📄 CSV-Import", "🏦 Bankanbindung (automatisch)"])

# ============================ CSV-Import ====================================
with tab_csv:
    st.caption("Funktioniert mit jedem Konto: CSV-Export im Online-Banking herunterladen "
               "und hier hochladen. Doppelte Buchungen werden automatisch übersprungen — "
               "du kannst also bedenkenlos überlappende Zeiträume importieren.")
    if acc.empty:
        st.warning("Lege zuerst unter **Konten & Schulden** ein Konto an.")
    else:
        konto = st.selectbox("Ziel-Konto", acc["name"].tolist())
        upload = st.file_uploader("CSV-Datei", type=["csv", "txt"])
        if upload is not None:
            try:
                raw_df = csv_import.read_bank_csv(upload.getvalue())
            except ValueError as e:
                st.error(str(e))
                st.stop()
            st.dataframe(raw_df.head(5), width="stretch")
            cols = raw_df.columns.tolist()

            def guess(candidates, default=0):
                for i, c in enumerate(cols):
                    if any(k in c.lower() for k in candidates):
                        return i
                return default

            c1, c2, c3, c4 = st.columns(4)
            col_date = c1.selectbox("Spalte: Datum", cols, index=guess(["buchung", "datum", "date"]))
            col_amount = c2.selectbox("Spalte: Betrag", cols, index=guess(["betrag", "amount", "umsatz"]))
            col_payee = c3.selectbox("Spalte: Empfänger", ["(keine)"] + cols,
                                     index=1 + guess(["empfänger", "beguenstigter", "begünstigter", "auftraggeber", "name"], -1)
                                     if guess(["empfänger", "beguenstigter", "begünstigter", "auftraggeber", "name"], -1) >= 0 else 0)
            col_desc = c4.selectbox("Spalte: Verwendungszweck", ["(keine)"] + cols,
                                    index=1 + guess(["verwendung", "zweck", "beschreibung", "text"], -1)
                                    if guess(["verwendung", "zweck", "beschreibung", "text"], -1) >= 0 else 0)

            norm = csv_import.normalize(
                raw_df, col_date, col_amount,
                None if col_payee == "(keine)" else col_payee,
                None if col_desc == "(keine)" else col_desc,
            )
            if norm.empty:
                st.error("Keine gültigen Zeilen erkannt — stimmen Datums- und Betragsspalte?")
            else:
                st.success(f"{len(norm)} Buchungen erkannt · Summe {ui.eur(float(norm['amount'].sum()))}")
                st.dataframe(norm.head(10), width="stretch")
                if st.button("Importieren", type="primary"):
                    acc_id = int(acc.loc[acc["name"] == konto, "id"].iloc[0])
                    rows = [
                        (acc_id, r["date"], r["amount"], r["payee"], r["description"],
                         db.import_hash(acc_id, r["date"], r["amount"], r["payee"], r["description"]))
                        for _, r in norm.iterrows()
                    ]
                    n = db.exec_many(
                        "INSERT OR IGNORE INTO transactions(account_id, date, amount, payee, description, import_hash) "
                        "VALUES(?,?,?,?,?,?)", rows,
                    )
                    st.success(f"{n} neue Buchungen importiert ({len(rows) - n} Duplikate übersprungen). "
                               "Jetzt auf der Seite **Transaktionen** kategorisieren.")

# ========================= Bankanbindung (PSD2) ==============================
with tab_bank:
    st.markdown(
        "Automatischer Abruf über **GoCardless Bank Account Data** (PSD2-Kontoinformationsdienst, "
        "für Privatnutzung kostenlos, ~2.300 europäische Banken). Eure Bank-Zugangsdaten "
        "bleiben bei der Bank — ihr bestätigt den Zugriff einmalig direkt im Online-Banking, "
        "die Freigabe gilt je nach Bank 90–180 Tage."
    )
    if not bank_sync.credentials_present():
        st.info(
            "**Einrichtung (einmalig, ca. 10 Minuten):**\n\n"
            "1. Kostenlosen Account anlegen: https://bankaccountdata.gocardless.com\n"
            "2. Dort unter *Developers → User secrets* eine Secret ID + Secret Key erzeugen\n"
            "3. Beide als Umgebungsvariablen setzen (lokal oder im Railway-Service):\n"
            "   `GOCARDLESS_SECRET_ID` und `GOCARDLESS_SECRET_KEY`\n"
            "4. App neu starten — dann erscheint hier der Verbindungsassistent.\n\n"
            "Bis dahin funktioniert der CSV-Import mit allen Konten."
        )
        st.stop()

    client = bank_sync.GoCardlessClient()

    st.subheader("1) Bank verbinden")
    @st.cache_data(ttl=3600, show_spinner="Lade Bankenliste …")
    def _institutions():
        return client.institutions("de")

    try:
        inst = _institutions()
    except Exception as e:
        st.error(f"Bankenliste konnte nicht geladen werden: {e}")
        st.stop()

    names = {i["name"]: i["id"] for i in inst}
    bank_name = st.selectbox("Bank auswählen", sorted(names.keys()))
    redirect = st.text_input("Redirect-URL (URL dieser App)", "http://localhost:8501")
    if st.button("Verbindung starten"):
        try:
            req = client.create_requisition(names[bank_name], redirect,
                                            reference=f"famfin-{date.today().isoformat()}-{bank_name[:20]}")
            db.exec_sql(
                "INSERT OR IGNORE INTO bank_links(requisition_id, institution, created_at) VALUES(?,?,?)",
                (req["id"], bank_name, date.today().isoformat()),
            )
            st.success("Verbindung angelegt. Jetzt bei der Bank freigeben:")
            st.markdown(f"### 👉 [Bei {bank_name} anmelden und Zugriff freigeben]({req['link']})")
            st.caption("Danach hierher zurückkommen und unten die Konten abrufen.")
        except Exception as e:
            st.error(f"Fehler beim Anlegen der Verbindung: {e}")

    st.divider()
    st.subheader("2) Konten zuordnen")
    links = db.q("SELECT * FROM bank_links ORDER BY id DESC")
    if links.empty:
        st.caption("Noch keine Bankverbindung angelegt.")
    else:
        link_label = st.selectbox(
            "Bankverbindung", links["institution"] + " · " + links["created_at"] + " · " + links["requisition_id"]
        )
        req_id = link_label.rsplit(" · ", 1)[1]
        try:
            req = client.requisition(req_id)
            bank_accounts = req.get("accounts", [])
            if not bank_accounts:
                st.warning(f"Noch keine Konten freigegeben (Status: {req.get('status')}). "
                           "Erst den Freigabe-Link der Bank abschließen.")
            for ba in bank_accounts:
                det = client.account_details(ba)
                label = f"{det.get('name') or det.get('product') or 'Konto'} · {det.get('iban', ba)}"
                c1, c2 = st.columns([2, 2])
                c1.markdown(f"**{label}**")
                options = ["(nicht zuordnen)"] + acc["name"].tolist()
                current = acc.loc[acc["gocardless_id"] == ba, "name"]
                idx = options.index(current.iloc[0]) if not current.empty else 0
                target = c2.selectbox("Lokales Konto", options, index=idx, key=f"map_{ba}")
                if target != "(nicht zuordnen)":
                    tid = int(acc.loc[acc["name"] == target, "id"].iloc[0])
                    db.exec_sql("UPDATE accounts SET gocardless_id=? WHERE id=?", (ba, tid))
        except Exception as e:
            st.error(f"Konnte Verbindung nicht abrufen: {e}")

    st.divider()
    st.subheader("3) Umsätze synchronisieren")
    linked = acc.loc[acc["gocardless_id"].notna()]
    if linked.empty:
        st.caption("Noch kein lokales Konto mit einem Bankkonto verknüpft.")
    else:
        days = st.slider("Zeitraum (Tage rückwirkend)", 7, 730, 90)
        if st.button("Jetzt synchronisieren", type="primary"):
            since = (date.today() - timedelta(days=days)).isoformat()
            total_new = 0
            for _, row in linked.iterrows():
                try:
                    txs = client.transactions(row["gocardless_id"], date_from=since)
                except Exception as e:
                    st.error(f"{row['name']}: {e}")
                    continue
                rows = [
                    (int(row["id"]), t["date"], t["amount"], t["payee"], t["description"],
                     db.import_hash(int(row["id"]), t["date"], t["amount"], t["payee"], t["description"]))
                    for t in txs if t["date"]
                ]
                n = db.exec_many(
                    "INSERT OR IGNORE INTO transactions(account_id, date, amount, payee, description, import_hash) "
                    "VALUES(?,?,?,?,?,?)", rows,
                )
                total_new += n
                st.write(f"✅ {row['name']}: {n} neue Buchungen ({len(rows)} abgerufen)")
            st.success(f"Fertig — {total_new} neue Buchungen. Jetzt unter **Transaktionen** kategorisieren.")
