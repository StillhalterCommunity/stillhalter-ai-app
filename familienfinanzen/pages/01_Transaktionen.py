"""Transaktionen: erfassen, filtern, kategorisieren, löschen."""

from datetime import date

import pandas as pd
import streamlit as st

import db
import ui

ui.page("Transaktionen", "🧾")
db.init_db()

st.title("🧾 Transaktionen")

mem = db.members()
cats = db.categories()
acc = db.accounts()

if acc.empty:
    st.warning("Lege zuerst unter **Konten & Schulden** mindestens ein Konto an.")
    st.stop()

# --- Neue Buchung -----------------------------------------------------------
with st.expander("➕ Neue Buchung erfassen", expanded=False):
    art = st.radio("Art", ["Ausgabe", "Einnahme", "Umbuchung"], horizontal=True)
    with st.form("neue_buchung", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        tx_date = c1.date_input("Datum", value=date.today(), format="DD.MM.YYYY")
        betrag = c2.number_input("Betrag (€)", min_value=0.0, step=1.0, format="%.2f")
        default_member = st.session_state.get("member_name", mem["name"].iloc[0])
        member = c3.selectbox("Wer?", mem["name"].tolist(),
                              index=mem["name"].tolist().index(default_member)
                              if default_member in mem["name"].tolist() else 0)

        if art == "Umbuchung":
            c4, c5 = st.columns(2)
            von = c4.selectbox("Von Konto", acc["name"].tolist())
            nach = c5.selectbox("Nach Konto", acc["name"].tolist(), index=min(1, len(acc) - 1))
            payee, desc, kat = "", st.text_input("Notiz", ""), "Umbuchung"
            konto = von
        else:
            kind = "einnahme" if art == "Einnahme" else "ausgabe"
            c4, c5 = st.columns(2)
            konto = c4.selectbox("Konto", acc["name"].tolist())
            kat_opts = cats.loc[cats["kind"] == kind, "name"].tolist()
            kat = c5.selectbox("Kategorie", kat_opts)
            payee = st.text_input("Empfänger / Zahler", "")
            desc = st.text_input("Beschreibung", "")

        if st.form_submit_button("Speichern", type="primary") and betrag > 0:
            member_id = int(mem.loc[mem["name"] == member, "id"].iloc[0])
            cat_id = int(cats.loc[cats["name"] == kat, "id"].iloc[0])
            d = tx_date.strftime("%Y-%m-%d")
            if art == "Umbuchung":
                if von == nach:
                    st.error("Von- und Nach-Konto müssen unterschiedlich sein.")
                else:
                    for name, amt in ((von, -betrag), (nach, betrag)):
                        db.exec_sql(
                            "INSERT INTO transactions(account_id, date, amount, payee, description, category_id, member_id) "
                            "VALUES(?,?,?,?,?,?,?)",
                            (int(acc.loc[acc["name"] == name, "id"].iloc[0]), d, amt,
                             "", desc, cat_id, member_id),
                        )
                    st.success("Umbuchung gespeichert.")
                    st.rerun()
            else:
                amt = betrag if art == "Einnahme" else -betrag
                acc_id = int(acc.loc[acc["name"] == konto, "id"].iloc[0])
                db.exec_sql(
                    "INSERT INTO transactions(account_id, date, amount, payee, description, category_id, member_id) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (acc_id, d, amt, payee, desc, cat_id, member_id),
                )
                st.success(f"{art} über {ui.eur(betrag)} gespeichert.")
                st.rerun()

# --- Filter -----------------------------------------------------------------
st.subheader("Buchungen")
f1, f2, f3, f4 = st.columns(4)
month = f1.selectbox("Monat", ["Alle"] + ui.month_options(), format_func=lambda m: m if m == "Alle" else ui.month_label(m))
konto_f = f2.selectbox("Konto", ["Alle"] + acc["name"].tolist())
grp_f = f3.selectbox("Budget-Gruppe", ["Alle"] + sorted(cats["grp"].unique().tolist()))
nur_unkat = f4.checkbox("Nur ohne Kategorie")

sql = """
    SELECT t.id, t.date, t.amount, t.payee, t.description,
           c.name AS category, m.name AS member, a.name AS account, c.grp
    FROM transactions t
    LEFT JOIN categories c ON c.id = t.category_id
    LEFT JOIN members m ON m.id = t.member_id
    JOIN accounts a ON a.id = t.account_id
    WHERE 1=1
"""
params = []
if month != "Alle":
    sql += " AND substr(t.date,1,7)=?"
    params.append(month)
if konto_f != "Alle":
    sql += " AND a.name=?"
    params.append(konto_f)
if grp_f != "Alle":
    sql += " AND c.grp=?"
    params.append(grp_f)
if nur_unkat:
    sql += " AND t.category_id IS NULL"
sql += " ORDER BY t.date DESC, t.id DESC LIMIT 1000"

txs = db.q(sql, tuple(params))

if txs.empty:
    st.info("Keine Buchungen für diese Auswahl.")
    st.stop()

st.caption(f"{len(txs)} Buchungen · Summe: {ui.eur(float(txs['amount'].sum()))} — "
           "Kategorie und Person kannst du direkt in der Tabelle ändern.")

edit = txs.drop(columns=["grp"]).copy()
edited = st.data_editor(
    edit,
    hide_index=True,
    width="stretch",
    disabled=["id", "account"],
    column_config={
        "id": st.column_config.NumberColumn("ID", width="small"),
        "date": st.column_config.TextColumn("Datum"),
        "amount": st.column_config.NumberColumn("Betrag €", format="%.2f"),
        "payee": st.column_config.TextColumn("Empfänger/Zahler"),
        "description": st.column_config.TextColumn("Beschreibung"),
        "category": st.column_config.SelectboxColumn("Kategorie", options=cats["name"].tolist()),
        "member": st.column_config.SelectboxColumn("Person", options=mem["name"].tolist()),
        "account": st.column_config.TextColumn("Konto"),
    },
    key="tx_editor",
)

col_a, col_b = st.columns([1, 2])
if col_a.button("Änderungen speichern", type="primary"):
    cat_by_name = dict(zip(cats["name"], cats["id"]))
    mem_by_name = dict(zip(mem["name"], mem["id"]))
    changed = 0
    orig = edit.set_index("id")
    for _, row in edited.iterrows():
        o = orig.loc[row["id"]]
        if (row[["date", "amount", "payee", "description", "category", "member"]]
                .fillna("").astype(str).tolist()
                != o[["date", "amount", "payee", "description", "category", "member"]]
                .fillna("").astype(str).tolist()):
            db.exec_sql(
                "UPDATE transactions SET date=?, amount=?, payee=?, description=?, category_id=?, member_id=? WHERE id=?",
                (str(row["date"]), float(row["amount"]), row["payee"] or "", row["description"] or "",
                 cat_by_name.get(row["category"]), mem_by_name.get(row["member"]), int(row["id"])),
            )
            changed += 1
    st.success(f"{changed} Buchung(en) aktualisiert.")
    st.rerun()

with col_b.expander("Buchungen löschen"):
    ids = st.multiselect("IDs auswählen", txs["id"].tolist())
    if st.button("Ausgewählte endgültig löschen") and ids:
        for i in ids:
            db.exec_sql("DELETE FROM transactions WHERE id=?", (int(i),))
        st.success(f"{len(ids)} Buchung(en) gelöscht.")
        st.rerun()
