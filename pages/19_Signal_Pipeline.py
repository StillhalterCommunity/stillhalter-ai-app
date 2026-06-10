"""
Stillhalter AI App — Signal Pipeline & Freigabe-Gate  (§8 der Spec)

Workflow:
  1. Scan-Ergebnisse → Kandidaten bewerten und als Trade Card speichern
  2. Offene Cards: Status täglich prüfen und ggf. manuell wechseln
  3. Freigabe → WhatsApp-Text + Circle-HTML vorschau → Senden/Posten
"""
import os
import pickle
from dataclasses import replace
from datetime import datetime

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="Signal Pipeline · Stillhalter AI App",
    page_icon="🚦",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from ui.theme import get_css, get_logo_html
from ui.sidebar import render_sidebar
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)
render_sidebar()

import data.trade_store as store
from data.trade_store import ModelEntry, StatusEvent, TradeCard
from analysis.signal_engine import (
    apply_status_change,
    candidate_card_from_row,
    signal_grade,
)
from pipeline.renderers import render_circle, render_whatsapp
from pipeline.publishers import CirclePublisher, WhatsAppPublisher

# ── Header ────────────────────────────────────────────────────────────────────
h1, h2 = st.columns([1, 6])
with h1:
    st.markdown(get_logo_html("white", 36), unsafe_allow_html=True)
with h2:
    st.markdown(
        '<div class="sc-page-title">🚦 Signal Pipeline</div>'
        '<div class="sc-page-subtitle">'
        "Tägliches Briefing · Kandidaten freigeben · WhatsApp & Circle publizieren"
        "</div>",
        unsafe_allow_html=True,
    )
st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

# ── Secrets laden ─────────────────────────────────────────────────────────────
def _sec(key: str, default: str = "") -> str:
    try:
        return str(st.secrets.get(key, os.environ.get(key, default)))
    except Exception:
        return os.environ.get(key, default)

_wa_key      = _sec("WHATSAPP_API_KEY")
_wa_channel  = _sec("WHATSAPP_CHANNEL_ID")
_wa_provider = _sec("WHATSAPP_PROVIDER", "wassenger")
_ci_token    = _sec("CIRCLE_API_TOKEN")
_ci_spaces   = {
    "daily":        int(_sec("CIRCLE_SPACE_DAILY",        "0") or 0),
    "masterclass":  int(_sec("CIRCLE_SPACE_MASTERCLASS",  "0") or 0),
    "vip":          int(_sec("CIRCLE_SPACE_VIP",          "0") or 0),
}
_wa_ok = bool(_wa_key and _wa_channel)
_ci_ok = bool(_ci_token and any(_ci_spaces.values()))

# ── Scan-Cache laden ──────────────────────────────────────────────────────────
_CACHE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "last_scan_cache.pkl")

@st.cache_data(ttl=300, show_spinner=False)
def _load_scan() -> pd.DataFrame:
    try:
        with open(_CACHE, "rb") as f:
            return pickle.load(f).get("results", pd.DataFrame())
    except Exception:
        return pd.DataFrame()

