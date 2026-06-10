"""
Stillhalter AI — Signal-Pipeline Renderer
• render_whatsapp()  : kurzer Teaser-Post (§4 der Spec)
• render_circle()    : vollständige Trade Card als HTML (§5 der Spec)

WhatsApp: Management zuerst (Retention), neue Setups ohne Strike-Details → Klick.
Circle:   Alle Details, Expressions nach Eignungsstufe gefiltert.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Tuple

from data.trade_store import Expression, TradeCard

# ── Icons & Mapping ───────────────────────────────────────────────────────────

_RISK_ICON = {
    "defensiv":       "🟢",
    "balanced":       "🟡",
    "opportunistisch": "🔴",
}
_STATUS_ICON = {
    "NEU":       "🆕",
    "AKTIV":     "✅",
    "WATCH":     "👁️",
    "WARNING":   "⚠️",
    "ROLL":      "🔄",
    "CLOSE":     "🏁",
    "CANCELLED": "❌",
    "EXPIRED":   "⏰",
    "REVIEWED":  "📋",
}
_VIEW_DE = {
    "bullisch":         "Bullisch 📈",
    "bullisch-neutral": "Bullisch-neutral",
    "neutral":          "Neutral",
    "bärisch-neutral":  "Bärisch-neutral",
    "bärisch":          "Bärisch 📉",
}
_EIGNUNG_RANK = {"einsteiger": 0, "fortgeschritten": 1, "profi": 2}

_DISCLAIMER = (
    "Schulische Trading-Idee für die Community. "
    "Keine individuelle Anlageberatung. "
    "Live-Prämien immer direkt im OptionStrat-Link prüfen."
)


def _fmt_date(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y")
    except Exception:
        return iso[:10] if len(iso) >= 10 else iso


def _grade_color(grade: str) -> str:
    if grade.startswith("A"): return "#22c55e"
    if grade.startswith("B"): return "#f59e0b"
    return "#ef4444"


# ═══════════════════════════════════════════════════════════════════════════════
# WHATSAPP RENDERER (§4)
# ═══════════════════════════════════════════════════════════════════════════════

def render_whatsapp(
    new_cards: List[TradeCard],
    status_changes: List[Tuple[TradeCard, str, str]],  # (card, new_status, reason)
    datum: str = "",
) -> str:
    """
    Täglicher WhatsApp-Post nach §4-Vorlage.

    Regeln:
    • Management (Statuswechsel) ZUERST — Retention-Anker
    • Neue Setups: kein Strike, keine Struktur, kein Management-Detail
    • Info-Gap macht den Circle-Klick wertvoll
    • An ideen­losen Tagen: nur Management-Block
    """
    if not datum:
        datum = datetime.now().strftime("%d.%m.%Y")

    lines: List[str] = [f"📊 Stillhalter AI · Daily · {datum}", ""]

    # ── MANAGEMENT ────────────────────────────────────────────────────────────
    if status_changes:
        lines.append("⚙️ MANAGEMENT (laufende Setups)")
        for card, new_s, reason in status_changes:
            expr       = card.expressions[0] if card.expressions else None
            strat_kurz = (
                expr.strategy
                .replace("Cash-Secured ", "CS-")
                .replace(" Credit Spread", "-Spread")
                if expr else "–"
            )
            icon = _STATUS_ICON.get(new_s, "•")
            short_reason = reason[:60] + "…" if len(reason) > 60 else reason
            lines.append(f"• {card.ticker} {strat_kurz} → {icon} {new_s}  {short_reason}")
            if card.circle_url:
                lines.append(f"  {card.circle_url}")
        lines.append("")

    # ── NEUE SETUPS ───────────────────────────────────────────────────────────
    if new_cards:
        lines.append("💡 NEUE SETUPS")
        for i, card in enumerate(new_cards, 1):
            risk_icon = _RISK_ICON.get(card.risk_class, "•")
            expr      = card.expressions[0] if card.expressions else None
            anchor    = expr.strike_anchor if expr else "–"
            view_str  = _VIEW_DE.get(card.view, card.view)
            lines.append(
                f"{i}. {risk_icon} {card.risk_class.capitalize()} · "
                f"{card.ticker} · {card.laufzeit} · Grade {card.signal_grade}"
            )
            lines.append(f"   {view_str} · {anchor}")
            if card.circle_url:
                lines.append(f"   {card.circle_url}")
            else:
                lines.append(f"   → Struktur + Live-Prämie im Circle-Post")
        lines.append("")
        lines.append("Tracking + konkrete Struktur + Live-Prämie im Link.")
    else:
        lines += [
            "Heute Fokus Management — keine neuen Setups.",
            "Das ist Stillhalter-Disziplin, kein Mangel. 💪",
        ]

    lines += ["", _DISCLAIMER]
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
# CIRCLE RENDERER (§5)
# ═══════════════════════════════════════════════════════════════════════════════

def _visible_exprs(
    card: TradeCard,
    member_level: str,
) -> Tuple[List[Expression], List[Expression]]:
    """Gibt (sichtbare Expressions, [Teaser der nächsten Stufe]) zurück."""
    rank    = _EIGNUNG_RANK.get(member_level, 0)
    visible: List[Expression] = []
    teaser:  List[Expression] = []
    for e in card.expressions:
        e_rank = _EIGNUNG_RANK.get(e.eignung, 0)
        if e.min_vip and member_level != "profi":
            if not teaser:
                teaser.append(e)
        elif e_rank <= rank:
            visible.append(e)
        elif not teaser:
            teaser.append(e)
    return visible, teaser


def _expr_html(e: Expression, locked: bool = False, next_tier: str = "") -> str:
    if locked:
        return (
            f'<div style="background:#f1f5f9;border-left:3px solid #94a3b8;'
            f'padding:12px 16px;margin:8px 0;border-radius:4px;opacity:0.65">'
            f'🔒 ab {next_tier}: <b>{e.strategy}</b> — {e.strike_anchor}'
            f'</div>'
        )
    risk_badge = (
        '<span style="color:#22c55e;font-weight:600">✅ Definiertes Risiko</span>'
        if e.defined_risk
        else '<span style="color:#f59e0b">⚠️ Undefiniertes Risiko</span>'
    )
    vip_badge = ' &nbsp;<span style="background:#8b5cf6;color:#fff;font-size:0.7rem;padding:2px 6px;border-radius:10px">VIP</span>' if e.min_vip else ""
    return (
        f'<div style="background:#f8f9fa;border-left:3px solid #22c55e;'
        f'padding:12px 16px;margin:8px 0;border-radius:4px">'
        f'<b>{e.strategy}</b>{vip_badge} — Eignung: <i>{e.eignung.capitalize()}</i><br>'
        f'📍 {e.strike_anchor}<br>'
        f'📅 Laufzeit: {e.dte} Tage &nbsp;|&nbsp; 💰 {e.kapitalbedarf}'
        f'{"<br>🔢 Strikes: " + e.strikes if e.strikes else ""}<br>'
        f'{risk_badge}<br>'
        f'<a href="{e.optionstrat_url}" target="_blank" style="color:#3b82f6">'
        f'📊 Live-Prämie auf OptionStrat prüfen →</a>'
        f'</div>'
    )


def render_circle(card: TradeCard, member_level: str = "einsteiger") -> dict:
    """
    Rendert vollständige Trade Card als HTML (§5).
    Gibt {"title": str, "html": str} zurück.
    """
    visible_exprs, teaser_exprs = _visible_exprs(card, member_level)
    risk_icon    = _RISK_ICON.get(card.risk_class, "•")
    status_icon  = _STATUS_ICON.get(card.status, "•")
    grade_color  = _grade_color(card.signal_grade)
    c            = card.components

    # Komponenten-Badges
    trend_badge = {"+": "↑ Trend 🟢", "0": "→ Trend 🟡", "-": "↓ Trend 🔴"}.get(c.trend, c.trend)
    macd_badge  = {"bestätigt": "MACD ✅", "neutral": "MACD →", "gegen": "MACD ⚠️"}.get(c.macd, c.macd)
    earn_badge  = {
        "clear":         "Earnings OK ✅",
        "vor_earnings":  "⚠️ Earnings bald",
        "nach_earnings": "Earnings vorbei",
    }.get(c.earnings, c.earnings)
    liq_badge   = {"hoch": "Liq. 🟢", "mittel": "Liq. 🟡", "niedrig": "Liq. 🔴"}.get(c.liquiditaet, c.liquiditaet)
    source_label = "Echtgeld (IBKR) 🏦" if card.source == "live_ibkr" else "Modell-Setup 🖥️"

    # Expressions HTML
    next_tier_label = {"einsteiger": "Masterclass", "fortgeschritten": "VIP"}.get(member_level, "VIP")
    exprs_html = "".join(_expr_html(e) for e in visible_exprs)
    exprs_html += "".join(_expr_html(e, locked=True, next_tier=next_tier_label) for e in teaser_exprs)

    # Status-Historie (letzte 5 Einträge, neueste zuerst)
    hist_items = "".join(
        f"<li>{_fmt_date(ev.ts)} — {_STATUS_ICON.get(ev.status,'•')} "
        f"<b>{ev.status}</b>: {ev.note or '–'}</li>"
        for ev in reversed(card.status_history[-5:])
    )

    title = (
        f"{risk_icon} {card.ticker} · Grade {card.signal_grade} · "
        f"{card.laufzeit} · {_VIEW_DE.get(card.view, card.view)}"
    )

    html = f"""
