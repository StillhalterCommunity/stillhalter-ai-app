"""Gemeinsame UI-Helfer: Login, Formatierung, Chart-Defaults."""

import os
from datetime import date

import streamlit as st

# Validierte kategoriale Palette (dunkles Theme), feste Reihenfolge — nie rotieren.
PALETTE = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"]
COL_AUSGABEN = PALETTE[0]   # blau
COL_EINNAHMEN = PALETTE[2]  # aqua
COL_SCHULDEN = PALETTE[1]   # orange


def eur(x: float) -> str:
    """1234.5 -> '1.234,50 €' (deutsche Schreibweise)."""
    if x is None:
        return "–"
    s = f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"


def month_options(n_back: int = 24, n_forward: int = 1) -> list:
    """Liste 'YYYY-MM', aktueller Monat zuerst."""
    y, m = date.today().year, date.today().month
    out = []
    for delta in range(-n_forward, n_back + 1):
        mm = m - delta
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        while mm > 12:
            mm -= 12
            yy += 1
        out.append(f"{yy:04d}-{mm:02d}")
    return sorted(set(out), reverse=True)


def month_select(label: str = "Monat", sidebar: bool = False, key=None) -> str:
    """Monats-Selectbox, vorbelegt mit dem aktuellen Monat."""
    months = month_options()
    cur = date.today().strftime("%Y-%m")
    idx = months.index(cur) if cur in months else 0
    widget = st.sidebar if sidebar else st
    return widget.selectbox(label, months, index=idx, format_func=month_label, key=key)


def month_label(month: str) -> str:
    names = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
             "August", "September", "Oktober", "November", "Dezember"]
    y, m = month.split("-")
    return f"{names[int(m) - 1]} {y}"


def guard() -> None:
    """Optionaler Familien-PIN (Umgebungsvariable FINANZEN_PIN)."""
    pin = os.environ.get("FINANZEN_PIN", "")
    if not pin:
        return
    if st.session_state.get("_pin_ok"):
        return
    st.title("🔒 Familien-Finanzen")
    entered = st.text_input("PIN", type="password")
    if entered:
        if entered == pin:
            st.session_state["_pin_ok"] = True
            st.rerun()
        else:
            st.error("Falscher PIN.")
    st.stop()


def page(title: str, icon: str, wide: bool = True) -> None:
    st.set_page_config(page_title=f"{title} · Familien-Finanzen", page_icon=icon,
                       layout="wide" if wide else "centered")
    guard()


def plotly_defaults(fig):
    """Zurueckhaltende Achsen/Grid, transparente Flaeche, Legende oben."""
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#c3c2b7", size=13),
        margin=dict(l=8, r=8, t=32, b=8),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
        hoverlabel=dict(bgcolor="#1a1a19"),
    )
    fig.update_xaxes(gridcolor="rgba(195,194,183,0.12)", zerolinecolor="rgba(195,194,183,0.25)")
    fig.update_yaxes(gridcolor="rgba(195,194,183,0.12)", zerolinecolor="rgba(195,194,183,0.25)")
    return fig
