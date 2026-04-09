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


def _ibkr_flex_fetch(token: str, query_id: str, timeout: int = 30):
    """
    Ruft IBKR Flex Query per Web Service ab. Probiert alle bekannten Endpoints.
    Gibt (xml_string, error_detail, debug_info) zurück.
    """
    debug = []
    conn_errors = []

    for send_url in _IBKR_SEND_URLS:
        host = send_url.split("/")[2]
        debug.append(f"\n── Versuche {host} ──")
        try:
            url1 = f"{send_url}?t={token}&q={query_id}&v=3"
            r1 = requests.get(url1, headers=_IBKR_HEADERS, timeout=timeout)
            debug.append(f"Step1: HTTP {r1.status_code}, {len(r1.content)} bytes")

            try:
                root1 = ET.fromstring(r1.content)
            except ET.ParseError as e:
                debug.append(f"XML-Fehler: {e} | Rohdaten: {r1.text[:200]}")
                continue

            stat1 = root1.findtext("Status") or ""
            ref   = root1.findtext("ReferenceCode") or ""
            url2  = root1.findtext("Url") or _IBKR_GET_URLS.get(host, _IBKR_GET_URLS["www.interactivebrokers.com"])
            err1  = root1.findtext("ErrorMessage") or root1.findtext("Message") or ""
            debug.append(f"Status={stat1!r}  ref={ref!r}  err={err1!r}")

            if not ref:
                debug.append(f"Kein ReferenceCode → nächsten Endpoint versuchen")
                debug.append(f"Rohdaten: {r1.text[:400]}")
                conn_errors.append(f"{host}: Status='{stat1}', Fehler='{err1}'")
                continue

            # ── Step 2: Pollen ────────────────────────────────────────────────
            # URL2 auf funktionierenden Host umleiten
            for old_h in ["gdcdyn.interactivebrokers.com", "www.interactivebrokers.com", "www.interactivebrokers.eu"]:
                if old_h in url2 and old_h != host:
                    url2 = url2.replace(old_h, host)
            debug.append(f"Polling-URL: {url2}")

            for attempt in range(10):
                time.sleep(3)
                r2 = requests.get(f"{url2}?q={ref}&t={token}&v=3",
                                  headers=_IBKR_HEADERS, timeout=timeout)
                size = len(r2.content)
                debug.append(f"Poll {attempt+1}: HTTP {r2.status_code}, {size} bytes")

                # Großer Response (>10 KB) = Flex-Report-Daten, kein Status-Wrapper
                if size > 10000:
                    debug.append(f"  → Flex-Report empfangen ({size} bytes)")
                    return r2.text, None, "\n".join(debug)

                try:
                    root2 = ET.fromstring(r2.content)
                except ET.ParseError:
                    if size > 500:
                        return r2.text, None, "\n".join(debug)
                    continue

                st2  = root2.findtext("Status") or ""
                err2 = root2.findtext("ErrorMessage") or root2.findtext("Message") or ""
                debug.append(f"  Status={st2!r}  err={err2!r}")

                if st2 == "Success":
                    return r2.text, None, "\n".join(debug)
                if st2 not in ("", "Processing", "Statement generation in progress"):
                    return None, f"IBKR: Status='{st2}', Meldung='{err2}'", "\n".join(debug)

            return None, "Timeout: kein Ergebnis nach 30 Sek.", "\n".join(debug)

        except (requests.exceptions.ConnectionError,
                requests.exceptions.SSLError) as e:
            debug.append(f"Verbindungsfehler: {str(e)[:120]}")
            conn_errors.append(f"{host}: {str(e)[:80]}")
            continue
        except requests.exceptions.Timeout:
            return None, f"Request-Timeout bei {host}", "\n".join(debug)
        except Exception as e:
            return None, f"{type(e).__name__}: {e}", "\n".join(debug)

    return None, (
        "Alle IBKR-Endpoints nicht erreichbar:\n" + "\n".join(conn_errors)
    ), "\n".join(debug)


