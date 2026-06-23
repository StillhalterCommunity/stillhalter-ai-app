"""
Stillhalter AI App — Trade Monitor
Live-Ticker für gespeicherte Trades — verfolgt jede Option bis zum Verfall.
"""

import streamlit as st
import pandas as pd
import json
import os
import math
from datetime import datetime, date

st.set_page_config(
    page_title="Trade Monitor · Stillhalter AI App",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
# Trade Monitor ist die öffentliche Tracking-Seite: geteilte Live-Tracking-Links
# (aus den Trade Cards) müssen ohne Login funktionieren — auch im Wartungsmodus.
render_sidebar(allow_public=True)

# ── Theme-Farben (hell im Grün-Theme, dunkel im Dark-Theme) ──────────────────────
_IS_GREEN = st.session_state.get("app_theme", "dark") == "green"
if _IS_GREEN:
    CARD_BG, CARD_BG2, CARD_BG3, CARD_BD = "#f6fdfb", "#eef8f5", "#eef8f5", "#b7e4c7"
    TXT_MAIN, TXT_SUB, TXT_MUTED = "#0a1628", "#475569", "#94a3b8"
else:
    CARD_BG, CARD_BG2, CARD_BG3, CARD_BD = "#111", "#0e0e0e", "#0a120a", "#1e1e1e"
    TXT_MAIN, TXT_SUB, TXT_MUTED = "#f0f0f0", "#888", "#555"

# ── Konstanten ─────────────────────────────────────────────────────────────────
# Trades persistent ablegen: auf dem Volume (STILLHALTER_DATA_DIR), damit sie
# Neustarts überleben und so lange verfolgbar bleiben, wie sie laufen.
_TRADES_DIR = os.environ.get("STILLHALTER_DATA_DIR", "").strip()
if _TRADES_DIR:
    MANUAL_TRADES_PATH = os.path.join(_TRADES_DIR, "manual_trades.json")
else:
    MANUAL_TRADES_PATH = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "data", "manual_trades.json"
    )

STATUS_COLORS = {
    "AKTIV":      "#22c55e",
    "WATCH":      "#f59e0b",
    "WARNING":    "#ef4444",
    "ROLL":       "#a78bfa",
    "CLOSE":      "#888",
    "EXPIRED":    "#555",
    "CANCELLED":  "#555",
}

# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def _load_trades() -> list:
    if not os.path.exists(MANUAL_TRADES_PATH):
        return []
    try:
        with open(MANUAL_TRADES_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_trades(trades: list) -> None:
    with open(MANUAL_TRADES_PATH, "w", encoding="utf-8") as f:
        json.dump(trades, f, ensure_ascii=False, indent=2)


def _update_trade_status(trade_id: str, new_status: str, note: str = "") -> None:
    trades = _load_trades()
    for t in trades:
        if t.get("trade_id") == trade_id:
            t["status"] = new_status
            if "status_log" not in t:
                t["status_log"] = []
            t["status_log"].append({
                "ts": datetime.now().isoformat(),
                "status": new_status,
                "note": note,
            })
    _save_trades(trades)


@st.cache_data(ttl=60, show_spinner=False)
def _fetch_current_price(ticker: str) -> float:
    # Über den gecachten Daten-Layer (yfinance + Disk-Cache) — zuverlässiger
    try:
        from data.fetcher import fetch_stock_info
        p = fetch_stock_info(ticker).get("price")
        if p and not math.isnan(float(p)):
            return float(p)
    except Exception:
        pass
    try:
        import yfinance as yf
        info = yf.Ticker(ticker).info
        v = float(
            info.get("currentPrice") or info.get("regularMarketPrice")
            or info.get("previousClose") or 0
        )
        return 0.0 if math.isnan(v) else v
    except Exception:
        return 0.0


@st.cache_data(ttl=120, show_spinner=False)
def _fetch_option_mid(ticker: str, expiry_str: str, strike: float, is_call: bool) -> float:
    """Aktueller Optionspreis (Mid). Bevorzugt Polygon/Massive, yfinance als Fallback."""
    # 1. Polygon/Massive (funktioniert zuverlässig, echte Greeks/Quotes)
    try:
        from data.fetcher import _massive_enabled
        if _massive_enabled():
            from data.massive_fetcher import get_options_chain
            df = get_options_chain(ticker, expiry_str, "call" if is_call else "put")
            if not df.empty:
                idx = (df["strike"].astype(float) - strike).abs().idxmin()
                row = df.loc[idx]
                mid = float(row.get("mid_price") or 0)
                if mid > 0:
                    return round(mid, 2)
                last = float(row.get("lastPrice") or 0)
                if last > 0:
                    return round(last, 2)
    except Exception:
        pass
    # 2. yfinance Fallback
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        chain = t.option_chain(expiry_str)
        df = chain.calls if is_call else chain.puts
        row = df[abs(df["strike"] - strike) < 0.01]
        if row.empty:
            row = df.iloc[(df["strike"] - strike).abs().argsort()[:1]]
        if row.empty:
            return 0.0
        bid = float(row["bid"].iloc[0])
        ask = float(row["ask"].iloc[0])
        if bid > 0 and ask > 0:
            return round((bid + ask) / 2, 2)
        return float(row["lastPrice"].iloc[0])
    except Exception:
        return 0.0


def _fmt_num(val: float, dec: int = 2) -> str:
    return f"{{:.{dec}f}}".format(val).replace(".", ",")


def _dte_from_expiry(expiry_str: str) -> int:
    try:
        d = pd.to_datetime(expiry_str).date()
        return max(0, (d - date.today()).days)
    except Exception:
        return 0


def _strike_str(s) -> str:
    """Schlichter Strike fürs OptionStrat-Format: 230 → '230', 222.5 → '222.5'."""
    return f"{float(s):g}"


@st.cache_data(ttl=1800, show_spinner=False)
def _snap_contract(ticker: str, expiry, strike: float, option_type: str):
    """Rastet (Verfall, Strike) auf einen echten handelbaren Kontrakt ein."""
    try:
        from data.massive_fetcher import nearest_contract
        return nearest_contract(ticker, expiry, strike, option_type)
    except Exception:
        return None, None


def _build_optionstrat_url(trade: dict) -> str:
    """Baut die OptionStrat-URL (echtes Format: schlichter Strike, x100 beim CC).
    Verfall + Strike werden auf einen existierenden Kontrakt eingerastet."""
    try:
        t = (trade.get("ticker") or "").upper()
        strike = float(trade.get("strike") or 0)
        if not t or strike <= 0:
            return ""
        strat = (trade.get("strategy") or "").lower()
        call_strike = float(trade.get("call_strike") or 0)

        if "strangle" in strat and call_strike > 0:
            pe, ps = _snap_contract(t, trade.get("expiry"), strike, "put")
            ce, cs = _snap_contract(t, trade.get("call_expiry") or trade.get("expiry"), call_strike, "call")
            if not pe:
                return ""
            pexp = pd.to_datetime(pe).strftime("%y%m%d")
            cexp = pd.to_datetime(ce or pe).strftime("%y%m%d")
            return (f"https://optionstrat.com/build/short-strangle/{t}"
                    f"/-.{t}{pexp}P{_strike_str(ps)},-.{t}{cexp}C{_strike_str(cs)}")
        if "call" in strat:   # Covered Call
            ce, cs = _snap_contract(t, trade.get("expiry"), strike, "call")
            if not ce:
                return ""
            exp = pd.to_datetime(ce).strftime("%y%m%d")
            return (f"https://optionstrat.com/build/covered-call/{t}"
                    f"/{t}x100,-.{t}{exp}C{_strike_str(cs)}")
        pe, ps = _snap_contract(t, trade.get("expiry"), strike, "put")
        if not pe:
            return ""
        exp = pd.to_datetime(pe).strftime("%y%m%d")
        return f"https://optionstrat.com/build/cash-secured-put/{t}/-.{t}{exp}P{_strike_str(ps)}"
    except Exception:
        return ""


def _pnl_color(pnl_pct: float) -> str:
    if pnl_pct >= 30:  return "#22c55e"
    if pnl_pct >= 0:   return "#4ade80"
    if pnl_pct >= -30: return "#f59e0b"
    return "#ef4444"


def _timeline_card_html(trade: dict, track_bg: str, txt_main: str,
                        txt_sub: str, txt_muted: str) -> str:
    """Kompakter Zeitstrahl pro Trade: Balkenfüllung = verstrichene Laufzeit,
    Farbe = Kurs-vs-Strike-Status (grün OK / gelb nah / rot im Geld)."""
    ticker   = trade.get("ticker", "–")
    strategy = trade.get("strategy", "–")
    cls      = trade.get("class", "–")
    strike   = float(trade.get("strike", 0) or 0)
    premium  = float(trade.get("premium", 0) or 0)
    expiry   = trade.get("expiry", "")
    is_call  = "Call" in strategy

    price   = _fetch_current_price(ticker)
    try:
        d_exp = pd.to_datetime(expiry)
        opt_mid = _fetch_option_mid(ticker, d_exp.strftime("%Y-%m-%d"), strike, is_call)
        end = d_exp.date()
    except Exception:
        opt_mid, end = 0.0, date.today()

    # Kurs-vs-Strike: Abstand (positiv = aus dem Geld) + ITM-Flag
    if price > 0 and strike > 0:
        otm = ((strike - price) / price * 100) if is_call else ((price - strike) / price * 100)
        itm = (price > strike) if is_call else (price < strike)
    else:
        otm, itm = 0.0, False
    if itm:
        col, word = "#ef4444", "🔴 Im Geld"
    elif abs(otm) < 3:
        col, word = "#f59e0b", "🟡 nah am Strike"
    else:
        col, word = "#22c55e", "🟢 OK"

    # Zeitstrahl: Abschluss → Verfall, Füllung = verstrichen
    start_raw = trade.get("created_at", "")
    try:
        start = pd.to_datetime(start_raw).date() if start_raw else (end - timedelta(days=45))
    except Exception:
        start = end - timedelta(days=45)
    today = date.today()
    total = max(1, (end - start).days)
    elapsed = min(total, max(0, (today - start).days))
    elapsed_pct = round(elapsed / total * 100)
    dte = max(0, (end - today).days)

    decay = ((premium - opt_mid) / premium * 100) if (premium > 0 and opt_mid > 0) else None

    # Handlungsempfehlung (kurz)
    if itm:
        action = "⚠️ Im Geld — beobachten oder rollen"
    elif dte <= 3:
        action = "⏳ Verfall nah — schließen oder auf nächsten Monat rollen"
    elif decay is not None and decay >= 50:
        action = "💡 50%+ Gewinn — Schließen erwägen (Take Profit)"
    else:
        action = "✅ läuft — alles in Ordnung"

    _price_str = f"${price:.2f}" if price > 0 else "–"
    _opt_str   = f"${opt_mid:.2f}" if opt_mid > 0 else "–"
    _decay_str = f"{decay:.0f}%" if decay is not None else "–"
    _otm_lbl   = "ITM" if itm else "OTM"

    # ── Kurs↔Strike-Skala: Strike mittig, Preis-Marker, farbige Zonen ──────────
    _lo, _hi = strike * 0.85, strike * 1.15
    _ppos = ((price - _lo) / (_hi - _lo) * 100) if (price > 0 and _hi > _lo) else 50.0
    _ppos = max(4, min(96, _ppos))
    G, R = "#22c55e", "#ef4444"
    # Put: links vom Strike = ITM (rot), rechts = OTM (grün) · Call umgekehrt
    if is_call:
        _zone = f"linear-gradient(90deg,{G}33 0%,{G}1f 49%,{R}1f 51%,{R}33 100%)"
    else:
        _zone = f"linear-gradient(90deg,{R}33 0%,{R}1f 49%,{G}1f 51%,{G}33 100%)"

    def _tile(label: str, value: str, vcolor: str) -> str:
        return (
            f"<div style='flex:1;min-width:70px;background:{track_bg};border:1px solid {txt_muted}33;"
            f"border-radius:8px;padding:6px 8px;text-align:center'>"
            f"<div style='font-size:0.58rem;color:{txt_muted};text-transform:uppercase;"
            f"letter-spacing:0.05em'>{label}</div>"
            f"<div style='font-size:0.92rem;font-weight:700;color:{vcolor}'>{value}</div></div>"
        )

    tiles = (
        _tile("Abstand", f"{otm:+.1f}% {_otm_lbl}", col)
        + _tile("Option", _opt_str, txt_main)
        + _tile("Verfall", _decay_str, G if (decay or 0) >= 0 else R)
        + _tile("Rest", f"{dte} T", txt_main)
    )

    return f"""
<div style='background:{track_bg};border:1px solid {col}40;border-radius:14px;
            padding:14px 16px;margin-bottom:12px;box-shadow:0 1px 4px rgba(0,0,0,0.18);
            font-family:RedRose,sans-serif'>
  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:11px'>
    <div style='display:flex;align-items:center;gap:9px;flex-wrap:wrap'>
      <span style='font-weight:700;font-size:1.18rem;color:{txt_main};letter-spacing:0.02em'>{ticker}</span>
      <span style='background:{col}1f;color:{col};font-size:0.7rem;font-weight:700;
                   padding:3px 9px;border-radius:6px'>{strategy} ${strike:g}</span>
      <span style='color:{txt_muted};font-size:0.7rem'>Class {cls}</span>
    </div>
    <span style='background:{col};color:#fff;font-size:0.72rem;font-weight:700;
                 padding:3px 12px;border-radius:20px;white-space:nowrap'>{word}</span>
  </div>

  <div style='display:flex;justify-content:space-between;font-size:0.62rem;color:{txt_muted};margin-bottom:4px'>
    <span>📅 Abschluss {start.strftime('%d.%m.')}</span>
    <span style='font-weight:700;color:{txt_sub}'>{elapsed_pct}% Laufzeit · noch {dte} Tage</span>
    <span>🏁 Verfall {end.strftime('%d.%m.')}</span>
  </div>
  <div style='position:relative;height:12px;background:{txt_muted}22;border-radius:6px;overflow:hidden'>
    <div style='position:absolute;left:0;top:0;height:100%;width:{elapsed_pct}%;
                background:linear-gradient(90deg,{col}88,{col});border-radius:6px'></div>
    <div style='position:absolute;left:calc({elapsed_pct}% - 1.5px);top:-2px;height:16px;width:3px;
                background:{txt_main};border-radius:2px'></div>
  </div>

  <div style='display:flex;justify-content:space-between;font-size:0.6rem;color:{txt_muted};
              margin:11px 0 3px'>
    <span>Kurs ↔ Strike</span><span style='color:{col};font-weight:700'>{word}</span>
  </div>
  <div style='position:relative;height:14px;border-radius:7px;background:{_zone}'>
    <div style='position:absolute;left:50%;top:-2px;height:18px;width:2px;background:{txt_main};opacity:0.55'></div>
    <div style='position:absolute;left:{_ppos}%;top:-4px;width:0;height:0;
                border-left:6px solid transparent;border-right:6px solid transparent;
                border-top:9px solid {col};transform:translateX(-6px)'></div>
  </div>
  <div style='display:flex;justify-content:space-between;font-size:0.6rem;color:{txt_muted};margin-top:3px'>
    <span>💵 Kurs {_price_str}</span><span>🎯 Strike ${strike:g}</span>
  </div>

  <div style='display:flex;gap:7px;margin-top:11px'>{tiles}</div>

  <div style='font-size:0.76rem;color:{txt_sub};margin-top:9px'>→ {action}</div>
</div>
"""


# ── Header ─────────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.markdown(get_logo_html("auto", 40), unsafe_allow_html=True)
with col_title:
    st.markdown("""
    <div style='padding-top:4px'>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.8rem;
                    color:#f0f0f0;letter-spacing:0.04em'>📡 TRADE MONITOR</div>
        <div style='font-family:RedRose,sans-serif;font-weight:300;font-size:0.8rem;
                    color:#666;text-transform:uppercase;letter-spacing:0.12em;margin-top:2px'>
            Live-Tracking · Optionen verfolgen bis zum Verfall
        </div>
    </div>
    """, unsafe_allow_html=True)

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── URL-Parameter lesen: alle Trade-Daten aus dem Link ────────────────────────
_qp = dict(st.query_params)
highlight_id = _qp.get("trade_id", "")

# ── Trades laden ───────────────────────────────────────────────────────────────
all_trades = _load_trades()

# Wenn Trade-Daten vollständig in URL kodiert sind und Trade nicht lokal gespeichert
if "t" in _qp and "s" in _qp and "e" in _qp:
    _url_trade_id = _qp.get("trade_id", "")
    _in_local = any(t.get("trade_id") == _url_trade_id for t in all_trades)
    if not _in_local:
        try:
            _url_trade = {
                "trade_id":       _url_trade_id,
                "class":          _qp.get("cls", "A"),
                "ticker":         _qp.get("t", ""),
                "company":        _qp.get("co", _qp.get("t", "")),
                "strategy":       _qp.get("strat", "Short PUT"),
                "strike":         float(_qp.get("s", 0)),
                "call_strike":    0.0,
                "expiry":         _qp.get("e", ""),
                "premium":        float(_qp.get("p", 0)),
                "delta":          float(_qp.get("d", -0.2)),
                "iv_pct":         float(_qp.get("iv", 25)),
                "price_at_entry": float(_qp.get("px", 0)),
                "created_at":     "",
                "post_ts":        "–",
                "optionstrat_url": "",
                "tracking_url":   "",
                "status":         "AKTIV",
            }
            all_trades = [_url_trade] + all_trades
            highlight_id = _url_trade_id
        except Exception:
            pass

if not all_trades:
    st.html(f"""
    <div style='background:{CARD_BG};border:1px dashed {CARD_BD};border-radius:12px;
                padding:40px;text-align:center;margin-top:24px'>
        <div style='font-size:3rem;margin-bottom:12px'>📡</div>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.1rem;
                    color:{TXT_SUB};letter-spacing:0.05em;margin-bottom:8px'>
            Noch keine Trades gespeichert
        </div>
        <div style='font-family:RedRose,sans-serif;font-size:0.88rem;color:{TXT_MUTED};line-height:1.7'>
            Gehe zu <b style='color:{"#b8902f" if _IS_GREEN else "#d4a843"}'>Trade Cards → Manuell eingeben</b>,
            trage deine Optionen ein und generiere Posts —<br>
            die Trades werden dann hier automatisch zum Live-Tracking gespeichert.
        </div>
    </div>
    """)
    st.stop()

# ── Filter-Controls ────────────────────────────────────────────────────────────
fc1, fc2, fc3 = st.columns([2, 2, 3])
with fc1:
    status_filter = st.multiselect(
        "Status-Filter",
        ["AKTIV", "WATCH", "WARNING", "ROLL", "CLOSE", "EXPIRED", "CANCELLED"],
        default=["AKTIV", "WATCH", "WARNING", "ROLL"],
        key="tm_status",
    )
with fc2:
    class_filter = st.multiselect(
        "Klasse",
        ["A", "B", "C"],
        default=["A", "B", "C"],
        key="tm_class",
    )
with fc3:
    st.caption(f"📡 {len(all_trades)} Trades gespeichert · Live-Preise werden alle 60s aktualisiert")

# Filtern
visible_trades = [
    t for t in all_trades
    if t.get("status", "AKTIV") in status_filter
    and t.get("class", "A") in class_filter
]

# Hervorgehobenen Trade zuerst zeigen
if highlight_id:
    visible_trades = sorted(
        visible_trades,
        key=lambda t: 0 if t.get("trade_id") == highlight_id else 1,
    )

if not visible_trades:
    st.info("Keine Trades mit den gewählten Filtern gefunden.")
    st.stop()

# ── Übersicht: Zeitstrahl pro Trade ─────────────────────────────────────────────
st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)
st.markdown(f"### 📊 Übersicht — {len(visible_trades)} Trades")
st.caption("Balken = Laufzeit (Abschluss → Verfall, Füllung = verstrichene Zeit) · "
           "Farbe: 🟢 OK · 🟡 nah am Strike · 🔴 im Geld")

