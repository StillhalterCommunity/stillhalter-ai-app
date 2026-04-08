"""
Stillhalter AI App — IBKR Integration Guide
Schritt-für-Schritt Anleitung zur Anbindung von Interactive Brokers
via Flex Queries und TWS API für das Trade Management.
"""

import streamlit as st
import pandas as pd
import io
import requests
import xml.etree.ElementTree as ET
from typing import Optional, List, Dict

st.set_page_config(
    page_title="IBKR Integration · Stillhalter AI App",
    page_icon="🔌",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.html(f"""
<div style='display:flex;align-items:center;gap:16px;margin-bottom:8px'>
  {get_logo_html(height=44)}
  <div style='border-left:1px solid #222;height:40px;margin:0 4px'></div>
  <div>
    <div style='font-size:1.4rem;font-weight:800;color:#f0f0f0;font-family:sans-serif'>
      🔌 IBKR Portfolio-Integration
    </div>
    <div style='font-size:0.8rem;color:#666;font-family:sans-serif'>
      Dein Interactive Brokers Portfolio direkt im Trade Management — zwei Methoden erklärt
    </div>
  </div>
</div>
""")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# METHODEN ÜBERSICHT
# ══════════════════════════════════════════════════════════════════════════════
st.html("""
<div style='font-size:1.0rem;font-weight:700;color:#f0f0f0;font-family:sans-serif;
     margin-bottom:12px'>📋 Zwei Integrationsmethoden im Überblick</div>
""")

ov1, ov2 = st.columns(2)
with ov1:
    st.html("""
<div style='background:linear-gradient(135deg,#0a140a 0%,#0e0e0e 100%);
     border:2px solid #22c55e;border-radius:14px;padding:20px'>
  <div style='display:flex;align-items:center;gap:12px;margin-bottom:14px'>
    <span style='font-size:2.5rem'>📄</span>
    <div>
      <div style='font-size:1.0rem;font-weight:800;color:#22c55e;font-family:sans-serif'>
        Methode 1: Flex Queries</div>
      <div style='font-size:0.72rem;color:#888;font-family:sans-serif'>
        ⭐ Empfohlen für Einsteiger</div>
    </div>
  </div>
  <div style='font-size:0.78rem;color:#aaa;font-family:sans-serif;line-height:1.7;
       margin-bottom:14px'>
    IBKR generiert auf Knopfdruck eine CSV/XML-Datei mit all deinen Positionen,
    Trades und Kontoinfos. Du lädst die Datei hoch — die App importiert alles automatisch.
    <br><br>
    <b style='color:#f0f0f0'>Kein Code, kein API-Setup, keine Software nötig.</b>
    Funktioniert in ~15 Minuten.
  </div>
  <div style='display:grid;grid-template-columns:1fr 1fr;gap:6px'>
    <div style='background:#0a0a0a;border-radius:6px;padding:8px;text-align:center'>
      <div style='font-size:1.2rem'>✅</div>
      <div style='font-size:0.65rem;color:#888;font-family:sans-serif'>Kein Code nötig</div>
    </div>
    <div style='background:#0a0a0a;border-radius:6px;padding:8px;text-align:center'>
      <div style='font-size:1.2rem'>✅</div>
      <div style='font-size:0.65rem;color:#888;font-family:sans-serif'>Einfach & sicher</div>
    </div>
    <div style='background:#0a0a0a;border-radius:6px;padding:8px;text-align:center'>
      <div style='font-size:1.2rem'>⚠️</div>
      <div style='font-size:0.65rem;color:#888;font-family:sans-serif'>Manueller Export</div>
    </div>
    <div style='background:#0a0a0a;border-radius:6px;padding:8px;text-align:center'>
      <div style='font-size:1.2rem'>✅</div>
      <div style='font-size:0.65rem;color:#888;font-family:sans-serif'>Historische Trades</div>
    </div>
  </div>
</div>
""")

with ov2:
    st.html("""
<div style='background:linear-gradient(135deg,#0a0a14 0%,#0e0e0e 100%);
     border:1px solid #3b82f6;border-radius:14px;padding:20px'>
  <div style='display:flex;align-items:center;gap:12px;margin-bottom:14px'>
    <span style='font-size:2.5rem'>🔌</span>
    <div>
      <div style='font-size:1.0rem;font-weight:800;color:#3b82f6;font-family:sans-serif'>
        Methode 2: TWS API</div>
      <div style='font-size:0.72rem;color:#888;font-family:sans-serif'>
        Für fortgeschrittene Nutzer</div>
    </div>
  </div>
  <div style='font-size:0.78rem;color:#aaa;font-family:sans-serif;line-height:1.7;
       margin-bottom:14px'>
    Die TWS (Trader Workstation) läuft lokal auf deinem Rechner und stellt eine
    API zur Verfügung. Python verbindet sich direkt, holt Live-Positionen und
    aktualisiert das Trade Management automatisch.
    <br><br>
    <b style='color:#f0f0f0'>Echtzeit-Daten, vollautomatisch — aber mehr Setup-Aufwand.</b>
  </div>
  <div style='display:grid;grid-template-columns:1fr 1fr;gap:6px'>
    <div style='background:#0a0a0a;border-radius:6px;padding:8px;text-align:center'>
      <div style='font-size:1.2rem'>✅</div>
      <div style='font-size:0.65rem;color:#888;font-family:sans-serif'>Echtzeit</div>
    </div>
    <div style='background:#0a0a0a;border-radius:6px;padding:8px;text-align:center'>
      <div style='font-size:1.2rem'>✅</div>
      <div style='font-size:0.65rem;color:#888;font-family:sans-serif'>Automatisch</div>
    </div>
    <div style='background:#0a0a0a;border-radius:6px;padding:8px;text-align:center'>
      <div style='font-size:1.2rem'>⚠️</div>
      <div style='font-size:0.65rem;color:#888;font-family:sans-serif'>Python nötig</div>
    </div>
    <div style='background:#0a0a0a;border-radius:6px;padding:8px;text-align:center'>
      <div style='font-size:1.2rem'>⚠️</div>
      <div style='font-size:0.65rem;color:#888;font-family:sans-serif'>TWS läuft immer</div>
    </div>
  </div>
</div>
""")

st.markdown("")

# ══════════════════════════════════════════════════════════════════════════════
# METHODE 1: FLEX QUERIES
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("📄  Methode 1: Flex Queries — Schritt-für-Schritt-Anleitung", expanded=True):

    st.html("""
<div style='font-size:0.82rem;color:#aaa;font-family:sans-serif;line-height:1.7;
     margin-bottom:16px;background:#0e0e0e;border-radius:8px;padding:14px;
     border-left:3px solid #22c55e'>
  <b style='color:#22c55e'>💡 Was ist eine Flex Query?</b><br>
  IBKR Flex Queries sind benutzerdefinierte Berichte, die du einmal einrichtest
  und dann per Knopfdruck aktuelle Daten exportierst. Du definierst genau, welche
  Felder du brauchst (Positionen, Trades, Prämien usw.).
</div>
""")

    steps = [
        ("1", "#22c55e", "IBKR Client Portal öffnen",
         "Gehe zu <b>clientportal.ibkr.com</b> und melde dich an.",
         [
             "Öffne deinen Browser",
             "Navigiere zu: clientportal.ibkr.com",
             "Mit deinen IBKR-Zugangsdaten einloggen",
             "Zwei-Faktor-Authentifizierung bestätigen",
         ], None),

        ("2", "#22c55e", "Flex Query erstellen",
         "Navigiere zu: <b>Leistung & Berichte → Flex Queries</b>",
         [
             "Im linken Menü: 'Leistung & Berichte' aufklappen",
             "Klick auf 'Flex Queries'",
             "Button '+' oder 'Erstellen' klicken",
             "Query-Typ wählen: 'Aktivitäten-Flex-Query'",
         ],
         """<div style='background:#0a0a0a;border-radius:8px;padding:12px;
            font-size:0.75rem;color:#888;font-family:sans-serif;line-height:1.6'>
  <b style='color:#f0f0f0'>Direkte URL im Client Portal:</b><br>
  Leistung &amp; Berichte → Berichte → Flex Queries → Aktivitäten-Flex-Query
</div>"""),

        ("3", "#22c55e", "Flex Query konfigurieren",
         "Wähle folgende <b>Felder</b> für den Optionen-Import:",
         [
             "Section: 'Open Positions' (Offene Positionen)",
             "Section: 'Trades' (für historische Transaktionen)",
         ],
         """<div style='background:#0a0a0a;border-radius:8px;padding:14px;font-family:sans-serif'>
  <div style='font-size:0.72rem;color:#d4a843;font-weight:700;margin-bottom:8px'>
    Wichtige Felder in 'Open Positions':</div>
  <div style='display:grid;grid-template-columns:1fr 1fr;gap:4px'>
    <div style='font-size:0.68rem;color:#22c55e'>✓ Symbol</div>
    <div style='font-size:0.68rem;color:#aaa'>Aktien-Ticker</div>
    <div style='font-size:0.68rem;color:#22c55e'>✓ Description</div>
    <div style='font-size:0.68rem;color:#aaa'>Optionsbeschreibung</div>
    <div style='font-size:0.68rem;color:#22c55e'>✓ Position</div>
    <div style='font-size:0.68rem;color:#aaa'>Anzahl Kontrakte</div>
    <div style='font-size:0.68rem;color:#22c55e'>✓ MarkPrice</div>
    <div style='font-size:0.68rem;color:#aaa'>Aktueller Preis</div>
    <div style='font-size:0.68rem;color:#22c55e'>✓ CostBasisPrice</div>
    <div style='font-size:0.68rem;color:#aaa'>Einstandspreis (Prämie)</div>
    <div style='font-size:0.68rem;color:#22c55e'>✓ UnrealizedPnL</div>
    <div style='font-size:0.68rem;color:#aaa'>Unrealisierter Gewinn/Verlust</div>
    <div style='font-size:0.68rem;color:#22c55e'>✓ Strike</div>
    <div style='font-size:0.68rem;color:#aaa'>Ausübungspreis</div>
    <div style='font-size:0.68rem;color:#22c55e'>✓ Expiry</div>
    <div style='font-size:0.68rem;color:#aaa'>Verfallsdatum</div>
    <div style='font-size:0.68rem;color:#22c55e'>✓ PutOrCall</div>
    <div style='font-size:0.68rem;color:#aaa'>PUT oder CALL</div>
    <div style='font-size:0.68rem;color:#22c55e'>✓ AssetClass</div>
    <div style='font-size:0.68rem;color:#aaa'>Filter: OPT (Options)</div>
  </div>
  <div style='margin-top:10px;font-size:0.68rem;color:#555'>
    Format: CSV · Datum-Format: YYYYMMDD · Dezimaltrennzeichen: Punkt
  </div>
</div>"""),

        ("4", "#22c55e", "Format einstellen",
         "Format-Einstellungen für optimale Kompatibilität:",
         [
             "Format: CSV (empfohlen) oder XML",
             "Datum-Format: YYYYMMDD",
             "Berichts-Zeitraum: 'Letzte N Tage' (z.B. 365)",
             "Konten: Alle Konten oder spezifisches Konto wählen",
         ],
         None),

        ("5", "#22c55e", "Query ausführen & herunterladen",
         "Die Query ist eingerichtet — jetzt exportieren:",
         [
             "Auf 'Ausführen' oder 'Token anfordern' klicken",
             "IBKR generiert die Datei (kann 1–2 Min. dauern)",
             "CSV-Datei herunterladen und speichern",
             "Datei in den Upload-Bereich unten hochladen",
         ],
         None),
    ]

    for step_num, color, title, desc, bullets, extra_html in steps:
        bullet_html = "".join(
            f"<div style='display:flex;align-items:baseline;gap:6px;padding:3px 0'>"
            f"<span style='color:{color};font-size:0.75rem;min-width:12px'>→</span>"
            f"<span style='font-size:0.75rem;color:#aaa;font-family:sans-serif'>{b}</span></div>"
            for b in bullets
        )
        st.html(f"""
<div style='display:flex;gap:14px;margin-bottom:14px;align-items:flex-start'>
  <div style='background:{color}22;border:2px solid {color};border-radius:50%;
       width:32px;height:32px;display:flex;align-items:center;justify-content:center;
       flex-shrink:0;font-size:0.88rem;font-weight:800;color:{color};font-family:sans-serif'>
    {step_num}</div>
  <div style='flex:1;background:#0e0e0e;border:1px solid #1e1e1e;border-radius:10px;
       padding:14px'>
    <div style='font-size:0.88rem;font-weight:700;color:#f0f0f0;font-family:sans-serif;
         margin-bottom:4px'>{title}</div>
    <div style='font-size:0.75rem;color:#888;font-family:sans-serif;margin-bottom:8px'>
      {desc}</div>
    {bullet_html}
    {extra_html or ''}
  </div>
</div>
""")

    # ── CSV Upload ─────────────────────────────────────────────────────────────
    st.html("""
<div style='background:#1a1005;border:2px dashed #d4a843;border-radius:10px;
     padding:16px;margin-top:8px'>
  <div style='font-size:0.88rem;font-weight:700;color:#d4a843;font-family:sans-serif;
       margin-bottom:4px'>📤 Schritt 6: Flex-Query-Datei hochladen</div>
  <div style='font-size:0.75rem;color:#888;font-family:sans-serif'>
    Lade deine exportierte CSV-Datei hoch — die App liest alle Optionspositionen aus
    und zeigt sie im Trade Management an.
  </div>
</div>
""")

    uploaded = st.file_uploader(
        "IBKR Flex Query CSV hochladen",
        type=["csv", "txt"],
        help="Exportierte Flex-Query-Datei von Interactive Brokers",
        key="ibkr_flex_upload",
    )

    if uploaded is not None:
        try:
            raw = uploaded.read().decode("utf-8", errors="replace")
            lines = [l for l in raw.splitlines() if l.strip()]

            # Versuche, die Positions-Sektion zu finden
            pos_lines = []
            in_positions = False
            headers = None

            for line in lines:
                if "OpenPositions" in line or "Open Positions" in line:
                    in_positions = True
                if in_positions:
                    if not headers and "Symbol" in line and "Strike" in line:
                        headers = [h.strip() for h in line.split(",")]
                    elif headers and line and not any(
                        kw in line for kw in ["Total", "Header", "END"]
                    ):
                        parts = line.split(",")
                        if len(parts) >= 5:
                            pos_lines.append(parts)

            if headers and pos_lines:
                df = pd.DataFrame(pos_lines, columns=headers[:len(pos_lines[0])])

                # Filter auf OPT
                if "AssetClass" in df.columns:
                    df = df[df["AssetClass"].str.strip() == "OPT"]

                st.success(f"✅ {len(df)} Optionspositionen aus der Datei gelesen!")

                if not df.empty:
                    st.html("""
<div style='font-size:0.8rem;font-weight:700;color:#f0f0f0;font-family:sans-serif;
     margin:10px 0 6px 0'>Importierte Positionen</div>
""")
                    display_cols = [c for c in [
                        "Symbol", "Description", "PutOrCall", "Strike", "Expiry",
                        "Position", "MarkPrice", "CostBasisPrice", "UnrealizedPnL",
                    ] if c in df.columns]
                    st.dataframe(
                        df[display_cols].reset_index(drop=True),
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.html("""
<div style='background:#0a140a;border:1px solid #22c55e33;border-radius:8px;
     padding:12px 14px;margin-top:8px;font-family:sans-serif'>
  <div style='font-size:0.78rem;font-weight:700;color:#22c55e;margin-bottom:4px'>
    ✅ Nächster Schritt</div>
  <div style='font-size:0.72rem;color:#888;line-height:1.6'>
    Die Positionen werden erkannt. In zukünftigen Versionen der App werden diese
    Daten automatisch ins Trade Management importiert. Aktuell kannst du die Werte
    manuell in das Trade Management (Seite 4) eintragen.
    <br><br>
    <b style='color:#f0f0f0'>Tipp:</b> Exportiere die Flex Query wöchentlich (z.B. montags),
    um einen aktuellen Überblick deiner Positionen zu haben.
  </div>
</div>
""")
            else:
                # Fallback: Rohdaten anzeigen
                st.html("""
<div style='background:#140a0a;border:1px solid #ef444433;border-radius:8px;
     padding:12px;font-family:sans-serif;margin-bottom:8px'>
  <div style='font-size:0.78rem;font-weight:700;color:#ef4444;margin-bottom:4px'>
    ⚠️ Format nicht erkannt</div>
  <div style='font-size:0.72rem;color:#888;line-height:1.6'>
    Die hochgeladene Datei konnte nicht automatisch als IBKR Flex Query erkannt werden.
    Bitte stelle sicher, dass du die Datei korrekt konfiguriert hast (Schritt 3).
    Unten siehst du die ersten Zeilen der Datei zur Diagnose.
  </div>
</div>
""")
                st.code("\n".join(lines[:10]), language="text")

        except Exception as e:
            st.error(f"Fehler beim Lesen der Datei: {e}")

    # ── Beispiel-CSV ────────────────────────────────────────────────────────────
    with st.expander("📋 Beispiel: So sieht eine korrekte Flex-Query-CSV aus"):
        example_csv = """BOF,FLEX_VERSION=3,CLIENT_CODE=12345678
OpenPositions,Header,DataDiscriminator,AssetClass,SubCategory,Symbol,Description,Conid,SecurityID,SICCode,SecurityIDType,CUSIP,ISIN,UnderlyingConid,UnderlyingSymbol,Issuer,Multiplier,Strike,Expiry,PutOrCall,PrincipalAdjustFactor,ReportDate,Position,MarkPrice,PositionValue,OpenPrice,CostBasisPrice,CostBasisMoney,PercentOfNAV,FifoPnlUnrealized,Side,Level1,Level2,Level3,Level4,Code
OpenPositions,Data,,,OPT,,AAPL 250117C00200000,684318696,,,,,,8552619,AAPL,,100,200,20250117,C,1,20250406,-3,8.5,-2550,12.3,12.3,-3690,-0.45,-1140,Short,,,,,
OpenPositions,Data,,,OPT,,NVDA 250221P00750000,694781234,,,,,,4815747,NVDA,,100,750,20250221,P,1,20250406,5,18.2,9100,15.4,15.4,7700,0.82,1400,Long,,,,,
EOF"""
        st.code(example_csv, language="text")

# ══════════════════════════════════════════════════════════════════════════════
# METHODE 1b: FLEX WEB SERVICE — AUTOMATISCHER PUSH (wie Visual Trading Journal)
# ══════════════════════════════════════════════════════════════════════════════

_IBKR_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/xml,application/xml,*/*",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Connection": "keep-alive",
}
# IBKR hat zwei Endpoints — gdcdyn ist CDN, www ist Fallback
_IBKR_BASES = [
    "https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService",
    "https://www.interactivebrokers.com/Universal/servlet/FlexStatementService",
]


def _ibkr_get(url: str, timeout: int = 30):
    """
    GET gegen IBKR. requests (verify=True → False) → urllib Fallback.
    Wirft immer ConnectionError wenn alle Methoden scheitern.
    """
    import ssl, urllib.request as _ur
    errors = []

    for verify in (True, False):
        try:
            return requests.get(url, headers=_IBKR_HEADERS, timeout=timeout, verify=verify)
        except (requests.exceptions.SSLError,
                requests.exceptions.ConnectionError) as e:
            errors.append(str(e)[:120])

    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode    = ssl.CERT_NONE
        req  = _ur.Request(url, headers=_IBKR_HEADERS)
        resp = _ur.urlopen(req, timeout=timeout, context=ctx)
        class _FakeResp:
            def __init__(self, r):
                self.content     = r.read()
                self.text        = self.content.decode("utf-8", errors="replace")
                self.status_code = r.status
            def raise_for_status(self): pass
        return _FakeResp(resp)
    except Exception as e:
        errors.append(str(e)[:120])

    raise requests.exceptions.ConnectionError(
        f"Alle Verbindungsmethoden fehlgeschlagen: {'; '.join(errors[-2:])}"
    )


def _flex_fetch_xml(token: str, query_id: str, timeout: int = 30):
    """
    Ruft eine Flex Query per Web Service ab. Probiert beide IBKR-Endpoints.
    Gibt (xml_string, error_detail) zurück.
    """
    import time
    last_conn_err = ""
    for base in _IBKR_BASES:
        try:
            req_url = f"{base}.SendRequest?t={token}&q={query_id}&v=3"
            r1 = _ibkr_get(req_url, timeout=timeout)
            r1.raise_for_status()

            try:
                root1 = ET.fromstring(r1.content)
            except ET.ParseError as e:
                return None, f"XML-Parse-Fehler (Step 1): {e}\nRohdaten: {r1.text[:400]}"

            status1 = root1.findtext("Status") or ""
            ref     = root1.findtext("ReferenceCode") or ""
            url2    = root1.findtext("Url") or ""
            err_msg = root1.findtext("ErrorMessage") or root1.findtext("Message") or ""

            if not ref:
                detail = f"IBKR Fehler — Status: '{status1}'"
                if err_msg:
                    detail += f"\nIBKR-Meldung: {err_msg}"
                detail += f"\nRohantwort: {r1.text[:500]}"
                return None, detail

            if not url2:
                url2 = f"{base}.GetStatement"
            # gdcdyn kann bei manchen Netzen nicht aufgelöst werden → auf www umleiten
            url2 = url2.replace("gdcdyn.interactivebrokers.com", "www.interactivebrokers.com")

            last_status2 = ""
            last_err2    = ""
            for attempt in range(10):
                time.sleep(3)
                r2 = _ibkr_get(f"{url2}?q={ref}&t={token}&v=3", timeout=timeout)
                size = len(r2.content)

                # Großer Response (>10 KB) = direkter Flex-Report, kein Status-Wrapper
                if size > 10000:
                    return r2.text, None

                try:
                    root2 = ET.fromstring(r2.content)
                except ET.ParseError:
                    if size > 500:
                        return r2.text, None
                    continue

                st2  = root2.findtext("Status") or ""
                err2 = root2.findtext("ErrorMessage") or root2.findtext("Message") or ""
                last_status2 = st2
                last_err2    = err2

                if st2 == "Success":
                    return r2.text, None
                if st2 not in ("", "Processing", "Statement generation in progress"):
                    break

            detail = f"IBKR Step 2 — letzter Status: '{last_status2}'"
            if last_err2:
                detail += f"\nIBKR-Meldung: {last_err2}"
            return None, detail

        except (requests.exceptions.ConnectionError,
                requests.exceptions.SSLError) as e:
            last_conn_err = str(e)
            continue  # nächsten Endpoint versuchen
        except requests.exceptions.Timeout:
            return None, "Timeout: IBKR-Server antwortet nicht. Bitte in 1–2 Min. erneut versuchen."
        except requests.exceptions.HTTPError as e:
            return None, f"HTTP-Fehler: {e}"
        except Exception as e:
            return None, f"Unerwarteter Fehler ({type(e).__name__}): {e}"

    return None, (
        f"Beide IBKR-Server nicht erreichbar (DNS/Netzwerk).\n"
        f"Letzter Fehler: {last_conn_err[:300]}\n\n"
        f"Mögliche Ursachen:\n"
        f"• VPN aktiv? → VPN deaktivieren und erneut versuchen\n"
        f"• DNS-Blocker (Pi-hole, AdGuard)? → interactivebrokers.com freigeben\n"
        f"• Firewall blockiert Port 443 zu interactivebrokers.com?\n"
        f"• Proxy-Einstellungen prüfen"
    )


def _parse_flex_positions(xml_str: str) -> pd.DataFrame:
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
                "Typ":         a.get("putCall", ""),
                "Strike":      float(a.get("strike", 0)),
                "Verfall":     a.get("expiry", ""),
                "Menge":       int(float(a.get("position", 0))),
                "Prämie_Ein":  float(a.get("costBasisPrice", 0)),
                "Prämie_Akt":  float(a.get("markPrice", 0)),
                "PnL_USD":     float(a.get("fifoPnlUnrealized", 0)),
                "Notiz":       a.get("description", ""),
                "_ibkr":       True,
            })
        except Exception:
            continue

    if not rows:
        # Fallback: Trades parsen
        for tr in root.iter("Trade"):
            a = tr.attrib
            if a.get("assetCategory", "") != "OPT":
                continue
            try:
                rows.append({
                    "Ticker":      a.get("underlyingSymbol", a.get("symbol", "")),
                    "Typ":         a.get("putCall", ""),
                    "Strike":      float(a.get("strike", 0)),
                    "Verfall":     a.get("expiry", ""),
                    "Menge":       int(float(a.get("quantity", 0))),
                    "Prämie_Ein":  float(a.get("tradePrice", 0)),
                    "Prämie_Akt":  0.0,
                    "PnL_USD":     float(a.get("fifoPnlRealized", 0)),
                    "Notiz":       a.get("description", ""),
                    "_ibkr":       True,
                })
            except Exception:
                continue

    return pd.DataFrame(rows) if rows else pd.DataFrame()


with st.expander("🔄  Methode 1b: Flex Web Service — Automatischer Live-Abruf", expanded=False):

    st.html("""
<div style='background:#0a1020;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;
     padding:14px 16px;margin-bottom:18px;font-family:sans-serif'>
  <div style='font-size:0.88rem;font-weight:800;color:#3b82f6;margin-bottom:6px'>
    🚀 Kein manueller Download mehr</div>
  <div style='font-size:0.76rem;color:#aaa;line-height:1.75'>
    Du gibst einmalig deinen <b style='color:#f0f0f0'>Flex-Web-Service-Token</b> und
    zwei <b style='color:#f0f0f0'>Query-IDs</b> ein — die App holt die Daten dann
    automatisch direkt von IBKR. Identisch mit dem Ansatz von Visual Trading Journal.<br><br>
    Die Verbindung ist <b style='color:#22c55e'>read-only</b> — kein Handel, kein Zugriff
    auf Zugangsdaten, nur Reporting-Daten.
  </div>
</div>
""")

    # ── Schritt-für-Schritt Setup ──────────────────────────────────────────────
    setup_steps = [
        ("1", "#3b82f6", "Flex Web Service aktivieren",
         "Im IBKR Client Portal → <b>Performance &amp; Berichte → Flex Queries</b>",
         [
             "Oben rechts auf das ⚙️ Zahnrad-Symbol klicken (Flex-Web-Service-Konfiguration)",
             "Checkbox <b>Flex-Web-Service-Status</b> aktivieren",
             "Auf <b>Token generieren</b> klicken — Gültigkeit: max. 1 Jahr",
             "Den generierten Token kopieren und unten einfügen",
         ]),
        ("2", "#3b82f6", "Kontoumsatz-Flex-Query erstellen (14 Sektionen)",
         "Neue <b>Aktivitäten-Flex-Query</b> anlegen mit allen 14 Pflicht-Sektionen:",
         [
             "Bartransaktionen · Cash-Bericht · Forex-G&amp;V-Details",
             "Gewährung von Bezugsrechten · Kapitalflussrechnung · Kapitalmaßnahmen",
             "Kontoinformationen · NAV in Basiswährung · <b>Offene Positionen ✓</b>",
             "Optionsausübungen/-zuteilungen/-fälligkeiten · <b>Trades ✓</b>",
             "Transaktionsgebühren · Transfers · Umsatzsteuer-Details",
             "Zeitraum: <b>Letzte 30 Kalendertage</b> · Format: XML",
             "Nach Speichern: auf ℹ️ klicken → <b>6-stellige Query-ID</b> kopieren",
         ]),
        ("3", "#3b82f6", "Handelsbestätigungs-Flex-Query erstellen",
         "Separate <b>Handelsbestätigungs-Flex-Query</b> anlegen:",
         [
             "Sektion: <b>Handelsbestätigung</b> → Alle Unter-Optionen auswählen",
             "Zeitraum: Letzte 30 Kalendertage · Format: XML",
             "Nach Speichern: auf ℹ️ klicken → <b>6-stellige Query-ID</b> kopieren",
         ]),
    ]

    for snum, scol, stitle, sdesc, sbullets in setup_steps:
        bhtml = "".join(
            f"<div style='display:flex;align-items:baseline;gap:6px;padding:2px 0'>"
            f"<span style='color:{scol};font-size:0.72rem;min-width:10px'>→</span>"
            f"<span style='font-size:0.73rem;color:#aaa;font-family:sans-serif'>{b}</span></div>"
            for b in sbullets
        )
        st.html(f"""
<div style='display:flex;gap:14px;margin-bottom:12px;align-items:flex-start'>
  <div style='background:{scol}22;border:2px solid {scol};border-radius:50%;
       width:30px;height:30px;min-width:30px;display:flex;align-items:center;
       justify-content:center;font-size:0.85rem;font-weight:800;color:{scol};
       font-family:sans-serif'>{snum}</div>
  <div style='flex:1;background:#0e0e0e;border:1px solid #1e1e1e;border-radius:10px;
       padding:12px 14px'>
    <div style='font-size:0.86rem;font-weight:700;color:#f0f0f0;
         font-family:sans-serif;margin-bottom:3px'>{stitle}</div>
    <div style='font-size:0.73rem;color:#666;font-family:sans-serif;margin-bottom:7px'>
      {sdesc}</div>
    {bhtml}
  </div>
</div>
""")

    st.divider()
    st.markdown("**🔑 Token & Query-IDs eingeben:**")

    # Session-State für Credentials
    if "ibkr_token"    not in st.session_state: st.session_state["ibkr_token"]    = ""
    if "ibkr_qid_pos"  not in st.session_state: st.session_state["ibkr_qid_pos"]  = ""
    if "ibkr_qid_trade" not in st.session_state: st.session_state["ibkr_qid_trade"] = ""

    fc1, fc2, fc3 = st.columns([3, 1.5, 1.5])
    with fc1:
        token = st.text_input(
            "Flex-Web-Service-Token",
            value=st.session_state["ibkr_token"],
            placeholder="z.B. 1234567890abcdef…  (aus IBKR Flex-Web-Service-Konfiguration)",
            type="password",
            key="ibkr_token_input",
            label_visibility="visible",
        )
        st.session_state["ibkr_token"] = token

    with fc2:
        qid_pos = st.text_input(
            "Query-ID: Kontoumsatz",
            value=st.session_state["ibkr_qid_pos"],
            placeholder="123456",
            key="ibkr_qid_pos_input",
            label_visibility="visible",
        )
        st.session_state["ibkr_qid_pos"] = qid_pos

    with fc3:
        qid_trade = st.text_input(
            "Query-ID: Handelsbestätigung",
            value=st.session_state["ibkr_qid_trade"],
            placeholder="654321",
            key="ibkr_qid_trade_input",
            label_visibility="visible",
        )
        st.session_state["ibkr_qid_trade"] = qid_trade

    st.html("""
<div style='font-size:0.68rem;color:#444;font-family:sans-serif;margin-top:4px;margin-bottom:12px'>
  🔒 Token wird nur lokal in deiner Browser-Session gespeichert — nie übertragen oder gespeichert.
  Die Verbindung ist read-only (kein Handel möglich).
</div>
""")

    col_btn, col_test, col_status = st.columns([2, 1.5, 2])
    with col_btn:
        fetch_btn = st.button(
            "🔄 Jetzt von IBKR abrufen",
            key="ibkr_flex_fetch",
            type="primary",
            use_container_width=True,
            disabled=not (token.strip() and qid_pos.strip()),
        )
    with col_test:
        test_btn = st.button("🔍 Verbindung testen", key="ibkr_test_conn",
                             use_container_width=True,
                             help="Prüft ob IBKR-Server erreichbar ist")

    if test_btn:
        with st.spinner("Teste Verbindung zu IBKR-Servern…"):
            results = []
            for base in _IBKR_BASES:
                try:
                    tr = _ibkr_get(f"{base}.SendRequest?t=TEST&q=0&v=3", timeout=10)
                    results.append(f"✅ {base.split('/')[2]} → HTTP {tr.status_code}")
                except Exception as te:
                    results.append(f"❌ {base.split('/')[2]} → {type(te).__name__}: {str(te)[:120]}")
            status_str = "\n".join(results)
            if any("✅" in r for r in results):
                st.success(f"IBKR-Server erreichbar:\n{status_str}\n\nToken & Query-ID prüfen falls Abruf trotzdem fehlschlägt.")
            else:
                st.error(
                    f"Beide IBKR-Server nicht erreichbar:\n{status_str}\n\n"
                    "**→ Mögliche Lösung: VPN deaktivieren oder DNS-Blocker prüfen**"
                )

    if fetch_btn:
        if not token.strip() or not qid_pos.strip():
            st.warning("Bitte Token und Query-ID (Kontoumsatz) eingeben.")
        else:
            with st.spinner("Verbinde mit IBKR Flex Web Service… (kann 10–20 Sek. dauern)"):
                xml_str, err_detail = _flex_fetch_xml(token.strip(), qid_pos.strip())

            if xml_str:
                positions_df = _parse_flex_positions(xml_str)
                if not positions_df.empty:
                    st.session_state["ibkr_flex_positions"] = positions_df
                    st.success(f"✅ {len(positions_df)} Optionspositionen erfolgreich abgerufen!")

                    # Vorschau
                    preview_cols = [c for c in [
                        "Ticker", "Typ", "Strike", "Verfall", "Menge",
                        "Prämie_Ein", "Prämie_Akt", "PnL_USD"
                    ] if c in positions_df.columns]
                    st.dataframe(
                        positions_df[preview_cols].reset_index(drop=True),
                        use_container_width=True,
                        hide_index=True,
                    )

                    st.html("""
<div style='background:#0a140a;border:1px solid #22c55e44;border-radius:8px;
     padding:12px 14px;margin-top:8px;font-family:sans-serif'>
  <div style='font-size:0.78rem;font-weight:700;color:#22c55e;margin-bottom:4px'>
    ✅ Nächster Schritt</div>
  <div style='font-size:0.73rem;color:#888;line-height:1.6'>
    Klicke unten auf <b style='color:#f0f0f0'>„Ins Trade Management übernehmen"</b>
    um die Positionen direkt ins Trade Management (Seite 4) zu laden.
  </div>
</div>
""")
                    if st.button(
                        "📊 Ins Trade Management übernehmen",
                        key="ibkr_push_to_tm",
                        type="primary",
                    ):
                        st.session_state["tm_positions"] = positions_df
                        st.session_state["tm_results"]   = {}
                        st.session_state["tm_is_ibkr"]   = True
                        st.success("✅ Positionen ins Trade Management übertragen! → Seite 4 öffnen.")

                else:
                    st.warning("Verbindung erfolgreich, aber keine OPT-Positionen in der Antwort gefunden. "
                               "Prüfe ob Optionspositionen offen sind und die Query korrekt konfiguriert ist.")
                    with st.expander("🔍 XML-Rohdaten zur Diagnose"):
                        st.code(xml_str[:3000], language="xml")
            else:
                # Zeige konkreten Fehler aus dem API-Call
                err_lines = (err_detail or "Unbekannter Fehler").splitlines()
                err_md = "\n".join(f"• {l}" for l in err_lines if l.strip())
                st.error(
                    "❌ Verbindung fehlgeschlagen.\n\n"
                    + err_md +
                    "\n\n**Mögliche Ursachen:**\n"
                    "• Token falsch oder abgelaufen (max. 1 Jahr Gültigkeit)\n"
                    "• Flex Web Service nicht aktiviert (⚙️ Zahnrad in Flex Queries → aktivieren)\n"
                    "• Query-ID falsch — die Zahl aus dem ℹ️ Symbol neben der Query\n"
                    "• IBKR-Server temporär nicht erreichbar — in 1–2 Min. erneut versuchen"
                )

# ══════════════════════════════════════════════════════════════════════════════
# METHODE 2: TWS API
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("🔌  Methode 2: TWS API — Live-Verbindung einrichten"):

    st.html("""
<div style='background:#0a0a14;border-left:3px solid #3b82f6;border-radius:0 8px 8px 0;
     padding:12px 14px;margin-bottom:16px;font-family:sans-serif'>
  <div style='font-size:0.82rem;font-weight:700;color:#3b82f6;margin-bottom:4px'>
    Voraussetzungen</div>
  <div style='font-size:0.72rem;color:#888;line-height:1.7'>
    • Interactive Brokers TWS (Trader Workstation) auf dem Rechner installiert<br>
    • Python 3.9+ installiert<br>
    • ib_insync Bibliothek: <code style='color:#f0f0f0'>pip install ib_insync</code><br>
    • TWS muss geöffnet und eingeloggt sein wenn die App läuft
  </div>
</div>
""")

    st.html("""
<div style='font-size:0.82rem;font-weight:700;color:#f0f0f0;font-family:sans-serif;
     margin-bottom:8px'>Schritt 1: TWS API aktivieren</div>
""")
    st.html("""
<div style='background:#0e0e0e;border:1px solid #1e1e1e;border-radius:8px;padding:12px;
     font-family:sans-serif;font-size:0.75rem;color:#aaa;line-height:1.7;margin-bottom:12px'>
  <b style='color:#f0f0f0'>In der TWS:</b><br>
  → Datei → Globale Konfiguration → API → Einstellungen<br>
  → "Socket-Port": <b style='color:#3b82f6'>7497</b> (Paper) oder <b style='color:#3b82f6'>7496</b> (Live)<br>
  → "Vertrauenswürdige IPs": <code style='color:#f0f0f0'>127.0.0.1</code> hinzufügen<br>
  → "ActiveX und Socket-Clients zulassen" ✓ ankreuzen<br>
  → Bestätigen und TWS neu starten
</div>
""")

    st.html("""
<div style='font-size:0.82rem;font-weight:700;color:#f0f0f0;font-family:sans-serif;
     margin-bottom:8px'>Schritt 2: Python-Code — Positionen abrufen</div>
""")

    code_example = '''"""
Stillhalter AI App — IBKR TWS API Verbindung
Liest alle offenen Optionspositionen aus dem laufenden TWS.
Voraussetzung: pip install ib_insync
"""

from ib_insync import IB, util
import pandas as pd
from datetime import date

def get_ibkr_option_positions(host: str = "127.0.0.1",
                               port: int = 7497,    # 7497=Paper, 7496=Live
                               client_id: int = 1) -> pd.DataFrame:
    """
    Verbindet sich mit dem laufenden TWS und holt alle Optionspositionen.
    Gibt einen DataFrame zurück, der direkt ins Trade Management importiert werden kann.
    """
    ib = IB()
    ib.connect(host, port, clientId=client_id)

    positions = ib.positions()
    records = []

    for pos in positions:
        contract = pos.contract
        if contract.secType != "OPT":
            continue   # Nur Optionen

        # Marktdaten anfordern
        ticker = ib.reqMktData(contract, "", False, False)
        ib.sleep(1)   # kurz warten

        records.append({
            "Ticker":      contract.symbol,
            "Typ":         contract.right,     # "C" = Call, "P" = Put
            "Strike":      float(contract.strike),
            "Verfall":     contract.lastTradeDateOrContractMonth,
            "DTE":         (date.fromisoformat(contract.lastTradeDateOrContractMonth)
                           - date.today()).days,
            "Kontrakte":   int(pos.position),
            "Prämie_ein":  round(float(pos.avgCost) / 100, 2),  # pro Aktie
            "Preis_akt":   round(float(ticker.marketPrice() or 0), 2),
            "P&L_unreal":  round(float(pos.unrealizedPnL or 0), 2),
        })

    ib.disconnect()

    df = pd.DataFrame(records)
    if not df.empty:
        df["Typ"] = df["Typ"].map({"C": "CALL", "P": "PUT"})
    return df


# ── Beispielaufruf ──────────────────────────────────────────────────────────
if __name__ == "__main__":
    df = get_ibkr_option_positions(port=7497)  # Paper Trading
    print(f"\\n{len(df)} Optionspositionen geladen:")
    print(df.to_string(index=False))

    # Optional: Als CSV speichern für manuellen Import
    df.to_csv("ibkr_positionen.csv", index=False, sep=";")
    print("\\n✅ ibkr_positionen.csv gespeichert")
'''

    st.code(code_example, language="python")

    st.html("""
<div style='background:#0e0e0e;border:1px solid #1e1e1e;border-radius:8px;
     padding:14px;margin-top:8px;font-family:sans-serif'>
  <div style='font-size:0.78rem;font-weight:700;color:#f59e0b;margin-bottom:6px'>
    ⚠️ Wichtige Sicherheitshinweise</div>
  <div style='font-size:0.72rem;color:#888;line-height:1.7'>
    • <b style='color:#f0f0f0'>Immer Paper Trading zuerst testen</b> (Port 7497) bevor du Live-Konten verbindest<br>
    • Die API-Verbindung ist nur lesend — keine Orders werden automatisch gesendet<br>
    • Die App sendet keine Daten an externe Server — alles läuft lokal<br>
    • Bei Disconnects: TWS neu starten und client_id incrementieren (z.B. clientId=2)
  </div>
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# HÄUFIGE FRAGEN
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("")
st.html("""
<div style='font-size:1.0rem;font-weight:700;color:#f0f0f0;font-family:sans-serif;
     margin-bottom:12px'>❓ Häufige Fragen (FAQ)</div>
""")

faqs = [
    ("Wie oft soll ich die Flex Query exportieren?",
     "Empfehlung: <b>einmal pro Woche</b>, idealerweise montags vor Marktöffnung. "
     "Für aktive Trader mit vielen Positionen auch täglich möglich. "
     "Die Flex Query speichert du einmal, dann ist es nur noch ein Klick zum Exportieren."),

    ("Meine CSV wird nicht erkannt — was tun?",
     "Überprüfe folgendes: <br>"
     "1. Hast du die Sektion 'Open Positions' in der Query aktiviert?<br>"
     "2. Sind die Felder 'Symbol', 'Strike', 'Expiry', 'PutOrCall' ausgewählt?<br>"
     "3. Format: CSV (nicht XML)?<br>"
     "4. AssetClass-Feld aktiviert (für Filter OPT)?"),

    ("Kann die App automatisch Orders bei IBKR platzieren?",
     "Nein — und das ist gewollt! Die App ist ein <b>Analyse- und Monitoring-Tool</b>, "
     "kein automatisierter Handelsroboter. Alle finalen Handelsentscheidungen "
     "triffst du selbst in IBKR. Das schützt dich vor ungewollten Trades."),

    ("Funktioniert das auch mit anderen Brokern?",
     "Die Flex-Query-Funktion ist IBKR-spezifisch. Andere Broker (Tastyworks, TradeStation etc.) "
     "haben ähnliche Export-Funktionen. Du kannst die CSV-Datei manuell anpassen "
     "oder die Trades direkt ins Trade Management eintragen. "
     "Eine Erweiterung für weitere Broker ist geplant."),

    ("Sind meine IBKR-Daten sicher?",
     "Absolut. Alle Daten bleiben auf deinem Rechner. "
     "Weder die Flex-Query-Datei noch API-Verbindungsdaten werden an externe Server übertragen. "
     "Die App läuft komplett lokal auf deinem Gerät."),
]

for q, a in faqs:
    with st.expander(f"❓ {q}"):
        st.html(f"""
<div style='font-size:0.78rem;color:#aaa;font-family:sans-serif;line-height:1.7;
     padding:8px 4px'>{a}</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# KONTAKT / SUPPORT
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("")
st.html("""
<div style='background:linear-gradient(135deg,#0e0e0e 0%,#111 100%);
     border:1px solid #1e1e1e;border-radius:12px;padding:18px 22px'>
  <div style='font-size:0.88rem;font-weight:700;color:#d4a843;font-family:sans-serif;
       margin-bottom:8px'>🤝 Brauchst du Hilfe bei der Einrichtung?</div>
  <div style='font-size:0.78rem;color:#aaa;font-family:sans-serif;line-height:1.7'>
    Wenn du Probleme bei der Flex-Query-Konfiguration hast oder die TWS-API-Verbindung
    nicht klappt, wende dich an das Stillhalter AI App Support-Team.<br><br>
    Beschreibe dabei:<br>
    • Welche Methode du verwendest (Flex Query oder TWS API)<br>
    • Was du konkret siehst (Fehlermeldung, leere Datei etc.)<br>
    • Deine TWS-Version (zu finden unter: Hilfe → Info)
  </div>
</div>
""")