def _ibkr_parse_positions(xml_str: str) -> pd.DataFrame:
    """Parst Flex Web Service XML → normalisiertes Positions-DataFrame."""
    try:
        root = ET.fromstring(xml_str)
    except Exception:
        return pd.DataFrame()

    rows: List[Dict] = []
    for pos in root.iter("OpenPosition"):
        a = pos.attrib
        if a.get("assetCategory", "") != "OPT":
            continue
        try:
            rows.append({
                "Ticker":      a.get("underlyingSymbol", a.get("symbol", "")),
                "Typ":         "PUT" if a.get("putCall", "") == "P" else "CALL",
                "Strike":      float(a.get("strike", 0)),
                "Verfall":     a.get("expiry", ""),
                "Menge":       int(float(a.get("position", 0))),
                "Prämie_Ein":  float(a.get("costBasisPrice", 0)),
                "Prämie_Akt":  float(a.get("markPrice", 0)),
                "PnL_USD":     float(a.get("fifoPnlUnrealized", 0)),
                "Notizen":     a.get("description", ""),
                "_ibkr":       True,
            })
        except Exception:
            continue

    if not rows:
        for tr in root.iter("Trade"):
            a = tr.attrib
            if a.get("assetCategory", "") != "OPT":
                continue
            try:
                rows.append({
                    "Ticker":      a.get("underlyingSymbol", a.get("symbol", "")),
                    "Typ":         "PUT" if a.get("putCall", "") == "P" else "CALL",
                    "Strike":      float(a.get("strike", 0)),
                    "Verfall":     a.get("expiry", ""),
                    "Menge":       int(float(a.get("quantity", 0))),
                    "Prämie_Ein":  float(a.get("tradePrice", 0)),
                    "Prämie_Akt":  0.0,
                    "PnL_USD":     float(a.get("fifoPnlRealized", 0)),
                    "Notizen":     a.get("description", ""),
                    "_ibkr":       True,
                })
            except Exception:
                continue

    return pd.DataFrame(rows) if rows else pd.DataFrame()


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

@st.cache_data(ttl=300, show_spinner=False)
def _get_option_price(ticker, typ, strike, verfall_str):
    """Holt aktuellen Mid-Preis der Option von yfinance."""
    try:
        stock = yf.Ticker(ticker)
        exps  = stock.options
        if not exps:
            return None
        target   = datetime.strptime(verfall_str, "%Y-%m-%d").date()
        best_exp = min(exps, key=lambda e: abs((datetime.strptime(e, "%Y-%m-%d").date() - target).days))
        chain    = stock.option_chain(best_exp)
        df       = chain.puts if typ == "PUT" else chain.calls
        if df.empty:
            return None
        row = df.iloc[(df["strike"] - strike).abs().argsort()[:1]]
        bid  = float(row["bid"].iloc[0] or 0)
        ask  = float(row["ask"].iloc[0] or 0)
        last = float(row["lastPrice"].iloc[0] or 0)
        if bid > 0 and ask > 0:
            return round((bid + ask) / 2, 2)
        return round(last, 2) if last > 0 else None
    except Exception:
        return None


