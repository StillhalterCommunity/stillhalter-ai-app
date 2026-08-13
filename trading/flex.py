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
# Endgueltige Fehler: weitere Versuche/Endpoint-Wechsel sind zwecklos
_TOKEN_CODES = {"1012": "abgelaufen", "1015": "ungültig", "1016": "deaktiviert"}
_QUERY_CODES = {"1020", "1003"}
# Wartezeiten Step 1 ('Statement could not be generated'): ~2 Min Gesamtbudget
_S1_DELAYS = (0, 15, 30, 60)
# Wartezeiten Polling (GetStatement, 'generation in progress'): ~110 s
_POLL_DELAYS = (3, 3, 5, 5, 8, 8, 13, 13, 21, 21)


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
            ref = ""
            stat1 = ""
            err1 = ""
            err_code = ""
            url2 = IBKR_GET_URLS.get(host, IBKR_GET_URLS["www.interactivebrokers.com"])
            parse_fail = False

            # 'Statement could not be generated at this time' ist ein
            # VORÜBERGEHENDER Fehler auf Statement-Ebene: Endpoint-Wechsel
            # hilft nicht und verbrennt nur das Token-Rate-Limit (Code 1018).
            # → gleichen Endpoint mit wachsender Wartezeit wiederholen
            #   (IBKR braucht dafür oft 1-3 Minuten).
            for s1_try, s1_delay in enumerate(_S1_DELAYS):
                if s1_delay:
                    debug.append(f"…Statement wird IBKR-seitig noch erzeugt → {s1_delay} s warten, GLEICHER Endpoint")
                    time.sleep(s1_delay)
                r1 = requests.get(url1, headers=IBKR_HEADERS, timeout=timeout)
                debug.append(f"Step1 (Versuch {s1_try+1}): HTTP {r1.status_code}, {len(r1.content)} bytes")
                try:
                    root1 = ET.fromstring(r1.content)
                except ET.ParseError as e:
                    debug.append(f"XML-Fehler: {e} | Rohdaten: {r1.text[:200]}")
                    parse_fail = True
                    break
                stat1    = root1.findtext("Status") or ""
                ref      = root1.findtext("ReferenceCode") or ""
                url2     = root1.findtext("Url") or url2
                err1     = root1.findtext("ErrorMessage") or root1.findtext("Message") or ""
                err_code = root1.findtext("ErrorCode") or ""
                debug.append(f"Status={stat1!r}  ref={ref!r}  err={err1!r}")
                if ref:
                    break
                if err_code in _RATE_LIMIT_CODES:
                    return None, (
                        f"⏱️ IBKR Rate Limit (Code {err_code}): Zu viele Anfragen mit diesem Token.\n"
                        "Bitte **5–10 Minuten warten** und dann erneut versuchen."
                    ), "\n".join(debug)
                if err_code in _TOKEN_CODES:
                    return None, (
                        f"🔑 Dein Flex-Token ist **{_TOKEN_CODES[err_code]}** (IBKR-Code {err_code}).\n"
                        "In der IBKR-Kontoverwaltung unter *Einstellungen → Flex-Webdienst* "
                        "einen neuen Prüfcode erzeugen und hier speichern."
                    ), "\n".join(debug)
                if err_code in _QUERY_CODES:
                    return None, (
                        f"❌ IBKR kann die Query nicht verarbeiten (Code {err_code}: {err1}).\n"
                        "Bitte prüfen: Stimmt die **Query-ID**? Ist es eine **Activity Flex Query** "
                        "(Handelsbestätigungs-Queries gehören ins zweite Feld)?"
                    ), "\n".join(debug)
                if not (err_code in _TRANSIENT_CODES
                        or "could not be generated" in err1.lower()):
                    break   # unbekannter Fehler → Endpoint-Wechsel versuchen

            if parse_fail:
                continue
            if not ref:
                conn_errors.append(f"{host}: Status='{stat1}', Fehler='{err1}'")
                if err_code in _TRANSIENT_CODES or "could not be generated" in err1.lower():
                    return None, (
                        "⏳ IBKR konnte das Statement auch nach mehreren Versuchen über "
                        "~2 Minuten nicht erzeugen ('Statement could not be generated "
                        "at this time'). Meist ist das ein vorübergehender IBKR-Zustand — "
                        "bitte in **ein paar Minuten** erneut versuchen.\n\n"
                        "Wenn es **wiederholt** fehlschlägt, liegt es fast immer an der "
                        "Query-Konfiguration bei IBKR:\n"
                        "- Zeitraum der Query auf **'Letzter Geschäftstag'** oder wenige Tage "
                        "stellen (sehr lange Zeiträume schlagen oft fehl)\n"
                        "- Prüfen, ob es eine **Activity Flex Query** ist (keine Handelsbestätigungs-Query)\n"
                        "- Während der IBKR-Wartungsfenster (nachts ~23:45–00:45 New Yorker Zeit, "
                        "samstags länger) schlägt die Erzeugung generell fehl."
                    ), "\n".join(debug)
                debug.append("Kein ReferenceCode → nächsten Endpoint versuchen")
                continue

            for old_h in ["gdcdyn.interactivebrokers.com", "www.interactivebrokers.com",
                          "www.interactivebrokers.eu"]:
                if old_h in url2 and old_h != host:
                    url2 = url2.replace(old_h, host)
            debug.append(f"Polling-URL: {url2}")

            for attempt, poll_delay in enumerate(_POLL_DELAYS):
                time.sleep(poll_delay)
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
                st2   = root2.findtext("Status") or ""
                err2  = root2.findtext("ErrorMessage") or root2.findtext("Message") or ""
                code2 = root2.findtext("ErrorCode") or ""
                if st2 == "Success":
                    return r2.text, None, "\n".join(debug)
                # 'Statement generation in progress' kommt je nach Endpoint auch als
                # Status='Warn' mit ErrorCode 1019 → weiter pollen, NICHT abbrechen.
                if (code2 == "1019" or "in progress" in err2.lower()
                        or "try again" in err2.lower()
                        or st2 in ("", "Processing", "Statement generation in progress")):
                    debug.append(f"…noch in Arbeit (Status={st2!r}, Code={code2!r})")
                    continue
                return None, f"IBKR: Status='{st2}', Meldung='{err2}'", "\n".join(debug)

            return None, ("Timeout: Statement war nach ~110 Sek. noch nicht fertig — "
                          "bitte erneut auf 'Depot jetzt aktualisieren' klicken "
                          "(IBKR erzeugt es im Hintergrund weiter)."), "\n".join(debug)

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
