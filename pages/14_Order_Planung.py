"""
Stillhalter AI App — Order-Planung & IBKR Freigabe
====================================================
Orders werden in TWS als "Held" platziert (transmit=False).
Der Nutzer gibt die finale Freigabe direkt in TWS.
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
from typing import Optional

st.set_page_config(
    page_title="Order-Planung · Stillhalter AI App",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

# ── Lazy import trading module ─────────────────────────────────────────────────
try:
    from trading.ibkr_tws import (
        IBKRConfig, OptionOrderParams, PlacedOrder,
        test_connection, get_account_summary, get_open_orders,
        place_option_order, place_strangle_order, cancel_held_order,
        TWS_PORT_PAPER, TWS_PORT_LIVE, IB_GW_PORT_PAPER, IB_GW_PORT_LIVE,
    )
    IBKR_AVAILABLE = True
except ImportError:
    IBKR_AVAILABLE = False

def _check_ib_insync() -> bool:
    """Prüft ob ib_insync installiert ist ohne es zu importieren (vermeidet asyncio-Fehler)."""
    import importlib.util
    return importlib.util.find_spec("ib_insync") is not None

IB_INSYNC_INSTALLED = _check_ib_insync()

# ══════════════════════════════════════════════════════════════════════════════
# SESSION STATE
# ══════════════════════════════════════════════════════════════════════════════
for _k, _v in {
    "ibkr_config": None,
    "ibkr_connected": False,
    "placed_orders": [],   # List[dict] — Historie dieser Session
    "account_info": None,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v


def _config() -> IBKRConfig:
    return st.session_state.get("ibkr_config") or IBKRConfig()


# ══════════════════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════════════════
st.html(f"""
<div style='display:flex;align-items:center;gap:16px;margin-bottom:8px'>
  {get_logo_html(height=44)}
  <div style='border-left:1px solid #222;height:40px;margin:0 4px'></div>
  <div>
    <div style='font-size:1.4rem;font-weight:800;color:#f0f0f0;font-family:sans-serif'>
      📋 Order-Planung
    </div>
    <div style='font-size:0.8rem;color:#666;font-family:sans-serif'>
      Orders in IBKR TWS als "Held" platzieren — Freigabe erfolgt manuell in TWS
    </div>
  </div>
</div>
""")
st.divider()

# ══════════════════════════════════════════════════════════════════════════════
# INSTALLATION CHECK
# ══════════════════════════════════════════════════════════════════════════════
if not IB_INSYNC_INSTALLED:
    st.html("""
<div style='background:#1a0e0e;border:1px solid #ef4444;border-radius:12px;padding:20px;
     margin-bottom:20px'>
  <div style='font-size:1.0rem;font-weight:700;color:#ef4444;margin-bottom:10px'>
    ⚠️ ib_insync nicht installiert
  </div>
  <div style='font-size:0.82rem;color:#aaa;line-height:1.7'>
    Für die IBKR TWS-Anbindung wird <code>ib_insync</code> benötigt.<br>
    Bitte im Terminal ausführen:
  </div>
  <div style='background:#0a0a0a;border-radius:6px;padding:10px;margin-top:10px;
       font-family:monospace;color:#22c55e;font-size:0.85rem'>
    pip install ib_insync
  </div>
</div>
""")

# ══════════════════════════════════════════════════════════════════════════════
# TWS VERBINDUNG
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("🔌 TWS Verbindung", expanded=not st.session_state.ibkr_connected):

    # Verbindungsmodus wählen
    conn_mode = st.radio(
        "Verbindungsart",
        ["🌐 Über Bridge (Railway / Cloud)", "🏠 Lokal (localhost)"],
        horizontal=True,
    )
    use_bridge = "Bridge" in conn_mode

    if use_bridge:
        st.html("""
