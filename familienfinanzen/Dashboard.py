"""Familien-Finanzen — Dashboard.

Start:  streamlit run familienfinanzen/Dashboard.py
"""

import plotly.graph_objects as go
import streamlit as st

import db
import ui

ui.page("Dashboard", "🏠")
db.init_db()

# --- Sidebar --------------------------------------------------------------
st.sidebar.title("💶 Familien-Finanzen")
month = ui.month_select(sidebar=True)

mem = db.members()
who = st.sidebar.selectbox("Wer bist du?", mem["name"].tolist(),
                           key="member_name",
                           help="Wird bei neuen Buchungen vorbelegt.")
st.sidebar.caption("Gleichzeitige Nutzung ist okay — alle Daten landen in derselben Datenbank.")

# --- Daten ----------------------------------------------------------------
flows = db.month_flows(month)
acc = db.accounts()
budgets = db.effective_budgets(month)

einnahmen = float(flows.loc[flows["kind"] == "einnahme", "amount"].sum())
ausgaben = float(-flows.loc[flows["kind"] == "ausgabe", "amount"].sum())
saldo = einnahmen - ausgaben
vermoegen = float(acc["balance"].sum()) if not acc.empty else 0.0
schulden = float(-acc.loc[acc["type"].isin(db.DEBT_TYPES), "balance"].clip(upper=0).sum()) if not acc.empty else 0.0
unkategorisiert = int(flows["category_id"].isna().sum())

st.title(f"Übersicht · {ui.month_label(month)}")

c1, c2, c3 = st.columns(3)
c1.metric("Einnahmen", ui.eur(einnahmen))
c2.metric("Ausgaben", ui.eur(ausgaben))
c3.metric("Saldo", ui.eur(saldo), delta=ui.eur(saldo) if saldo else None)
c4, c5, _ = st.columns(3)
c4.metric("Nettovermögen", ui.eur(vermoegen))
c5.metric("Schulden gesamt", ui.eur(schulden))

if unkategorisiert:
    st.warning(f"{unkategorisiert} Buchung(en) in diesem Monat sind noch ohne Kategorie "
               f"— auf der Seite **Transaktionen** zuordnen, damit die Auswertung stimmt.")

st.divider()

# --- Budgets --------------------------------------------------------------
st.subheader("Budgets")
spent_by_grp = (
    flows.loc[flows["kind"] == "ausgabe"]
    .groupby("grp")["amount"].sum().mul(-1)
)
bcols = st.columns(2)
for i, grp in enumerate(db.GROUPS):
    budget = float(budgets.loc[budgets["grp"] == grp, "amount"].sum())
    spent = float(spent_by_grp.get(grp, 0.0))
    with bcols[i % 2]:
        rest = budget - spent
        if budget > 0:
            pct = min(spent / budget, 1.0)
            st.markdown(f"**{grp}** — {ui.eur(spent)} von {ui.eur(budget)} "
                        f"({'noch ' + ui.eur(rest) + ' frei' if rest >= 0 else ui.eur(-rest) + ' drüber ⚠️'})")
            st.progress(pct)
        else:
            st.markdown(f"**{grp}** — {ui.eur(spent)} ausgegeben *(kein Budget gesetzt)*")
            st.progress(0.0)

st.caption("Budgets setzt und änderst du auf der Seite **Budgets**.")
st.divider()

# --- Charts ---------------------------------------------------------------
left, right = st.columns(2)

with left:
    st.subheader("Wofür geben wir Geld aus?")
    by_cat = (
        flows.loc[flows["kind"] == "ausgabe"]
        .groupby("category")["amount"].sum().mul(-1)
        .sort_values(ascending=True)
    )
    if by_cat.empty:
        st.info("Noch keine Ausgaben in diesem Monat erfasst.")
    else:
        fig = go.Figure(
            go.Bar(
                x=by_cat.values, y=by_cat.index, orientation="h",
                marker=dict(color=ui.COL_AUSGABEN, cornerradius=4),
                hovertemplate="%{y}: %{x:,.2f} €<extra></extra>",
            )
        )
        fig.update_layout(height=max(280, 28 * len(by_cat)), separators=",.",
                          xaxis_title="Ausgaben (€)")
        st.plotly_chart(ui.plotly_defaults(fig), width="stretch")

with right:
    st.subheader("Verlauf: Einnahmen vs. Ausgaben")
    hist = db.q(
        """
        SELECT substr(t.date,1,7) AS mon,
               SUM(CASE WHEN c.kind='einnahme' THEN t.amount ELSE 0 END) AS einnahmen,
               SUM(CASE WHEN c.kind='ausgabe' THEN -t.amount ELSE 0 END) AS ausgaben
        FROM transactions t LEFT JOIN categories c ON c.id = t.category_id
        GROUP BY mon ORDER BY mon DESC LIMIT 12
        """
    ).sort_values("mon")
    if hist.empty:
        st.info("Noch keine Daten für den Verlauf.")
    else:
        fig = go.Figure()
        fig.add_bar(x=hist["mon"], y=hist["einnahmen"], name="Einnahmen",
                    marker=dict(color=ui.COL_EINNAHMEN, cornerradius=4),
                    hovertemplate="%{x} · Einnahmen: %{y:,.2f} €<extra></extra>")
        fig.add_bar(x=hist["mon"], y=hist["ausgaben"], name="Ausgaben",
                    marker=dict(color=ui.COL_AUSGABEN, cornerradius=4),
                    hovertemplate="%{x} · Ausgaben: %{y:,.2f} €<extra></extra>")
        fig.update_layout(barmode="group", height=380, separators=",.",
                          yaxis_title="€ pro Monat")
        st.plotly_chart(ui.plotly_defaults(fig), width="stretch")

st.divider()

# --- Schulden -------------------------------------------------------------
st.subheader("Schulden & Darlehen")
debts = acc.loc[acc["type"].isin(db.DEBT_TYPES) & (acc["balance"] < 0)].copy() if not acc.empty else acc
if debts is None or debts.empty:
    st.info("Keine Schulden erfasst — Kreditkarten und Darlehen legst du unter **Konten & Schulden** an.")
else:
    debts["Restschuld"] = -debts["balance"]
    show = debts[["name", "type", "Restschuld", "interest_rate", "monthly_payment", "note"]].rename(
        columns={"name": "Konto", "type": "Art", "interest_rate": "Zins % p.a.",
                 "monthly_payment": "Rate €/Monat", "note": "Notiz"}
    )
    show["Art"] = show["Art"].map(db.ACCOUNT_TYPES)
    st.dataframe(
        show, width="stretch", hide_index=True,
        column_config={
            "Restschuld": st.column_config.NumberColumn(format="%.2f €"),
            "Rate €/Monat": st.column_config.NumberColumn(format="%.2f €"),
            "Zins % p.a.": st.column_config.NumberColumn(format="%.2f %%"),
        },
    )
    st.markdown(f"**Gesamt: {ui.eur(schulden)} Restschuld**, "
                f"monatliche Raten: {ui.eur(float(debts['monthly_payment'].fillna(0).sum()))}")
