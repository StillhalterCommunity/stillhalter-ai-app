"""
IBKR Flex Web Service — zentrales Modul (aus Seite 7 extrahiert, erweitert).

fetch_flex(token, query_id)      → (xml_string, error, debug)
parse_option_positions(xml)      → DataFrame (Ticker/Typ/Strike/Verfall/… — Seite 7)
parse_all_positions(xml)         → DataFrame ALLER Positionen (Dashboard)
parse_account_summary(xml)       → dict (nlv, cash, base_currency, report_date)
parse_option_trades(xml)         → DataFrame der Options-Trades (Cashflow)
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Dict, List

import pandas as pd
import requests

IBKR_SEND_URLS = [
    "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest",
    "https://www.interactivebrokers.eu/Universal/servlet/FlexStatementService.SendRequest",
    "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest",
]
IBKR_GET_URLS = {
    "www.interactivebrokers.com":    "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement",
    "www.interactivebrokers.eu":     "https://www.interactivebrokers.eu/Universal/servlet/FlexStatementService.GetStatement",
    "gdcdyn.interactivebrokers.com": "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement",
}
IBKR_HEADERS = {"User-Agent": "Mozilla/5.0"}
_RATE_LIMIT_CODES = {"1018"}
_TRANSIENT_CODES  = {"1019", "1021"}


def fetch_flex(token: str, query_id: str, timeout: int = 30):
    """Ruft die IBKR Flex Query ab. Probiert alle bekannten Endpoints.
    Gibt (xml_string, error_detail, debug_info) zurück."""
    debug: List[str] = []
    conn_errors: List[str] = []

    for i, send_url in enumerate(IBKR_SEND_URLS):
        host = send_url.split("/")[2]
        if i > 0:
            time.sleep(5)
        debug.append(f"\n── Versuche {host} ──")
        try:
            url1 = f"{send_url}?t={token}&q={query_id}&v=3"
            r1 = requests.get(url1, headers=IBKR_HEADERS, timeout=timeout)
            debug.append(f"Step1: HTTP {r1.status_code}, {len(r1.content)} bytes")

            try:
                root1 = ET.fromstring(r1.content)
            except ET.ParseError as e:
                debug.append(f"XML-Fehler: {e} | Rohdaten: {r1.text[:200]}")
                continue

            stat1    = root1.findtext("Status") or ""
            ref      = root1.findtext("ReferenceCode") or ""
            url2     = root1.findtext("Url") or IBKR_GET_URLS.get(host, IBKR_GET_URLS["www.interactivebrokers.com"])
            err1     = root1.findtext("ErrorMessage") or root1.findtext("Message") or ""
            err_code = root1.findtext("ErrorCode") or ""
            debug.append(f"Status={stat1!r}  ref={ref!r}  err={err1!r}")

            if not ref:
                debug.append("Kein ReferenceCode → nächsten Endpoint versuchen")
                conn_errors.append(f"{host}: Status='{stat1}', Fehler='{err1}'")
                if err_code in _RATE_LIMIT_CODES:
                    return None, (
                        f"⏱️ IBKR Rate Limit (Code {err_code}): Zu viele Anfragen mit diesem Token.\n"
                        "Bitte **5–10 Minuten warten** und dann erneut versuchen."
                    ), "\n".join(debug)
                if err_code in _TRANSIENT_CODES:
                    time.sleep(10)
                continue

            for old_h in ["gdcdyn.interactivebrokers.com", "www.interactivebrokers.com",
                          "www.interactivebrokers.eu"]:
                if old_h in url2 and old_h != host:
                    url2 = url2.replace(old_h, host)
            debug.append(f"Polling-URL: {url2}")

            for attempt in range(10):
                time.sleep(3)
                r2 = requests.get(f"{url2}?q={ref}&t={token}&v=3",
                                  headers=IBKR_HEADERS, timeout=timeout)
                size = len(r2.content)
                debug.append(f"Poll {attempt+1}: HTTP {r2.status_code}, {size} bytes")
                if size > 10000:
                    return r2.text, None, "\n".join(debug)
                try:
                    root2 = ET.fromstring(r2.content)
                except ET.ParseError:
                    if size > 500:
                        return r2.text, None, "\n".join(debug)
                    continue
                st2  = root2.findtext("Status") or ""
                err2 = root2.findtext("ErrorMessage") or root2.findtext("Message") or ""
                if st2 == "Success":
                    return r2.text, None, "\n".join(debug)
                if st2 not in ("", "Processing", "Statement generation in progress"):
                    return None, f"IBKR: Status='{st2}', Meldung='{err2}'", "\n".join(debug)

            return None, "Timeout: kein Ergebnis nach 30 Sek.", "\n".join(debug)

        except (requests.exceptions.ConnectionError, requests.exceptions.SSLError) as e:
            debug.append(f"Verbindungsfehler: {str(e)[:120]}")
            conn_errors.append(f"{host}: {str(e)[:80]}")
            continue
        except requests.exceptions.Timeout:
            return None, f"Request-Timeout bei {host}", "\n".join(debug)
        except Exception as e:
            return None, f"{type(e).__name__}: {e}", "\n".join(debug)

    return None, ("Alle IBKR-Endpoints nicht erreichbar:\n" + "\n".join(conn_errors)), "\n".join(debug)


def parse_option_positions(xml_str: str) -> pd.DataFrame:
    """Nur OPTIONS-Positionen (Format der Seite 7 / Trade Management)."""
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


def parse_all_positions(xml_str: str) -> pd.DataFrame:
    """ALLE Positionen (Aktien/ETF/Optionen) fürs Depot-Dashboard."""
    try:
        root = ET.fromstring(xml_str)
    except Exception:
        return pd.DataFrame()

    rows: List[Dict] = []
    for pos in root.iter("OpenPosition"):
        a = pos.attrib
        try:
            cat   = a.get("assetCategory", "")
            qty   = float(a.get("position", 0))
            mark  = float(a.get("markPrice", 0))
            mult  = float(a.get("multiplier", 1) or 1)
            value = qty * mark * mult
            put_call = a.get("putCall", "")
            if cat == "OPT":
                typ = ("Short Put" if (put_call == "P" and qty < 0) else
                       "Short Call" if (put_call == "C" and qty < 0) else
                       "Long Put" if put_call == "P" else "Long Call")
            elif cat in ("STK", "ETF"):
                typ = "Aktie/ETF Long" if qty >= 0 else "Aktie Short"
            else:
                typ = cat or "Sonstiges"
            rows.append({
                "symbol":     a.get("underlyingSymbol") or a.get("symbol", ""),
                "raw_symbol": a.get("symbol", ""),
                "category":   cat,
                "typ":        typ,
                "qty":        qty,
                "mark":       mark,
                "value":      value,
                "pnl":        float(a.get("fifoPnlUnrealized", 0) or 0),
                "strike":     float(a.get("strike", 0) or 0),
                "expiry":     a.get("expiry", ""),
                "put_call":   put_call,
            })
        except Exception:
            continue
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def parse_account_summary(xml_str: str) -> dict:
    """NLV/Cash aus EquitySummaryInBase bzw. CashReport (falls die Flex Query
    diese Sektionen enthält). Fehlt beides → leeres Dict."""
    out: dict = {}
    try:
        root = ET.fromstring(xml_str)
    except Exception:
        return out
    # Letzte EquitySummary-Zeile = aktuellster Report-Tag
    eq_rows = list(root.iter("EquitySummaryByReportDateInBase"))
    if eq_rows:
        a = eq_rows[-1].attrib
        try:
            out["nlv"] = float(a.get("total", 0) or 0)
            out["cash"] = float(a.get("cash", 0) or 0)
            out["report_date"] = a.get("reportDate", "")
        except Exception:
            pass
    if "cash" not in out:
        for c in root.iter("CashReportCurrency"):
            a = c.attrib
            if a.get("currency", "") in ("BASE_SUMMARY", ""):
                try:
                    out["cash"] = float(a.get("endingCash", 0) or 0)
                except Exception:
                    pass
    for st_ in root.iter("FlexStatement"):
        out.setdefault("report_date", st_.attrib.get("toDate", ""))
        out["base_currency"] = st_.attrib.get("currency", "") or out.get("base_currency", "")
        break
    return out


def parse_option_trades(xml_str: str) -> pd.DataFrame:
    """Options-Trades des Report-Zeitraums (für Options-Cashflow)."""
    try:
        root = ET.fromstring(xml_str)
    except Exception:
        return pd.DataFrame()
    rows: List[Dict] = []
    for tr in root.iter("Trade"):
        a = tr.attrib
        if a.get("assetCategory", "") != "OPT":
            continue
        try:
            rows.append({
                "symbol":   a.get("underlyingSymbol") or a.get("symbol", ""),
                "datum":    a.get("tradeDate", ""),
                "qty":      float(a.get("quantity", 0)),
                "proceeds": float(a.get("proceeds", 0) or 0),
                "put_call": a.get("putCall", ""),
            })
        except Exception:
            continue
    return pd.DataFrame(rows) if rows else pd.DataFrame()
