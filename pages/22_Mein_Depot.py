"""
Stillhalter AI App — Mein Depot (Seite 22)

Individuelles Depot-Dashboard je Nutzer (Datengrundlage: IBKR Flex Query):
Hebel · Cashquote · NLV-Verlauf · Options-Cashflow · Portfoliozusammensetzung
(Positionen, Asset-Typen, Branchen) + offene Optionspositionen.

Die Flex-Zugangsdaten (Token + Query-ID) werden PRO NUTZER persistent im
Volume gespeichert (data/user_store.py) — einmal einrichten, danach lädt
das Dashboard auf Knopfdruck. Jeder Nutzer sieht ausschließlich sein Depot.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(
    page_title="Mein Depot · Stillhalter AI App",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

import plotly.graph_objects as go
from trading import flex as _flex
from data import user_store as _us
from data.watchlist import get_sector_for_ticker

_user = st.session_state.get("auth_user", "")
_IS_GREEN = st.session_state.get("app_theme", "dark") == "green"
_TXT = "#0a1628" if _IS_GREEN else "#ffffff"

# ── Header ─────────────────────────────────────────────────────────────────────
c1, c2 = st.columns([1, 6])
with c1:
    st.markdown(get_logo_html("auto", 40), unsafe_allow_html=True)
with c2:
    st.markdown(f"""
    <div style='padding-top:4px'>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.8rem;
                    letter-spacing:0.04em'>💼 MEIN DEPOT</div>
        <div style='font-family:RedRose,sans-serif;font-weight:300;font-size:0.8rem;
                    color:#888;text-transform:uppercase;letter-spacing:0.12em;margin-top:2px'>
            Persönliches Dashboard · {_user}
        </div>
    </div>
    """, unsafe_allow_html=True)
st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── Flex-Zugangsdaten (pro Nutzer gespeichert) ────────────────────────────────
_cred = _us.get_value(_user, "flex_credentials", {}) or {}
with st.expander("🔐 IBKR Flex Query — Zugangsdaten",
                 expanded=not (_cred.get("token") and _cred.get("query_id"))):
    st.caption(
        "Einmal eintragen — wird **nur für dein Konto** gespeichert (persistent, "
        "kein erneutes Anmelden nötig). Anleitung zum Erstellen der Flex Queries: "
        "Seite 12 · IBKR Integration. Empfohlene Sektionen der Haupt-Query: "
        "**Open Positions**, **Net Asset Value (NAV) in Base**, **Cash Report**, "
        "**Trades**. Beim Abruf werden beide Queries geholt und zusammengeführt."
    )
    _tok_in = st.text_input("Aktiver Prüfcode (Flex-Query-Token)",
                            value=_cred.get("token", ""), type="password", key="md_tok")
    fq1, fq2 = st.columns(2)
    with fq1:
        _qid_in = st.text_input("Flex-Query ID für Kontoumsätze / Trades *",
                                value=_cred.get("query_id", ""), key="md_qid",
                                help="Pflicht — Haupt-Query mit Open Positions, NAV in "
                                     "Base, Cash Report und Trades: Grundlage für alle "
                                     "Kennzahlen, Charts und den Options-Cashflow.")
    with fq2:
        _qid2_in = st.text_input("Flex-Query ID für Handelsbestätigungen",
                                 value=_cred.get("query_id2", "") or _cred.get("query_id3", ""),
                                 key="md_qid2",
                                 help="Optional: Query mit 'Trade Confirmations' — "
                                      "ergänzt tagesaktuelle Ausführungen.")
    if st.button("💾 Speichern", key="md_save"):
        _us.set_value(_user, "flex_credentials",
                      {"token": _tok_in.strip(), "query_id": _qid_in.strip(),
                       "query_id2": _qid2_in.strip()})
        st.success("Gespeichert — gilt nur für dein Konto.")
        st.rerun()

_cred = _us.get_value(_user, "flex_credentials", {}) or {}
_ready = bool(_cred.get("token") and _cred.get("query_id"))

if not _ready:
    st.info("👆 Zugangsdaten eintragen und speichern — danach lädt dein Dashboard "
            "hier auf Knopfdruck.")
    st.stop()

# ── Daten laden (Session-Cache, um IBKR-Rate-Limits zu schonen) ───────────────
_ck = f"md_data_{_user}"
lc1, lc2 = st.columns([2, 6])
with lc1:
    _do_fetch = st.button("🔄 Depot jetzt aktualisieren", type="primary",
                          use_container_width=True)
with lc2:
    _last = _us.get_value(_user, "last_fetch_ts", "")
    st.caption(f"Letzter Abruf: {_last or '—'} · Abrufe sind bei IBKR "
               f"limitiert — Dashboard nutzt zwischendurch den letzten Stand.")

def _parse_bundle(xmls: list) -> tuple:
    """Mehrere Flex-Reports zusammenführen: NAV/Cash und Positionen aus dem
    ersten Report, der sie liefert — Options-Trades aus allen kombiniert."""
    summ, allpos, _tr_parts = {}, pd.DataFrame(), []
    for _x in xmls:
        _s = _flex.parse_account_summary(_x)
        if _s and (_s.get("nlv") or not summ):
            if _s.get("nlv") or not summ.get("nlv"):
                summ = _s
        _p = _flex.parse_all_positions(_x)
        if allpos.empty and not _p.empty:
            allpos = _p
        _t = _flex.parse_option_trades(_x)
        if not _t.empty:
            _tr_parts.append(_t)
    opttr = (pd.concat(_tr_parts, ignore_index=True).drop_duplicates()
             if _tr_parts else pd.DataFrame())
    return summ, allpos, opttr

if _do_fetch:
    # query_id3 nur noch als Alt-Bestand (frühere 3-Feld-Version) berücksichtigt
    _qids = [q for q in [_cred.get("query_id"), _cred.get("query_id2"),
                         _cred.get("query_id3")] if q]
    _qids = list(dict.fromkeys(_qids))
    xmls, _fails = [], []
    with st.spinner(f"Hole Depot von IBKR… ({len(_qids)} "
                    f"Quer{'ies' if len(_qids) > 1 else 'y'}, je bis zu 45 Sek.)"):
        for _qid in _qids:
            _x, _err, _dbg = _flex.fetch_flex(_cred["token"], _qid)
            if _x:
                xmls.append(_x)
            else:
                _fails.append((_qid, _err, _dbg))
    for _qid, _err, _dbg in _fails:
        st.error(f"Query {_qid}: {_err or 'Unbekannter Fehler'}")
        with st.expander(f"🔍 Diagnose Query {_qid}"):
            st.code(_dbg or "", language="text")
    if xmls:
        st.session_state[_ck] = xmls
        _ts = datetime.now().strftime("%d.%m.%Y %H:%M")
        _us.set_value(_user, "last_fetch_ts", _ts)
        _us.set_value(_user, "last_flex_xml_len", sum(len(_x) for _x in xmls))
        # Persistente Kurzfassung für Anzeige ohne Neuabruf
        summ, allpos, _ = _parse_bundle(xmls)
        _us.set_value(_user, "last_positions", allpos.to_dict("records") if not allpos.empty else [])
        _us.set_value(_user, "last_summary", summ)
        if summ.get("nlv"):
            _us.append_snapshot(_user, "nlv_history",
                                {"ts": _ts, "nlv": summ.get("nlv"), "cash": summ.get("cash")})
        st.success(f"Depot aktualisiert ({len(xmls)} von {len(_qids)} Queries).")

# Datenbasis: frischer Abruf ODER letzter gespeicherter Stand
_xml = st.session_state.get(_ck)
if _xml:
    # Abwärtskompatibel: ältere Sessions haben einen einzelnen XML-String
    summ, allpos, opttr = _parse_bundle([_xml] if isinstance(_xml, str) else _xml)
else:
    summ   = _us.get_value(_user, "last_summary", {}) or {}
    _rec   = _us.get_value(_user, "last_positions", []) or []
    allpos = pd.DataFrame(_rec)
    opttr  = pd.DataFrame()

if allpos.empty and not summ:
    st.warning("Noch keine Daten — bitte einmal **🔄 Depot jetzt aktualisieren** klicken.")
    st.stop()

# ── Kennzahlen ────────────────────────────────────────────────────────────────
nlv  = float(summ.get("nlv") or 0)
cash = float(summ.get("cash") or 0)
gross = float(allpos["value"].abs().sum()) if not allpos.empty else 0.0
long_val = float(allpos.loc[allpos["value"] > 0, "value"].sum()) if not allpos.empty else 0.0
hebel = (gross / nlv) if nlv > 0 else None
cashq = (cash / nlv * 100) if nlv > 0 else None
upnl  = float(allpos["pnl"].sum()) if (not allpos.empty and "pnl" in allpos.columns) else 0.0
opt_cf = float(opttr["proceeds"].sum()) if not opttr.empty else None

k = st.columns(6)
k[0].metric("NLV (Depotwert)", f"${nlv:,.0f}" if nlv else "–",
            help="Net Liquidation Value — braucht die Flex-Sektion 'NAV in Base'.")
k[1].metric("Cash", f"${cash:,.0f}" if summ.get("cash") is not None else "–")
k[2].metric("Hebel", f"{hebel:.2f}×" if hebel else "–",
            help="Brutto-Exposure aller Positionen ÷ NLV")
k[3].metric("Cashquote", f"{cashq:.1f}%" if cashq is not None else "–")
k[4].metric("Unrealisierter P&L", f"${upnl:+,.0f}" if not allpos.empty else "–")
k[5].metric("Options-Cashflow (Report)", f"${opt_cf:+,.0f}" if opt_cf is not None else "–",
            help="Summe der Options-Prämien im Report-Zeitraum — braucht die "
                 "Flex-Sektion 'Trades'.")

# ── Gauges: Hebel + Cashquote ────────────────────────────────────────────────
if hebel is not None or cashq is not None:
    g1, g2, gpad = st.columns([2, 2, 4])
    if hebel is not None:
        with g1:
            figH = go.Figure(go.Indicator(
                mode="gauge+number", value=round(hebel, 2),
                title={"text": "Hebel", "font": {"size": 14}},
                gauge={"axis": {"range": [0, 4]},
                       "bar": {"color": "#d4a843"},
                       "steps": [
                           {"range": [0, 1.2], "color": "rgba(34,197,94,0.35)"},
                           {"range": [1.2, 2], "color": "rgba(245,158,11,0.35)"},
                           {"range": [2, 4], "color": "rgba(239,68,68,0.35)"}]}))
            figH.update_layout(height=180, margin=dict(l=10, r=10, t=30, b=5),
                               paper_bgcolor="rgba(0,0,0,0)", font={"color": _TXT})
            st.plotly_chart(figH, use_container_width=True, config={"displayModeBar": False})
    if cashq is not None:
        with g2:
            figC = go.Figure(go.Indicator(
                mode="gauge+number", value=round(cashq, 1),
                number={"suffix": " %"},
                title={"text": "Cashquote", "font": {"size": 14}},
                gauge={"axis": {"range": [min(0, cashq), 100]},
                       "bar": {"color": "#d4a843"},
                       "steps": [
                           {"range": [min(0, cashq), 10], "color": "rgba(239,68,68,0.35)"},
                           {"range": [10, 30], "color": "rgba(245,158,11,0.35)"},
                           {"range": [30, 100], "color": "rgba(34,197,94,0.35)"}]}))
            figC.update_layout(height=180, margin=dict(l=10, r=10, t=30, b=5),
                               paper_bgcolor="rgba(0,0,0,0)", font={"color": _TXT})
            st.plotly_chart(figC, use_container_width=True, config={"displayModeBar": False})

# ── NLV-Verlauf (wächst mit jedem Abruf) ─────────────────────────────────────
_histo = _us.get_value(_user, "nlv_history", []) or []
if len(_histo) >= 2:
    st.markdown("#### 📈 Depotwert-Verlauf")
    hdf = pd.DataFrame(_histo)
    hdf["ts"] = pd.to_datetime(hdf["ts"], format="%d.%m.%Y %H:%M", errors="coerce")
    st.line_chart(hdf.set_index("ts")["nlv"], height=220)
elif nlv:
    st.caption("📈 Der Depotwert-Verlauf baut sich mit jedem Abruf auf "
               "(erster Punkt ist gespeichert).")

# ── Portfoliozusammensetzung ──────────────────────────────────────────────────
if not allpos.empty:
    def _pie(names, values, title):
        fig = go.Figure(go.Pie(labels=names, values=values, hole=0.35,
                               textinfo="label+percent"))
        fig.update_layout(title=title, height=330, showlegend=False,
                          margin=dict(l=10, r=10, t=40, b=10),
                          paper_bgcolor="rgba(0,0,0,0)", font={"color": _TXT})
        return fig

    p1, p2, p3 = st.columns(3)
    with p1:
        by_sym = (allpos.assign(v=allpos["value"].abs())
                  .groupby("symbol")["v"].sum().sort_values(ascending=False))
        top = by_sym.head(12)
        rest = by_sym.iloc[12:].sum()
        if rest > 0:
            top = pd.concat([top, pd.Series({"Rest": rest})])
        st.plotly_chart(_pie(top.index, top.values,
                             f"Positionen ({allpos['symbol'].nunique()})"),
                        use_container_width=True, config={"displayModeBar": False})
    with p2:
        by_typ = (allpos.assign(v=allpos["value"].abs())
                  .groupby("typ")["v"].sum().sort_values(ascending=False))
        st.plotly_chart(_pie(by_typ.index, by_typ.values, "Asset-Typen"),
                        use_container_width=True, config={"displayModeBar": False})
    with p3:
        def _sector(sym):
            try:
                s = get_sector_for_ticker(sym)
                return (s.split(".", 1)[-1].strip().split("(")[0].strip()
                        if "." in s else s) or "Sonstige"
            except Exception:
                return "Sonstige"
        secs = (allpos.assign(sec=allpos["symbol"].map(_sector),
                              v=allpos["value"].abs())
                .groupby("sec")["v"].sum().sort_values(ascending=False))
        st.plotly_chart(_pie(secs.index, secs.values, "Branchen"),
                        use_container_width=True, config={"displayModeBar": False})

    # ── Offene Optionspositionen ─────────────────────────────────────────────
    opts = allpos[allpos["category"] == "OPT"].copy()
    if not opts.empty:
        st.markdown("#### 🧾 Offene Optionspositionen")
        show = opts[["symbol", "typ", "strike", "expiry", "qty", "mark", "value", "pnl"]] \
            .rename(columns={"symbol": "Ticker", "typ": "Typ", "strike": "Strike",
                             "expiry": "Verfall", "qty": "Kontrakte", "mark": "Preis",
                             "value": "Marktwert", "pnl": "P&L"})
        st.dataframe(show.sort_values("Verfall"), use_container_width=True, hide_index=True,
                     column_config={
                         "Strike":    st.column_config.NumberColumn(format="$%.2f"),
                         "Preis":     st.column_config.NumberColumn(format="$%.2f"),
                         "Marktwert": st.column_config.NumberColumn(format="$%.0f"),
                         "P&L":       st.column_config.NumberColumn(format="$%.0f"),
                     })
        st.caption("➡️ Bewertung nach Stillhalter-Regeln: **Seite 7 · Trade Management** "
                   "(dort denselben Flex-Abruf nutzen).")

if not summ.get("nlv"):
    st.info("ℹ️ **Tipp:** Deine Flex Query liefert aktuell keine NAV-/Cash-Daten — "
            "füge in der Query die Sektionen **'Net Asset Value (NAV) in Base'** und "
            "**'Cash Report'** hinzu, dann erscheinen NLV, Hebel, Cashquote und der "
            "Depotwert-Verlauf. **'Trades'** ergänzt den Options-Cashflow.")
