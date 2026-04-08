"""
Stillhalter AI App — Top 9 Trading Ideen des Tages
Separater Tab für die besten 3 Optionen pro IV-Klasse (Low/Mid/High).
"""

import streamlit as st
import pandas as pd
import pickle
import os
import math
from datetime import datetime

st.set_page_config(
    page_title="Top 9 Ideen · Stillhalter AI App",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)

from data.fetcher import (
    fetch_extended_hours_price, get_extended_hours_session, is_market_open,
)

# ── Header ─────────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.markdown(get_logo_html("white", 40), unsafe_allow_html=True)
with col_title:
    st.markdown("""
    <div style='padding-top:4px'>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.8rem;
                    color:#f0f0f0;letter-spacing:0.04em'>🏆 TOP 9 TRADING IDEEN</div>
        <div style='font-family:RedRose,sans-serif;font-weight:300;font-size:0.8rem;
                    color:#666;text-transform:uppercase;letter-spacing:0.12em;margin-top:2px'>
            Top 3 pro IV-Klasse · Aus letztem Scanner-Lauf · Community-Post Generator
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# Extended-Hours Session
ext_session = get_extended_hours_session()

# ── IV-Klassen in Sidebar ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ IV-Klassen Schwellenwerte")
    st.caption(
        "Tipp: Watchlist-Aktien (AAPL, MSFT, JPM…) haben meist IV 20–40%. "
        "Setze die Grenzen entsprechend um alle drei Klassen zu befüllen."
    )
    iv_thresh_low = st.slider("Low IV Grenze (%)", 10, 60, 20, 5,
                               help="IV unterhalb dieser Grenze = Low IV (Konservativ)")
    iv_thresh_mid = st.slider("Mid IV Grenze (%)", 20, 120, 40, 5,
                               help="IV unterhalb dieser Grenze = Mid IV (Ausgewogen)")
    st.caption(f"Low IV: 0–{iv_thresh_low}% · Mid IV: {iv_thresh_low}–{iv_thresh_mid}% · High IV: >{iv_thresh_mid}%")


# ── Cache-Datei ────────────────────────────────────────────────────────────────
CACHE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "last_scan_cache.pkl")


def load_top9_cache():
    if not os.path.exists(CACHE_PATH):
        return None, None, None
    try:
        with open(CACHE_PATH, "rb") as f:
            data = pickle.load(f)
        return data.get("results"), data.get("timestamp"), data.get("strategy", "Cash Covered Put")
    except Exception:
        return None, None, None


def get_risk_class(iv_pct, low=None, mid=None):
    low = low if low is not None else iv_thresh_low
    mid = mid if mid is not None else iv_thresh_mid
    if iv_pct <= low:
        return "A"
    elif iv_pct <= mid:
        return "B"
    else:
        return "C"


# ══════════════════════════════════════════════════════════════════════════════
# ENRICHMENT (gecacht 1h)
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(ttl=3600, show_spinner=False)
def enrich_top9_ticker(ticker: str, kurs: float, iv_pct: float) -> dict:
    """Holt Firmenname, TA-Signale und Roll-Potenzial."""
    result = {
        "company_name":     ticker,
        "trend_str":        "",
        "ema_str":          "",
        "macd_str":         "",
        "stoch_str":        "",
        "rsi":              None,
        "adx":              None,
        "above_ma50":       None,
        "above_ma200":      None,
        "support_near":     None,
        "support_dist_pct": None,
        "resistance_near":  None,
        "roll_usd":         0.0,
        "roll_pct":         0.0,
    }
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        name = info.get("shortName") or info.get("longName") or ticker
        result["company_name"] = name
    except Exception:
        pass

    try:
        from data.fetcher import fetch_price_history
        from analysis.technicals import analyze_technicals

        hist = fetch_price_history(ticker, period="6mo")
        if hist is not None and not hist.empty:
            tech = analyze_technicals(hist)
            if tech:
                trend_map = {"bullish": "↑ Aufwärtstrend", "bearish": "↓ Abwärtstrend", "neutral": "→ Seitwärts"}
                result["trend_str"]   = trend_map.get(tech.trend, "")
                result["above_ma50"]  = tech.above_sma50
                result["above_ma200"] = tech.above_sma200

                if tech.above_sma50 and tech.above_sma200:
                    result["ema_str"] = "MA50 > MA200 (bullisch)"
                elif tech.above_sma50 and not tech.above_sma200:
                    result["ema_str"] = "Über MA50, unter MA200"
                elif not tech.above_sma50 and tech.above_sma200:
                    result["ema_str"] = "Unter MA50, über MA200"
                else:
                    result["ema_str"] = "Unter MA50 & MA200 (bärisch)"

                if tech.sc_macd:
                    macd_map = {
                        "strong_bull": f"MACD Pro: STARK bullisch ⬆⬆ (ADX {tech.sc_macd.adx_val:.0f})",
                        "bull":        f"MACD Pro: bullisch ⬆ (ADX {tech.sc_macd.adx_val:.0f})",
                        "neutral":     "MACD Pro: neutral",
                        "bear":        f"MACD Pro: bearisch ⬇ (ADX {tech.sc_macd.adx_val:.0f})",
                        "strong_bear": f"MACD Pro: STARK bearisch ⬇⬇ (ADX {tech.sc_macd.adx_val:.0f})",
                    }
                    result["macd_str"] = macd_map.get(tech.sc_macd.signal_strength, "")
                    result["adx"] = tech.sc_macd.adx_val

                if tech.dual_stoch:
                    ss = tech.dual_stoch.signal_strength
                    stoch_map = {
                        "strong_buy":  "Dual Stoch: stark überverkauft ✅✅",
                        "buy":         "Dual Stoch: überverkauft ✅",
                        "neutral":     "",
                        "sell":        "Dual Stoch: überkauft ⚠️",
                        "strong_sell": "Dual Stoch: stark überkauft ❌",
                    }
                    result["stoch_str"] = stoch_map.get(ss, "")

                if tech.support_levels:
                    below = [s for s in tech.support_levels if s < kurs]
                    if below:
                        nearest_sup = max(below)
                        result["support_near"]     = nearest_sup
                        result["support_dist_pct"] = (kurs - nearest_sup) / kurs * 100
                if tech.resistance_levels:
                    above = [r for r in tech.resistance_levels if r > kurs]
                    if above:
                        result["resistance_near"] = min(above)

                close = hist["Close"]
                delta_c = close.diff()
                gain  = delta_c.clip(lower=0)
                loss  = (-delta_c).clip(lower=0)
                avg_g = gain.ewm(alpha=1/14, adjust=False).mean()
                avg_l = loss.ewm(alpha=1/14, adjust=False).mean()
                rs    = avg_g / avg_l.replace(0, 1e-10)
                result["rsi"] = float((100 - (100 / (1 + rs))).iloc[-1])
    except Exception:
        pass

    if iv_pct > 0 and kurs > 0:
        weekly_iv = (iv_pct / 100) / math.sqrt(52)
        result["roll_usd"] = round(kurs * weekly_iv, 2)
        result["roll_pct"] = round(weekly_iv * 100, 2)

    return result


# ══════════════════════════════════════════════════════════════════════════════
# ABSICHERUNGS-AMPEL
# ══════════════════════════════════════════════════════════════════════════════

def _hedge_pills_html(row: dict, tech: dict, strategy: str) -> str:
    otm      = float(row.get("OTM %", 0))
    delta    = float(row.get("Delta", 0))
    iv_pct   = float(row.get("IV %", 0))
    earnings = str(row.get("⚠️ Earnings", ""))
    strike   = float(row.get("Strike", 0))
    is_put   = "Put" in strategy or "put" in strategy.lower()

    trend_str    = tech.get("trend_str", "")
    support_near = tech.get("support_near")

    checks = []
    if is_put:
        if "↑" in trend_str:   checks.append(("Trend ↑", "ok"))
        elif "↓" in trend_str: checks.append(("Trend ↓ !", "bad"))
        else:                  checks.append(("Trend →", "warn"))
    else:
        if "↑" in trend_str:   checks.append(("Trend ↑", "warn"))
        elif "↓" in trend_str: checks.append(("Trend ↓", "ok"))
        else:                  checks.append(("Trend →", "ok"))

    if support_near and strike > 0:
        dist = (strike - support_near) / strike * 100
        if dist >= 3:   checks.append((f"Strike +{dist:.0f}% über Sup.", "ok"))
        elif dist >= 0: checks.append((f"Strike nahe Sup. ({dist:.0f}%)", "warn"))
        else:           checks.append(("Strike unter Sup.", "bad"))
    else:
        checks.append((f"OTM-Puffer {otm:.1f}%", "ok" if otm >= 5 else "warn"))

    if otm >= 8:    checks.append((f"OTM {otm:.0f}% (gut)", "ok"))
    elif otm >= 5:  checks.append((f"OTM {otm:.0f}% (ok)", "warn"))
    else:           checks.append((f"OTM {otm:.0f}% (eng)", "bad"))

    abs_d = abs(delta)
    if abs_d <= 0.20:   checks.append(("Delta konservativ", "ok"))
    elif abs_d <= 0.30: checks.append(("Delta ausgewogen", "warn"))
    else:               checks.append(("Delta aggressiv", "bad"))

    if iv_pct >= 25:    checks.append(("Rollbar ✓", "ok"))
    elif iv_pct >= 15:  checks.append(("Roll moderat", "warn"))
    else:               checks.append(("Roll schwierig", "bad"))

    if earnings and "⚠️" in earnings: checks.append(("Earnings in LZ!", "bad"))
    else:                              checks.append(("Kein Earnings-Risiko", "ok"))

    pill_css = {
        "ok":   "background:#0f2d18;color:#22c55e;border:1px solid #1a5c2e",
        "warn": "background:#2d2200;color:#f59e0b;border:1px solid #5c4000",
        "bad":  "background:#2d0f0f;color:#ef4444;border:1px solid #5c1a1a",
    }
    pills = ""
    for label, status in checks:
        icon = "✅" if status == "ok" else ("⚠️" if status == "warn" else "❌")
        pills += (
            f"<span style='{pill_css[status]};border-radius:4px;padding:2px 7px;"
            f"font-size:0.68rem;margin:2px 2px;display:inline-block;white-space:nowrap'>"
            f"{icon} {label}</span>"
        )
    return f"<div style='line-height:1.8;margin-top:4px'>{pills}</div>"


# ══════════════════════════════════════════════════════════════════════════════
# COMMUNITY-POST TEXT
# ══════════════════════════════════════════════════════════════════════════════

def _build_share_text(row: dict, tech: dict, strategy: str) -> str:
    ticker   = str(row.get("Ticker", ""))
    company  = tech.get("company_name", ticker)
    kurs     = float(row.get("Kurs", 0))
    strike   = float(row.get("Strike", 0))
    verfall  = str(row.get("Verfall", ""))
    dte      = int(row.get("DTE", 0))
    praemie  = float(row.get("Prämie", 0))
    delta    = float(row.get("Delta", 0))
    iv_pct   = float(row.get("IV %", 0))
    otm      = float(row.get("OTM %", 0))
    rend_lz  = float(row.get("Rendite % Laufzeit", 0))
    rend_ann = float(row.get("Rendite ann. %", 0))
    crv      = float(row.get("CRV Score", 0))
    iv_rank  = str(row.get("IV Rank", "–"))
    sektor   = str(row.get("Sektor", ""))
    earnings = str(row.get("⚠️ Earnings", ""))

    praemie_usd  = praemie * 100
    einbuch_pct  = abs(delta) * 100
    roll_usd     = tech.get("roll_usd", 0.0)

    try:
        vd = datetime.strptime(verfall[:10], "%Y-%m-%d")
        verfall_fmt = vd.strftime("%b %d '%y")
    except Exception:
        verfall_fmt = verfall[:10]

    is_put      = "Put" in strategy or "put" in strategy.lower()
    action      = "PUT verkaufen" if is_put else "CALL verkaufen"
    strat_short = "Short PUT" if is_put else "Covered CALL"

    trend_str = tech.get("trend_str", "")
    ema_str   = tech.get("ema_str", "")
    macd_str  = tech.get("macd_str", "")
    stoch_str = tech.get("stoch_str", "")
    rsi       = tech.get("rsi")
    support   = tech.get("support_near")

    ta_parts = []
    if trend_str: ta_parts.append(trend_str)
    if ema_str:   ta_parts.append(ema_str)
    if macd_str:  ta_parts.append(macd_str)
    if stoch_str: ta_parts.append(stoch_str)
    if rsi is not None: ta_parts.append(f"RSI {rsi:.0f}")
    ta_text = "\n".join(f"  • {p}" for p in ta_parts) if ta_parts else "  Daten werden geladen..."

    if support:
        sup_dist = (strike - support) / strike * 100
        absich_sup = (
            f"  • Strike {sup_dist:.1f}% über nächster Unterstützung USD {support:.2f}\n"
            if sup_dist > 0 else f"  • Nächste Unterstützung bei USD {support:.2f}\n"
        )
    else:
        absich_sup = f"  • OTM-Puffer {otm:.1f}% zum aktuellen Kurs\n"

    delta_label = (
        "konservativ (≤20%)" if einbuch_pct <= 20
        else "ausgewogen (21–30%)" if einbuch_pct <= 30
        else "aggressiv (>30%)"
    )
    earnings_line = (
        f"\n⚠️  Achtung: Earnings innerhalb der Laufzeit ({earnings})\n"
        if earnings and "⚠️" in earnings else ""
    )

    return (
        f"🔔 Trading Idee | {ticker} {verfall_fmt} @{strike:.0f} {action}\n"
        f"\n"
        f"💰 Prämie: {praemie:.2f} USD | {praemie_usd:.0f} USD gesamt (1x Kontrakt)\n"
        f"📈 Rendite: ~{rend_ann:.1f}% p.a. / {rend_lz:.2f}% Laufzeit ({dte}T)\n"
        f"📉 Strategie: {strat_short}\n"
        f"🎯 Strike: USD {strike:.2f} ({otm:.1f}% OTM)\n"
        f"📅 Laufzeit: {verfall_fmt} ({dte} Tage)\n"
        f"⚡ Einbuchungswahrscheinlichkeit: ~{einbuch_pct:.0f}% (Delta {delta:.2f})\n"
        f"{earnings_line}"
        f"\n"
        f"📊 Technische Analyse (1D):\n"
        f"{ta_text}\n"
        f"\n"
        f"🔄 Roll-Potenzial: ±USD {roll_usd:.2f} pro Woche (1σ bei IV {iv_pct:.0f}%)\n"
        f"   → Rollbar auf Strike -{roll_usd:.2f} nach einer Woche möglich\n"
        f"\n"
        f"🛡️ Absicherung:\n"
        f"{absich_sup}"
        f"  • Delta {delta:.2f} — Einbuchungsrisiko {delta_label}\n"
        f"  • {'Rollbar (IV ausreichend hoch)' if iv_pct >= 20 else 'Roll prüfen (geringe IV)'}\n"
        f"  • Cash Reserve: USD {strike * 100:,.0f} pro Kontrakt einplanen\n"
        f"\n"
        f"⭐ CRV Score: {crv:.0f}  ·  IV Rank: {iv_rank}  ·  Sektor: {sektor}\n"
        f"🏢 {company}\n"
        f"\n"
        f"— Stillhalter AI App Dashboard"
    )


# ══════════════════════════════════════════════════════════════════════════════
# QUICK SCAN
# ══════════════════════════════════════════════════════════════════════════════

def _run_quick_scan(strategy="Cash Covered Put"):
    """Scannt die komplette Watchlist und speichert Ergebnisse im Cache."""
    from analysis.batch_screener import scan_watchlist
    from data.watchlist import ALL_TICKERS
    import pickle as _pickle
    import datetime as _dt

    tickers = ALL_TICKERS
    progress_bar = st.progress(0.0)
    status_ph    = st.empty()
    live_partial = []

    def on_progress(current, total_n, ticker):
        progress_bar.progress(min(current / max(total_n, 1), 1.0))
        status_ph.markdown(
            f"⚡ Scanne `{ticker}` ({current}/{total_n}) — "
            f"{len(live_partial)} Aktien mit Treffern"
        )

    def on_result(ticker_r, df_r):
        live_partial.append(df_r)

    results = scan_watchlist(
        tickers=tickers,
        strategy=strategy,
        delta_min=-0.35, delta_max=-0.05,
        dte_min=14,      dte_max=60,
        iv_min=0.15,     premium_min=0.05,
        min_oi=5,        otm_min=3.0,   otm_max=50.0,
        progress_callback=on_progress,
        result_callback=on_result,
    )

    progress_bar.empty()
    status_ph.empty()

    if not results.empty:
        try:
            cache_path = os.path.join(os.path.dirname(__file__), "..", "data", "last_scan_cache.pkl")
            with open(cache_path, "wb") as f:
                _pickle.dump({
                    "results":   results,
                    "timestamp": _dt.datetime.now(),
                    "strategy":  strategy,
                }, f)
            st.success(
                f"✅ Scan abgeschlossen — **{len(results)} Optionen** aus "
                f"**{results['Ticker'].nunique()} Aktien** gespeichert"
            )
            st.rerun()
        except Exception as exc:
            st.error(f"Cache-Fehler: {exc}")
    else:
        st.warning("Keine Optionen gefunden — Markt möglicherweise geschlossen oder Daten nicht verfügbar.")


# ══════════════════════════════════════════════════════════════════════════════
# HAUPTDARSTELLUNG
# ══════════════════════════════════════════════════════════════════════════════

cached_results, cached_ts, cached_strategy = load_top9_cache()

# ── Cache-Status & Quick-Scan Banner ───────────────────────────────────────────
age_hours_global   = (datetime.now() - cached_ts).total_seconds() / 3600 if cached_ts else 9999
cache_stale        = age_hours_global > 6
freshness_color_g  = "#22c55e" if age_hours_global < 4 else ("#f59e0b" if age_hours_global < 24 else "#ef4444")
ts_str_g           = cached_ts.strftime("%d.%m.%Y %H:%M") if cached_ts else None
mkt_open           = is_market_open()

_qs_label = (
    "🚀 Scan jetzt starten" if cache_stale else "🔄 Scan aktualisieren"
)
_qs_expanded = (cached_results is None or cache_stale)

with st.expander(_qs_label, expanded=_qs_expanded):
    sq1, sq2 = st.columns([3, 2])
    with sq1:
        if ts_str_g:
            st.markdown(
                f"Letzter Scan: **{ts_str_g} Uhr** "
                f"<span style='color:{freshness_color_g}'>({age_hours_global:.0f}h ago)</span> "
                f"· Strategie: {cached_strategy or '–'}",
                unsafe_allow_html=True,
            )
        else:
            st.markdown("**Noch kein Scan gespeichert** — starte einen Watchlist-Scan um die Top 9 zu befüllen.")
        st.caption(
            "Scannt alle ~225 Aktien der Watchlist · Cash Covered Puts · "
            f"DTE 14–60 · Delta 0.05–0.35 · Dauer ca. 2–4 Minuten"
        )
    with sq2:
        qs_strat = st.selectbox(
            "Strategie", ["Cash Covered Put", "Covered Call"],
            key="qs_strategy", label_visibility="collapsed"
        )
    if st.button("🚀 Watchlist-Scan starten", type="primary", use_container_width=True,
                 key="btn_quickscan"):
        _run_quick_scan(qs_strat)

if cached_results is not None and not cached_results.empty:
    ts_str = cached_ts.strftime("%d.%m.%Y %H:%M") if cached_ts else "unbekannt"
    age_hours = age_hours_global
    freshness_color = freshness_color_g

    info_c1, info_c2 = st.columns([6, 2])
    with info_c1:
        st.html(
            f"<div style='font-size:0.8rem;color:#444;font-family:RedRose,sans-serif;margin-bottom:12px'>"
            f"Letzte Berechnung: <span style='color:{freshness_color}'>{ts_str} Uhr</span>"
            f" &nbsp;·&nbsp; Strategie: <span style='color:#888'>{cached_strategy}</span>"
            f" &nbsp;·&nbsp; <span style='color:#555'>Scan-Details → Scanner-Seite</span>"
            f"</div>"
        )
    with info_c2:
        st.page_link("pages/04_Watchlist_Scanner.py", label="→ Scanner starten", icon="🔍")

    df = cached_results.copy()
    if "IV %" in df.columns:
        df["_risk_class"] = df["IV %"].apply(lambda x: get_risk_class(x, iv_thresh_low, iv_thresh_mid))
    else:
        df["_risk_class"] = "B"

    CLASS_CONFIG = {
        "A": {
            "label":    f"🟢 LOW IV — Konservativ (≤{iv_thresh_low}%)",
            "subtitle": f"IV 0–{iv_thresh_low}% · Geringes Risiko · Stabile Aktien",
            "color":    "#22c55e", "border": "#0f3320", "bg": "#0a1a0f",
        },
        "B": {
            "label":    f"🟡 MID IV — Ausgewogen ({iv_thresh_low}–{iv_thresh_mid}%)",
            "subtitle": f"IV {iv_thresh_low}–{iv_thresh_mid}% · Mittleres Risiko · Gute Prämien",
            "color":    "#d4a843", "border": "#3a2f0a", "bg": "#1a1508",
        },
        "C": {
            "label":    f"🔴 HIGH IV — Aggressiv (>{iv_thresh_mid}%)",
            "subtitle": f"IV >{iv_thresh_mid}% · Hohes Risiko · Sehr hohe Prämien",
            "color":    "#ef4444", "border": "#3a1010", "bg": "#1a0a0a",
        },
    }

    # Enrichment für alle sichtbaren Ticker (max 9)
    visible = []
    for cls in ["A", "B", "C"]:
        for _, r in df[df["_risk_class"] == cls].head(3).iterrows():
            t  = str(r.get("Ticker", ""))
            k  = float(r.get("Kurs", 0))
            iv = float(r.get("IV %", 0))
            if t:
                visible.append((t, k, iv))

    enrich = {}
    if visible:
        with st.spinner("📊 Technische Analyse wird geladen..."):
            for ticker_e, kurs_e, iv_e in visible:
                if ticker_e not in enrich:
                    enrich[ticker_e] = enrich_top9_ticker(ticker_e, kurs_e, iv_e)

    # ── Klassen rendern ────────────────────────────────────────────────────────
    for cls in ["A", "B", "C"]:
        cfg    = CLASS_CONFIG[cls]
        cls_df = df[df["_risk_class"] == cls].head(3)

        st.html(f"""
        <div style='background:{cfg["bg"]};border:1px solid {cfg["border"]};
                    border-left:4px solid {cfg["color"]};border-radius:10px;
                    padding:12px 16px;margin:16px 0 8px 0'>
            <span style='font-family:sans-serif;font-weight:700;
                         color:{cfg["color"]};font-size:1rem;letter-spacing:0.06em'>
                {cfg["label"]}
            </span>
            <span style='font-family:sans-serif;font-size:0.78rem;
                         color:#666;margin-left:12px'>{cfg["subtitle"]}</span>
        </div>
        """)

        if cls_df.empty:
            st.html(f"""
            <div style='background:#0e0e0e;border:1px dashed #222;border-radius:8px;
                        padding:14px 18px;color:#444;font-family:sans-serif;
                        font-size:0.85rem;margin-bottom:16px;line-height:1.6'>
                <b style='color:#555'>Keine Optionen in Klasse {cls}</b><br>
                Im letzten Scan wurden keine Optionen mit dieser IV-Range gefunden.
                IV-Schwellenwerte links anpassen oder neuen Scan starten.
            </div>
            """)
            continue

        cols = st.columns(3, gap="small")
        for idx, (col, (_, row)) in enumerate(zip(cols, cls_df.iterrows())):
            rank_icon = ["🥇", "🥈", "🥉"][idx]

            ticker   = str(row.get("Ticker", ""))
            kurs     = float(row.get("Kurs", 0))
            strike   = float(row.get("Strike", 0))
            verfall  = str(row.get("Verfall", ""))
            dte      = int(row.get("DTE", 0))
            praemie  = float(row.get("Prämie", 0))
            crv      = float(row.get("CRV Score", 0))
            delta    = float(row.get("Delta", 0))
            iv_pct   = float(row.get("IV %", 0))
            otm      = float(row.get("OTM %", 0))
            rend_lz  = float(row.get("Rendite % Laufzeit", praemie / strike * 100 if strike > 0 else 0))
            rend_ann = float(row.get("Rendite ann. %", 0))
            rend_tag = float(row.get("Rendite %/Tag", rend_lz / max(1, dte)))
            tf_align = str(row.get("TF-Align", "–"))
            sektor   = str(row.get("Sektor", ""))
            iv_rank  = str(row.get("IV Rank", "–"))
            earnings = str(row.get("⚠️ Earnings", ""))

            praemie_usd = praemie * 100
            einbuch_pct = abs(delta) * 100
            trend_arrow = "↑" if "Aufwärts" in str(row.get("Trend","")) else ("↓" if "Abwärts" in str(row.get("Trend","")) else "→")
            trend_c     = "#22c55e" if trend_arrow == "↑" else ("#ef4444" if trend_arrow == "↓" else "#f59e0b")

            try:
                vd = datetime.strptime(verfall[:10], "%Y-%m-%d")
                verfall_fmt   = vd.strftime("%d. %b %Y")
                verfall_short = vd.strftime("%b '%y")
            except Exception:
                verfall_fmt   = verfall[:10]
                verfall_short = verfall[:7]

            # Extended Hours
            ext = {}
            if ext_session:
                try:
                    ext = fetch_extended_hours_price(ticker)
                except Exception:
                    ext = {}

            # Enrichment
            tech      = enrich.get(ticker, {"company_name": ticker, "roll_usd": 0.0})
            company   = tech.get("company_name", ticker)
            roll_usd  = tech.get("roll_usd", 0.0)
            rsi_val   = tech.get("rsi")
            support   = tech.get("support_near")
            macd_str  = tech.get("macd_str", "")
            stoch_str = tech.get("stoch_str", "")
            ema_str   = tech.get("ema_str", "")

            # TA-Begründung
            ta_lines = []
            if tech.get("trend_str"): ta_lines.append(f"<b style='color:{trend_c}'>{tech['trend_str']}</b>")
            if ema_str:   ta_lines.append(ema_str)
            if macd_str:  ta_lines.append(macd_str)
            if stoch_str: ta_lines.append(stoch_str)
            if rsi_val is not None:
                rsi_c = "#ef4444" if rsi_val > 70 else ("#22c55e" if rsi_val < 30 else "#aaa")
                ta_lines.append(f"RSI <span style='color:{rsi_c}'>{rsi_val:.0f}</span>")
            if support:
                sup_dist = (kurs - support) / kurs * 100
                ta_lines.append(f"Support: USD {support:.2f} ({sup_dist:.1f}% unter Kurs)")
            ta_html = " &nbsp;·&nbsp; ".join(ta_lines) if ta_lines else "Technische Daten werden geladen…"

            # Strike vs Support
            if support and strike > 0:
                ssd = (strike - support) / strike * 100
                strike_sup_html = (
                    f"<span style='color:#22c55e'>+{ssd:.1f}% über Support</span>"
                    if ssd >= 2 else
                    f"<span style='color:#f59e0b'>nahe Support ({ssd:.1f}%)</span>"
                )
            else:
                strike_sup_html = f"<span style='color:#888'>{otm:.1f}% OTM</span>"

            # DTE-Dringlichkeit
            if dte <= 7:
                dte_color, dte_icon = "#ef4444", "🔴"
            elif dte <= 21:
                dte_color, dte_icon = "#f59e0b", "🟡"
            else:
                dte_color, dte_icon = "#22c55e", "🟢"

            # Extended-Hours Badge
            if ext:
                _ec   = ext.get("label_color", "#888")
                _el   = ext.get("label", "")
                _ep   = ext.get("price", 0.0)
                _echg = ext.get("change_pct", 0.0)
                _es   = "+" if _echg >= 0 else ""
                _ecc  = "#22c55e" if _echg >= 0 else "#ef4444"
                ext_badge = (
                    f"<span style='background:#1a1028;color:{_ec};border-radius:3px;"
                    f"padding:0 5px;font-size:0.58rem'>{_el}</span>"
                )
                ext_line = (
                    f"<div style='font-size:0.7rem;color:{_ecc};font-family:sans-serif'>"
                    f"{_es}{_echg:.2f}% &nbsp;·&nbsp; {_ep:.2f}</div>"
                )
            else:
                ext_badge = ext_line = ""

            hedge_html = _hedge_pills_html(row.to_dict(), tech, cached_strategy)
            earn_badge = (
                f"<span style='background:#3a1010;color:#ef4444;border-radius:4px;"
                f"padding:1px 7px;font-size:0.68rem;margin-left:6px'>⚠️ Earnings</span>"
                if earnings and "⚠️" in earnings else ""
            )

            with col:
                st.html(f"""
                <div style='background:#111;border:1px solid #1e1e1e;border-radius:12px;
                            padding:14px;border-top:2px solid {cfg["color"]};margin-bottom:4px'>

                    <!-- Header -->
                    <div style='margin-bottom:6px'>
                        <div style='display:flex;justify-content:space-between;align-items:flex-start'>
                            <div>
                                <span style='font-size:1.2rem;font-weight:700;color:#f0f0f0;
                                             font-family:sans-serif'>{rank_icon} {ticker}</span>
                                {earn_badge}
                            </div>
                            <span style='font-size:0.65rem;color:#444;font-family:sans-serif;text-align:right'>{sektor}</span>
                        </div>
                        <div style='font-size:0.78rem;color:#888;font-family:sans-serif;
                                     margin-top:1px;font-style:italic'>{company}</div>
                    </div>

                    <!-- Kurs & Strike kompakt -->
                    <div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:6px'>
                        <div style='background:#0e0e0e;border-radius:5px;padding:5px 8px'>
                            <div style='font-size:0.6rem;color:#555;font-family:sans-serif;text-transform:uppercase'>Kurs {ext_badge}</div>
                            <div style='font-size:0.95rem;font-weight:600;color:#e0e0e0;font-family:sans-serif'>USD {kurs:.2f}</div>
                            {ext_line}
                        </div>
                        <div style='background:#0e0e0e;border-radius:5px;padding:5px 8px'>
                            <div style='font-size:0.6rem;color:#555;font-family:sans-serif;text-transform:uppercase'>Strike &nbsp; {strike_sup_html}</div>
                            <div style='font-size:0.95rem;font-weight:600;color:#e0e0e0;font-family:sans-serif'>USD {strike:.2f}</div>
                        </div>
                    </div>

                    <!-- Laufzeit-Banner (PROMINENT) -->
                    <div style='background:#0e0c0a;border:1px solid #2a2010;border-radius:7px;
                                padding:8px 12px;margin-bottom:6px;
                                display:flex;justify-content:space-between;align-items:center'>
                        <div>
                            <div style='font-size:0.6rem;color:#555;font-family:sans-serif;text-transform:uppercase;letter-spacing:0.06em'>📅 Verfall</div>
                            <div style='font-size:1.05rem;font-weight:700;color:#d4a843;font-family:sans-serif;margin-top:1px'>{verfall_fmt}</div>
                        </div>
                        <div style='text-align:right'>
                            <div style='font-size:0.6rem;color:#555;font-family:sans-serif;text-transform:uppercase;letter-spacing:0.06em'>Restlaufzeit</div>
                            <div style='font-size:1.5rem;font-weight:900;color:{dte_color};font-family:sans-serif;line-height:1'>
                                {dte_icon} {dte} <span style='font-size:0.72rem;font-weight:400;color:#888'>Tage</span>
                            </div>
                        </div>
                    </div>

                    <!-- Prämie + Rendite kompakt in einer Zeile -->
                    <div style='background:#0a120a;border:1px solid #1a2a1a;border-radius:7px;
                                padding:6px 10px;margin-bottom:6px;
                                display:grid;grid-template-columns:auto 1fr 1fr 1fr;gap:8px;align-items:center'>
                        <div style='font-size:0.65rem;color:#555;font-family:sans-serif'>💰</div>
                        <div style='text-align:center'>
                            <div style='font-size:0.58rem;color:#444;font-family:sans-serif'>Prämie</div>
                            <div style='font-size:0.88rem;font-weight:700;color:#d4a843;font-family:sans-serif'>{praemie:.2f} | {praemie_usd:.0f}$</div>
                        </div>
                        <div style='text-align:center;background:#0c1a0c;border-radius:4px;padding:2px 4px'>
                            <div style='font-size:0.58rem;color:#444;font-family:sans-serif'>ann.</div>
                            <div style='font-size:0.85rem;font-weight:700;color:#22c55e;font-family:sans-serif'>{rend_ann:.1f}%</div>
                        </div>
                        <div style='text-align:center;background:#0c1a0c;border-radius:4px;padding:2px 4px'>
                            <div style='font-size:0.58rem;color:#444;font-family:sans-serif'>LZ {dte}T</div>
                            <div style='font-size:0.85rem;font-weight:600;color:#4ade80;font-family:sans-serif'>{rend_lz:.2f}%</div>
                        </div>
                    </div>

                    <!-- TA-Begründung -->
                    <div style='background:#0c0f0c;border:1px solid #1a2a1a;border-radius:6px;
                                padding:6px 10px;margin-bottom:6px;
                                font-size:0.72rem;color:#999;font-family:sans-serif;line-height:1.6'>
                        <span style='color:#444;font-size:0.62rem;text-transform:uppercase;letter-spacing:0.07em'>📊 Technische Begründung</span><br>
                        {ta_html}
                    </div>

                    <!-- Delta + Roll in einer Zeile -->
                    <div style='display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:6px'>
                        <div style='background:#0e0e0e;border-radius:5px;padding:5px 8px'>
                            <div style='font-size:0.6rem;color:#555;font-family:sans-serif'>⚡ Einbuchung</div>
                            <div style='font-size:0.88rem;font-weight:700;color:#60a5fa;font-family:sans-serif'>
                                ~{einbuch_pct:.0f}% <span style='font-size:0.68rem;color:#444'>(Δ {delta:.2f})</span>
                            </div>
                        </div>
                        <div style='background:#0e0e0e;border-radius:5px;padding:5px 8px'>
                            <div style='font-size:0.6rem;color:#555;font-family:sans-serif'>🔄 Roll/Woche (1σ)</div>
                            <div style='font-size:0.88rem;font-weight:700;color:#a78bfa;font-family:sans-serif'>
                                ±{roll_usd:.2f}$ <span style='font-size:0.65rem;color:#444'>IV {iv_pct:.0f}%</span>
                            </div>
                        </div>
                    </div>

                    <!-- Absicherungs-Ampel -->
                    <div style='border-top:1px solid #1a1a1a;padding-top:6px;margin-bottom:6px'>
                        <div style='font-size:0.62rem;color:#444;text-transform:uppercase;letter-spacing:0.07em;margin-bottom:2px;font-family:sans-serif'>🛡️ Absicherung</div>
                        {hedge_html}
                    </div>

                    <!-- Footer Badges -->
                    <div style='display:flex;flex-wrap:wrap;gap:4px;margin-top:2px'>
                        <span style='background:#1a1a0a;color:{cfg["color"]};border-radius:4px;padding:2px 8px;font-size:0.7rem;font-family:sans-serif;font-weight:700'>⭐ CRV {crv:.0f}</span>
                        <span style='background:#0e0e0e;color:#60a5fa;border-radius:4px;padding:2px 8px;font-size:0.7rem;font-family:sans-serif'>TF {tf_align}</span>
                        <span style='background:#0e0e0e;color:#888;border-radius:4px;padding:2px 8px;font-size:0.7rem;font-family:sans-serif'>OTM {otm:.1f}%</span>
                        <span style='background:#0e0e0e;color:#888;border-radius:4px;padding:2px 8px;font-size:0.7rem;font-family:sans-serif'>IV {iv_pct:.0f}%  Rank {iv_rank}</span>
                    </div>
                </div>
                """)

                # Share-Button
                share_key = f"share_{cls}_{idx}"
                show_key  = f"show_{share_key}"
                share_text = _build_share_text(row.to_dict(), tech, cached_strategy)

                btn_col, _ = st.columns([2, 3])
                with btn_col:
                    if st.button("📋 Community-Post", key=share_key, use_container_width=True,
                                 help="Formatierten Post für die Community kopieren"):
                        st.session_state[show_key] = not st.session_state.get(show_key, False)

                if st.session_state.get(show_key, False):
                    st.text_area("Post kopieren:", value=share_text, height=340,
                                 key=f"txt_{share_key}",
                                 help="Text markieren → Strg+A → Strg+C")

        st.html("<div style='height:12px'></div>")

else:
    st.html("""
<div style='background:#111;border:1px dashed #222;border-radius:12px;
            padding:40px;text-align:center;margin-top:24px'>
    <div style='font-size:3rem;margin-bottom:12px'>🏆</div>
    <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.1rem;
                color:#555;letter-spacing:0.05em;margin-bottom:8px'>
        Noch kein Scan vorhanden
    </div>
    <div style='font-family:RedRose,sans-serif;font-size:0.88rem;color:#333;line-height:1.7'>
        Starte oben einen Watchlist-Scan — die Top 9 Optionen erscheinen dann automatisch hier.<br>
        Alternativ: Watchlist Scanner → Scan ausführen → Ergebnisse werden hier gespeichert.
    </div>
</div>
""")

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align:center;font-family:RedRose,sans-serif;font-size:0.76rem;color:#333;letter-spacing:0.08em'>
    STILLHALTER COMMUNITY · Daten: Yahoo Finance · Nicht als Finanzberatung zu verstehen
</div>
""", unsafe_allow_html=True)
