"""Trade-Karten im Trade-Monitor-Look — fuer das Depot-Dashboard (Seite 22).

Gleiche visuelle Sprache wie pages/20_Trade_Monitor.py (Zeitstrahl,
Kurs-Strike-Skala, Kennzahl-Kacheln, Status-Pille), aber gespeist aus den
IBKR-Flex-Positionen statt aus manuell gespeicherten Trades.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd


def depot_option_card_html(pos: dict, txt_main: str, txt_sub: str,
                           txt_muted: str, card_bg: str,
                           ev: dict | None = None) -> str:
    """Eine Optionsposition als Trade-Monitor-Karte.

    pos: ticker, is_call, is_short, strike, expiry, qty, mark, premium,
         pnl_usd, kurs (Aktienkurs oder 0)
    ev:  optionales Ergebnis von trading.position_eval.evaluate_position —
         liefert dann Empfehlung + Farbe wie im Trade Management.
    """
    ticker   = pos.get("ticker", "–")
    is_call  = bool(pos.get("is_call"))
    is_short = bool(pos.get("is_short", True))
    strike   = float(pos.get("strike", 0) or 0)
    qty      = int(pos.get("qty", 0) or 0)
    mark     = float(pos.get("mark", 0) or 0)
    premium  = float(pos.get("premium", 0) or 0)
    pnl_usd  = pos.get("pnl_usd")
    price    = float(pos.get("kurs", 0) or 0)

    strategy = (("Short " if is_short else "Long ") + ("Call" if is_call else "Put"))

    try:
        end = pd.to_datetime(pos.get("expiry")).date()
    except Exception:
        end = date.today()
    today = date.today()
    dte = max(0, (end - today).days)

    # Kurs vs. Strike: Abstand (positiv = aus dem Geld) + ITM-Flag
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

    # Zeitstrahl: Einstieg unbekannt → typischer 45-DTE-Einstieg angenommen
    # (gleiche Annahme wie das Theta-Modell im Trade Management)
    start = min(end - timedelta(days=45), today)
    total = max(1, (end - start).days)
    elapsed = min(total, max(0, (today - start).days))
    elapsed_pct = round(elapsed / total * 100)

    decay = ((premium - mark) / premium * 100) if (is_short and premium > 0 and mark > 0) else None

    G, R = "#22c55e", "#ef4444"
    _price_str = f"${price:.2f}" if price > 0 else "–"
    _opt_str   = f"${mark:.2f}" if mark > 0 else "–"
    _otm_lbl   = "ITM" if itm else "OTM"

    # Kurs↔Strike-Skala: Strike mittig, Preis-Marker, farbige Zonen
    _lo, _hi = strike * 0.85, strike * 1.15
    _ppos = ((price - _lo) / (_hi - _lo) * 100) if (price > 0 and _hi > _lo) else 50.0
    _ppos = max(4, min(96, _ppos))
    if is_call:
        _zone = f"linear-gradient(90deg,{G}33 0%,{G}1f 49%,{R}1f 51%,{R}33 100%)"
    else:
        _zone = f"linear-gradient(90deg,{R}33 0%,{R}1f 49%,{G}1f 51%,{G}33 100%)"

    def _tile(label: str, value: str, vcolor: str, sub: str = "") -> str:
        sub_html = (f"<div style='font-size:0.7rem;color:{txt_sub};margin-top:1px'>{sub}</div>"
                    if sub else "")
        return (
            f"<div style='flex:1;min-width:74px;background:{card_bg};border:1px solid {txt_sub}55;"
            f"border-radius:8px;padding:8px 8px;text-align:center'>"
            f"<div style='font-size:0.72rem;color:{txt_sub};text-transform:uppercase;"
            f"letter-spacing:0.04em'>{label}</div>"
            f"<div style='font-size:1.12rem;font-weight:700;color:{vcolor};margin-top:2px'>{value}</div>"
            f"{sub_html}</div>"
        )

    pnl_col  = G if (pnl_usd or 0) >= 0 else R
    _pnl_str = f"{pnl_usd:+,.0f} $" if pnl_usd is not None else "–"

    tiles = (
        _tile("Abstand", f"{otm:+.1f}% {_otm_lbl}", col,
              sub=f"{abs(qty)} Kontrakt{'e' if abs(qty) != 1 else ''}")
        + _tile("Option", _opt_str, txt_main,
                sub=(f"Einstieg ${premium:.2f}" if premium > 0 else ""))
        + _tile("P&L", _pnl_str, pnl_col,
                sub=(f"{decay:+.0f}% der Prämie" if decay is not None else ""))
        + _tile("Rest", f"{dte} T", txt_main, sub=end.strftime("%d.%m.%y"))
    )

    # Handlungszeile: Stillhalter-Bewertung (falls vorhanden), sonst
    # dieselbe 5-Status-Kurzlogik wie im Trade Monitor
    if ev and ev.get("empfehlung") and ev["empfehlung"] != "–":
        action, action_col = ev["empfehlung"], ev.get("empfehlung_color", txt_main)
    else:
        action_col = txt_main
        if dte <= 0:
            action = ("📋 Abgelaufen — wertlos verfallen ✅" if not itm
                      else "📋 Abgelaufen — Einbuchung prüfen")
        elif not is_short:
            action = "📋 Long-Position (Absicherung / Spread-Leg)"
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

    _tp_html = (f"🎯 TP 50% ≤ ${premium*0.5:.2f} · TP 70% ≤ ${premium*0.3:.2f}"
                if (is_short and premium > 0) else "")

    # Earnings-Badge aus der Bewertung
    earnings_badge = ""
    if ev and ev.get("earnings"):
        earnings_badge = (
            f"<span style='background:#f59e0b22;color:#f59e0b;font-size:0.78rem;"
            f"font-weight:700;padding:3px 10px;border-radius:6px'>"
            f"⚠️ Earnings {ev['earnings']}</span>"
        )

    return f"""
<div style='background:{card_bg};border:1px solid {col}40;border-radius:14px;
            padding:14px 16px;margin-bottom:12px;box-shadow:0 1px 4px rgba(0,0,0,0.18);
            font-family:RedRose,sans-serif'>
  <div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:12px'>
    <div style='display:flex;align-items:center;gap:10px;flex-wrap:wrap'>
      <span style='font-weight:700;font-size:1.4rem;color:{txt_main};letter-spacing:0.02em'>{ticker}</span>
      <span style='background:{col}2a;color:{col};font-size:0.85rem;font-weight:700;
                   padding:3px 10px;border-radius:6px'>{strategy} ${strike:g}</span>
      <span style='color:{txt_sub};font-size:0.82rem;font-weight:600'>IBKR</span>
      {earnings_badge}
    </div>
    <span style='background:{col};color:#fff;font-size:0.9rem;font-weight:700;
                 padding:5px 16px;border-radius:20px;white-space:nowrap'>{word}</span>
  </div>

  <div style='display:flex;justify-content:space-between;font-size:0.78rem;color:{txt_sub};margin-bottom:5px'>
    <span>📅 Laufzeit (Einstieg ~45 DTE angenommen)</span>
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
    <span>💵 Kurs {_price_str}</span>
    <span>🎯 Strike ${strike:g}</span>
  </div>

  <div style='display:flex;gap:8px;margin-top:12px'>{tiles}</div>

  <div style='display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;
              gap:6px;margin-top:10px'>
    <span style='font-size:0.9rem;color:{action_col};font-weight:600'>→ {action}</span>
    <span style='font-size:0.78rem;color:{txt_sub}'>{_tp_html}</span>
  </div>
</div>
"""
