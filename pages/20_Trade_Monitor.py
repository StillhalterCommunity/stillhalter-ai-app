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

# Nur der Admin (Oliver) darf Trades schließen/entfernen — andere Nutzer sehen
# die Trades nur (read-only). Anonyme Tracking-Link-Besucher ohnehin nicht.
try:
    from data.maintenance import is_admin as _is_admin
    _is_owner = _is_admin(st.session_state.get("auth_user", ""))
except Exception:
    _is_owner = False

# ── Theme-Farben (hell im Grün-Theme, dunkel im Dark-Theme) ──────────────────────
_IS_GREEN = st.session_state.get("app_theme", "dark") == "green"
if _IS_GREEN:
    CARD_BG, CARD_BG2, CARD_BG3, CARD_BD = "#f6fdfb", "#eef8f5", "#eef8f5", "#b7e4c7"
    TXT_MAIN, TXT_SUB, TXT_MUTED = "#0a1628", "#475569", "#94a3b8"
else:
    CARD_BG, CARD_BG2, CARD_BG3, CARD_BD = "#111", "#0e0e0e", "#0a120a", "#1e1e1e"
    # Im Dark-Theme alles weiß (statt grau) für maximale Lesbarkeit.
    TXT_MAIN, TXT_SUB, TXT_MUTED = "#ffffff", "#ffffff", "#e8e8e8"

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


def _delete_trade(trade_id: str) -> None:
    """Entfernt einen Trade dauerhaft aus dem Monitor (nur Admin)."""
    trades = [t for t in _load_trades() if t.get("trade_id") != trade_id]
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


