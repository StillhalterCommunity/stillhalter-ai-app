"""Budgets je Gruppe setzen und mit den Ist-Ausgaben vergleichen."""

from datetime import date

import streamlit as st

import db
import ui

ui.page("Budgets", "🎯")
db.init_db()

st.title("🎯 Budgets")
st.caption("Ein Budget gilt ab dem gewählten Monat, bis du ein neues setzt. "
           "So musst du nicht jeden Monat alles neu eintragen.")

month = ui.month_select()
budgets = db.effective_budgets(month)
flows = db.month_flows(month)
spent_by_grp = flows.loc[flows["kind"] == "ausgabe"].groupby("grp")["amount"].sum().mul(-1)

# --- Budgets bearbeiten -----------------------------------------------------
with st.form("budget_form"):
    st.subheader(f"Budgets ab {ui.month_label(month)}")
    new_values = {}
    cols = st.columns(2)
    for i, grp in enumerate(db.GROUPS):
        current = float(budgets.loc[budgets["grp"] == grp, "amount"].sum())
        new_values[grp] = cols[i % 2].number_input(
            grp, min_value=0.0, value=current, step=50.0, format="%.2f"
        )
    if st.form_submit_button("Budgets speichern", type="primary"):
        for grp, amount in new_values.items():
            db.exec_sql(
                "INSERT INTO budgets(grp, month_from, amount) VALUES(?,?,?) "
                "ON CONFLICT(grp, month_from) DO UPDATE SET amount=excluded.amount",
                (grp, month, float(amount)),
            )
        st.success(f"Budgets ab {ui.month_label(month)} gespeichert.")
        st.rerun()

st.divider()

# --- Vergleich Budget vs. Ist ------------------------------------------------
st.subheader(f"Budget vs. Ist · {ui.month_label(month)}")
total_budget = total_spent = 0.0
for grp in db.GROUPS:
    budget = float(budgets.loc[budgets["grp"] == grp, "amount"].sum())
    spent = float(spent_by_grp.get(grp, 0.0))
    total_budget += budget
    total_spent += spent
    rest = budget - spent
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    c1.markdown(f"**{grp}**")
    c2.markdown(f"Budget: {ui.eur(budget)}")
    c3.markdown(f"Ist: {ui.eur(spent)}")
    c4.markdown(f"{'✅ ' + ui.eur(rest) + ' frei' if rest >= 0 else '⚠️ ' + ui.eur(-rest) + ' drüber'}")
    st.progress(min(spent / budget, 1.0) if budget > 0 else 0.0)

st.divider()
st.markdown(f"**Gesamt** — Budget: {ui.eur(total_budget)} · Ist: {ui.eur(total_spent)} · "
            f"{'frei: ' + ui.eur(total_budget - total_spent) if total_budget >= total_spent else 'überzogen: ' + ui.eur(total_spent - total_budget)}")
