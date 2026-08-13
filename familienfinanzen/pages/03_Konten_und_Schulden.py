"""Konten, Kreditkarten, Depots und Darlehen verwalten."""

import streamlit as st

import db
import ui

ui.page("Konten & Schulden", "🏦")
db.init_db()

st.title("🏦 Konten & Schulden")

mem = db.members()
acc = db.accounts(include_inactive=True)

# --- Neues Konto -------------------------------------------------------------
with st.expander("➕ Konto / Kreditkarte / Darlehen anlegen"):
    with st.form("neues_konto", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Name (z. B. 'DKB Giro', 'Amex Gold', 'Darlehen ETW Leipzig')")
        typ = c2.selectbox("Art", list(db.ACCOUNT_TYPES.keys()),
                           format_func=lambda t: db.ACCOUNT_TYPES[t])
        owner = c3.selectbox("Gehört", ["Familie"] + mem["name"].tolist())
        c4, c5 = st.columns(2)
        iban = c4.text_input("IBAN / Kartennummer (optional)")
        start = c5.number_input("Aktueller Stand (€) — bei Schulden negativ, z. B. -250000",
                                step=100.0, format="%.2f")
        st.markdown("**Nur für Darlehen / Kreditkarten:**")
        c6, c7, c8 = st.columns(3)
        zins = c6.number_input("Zins % p.a.", min_value=0.0, step=0.1, format="%.2f")
        rate = c7.number_input("Monatliche Rate (€)", min_value=0.0, step=50.0, format="%.2f")
        note = c8.text_input("Notiz (z. B. Objekt, Bank, Laufzeit)")
        if st.form_submit_button("Anlegen", type="primary") and name:
            owner_id = None if owner == "Familie" else int(mem.loc[mem["name"] == owner, "id"].iloc[0])
            db.exec_sql(
                "INSERT INTO accounts(name, type, owner_id, iban, start_balance, interest_rate, monthly_payment, note) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (name, typ, owner_id, iban, start, zins or None, rate or None, note),
            )
            st.success(f"Konto »{name}« angelegt.")
            st.rerun()

if acc.empty:
    st.info("Noch keine Konten angelegt. Tipp: Beginne mit euren Girokonten, Kreditkarten "
            "und den Immobiliendarlehen — der 'aktuelle Stand' ist der Startpunkt, "
            "ab dann führen Buchungen den Saldo fort.")
    st.stop()

# --- Übersicht ---------------------------------------------------------------
st.subheader("Vermögen")
assets = acc.loc[~acc["type"].isin(db.DEBT_TYPES) & (acc["active"] == 1)]
debts = acc.loc[acc["type"].isin(db.DEBT_TYPES) & (acc["active"] == 1)]

c1, c2, c3 = st.columns(3)
c1.metric("Guthaben & Depots", ui.eur(float(assets["balance"].sum())))
c2.metric("Schulden", ui.eur(float(-debts["balance"].clip(upper=0).sum())))
c3.metric("Nettovermögen", ui.eur(float(acc.loc[acc['active'] == 1, 'balance'].sum())))

show = acc.loc[acc["active"] == 1, ["id", "name", "type", "owner", "iban", "balance",
                                    "interest_rate", "monthly_payment", "note"]].copy()
show["type"] = show["type"].map(db.ACCOUNT_TYPES)
show = show.rename(columns={"id": "ID", "name": "Konto", "type": "Art", "owner": "Gehört",
                            "iban": "IBAN", "balance": "Saldo",
                            "interest_rate": "Zins %", "monthly_payment": "Rate €", "note": "Notiz"})
show["Gehört"] = show["Gehört"].fillna("Familie")
st.dataframe(
    show, width="stretch", hide_index=True,
    column_config={
        "Saldo": st.column_config.NumberColumn(format="%.2f €"),
        "Rate €": st.column_config.NumberColumn(format="%.2f €"),
        "Zins %": st.column_config.NumberColumn(format="%.2f %%"),
    },
)

# --- Bearbeiten / Deaktivieren -------------------------------------------------
with st.expander("✏️ Konto bearbeiten oder deaktivieren"):
    sel = st.selectbox("Konto wählen", acc["name"] + " (ID " + acc["id"].astype(str) + ")")
    sel_id = int(sel.rsplit("(ID ", 1)[1].rstrip(")"))
    row = acc.loc[acc["id"] == sel_id].iloc[0]
    with st.form("konto_edit"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Name", row["name"])
        start = c2.number_input("Startsaldo (€)", value=float(row["start_balance"]),
                                step=100.0, format="%.2f")
        c3, c4, c5 = st.columns(3)
        zins = c3.number_input("Zins % p.a.", value=float(row["interest_rate"] or 0), step=0.1, format="%.2f")
        rate = c4.number_input("Rate €/Monat", value=float(row["monthly_payment"] or 0), step=50.0, format="%.2f")
        note = c5.text_input("Notiz", row["note"] or "")
        aktiv = st.checkbox("Aktiv", value=bool(row["active"]))
        if st.form_submit_button("Speichern", type="primary"):
            db.exec_sql(
                "UPDATE accounts SET name=?, start_balance=?, interest_rate=?, monthly_payment=?, note=?, active=? WHERE id=?",
                (name, start, zins or None, rate or None, note, int(aktiv), sel_id),
            )
            st.success("Gespeichert.")
            st.rerun()

# --- Familienmitglieder --------------------------------------------------------
with st.expander("👨‍👩‍👧 Familienmitglieder verwalten"):
    st.dataframe(mem[["id", "name"]].rename(columns={"id": "ID", "name": "Name"}),
                 hide_index=True)
    c1, c2 = st.columns(2)
    with c1:
        neu = st.text_input("Neues Mitglied")
        if st.button("Hinzufügen") and neu:
            db.exec_sql("INSERT OR IGNORE INTO members(name) VALUES(?)", (neu,))
            st.rerun()
    with c2:
        alt = st.selectbox("Umbenennen", mem["name"].tolist())
        neu_name = st.text_input("Neuer Name", key="rename_input")
        if st.button("Umbenennen", key="rename_btn") and neu_name:
            db.exec_sql("UPDATE members SET name=? WHERE name=?", (neu_name, alt))
            st.rerun()