<div style="font-family:system-ui,sans-serif;max-width:740px;line-height:1.6">

<!-- Header -->
<div style="display:flex;align-items:flex-start;gap:16px;margin-bottom:16px;
            border-bottom:2px solid #e2e8f0;padding-bottom:16px">
  <span style="font-size:2.5rem">{risk_icon}</span>
  <div style="flex:1">
    <h2 style="margin:0 0 4px">{card.ticker}</h2>
    <div style="color:#64748b;font-size:0.85rem">
      <code>{card.trade_id}</code> &nbsp;·&nbsp; {source_label}
    </div>
  </div>
  <div style="text-align:right">
    <div style="font-size:2rem;font-weight:700;color:{grade_color}">{card.signal_grade}</div>
    <div style="font-size:0.75rem;color:#94a3b8">Signal-Grade</div>
  </div>
</div>

<!-- Meta-Badges -->
<p style="color:#475569;font-size:0.9rem;margin:0 0 16px">
  {status_icon} <b>{card.status}</b> &nbsp;·&nbsp;
  Laufzeit: <b>{card.laufzeit}</b> &nbsp;·&nbsp;
  Risiko: <b>{card.risk_class.capitalize()}</b> &nbsp;·&nbsp;
  {_VIEW_DE.get(card.view, card.view)}