with st.spinner("⏳ Live-Daten…"):
    for _t in visible_trades:
        st.html(_timeline_card_html(_t, CARD_BG2, TXT_MAIN, TXT_SUB, TXT_MUTED))

st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)
st.markdown("#### 🔎 Details")

# ── Live-Karten ────────────────────────────────────────────────────────────────
for trade in visible_trades:
    trade_id  = trade.get("trade_id", "")
    cls       = trade.get("class", "–")
    ticker    = trade.get("ticker", "–")
    company   = trade.get("company", ticker)
    strategy  = trade.get("strategy", "–")
    strike    = float(trade.get("strike", 0))
    expiry    = trade.get("expiry", "")
    premium   = float(trade.get("premium", 0))
    delta     = float(trade.get("delta", 0))
    iv_pct    = float(trade.get("iv_pct", 0))
    entry_px  = float(trade.get("price_at_entry", 0))
    status    = trade.get("status", "AKTIV")
    post_ts   = trade.get("post_ts", "–")
    # Immer frisch im korrekten OCC-Format bauen (alte gespeicherte URLs könnten
    # noch das veraltete Format haben); gespeicherte nur als Fallback.
    opt_url   = _build_optionstrat_url(trade) or trade.get("optionstrat_url", "")
    track_url = trade.get("tracking_url", "")
    is_call   = "Call" in strategy

    is_highlighted = (trade_id == highlight_id)
    cls_colors = {"A": "#22c55e", "B": "#d4a843", "C": "#ef4444"}
    cls_color  = cls_colors.get(cls, "#888")
    stat_color = STATUS_COLORS.get(status, "#888")

    dte = _dte_from_expiry(expiry)
    dte_color = "#ef4444" if dte <= 7 else ("#f59e0b" if dte <= 21 else "#22c55e")
    dte_icon  = "🔴" if dte <= 7 else ("🟡" if dte <= 21 else "🟢")

    border_extra = "box-shadow:0 0 12px #d4a84366;" if is_highlighted else ""

    with st.container():
        header_exp = st.expander(
            f"{'⭐ ' if is_highlighted else ''}"
            f"Class {cls} · **{ticker}** · {strategy} · Strike ${strike:.0f} · "
            f"{dte_icon} {dte}T bis Verfall · Status: {status}",
            expanded=is_highlighted,
        )
        with header_exp:
            # ── Live-Daten laden ────────────────────────────────────────────
            with st.spinner(f"⏳ Live-Daten für {ticker}…"):
                current_price = _fetch_current_price(ticker)
                try:
                    d_exp = pd.to_datetime(expiry)
                    expiry_chain = d_exp.strftime("%Y-%m-%d")
                except Exception:
                    expiry_chain = expiry
                current_opt_mid = _fetch_option_mid(ticker, expiry_chain, strike, is_call)

            # ── P/L-Berechnung ──────────────────────────────────────────────
            pnl_usd = 0.0
            pnl_pct = 0.0
            if premium > 0:
                if current_opt_mid > 0:
                    pnl_usd = (premium - current_opt_mid) * 100
                    pnl_pct = (premium - current_opt_mid) / premium * 100
                elif current_price > 0 and entry_px > 0:
                    # Grobe Schätzung wenn keine Option gefunden
                    px_chg = (current_price - entry_px) / entry_px
                    pnl_pct = -px_chg * abs(delta) * 100 * (-1 if is_call else 1) + 10
                    pnl_usd = pnl_pct / 100 * premium * 100

            pl_color = _pnl_color(pnl_pct)

            # ── Layout ──────────────────────────────────────────────────────
            c1, c2, c3, c4 = st.columns([2, 2, 2, 2])

            _cp_str = f"${current_price:.2f}" if (current_price and current_price > 0) else "–"
            with c1:
                st.html(f"""
                <div style='background:{CARD_BG};border:1px solid {cls_color}40;border-left:3px solid {cls_color};
                            border-radius:8px;padding:10px 14px;{border_extra}'>
                    <div style='font-size:0.6rem;color:{TXT_MUTED};text-transform:uppercase;font-family:sans-serif'>
                        Class {cls} · {company}</div>
                    <div style='font-size:1.4rem;font-weight:700;color:{TXT_MAIN};font-family:sans-serif;
                                margin:4px 0'>{ticker}</div>
                    <div style='font-size:0.78rem;color:{TXT_SUB};font-family:sans-serif'>{strategy}</div>
                    <div style='margin-top:6px'>
                        <span style='background:{stat_color}22;color:{stat_color};border-radius:4px;
                                     padding:2px 8px;font-size:0.7rem;font-weight:700'>{status}</span>
                    </div>
                </div>
                """)

            with c2:
                st.html(f"""
                <div style='background:{CARD_BG2};border:1px solid {CARD_BD};border-radius:8px;padding:10px 14px'>
                    <div style='font-size:0.58rem;color:{TXT_MUTED};text-transform:uppercase;font-family:sans-serif'>
                        Aktueller Kurs</div>
                    <div style='font-size:1.2rem;font-weight:700;color:{TXT_MAIN};font-family:sans-serif'>
                        {_cp_str}</div>
                    <div style='margin-top:6px;font-size:0.58rem;color:{TXT_MUTED};text-transform:uppercase;
                                font-family:sans-serif'>Einstieg</div>
                    <div style='font-size:0.88rem;color:{TXT_SUB};font-family:sans-serif'>
                        ${entry_px:.2f}</div>
                </div>
                """)

            with c3:
                opt_price_str = f"${current_opt_mid:.2f}" if current_opt_mid > 0 else "–"
                st.html(f"""
                <div style='background:{CARD_BG3};border:1px solid {CARD_BD};border-radius:8px;padding:10px 14px'>
                    <div style='font-size:0.58rem;color:{TXT_MUTED};text-transform:uppercase;font-family:sans-serif'>
                        Option aktuell (Mid)</div>
                    <div style='font-size:1.2rem;font-weight:700;color:#16a34a;font-family:sans-serif'>
                        {opt_price_str}</div>
                    <div style='margin-top:6px;font-size:0.58rem;color:{TXT_MUTED};text-transform:uppercase;
                                font-family:sans-serif'>Einstiegsprämie</div>
                    <div style='font-size:0.88rem;color:{TXT_SUB};font-family:sans-serif'>
                        ${premium:.2f}</div>
                </div>
                """)

            with c4:
                pnl_sign = "+" if pnl_usd >= 0 else ""
                st.html(f"""
                <div style='background:{CARD_BG2};border:1px solid {pl_color}40;border-radius:8px;padding:10px 14px'>
                    <div style='font-size:0.58rem;color:{TXT_MUTED};text-transform:uppercase;font-family:sans-serif'>
                        P/L (1 Kontrakt)</div>
                    <div style='font-size:1.4rem;font-weight:700;color:{pl_color};font-family:sans-serif'>
                        {pnl_sign}{pnl_usd:.0f} USD</div>
                    <div style='font-size:0.9rem;color:{pl_color};font-family:sans-serif'>
                        {pnl_sign}{pnl_pct:.1f}% der Prämie</div>
                    <div style='margin-top:4px;font-size:0.7rem;color:{TXT_MUTED};font-family:sans-serif'>
                        {'💡 TP bei 50%' if pnl_pct >= 50 else '⏳ Läuft noch' if pnl_pct >= 0 else '⚠️ Im Minus'}</div>
                </div>
                """)

            # ── DTE + Strike-Abstand ─────────────────────────────────────────
            st.markdown("---")
            d1, d2, d3 = st.columns(3)
            with d1:
                try:
                    exp_fmt = pd.to_datetime(expiry).strftime("%d. %b %Y")
                except Exception:
                    exp_fmt = expiry
                st.html(f"""
                <div style='background:{CARD_BG};border:1px solid {CARD_BD};border-radius:6px;padding:8px 12px'>
                    <div style='font-size:0.58rem;color:{TXT_MUTED};text-transform:uppercase;font-family:sans-serif'>
                        📅 Verfall</div>
                    <div style='font-size:1rem;font-weight:700;color:{"#b8902f" if _IS_GREEN else "#d4a843"};font-family:sans-serif'>
                        {exp_fmt}</div>
                    <div style='font-size:1.8rem;font-weight:900;color:{dte_color};font-family:sans-serif'>
                        {dte_icon} {dte} <span style='font-size:0.7rem;color:{TXT_SUB}'>Tage</span></div>
                </div>
                """)

            with d2:
                if current_price > 0 and strike > 0:
                    dist_pct = (current_price - strike) / current_price * 100
                    dist_label = f"{'OTM' if (dist_pct > 0 and not is_call) or (dist_pct < 0 and is_call) else '⚠️ ITM'}"
                    dist_color = "#22c55e" if "OTM" in dist_label else "#ef4444"
                else:
                    dist_pct, dist_label, dist_color = 0.0, "–", TXT_SUB
                st.html(f"""
                <div style='background:{CARD_BG2};border:1px solid {CARD_BD};border-radius:6px;padding:8px 12px'>
                    <div style='font-size:0.58rem;color:{TXT_MUTED};text-transform:uppercase;font-family:sans-serif'>
                        Strike-Abstand</div>
                    <div style='font-size:1rem;font-weight:700;color:{dist_color};font-family:sans-serif'>
                        {_fmt_num(abs(dist_pct), 1)}% {dist_label}</div>
                    <div style='font-size:0.78rem;color:{TXT_SUB};font-family:sans-serif'>
                        Strike ${strike:.0f} · Delta {delta:.2f}</div>
                </div>
                """)

            with d3:
                tp50 = premium * 0.50
                tp70 = premium * 0.30  # 70% Gewinn → Option noch 30% des Preises wert
                capital_basis = entry_px if is_call and entry_px > 0 else (strike if strike > 0 else premium)
                rend_lz_pct = premium / capital_basis * 100 if capital_basis > 0 else 0
                basis_label = "Aktienkurs" if is_call else "Strike/Cash"
                _tp_green = "#16a34a" if _IS_GREEN else "#4ade80"
                st.html(f"""
                <div style='background:{CARD_BG3};border:1px solid {CARD_BD};border-radius:6px;padding:8px 12px'>
                    <div style='font-size:0.58rem;color:{TXT_MUTED};text-transform:uppercase;font-family:sans-serif'>
                        Take Profit Ziele</div>
                    <div style='font-size:0.82rem;color:{_tp_green};font-family:sans-serif'>
                        50% → Prämie &lt; ${tp50:.2f} → schließen</div>
                    <div style='font-size:0.82rem;color:#16a34a;font-family:sans-serif'>
                        70% → Prämie &lt; ${tp70:.2f} → schließen</div>
                    <div style='font-size:0.72rem;color:{_tp_green};margin-top:4px;font-family:sans-serif'>
                        Rendite: {rend_lz_pct:.2f}% ({basis_label})</div>
                    <div style='font-size:0.7rem;color:{TXT_MUTED};margin-top:2px;font-family:sans-serif'>
                        Post: {post_ts}</div>
                </div>
                """)

            # ── Trade Management Empfehlungen ────────────────────────────────
            st.markdown("---")
            st.markdown("**🎯 Trade Management**")
            _mgmt_items = []

            # P/L basierte Empfehlungen
            if pnl_pct >= 70:
                _mgmt_items.append(("🏆", "#22c55e",
                    f"**70% Take Profit erreicht!** → Position jetzt schließen "
                    f"(Prämie < ${premium * 0.30:.2f})"))
            elif pnl_pct >= 50:
                _mgmt_items.append(("✅", "#4ade80",
                    f"**50% Take Profit erreicht** → Schließen empfohlen "
                    f"(Prämie < ${premium * 0.50:.2f})"))
            elif pnl_pct >= 25:
                _mgmt_items.append(("📈", "#86efac",
                    f"Position läuft gut ({pnl_pct:.0f}% der Prämie verdient) — weiter halten"))
            elif pnl_pct < -50:
                _mgmt_items.append(("🚨", "#ef4444",
                    f"**Verlust > 50%** → Position sofort schließen oder rollen! "
                    f"Prämie verdoppelt sich — keine weiteren Verluste riskieren"))
            elif pnl_pct < -20:
                _mgmt_items.append(("⚠️", "#f59e0b",
                    f"Position im Minus ({pnl_pct:.0f}%) → Engmaschig beobachten"))
            else:
                _mgmt_items.append(("⏳", "#888",
                    f"Position neutral ({pnl_pct:.0f}%) — weiter laufen lassen"))

            # DTE-basierte Empfehlungen
            if dte == 0:
                _mgmt_items.append(("⏰", "#ef4444",
                    "**Verfall heute!** → Option verfällt wertlos oder wird ausgeübt"))
            elif dte <= 3:
                _mgmt_items.append(("⏰", "#ef4444",
                    f"**Nur noch {dte} Tage bis Verfall** → "
                    f"Position schließen oder auf nächsten Monat rollen"))
            elif dte <= 7:
                _mgmt_items.append(("📅", "#f59e0b",
                    f"{dte} Tage verbleibend — Rollen prüfen wenn Strike unter Druck"))

            # Strike-Abstand / ITM-Warnung
            if current_price > 0 and strike > 0:
                dist_abs = current_price - strike if not is_call else strike - current_price
                if dist_abs < 0:
                    _mgmt_items.append(("🔴", "#ef4444",
                        f"**Strike ITM!** Kurs ${current_price:.2f} hat Strike ${strike:.0f} "
                        f"{'unterschritten' if not is_call else 'überschritten'} → "
                        f"Rollen auf niedrigeren Strike oder schließen"))
                elif dist_abs < strike * 0.03:
                    _mgmt_items.append(("🟡", "#f59e0b",
                        f"Strike nahe am Geld (nur {dist_abs:.2f} USD Puffer) → "
                        f"Erhöhte Aufmerksamkeit, Rollen vorbereiten"))

            # Covered Call: Aufwertung / Rückkauf bei Kursrückgang
            if is_call and current_price > 0 and entry_px > 0:
                cc_chg = (current_price - entry_px) / entry_px * 100
                if cc_chg < -10:
                    _mgmt_items.append(("📉", "#a78bfa",
                        f"Aktie {cc_chg:.1f}% gefallen → CALL günstig zurückzukaufen, "
                        f"Strike nach unten rollen für mehr Prämie"))

            for icon, color, text in _mgmt_items:
                st.html(
                    f"<div style='display:flex;gap:10px;align-items:flex-start;"
                    f"background:{CARD_BG};border:1px solid {CARD_BD};border-left:3px solid {color};"
                    f"border-radius:0 6px 6px 0;"
                    f"padding:8px 12px;margin:4px 0;font-family:sans-serif'>"
                    f"<span style='font-size:1.1rem'>{icon}</span>"
                    f"<span style='font-size:0.82rem;color:{TXT_MAIN};line-height:1.5'>{text}</span>"
                    f"</div>"
                )

            # ── Links ────────────────────────────────────────────────────────
            if opt_url or track_url:
                st.markdown("**🔗 Links**")
                lc1, lc2 = st.columns(2)
                with lc1:
                    if opt_url:
                        st.markdown(f"[📊 OptionStrat öffnen]({opt_url})")
                with lc2:
                    if track_url:
                        st.markdown(f"[📡 Dieser Trade (Link für Post)]({track_url})")

            # ── Status-Steuerung ─────────────────────────────────────────────
            st.markdown("**⚙️ Status aktualisieren**")
            sc1, sc2, sc3 = st.columns([2, 2, 3])
            with sc1:
                new_status = st.selectbox(
                    "Neuer Status",
                    ["AKTIV", "WATCH", "WARNING", "ROLL", "CLOSE", "EXPIRED", "CANCELLED"],
                    index=["AKTIV", "WATCH", "WARNING", "ROLL", "CLOSE", "EXPIRED", "CANCELLED"].index(status)
                    if status in ["AKTIV", "WATCH", "WARNING", "ROLL", "CLOSE", "EXPIRED", "CANCELLED"] else 0,
                    key=f"ns_{trade_id}",
                    label_visibility="collapsed",
                )
            with sc2:
                status_note = st.text_input(
                    "Notiz", placeholder="z.B. Strike bedroht, rollen…",
                    key=f"note_{trade_id}", label_visibility="collapsed",
                )
            with sc3:
                if st.button(
                    f"💾 Status speichern", key=f"save_{trade_id}", use_container_width=True,
                ):
                    _update_trade_status(trade_id, new_status, status_note)
                    st.success(f"Status auf **{new_status}** gesetzt.")
                    st.rerun()

    st.html("<div style='height:8px'></div>")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style='text-align:center;font-family:RedRose,sans-serif;font-size:0.76rem;color:#333;letter-spacing:0.08em'>
    STILLHALTER COMMUNITY · Live-Preise: Yahoo Finance · Nicht als Finanzberatung zu verstehen
</div>
""", unsafe_allow_html=True)