@st.cache_data(ttl=3600, show_spinner=False)
def _fetch_earnings(ticker: str):
    """Nächster Earnings-Termin (YYYY-MM-DD) oder None."""
    try:
        from data.fetcher import fetch_earnings_date
        return fetch_earnings_date(ticker)
    except Exception:
        return None


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

    # Live-Preise; fallen auf die gespeicherten Einstiegswerte zurück, wenn der
    # Markt zu ist / kein Live-Kurs verfügbar — sonst stünden überall "–".
    price_at_entry = float(trade.get("price_at_entry", 0) or 0)
    _live_price = _fetch_current_price(ticker)
    price = _live_price if _live_price > 0 else price_at_entry
    try:
        d_exp = pd.to_datetime(expiry)
        _live_opt = _fetch_option_mid(ticker, d_exp.strftime("%Y-%m-%d"), strike, is_call)
        end = d_exp.date()
    except Exception:
        _live_opt, end = 0.0, date.today()
    opt_mid = _live_opt if _live_opt > 0 else premium

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

    # Handlungsempfehlung — gleiche 5-Status-Logik wie im Trade Management
    if dte <= 0:
        action = ("📋 Abgelaufen — wertlos verfallen ✅" if not itm
                  else "📋 Abgelaufen — Einbuchung prüfen")
    elif itm:
        action = ("👀 ITM — Gegenbewegung abwarten" if dte > 21
                  else "🔄 Rollen oder Einbuchen prüfen")
    elif abs(otm) < 5:
        action = "⚠️ Am Geld — Entscheidung nötig"
    elif decay is not None and decay >= 70:
        action = "💰 70%-Ziel erreicht — schließen"
    elif decay is not None and decay >= 50:
        action = "💰 50%+ der Prämie verdient — Schließen erwägen"
    elif abs(otm) < 8:
        action = "👀 OTM-Abstand gering — beobachten"
    else:
        action = "✅ Nach Plan — laufen lassen"

    # Earnings-Warnung: Termin innerhalb der Restlaufzeit?
    earnings_badge = ""
    try:
        _edate = _fetch_earnings(ticker)
        if _edate:
            _ed = pd.to_datetime(_edate).date()
            if date.today() <= _ed <= end:
                earnings_badge = (
                    f"<span style='background:#f59e0b22;color:#f59e0b;font-size:0.78rem;"
                    f"font-weight:700;padding:3px 10px;border-radius:6px'>"
                    f"⚠️ Earnings {_ed.strftime('%d.%m.')}</span>"
                )
    except Exception:
        pass

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

    def _tile(label: str, value: str, vcolor: str, sub: str = "") -> str:
        sub_html = (f"<div style='font-size:0.7rem;color:{txt_sub};margin-top:1px'>{sub}</div>"
                    if sub else "")
        return (
            f"<div style='flex:1;min-width:74px;background:{track_bg};border:1px solid {txt_sub}55;"
            f"border-radius:8px;padding:8px 8px;text-align:center'>"
            f"<div style='font-size:0.72rem;color:{txt_sub};text-transform:uppercase;"
            f"letter-spacing:0.04em'>{label}</div>"
            f"<div style='font-size:1.12rem;font-weight:700;color:{vcolor};margin-top:2px'>{value}</div>"
            f"{sub_html}</div>"
        )

    # P&L pro Kontrakt (eingenommene Prämie − aktueller Optionspreis)
    delta_v  = float(trade.get("delta", 0) or 0)
    pnl_usd  = ((premium - opt_mid) * 100) if premium > 0 else None
    pnl_col  = G if (pnl_usd or 0) >= 0 else R
    _pnl_str = f"{pnl_usd:+,.0f} $" if pnl_usd is not None else "–"

    tiles = (
        _tile("Abstand", f"{otm:+.1f}% {_otm_lbl}", col,
              sub=(f"Δ {delta_v:+.2f}" if delta_v else ""))
        + _tile("Option", _opt_str, txt_main,
                sub=(f"Einstieg ${premium:.2f}" if premium > 0 else ""))
        + _tile("P&L", _pnl_str, pnl_col,
                sub=(f"{decay:+.0f}% der Prämie" if decay is not None else ""))
        + _tile("Rest", f"{dte} T", txt_main, sub=end.strftime("%d.%m.%y"))
    )

    # Take-Profit-Ziele + Links (OptionStrat, Post-Link)
    opt_url   = _build_optionstrat_url(trade) or trade.get("optionstrat_url", "")
    track_url = trade.get("tracking_url", "")
    _tp_html = (f"🎯 TP 50% ≤ ${premium*0.5:.2f} · TP 70% ≤ ${premium*0.3:.2f}"
                if premium > 0 else "")
    _link_parts = []
    if opt_url:
        _link_parts.append(f"<a href='{opt_url}' target='_blank' "
                           f"style='color:{col};text-decoration:none;font-weight:600'>📊 OptionStrat ↗</a>")
    if track_url:
        _link_parts.append(f"<a href='{track_url}' target='_blank' "
                           f"style='color:{txt_sub};text-decoration:none'>📡 Post-Link</a>")
    _links_html = " &nbsp;·&nbsp; ".join(_link_parts)

    return f"""
<div style='background:{track_bg};border:1px solid {col}40;border-radius:14px;
            padding:14px 16px;margin-bottom:12px;box-shadow:0 1px 4px rgba(0,0,0,0.18);
            font-family:RedRose,sans-serif'>
  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px'>
    <div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap'>
      <span style='font-weight:700;font-size:1.4rem;color:{txt_main};letter-spacing:0.02em'>{ticker}</span>
      <span style='background:{col}2a;color:{col};font-size:0.85rem;font-weight:700;
                   padding:3px 10px;border-radius:6px'>{strategy} ${strike:g}</span>
      <span style='color:{txt_sub};font-size:0.82rem;font-weight:600'>Class {cls}</span>
      {earnings_badge}
    </div>
    <span style='background:{col};color:#fff;font-size:0.9rem;font-weight:700;
                 padding:5px 16px;border-radius:20px;white-space:nowrap'>{word}</span>
  </div>

  <div style='display:flex;justify-content:space-between;font-size:0.78rem;color:{txt_sub};margin-bottom:5px'>
    <span>📅 Abschluss {start.strftime('%d.%m.')}</span>
    <span style='font-weight:700;color:{txt_main}'>{elapsed_pct}% Laufzeit · noch {dte} Tage</span>
    <span>🏁 Verfall {end.strftime('%d.%m.')}</span>
  </div>
  <div style='position:relative;height:12px;background:{txt_muted}22;border-radius:6px;overflow:hidden'>
    <div style='position:absolute;left:0;top:0;height:100%;width:{elapsed_pct}%;
                background:linear-gradient(90deg,{col}88,{col});border-radius:6px'></div>
    <div style='position:absolute;left:calc({elapsed_pct}% - 1.5px);top:-2px;height:16px;width:3px;
                background:{txt_main};border-radius:2px'></div>
  </div>

  <div style='display:flex;justify-content:space-between;font-size:0.74rem;color:{txt_sub};
              margin:12px 0 3px'>
    <span style='font-weight:600'>Kurs ↔ Strike</span><span style='color:{col};font-weight:700'>{word}</span>
  </div>
  <div style='position:relative;height:14px;border-radius:7px;background:{_zone}'>
    <div style='position:absolute;left:50%;top:-2px;height:18px;width:2px;background:{txt_main};opacity:0.55'></div>
    <div style='position:absolute;left:{_ppos}%;top:-4px;width:0;height:0;
                border-left:6px solid transparent;border-right:6px solid transparent;
                border-top:9px solid {col};transform:translateX(-6px)'></div>
  </div>
  <div style='display:flex;justify-content:space-between;font-size:0.82rem;color:{txt_sub};
              font-weight:600;margin-top:4px'>
    <span>💵 Kurs {_price_str}{f" <span style='font-weight:400'>(Einstieg ${price_at_entry:.2f})</span>" if price_at_entry > 0 else ""}</span>
    <span>🎯 Strike ${strike:g}</span>
  </div>

  <div style='display:flex;gap:8px;margin-top:12px'>{tiles}</div>

  <div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;
              gap:6px;margin-top:10px'>
    <span style='font-size:0.9rem;color:{txt_main};font-weight:600'>→ {action}</span>
    <span style='font-size:0.78rem;color:{txt_sub}'>{_tp_html}{" &nbsp;·&nbsp; " if (_tp_html and _links_html) else ""}{_links_html}</span>
  </div>
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
                    color:#e8e8e8;text-transform:uppercase;letter-spacing:0.12em;margin-top:2px'>
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
    _ALL_STATUS = ["AKTIV", "WATCH", "WARNING", "ROLL", "CLOSE", "EXPIRED", "CANCELLED"]
    status_filter = st.multiselect(
        "Status-Filter",
        _ALL_STATUS,
        default=_ALL_STATUS,   # alle aktiv; einzelne über das ✕ am Chip ausblenden
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
    # ── Alle Trades entfernen (nur Admin, mit Bestätigung) ────────────────────
    if _is_owner and all_trades:
        with st.popover("🗑️ Alle Trades entfernen"):
            st.warning(f"⚠️ Entfernt **alle {len(all_trades)} Trades** dauerhaft "
                       f"aus dem Monitor. Das kann nicht rückgängig gemacht werden.")
            if st.button("Ja, alle Trades unwiderruflich entfernen",
                         type="primary", key="btn_del_all_trades",
                         use_container_width=True):
                _save_trades([])
                st.rerun()

# Filtern
visible_trades = [
    t for t in all_trades
    if t.get("status", "AKTIV") in status_filter
    and t.get("class", "A") in class_filter
]

# Immer nach Laufzeitende (Verfall) sortieren — der naheste Verfall zuerst.
def _expiry_key(t: dict):
    # errors="coerce" → NaT statt Crash; leeres/ungültiges Datum ans Ende.
    d = pd.to_datetime(t.get("expiry", ""), errors="coerce")
    if pd.isna(d):
        return date.max
    try:
        return d.date()
    except Exception:
        return date.max
visible_trades = sorted(visible_trades, key=_expiry_key)

# Hervorgehobenen Trade (aus Tracking-Link) trotzdem zuerst zeigen
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

_STAT_OPTIONS = ["AKTIV", "WATCH", "WARNING", "ROLL", "CLOSE", "EXPIRED", "CANCELLED"]

with st.spinner("⏳ Live-Daten…"):
    for _t in visible_trades:
        st.html(_timeline_card_html(_t, CARD_BG2, TXT_MAIN, TXT_SUB, TXT_MUTED))

        # ── Verwaltung direkt an der Karte (nur Admin) ────────────────────────
        if _is_owner:
            _tid    = _t.get("trade_id", "")
            _tkr    = _t.get("ticker", "–")
            _status = _t.get("status", "AKTIV")
            with st.popover(f"⚙️ {_tkr} verwalten", use_container_width=False):
                _ns = st.selectbox(
                    "Status", _STAT_OPTIONS,
                    index=_STAT_OPTIONS.index(_status) if _status in _STAT_OPTIONS else 0,
                    key=f"ov_ns_{_tid}",
                )
                _note = st.text_input("Notiz", placeholder="z.B. Strike bedroht, rollen…",
                                      key=f"ov_note_{_tid}")
                _b1, _b2 = st.columns(2)
                with _b1:
                    if st.button("💾 Status speichern", key=f"ov_save_{_tid}",
                                 use_container_width=True):
                        _update_trade_status(_tid, _ns, _note)
                        st.rerun()
                with _b2:
                    if st.button("✕ Trade entfernen", key=f"ov_del_{_tid}",
                                 use_container_width=True):
                        _delete_trade(_tid)
                        st.rerun()

                # ── Order direkt an IBKR (Held) über die lokale Bridge ────────
                st.markdown("---")
                _t_strike  = float(_t.get("strike", 0) or 0)
                _t_expiry  = str(_t.get("expiry", ""))[:10]
                _t_iscall  = "Call" in str(_t.get("strategy", ""))
                _t_premium = float(_t.get("premium", 0) or 0)
                _ord_lmt = st.number_input(
                    "Limit $", min_value=0.01,
                    value=max(0.01, round(_t_premium * 0.9, 2) or 0.05),
                    step=0.05, format="%.2f", key=f"ov_lmt_{_tid}",
                    help="Vorschlag: 90% der Einstiegsprämie — anpassen nach Marktlage",
                )
                _ord_qty = st.number_input("Kontrakte", 1, 100, 1, key=f"ov_qty_{_tid}")
                if st.button("📤 An IBKR senden (Held)", key=f"ov_ibkr_{_tid}",
                             use_container_width=True,
                             help="Pausiert (Held) in TWS platzieren — Freigabe in TWS"):
                    from trading.order_sender import send_short_option as _send_ord
                    _ok, _msg = _send_ord(
                        ticker=_tkr, right=("C" if _t_iscall else "P"),
                        strike=_t_strike, expiration=_t_expiry,
                        limit_price=float(_ord_lmt), quantity=int(_ord_qty),
                    )
                    (st.success if _ok else st.error)(_msg)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("""
<div style='text-align:center;font-family:RedRose,sans-serif;font-size:0.76rem;color:#cfcfcf;letter-spacing:0.08em'>
    STILLHALTER COMMUNITY · Live-Preise: Yahoo Finance · Nicht als Finanzberatung zu verstehen
</div>
""", unsafe_allow_html=True)