@st.cache_data(ttl=300, show_spinner=False)
def evaluate_position(
    ticker,
    typ,
    strike,
    verfall_str,
    menge,
    praemie_ein,
    praemie_akt_pre=None,   # vorberechneter aktueller Preis (aus IBKR)
    pnl_usd_pre=None,       # vorberechneter P&L in USD (aus IBKR)
):
    """
    Bewertet eine einzelne Stillhalter-Position nach Strategie-Regeln.
    Wenn praemie_akt_pre/pnl_usd_pre gesetzt, werden diese direkt genutzt (IBKR-Import).
    """
    result = {
        "ticker":           ticker,
        "typ":              typ,
        "strike":           strike,
        "verfall":          verfall_str,
        "menge":            menge,
        "praemie_ein":      praemie_ein,
        "kurs":             None,
        "praemie_aktuell":  praemie_akt_pre,   # direkt aus IBKR oder via yfinance
        "dte":              None,
        "pnl_pct":          None,
        "pnl_usd":          pnl_usd_pre,       # direkt aus IBKR oder berechnet
        "otm_pct":          None,
        "trend":            None,
        "macd":             None,
        "stoch":            None,
        "earnings":         None,
        "empfehlung":       "–",
        "empfehlung_color": "#888",
        "risiko_score":     50,
        "details":          [],
    }

    kontrakte = abs(menge)
    is_short  = menge < 0

    # ── Aktueller Kurs ────────────────────────────────────────────────────────
    try:
        info = fetch_stock_info(ticker)
        kurs = info.get("price")
        if kurs:
            result["kurs"] = round(float(kurs), 2)
    except Exception:
        pass

    # ── DTE ───────────────────────────────────────────────────────────────────
    try:
        dte = calculate_dte(verfall_str)
        result["dte"] = max(0, dte)
    except Exception:
        pass

    # ── Aktueller Optionspreis (nur wenn nicht aus IBKR) ─────────────────────
    if praemie_akt_pre is None:
        try:
            p_aktuell = _get_option_price(ticker, typ, strike, verfall_str)
            result["praemie_aktuell"] = p_aktuell
        except Exception:
            pass

    # ── P&L berechnen ────────────────────────────────────────────────────────
    p_ein = praemie_ein
    p_akt = result["praemie_aktuell"]

    if pnl_usd_pre is not None:
        # IBKR liefert P&L direkt — nur % berechnen
        result["pnl_usd"] = pnl_usd_pre
        if p_ein and p_ein > 0 and kontrakte > 0:
            max_profit = p_ein * 100 * kontrakte
            result["pnl_pct"] = round(pnl_usd_pre / max_profit * 100, 1)
    elif p_ein and p_akt is not None:
        if is_short:
            pnl_per_share = p_ein - p_akt
        else:
            pnl_per_share = p_akt - p_ein
        result["pnl_pct"] = round(pnl_per_share / p_ein * 100, 1) if p_ein > 0 else None
        result["pnl_usd"] = round(pnl_per_share * 100 * kontrakte, 0)

    # ── OTM% berechnen ────────────────────────────────────────────────────────
    kurs = result["kurs"]
    if kurs and strike > 0:
        if typ == "PUT":
            otm = (kurs - strike) / kurs * 100
        else:
            otm = (strike - kurs) / kurs * 100
        result["otm_pct"] = round(otm, 1)
        # OTM in USD (absoluter Abstand)
        result["otm_usd"] = round(abs(kurs - strike), 2)

    # ── Technische Analyse ────────────────────────────────────────────────────
    try:
        hist = fetch_price_history(ticker, period="6mo")
        if hist is not None and not hist.empty:
            tech = analyze_technicals(hist)
            if tech:
                result["trend"] = tech.trend
                result["macd"]  = tech.sc_macd.signal_strength if tech.sc_macd else None
                result["stoch"] = tech.dual_stoch.signal_strength if tech.dual_stoch else None
                if tech.support_levels and kurs:
                    below = [s for s in tech.support_levels if s < kurs]
                    if below:
                        result["nearest_support"] = max(below)
    except Exception:
        pass

    # ── Earnings ──────────────────────────────────────────────────────────────
    try:
        earn_str = fetch_earnings_date(ticker)
        if earn_str:
            earn_dte = calculate_dte(earn_str)
            dte_val  = result["dte"] or 999
            if 0 <= earn_dte <= dte_val:
                result["earnings"] = earn_str
    except Exception:
        pass

    # ── Empfehlung erzeugen ───────────────────────────────────────────────────
    details     = []
    risk_points = 0

    dte_val = result["dte"]
    pnl_pct = result["pnl_pct"]
    pnl_usd = result["pnl_usd"]
    otm_pct = result["otm_pct"]
    otm_usd = result.get("otm_usd")
    trend   = result["trend"]
    macd    = result["macd"]

    # ══════════════════════════════════════════════════════════════════════════
    # LONG POSITIONEN — vollständig separate Logik
    # (gekaufte Optionen: Schutzpositionen, Spread-Legs, spekulative Longs)
    # ══════════════════════════════════════════════════════════════════════════
    if not is_short:
        result["is_long"] = True

        # Info-Label
        details.append(("📋", f"Long {typ} — gekaufte Option (Absicherung oder Spread-Leg)"))

        # DTE für Long: OTM + verfallend = GUT (Schutz war nicht nötig)
        if dte_val is not None:
            if dte_val <= 0:
                details.append(("📋", "Option abgelaufen — Prämie verfallen (einkalkulierte Absicherungskosten)"))
            elif dte_val <= 14:
                if otm_pct is not None and otm_pct >= 5:
                    details.append(("✅", f"Noch {dte_val} Tage bis Verfall — Option OTM: verfällt planmäßig wertlos (Schutz war nicht nötig)"))
                elif otm_pct is not None and otm_pct < 0:
                    details.append(("💰", f"Noch {dte_val} Tage bis Verfall — Option ITM: Schutz greift! Inneren Wert sichern."))
                else:
                    details.append(("🕐", f"Noch {dte_val} Tage bis Verfall — nahe am Strike: Entwicklung beobachten"))
            else:
                details.append(("✅", f"{dte_val} Tage bis Verfall — ausreichend Zeit"))

        # P&L für Long: Verlust bei OTM-Verfall ist NORMAL/ERWARTET
        if pnl_pct is not None:
            pnl_usd_str = f" ({'+' if (pnl_usd or 0) >= 0 else ''}{pnl_usd:.0f} USD)" if pnl_usd is not None else ""
            if pnl_pct >= 50:
                details.append(("💰", f"Option im Plus +{pnl_pct:.0f}%{pnl_usd_str} — Gewinnmitnahme möglich"))
            elif pnl_pct >= 0:
                details.append(("✅", f"Option leicht im Plus +{pnl_pct:.0f}%{pnl_usd_str}"))
            elif pnl_pct >= -60:
                if otm_pct is not None and otm_pct >= 5:
                    details.append(("✅", f"Absicherungskosten {pnl_pct:.0f}%{pnl_usd_str} — erwartet bei OTM-Option (Schutz nicht benötigt)"))
                else:
                    details.append(("🟡", f"Option {pnl_pct:.0f}%{pnl_usd_str} — normaler Zeitwertverlust"))
            else:
                details.append(("⚠️", f"Hohe Absicherungskosten {pnl_pct:.0f}%{pnl_usd_str} — Strategie prüfen"))

        # OTM für Long: ITM = gut (Schutz greift)
        if otm_pct is not None:
            otm_usd_str = f" ({otm_usd:.2f} USD Abstand)" if otm_usd else ""
            if otm_pct < 0:
                details.append(("🛡️", f"Option ITM {abs(otm_pct):.1f}%{otm_usd_str} — Schutzstellung greift!"))
            elif otm_pct < 5:
                details.append(("🕐", f"Option nahe am Strike ({otm_pct:.1f}% OTM){otm_usd_str} — beobachten"))
            else:
                details.append(("✅", f"Option {otm_pct:.1f}% OTM{otm_usd_str} — verfällt voraussichtlich wertlos"))

        # Trend für Long: bearish ist GUT für Long PUT (umgekehrte Logik)
        if trend:
            if typ == "PUT":
                if trend == "bearish":
                    details.append(("✅", "Trend bearisch — vorteilhaft für Long PUT (Schutz wächst im Wert)"))
                elif trend == "bullish":
                    details.append(("📋", "Trend bullisch — Long PUT verliert an Wert (Schutz nicht benötigt, planmäßig)"))
                else:
                    details.append(("🟡", "Trend seitwärts — neutral für Long PUT"))
            else:  # CALL
                if trend == "bullish":
                    details.append(("✅", "Trend bullisch — vorteilhaft für Long CALL"))
                elif trend == "bearish":
                    details.append(("📋", "Trend bearisch — Long CALL verliert an Wert"))

        # MACD für Long
        if macd:
            macd_long_map = {
                "strong_bull": ("✅", "SC MACD Pro stark bullisch") if typ == "CALL" else ("📋", "SC MACD Pro stark bullisch — Long PUT verliert Wert"),
                "bull":        ("✅", "SC MACD Pro bullisch") if typ == "CALL" else ("📋", "SC MACD Pro bullisch"),
                "neutral":     ("🟡", "SC MACD Pro neutral"),
                "bear":        ("✅", "SC MACD Pro bearisch — Long PUT gewinnt Wert") if typ == "PUT" else ("📋", "SC MACD Pro bearisch"),
                "strong_bear": ("✅", "SC MACD Pro stark bearisch — Long PUT greift") if typ == "PUT" else ("📋", "SC MACD Pro stark bearisch"),
            }
            if macd in macd_long_map:
                details.append(macd_long_map[macd])

        # Earnings
        if result["earnings"]:
            details.append(("ℹ️", f"Earnings innerhalb Laufzeit: {result['earnings']} → IV-Anstieg begünstigt Long-Option"))

        # Kein Roll für Long OTM Positionen
        # Gesamtempfehlung für Long
        result["risiko_score"] = 0
        result["details"] = details

        if dte_val is not None and dte_val <= 0:
            result["empfehlung"]       = "📋 Abgelaufen (Kosten einkalkuliert)"
            result["empfehlung_color"] = "#888"
        elif otm_pct is not None and otm_pct < 0:
            result["empfehlung"]       = "🛡️ Schutz greift (ITM)"
            result["empfehlung_color"] = "#60a5fa"
        elif pnl_pct is not None and pnl_pct >= 50:
            result["empfehlung"]       = "💰 Gewinnmitnahme"
            result["empfehlung_color"] = "#22c55e"
        elif otm_pct is not None and otm_pct >= 5 and dte_val is not None and dte_val <= 14:
            result["empfehlung"]       = "✅ Schutz läuft planmäßig aus"
            result["empfehlung_color"] = "#22c55e"
        else:
            result["empfehlung"]       = "📋 Halten (Absicherung)"
            result["empfehlung_color"] = "#888"

        return result

    # ══════════════════════════════════════════════════════════════════════════
    # SHORT POSITIONEN — Stillhalter-Logik
    # Klares Statusmodell: Halten / Schließen / Rollen / Einbuchen / Abgelaufen
    # ══════════════════════════════════════════════════════════════════════════

    # ── ATH (52-Wochen-Hoch als Proxy für "günstige Einbuchung") ─────────────
    ath = None
    try:
        info = fetch_stock_info(ticker)
        ath  = info.get("week52High") or info.get("fiftyTwoWeekHigh")
        if ath:
            ath = float(ath)
            result["ath"] = ath
    except Exception:
        pass

    # ── Theta-Verlauf: Ist der Zeitwertverfall im Plan? ──────────────────────
    # Modell: Theta ist konvex (beschleunigt zur Laufzeit-Ende)
    # Approximation: verbleibender Wert ∝ sqrt(DTE_rest / DTE_gesamt)
    # Annahme: typischer Einstieg bei 45 DTE
    theta_status    = "unbekannt"
    expected_pnl    = None
    theta_label     = ""
    assumed_dte_ein = 45   # typischer Einstieg

    if dte_val is not None and praemie_ein > 0 and pnl_pct is not None:
        total_dte = max(assumed_dte_ein, dte_val + 5)  # mindestens 5 Tage Laufzeit vergangen
        elapsed_frac = max(0.0, (total_dte - dte_val) / total_dte)
        expected_pnl = round((1 - math.sqrt(max(0, 1 - elapsed_frac))) * 100, 1)

        if pnl_pct >= expected_pnl * 1.25:
            theta_status = "schnell"
            theta_label  = f"Zeitwert verfällt schneller als erwartet (+{pnl_pct:.0f}% vs. erwartet {expected_pnl:.0f}%) — günstige Entwicklung"
        elif pnl_pct <= expected_pnl * 0.65:
            theta_status = "langsam"
            theta_label  = f"Zeitwert verfällt langsamer als erwartet ({pnl_pct:.0f}% vs. erwartet {expected_pnl:.0f}%) — IV oder Kurs wirkt gegen die Position"
        else:
            theta_status = "planmäßig"
            theta_label  = f"Zeitwert verfällt planmäßig ({pnl_pct:.0f}% vereinnahmt, erwartet ~{expected_pnl:.0f}%) — Position im Rahmen"

    result["theta_status"] = theta_status
    result["expected_pnl"] = expected_pnl

    # ── Details aufbauen (maximal 5 klare Punkte) ────────────────────────────
    pnl_usd_str = f" ({'+' if (pnl_usd or 0) >= 0 else ''}{pnl_usd:.0f} USD)" if pnl_usd is not None else ""

    # 1. Theta-Verlauf (wichtigster Indikator)
    if theta_label:
        theta_icon = "✅" if theta_status == "schnell" else ("⚠️" if theta_status == "langsam" else "🟡")
        details.append((theta_icon, theta_label))

    # 2. OTM-Abstand (Sicherheitszone)
    if otm_pct is not None:
        otm_usd_str = f" ({otm_usd:.2f} USD Abstand)" if otm_usd else ""
        if otm_pct >= 15:
            details.append(("✅", f"{otm_pct:.1f}% OTM{otm_usd_str} — sicherer Puffer"))
        elif otm_pct >= 8:
            details.append(("🟡", f"{otm_pct:.1f}% OTM{otm_usd_str} — Puffer vorhanden, beobachten"))
        elif otm_pct >= 3:
            details.append(("⚠️", f"Nur {otm_pct:.1f}% OTM{otm_usd_str} — Strike in Reichweite! Delta ist gestiegen."))
        elif otm_pct >= 0:
            details.append(("🔴", f"Sehr nah am Geld ({otm_pct:.1f}% OTM){otm_usd_str} — Entscheidung nötig: Rollen oder Einbuchen"))
        else:
            details.append(("🔴", f"Im Geld ({abs(otm_pct):.1f}% ITM){otm_usd_str} — Einbuchung droht"))

    # 3. Trend — kurz und relevant
    if trend:
        if typ == "PUT":
            if trend == "bullish":
                details.append(("✅", "Trend bullisch — Aktie bewegt sich vom Strike weg"))
            elif trend == "bearish":
                details.append(("⚠️", "Trend bearisch — Aktie bewegt sich Richtung Strike"))
        else:
            if trend == "bearish":
                details.append(("✅", "Trend bearisch — Aktie bewegt sich vom Strike weg"))
            elif trend == "bullish":
                details.append(("⚠️", "Trend bullisch — Aktie bewegt sich Richtung Strike"))

    # 4. Earnings-Warnung
    if result["earnings"]:
        details.append(("⚠️", f"Earnings {result['earnings']} innerhalb der Laufzeit — IV-Anstieg kann Option verteuern"))

    # 5. Einbuchungs-Analyse (wenn nahe am Geld oder ITM)
    if ath and kurs and (otm_pct is not None and otm_pct < 10):
        pct_below_ath = round((ath - strike) / ath * 100, 1)
        if typ == "PUT":
            if pct_below_ath >= 40:
                details.append((
                    "📦",
                    f"Strike @{strike:.0f} liegt {pct_below_ath:.0f}% unter dem 52-Wochen-Hoch ({ath:.2f}) — "
                    f"Einbuchung zu einem stark vergünstigten Kurs attraktiv."
                ))
            elif pct_below_ath >= 20:
                details.append((
                    "📦",
                    f"Strike @{strike:.0f} liegt {pct_below_ath:.0f}% unter dem 52-Wochen-Hoch ({ath:.2f}) — "
                    f"Einbuchung möglicherweise akzeptabel (Aktie kaufen zu Rabattpreis)."
                ))
            else:
                details.append((
                    "🔄",
                    f"Strike @{strike:.0f} nur {pct_below_ath:.0f}% unter 52W-Hoch ({ath:.2f}) — "
                    f"Einbuchung wenig attraktiv → Rollen bevorzugen."
                ))

    # ── Roll-Angabe bei Bedarf ────────────────────────────────────────────────
    if otm_pct is not None and otm_pct < 5 and dte_val is not None and 0 < dte_val <= 21:
        target_dte = (dte_val or 0) + 35
        if otm_pct < 0:
            new_strike = round(strike * (0.90 if typ == "PUT" else 1.10) / 5) * 5
            details.append((
                "🔄",
                f"Roll-Option: {typ} von @{strike:.0f} auf @{new_strike:.0f} "
                f"({'−10%' if typ=='PUT' else '+10%'}) und ~{target_dte} Tage Laufzeit — "
                f"nur wenn Netto-Kredit positiv (Einnahme > Ausgabe)."
            ))
        else:
            details.append((
                "🔄",
                f"Roll-Option: {typ} @{strike:.0f} gleicher Strike auf ~{target_dte} Tage weiter rollen — "
                f"mehr Zeit kaufen, zusätzliche Prämie einsammeln."
            ))

    # ── Gesamtempfehlung — 5 klare Status, keine Überschneidung ─────────────
    result["risiko_score"] = 0   # nicht mehr verwendet, aber Feld bleibt kompatibel
    result["details"]      = details

    # STATUS-LOGIK (Priorität von oben nach unten):
    if dte_val is not None and dte_val <= 0:
        # Abgelaufen — kein Handlungsbedarf mehr, Status nur informativ
        if otm_pct is not None and otm_pct >= 0:
            result["empfehlung"]       = "📋 Abgelaufen · wertlos verfallen"
            result["empfehlung_color"] = "#22c55e"
        else:
            result["empfehlung"]       = "📋 Abgelaufen · Eingebucht (bitte anpassen)"
            result["empfehlung_color"] = "#60a5fa"

    elif otm_pct is not None and otm_pct < 0:
        # ITM — erst bei kurzer Restlaufzeit handeln, sonst Gegenbewegung abwarten
        if dte_val is not None and dte_val > 21:
            result["empfehlung"]       = "👀 ITM — Gegenbewegung abwarten"
            result["empfehlung_color"] = "#f59e0b"
        elif ath and typ == "PUT":
            pct_below = (ath - strike) / ath * 100
            if pct_below >= 30:
                result["empfehlung"]       = "📦 Einbuchen prüfen (attraktiver Kurs)"
                result["empfehlung_color"] = "#60a5fa"
            else:
                result["empfehlung"]       = "🔄 Rollen oder Einbuchen"
                result["empfehlung_color"] = "#f97316"
        else:
            result["empfehlung"]       = "🔄 Rollen oder Einbuchen"
            result["empfehlung_color"] = "#f97316"

    elif otm_pct is not None and otm_pct < 5:
        # Sehr nah am Geld — Alarm
        result["empfehlung"]       = "⚠️ Am Geld — Entscheidung nötig"
        result["empfehlung_color"] = "#f59e0b"

    elif pnl_pct is not None and pnl_pct >= 70:
        # 70%-Ziel erreicht
        result["empfehlung"]       = "💰 70%-Ziel erreicht — schließen"
        result["empfehlung_color"] = "#22c55e"

    elif pnl_pct is not None and pnl_pct >= 50 and theta_status == "schnell":
        # Überdurchschnittlicher Zerfall — frühzeitig schließen lohnt
        result["empfehlung"]       = "💰 Schneller Zerfall — Schließen prüfen"
        result["empfehlung_color"] = "#22c55e"

    elif otm_pct is not None and otm_pct < 8:
        # Puffer wird kleiner — beobachten
        result["empfehlung"]       = "👀 OTM-Abstand gering — beobachten"
        result["empfehlung_color"] = "#f59e0b"

    elif theta_status == "langsam" and (pnl_pct or 0) < 0:
        # Zeitwert läuft langsam UND im Minus — aktiv beobachten
        result["empfehlung"]       = "👀 Unter Plan — beobachten"
        result["empfehlung_color"] = "#60a5fa"

    else:
        result["empfehlung"]       = "✅ Läuft nach Plan"
        result["empfehlung_color"] = "#22c55e"

    return result