<div style='font-size:0.78rem;color:#aaa;line-height:1.9;margin-bottom:10px;
     background:#0a0a14;border-radius:8px;padding:14px;border-left:3px solid #8b5cf6'>
  <b style='color:#a78bfa'>So verbinden (einmalig ~2 Min, kein Account nötig):</b><br>
  1. TWS auf deinem Mac/PC starten (Paper Trading, Port 7497)<br>
  2. Terminal öffnen im App-Ordner und eingeben:<br>
  <code style='background:#111;padding:4px 10px;border-radius:4px;display:block;margin:4px 0;color:#22c55e'>
    python3 bridge.py</code>
  3. Das Skript zeigt eine <b>Tunnel-URL</b> (z.B. https://xxxxx.localhost.run) → hier unten eintragen<br>
  <span style='color:#6b7280'>✓ API-Key wird automatisch verwendet — kein manuelles Eintragen nötig</span>
</div>""")

        saved_url = st.session_state.get("bridge_url", "")
        bridge_url = st.text_input(
            "Tunnel-URL (aus bridge.py)",
            value=saved_url,
            placeholder="https://xxxxx.localhost.run",
            help="Die vollständige URL die bridge.py anzeigt"
        )
        if bridge_url:
            st.session_state["bridge_url"] = bridge_url.rstrip("/")

        bridge_key = "stillhalter-bridge"   # muss mit bridge.py übereinstimmen

        if st.button("Verbindung testen", key="test_bridge",
                     disabled=not bridge_url):
            try:
                import requests as _req
                r = _req.get(f"{bridge_url.rstrip('/')}/ping", timeout=8)
                data = r.json()
                if data.get("tws"):
                    st.session_state.ibkr_connected = True
                    st.session_state.ibkr_config = {"mode": "bridge",
                                                     "url": bridge_url.rstrip("/"),
                                                     "key": bridge_key}
                    st.success("Verbunden — Bridge läuft, TWS erreichbar")
                    st.rerun()
                else:
                    st.error("Bridge erreichbar, aber TWS antwortet nicht. "
                             "Bitte TWS auf dem Mac starten.")
            except Exception as e:
                st.error(f"Keine Verbindung zur Bridge: {e}")

    else:
        st.html("""
<div style='font-size:0.78rem;color:#888;line-height:1.6;margin-bottom:10px;
     background:#0e0e0e;border-radius:8px;padding:12px;border-left:3px solid #3b82f6'>
  Nur für lokalen Betrieb — TWS und App müssen auf demselben Rechner laufen.
</div>""")
        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            host = st.text_input("Host", value="127.0.0.1")
        with col2:
            mode = st.selectbox("Modus", ["Paper Trading (TWS)", "Live Trading (TWS)",
                                           "Paper (Gateway)", "Live (Gateway)"])
            port_map = {
                "Paper Trading (TWS)": TWS_PORT_PAPER if IBKR_AVAILABLE else 7497,
                "Live Trading (TWS)":  TWS_PORT_LIVE  if IBKR_AVAILABLE else 7496,
                "Paper (Gateway)":     IB_GW_PORT_PAPER if IBKR_AVAILABLE else 4002,
                "Live (Gateway)":      IB_GW_PORT_LIVE  if IBKR_AVAILABLE else 4001,
            }
            port = port_map[mode]
        with col3:
            client_id = st.number_input("Client ID", min_value=1, max_value=999,
                                         value=42, step=1)

        is_live = "Live" in mode
        if is_live:
            st.warning("Live Trading — Orders mit echtem Geld!")

        if st.button("Verbindung testen", disabled=not IB_INSYNC_INSTALLED):
            if IBKR_AVAILABLE:
                cfg = IBKRConfig(host=host, port=port, client_id=client_id)
                with st.spinner("Verbinde..."):
                    ok, msg = test_connection(cfg)
                if ok:
                    st.session_state.ibkr_config = cfg
                    st.session_state.ibkr_connected = True
                    acc = get_account_summary(cfg)
                    if acc:
                        st.session_state.account_info = acc
                    st.success(f"Verbunden: {msg}")
                    st.rerun()
                else:
                    st.session_state.ibkr_connected = False
                    st.error(f"Fehler: {msg}")

    if st.session_state.ibkr_connected:
        st.success("Verbunden mit TWS")
        acc = st.session_state.account_info
        if acc:
            c1, c2, c3 = st.columns(3)
            c1.metric("Net Liquidation", f"${acc.net_liquidation:,.0f}")
            c2.metric("Available Funds", f"${acc.available_funds:,.0f}")
            c3.metric("Buying Power", f"${acc.buying_power:,.0f}")


# ══════════════════════════════════════════════════════════════════════════════
# ORDER EINGABE
# ══════════════════════════════════════════════════════════════════════════════

# ── Prefill aus Scanner auslesen ──────────────────────────────────────────────
_pf = st.session_state.pop("order_prefill", None)  # einmalig lesen & löschen

if _pf:
    _pf_strategy = "Short Call" if _pf.get("right") == "C" else "Short Put"
    # Strangle erkennen (kommt nur wenn Scanner Strangle-Strategie aktiv hatte)
    if "Strangle" in str(_pf.get("strategy", "")):
        _pf_strategy = "Short Strangle"
    st.html(f"""
<div style='background:#0a0e12;border:1px solid #3b82f6;border-radius:10px;
     padding:12px 16px;margin-bottom:16px;display:flex;align-items:center;gap:12px'>
  <span style='font-size:1.3rem'>📥</span>
  <div style='font-size:0.82rem;color:#93c5fd;font-family:sans-serif'>
    <b>Aus Watchlist Scanner übernommen:</b>
    {_pf.get("ticker")} · Strike ${_pf.get("strike", 0):.2f} ·
    Prämie ${_pf.get("premium", 0):.2f} · DTE {_pf.get("dte", 0)} ·
    Delta {_pf.get("delta", 0):.2f}
  </div>
</div>
""")
else:
    _pf_strategy = "Short Put"

st.html("""
<div style='font-size:1.05rem;font-weight:700;color:#f0f0f0;font-family:sans-serif;
     margin:20px 0 12px'>
  📝 Order konfigurieren
</div>
""")

# Strategie-Auswahl
_strategy_options = ["Short Put", "Short Call", "Short Strangle", "Short Put Spread", "Short Call Spread"]
strategy = st.segmented_control(
    "Strategie",
    _strategy_options,
    default=_pf_strategy if _pf_strategy in _strategy_options else "Short Put",
)

st.markdown("")

# ── Prefill-Werte für Felder ──────────────────────────────────────────────────
_default_ticker  = _pf.get("ticker", "AAPL")      if _pf else "AAPL"
_default_qty     = int(_pf.get("quantity", 1))     if _pf else 1
_default_lmt_put = float(_pf.get("limit_price", 1.50)) if _pf and _pf.get("right") != "C" else 1.50
_default_lmt_call= float(_pf.get("limit_price", 1.20)) if _pf and _pf.get("right") == "C" else 1.20
_default_strike_put  = float(_pf.get("strike", 185.0)) if _pf and _pf.get("right") != "C" else 185.0
_default_strike_call = float(_pf.get("strike", 210.0)) if _pf and _pf.get("right") == "C" else 210.0

# Expiry parsen
_default_expiry = date.today().replace(day=20)
if _pf and _pf.get("expiration"):
    try:
        _exp_str = str(_pf["expiration"])
        if len(_exp_str) == 10:   # YYYY-MM-DD
            _default_expiry = date.fromisoformat(_exp_str)
        elif len(_exp_str) == 8:  # YYYYMMDD
            _default_expiry = date(int(_exp_str[:4]), int(_exp_str[4:6]), int(_exp_str[6:]))
    except Exception:
        pass

# ── Gemeinsame Felder ─────────────────────────────────────────────────────────
col_a, col_b, col_c, col_d = st.columns([2, 1, 1, 1])
with col_a:
    ticker = st.text_input("Ticker", value=_default_ticker, max_chars=10).upper().strip()
with col_b:
    expiry_date = st.date_input(
        "Verfall",
        value=_default_expiry,
        min_value=date.today(),
        format="DD.MM.YYYY",
    )
with col_c:
    quantity = st.number_input("Kontrakte", min_value=1, max_value=100, value=_default_qty, step=1)
with col_d:
    order_type = st.selectbox("Order-Typ", ["LMT", "MKT"])

expiry_str = expiry_date.strftime("%Y%m%d")

# ── Aktueller Kurs ────────────────────────────────────────────────────────────
if ticker:
    try:
        import yfinance as yf
        _info = yf.Ticker(ticker).fast_info
        _price = float(_info.last_price or _info.previous_close or 0)
        _prev  = float(_info.previous_close or 0)
        _chg   = _price - _prev
        _chg_pct = (_chg / _prev * 100) if _prev > 0 else 0
        _color = "#22c55e" if _chg >= 0 else "#ef4444"
        _sign  = "+" if _chg >= 0 else ""
        if _price > 0:
            st.html(f"""
<div style='background:#0e0e0e;border:1px solid #222;border-radius:8px;
     padding:10px 16px;margin:8px 0;display:inline-flex;align-items:center;gap:16px'>
  <span style='font-size:0.78rem;color:#666;font-family:sans-serif'>{ticker} Kurs</span>
  <span style='font-size:1.1rem;font-weight:700;color:#f0f0f0;font-family:sans-serif'>
    ${_price:.2f}
  </span>
  <span style='font-size:0.82rem;color:{_color};font-family:sans-serif'>
    {_sign}{_chg:.2f} ({_sign}{_chg_pct:.2f}%)
  </span>
  <span style='font-size:0.72rem;color:#444;font-family:sans-serif'>15 Min verzögert</span>
</div>
""")
    except Exception:
        pass

st.markdown("")

# ── Strike-Eingaben je Strategie ──────────────────────────────────────────────
def _leg_inputs(label: str, right: str, default_strike: float = 190.0,
                default_price: float = 1.50) -> tuple[float, float]:
    """Gibt (strike, limit_price) zurück."""
    with st.container():
        st.markdown(f"**{label}**")
        c1, c2 = st.columns(2)
        with c1:
            strike = st.number_input(
                f"Strike ({label})", min_value=0.01, value=default_strike,
                step=0.5, format="%.2f", key=f"strike_{label}"
            )
        with c2:
            limit_price = st.number_input(
                f"Prämie $ ({label})", min_value=0.01, value=default_price,
                step=0.05, format="%.2f", key=f"lmt_{label}",
                help="Limit-Preis pro Aktie (×100 = Kontrakt-Wert)"
            )
    return strike, limit_price


if strategy == "Short Put":
    put_strike, put_lmt = _leg_inputs("Short Put", "P", _default_strike_put, _default_lmt_put)

elif strategy == "Short Call":
    call_strike, call_lmt = _leg_inputs("Short Call", "C", _default_strike_call, _default_lmt_call)

elif strategy == "Short Strangle":
    scol1, scol2 = st.columns(2)
    with scol1:
        put_strike, put_lmt = _leg_inputs("Short Put", "P", _default_strike_put, _default_lmt_put)
    with scol2:
        call_strike, call_lmt = _leg_inputs("Short Call", "C", _default_strike_call, _default_lmt_call)

elif strategy == "Short Put Spread":
    scol1, scol2 = st.columns(2)
    with scol1:
        put_strike, put_lmt = _leg_inputs("Short Put (verkauft)", "P", 185.0, 2.00)
    with scol2:
        put_long_strike, put_long_lmt = _leg_inputs("Long Put (gekauft, Absicherung)", "P", 180.0, 0.80)

elif strategy == "Short Call Spread":
    scol1, scol2 = st.columns(2)
    with scol1:
        call_strike, call_lmt = _leg_inputs("Short Call (verkauft)", "C", 210.0, 1.80)
    with scol2:
        call_long_strike, call_long_lmt = _leg_inputs("Long Call (gekauft, Absicherung)", "C", 215.0, 0.70)

# ── Order-Vorschau ────────────────────────────────────────────────────────────
st.markdown("")
st.html("""
<div style='font-size:0.9rem;font-weight:700;color:#f0f0f0;margin-bottom:8px'>
  📋 Order-Vorschau
</div>
""")


def _preview_box(action: str, right: str, strike: float, qty: int,
                 lmt: float, expiry: str, ticker: str, color: str) -> str:
    right_label = "Put" if right == "P" else "Call"
    action_label = "VERKAUFEN" if action == "SELL" else "KAUFEN"
    premium = lmt * 100 * qty
    exp_fmt = f"{expiry[6:8]}.{expiry[4:6]}.{expiry[:4]}"
    return f"""
<div style='background:#0e0e0e;border:1px solid {color};border-radius:10px;
     padding:16px;margin-bottom:10px'>
  <div style='display:flex;justify-content:space-between;align-items:center'>
    <div>
      <span style='font-size:0.95rem;font-weight:700;color:{color}'>
        {action_label} {qty}x {ticker} {right_label}
      </span>
      <span style='font-size:0.82rem;color:#888;margin-left:10px'>
        Strike ${strike:.2f} · Verfall {exp_fmt}
      </span>
    </div>
    <div style='text-align:right'>
      <div style='font-size:0.85rem;color:#f0f0f0'>
        Limit: ${lmt:.2f}/Aktie
      </div>
      <div style='font-size:0.72rem;color:#888'>
        = ${premium:,.0f} Prämie
      </div>
    </div>
  </div>
  <div style='margin-top:8px;font-size:0.72rem;color:#555;font-family:monospace'>
    transmit=False → Order erscheint in TWS als "Held" (gelb) — du gibst die Freigabe
  </div>
</div>"""


preview_html = ""
orders_to_place: list[OptionOrderParams] = []

if strategy == "Short Put":
    preview_html += _preview_box("SELL", "P", put_strike, quantity, put_lmt,
                                  expiry_str, ticker, "#f59e0b")
    orders_to_place.append(OptionOrderParams(
        ticker=ticker, expiration=expiry_str, strike=put_strike, right="P",
        action="SELL", quantity=quantity, limit_price=put_lmt, order_type=order_type,
    ))

elif strategy == "Short Call":
    preview_html += _preview_box("SELL", "C", call_strike, quantity, call_lmt,
                                  expiry_str, ticker, "#3b82f6")
    orders_to_place.append(OptionOrderParams(
        ticker=ticker, expiration=expiry_str, strike=call_strike, right="C",
        action="SELL", quantity=quantity, limit_price=call_lmt, order_type=order_type,
    ))

elif strategy == "Short Strangle":
    preview_html += _preview_box("SELL", "P", put_strike, quantity, put_lmt,
                                  expiry_str, ticker, "#f59e0b")
    preview_html += _preview_box("SELL", "C", call_strike, quantity, call_lmt,
                                  expiry_str, ticker, "#3b82f6")
    total = (put_lmt + call_lmt) * 100 * quantity
    preview_html += f"""
<div style='background:#0a0e0a;border:1px solid #22c55e;border-radius:8px;
     padding:10px 16px;font-size:0.82rem;color:#22c55e'>
  Gesamtprämie Strangle: ${total:,.0f}
</div>"""
    orders_to_place.append(OptionOrderParams(
        ticker=ticker, expiration=expiry_str, strike=put_strike, right="P",
        action="SELL", quantity=quantity, limit_price=put_lmt, order_type=order_type,
    ))
    orders_to_place.append(OptionOrderParams(
        ticker=ticker, expiration=expiry_str, strike=call_strike, right="C",
        action="SELL", quantity=quantity, limit_price=call_lmt, order_type=order_type,
    ))

elif strategy == "Short Put Spread":
    net_credit = (put_lmt - put_long_lmt) * 100 * quantity
    preview_html += _preview_box("SELL", "P", put_strike, quantity, put_lmt,
                                  expiry_str, ticker, "#f59e0b")
    preview_html += _preview_box("BUY", "P", put_long_strike, quantity, put_long_lmt,
                                  expiry_str, ticker, "#6366f1")
    preview_html += f"""
<div style='background:#0a0e0a;border:1px solid #22c55e;border-radius:8px;
     padding:10px 16px;font-size:0.82rem;color:#22c55e'>
  Netto-Prämie: ${net_credit:,.0f} · Max. Risiko: ${(put_strike - put_long_strike - put_lmt + put_long_lmt)*100*quantity:,.0f}
</div>"""
    orders_to_place.append(OptionOrderParams(
        ticker=ticker, expiration=expiry_str, strike=put_strike, right="P",
        action="SELL", quantity=quantity, limit_price=put_lmt, order_type=order_type,
    ))
    orders_to_place.append(OptionOrderParams(
        ticker=ticker, expiration=expiry_str, strike=put_long_strike, right="P",
        action="BUY", quantity=quantity, limit_price=put_long_lmt, order_type=order_type,
    ))

elif strategy == "Short Call Spread":
    net_credit = (call_lmt - call_long_lmt) * 100 * quantity
    preview_html += _preview_box("SELL", "C", call_strike, quantity, call_lmt,
                                  expiry_str, ticker, "#3b82f6")
    preview_html += _preview_box("BUY", "C", call_long_strike, quantity, call_long_lmt,
                                  expiry_str, ticker, "#6366f1")
    preview_html += f"""
<div style='background:#0a0e0a;border:1px solid #22c55e;border-radius:8px;
     padding:10px 16px;font-size:0.82rem;color:#22c55e'>
  Netto-Prämie: ${net_credit:,.0f} · Max. Risiko: ${(call_long_strike - call_strike - call_lmt + call_long_lmt)*100*quantity:,.0f}
</div>"""
    orders_to_place.append(OptionOrderParams(
        ticker=ticker, expiration=expiry_str, strike=call_strike, right="C",
        action="SELL", quantity=quantity, limit_price=call_lmt, order_type=order_type,
    ))
    orders_to_place.append(OptionOrderParams(
        ticker=ticker, expiration=expiry_str, strike=call_long_strike, right="C",
        action="BUY", quantity=quantity, limit_price=call_long_lmt, order_type=order_type,
    ))

st.html(preview_html)

# ══════════════════════════════════════════════════════════════════════════════
# ORDER AUSFÜHREN — Methode 1: Basket Trader Export (für alle Nutzer)
# ══════════════════════════════════════════════════════════════════════════════

def _generate_basket_csv(orders: list) -> str:
    """TWS Basket Trader CSV-Format (File → Import → Basket Trader in TWS)."""
    header = ("Action,Quantity,Symbol,SecType,"
              "LastTradingDayOrContractMonth,Strike,Right,"
              "Exchange,Currency,TimeInForce,OrderType,LmtPrice,Comment")
    lines = [header]
    for o in orders:
        ot = getattr(o, "order_type", "LMT")
        lmt = f"{o.limit_price:.2f}" if ot == "LMT" else ""
        lines.append(
            f"{o.action},{o.quantity},{o.ticker},OPT,"
            f"{o.expiration},{o.strike:.2f},{o.right},"
            f"SMART,USD,DAY,{ot},{lmt},Stillhalter AI App"
        )
    return "\n".join(lines)


st.html("""
<div style='font-size:0.95rem;font-weight:700;color:#f0f0f0;margin:20px 0 6px'>
  🚀 Order übertragen
</div>
""")

# Methode 1: Basket Export
with st.container():
    st.markdown("""
<div style='background:#0a120a;border:1px solid #22c55e;border-radius:12px;
     padding:16px 20px;margin-bottom:10px'>
<div style='font-size:0.88rem;font-weight:700;color:#22c55e;margin-bottom:6px'>
  📥 Methode 1 — TWS Basket Trader (empfohlen · für alle Nutzer)</div>
<div style='font-size:0.78rem;color:#6b7280;line-height:1.6'>
  Exportiert die Order als CSV-Datei → in TWS importieren → in Ruhe prüfen → absenden.<br>
  <b>TWS:</b> File → Import → Basket Trader → CSV auswählen → Submit All<br>
  <span style='color:#4ade80'>✓ Kein Bridge · Kein Tunnel · Funktioniert für alle Nutzer</span>
</div></div>
""", unsafe_allow_html=True)

    if orders_to_place:
        csv_data = _generate_basket_csv(orders_to_place)
        fname = f"order_{ticker}_{expiry_str}.csv"
        st.download_button(
            "📥 Als TWS-Basket-Datei exportieren",
            data=csv_data,
            file_name=fname,
            mime="text/csv",
            type="primary",
            use_container_width=True,
            help="TWS → File → Import → Basket Trader → Datei öffnen → Submit All",
        )
    else:
        st.button("📥 Als TWS-Basket-Datei exportieren", disabled=True,
                  use_container_width=True,
                  help="Bitte oben Ticker und Strike eingeben")

st.markdown("<div style='height:4px'></div>", unsafe_allow_html=True)

# Methode 2: Direkte TWS-Verbindung (Bridge oder lokal)
st.markdown("""
<div style='background:#0e0e14;border:1px solid #374151;border-radius:12px;
     padding:14px 18px;margin-bottom:10px'>
<div style='font-size:0.88rem;font-weight:700;color:#9ca3af;margin-bottom:6px'>
  🔌 Methode 2 — Direkt in TWS platzieren (Bridge / Lokal)</div>
<div style='font-size:0.78rem;color:#4b5563;line-height:1.6'>
Platziert die Order live in TWS als <b>"Held"</b> (gelb, noch nicht übertragen).<br>
Du gibst die finale Freigabe direkt in TWS durch Klick auf <b>Transmit</b>.<br>
<i>Voraussetzung: TWS Verbindung oben konfiguriert und getestet.</i>
</div></div>
""", unsafe_allow_html=True)

# ── Order-Button ──────────────────────────────────────────────────────────────
btn_disabled = not (st.session_state.ibkr_connected and IB_INSYNC_INSTALLED)
btn_label = "📋 Order in TWS platzieren (Held)" if not btn_disabled else \
            "🔌 Zuerst TWS verbinden" if not st.session_state.ibkr_connected else \
            "⚠️ ib_insync nicht installiert"

confirm_col, btn_col = st.columns([3, 1])
with confirm_col:
    is_live_mode = st.session_state.ibkr_config and \
                   st.session_state.ibkr_config.port in (7496, 4001)
    if is_live_mode:
        confirmed = st.checkbox(
            "Ich bestätige: Dies ist Live Trading mit echtem Geld",
            value=False
        )
        btn_disabled = btn_disabled or not confirmed
with btn_col:
    place_clicked = st.button(
        btn_label,
        type="primary",
        disabled=btn_disabled,
        use_container_width=True,
    )

# ── Order ausführen ───────────────────────────────────────────────────────────
if place_clicked:
    cfg = _config()
    use_bridge_mode = isinstance(cfg, dict) and cfg.get("mode") == "bridge"

    with st.spinner(f"Platziere {len(orders_to_place)} Order(s) in TWS..."):
        for params in orders_to_place:
            if use_bridge_mode:
                # Bridge-Modus: HTTP-Request an lokale Bridge
                import requests as _req
                try:
                    r = _req.post(
                        f"{cfg['url']}/order",
                        json={
                            "ticker":      params.ticker,
                            "expiration":  params.expiration,
                            "strike":      params.strike,
                            "right":       params.right,
                            "action":      params.action,
                            "quantity":    params.quantity,
                            "limit_price": params.limit_price,
                            "order_type":  params.order_type,
                        },
                        headers={"X-API-Key": cfg["key"]},
                        timeout=15,
                    )
                    data = r.json()
                    order_id = data.get("order_id", -1)
                    error = data.get("error") if r.status_code != 200 else None
                    desc = (f"{params.action} {params.quantity}x {params.ticker} "
                            f"{params.strike}{params.right} {params.expiration}")
                    st.session_state.placed_orders.append({
                        "Zeit":         datetime.now().strftime("%H:%M:%S"),
                        "Ticker":       params.ticker,
                        "Beschreibung": desc,
                        "Limit $":      f"${params.limit_price:.2f}",
                        "Order-ID":     order_id,
                        "Status":       "Held" if not error else "Fehler",
                        "Fehler":       error or "",
                    })
                    if error:
                        st.error(f"Fehler: {error}")
                    else:
                        st.success(f"Platziert (Held): {desc} · Order-ID {order_id}")
                except Exception as e:
                    st.error(f"Bridge nicht erreichbar: {e}")

            elif IBKR_AVAILABLE:
                # Lokal-Modus: direkte ib_insync Verbindung
                result = place_option_order(params, cfg)
                st.session_state.placed_orders.append({
                    "Zeit":         datetime.now().strftime("%H:%M:%S"),
                    "Ticker":       result.ticker,
                    "Beschreibung": result.description,
                    "Limit $":      f"${result.limit_price:.2f}",
                    "Order-ID":     result.order_id,
                    "Status":       result.status,
                    "Fehler":       result.error or "",
                })
                if result.error:
                    st.error(f"Fehler: {result.error}")
                else:
                    st.success(f"Platziert: {result.description} (ID {result.order_id})")

    st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# OFFENE ORDERS IN TWS
# ══════════════════════════════════════════════════════════════════════════════
st.divider()
st.html("""
<div style='font-size:1.05rem;font-weight:700;color:#f0f0f0;margin-bottom:12px'>
  📊 Offene Orders in TWS
</div>
""")

refresh_col, _ = st.columns([1, 4])
with refresh_col:
    refresh = st.button("Aktualisieren", disabled=not st.session_state.ibkr_connected)

if refresh and st.session_state.ibkr_connected and IBKR_AVAILABLE:
    with st.spinner("Lade offene Orders..."):
        open_orders = get_open_orders(_config())
    if open_orders:
        df_open = pd.DataFrame(open_orders)
        # Spalten umbenennen für Anzeige
        col_rename = {
            "order_id": "Order-ID",
            "ticker": "Ticker",
            "action": "Aktion",
            "qty": "Kontrakte",
            "limit_price": "Limit $",
            "status": "Status",
            "strike": "Strike",
            "expiry": "Verfall",
            "right": "Put/Call",
            "sec_type": "Typ",
        }
        df_open = df_open.rename(columns=col_rename)

        # Status-Farbe
        def _status_color(s: str) -> str:
            if s in ("Submitted", "Filled"):
                return "color: #22c55e"
            elif s in ("PreSubmitted", "Held"):
                return "color: #f59e0b"
            elif s in ("Cancelled", "Inactive"):
                return "color: #ef4444"
            return "color: #888"

        st.dataframe(
            df_open,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Status": st.column_config.TextColumn("Status"),
            }
        )

        # Stornieren-Bereich
        st.markdown("**Order stornieren:**")
        cancel_id = st.number_input("Order-ID zum Stornieren", min_value=0, step=1, value=0)
        if st.button("Stornieren", disabled=cancel_id == 0):
            ok, msg = cancel_held_order(int(cancel_id), _config())
            if ok:
                st.success(msg)
            else:
                st.error(msg)
    else:
        st.info("Keine offenen Orders in TWS gefunden.")

# ══════════════════════════════════════════════════════════════════════════════
# SESSION HISTORIE
# ══════════════════════════════════════════════════════════════════════════════
if st.session_state.placed_orders:
    st.divider()
    st.html("""
<div style='font-size:1.0rem;font-weight:700;color:#f0f0f0;margin-bottom:8px'>
  🕐 Orders dieser Session
</div>
""")
    df_hist = pd.DataFrame(st.session_state.placed_orders)
    st.dataframe(df_hist, use_container_width=True, hide_index=True)

    if st.button("Verlauf löschen"):
        st.session_state.placed_orders = []
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# SETUP-ANLEITUNG (kollabiert)
# ══════════════════════════════════════════════════════════════════════════════
with st.expander("⚙️ TWS Setup-Anleitung", expanded=True):
    st.markdown("""
**Schritt 1 — TWS starten und einloggen**
- Trader Workstation (TWS) öffnen und mit deinem IBKR-Account einloggen

**Schritt 2 — API-Einstellungen öffnen**
- In TWS oben: **Bearbeiten → Globale Konfiguration**
- Links in der Liste: **API → Einstellungen**

**Schritt 3 — Diese Einstellungen vornehmen**

| Einstellung | Wert |
|---|---|
| ✅ ActiveX- und Socket-Clients aktivieren | einschalten |
| ☐ Schreibgeschützte API | **ausschalten** (sonst keine Orders möglich) |
| Socket Port | `7497` (Paper Trading) |
| ✅ Nur Verbindungen vom lokalen Host zulassen | einschalten |
| Vertrauenswürdige IPs | `127.0.0.1` eintragen → **Erstellen** klicken |

→ **Übernehmen** klicken, dann TWS neu starten

**Schritt 4 — Verbindung hier testen**
- Host: `127.0.0.1` · Modus: Paper Trading (TWS) · Client ID: `42`
- Auf **"Verbindung testen"** klicken → bei Erfolg erscheinen deine Kontodaten

**Schritt 5 — Held Orders verstehen**
- Die App platziert Orders mit `transmit=False` → erscheinen in TWS **gelb ("Held")**
- Sie werden **nicht** an die Börse gesendet
- Du gibst die finale Freigabe direkt in TWS: Rechtsklick auf die Order → **Übertragen**

**Port-Referenz**

| Software | Modus | Port |
|---|---|---|
| TWS | Paper Trading | 7497 |
| TWS | Live Trading | 7496 |
| IB Gateway | Paper | 4002 |
| IB Gateway | Live | 4001 |
""")
