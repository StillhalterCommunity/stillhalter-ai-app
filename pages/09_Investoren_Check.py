"""
Stillhalter AI App — Legendäre Investoren-Check
5 weltberühmte Hedge-Fund-Manager bewerten einen Trade nach ihren Prinzipien.
"""

import streamlit as st
import yfinance as yf
import math
from datetime import date, datetime, timedelta
from typing import Optional, Dict, List, Tuple

st.set_page_config(
    page_title="Investoren-Check · Stillhalter AI App",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# INVESTOR PROFILE DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════

INVESTORS = {
    "buffett": {
        "name":    "Warren Buffett",
        "title":   "Value-Investor · Berkshire Hathaway",
        "avatar":  "🎩",
        "color":   "#f59e0b",
        "style":   "Langfristiger Value-Investor. Kauft hervorragende Unternehmen zu fairen Preisen.",
        "rules": {
            "pe_max":        25,     # KGV max. 25
            "pb_max":        5,      # KBV max. 5
            "roe_min":       15,     # ROE mindestens 15%
            "debt_eq_max":   1.5,    # Debt/Equity max 1.5
            "div_yield_min": 0,      # Dividende nicht zwingend
            "dte_max":       90,     # max. 90 Tage Laufzeit akzeptiert
            "opt_type_ok":   ["CALL"],  # Buffett kauft Calls wenn bullish; skeptisch bei Puts als Spekulation
        },
        "quotes": {
            "buy":      "Kauf einen wundervollen Betrieb zu einem fairen Preis.",
            "wait":     "Geduld ist der Schlüssel. Nicht jedes Pitch schlagen.",
            "against":  "Ich verstehe keine spekulativen Wetten. Das ist keine Investition.",
        },
        "weights": {"quality": 0.35, "value": 0.30, "trend": 0.10, "risk": 0.25},
    },
    "munger": {
        "name":    "Charlie Munger",
        "title":   "Mentale Modelle · Poor Charlie's Almanack",
        "avatar":  "📚",
        "color":   "#8b5cf6",
        "style":   "Multidisziplinäres Denken. Meidet Komplexität, sucht offensichtliche Qualität.",
        "rules": {
            "pe_max":        30,
            "margin_min":    15,     # Nettomarge min. 15%
            "dte_max":       60,
            "opt_type_ok":   ["CALL", "PUT"],
        },
        "quotes": {
            "buy":      "Invert, always invert. Wenn es sich aufdrängt — dann ja.",
            "wait":     "Die meisten Menschen sollten nichts tun. Abwarten ist eine Position.",
            "against":  "Das ist zu komplex. Bleib im Circle of Competence.",
        },
        "weights": {"quality": 0.45, "value": 0.25, "trend": 0.05, "risk": 0.25},
    },
    "dalio": {
        "name":    "Ray Dalio",
        "title":   "All Weather · Bridgewater Associates",
        "avatar":  "🌊",
        "color":   "#06b6d4",
        "style":   "Makro-Investor. Risk Parity, Diversifikation und Verständnis der Wirtschaftsmaschine.",
        "rules": {
            "spy_regime_ok": ["bullish"],   # Markt-Regime für Calls
            "dte_min":       30,            # Dalio denkt langfristiger
            "iv_ok":         ["sehr günstig", "günstig", "normal"],
        },
        "quotes": {
            "buy":      "Diversifiziere klug. Dieser Trade passt in das Makro-Bild.",
            "wait":     "Das Makro-Regime ist unklar. Erst wenn die Maschine läuft.",
            "against":  "Das ist konzentriertes Risiko. Wo ist die Absicherung?",
        },
        "weights": {"quality": 0.20, "value": 0.15, "trend": 0.40, "risk": 0.25},
    },
    "ackman": {
        "name":    "Bill Ackman",
        "title":   "Activist Investor · Pershing Square",
        "avatar":  "🦁",
        "color":   "#ef4444",
        "style":   "Hochkonzentrierte Wetten auf unterbewertete Unternehmen mit Katalysator.",
        "rules": {
            "score_min":     5,      # STI-Score mindestens 5
            "iv_max_ratio":  1.8,    # IV nicht zu teuer
            "dte_min":       45,     # Ackman braucht Zeit für Thesen
        },
        "quotes": {
            "buy":      "Das ist eine asymmetrische Wette. Ich bin dabei — mit voller Überzeugung.",
            "wait":     "Die Thesis stimmt, aber der Katalysator fehlt noch.",
            "against":  "Zu kurzfristig gedacht. Das ist kein Investment, das ist Zocken.",
        },
        "weights": {"quality": 0.25, "value": 0.20, "trend": 0.35, "risk": 0.20},
    },
    "simons": {
        "name":    "Jim Simons",
        "title":   "Quantitative Strategien · Renaissance Technologies",
        "avatar":  "🤖",
        "color":   "#22c55e",
        "style":   "Rein datengetrieben. Statistische Muster, Erwartungswert, Wahrscheinlichkeiten.",
        "rules": {
            "score_min":     4,      # Signal-Score
            "ev_positive":   True,   # Positiver Erwartungswert notwendig
            "win_rate_min":  50,     # Win-Rate mindestens 50%
        },
        "quotes": {
            "buy":      "Die Statistik spricht für diesen Trade. Erwartungswert ist positiv.",
            "wait":     "Ungenügende Datenlage. Mehr Samples nötig.",
            "against":  "Die Wahrscheinlichkeiten rechtfertigen das Risiko nicht.",
        },
        "weights": {"quality": 0.15, "value": 0.10, "trend": 0.50, "risk": 0.25},
    },
}

# ══════════════════════════════════════════════════════════════════════════════
# SCORING ENGINE
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_fundamentals(ticker: str) -> Dict:
    """Lädt Fundamental-Daten via yfinance."""
    out = {
        "pe": None, "pb": None, "ps": None,
        "roe": None, "net_margin": None,
        "debt_equity": None, "div_yield": None,
        "market_cap": None, "sector": None, "name": None,
        "price": None, "iv_hv_ratio": None,
    }
    try:
        t    = yf.Ticker(ticker)
        info = t.info or {}
        out["pe"]           = info.get("trailingPE") or info.get("forwardPE")
        out["pb"]           = info.get("priceToBook")
        out["ps"]           = info.get("priceToSalesTrailing12Months")
        out["roe"]          = (info.get("returnOnEquity") or 0) * 100
        out["net_margin"]   = (info.get("profitMargins") or 0) * 100
        out["debt_equity"]  = info.get("debtToEquity")
        out["div_yield"]    = (info.get("dividendYield") or 0) * 100
        out["market_cap"]   = info.get("marketCap")
        out["sector"]       = info.get("sector", "")
        out["name"]         = info.get("shortName", ticker)
        out["price"]        = info.get("currentPrice") or info.get("regularMarketPrice")
    except Exception:
        pass
    return out


def _score_investor(
    investor_key: str,
    ticker: str,
    opt_type: str,      # "CALL" or "PUT"
    dte: int,
    premium: float,
    strike: float,
    score_sti: int,
    iv_rating: str,
    spy_regime: str,
    win_rate: Optional[float] = None,
    ev: Optional[float] = None,
) -> Dict:
    """Berechnet Zustimmung eines Investors (0–100%)."""
    inv  = INVESTORS[investor_key]
    rules = inv["rules"]
    fund  = _fetch_fundamentals(ticker)

    points      = 0
    max_points  = 0
    reasons_ok  = []
    reasons_nok = []

    def _add(ok: bool, pts: int, label_ok: str, label_nok: str):
        nonlocal points, max_points
        max_points += pts
        if ok:
            points += pts
            reasons_ok.append(label_ok)
        else:
            reasons_nok.append(label_nok)

    # ── Qualität ──────────────────────────────────────────────────────────────
    if "roe_min" in rules:
        roe = fund.get("roe") or 0
        _add(roe >= rules["roe_min"], 15,
             f"ROE {roe:.1f}% ≥ {rules['roe_min']}% ✓",
             f"ROE {roe:.1f}% zu niedrig (min. {rules['roe_min']}%)")

    if "margin_min" in rules:
        nm = fund.get("net_margin") or 0
        _add(nm >= rules["margin_min"], 15,
             f"Nettomarge {nm:.1f}% stark ✓",
             f"Nettomarge {nm:.1f}% zu dünn (min. {rules['margin_min']}%)")

    if "debt_eq_max" in rules:
        de = fund.get("debt_equity") or 0
        _add(de <= rules["debt_eq_max"], 10,
             f"Verschuldung D/E={de:.1f} solide ✓",
             f"D/E={de:.1f} — zu viel Schulden")

    # ── Bewertung ─────────────────────────────────────────────────────────────
    if "pe_max" in rules:
        pe = fund.get("pe")
        if pe and pe > 0:
            _add(pe <= rules["pe_max"], 15,
                 f"KGV {pe:.1f} fair bewertet ✓",
                 f"KGV {pe:.1f} zu teuer (max. {rules['pe_max']})")
        else:
            max_points += 15   # neutral — zählt nicht gegen

    if "pb_max" in rules:
        pb = fund.get("pb")
        if pb and pb > 0:
            _add(pb <= rules["pb_max"], 10,
                 f"KBV {pb:.1f} akzeptabel ✓",
                 f"KBV {pb:.1f} zu hoch (max. {rules['pb_max']})")

    # ── Trend & Signal ────────────────────────────────────────────────────────
    if "score_min" in rules:
        _add(score_sti >= rules["score_min"], 20,
             f"STI-Score {score_sti}/6 stark ✓",
             f"STI-Score {score_sti}/6 zu schwach (min. {rules['score_min']})")

    if "spy_regime_ok" in rules:
        _add(spy_regime in rules["spy_regime_ok"], 15,
             f"Markt-Regime '{spy_regime}' passt ✓",
             f"Markt-Regime '{spy_regime}' — Gegenwind")

    if "ev_positive" in rules and ev is not None:
        _add(ev > 0, 20,
             f"Erwartungswert +{ev:.0f}% positiv ✓",
             f"Erwartungswert {ev:.0f}% — negativ!")

    if "win_rate_min" in rules and win_rate is not None:
        _add(win_rate >= rules["win_rate_min"], 10,
             f"Win-Rate {win_rate:.0f}% ≥ {rules['win_rate_min']}% ✓",
             f"Win-Rate {win_rate:.0f}% zu niedrig")

    # ── Risiko & Optionsprofil ────────────────────────────────────────────────
    if "dte_max" in rules:
        _add(dte <= rules["dte_max"], 10,
             f"Laufzeit {dte}T im Rahmen ✓",
             f"Laufzeit {dte}T zu lang (max. {rules['dte_max']}T)")

    if "dte_min" in rules:
        _add(dte >= rules["dte_min"], 10,
             f"Laufzeit {dte}T ausreichend ✓",
             f"Laufzeit {dte}T zu kurz (min. {rules['dte_min']}T)")

    if "iv_ok" in rules:
        _add(iv_rating in rules["iv_ok"], 10,
             f"IV '{iv_rating}' akzeptabel ✓",
             f"IV '{iv_rating}' zu teuer")

    if "opt_type_ok" in rules:
        _add(opt_type in rules["opt_type_ok"], 10,
             f"{opt_type} — passt zur Strategie ✓",
             f"{opt_type} — passt nicht zur Philosophie")

    score_pct = round(points / max_points * 100) if max_points > 0 else 50

    if score_pct >= 70:
        verdict = "zustimmend"
        verdict_icon = "✅"
    elif score_pct >= 45:
        verdict = "abwartend"
        verdict_icon = "🤔"
    else:
        verdict = "ablehnend"
        verdict_icon = "❌"

    quote_key = "buy" if score_pct >= 70 else ("wait" if score_pct >= 45 else "against")
    quote = inv["quotes"][quote_key]

    return {
        "score_pct":   score_pct,
        "verdict":     verdict,
        "verdict_icon": verdict_icon,
        "quote":       quote,
        "reasons_ok":  reasons_ok[:4],
        "reasons_nok": reasons_nok[:3],
        "fund":        fund,
    }


# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.html(f"""
<div style='display:flex;align-items:center;gap:16px;margin-bottom:8px'>
  {get_logo_html(height=44)}
  <div style='border-left:1px solid #222;height:40px;margin:0 4px'></div>
  <div>
    <div style='font-size:1.4rem;font-weight:800;color:#f0f0f0;font-family:sans-serif'>
      🧠 Legendäre Investoren-Check
    </div>
    <div style='font-size:0.8rem;color:#666;font-family:sans-serif'>
      Würden Buffett, Munger, Dalio, Ackman &amp; Simons diesen Trade machen?
    </div>
  </div>
</div>
""")

st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# INPUT FORM
# ══════════════════════════════════════════════════════════════════════════════
st.html("""
<div style='font-size:0.9rem;font-weight:700;color:#d4a843;font-family:sans-serif;
     margin-bottom:12px'>📝 Trade-Details eingeben</div>
""")

with st.form("investor_check_form"):
    fc1, fc2, fc3, fc4, fc5 = st.columns([2, 1.5, 1.5, 1.5, 1.5])
    with fc1:
        ticker_input = st.text_input("Ticker", value="AAPL", placeholder="z.B. AAPL",
                                     help="US-Aktiensymbol").upper().strip()
    with fc2:
        opt_type_input = st.selectbox("Option-Typ", ["CALL", "PUT"])
    with fc3:
        strike_input = st.number_input("Strike ($)", min_value=1.0, value=200.0, step=1.0)
    with fc4:
        premium_input = st.number_input("Prämie ($)", min_value=0.01, value=5.0, step=0.5,
                                        help="Optionspreis, den du bezahlst")
    with fc5:
        dte_input = st.number_input("DTE (Tage)", min_value=1, max_value=730, value=45, step=5)

    fc6, fc7, fc8 = st.columns([2, 2, 2])
    with fc6:
        sti_score = st.slider("STI-Score", min_value=-6, max_value=6, value=5,
                              help="Score aus der Trend-Signale-Seite")
    with fc7:
        iv_rating_input = st.selectbox(
            "IV-Rating", ["sehr günstig", "günstig", "normal", "erhöht", "teuer"]
        )
    with fc8:
        spy_regime_input = st.selectbox("SPY Markt-Regime", ["bullish", "neutral", "bearish"])

    fw1, fw2, fw3 = st.columns(3)
    with fw1:
        win_rate_input = st.number_input("Backtest Win-Rate (%)", 0.0, 100.0, 60.0, 5.0,
                                         help="Von der Trend-Signale Seite")
    with fw2:
        ev_input = st.number_input("Backtest Erwartungswert (%)", -100.0, 500.0, 50.0, 10.0,
                                   help="EV aus dem Backtest")
    with fw3:
        st.write("")

    submitted = st.form_submit_button("🧠 Investoren befragen", type="primary",
                                      use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════════
# ERGEBNISSE
# ══════════════════════════════════════════════════════════════════════════════
if submitted:
    with st.spinner(f"Analysiere {ticker_input} mit 5 Investoren-Perspektiven…"):
        fund_data = _fetch_fundamentals(ticker_input)

    # Fundamentaldaten-Übersicht
    name_disp = fund_data.get("name") or ticker_input
    price_disp = fund_data.get("price")
    pe_disp    = fund_data.get("pe")
    pb_disp    = fund_data.get("pb")
    roe_disp   = fund_data.get("roe")
    nm_disp    = fund_data.get("net_margin")
    de_disp    = fund_data.get("debt_equity")
    sector_disp = fund_data.get("sector", "")

    def _fmt(v, suffix="", decimals=1):
        return f"{v:.{decimals}f}{suffix}" if v is not None else "–"

    st.html(f"""
<div style='background:#0e0e0e;border:1px solid #1e1e1e;border-radius:10px;
     padding:16px;margin-bottom:20px'>
  <div style='font-size:0.78rem;font-weight:700;color:#d4a843;font-family:sans-serif;
       margin-bottom:10px'>📊 Fundamentaldaten — {name_disp} ({ticker_input})</div>
  <div style='display:flex;gap:12px;flex-wrap:wrap'>
    <div style='background:#111;border-radius:6px;padding:8px 14px;text-align:center'>
      <div style='font-size:0.6rem;color:#555;font-family:sans-serif'>Kurs</div>
      <div style='font-size:0.95rem;font-weight:700;color:#d4a843;font-family:monospace'>
        ${_fmt(price_disp)}</div>
    </div>
    <div style='background:#111;border-radius:6px;padding:8px 14px;text-align:center'>
      <div style='font-size:0.6rem;color:#555;font-family:sans-serif'>KGV</div>
      <div style='font-size:0.95rem;font-weight:700;color:#ccc;font-family:monospace'>
        {_fmt(pe_disp)}</div>
    </div>
    <div style='background:#111;border-radius:6px;padding:8px 14px;text-align:center'>
      <div style='font-size:0.6rem;color:#555;font-family:sans-serif'>KBV</div>
      <div style='font-size:0.95rem;font-weight:700;color:#ccc;font-family:monospace'>
        {_fmt(pb_disp)}</div>
    </div>
    <div style='background:#111;border-radius:6px;padding:8px 14px;text-align:center'>
      <div style='font-size:0.6rem;color:#555;font-family:sans-serif'>ROE</div>
      <div style='font-size:0.95rem;font-weight:700;color:#ccc;font-family:monospace'>
        {_fmt(roe_disp)}%</div>
    </div>
    <div style='background:#111;border-radius:6px;padding:8px 14px;text-align:center'>
      <div style='font-size:0.6rem;color:#555;font-family:sans-serif'>Nettomarge</div>
      <div style='font-size:0.95rem;font-weight:700;color:#ccc;font-family:monospace'>
        {_fmt(nm_disp)}%</div>
    </div>
    <div style='background:#111;border-radius:6px;padding:8px 14px;text-align:center'>
      <div style='font-size:0.6rem;color:#555;font-family:sans-serif'>D/E Ratio</div>
      <div style='font-size:0.95rem;font-weight:700;color:#ccc;font-family:monospace'>
        {_fmt(de_disp)}</div>
    </div>
    <div style='background:#111;border-radius:6px;padding:8px 14px;text-align:center'>
      <div style='font-size:0.6rem;color:#555;font-family:sans-serif'>Sektor</div>
      <div style='font-size:0.95rem;font-weight:700;color:#ccc;font-family:sans-serif'>
        {sector_disp or "–"}</div>
    </div>
  </div>
</div>
""")

    # ── Investoren-Karten ──────────────────────────────────────────────────────
    direction_from_type = "bullish" if opt_type_input == "CALL" else "bearish"

    scores_all = {}
    for key in INVESTORS:
        scores_all[key] = _score_investor(
            investor_key=key,
            ticker=ticker_input,
            opt_type=opt_type_input,
            dte=dte_input,
            premium=premium_input,
            strike=strike_input,
            score_sti=abs(sti_score),
            iv_rating=iv_rating_input,
            spy_regime=spy_regime_input,
            win_rate=win_rate_input,
            ev=ev_input,
        )

    # Layout: 2+3 Karten
    row1 = ["buffett", "munger"]
    row2 = ["dalio", "ackman", "simons"]

    for inv_keys in [row1, row2]:
        cols = st.columns(len(inv_keys))
        for col, key in zip(cols, inv_keys):
            inv  = INVESTORS[key]
            res  = scores_all[key]
            pct  = res["score_pct"]
            verd = res["verdict"]
            icon = res["verdict_icon"]
            color = inv["color"]

            bar_col = "#22c55e" if pct >= 70 else ("#f59e0b" if pct >= 45 else "#ef4444")
            bg_color = "#0a140a" if pct >= 70 else ("#0e0e08" if pct >= 45 else "#140a0a")

            ok_html = "".join(
                f"<div style='font-size:0.68rem;color:#22c55e;padding:2px 0;"
                f"font-family:sans-serif'>✓ {r}</div>"
                for r in res["reasons_ok"]
            )
            nok_html = "".join(
                f"<div style='font-size:0.68rem;color:#ef4444;padding:2px 0;"
                f"font-family:sans-serif'>✗ {r}</div>"
                for r in res["reasons_nok"]
            )

            with col:
                st.html(f"""
<div style='background:{bg_color};border:1px solid {color}44;border-top:3px solid {color};
     border-radius:12px;padding:16px;height:100%'>

  <div style='display:flex;align-items:center;gap:10px;margin-bottom:10px'>
    <span style='font-size:2rem'>{inv["avatar"]}</span>
    <div>
      <div style='font-size:0.88rem;font-weight:800;color:{color};font-family:sans-serif'>
        {inv["name"]}</div>
      <div style='font-size:0.65rem;color:#666;font-family:sans-serif'>{inv["title"]}</div>
    </div>
  </div>

  <!-- Zustimmungs-Balken -->
  <div style='margin-bottom:12px'>
    <div style='display:flex;justify-content:space-between;margin-bottom:4px'>
      <span style='font-size:0.7rem;color:#888;font-family:sans-serif'>Zustimmung</span>
      <span style='font-size:0.85rem;font-weight:700;color:{bar_col};font-family:sans-serif'>
        {icon} {pct}%</span>
    </div>
    <div style='background:#1a1a1a;border-radius:4px;height:8px'>
      <div style='width:{pct}%;height:100%;background:{bar_col};border-radius:4px;
           transition:width 0.5s'></div>
    </div>
    <div style='font-size:0.65rem;color:#555;margin-top:3px;font-family:sans-serif;
         text-align:right;text-transform:uppercase;letter-spacing:0.05em'>{verd}</div>
  </div>

  <!-- Zitat -->
  <div style='background:#0e0e0e;border-left:3px solid {color}88;border-radius:0 6px 6px 0;
       padding:8px 10px;margin-bottom:10px'>
    <div style='font-size:0.72rem;color:#aaa;font-family:sans-serif;
         font-style:italic;line-height:1.5'>
      &ldquo;{res["quote"]}&rdquo;
    </div>
  </div>

  <!-- Pro/Contra -->
  <div style='font-size:0.62rem;color:#555;text-transform:uppercase;
       letter-spacing:0.06em;margin-bottom:4px;font-family:sans-serif'>Begründung</div>
  {ok_html}
  {nok_html}

</div>
""")

    # ── Gesamturteil ───────────────────────────────────────────────────────────
    st.markdown("---")
    avg_score = sum(r["score_pct"] for r in scores_all.values()) / len(scores_all)
    approval_count = sum(1 for r in scores_all.values() if r["score_pct"] >= 70)
    wait_count     = sum(1 for r in scores_all.values() if 45 <= r["score_pct"] < 70)
    against_count  = sum(1 for r in scores_all.values() if r["score_pct"] < 45)

    overall_col = "#22c55e" if avg_score >= 65 else ("#f59e0b" if avg_score >= 45 else "#ef4444")
    overall_icon = "✅" if avg_score >= 65 else ("🤔" if avg_score >= 45 else "❌")
    overall_text = (
        "Breite Zustimmung — starke Grundlage für diesen Trade"
        if avg_score >= 65 else (
            "Gemischte Signale — abwägen und mit Vorsicht handeln"
            if avg_score >= 45 else
            "Mehrheitliche Ablehnung — Trade kritisch überdenken"
        )
    )

    st.html(f"""
<div style='background:linear-gradient(135deg,#0e0e0e,#111);
     border:2px solid {overall_col}44;border-radius:14px;padding:20px 24px;
     margin-top:8px'>
  <div style='display:flex;align-items:center;justify-content:space-between;
       flex-wrap:wrap;gap:12px'>
    <div>
      <div style='font-size:0.65rem;color:#555;text-transform:uppercase;
           letter-spacing:0.1em;font-family:sans-serif;margin-bottom:4px'>
        Gesamturteil der 5 Investoren</div>
      <div style='font-size:1.4rem;font-weight:800;color:{overall_col};
           font-family:sans-serif'>{overall_icon} {overall_text}</div>
    </div>
    <div style='display:flex;gap:16px'>
      <div style='text-align:center'>
        <div style='font-size:1.6rem;font-weight:800;color:#22c55e'>{approval_count}</div>
        <div style='font-size:0.65rem;color:#555;font-family:sans-serif'>Zustimmend</div>
      </div>
      <div style='text-align:center'>
        <div style='font-size:1.6rem;font-weight:800;color:#f59e0b'>{wait_count}</div>
        <div style='font-size:0.65rem;color:#555;font-family:sans-serif'>Abwartend</div>
      </div>
      <div style='text-align:center'>
        <div style='font-size:1.6rem;font-weight:800;color:#ef4444'>{against_count}</div>
        <div style='font-size:0.65rem;color:#555;font-family:sans-serif'>Ablehnend</div>
      </div>
      <div style='text-align:center'>
        <div style='font-size:1.6rem;font-weight:800;color:{overall_col}'>{avg_score:.0f}%</div>
        <div style='font-size:0.65rem;color:#555;font-family:sans-serif'>Ø Score</div>
      </div>
    </div>
  </div>
</div>
""")

    st.html("""
<div style='font-size:0.68rem;color:#444;font-family:sans-serif;margin-top:10px;
     line-height:1.6'>
  ⚠️ <b style='color:#555'>Haftungsausschluss:</b>
  Diese Analyse ist eine regelbasierte Simulation der bekannten Investment-Philosophien
  dieser Persönlichkeiten. Sie stellt keine echte Meinung der genannten Personen dar
  und ist keine Anlageberatung. Die Bewertungen basieren auf öffentlich zugänglichen
  Investmentprinzipien.
</div>
""")