# ══════════════════════════════════════════════════════════════════════════════
# SEITE
# ══════════════════════════════════════════════════════════════════════════════

# Header
col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.html(get_logo_html("white", 40))
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
        with st.spinner("Verbinde mit IBKR… (US → EU → CDN, bis zu 30 Sek.)"):
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

        # Expander-Icon: Long OTM near expiry = ✅, sonst nach Risiko
        if is_long and (otm_pct or 0) >= 5 and dte is not None and dte <= 14:
            exp_icon = "✅"
        elif is_long and (otm_pct or 0) < 0:
            exp_icon = "🛡️"
        elif dte is not None and dte <= 1 and not is_long:
            exp_icon = "🚨"
        elif risiko > 45:
            exp_icon = "⚠️"
        elif risiko <= 15:
            exp_icon = "✅"
        else:
            exp_icon = "🔵"

        with st.expander(
            f"{exp_icon} **{ticker}** {strategy_lbl} @{strike:.0f} | Verfall {verfall_fmt} "
            f"({dte_icon} {dte}T) | {empf}",
            expanded=(dte is not None and dte <= 2) or (risiko > 45 and not results)
        ):
            pc1, pc2, pc3 = st.columns([2, 2, 3])

            with pc1:
                st.html(f"""
<div style='background:#111;border:1px solid #1e1e1e;border-radius:10px;
            padding:14px;border-top:3px solid {empf_col}'>
    <div style='font-size:1.1rem;font-weight:700;color:#f0f0f0;
                font-family:sans-serif;margin-bottom:4px'>
        {ticker} &nbsp;
        <span style='font-size:0.78rem;color:#555;font-weight:400'>{sektor}</span>
    </div>
    <div style='font-size:0.82rem;color:#888;font-family:sans-serif;
                margin-bottom:12px'>{strategy_lbl} · {kontrakts}x Kontrakt</div>
    <div style='display:grid;grid-template-columns:1fr 1fr;gap:6px'>
        <div style='background:#0e0e0e;border-radius:6px;padding:6px 10px'>
            <div style='font-size:0.62rem;color:#555;font-family:sans-serif'>Kurs aktuell</div>
            <div style='font-size:1rem;font-weight:600;color:#e0e0e0;font-family:sans-serif'>
                {'USD ' + str(kurs) if kurs else '–'}</div>
        </div>
        <div style='background:#0e0e0e;border-radius:6px;padding:6px 10px'>
            <div style='font-size:0.62rem;color:#555;font-family:sans-serif'>Strike</div>
            <div style='font-size:1rem;font-weight:600;color:#e0e0e0;font-family:sans-serif'>
                USD {strike:.2f}</div>
        </div>
        <div style='background:#0e1a12;border-radius:6px;padding:6px 10px'>
            <div style='font-size:0.62rem;color:#555;font-family:sans-serif'>📅 Verfall</div>
            <div style='font-size:0.95rem;font-weight:700;color:#d4a843;font-family:sans-serif'>
                {verfall_fmt}</div>
        </div>
        <div style='background:#0e1a12;border-radius:6px;padding:6px 10px'>
            <div style='font-size:0.62rem;color:#555;font-family:sans-serif'>Restlaufzeit</div>
            <div style='font-size:1.3rem;font-weight:900;color:{dte_color};font-family:sans-serif'>
                {dte_icon} {dte if dte is not None else '–'}
                <span style='font-size:0.7rem;font-weight:400;color:#888'> T</span>
            </div>
        </div>
    </div>
    {"<div style='margin-top:8px;background:#0e0e0e;border-radius:6px;padding:6px 10px;font-size:0.78rem;color:#555;font-family:sans-serif'>" + notiz + "</div>" if notiz else ""}
</div>
""")

            with pc2:
                ibkr_hinweis = (
                    "<div style='font-size:0.62rem;color:#60a5fa;font-family:sans-serif;margin-bottom:6px'>"
                    "⬡ Daten direkt aus IBKR Import</div>"
                    if is_ibkr else ""
                )
                st.html(f"""
<div style='background:#111;border:1px solid #1e1e1e;border-radius:10px;
            padding:14px;height:100%'>
    {ibkr_hinweis}
    <div style='margin-bottom:10px'>
        <div style='font-size:0.65rem;color:#555;text-transform:uppercase;
                    letter-spacing:0.06em;font-family:sans-serif;margin-bottom:4px'>Prämie</div>
        <div style='display:flex;justify-content:space-between'>
            <span style='font-size:0.75rem;color:#666;font-family:sans-serif'>Einstieg</span>
            <span style='font-size:0.9rem;font-weight:600;color:#ccc;font-family:sans-serif'>
                {p_ein:.2f} USD</span>
        </div>
        <div style='display:flex;justify-content:space-between'>
            <span style='font-size:0.75rem;color:#666;font-family:sans-serif'>Aktuell</span>
            <span style='font-size:0.9rem;font-weight:600;color:#ccc;font-family:sans-serif'>
                {'%.2f USD' % p_akt if p_akt is not None else '–'}</span>
        </div>
        {intrinsic_str}{zeitwert_row}
    </div>
    <div style='background:{pnl_bg};border:1px solid {pnl_border};border-radius:8px;
                padding:8px 12px;margin-bottom:10px'>
        <div style='font-size:0.65rem;color:#555;text-transform:uppercase;
                    letter-spacing:0.06em;font-family:sans-serif;margin-bottom:4px'>
            {pnl_label}</div>
        <div style='font-size:1.6rem;font-weight:900;color:{pnl_color};
                    font-family:sans-serif;line-height:1.1'>{pnl_str}</div>
        <div style='font-size:0.82rem;color:{pnl_color};font-family:sans-serif'>
            {pnl_usd_str}
            {'(' + str(kontrakts) + 'x Kontrakt)' if kontrakts > 1 else '(1 Kontrakt)'}</div>
    </div>
    <div style='display:flex;justify-content:space-between;align-items:center;
                background:#0e0e0e;border-radius:6px;padding:6px 12px'>
        <span style='font-size:0.72rem;color:#555;font-family:sans-serif'>OTM-Abstand</span>
        <span style='font-size:0.95rem;font-weight:700;color:{otm_color};font-family:sans-serif'>
            {'%.1f%%' % otm_pct if otm_pct is not None else '–'}
            {'&nbsp;✅' if (otm_pct or 0) >= 10 else ('&nbsp;⚠️' if (otm_pct or 0) >= 0 else '&nbsp;🔴')}
        </span>
    </div>
    <div style='margin-top:10px;background:#0c0c0c;border:2px solid {empf_col};
                border-radius:8px;padding:10px 14px;text-align:center'>
        <div style='font-size:0.65rem;color:#555;text-transform:uppercase;
                    letter-spacing:0.06em;font-family:sans-serif;margin-bottom:3px'>
            Empfehlung</div>
        <div style='font-size:1.05rem;font-weight:700;color:{empf_col};font-family:sans-serif'>
            {empf}</div>
    </div>
</div>
""")

            with pc3:
                if details:
                    detail_html = "".join(
                        f"<div style='display:flex;gap:8px;align-items:flex-start;"
                        f"padding:5px 0;border-bottom:1px solid #1a1a1a;font-family:sans-serif'>"
                        f"<span style='font-size:1rem;flex-shrink:0'>{icon}</span>"
                        f"<span style='font-size:0.78rem;color:#aaa;line-height:1.4'>{text}</span>"
                        f"</div>"
                        for icon, text in details
                    )
                    st.html(f"""
<div style='background:#111;border:1px solid #1e1e1e;border-radius:10px;padding:14px'>
    <div style='font-size:0.65rem;color:#555;text-transform:uppercase;
                letter-spacing:0.06em;font-family:sans-serif;margin-bottom:8px'>
        🔍 Analyse-Details &amp; Handlungsempfehlungen
    </div>
    {detail_html}
</div>
""")
                elif results:
                    st.markdown("*Keine Details verfügbar*")
                else:
                    st.markdown("*Position noch nicht bewertet — klicke 'Alle Positionen bewerten'*")

            del_col, _ = st.columns([1, 5])
            with del_col:
                if st.button(f"🗑️ Position löschen", key=f"del_{i}_{ticker}",
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
