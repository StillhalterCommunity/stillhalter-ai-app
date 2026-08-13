"""
Stillhalter AI App — Trade Management
Bewertet offene Positionen nach Stillhalter-Strategie-Regeln.
Import via CSV (IBKR Flex Query oder eigene Vorlage) oder manuelle Eingabe.
"""

import re
import time
import streamlit as st
import pandas as pd
import numpy as np
import io
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, date
from typing import Optional, List, Dict
import math

st.set_page_config(
    page_title="Trade Management · Stillhalter AI App",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

import yfinance as yf
from data.fetcher import (
    fetch_price_history, fetch_stock_info, calculate_dte, fetch_earnings_date,
)
from analysis.technicals import analyze_technicals
from data.watchlist import get_sector_for_ticker


# ══════════════════════════════════════════════════════════════════════════════
# IBKR FLEX WEB SERVICE — geteilte Hilfsfunktionen
# ══════════════════════════════════════════════════════════════════════════════

_IBKR_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/xml,application/xml,*/*",
}
# IBKR Flex Web Service — alle bekannten Endpoints (US + EU + CDN)
_IBKR_SEND_URLS = [
    "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest",
    "https://www.interactivebrokers.eu/Universal/servlet/FlexStatementService.SendRequest",
    "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest",
]
_IBKR_GET_URLS = {
    "www.interactivebrokers.com":    "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement",
    "www.interactivebrokers.eu":     "https://www.interactivebrokers.eu/Universal/servlet/FlexStatementService.GetStatement",
    "gdcdyn.interactivebrokers.com": "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement",
}


_RATE_LIMIT_CODES = {"1018"}   # Too many requests — stop all retries
_TRANSIENT_CODES  = {"1001"}   # Statement not ready — wait, then next endpoint


# Flex-Logik zentral in trading/flex.py (auch vom Depot-Dashboard genutzt)
from trading.flex import (
    fetch_flex as _ibkr_flex_fetch,
    parse_option_positions as _ibkr_parse_positions,
)


# ══════════════════════════════════════════════════════════════════════════════
# VORLAGE CSV
# ══════════════════════════════════════════════════════════════════════════════

TEMPLATE_CSV = """Ticker,Typ,Strike,Verfall,Menge,Praemie_Einstieg,Notizen
AAPL,PUT,185,2026-05-16,-1,2.50,Konservativ nahe Support
NVDA,PUT,900,2026-04-17,-2,8.20,Earnings-Risiko beachten
GS,CALL,560,2026-06-20,-1,4.80,Covered Call auf Long-Position
"""

# Pflicht-Spalten und Aliase (einfache Vorlage)
COL_ALIASES = {
    "ticker":   ["ticker", "symbol", "underlying"],
    "typ":      ["typ", "type", "optiontype", "right"],
    "strike":   ["strike", "strikeprice"],
    "verfall":  ["verfall", "expiration", "expirationdate", "maturity"],
    "menge":    ["menge", "qty", "position", "pos"],
    "praemie":  ["praemie", "praemie_einstieg", "avgcost", "averagecost",
                 "costbasis", "premium", "praemieeinstieg"],
    "notizen":  ["notizen", "notes", "comment"],
}


def _find_col(df, field):
    """Sucht Spaltenname anhand von Aliasen (case-insensitive, leerzeichen-unabhängig)."""
    aliases = COL_ALIASES.get(field, [field])
    lower_cols = {c.lower().replace(" ", "").replace("_", ""): c for c in df.columns}
    for alias in aliases:
        key = alias.lower().replace(" ", "").replace("_", "")
        if key in lower_cols:
            return lower_cols[key]
    return None


# ══════════════════════════════════════════════════════════════════════════════
# IBKR FORMAT ERKENNUNG & PARSING
# ══════════════════════════════════════════════════════════════════════════════

def _is_ibkr_format(df):
    """Erkennt IBKR Flex Query Export anhand charakteristischer Spalten."""
    cols = {c.strip() for c in df.columns}
    # ClientAccountID ist sehr IBKR-spezifisch
    if "ClientAccountID" in cols:
        return True
    # Alternativ: Kombination aus IBKR-typischen Spalten
    ibkr_specific = {"UnderlyingSymbol", "MarkPrice", "FifoPnlUnrealized", "CostBasisPrice"}
    return len(ibkr_specific & cols) >= 3


def _parse_ibkr_option_symbol(symbol):
    """
    Parst IBKR Option-Symbol: 'CRCL  260417P00065000'
    Format: <TICKER><SPACES><YYMMDD><P|C><STRIKE*1000 8-stellig>
    Gibt zurück: (ticker, expiry_date, opt_type, strike) oder (None,None,None,None)
    """
    m = re.match(r'^([A-Z]+)\s+(\d{6})([PC])(\d{8})$', symbol.strip())
    if not m:
        return None, None, None, None
    ticker   = m.group(1)
    date_str = m.group(2)   # YYMMDD
    opt_type = "PUT" if m.group(3) == "P" else "CALL"
    strike   = int(m.group(4)) / 1000.0
    try:
        year   = 2000 + int(date_str[:2])
        month  = int(date_str[2:4])
        day    = int(date_str[4:6])
        expiry = date(year, month, day)
    except Exception:
        expiry = None
    return ticker, expiry, opt_type, strike


def _parse_ibkr_positions(df):
    """
    Parst IBKR Flex Query CSV in normalisiertes Positions-DataFrame.
    Nutzt UnderlyingSymbol als Ticker, CostBasisPrice als Einstiegsprämie,
    MarkPrice als aktuellen Preis, FifoPnlUnrealized als P&L.
    """
    rows = []
    has = {c.strip() for c in df.columns}

    for _, row in df.iterrows():
        def g(col):
            v = row.get(col, "")
            return str(v).strip() if pd.notna(v) else ""

        # Nur Options verarbeiten
        if "AssetClass" in has:
            asset = g("AssetClass").upper()
            if asset and asset not in ("OPT",):
                continue

        # Symbol (z.B. "CRCL  260417P00065000")
        symbol_raw = g("Symbol") if "Symbol" in has else ""
        if not symbol_raw or symbol_raw.lower() in ("", "nan"):
            continue

        # IBKR Symbol parsen (Fallback-Werte)
        sym_ticker, sym_expiry, sym_type, sym_strike = _parse_ibkr_option_symbol(symbol_raw)

        # Ticker: UnderlyingSymbol bevorzugt (sauber), sonst aus Symbol geparst
        ticker = ""
        if "UnderlyingSymbol" in has:
            ticker = g("UnderlyingSymbol")
        ticker = ticker or sym_ticker or ""
        if not ticker or ticker.lower() in ("", "nan"):
            continue

        # Optionstyp
        typ = sym_type or "PUT"
        if "Put/Call" in has:
            pc = g("Put/Call").upper()
            if pc == "P":
                typ = "PUT"
            elif pc == "C":
                typ = "CALL"

        # Strike
        strike = sym_strike or 0.0
        if "Strike" in has:
            try:
                strike = float(g("Strike"))
            except Exception:
                pass

        # Verfall (YYYYMMDD → date)
        expiry = sym_expiry
        if "Expiry" in has:
            exp_str = g("Expiry").strip()
            if len(exp_str) == 8 and exp_str.isdigit():
                try:
                    expiry = datetime.strptime(exp_str, "%Y%m%d").date()
                except Exception:
                    pass
            elif exp_str:
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d.%m.%Y"):
                    try:
                        expiry = datetime.strptime(exp_str, fmt).date()
                        break
                    except Exception:
                        continue

        # Quantity (negativ = Short)
        menge = -1
        if "Quantity" in has:
            try:
                menge = int(float(g("Quantity")))
            except Exception:
                pass

        # MarkPrice = aktueller Optionspreis
        praemie_akt = None
        if "MarkPrice" in has:
            try:
                praemie_akt = float(g("MarkPrice"))
            except Exception:
                pass

        # CostBasisPrice = Einstiegsprämie pro Aktie (Average Cost)
        praemie_ein = 0.0
        if "CostBasisPrice" in has:
            try:
                praemie_ein = abs(float(g("CostBasisPrice")))
            except Exception:
                pass

        # FifoPnlUnrealized = unrealisierter P&L in USD
        pnl_usd = None
        if "FifoPnlUnrealized" in has:
            try:
                pnl_usd = float(g("FifoPnlUnrealized"))
            except Exception:
                pass

        # Description als Notiz
        desc = g("Description") if "Description" in has else ""

        rows.append({
            "Ticker":     ticker,
            "Typ":        typ,
            "Strike":     strike,
            "Verfall":    expiry,
            "Menge":      menge,
            "Prämie_Ein": praemie_ein,
            "Prämie_Akt": praemie_akt,   # aus IBKR direkt
            "PnL_USD":    pnl_usd,        # aus IBKR direkt
            "Notizen":    desc,
            "_ibkr":      True,           # Marker für IBKR-Import
        })

    return pd.DataFrame(rows) if rows else pd.DataFrame()


def _parse_simple_positions(df):
    """Parst einfache Vorlage-CSV (Ticker, Typ, Strike, Verfall, Menge, Praemie_Einstieg)."""
    result_rows = []
    for _, row in df.iterrows():
        r = {k: str(v).strip() if pd.notna(v) else "" for k, v in row.items()}

        def _val(col):
            return r.get(col, "") if col else ""

        ticker = _val(_find_col(df, "ticker")).upper()
        if not ticker or ticker in ("NAN", ""):
            continue

        # Typ normalisieren
        typ_raw = _val(_find_col(df, "typ")).upper()
        if "PUT" in typ_raw or (typ_raw == "P"):
            typ = "PUT"
        elif "CALL" in typ_raw or (typ_raw == "C"):
            typ = "CALL"
        else:
            typ = "PUT"

        try:
            strike = float(_val(_find_col(df, "strike")).replace(",", "."))
        except Exception:
            strike = 0.0

        try:
            menge = int(float(_val(_find_col(df, "menge")).replace(",", ".")))
        except Exception:
            menge = -1

        try:
            praemie = abs(float(_val(_find_col(df, "praemie")).replace(",", ".")))
        except Exception:
            praemie = 0.0

        # Verfall parsen
        verfall_raw = _val(_find_col(df, "verfall"))
        verfall = None
        for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%m/%d/%Y", "%Y%m%d"):
            try:
                verfall = datetime.strptime(verfall_raw[:10], fmt).date()
                break
            except Exception:
                continue

        notiz = _val(_find_col(df, "notizen"))

        result_rows.append({
            "Ticker":     ticker,
            "Typ":        typ,
            "Strike":     strike,
            "Verfall":    verfall,
            "Menge":      menge,
            "Prämie_Ein": praemie,
            "Prämie_Akt": None,
            "PnL_USD":    None,
            "Notizen":    notiz,
            "_ibkr":      False,
        })

    return pd.DataFrame(result_rows) if result_rows else pd.DataFrame()


def parse_positions_csv(uploaded_file):
    """
    Liest Positions-CSV ein.
    Erkennt automatisch IBKR Flex Query Format oder einfache Vorlage.
    Gibt DataFrame mit normalisierten Spalten zurück.
    """
    try:
        raw = pd.read_csv(uploaded_file, sep=None, engine="python", dtype=str)
        raw.columns = raw.columns.str.strip()

        if _is_ibkr_format(raw):
            df = _parse_ibkr_positions(raw)
            return df
        else:
            return _parse_simple_positions(raw)
    except Exception as e:
        st.error(f"CSV-Fehler: {e}")
        return pd.DataFrame()


# ══════════════════════════════════════════════════════════════════════════════
# POSITIONS-BEWERTUNG
# ══════════════════════════════════════════════════════════════════════════════

# Bewertungslogik zentral in trading/position_eval.py (auch von Seite 22 genutzt)
from trading.position_eval import evaluate_position, _get_option_price  # noqa: F401




# ══════════════════════════════════════════════════════════════════════════════
# SEITE
# ══════════════════════════════════════════════════════════════════════════════

# Header
col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.html(get_logo_html("auto", 40))
with col_title:
    st.html(
        "<div style='padding-top:4px'>"
        "<div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.8rem;"
        "color:#f0f0f0;letter-spacing:0.04em'>TRADE MANAGEMENT</div>"
        "<div style='font-family:RedRose,sans-serif;font-weight:300;font-size:0.8rem;"
        "color:#666;text-transform:uppercase;letter-spacing:0.12em;margin-top:2px'>"
        "Offene Positionen bewerten · Rollempfehlungen · Stillhalter-Strategie"
        "</div></div>"
    )

st.html('<div class="gold-line"></div>')

# Disclaimer
st.html("""
<div style='background:#1a1205;border:1px solid #3a2a05;border-left:4px solid #d4a843;
            border-radius:8px;padding:10px 16px;font-family:sans-serif;font-size:0.8rem;
            color:#888;margin-bottom:16px'>
    ⚖️ <b style='color:#d4a843'>Kein Anlageberatung</b> — Alle Bewertungen basieren auf
    technischen Indikatoren der Stillhalter-Strategie und sind rein informativ.
    Entscheide eigenverantwortlich.
</div>
""")

# ── Session State ──────────────────────────────────────────────────────────────
if "tm_positions" not in st.session_state:
    st.session_state.tm_positions = pd.DataFrame()
if "tm_results"   not in st.session_state:
    st.session_state.tm_results   = {}
if "tm_is_ibkr"   not in st.session_state:
    st.session_state.tm_is_ibkr   = False


# ══════════════════════════════════════════════════════════════════════════════
# EINGABE: CSV UPLOAD ODER MANUELLE EINGABE
# ══════════════════════════════════════════════════════════════════════════════

tab_import, tab_manual, tab_ibkr = st.tabs(["📁 CSV Import", "✏️ Manuelle Eingabe", "🔌 IBKR Live"])

with tab_import:
    ci1, ci2 = st.columns([3, 1])
    with ci1:
        st.markdown(
            "**Positionsliste importieren** — lade eine CSV-Datei mit deinen offenen Optionspositionen. "
            "Unterstützt **IBKR Flex Query Export** und eigene Vorlage automatisch."
        )
        with st.expander("📋 CSV-Import — Anleitung"):
            st.markdown("""
**IBKR Flex Query Export (empfohlen):**
1. IBKR → Performance & Reports → Flex Queries → Create Query
2. Report Type: **Open Positions**
3. Alle Felder wählen (oder mindestens: Symbol, UnderlyingSymbol, Put/Call, Strike, Expiry, Quantity, MarkPrice, CostBasisPrice, FifoPnlUnrealized)
4. Format: CSV → Exportieren und hochladen

**Eigene Vorlage:**
1. Vorlage herunterladen (→ rechts)
2. Positionen eintragen: Ticker, Typ (PUT/CALL), Strike, Verfall, Menge (-=Short), Prämie
3. Als CSV speichern und hochladen

**Erkannte Spalten-Namen (automatisch):**
- `Ticker` / `UnderlyingSymbol` · `Typ` / `Put/Call`
- `Strike` · `Verfall` / `Expiry`
- `Menge` / `Quantity` · `Praemie_Einstieg` / `CostBasisPrice`
            """)

    with ci2:
        st.download_button(
            "📥 Vorlage herunterladen",
            TEMPLATE_CSV,
            "positionen_vorlage.csv",
            "text/csv",
            use_container_width=True,
        )

    uploaded = st.file_uploader(
        "CSV-Datei hochladen",
        type=["csv", "txt"],
        help="IBKR Flex Query Export oder eigene Vorlage",
    )

    if uploaded:
        parsed = parse_positions_csv(uploaded)
        if not parsed.empty:
            is_ibkr = "_ibkr" in parsed.columns and parsed["_ibkr"].any()
            fmt_label = "🏦 IBKR Flex Query" if is_ibkr else "📋 Eigene Vorlage"
            st.success(f"✅ {len(parsed)} Positionen erkannt ({fmt_label})")

            # Vorschau-Tabelle
            preview_cols = ["Ticker", "Typ", "Strike", "Verfall", "Menge", "Prämie_Ein"]
            if is_ibkr:
                preview_cols += ["Prämie_Akt", "PnL_USD"]
            display_cols = [c for c in preview_cols if c in parsed.columns]
            st.dataframe(parsed[display_cols], use_container_width=True, hide_index=True)

            if st.button("📊 Positionen übernehmen", type="primary"):
                st.session_state.tm_positions = parsed
                st.session_state.tm_results   = {}
                st.session_state.tm_is_ibkr   = is_ibkr
                st.rerun()
        else:
            st.error("Keine Positionen erkannt — bitte Spalten prüfen.")

with tab_manual:
    st.markdown("**Position manuell hinzufügen:**")
    mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
    with mc1:
        m_ticker  = st.text_input("Ticker", placeholder="AAPL", key="m_ticker").upper()
    with mc2:
        m_typ     = st.selectbox("Typ", ["PUT", "CALL"], key="m_typ")
    with mc3:
        m_strike  = st.number_input("Strike", 0.0, 10000.0, 100.0, 1.0, key="m_strike")
    with mc4:
        m_verfall = st.date_input("Verfall", value=date.today(), key="m_verfall")
    with mc5:
        m_menge   = st.number_input("Kontrakte", -50, 50, -1, 1, key="m_menge",
                                    help="Negativ = Short (Standard für Stillhalter)")
    with mc6:
        m_praemie = st.number_input("Prämie Einstieg", 0.0, 500.0, 0.0, 0.5, key="m_praemie",
                                    format="%.2f")

    m_notiz = st.text_input("Notiz (optional)", key="m_notiz")

    if st.button("➕ Position hinzufügen", use_container_width=False):
        if m_ticker and m_strike > 0 and m_praemie > 0:
            new_row = pd.DataFrame([{
                "Ticker":     m_ticker,
                "Typ":        m_typ,
                "Strike":     m_strike,
                "Verfall":    m_verfall,
                "Menge":      m_menge,
                "Prämie_Ein": m_praemie,
                "Prämie_Akt": None,
                "PnL_USD":    None,
                "Notizen":    m_notiz,
                "_ibkr":      False,
            }])
            st.session_state.tm_positions = pd.concat(
                [st.session_state.tm_positions, new_row], ignore_index=True
            )
            st.session_state.tm_results = {}
            st.success(f"✅ {m_ticker} {m_typ} @{m_strike:.0f} hinzugefügt")
        else:
            st.warning("Bitte Ticker, Strike und Einstiegsprämie ausfüllen.")

with tab_ibkr:
    # ── IBKR Flex Web Service Live-Abruf ─────────────────────────────────────
    st.html("""
<div style='background:#0a1020;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;
     padding:14px 16px;margin-bottom:18px;font-family:sans-serif'>
  <div style='font-size:0.9rem;font-weight:800;color:#3b82f6;margin-bottom:6px'>
    🔌 IBKR Flex Web Service — Live-Abruf</div>
  <div style='font-size:0.75rem;color:#aaa;line-height:1.7'>
    Gib einmalig deinen <b style='color:#f0f0f0'>Flex-Web-Service-Token</b> und die
    <b style='color:#f0f0f0'>Query-ID</b> ein — die App holt deine offenen Positionen
    direkt von IBKR. Kein manueller Export nötig.<br>
    <b style='color:#22c55e'>Read-only</b> — kein Handel, nur Reporting-Daten.
  </div>
</div>
""")

    # Session State für Credentials
    if "ibkr_token"    not in st.session_state: st.session_state["ibkr_token"]    = ""
    if "ibkr_qid_pos"  not in st.session_state: st.session_state["ibkr_qid_pos"]  = ""
    if "ibkr_qid_trade" not in st.session_state: st.session_state["ibkr_qid_trade"] = ""

    ti1, ti2, ti3 = st.columns([3, 1.5, 1.5])
    with ti1:
        tm_token = st.text_input(
            "Flex-Web-Service-Token",
            value=st.session_state["ibkr_token"],
            placeholder="Token aus IBKR → Flex Queries → ⚙️ Zahnrad → Token generieren",
            type="password",
            key="tm_ibkr_token_input",
        )
        st.session_state["ibkr_token"] = tm_token
    with ti2:
        tm_qid = st.text_input(
            "Query-ID: Kontoumsatz",
            value=st.session_state["ibkr_qid_pos"],
            placeholder="z.B. 1414125",
            key="tm_ibkr_qid_input",
        )
        st.session_state["ibkr_qid_pos"] = tm_qid
    with ti3:
        tm_qid_t = st.text_input(
            "Query-ID: Handelsbestätigung",
            value=st.session_state["ibkr_qid_trade"],
            placeholder="z.B. 1414127",
            key="tm_ibkr_qid_trade_input",
        )
        st.session_state["ibkr_qid_trade"] = tm_qid_t

    st.html("""
<div style='font-size:0.68rem;color:#444;font-family:sans-serif;margin-top:2px;margin-bottom:12px'>
  🔒 Token nur in deiner Session — nie gespeichert oder übertragen.
</div>
""")

    btn_col1, btn_col2 = st.columns([2, 3])
    with btn_col1:
        tm_fetch_btn = st.button(
            "🔄 Positionen von IBKR laden",
            key="tm_ibkr_fetch",
            type="primary",
            use_container_width=True,
            disabled=not (tm_token.strip() and tm_qid.strip()),
        )
    with btn_col2:
        tm_test_btn = st.button("🔍 Verbindung testen", key="tm_ibkr_test",
                                use_container_width=False,
                                help="Prüft ob IBKR-Server erreichbar ist (ohne Token)")

    if tm_test_btn:
        with st.spinner("Teste Verbindung zu allen IBKR-Endpoints…"):
            results = []
            for send_url in _IBKR_SEND_URLS:
                host = send_url.split("/")[2]
                try:
                    tr = requests.get(f"{send_url}?t=TEST&q=0&v=3",
                                      headers=_IBKR_HEADERS, timeout=10)
                    results.append(f"✅ {host} → HTTP {tr.status_code}")
                except Exception as te:
                    results.append(f"❌ {host} → {type(te).__name__}: {str(te)[:100]}")
            status_str = "\n".join(results)
            if any("✅" in r for r in results):
                st.success(f"Erreichbare IBKR-Server:\n{status_str}\n\n"
                           "Token & Query-ID prüfen falls Abruf trotzdem fehlschlägt.")
            else:
                st.error(f"Alle IBKR-Server nicht erreichbar:\n{status_str}\n\n"
                         "→ Netzwerkverbindung oder DNS prüfen")

    # Session-State-Keys für IBKR-Preview (persistent über Button-Klicks hinweg)
    if "ibkr_preview_df"  not in st.session_state: st.session_state["ibkr_preview_df"]  = None
    if "ibkr_fetch_error" not in st.session_state: st.session_state["ibkr_fetch_error"] = None
    if "ibkr_fetch_debug" not in st.session_state: st.session_state["ibkr_fetch_debug"] = None

    if tm_fetch_btn:
        with st.spinner("Verbinde mit IBKR… (bis zu 45 Sek., Endpoints werden nacheinander geprüft)"):
            xml_str, err_detail, debug_info = _ibkr_flex_fetch(
                tm_token.strip(), tm_qid.strip()
            )
        if xml_str:
            df_raw = _ibkr_parse_positions(xml_str)
            if not df_raw.empty:
                def _parse_verfall(v):
                    if isinstance(v, date): return v
                    try: return datetime.strptime(str(v), "%Y%m%d").date()
                    except Exception: return None
                df_raw["Verfall"] = df_raw["Verfall"].apply(_parse_verfall)
                st.session_state["ibkr_preview_df"]  = df_raw
                st.session_state["ibkr_fetch_error"] = None
            else:
                st.session_state["ibkr_preview_df"]  = pd.DataFrame()
                st.session_state["ibkr_fetch_error"] = "no_positions"
            st.session_state["ibkr_fetch_debug"] = None
        else:
            st.session_state["ibkr_preview_df"]  = None
            st.session_state["ibkr_fetch_error"] = err_detail
            st.session_state["ibkr_fetch_debug"] = debug_info

    # Preview und Accept-Button — immer gerendert wenn Daten vorhanden
    preview_df = st.session_state.get("ibkr_preview_df")
    fetch_err  = st.session_state.get("ibkr_fetch_error")
    fetch_dbg  = st.session_state.get("ibkr_fetch_debug")

    if preview_df is not None and not preview_df.empty:
        st.success(f"✅ {len(preview_df)} Optionspositionen von IBKR geladen!")
        preview_cols = [c for c in ["Ticker", "Typ", "Strike", "Verfall",
                                     "Menge", "Prämie_Ein", "Prämie_Akt", "PnL_USD"]
                        if c in preview_df.columns]
        st.dataframe(preview_df[preview_cols].reset_index(drop=True),
                     use_container_width=True, hide_index=True)

        if st.button("📊 Ins Trade Management übernehmen",
                     key="tm_ibkr_accept", type="primary"):
            st.session_state.tm_positions            = st.session_state["ibkr_preview_df"]
            st.session_state.tm_results              = {}
            st.session_state.tm_is_ibkr              = True
            st.session_state["ibkr_preview_df"]      = None  # Preview leeren
            st.rerun()

    elif fetch_err == "no_positions":
        st.warning("Verbindung OK, aber keine offenen Optionspositionen gefunden. "
                   "Prüfe ob die Query 'Open Positions' enthält und Optionen offen sind.")
    elif fetch_err:
        if "Rate Limit" in str(fetch_err) or "1018" in str(fetch_err):
            st.warning(f"⏱️ {fetch_err}", icon="⚠️")
        else:
            st.error(f"❌ {fetch_err}")
        if fetch_dbg:
            with st.expander("🔍 Diagnose-Log"):
                st.code(fetch_dbg, language="text")

    # Hinweis auf vollständige Anleitung
    st.html("""
<div style='margin-top:16px;font-size:0.73rem;color:#444;font-family:sans-serif'>
  📖 Vollständige Setup-Anleitung mit Screenshots → <b>Seite 11: IBKR Integration</b>
</div>
""")

st.html('<div class="gold-line"></div>')


# ══════════════════════════════════════════════════════════════════════════════
# POSITIONEN ANZEIGEN & BEWERTEN
# ══════════════════════════════════════════════════════════════════════════════

positions = st.session_state.tm_positions

if positions.empty:
    st.html("""
    <div style='text-align:center;padding:4rem 2rem;color:#333'>
        <div style='font-size:3rem'>⚖️</div>
        <div style='font-family:RedRose,sans-serif;font-size:1.1rem;margin-top:1rem;color:#555'>
            Noch keine Positionen — CSV importieren oder manuell eingeben
        </div>
    </div>
    """)
else:
    is_ibkr  = st.session_state.get("tm_is_ibkr", False)
    ibkr_badge = " &nbsp;<span style='background:#1a2a3a;border:1px solid #2a4a6a;border-radius:4px;padding:1px 8px;font-size:0.7rem;color:#60a5fa'>IBKR Import</span>" if is_ibkr else ""

    st.html(
        f"<div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.1rem;"
        f"color:#d4a843;margin-bottom:8px'>⚖️ {len(positions)} Offene Position(en){ibkr_badge}</div>"
    )

    btn_c1, btn_c2, _ = st.columns([2, 2, 8])
    with btn_c1:
        run_eval = st.button("📊 Alle Positionen bewerten", type="primary",
                             use_container_width=True)
    with btn_c2:
        if st.button("🗑️ Alle löschen", use_container_width=True):
            st.session_state.tm_positions = pd.DataFrame()
            st.session_state.tm_results   = {}
            st.session_state.tm_is_ibkr   = False
            st.rerun()

    # Dringende Warnung: Positionen mit DTE ≤ 1 sofort anzeigen
    urgent_positions = []
    for _, pos in positions.iterrows():
        verfall_val = pos.get("Verfall")
        if hasattr(verfall_val, "strftime"):
            verfall_str = verfall_val.strftime("%Y-%m-%d")
        else:
            verfall_str = str(verfall_val)[:10] if verfall_val else ""
        if verfall_str:
            try:
                dte_check = calculate_dte(verfall_str)
                if dte_check is not None and 0 <= dte_check <= 1:
                    ticker_u = str(pos.get("Ticker", ""))
                    typ_u    = str(pos.get("Typ", ""))
                    strike_u = float(pos.get("Strike", 0))
                    urgent_positions.append(f"{ticker_u} {typ_u} @{strike_u:.0f} ({dte_check}T)")
            except Exception:
                pass

    if urgent_positions:
        st.html(
            "<div style='background:#3a0a0a;border:2px solid #ef4444;border-radius:8px;"
            "padding:12px 16px;margin-bottom:12px;font-family:sans-serif'>"
            "<div style='font-weight:700;color:#ef4444;font-size:0.95rem;margin-bottom:4px'>"
            "🚨 DRINGENDE POSITIONEN — Verfallen morgen oder heute!</div>"
            "<div style='color:#fca5a5;font-size:0.82rem'>"
            + " &nbsp;·&nbsp; ".join(urgent_positions) +
            "</div></div>"
        )

    # Bewertung ausführen
    if run_eval:
        results  = {}
        progress = st.progress(0.0)
        status   = st.empty()
        total    = len(positions)

        for i, (_, pos) in enumerate(positions.iterrows()):
            ticker = str(pos.get("Ticker", ""))
            status.markdown(f"Analysiere **{ticker}** ({i+1}/{total})…")
            try:
                verfall_val = pos.get("Verfall")
                if hasattr(verfall_val, "strftime"):
                    verfall_str = verfall_val.strftime("%Y-%m-%d")
                else:
                    verfall_str = str(verfall_val)[:10]

                # Vorberechnete IBKR-Werte übergeben (wenn vorhanden)
                p_akt_pre = None
                pnl_pre   = None
                if "_ibkr" in pos.index and pos.get("_ibkr"):
                    try:
                        v = pos.get("Prämie_Akt")
                        p_akt_pre = float(v) if (v is not None and str(v) not in ("", "nan", "None")) else None
                    except Exception:
                        pass
                    try:
                        v = pos.get("PnL_USD")
                        pnl_pre = float(v) if (v is not None and str(v) not in ("", "nan", "None")) else None
                    except Exception:
                        pass

                ev = evaluate_position(
                    ticker          = ticker,
                    typ             = str(pos.get("Typ", "PUT")),
                    strike          = float(pos.get("Strike", 0)),
                    verfall_str     = verfall_str,
                    menge           = int(pos.get("Menge", -1)),
                    praemie_ein     = float(pos.get("Prämie_Ein", 0)),
                    praemie_akt_pre = p_akt_pre,
                    pnl_usd_pre     = pnl_pre,
                )
                results[i] = ev
            except Exception as e:
                results[i] = {"empfehlung": f"Fehler: {e}", "empfehlung_color": "#555"}
            progress.progress((i + 1) / total)

        status.markdown(f"✅ **{total} Positionen bewertet**")
        st.session_state.tm_results = results
        progress.empty()

    # ── Ergebnisse anzeigen ────────────────────────────────────────────────────
    results = st.session_state.tm_results

    # KPI-Übersicht
    if results:
        empf_counts = {}
        total_pnl   = 0.0
        for ev in results.values():
            if isinstance(ev, dict):
                e = ev.get("empfehlung", "–")
                empf_counts[e] = empf_counts.get(e, 0) + 1
                pnl = ev.get("pnl_usd")
                if pnl is not None:
                    total_pnl += pnl

        km = st.columns(5)
        km[0].metric("Positionen",      len(positions))
        km[1].metric("✅ Nach Plan",     sum(v for k, v in empf_counts.items()
                                            if k.startswith("✅")))
        km[2].metric("💰 Schließen",    sum(v for k, v in empf_counts.items()
                                            if k.startswith("💰")))
        km[3].metric("⚠️ Handlung nötig", sum(v for k, v in empf_counts.items()
                                              if any(x in k for x in ["Rollen", "Einbuchen", "Am Geld", "OTM-Abstand"])))
        pnl_delta = f"+{total_pnl:.0f}" if total_pnl >= 0 else f"{total_pnl:.0f}"
        km[4].metric("Gesamt P&L (USD)", pnl_delta)
        st.markdown("---")

    # ── Positions-Karten ───────────────────────────────────────────────────────
    for i, (_, pos) in enumerate(positions.iterrows()):
        ticker = str(pos.get("Ticker", ""))
        typ    = str(pos.get("Typ", "PUT"))
        strike = float(pos.get("Strike", 0))
        menge  = int(pos.get("Menge", -1))
        p_ein  = float(pos.get("Prämie_Ein", 0))
        notiz  = str(pos.get("Notizen", ""))
        if notiz in ("nan", "None"):
            notiz = ""

        verfall_val = pos.get("Verfall")
        if hasattr(verfall_val, "strftime"):
            verfall_str = verfall_val.strftime("%Y-%m-%d")
            verfall_fmt = verfall_val.strftime("%d.%m.%Y")
        else:
            verfall_str = str(verfall_val)[:10] if verfall_val else ""
            try:
                verfall_fmt = datetime.strptime(verfall_str, "%Y-%m-%d").strftime("%d.%m.%Y")
            except Exception:
                verfall_fmt = verfall_str

        ev = results.get(i, {})

        kurs     = ev.get("kurs")
        dte      = ev.get("dte")
        p_akt    = ev.get("praemie_aktuell")
        pnl_pct  = ev.get("pnl_pct")
        pnl_usd  = ev.get("pnl_usd")
        otm_pct  = ev.get("otm_pct")
        empf     = ev.get("empfehlung", "Noch nicht bewertet")
        empf_col = ev.get("empfehlung_color", "#555")
        risiko   = ev.get("risiko_score", 0)
        details  = ev.get("details", [])
        is_long  = ev.get("is_long", menge > 0)
        sektor   = get_sector_for_ticker(ticker)
        sektor   = sektor.split(".", 1)[-1].strip().split("(")[0].strip() if "." in sektor else sektor

        # DTE-Farbe — für Long OTM: DTE niedrig = GUT (grün)
        if dte is not None:
            if dte <= 1:
                if is_long and (otm_pct or 0) >= 5:
                    dte_color, dte_icon = "#22c55e", "✅"   # Long OTM verfällt wertlos = gut
                else:
                    dte_color, dte_icon = "#ef4444", "🚨"
            elif dte <= 7:
                if is_long and (otm_pct or 0) >= 5:
                    dte_color, dte_icon = "#22c55e", "🟢"
                else:
                    dte_color, dte_icon = "#ef4444", "🔴"
            elif dte <= 21:
                dte_color, dte_icon = "#f59e0b", "🟡"
            else:
                dte_color, dte_icon = "#22c55e", "🟢"
        else:
            dte_color, dte_icon = "#555", "⚪"

        # P&L Farbe — für Long OTM (erwartet wertlos): neutral/grün, nicht rot
        if pnl_pct is not None:
            if is_long and (pnl_pct or 0) < 0:
                if (otm_pct or 0) < 0:
                    # Long ITM — Schutz greift, Wertgewinn = grün
                    pnl_color = "#22c55e"
                elif (otm_pct or 0) >= 5:
                    # Long OTM verfällt planmäßig — neutral (grau), keine Warnung
                    pnl_color = "#888"
                else:
                    # Long nahe Strike — leichte Warnung
                    pnl_color = "#f59e0b"
            else:
                pnl_color = "#22c55e" if (pnl_pct or 0) >= 0 else "#ef4444"
        else:
            pnl_color = "#888"

        pnl_str     = f"{'+' if (pnl_pct or 0) >= 0 else ''}{pnl_pct:.1f}%" if pnl_pct is not None else "–"
        pnl_usd_str = (f"{'+'  if (pnl_usd or 0) >= 0 else ''}{pnl_usd:.0f} USD"
                       if pnl_usd is not None else "")

        # P&L Box Label und Hintergrund
        if is_long and (pnl_pct or 0) < 0 and (otm_pct or 0) >= 5:
            pnl_label  = "Absicherungskosten"
            pnl_bg     = "#0e0e0e"
            pnl_border = "#1e1e1e"
        elif is_long and (otm_pct or 0) < 0:
            pnl_label  = "Schutz aktiv · P&amp;L"
            pnl_bg     = "#0c1a0c"
            pnl_border = "#1a3a1a"
        else:
            pnl_label  = "P&amp;L unrealisiert"
            pnl_bg     = "#0c1a0c"
            pnl_border = "#1a3a1a"

        # OTM-Farbe
        otm_color = "#22c55e" if (otm_pct or 0) >= 10 else ("#f59e0b" if (otm_pct or 0) >= 0 else "#ef4444")

        # ── Innerer Wert + Zeitwert-Anzeige ────────────────────────────────────
        intrinsic_val = None
        if kurs and strike > 0:
            if typ == "PUT":
                intrinsic_val = round(max(0.0, strike - kurs), 2)
            else:
                intrinsic_val = round(max(0.0, kurs - strike), 2)

        intrinsic_str = ""
        zeitwert_row  = ""
        if p_akt is not None and p_ein > 0:
            if intrinsic_val is not None:
                # Für Short: Innerer Wert > 0 = Option ITM = schlecht (rot)
                # Für Long: Innerer Wert > 0 = Schutz greift = gut (grün)
                if intrinsic_val > 0:
                    itm_col = "#22c55e" if is_long else "#ef4444"
                else:
                    itm_col = "#555"
                intrinsic_str = (
                    f'<div style="display:flex;justify-content:space-between">'
                    f'<span style="font-size:0.72rem;color:#444;font-family:sans-serif">Innerer Wert</span>'
                    f'<span style="font-size:0.8rem;color:{itm_col};font-family:sans-serif">'
                    f'{intrinsic_val:.2f} USD</span></div>'
                )
            # Zeitwert-Saldo: p_ein - p_akt
            # Positiv = Option billiger als Einstieg (gut für Short)
            # Negativ = Option teurer als Einstieg (schlecht für Short)
            zeitwert_saldo = round(p_ein - p_akt, 2)
            if is_long:
                # Für Long: aktuellen Zeitwert zeigen (p_akt - intrinsic_val)
                tv = round(p_akt - (intrinsic_val or 0.0), 2) if intrinsic_val is not None else None
                tv_str = f"{tv:.2f} USD" if tv is not None else "–"
                zeitwert_row = (
                    f'<div style="display:flex;justify-content:space-between">'
                    f'<span style="font-size:0.72rem;color:#444;font-family:sans-serif">Zeitwert</span>'
                    f'<span style="font-size:0.8rem;color:#888;font-family:sans-serif">'
                    f'{tv_str}</span></div>'
                )
            else:
                z_col  = "#22c55e" if zeitwert_saldo > 0 else "#ef4444"
                z_sign = "+" if zeitwert_saldo > 0 else ""
                zeitwert_row = (
                    f'<div style="display:flex;justify-content:space-between">'
                    f'<span style="font-size:0.72rem;color:#444;font-family:sans-serif">Zeitwert</span>'
                    f'<span style="font-size:0.8rem;color:{z_col};font-family:sans-serif">'
                    f'{z_sign}{zeitwert_saldo:.2f} USD</span></div>'
                )

        kontrakts    = abs(menge)
        position_dir = "Short" if menge < 0 else "Long"
        strategy_lbl = f"{position_dir} {typ}"

        # ── Monitor-Style-Karte (einheitliches Layout wie Trade Monitor) ──────
        _is_green_tm = st.session_state.get("app_theme", "dark") == "green"
        if _is_green_tm:
            _bg, _tmain, _tsub = "#eef8f5", "#0a1628", "#475569"
        else:
            _bg, _tmain, _tsub = "#0e0e0e", "#ffffff", "#ffffff"

        G_, R_ = "#22c55e", "#ef4444"
        dte_v = dte if dte is not None else 0
        # Restlaufzeit-Balken (kein Einstiegsdatum in CSV/IBKR → DTE-Referenz 45T)
        _bar_col = G_ if dte_v > 21 else ("#f59e0b" if dte_v > 7 else R_)
        _bar_pct = int(min(1.0, dte_v / 45) * 100)

        # Kurs↔Strike-Skala — grüne Seite = gut für DIESE Position (Short/Long)
        is_call_tm = (typ == "CALL")
        _lo, _hi = strike * 0.85, strike * 1.15
        _ppos = ((kurs - _lo) / (_hi - _lo) * 100) if (kurs and _hi > _lo) else 50.0
        _ppos = max(4, min(96, _ppos))
        _good_right = (not is_call_tm)          # Short Put: über Strike = OTM = gut
        if is_long:
            _good_right = not _good_right       # Long: invertiert (ITM = Schutz greift)
        if _good_right:
            _zone = f"linear-gradient(90deg,{R_}33 0%,{R_}1f 49%,{G_}1f 51%,{G_}33 100%)"
        else:
            _zone = f"linear-gradient(90deg,{G_}33 0%,{G_}1f 49%,{R_}1f 51%,{R_}33 100%)"

        def _tm_tile(label, value, vcolor, sub=""):
            sub_html = (f"<div style='font-size:0.7rem;color:{_tsub};margin-top:1px'>{sub}</div>"
                        if sub else "")
            return (f"<div style='flex:1;min-width:74px;background:{_bg};border:1px solid {_tsub}55;"
                    f"border-radius:8px;padding:8px;text-align:center'>"
                    f"<div style='font-size:0.72rem;color:{_tsub};text-transform:uppercase;"
                    f"letter-spacing:0.04em'>{label}</div>"
                    f"<div style='font-size:1.12rem;font-weight:700;color:{vcolor};margin-top:2px'>{value}</div>"
                    f"{sub_html}</div>")

        _otm_lbl_tm = "OTM" if (otm_pct or 0) >= 0 else "ITM"
        tiles_tm = (
            _tm_tile("Abstand", (f"{otm_pct:+.1f}% {_otm_lbl_tm}" if otm_pct is not None else "–"), otm_color)
            + _tm_tile("Option", (f"${p_akt:.2f}" if p_akt is not None else "–"), _tmain,
                       sub=(f"Einstieg ${p_ein:.2f}" if p_ein > 0 else ""))
            + _tm_tile("P&L", pnl_usd_str or "–", pnl_color,
                       sub=(pnl_str if pnl_pct is not None else ""))
            + _tm_tile("Rest", f"{dte_v} T", _tmain, sub=verfall_fmt)
        )

        # OptionStrat-Link (aus Ticker/Strike/Verfall generiert)
        try:
            from analysis.batch_screener import _optionstrat_url as _tm_os_url
            _os = _tm_os_url(ticker, strike, verfall_str, is_call_tm) if verfall_str else ""
        except Exception:
            _os = ""
        _os_html = (f"<a href='{_os}' target='_blank' style='color:{empf_col};"
                    f"text-decoration:none;font-weight:600'>📊 OptionStrat ↗</a>" if _os else "")

        _details_html = ""
        if details:
            _dt_line = " &nbsp;·&nbsp; ".join(f"{icon} {text}" for icon, text in details[:4])
            _details_html = (f"<div style='font-size:0.78rem;color:{_tsub};margin-top:8px;"
                             f"line-height:1.6;opacity:0.9'>{_dt_line}</div>")
        _notiz_html = (f"<div style='font-size:0.78rem;color:{_tsub};margin-top:4px'>📝 {notiz}</div>"
                       if notiz else "")
        _ibkr_html = ("<span style='font-size:0.72rem;color:#60a5fa;font-weight:600'>⬡ IBKR</span>"
                      if is_ibkr else "")

        st.html(f"""
<div style='background:{_bg};border:1px solid {empf_col}40;border-radius:14px;
            padding:14px 16px;margin-bottom:4px;box-shadow:0 1px 4px rgba(0,0,0,0.18);
            font-family:RedRose,sans-serif'>
  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px'>
    <div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap'>
      <span style='font-weight:700;font-size:1.4rem;color:{_tmain};letter-spacing:0.02em'>{ticker}</span>
      <span style='background:{empf_col}2a;color:{empf_col};font-size:0.85rem;font-weight:700;
                   padding:3px 10px;border-radius:6px'>{strategy_lbl} ${strike:g} · {kontrakts}x</span>
      <span style='color:{_tsub};font-size:0.82rem'>{sektor}</span>
      {_ibkr_html}
    </div>
    <span style='background:{empf_col};color:#fff;font-size:0.9rem;font-weight:700;
                 padding:5px 16px;border-radius:20px;white-space:nowrap'>{empf}</span>
  </div>

  <div style='display:flex;justify-content:space-between;font-size:0.78rem;color:{_tsub};margin-bottom:5px'>
    <span>⏳ Restlaufzeit</span>
    <span style='font-weight:700;color:{_tmain}'>{dte_icon} noch {dte_v} Tage · 🏁 Verfall {verfall_fmt}</span>
  </div>
  <div style='position:relative;height:12px;background:{_tsub}22;border-radius:6px;overflow:hidden'>
    <div style='position:absolute;left:0;top:0;height:100%;width:{_bar_pct}%;
                background:linear-gradient(90deg,{_bar_col}88,{_bar_col});border-radius:6px'></div>
  </div>

  <div style='display:flex;justify-content:space-between;font-size:0.74rem;color:{_tsub};margin:12px 0 3px'>
    <span style='font-weight:600'>Kurs ↔ Strike</span>
  </div>
  <div style='position:relative;height:14px;border-radius:7px;background:{_zone}'>
    <div style='position:absolute;left:50%;top:-2px;height:18px;width:2px;background:{_tmain};opacity:0.55'></div>
    <div style='position:absolute;left:{_ppos}%;top:-4px;width:0;height:0;
                border-left:6px solid transparent;border-right:6px solid transparent;
                border-top:9px solid {empf_col};transform:translateX(-6px)'></div>
  </div>
  <div style='display:flex;justify-content:space-between;font-size:0.82rem;color:{_tsub};
              font-weight:600;margin-top:4px'>
    <span>💵 Kurs {("$%.2f" % kurs) if kurs else "–"}</span><span>🎯 Strike ${strike:g}</span>
  </div>

  <div style='display:flex;gap:8px;margin-top:12px'>{tiles_tm}</div>

  <div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;
              gap:6px;margin-top:10px'>
    <span style='font-size:0.9rem;color:{_tmain};font-weight:600'>→ {empf}</span>
    <span style='font-size:0.78rem'>{_os_html}</span>
  </div>
  {_details_html}
  {_notiz_html}
</div>
""")

        # Verwaltung an der Karte — Position aus der Liste entfernen
        with st.popover(f"⚙️ {ticker} verwalten"):
            if st.button("🗑️ Position löschen", key=f"del_{i}_{ticker}",
                         use_container_width=True):
                st.session_state.tm_positions = positions.drop(index=_).reset_index(drop=True)
                if i in st.session_state.tm_results:
                    del st.session_state.tm_results[i]
                st.rerun()

    # ── Gesamt-Übersicht ───────────────────────────────────────────────────────
    if results and len(results) > 1:
        st.markdown("---")
        st.markdown("**📋 Übersicht aller Positionen:**")
        summary_rows = []
        for i, (_, pos) in enumerate(positions.iterrows()):
            ev = results.get(i, {})
            if not isinstance(ev, dict):
                continue
            verfall_val = pos.get("Verfall")
            if hasattr(verfall_val, "strftime"):
                verfall_str = verfall_val.strftime("%d.%m.%Y")
            else:
                verfall_str = str(verfall_val)[:10]
            summary_rows.append({
                "Ticker":     pos.get("Ticker", ""),
                "Typ":        pos.get("Typ", ""),
                "Strike":     pos.get("Strike", 0),
                "Verfall":    verfall_str,
                "DTE":        ev.get("dte"),
                "Kurs":       ev.get("kurs"),
                "P&L %":      ev.get("pnl_pct"),
                "P&L USD":    ev.get("pnl_usd"),
                "OTM %":      ev.get("otm_pct"),
                "Empfehlung": ev.get("empfehlung", "–"),
            })

        if summary_rows:
            summary_df = pd.DataFrame(summary_rows)
            st.dataframe(
                summary_df, use_container_width=True, hide_index=True,
                column_config={
                    "Strike":  st.column_config.NumberColumn("Strike", format="$%.2f"),
                    "DTE":     st.column_config.NumberColumn("DTE", format="%d T"),
                    "Kurs":    st.column_config.NumberColumn("Kurs", format="$%.2f"),
                    "P&L %":   st.column_config.NumberColumn("P&L %", format="%.1f%%"),
                    "P&L USD": st.column_config.NumberColumn("P&L USD", format="%.0f"),
                    "OTM %":   st.column_config.NumberColumn("OTM %", format="%.1f%%"),
                },
            )