</p>

<!-- Signal-Komponenten -->
<h3 style="margin:16px 0 8px">📡 Signal-Komponenten</h3>
<div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:16px">
  <span style="background:#f0fdf4;border:1px solid #86efac;padding:4px 10px;border-radius:20px;font-size:0.82rem">
    IV-Rank <b>{c.iv_rank:.0f}/100</b>
  </span>
  <span style="background:#f0fdf4;border:1px solid #86efac;padding:4px 10px;border-radius:20px;font-size:0.82rem">
    IV/RV <b>{c.iv_rv:.1f}</b>
  </span>
  <span style="background:#f8fafc;border:1px solid #cbd5e1;padding:4px 10px;border-radius:20px;font-size:0.82rem">
    {trend_badge}
  </span>
  <span style="background:#f8fafc;border:1px solid #cbd5e1;padding:4px 10px;border-radius:20px;font-size:0.82rem">
    {macd_badge}
  </span>
  <span style="background:#f8fafc;border:1px solid #cbd5e1;padding:4px 10px;border-radius:20px;font-size:0.82rem">
    {earn_badge}
  </span>
  <span style="background:#f8fafc;border:1px solid #cbd5e1;padding:4px 10px;border-radius:20px;font-size:0.82rem">
    {liq_badge}
  </span>
</div>

<!-- These -->
<h3 style="margin:16px 0 8px">🧠 These — Warum dieser Trade?</h3>
<p style="background:#fffbeb;border-left:4px solid #fbbf24;padding:12px 16px;border-radius:4px;margin:0 0 16px">
  {card.thesis}
</p>

<!-- Struktur -->
<h3 style="margin:16px 0 8px">🏗️ Struktur ({member_level.capitalize()}-Sicht)</h3>
{exprs_html}

<!-- Management -->
<h3 style="margin:16px 0 8px">🛡️ Management-Regeln</h3>
<ul style="margin:0 0 16px;padding-left:20px">
  <li>Take Profit: <b>{card.management.take_profit_pct*100:.0f}%</b> Prämienrückgang → Position schließen</li>
  <li>Rollen ab: <b>DTE ≤ {card.management.roll_dte}</b> oder Delta ≥ <b>{card.management.roll_delta:.2f}</b></li>
  <li>⚠️ Warning: {card.management.warning}</li>
  <li>❌ Abbruch: {card.management.cancel}</li>
</ul>
<blockquote style="color:#64748b;font-style:italic;border-left:3px solid #e2e8f0;
                   padding:8px 16px;margin:0 0 16px;background:#f8fafc">
  ⚡ Prämien täglich prüfen — OptionStrat-Links zeigen Live-Kurse.
  Struktur immer an eigenes Kapital und Risikoprofil anpassen.
</blockquote>

<!-- Status-Historie -->
<h3 style="margin:16px 0 8px">📋 Status-Verlauf</h3>
<ul style="margin:0 0 16px;padding-left:20px;color:#475569;font-size:0.9rem">
  {hist_items}
</ul>

<hr style="border:none;border-top:1px solid #e2e8f0;margin:24px 0 12px">
<p style="color:#94a3b8;font-size:0.75rem;margin:0">{_DISCLAIMER}</p>

</div>"""

    return {"title": title, "html": html}