scan_df    = _load_scan()
open_cards = store.load_open()

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_neu, tab_offen, tab_publish, tab_cfg = st.tabs([
    "🆕 Neue Kandidaten",
    "📋 Offene Trades",
    "📤 Freigabe & Publish",
    "⚙️ Konfiguration",
])

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — NEUE KANDIDATEN (aus Scan-Ergebnis)
# ═══════════════════════════════════════════════════════════════════════════════
with tab_neu:
    if scan_df is None or scan_df.empty:
        st.warning(
            "Kein Scan-Ergebnis. Bitte zuerst im **Watchlist Scanner** einen Scan starten."
        )
        if st.button("➜ Zum Scanner", type="primary"):
            st.switch_page("pages/04_Watchlist_Scanner.py")
        st.stop()

    st.info(
        f"**{len(scan_df)} Optionen** aus letztem Scan · "
        f"Top-Kandidaten nach CRV Score — These ergänzen und freigeben.",
        icon="📊",
    )

    sort_col = "CRV Score" if "CRV Score" in scan_df.columns else scan_df.columns[0]
    top_scan = (
        scan_df.sort_values(sort_col, ascending=False)
        .drop_duplicates(subset=["Ticker"])
        .head(9)
        .reset_index(drop=True)
    )

    existing_tickers = {c.ticker for c in open_cards}

    for idx, row in top_scan.iterrows():
        ticker  = str(row.get("Ticker", ""))
        crv     = float(row.get("CRV Score", 0))
        dte     = int(row.get("DTE", 30))
        delta   = float(row.get("Delta", 0))
        iv_pct  = float(row.get("IV %", 25))
        otm     = float(row.get("OTM %", 5))
        prem    = float(row.get("Prämie", 0))
        conv    = float(row.get("Konvergenz", 0))
        kurs    = float(row.get("Kurs", 0))
        expiry  = str(row.get("Verfall", ""))
        sc      = str(row.get("SC Trend(1D)", ""))
        already = ticker in existing_tickers

        auto_grade = signal_grade(crv, conv, iv_pct)
        label = (
            f"**{ticker}** · Grade {auto_grade} · CRV {crv:.0f} · "
            f"{dte}T · Δ {delta:.2f} · {otm:.1f}% OTM"
            + (" ✅ gespeichert" if already else "")
        )

        with st.expander(label, expanded=(idx == 0 and not already)):
            col_l, col_r = st.columns([3, 2])

            with col_l:
                thesis_val = (
                    f"{ticker} zeigt {'bullisches' if 'bull' in sc.lower() or '↑' in sc else 'neutrales'} "
                    f"Setup mit IV {iv_pct:.0f}% — Prämie ${prem:.2f} "
                    f"({dte}T, {otm:.1f}% OTM)."
                )
                thesis_in = st.text_area(
                    "🧠 These — warum dieser Trade? (1–2 Sätze)",
                    value=thesis_val,
                    height=80,
                    key=f"thesis_{ticker}_{idx}",
                )
                grade_opts = ["A+", "A", "A-", "B+", "B", "B-", "C"]
                grade_sel  = st.selectbox(
                    "📊 Signal-Grade",
                    grade_opts,
                    index=grade_opts.index(auto_grade) if auto_grade in grade_opts else 4,
                    key=f"grade_{ticker}_{idx}",
                )

            with col_r:
                st.markdown(
                    f"**Kurs:** ${kurs:.2f} &nbsp;|&nbsp; **IV:** {iv_pct:.0f}%  \n"
                    f"**Prämie:** ${prem:.2f} &nbsp;|&nbsp; **DTE:** {dte}T  \n"
                    f"**Delta:** {delta:.2f} &nbsp;|&nbsp; **OTM:** {otm:.1f}%  \n"
                    f"**CRV:** {crv:.0f} &nbsp;|&nbsp; **Konvergenz:** {conv:.0f}/100"
                )
                st.markdown("**Sichtbarkeit:**")
                vis_d  = st.checkbox("📢 Daily (79€)",    value=(dte > 2),  key=f"vd_{ticker}_{idx}")
                vis_mc = st.checkbox("🎓 Masterclass",    value=True,       key=f"vm_{ticker}_{idx}")
                vis_vp = st.checkbox("⭐ VIP",            value=True,       key=f"vv_{ticker}_{idx}")

            if already:
                st.caption("ℹ️ Dieser Ticker ist bereits in den offenen Trades — Status im Tab **Offene Trades** verwalten.")
            else:
                if st.button(
                    f"✅ Freigeben & als Modell-Trade speichern ({ticker})",
                    key=f"approve_{ticker}_{idx}",
                    type="primary",
                ):
                    draft = candidate_card_from_row(row, thesis=thesis_in)
                    # Grade + Visibility überschreiben
                    draft = replace(draft,
                        signal_grade=grade_sel,
                        visibility={"daily": vis_d, "masterclass": vis_mc, "vip": vis_vp},
                    )
                    # Entry-Snapshot einfrieren
                    entry = ModelEntry(
                        ts=datetime.now().isoformat(),
                        legs=[{
                            "ticker": ticker,
                            "strike": float(row.get("Strike", 0)),
                            "right":  "C" if "call" in str(row.get("Strategie","")).lower() else "P",
                            "expiry": expiry,
                            "side":   "short",
                        }],
                        entry_credit=prem,
                        underlying_at_entry=kurs,
                    )
                    draft = replace(draft,
                        entry=entry,
                        status="AKTIV",
                        status_history=[
                            *draft.status_history,
                            StatusEvent(
                                ts=datetime.now().isoformat(),
                                status="AKTIV",
                                note="Freigegeben — Entry-Snapshot eingefroren",
                            ),
                        ],
                    )
                    store.upsert(draft)
                    st.success(f"✅ **{ticker}** gespeichert · ID: `{draft.trade_id}`")
                    st.rerun()

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — OFFENE TRADES & STATUS
# ═══════════════════════════════════════════════════════════════════════════════
with tab_offen:
    if not open_cards:
        st.info("Keine offenen Trade Cards — Kandidaten im Tab **Neue Kandidaten** freigeben.")
    else:
        st.subheader(f"{len(open_cards)} offene Trades")

        STATUS_LIST = ["NEU", "AKTIV", "WATCH", "WARNING", "ROLL", "CLOSE", "CANCELLED", "EXPIRED", "REVIEWED"]
        STATUS_COLOR = {
            "NEU": "#3b82f6", "AKTIV": "#22c55e", "WATCH": "#f59e0b",
            "WARNING": "#ef4444", "ROLL": "#8b5cf6",
            "CLOSE": "#64748b", "CANCELLED": "#94a3b8",
        }

        for card in open_cards:
            color = STATUS_COLOR.get(card.status, "#888")
            with st.expander(
                f"**{card.ticker}** &nbsp;·&nbsp; "
                f"Grade {card.signal_grade} &nbsp;·&nbsp; "
                f"Status: {card.status} &nbsp;·&nbsp; "
                f"{card.risk_class} &nbsp;·&nbsp; {card.laufzeit}",
                expanded=False,
            ):
                cl, cr = st.columns([3, 2])

                with cl:
                    st.markdown(f"**ID:** `{card.trade_id}`")
                    st.markdown(f"**These:** {card.thesis}")
                    st.markdown(
                        f"**View:** {card.view}  |  **Quelle:** {card.source}  |  "
                        f"**Erstellt:** {card.created_at[:10]}"
                    )
                    if card.entry:
                        e = card.entry
                        st.markdown(
                            f"**Entry-Credit:** ${e.entry_credit:.2f}  |  "
                            f"**Underlying:** ${e.underlying_at_entry:.2f}  |  "
                            f"**Entry-Zeit:** {e.ts[:16].replace('T', ' ')}"
                        )
                    if card.circle_url:
                        st.markdown(f"**Circle URL:** [{card.circle_url}]({card.circle_url})")

                    # Signal-Komponenten
                    c = card.components
                    st.caption(
                        f"IV-Rank {c.iv_rank:.0f}/100 · IV/RV {c.iv_rv:.1f} · "
                        f"Trend {c.trend} · MACD {c.macd} · "
                        f"{c.earnings} · Liq. {c.liquiditaet}"
                    )

                    # Status-Historie
                    st.markdown("**Status-Verlauf:**")
                    for ev in reversed(card.status_history[-4:]):
                        st.caption(f"{ev.ts[:10]} → **{ev.status}**: {ev.note or '–'}")

                with cr:
                    st.markdown("**Status manuell setzen:**")
                    new_s = st.selectbox(
                        "Status",
                        STATUS_LIST,
                        index=STATUS_LIST.index(card.status) if card.status in STATUS_LIST else 1,
                        key=f"sel_status_{card.trade_id}",
                        label_visibility="collapsed",
                    )
                    note_in = st.text_input(
                        "Begründung",
                        placeholder="z.B. Take Profit 50% erreicht",
                        key=f"note_{card.trade_id}",
                    )
                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("💾 Speichern", key=f"save_{card.trade_id}", type="primary", use_container_width=True):
                            updated = apply_status_change(card, new_s, note_in)
                            store.upsert(updated)
                            st.success(f"✅ {card.ticker} → {new_s}")
                            st.rerun()
                    with b2:
                        if st.button("🗑️ Löschen", key=f"del_{card.trade_id}", use_container_width=True):
                            store.delete(card.trade_id)
                            st.rerun()

                    # Management-Übersicht
                    st.markdown("**Management:**")
                    m = card.management
                    st.caption(
                        f"TP {m.take_profit_pct*100:.0f}% · "
                        f"Roll-DTE {m.roll_dte} · Roll-Δ {m.roll_delta:.2f}"
                    )
                    st.caption(f"⚠️ {m.warning}")

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — FREIGABE & PUBLISH
# ═══════════════════════════════════════════════════════════════════════════════
with tab_publish:
    st.markdown(
        "**Reihenfolge:** Erst Circle posten → URL holen → WhatsApp mit Link senden."
    )
    st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

    aktive_cards = [c for c in open_cards if c.status == "AKTIV"]
    neue_heute   = [
        c for c in aktive_cards
        if len(c.status_history) <= 2
        or (c.status_history and c.status_history[-1].ts[:10] == datetime.now().strftime("%Y-%m-%d"))
    ]

    # ── CIRCLE ────────────────────────────────────────────────────────────────
    st.subheader("🌐 Circle Posts")
    if not aktive_cards:
        st.info("Keine aktiven Trades. Kandidaten im Tab **Neue Kandidaten** freigeben.")
    else:
        member_level = st.selectbox(
            "Vorschau für Eignungsstufe",
            ["einsteiger", "fortgeschritten", "profi"],
            index=2,
        )
        for card in aktive_cards:
            rendered = render_circle(card, member_level=member_level)
            with st.expander(f"**{card.ticker}** — {rendered['title']}", expanded=False):
                # HTML-Vorschau
                with st.container():
                    st.markdown("**HTML-Vorschau (gekürzt):**")
                    st.code(rendered["html"][:800] + "\n…", language="html")

                # Post-Buttons je Tier
                tier_cols = st.columns(3)
                for col, tier in zip(tier_cols, ["daily", "masterclass", "vip"]):
                    with col:
                        vis = card.visibility.get(tier, False)
                        tier_label = {
                            "daily": "Daily (79€)", "masterclass": "Masterclass", "vip": "VIP",
                        }[tier]
                        if not vis:
                            st.caption(f"🚫 {tier_label}: nicht sichtbar")
                            continue
                        if st.button(
                            f"🌐 {tier_label} posten",
                            key=f"ci_{card.trade_id}_{tier}",
                            disabled=not _ci_ok,
                            use_container_width=True,
                        ):
                            try:
                                pub = CirclePublisher(token=_ci_token, space_ids=_ci_spaces)
                                url = pub.create_post(tier, rendered["title"], rendered["html"])
                                updated = replace(card, circle_url=url)
                                store.upsert(updated)
                                st.success(f"✅ {tier_label}: {url}")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"❌ {exc}")

        if not _ci_ok:
            st.warning(
                "⚙️ Circle nicht konfiguriert. "
                "CIRCLE_API_TOKEN + CIRCLE_SPACE_* im Tab **Konfiguration** eintragen."
            )

    st.markdown('<div class="gold-line"></div>', unsafe_allow_html=True)

    # ── WHATSAPP ─────────────────────────────────────────────────────────────
    st.subheader("📱 WhatsApp-Post")
    wa_text = render_whatsapp(
        new_cards=neue_heute,
        status_changes=[],
        datum=datetime.now().strftime("%d.%m.%Y"),
    )
    wa_text_edit = st.text_area(
        "WhatsApp-Text (bearbeiten vor dem Senden)",
        value=wa_text,
        height=300,
    )
    wa_col1, wa_col2 = st.columns([1, 3])
    with wa_col1:
        if st.button(
            "📱 Jetzt senden",
            type="primary",
            disabled=not _wa_ok,
            use_container_width=True,
        ):
            try:
                pub    = WhatsAppPublisher(api_key=_wa_key, channel_id=_wa_channel, provider=_wa_provider)
                result = pub.publish(wa_text_edit)
                st.success(f"✅ WhatsApp gesendet  ·  {result}")
            except Exception as exc:
                st.error(f"❌ Fehler beim Senden: {exc}")
    with wa_col2:
        if not _wa_ok:
            st.warning(
                "⚙️ WhatsApp nicht konfiguriert. "
                "WHATSAPP_API_KEY + WHATSAPP_CHANNEL_ID im Tab **Konfiguration** eintragen."
            )

# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — KONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════
with tab_cfg:
    st.subheader("⚙️ API-Konfiguration")
    st.info(
        "Secrets sicher in **`.streamlit/secrets.toml`** (lokal) "
        "oder im **Streamlit Cloud Secrets-Manager** eintragen. Niemals im Code!",
        icon="🔐",
    )
    st.code("""\
# .streamlit/secrets.toml

# WhatsApp (Wassenger oder Whapi.Cloud)
WHATSAPP_API_KEY    = "DEIN_KEY"
WHATSAPP_CHANNEL_ID = "491234567890@newsletter"   # Wassenger: Telefon@newsletter | Whapi: Channel-ID
WHATSAPP_PROVIDER   = "wassenger"                 # "wassenger" | "whapi"

# Circle (Business / Enterprise Plan, Admin API v2)
CIRCLE_API_TOKEN        = "DEIN_TOKEN"
CIRCLE_SPACE_DAILY      = 12345   # Space-ID aus Circle Admin-Einstellungen
CIRCLE_SPACE_MASTERCLASS = 12346
CIRCLE_SPACE_VIP        = 12347
""", language="toml")

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**📱 WhatsApp**")
        if _wa_ok:
            st.success(f"✅ Konfiguriert ({_wa_provider})")
            st.caption(f"Channel: {_wa_channel[:25]}…")
        else:
            st.error("❌ Nicht konfiguriert")
            missing = []
            if not _wa_key:     missing.append("WHATSAPP_API_KEY")
            if not _wa_channel: missing.append("WHATSAPP_CHANNEL_ID")
            st.caption("Fehlt: " + ", ".join(missing))
    with c2:
        st.markdown("**🌐 Circle**")
        if _ci_ok:
            st.success("✅ Konfiguriert")
            active = [t for t, sid in _ci_spaces.items() if sid]
            st.caption(f"Spaces: {', '.join(active)}")
        else:
            st.error("❌ Nicht konfiguriert")
            missing = []
            if not _ci_token:              missing.append("CIRCLE_API_TOKEN")
            if not _ci_spaces.get("daily"): missing.append("CIRCLE_SPACE_DAILY")
            st.caption("Fehlt: " + ", ".join(missing))

    st.markdown("---")
    st.subheader("🗄️ Trade Store")
    all_cards = store.load_all()
    if all_cards:
        store_rows = [
            {
                "ID": c.trade_id,
                "Ticker": c.ticker,
                "Grade": c.signal_grade,
                "Status": c.status,
                "Klasse": c.risk_class,
                "Laufzeit": c.laufzeit,
                "Quelle": c.source,
                "Erstellt": c.created_at[:10],
                "Circle URL": c.circle_url[:40] + "…" if len(c.circle_url) > 40 else c.circle_url,
            }
            for c in all_cards
        ]
        st.dataframe(pd.DataFrame(store_rows), use_container_width=True, hide_index=True)
        if st.button("🗑️ Alle Trade Cards löschen", type="secondary"):
            import json
            with open(store.STORE_PATH, "w") as f:
                json.dump([], f)
            st.success("Trade Store geleert.")
            st.rerun()
    else:
        st.caption("Noch keine Trade Cards gespeichert.")
