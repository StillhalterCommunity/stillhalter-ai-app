"""
Stillhalter AI App Dashboard — Startseite
Login-Gate + Daten-Preload + Navigation
"""

import streamlit as st
import uuid
from datetime import datetime

st.set_page_config(
    page_title="Stillhalter AI — Börsen Briefing & Optionsflow",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from ui.theme import get_css, get_logo_html
st.markdown(f"<style>{get_css()}</style>", unsafe_allow_html=True)

from data.auth import check_password, log_event

# ══════════════════════════════════════════════════════════════════════════════
# LOGIN GATE — muss vor allem anderen kommen
# ══════════════════════════════════════════════════════════════════════════════

if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "auth_user" not in st.session_state:
    st.session_state.auth_user = ""
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]
if "app_theme" not in st.session_state:
    st.session_state.app_theme = "dark"

if not st.session_state.authenticated:
    # Zentriertes Login-Fenster
    _, center, _ = st.columns([1, 2, 1])
    with center:
        _lt = st.session_state.get("app_theme", "dark")
        _login_bg     = "#ffffff"    if _lt == "green" else "#111"
        _login_border = "#b7e4c7"    if _lt == "green" else "#1e1e1e"
        _login_top    = "#2d6a4f"    if _lt == "green" else "#d4a843"
        _login_title  = "#0d2318"    if _lt == "green" else "#f0f0f0"
        _login_sub    = "#94a3b8"    if _lt == "green" else "#555"
        _logo_v       = "black"      if _lt == "green" else "white"
        st.html(f"""
<div style='text-align:center;margin:60px 0 32px 0'>
    {get_logo_html(_logo_v, 56)}
</div>
<div style='background:{_login_bg};border:1px solid {_login_border};
            border-top:3px solid {_login_top};border-radius:14px;padding:32px 36px;
            box-shadow:0 8px 32px rgba(0,0,0,.12)'>
    <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.4rem;
                color:{_login_title};letter-spacing:0.05em;margin-bottom:4px'>
        STILLHALTER AI APP
    </div>
    <div style='font-family:RedRose,sans-serif;font-size:0.78rem;color:{_login_sub};
                letter-spacing:0.1em;text-transform:uppercase;margin-bottom:24px'>
        Beta-Zugang · Bitte Passwort eingeben
    </div>
</div>
""")
        pw = st.text_input("Passwort", type="password", placeholder="Dein persönliches Passwort",
                           label_visibility="collapsed")
        col_btn, col_hint = st.columns([2, 3])
        with col_btn:
            login_btn = st.button("→ Einloggen", type="primary", use_container_width=True)
        with col_hint:
            st.caption("Passwort erhalten? Wende dich an die Stillhalter Community.")

        if login_btn or pw:
            username = check_password(pw)
            if username:
                st.session_state.authenticated = True
                st.session_state.auth_user = username
                log_event(username, "login", st.session_state.session_id)
                st.rerun()
            elif pw:
                st.error("Ungültiges Passwort — bitte prüfen oder Stillhalter Community kontaktieren.")
    st.stop()

# ── Ab hier: nur für eingeloggte Nutzer ──────────────────────────────────────
from ui.sidebar import render_sidebar

# _is_green muss VOR dem Page-Link-CSS bekannt sein
_is_green = st.session_state.get("app_theme", "dark") == "green"

# ── Kompaktes Spacing: Card → Link-Footer nahtlos ────────────────────────────
_pl_link_bg     = "#f6fdfb" if _is_green else "#0c0c0c"
_pl_link_border = "#b7e4c7" if _is_green else "#1e1e1e"
_pl_link_color  = "#475569" if _is_green else "#555555"
_pl_link_hover  = "#2d6a4f" if _is_green else "#d4a843"
_pl_link_hbg    = "#eef8f5" if _is_green else "#111111"
st.markdown(f"""
<style>
[data-testid="stMain"] [data-testid="stElementContainer"]:has([data-testid="stPageLink"]) {{
    margin-top: -10px !important;
    margin-bottom: 8px !important;
}}
[data-testid="stMain"] [data-testid="stPageLink"] > a {{
    border-radius: 0 0 14px 14px !important;
    background: {_pl_link_bg} !important;
    border: 1px solid {_pl_link_border} !important;
    border-top: none !important;
    padding: 9px 20px !important;
    font-size: 0.82rem !important;
    color: {_pl_link_color} !important;
    width: 100% !important;
    display: block !important;
    text-decoration: none !important;
    transition: color 0.15s, background 0.15s !important;
}}
[data-testid="stMain"] [data-testid="stPageLink"] > a:hover {{
    color: {_pl_link_hover} !important;
    background: {_pl_link_hbg} !important;
    text-decoration: none !important;
}}
</style>
""", unsafe_allow_html=True)

from data.fetcher import (
    market_status_text, is_market_open,
    fetch_extended_hours_price, get_extended_hours_session,
    fetch_price_history, fetch_stock_info,
)
import data.background_scan as bg_scan

render_sidebar()

# ── Theme-Farben für inline Styles ──────────────────────────────────────────
_th           = st.session_state.get("app_theme", "dark")
_is_green     = _th == "green"
_title_color  = "#0d2318" if _is_green else "#f0f0f0"
_sub_color    = "#475569" if _is_green else "#666666"
_user_color   = "#2d6a4f" if _is_green else "#d4a843"
_badge_bg     = "#eef8f5" if _is_green else "#1a1a2e"
_badge_border = "#b7e4c7" if _is_green else "#333333"
_preload_acc  = "#2d6a4f" if _is_green else "#d4a843"
_preload_pct  = "#0d2318" if _is_green else "#f0f0f0"
_preload_sub  = "#475569" if _is_green else "#555555"
_logo_variant = "black"   if _is_green else "white"

# ── Header ────────────────────────────────────────────────────────────────────
col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.html(get_logo_html(_logo_variant, 48))
with col_title:
    market_open  = is_market_open()
    ext_session  = get_extended_hours_session()
    mkt_class    = "market-open" if market_open else "market-closed"

    ext_badge = ""
    if ext_session:
        spy_ext = fetch_extended_hours_price("SPY")
        if spy_ext:
            sign      = "+" if spy_ext["change_pct"] >= 0 else ""
            col_chg   = "#22c55e" if spy_ext["change_pct"] >= 0 else "#ef4444"
            lbl_color = spy_ext["label_color"]
            lbl_text  = spy_ext["label"]
            spy_price = spy_ext["price"]
            spy_chg   = spy_ext["change_pct"]
            spy_time  = spy_ext["time_str"]
            ext_badge = (
                f" &nbsp;·&nbsp; <span style='background:{_badge_bg};border:1px solid {_badge_border};"
                f"border-radius:4px;padding:1px 8px;font-size:0.75rem;"
                f"color:{lbl_color}'>{lbl_text}</span>"
                f" &nbsp;<span style='color:{col_chg};font-size:0.78rem'>"
                f"SPY {spy_price:.2f} ({sign}{spy_chg:.2f}%) · {spy_time}</span>"
            )

    user_name = st.session_state.get("auth_user", "")
    st.html(
        f"<div style='padding-top:6px'>"
        f"<div style='font-family:RedRose,sans-serif;font-weight:700;font-size:2rem;"
        f"color:{_title_color};letter-spacing:0.04em'>Stillhalter AI — Börsen Briefing &amp; Optionsflow</div>"
        f"<div style='font-family:RedRose,sans-serif;font-weight:300;font-size:0.8rem;"
        f"color:{_sub_color};text-transform:uppercase;letter-spacing:0.15em;margin-top:2px'>"
        f"Options Trading Dashboard &nbsp;·&nbsp; <span class='{mkt_class}'>{market_status_text()}</span>"
        f"{ext_badge}"
        f" &nbsp;·&nbsp; <span style='color:{_user_color}'>👤 {user_name}</span>"
        f"</div></div>"
    )

st.html('<div class="gold-line"></div>')

# ── System-Steuerung ───────────────────────────────────────────────────────────
with st.expander("⚙️ System", expanded=False):

    # ── Theme-Umschalter ──────────────────────────────────────────────────────
    current_theme = st.session_state.get("app_theme", "dark")
    _lbl_color = "#475569" if _is_green else "#888888"
    th_label = "🌙 Dark · Schwarz/Gold" if current_theme == "dark" else "🌿 Hell · Grün/Weiß"
    st.markdown(
        f"<div style='font-size:0.75rem;color:{_lbl_color};letter-spacing:0.08em;"
        f"text-transform:uppercase;margin-bottom:6px'>Aktives Theme: <b>{th_label}</b></div>",
        unsafe_allow_html=True,
    )
    t1, t2, _tpad = st.columns([2, 2, 8])
    with t1:
        dark_active = current_theme == "dark"
        if st.button(
            "🌙 Dark" + (" ✓" if dark_active else ""),
            use_container_width=True,
            type="primary" if dark_active else "secondary",
            help="Schwarz + Gold — klassisches Stillhalter-Design",
        ):
            st.session_state.app_theme = "dark"
            st.rerun()
    with t2:
        green_active = current_theme == "green"
        if st.button(
            "🌿 Grün" + (" ✓" if green_active else ""),
            use_container_width=True,
            type="primary" if green_active else "secondary",
            help="Weiß + Grün — Landingpage-Palette",
        ):
            st.session_state.app_theme = "green"
            st.rerun()

    st.divider()

    # ── Wartungsmodus (nur Admin) ──────────────────────────────────────────────
    from data.maintenance import is_maintenance, is_admin, enable as maint_on, disable as maint_off
    if is_admin(st.session_state.get("auth_user", "")):
        _maint_active = is_maintenance()
        _maint_color = "#ef4444" if _maint_active else "#22c55e"
        _maint_label = "AKTIV — alle anderen Nutzer sehen Wartungsseite" if _maint_active else "INAKTIV"
        st.markdown(
            f"<div style='font-size:0.75rem;color:#888;margin-bottom:6px'>"
            f"🔧 Wartungsmodus: <b style='color:{_maint_color}'>{_maint_label}</b>"
            f"</div>",
            unsafe_allow_html=True,
        )
        _m1, _m2, _mpad = st.columns([2, 2, 8])
        with _m1:
            if not _maint_active:
                if st.button("🔧 Wartungsmodus AN", use_container_width=True,
                             help="Alle anderen Nutzer sehen Wartungsseite"):
                    maint_on()
                    st.rerun()
        with _m2:
            if _maint_active:
                if st.button("✅ Wartungsmodus AUS", use_container_width=True, type="primary",
                             help="App wieder für alle freigeben"):
                    maint_off()
                    st.rerun()

        # ── Tagesdaten-Prefetch (nur Admin) ────────────────────────────────────
        import data.prefetch as _pf
        _pf_state = _pf.get_state()
        _pf_meta  = _pf.last_prefetch()
        if _pf_state["running"]:
            _pf_pct = int(_pf_state["progress"] * 100)
            st.markdown(
                f"<div style='font-size:0.75rem;color:#888;margin:8px 0 6px'>"
                f"📦 Tagesdaten-Prefetch läuft: <b style='color:#d4a843'>{_pf_pct}%</b> "
                f"· {_pf_state['done']}/{_pf_state['total']} Ticker</div>",
                unsafe_allow_html=True,
            )
            st.progress(_pf_state["progress"])
        else:
            if _pf_meta:
                _pfc = _pf_meta.get("counts", {})
                st.markdown(
                    f"<div style='font-size:0.75rem;color:#888;margin:8px 0 6px'>"
                    f"📦 Letzter Prefetch: <b style='color:#22c55e'>{_pf_meta.get('finished_at','?')}</b> "
                    f"· Value-Daten {_pfc.get('value',0)}/{_pf_meta.get('total',0)} geladen</div>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    "<div style='font-size:0.75rem;color:#888;margin:8px 0 6px'>"
                    "📦 Noch kein Prefetch gelaufen</div>",
                    unsafe_allow_html=True,
                )
            _pf1, _pfpad = st.columns([2, 10])
            with _pf1:
                if st.button("📦 Tagesdaten laden", use_container_width=True,
                             help="Lädt Kurse, Fundamentals & Value-Daten für alle Ticker in den Cache"):
                    # Überlast-Schutz: nicht starten während Scan/Preloader laufen
                    if bg_scan.is_running() or _preloader.is_running():
                        st.warning("⏳ Es läuft gerade ein Scan/Preload. Bitte kurz warten "
                                   "und dann erneut starten — sonst überlastet die Instanz.")
                    else:
                        _pf.start_prefetch()
                        st.rerun()

        # ── Speicher-Diagnose: aktiver Cache-Pfad (zeigt ob Volume greift) ─────
        try:
            from data import _persistent_cache as _pc
            import os as _os
            _cdir = _pc._CACHE_DIR
            _persistent = _cdir.startswith("/data")
            _n_files = len([f for f in _os.listdir(_cdir) if f.endswith(".pkl")]) if _os.path.isdir(_cdir) else 0
            _diag_color = "#22c55e" if _persistent else "#f59e0b"
            _diag_label = "persistent (Volume aktiv)" if _persistent else "flüchtig (kein Volume!)"
            st.markdown(
                f"<div style='font-size:0.72rem;color:#666;margin:4px 0'>"
                f"💾 Cache: <span style='color:{_diag_color}'>{_diag_label}</span> · "
                f"<code>{_cdir}</code> · {_n_files} Dateien</div>",
                unsafe_allow_html=True,
            )
        except Exception:
            pass
        st.divider()

    # ── App-Steuerung ─────────────────────────────────────────────────────────
    sc1, sc2, sc3, sc4, _ = st.columns([2, 2, 2, 2, 4])
    with sc1:
        if st.button("🔄 App neu starten", use_container_width=True,
                     help="Startet die App komplett neu — behebt Hänger und Speicherfehler"):
            user = st.session_state.get("auth_user", "")
            sid  = st.session_state.get("session_id", "")
            log_event(user, "logout", sid)
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.cache_data.clear()
            st.rerun()
    with sc2:
        if st.button("🗑️ Cache leeren", use_container_width=True,
                     help="Löscht alle gecachten Börsendaten — erzwingt frischen Datenabruf"):
            st.cache_data.clear()
            st.success("✅ Cache geleert — Daten werden neu geladen")
    with sc3:
        if st.button("🔃 Seite aktualisieren", use_container_width=True,
                     help="Aktualisiert die aktuelle Seite"):
            st.rerun()
    with sc4:
        if st.button("🚪 Ausloggen", use_container_width=True,
                     help="Sitzung beenden"):
            user = st.session_state.get("auth_user", "")
            sid  = st.session_state.get("session_id", "")
            log_event(user, "logout", sid)
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()

st.html("<div style='margin-top:8px'></div>")

# ══════════════════════════════════════════════════════════════════════════════
# DATEN-PRELOAD — läuft parallel im Hintergrund, App bleibt sofort nutzbar
# Auto-Update alle 15 Minuten
# ══════════════════════════════════════════════════════════════════════════════

import data.preloader as _preloader
from data.watchlist import ALL_TICKERS

_PRELOAD_TICKERS = ["SPY", "QQQ"] + [t for t in ALL_TICKERS if t not in ("SPY", "QQQ")]

# Preload starten falls nötig (erstes Mal oder älter als 15 Min.)
if _preloader.needs_update():
    _preloader.start_preload(_PRELOAD_TICKERS)

# Status anzeigen
_pl = _preloader.get_state()

# Täglicher Voll-Prefetch (Fundamentals + Value-Daten) — einmal pro Tag.
# SERIALISIERT: startet nur wenn weder Preloader NOCH Hintergrund-Scan läuft,
# damit die Instanz nicht von 24 Threads gleichzeitig überlastet wird (502).
import data.prefetch as _prefetch
if (not _pl["running"]
        and not bg_scan.is_running()
        and _prefetch.needs_prefetch_today()
        and not _prefetch.is_running()):
    _prefetch.start_prefetch(_PRELOAD_TICKERS)
if _pl["running"]:
    pct_int  = int(_pl["progress"] * 100)
    done     = _pl["done"]
    total    = _pl["total"]
    _pl_hdr  = st.empty()
    _pl_bar  = st.progress(_pl["progress"])
    _pl_hdr.html(f"""
<div style='font-family:RedRose,sans-serif;font-weight:700;font-size:0.95rem;
            color:{_preload_acc};letter-spacing:0.08em;margin-bottom:4px'>
    ⚡ DATENIMPORT &nbsp;
    <span style='font-size:1.4rem;color:{_preload_pct}'>{pct_int}%</span>
    <span style='font-size:0.75rem;color:{_preload_sub};font-weight:300;margin-left:8px'>
        — {done}/{total} Ticker · Du kannst die App bereits nutzen
    </span>
</div>
""")
    import time as _t; _t.sleep(2); st.rerun()
elif _pl["last_update"]:
    _ago = int((datetime.now() - _pl["last_update"]).total_seconds() / 60)
    _next = max(0, 15 - _ago)
    st.html(f"""
<div style='font-family:RedRose,sans-serif;font-size:0.75rem;color:#333;margin-bottom:4px'>
    ✅ Kerndaten aktuell · zuletzt geladen vor {_ago} Min.
    · nächstes Update in ~{_next} Min.
</div>
""")

st.html("<div style='margin-bottom:8px'></div>")

# ══════════════════════════════════════════════════════════════════════════════
# AUTO-SCAN beim App-Start — startet einmal pro Session wenn Cache veraltet
# ══════════════════════════════════════════════════════════════════════════════
import pickle as _pickle, os as _os

_AUTO_SCAN_INTERVAL_H = 2          # Scan starten wenn Cache älter als 2 Stunden
_AUTO_CACHE_PATH = _os.path.join(_os.path.dirname(__file__), "data", "last_scan_cache.pkl")

def _cache_age_hours() -> float:
    """Wie alt ist der letzte Scan-Cache in Stunden? 9999 wenn nicht vorhanden."""
    try:
        with open(_AUTO_CACHE_PATH, "rb") as _f:
            _d = _pickle.load(_f)
        return (datetime.now() - _d["timestamp"]).total_seconds() / 3600
    except Exception:
        return 9999.0

_bg = bg_scan.get_state()

# Auto-Scan SERIALISIERT: startet nur wenn weder Preloader noch Prefetch laufen,
# damit die Instanz nicht überlastet wird (502). Bei Besetzung: Flag NICHT setzen
# → nächster Rerun versucht es erneut, sobald die anderen Jobs fertig sind.
if not st.session_state.get("_auto_scan_triggered"):
    _age_h = _cache_age_hours()
    _others_busy = _preloader.is_running() or _prefetch.is_running()
    if _age_h <= _AUTO_SCAN_INTERVAL_H:
        # Cache frisch genug → kein Auto-Scan nötig, nicht erneut versuchen
        st.session_state._auto_scan_triggered = True
    elif not _bg["running"] and not _others_busy:
        st.session_state._auto_scan_triggered = True
        # Alle Watchlist-Ticker, Standardparameter für Cash Covered Put
        from data.watchlist import ALL_TICKERS as _AT
        _auto_tickers = ["SPY", "QQQ"] + [t for t in _AT if t not in ("SPY", "QQQ")]
        _started = bg_scan.start_scan(
            tickers        = _auto_tickers,
            strategy       = "Cash Covered Put",
            delta_min      = -0.35,
            delta_max      = -0.05,
            dte_min        = 14,
            dte_max        = 60,
            iv_min         = 0.15,
            premium_min    = 0.05,
            min_oi         = 5,
            otm_min        = 3.0,
            otm_max        = 50.0,
            max_spread_pct = 40.0,
            require_valid_market = False,   # Off-Hours: Last Price verwenden
            exclude_earnings     = True,
        )
        if _started:
            _bg = bg_scan.get_state()   # State nach Start aktualisieren

# ══════════════════════════════════════════════════════════════════════════════
# HINTERGRUND-SCAN STATUS — zeigt laufenden Scan auf der Startseite
# ══════════════════════════════════════════════════════════════════════════════
_bg = bg_scan.get_state()
if _bg["running"]:
    pct  = _bg["progress"]
    done = _bg["done"]
    tot  = _bg["total"]
    cur  = _bg["current"]
    _scan_acc = "#2d6a4f" if _is_green else "#d4a843"
    _scan_bg  = "rgba(45,106,79,0.08)" if _is_green else "rgba(212,168,67,0.08)"
    _scan_bd  = "rgba(45,106,79,0.3)"  if _is_green else "rgba(212,168,67,0.3)"
    _scan_txt = "#1b4332" if _is_green else "#f0f0f0"
    _scan_sub = "#475569" if _is_green else "#888888"
    st.html(f"""
<div style='background:{_scan_bg};border:1px solid {_scan_bd};
            border-radius:10px;padding:12px 18px;margin-bottom:4px'>
    <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:0.85rem;
                color:{_scan_acc};margin-bottom:6px'>
        🔍 WATCHLIST-SCAN LÄUFT IM HINTERGRUND — automatisch gestartet
    </div>
    <div style='font-family:RedRose,sans-serif;font-size:0.8rem;color:{_scan_sub}'>
        Strategie: {_bg['strategy']} &nbsp;·&nbsp;
        Fortschritt: {done}/{tot} Aktien ({pct*100:.0f}%) &nbsp;·&nbsp;
        Aktuell: <strong style='color:{_scan_txt}'>{cur}</strong>
        &nbsp;·&nbsp; Seite wechseln ist jederzeit möglich ✓
    </div>
</div>
""")
    st.progress(pct)
    # Auto-Refresh alle 3 Sekunden solange Scan läuft
    import time as _time
    _time.sleep(3)
    st.rerun()
elif _bg["finished_at"] and _bg["results"] is not None:
    res = _bg["results"]
    dur = (_bg["finished_at"] - _bg["started_at"]).total_seconds() if _bg["started_at"] else 0
    n   = len(res)
    nt  = res["Ticker"].nunique() if "Ticker" in res.columns else 0
    st.success(
        f"✅ Letzter Scan abgeschlossen: **{n} Optionen** aus **{nt} Aktien** "
        f"gefunden · Dauer: {dur:.0f}s · "
        f"Ergebnisse in **Watchlist Scanner** & **Top 9** verfügbar"
    )

# ── Karten-Helper ─────────────────────────────────────────────────────────────
def _card(num: str, title: str, desc: str, color: str, page: str, icon: str, label: str):
    st.html(f"""
    <div style='background:#111;border:1px solid #1e1e1e;border-top:3px solid {color};
                border-bottom:none;border-radius:14px 14px 0 0;padding:20px 22px 14px'>
        <div style='font-family:RedRose,sans-serif;font-weight:700;font-size:1.1rem;
                    color:{color};letter-spacing:0.05em;margin-bottom:6px'>
            {icon} {num} · {title}
        </div>
        <div style='font-family:RedRose,sans-serif;font-size:0.83rem;color:#666;line-height:1.65'>
            {desc}
        </div>
    </div>
""")
    st.page_link(page, label=f"→ {label}", icon=icon)


# ── Zeile 1 ───────────────────────────────────────────────────────────────────
c1, c2 = st.columns(2, gap="large")
with c1:
    _card("1", "MARKTANALYSE / NEWS",
          "Makro-Überblick · Fear &amp; Greed · Sektoren-Heatmap · Top-News &amp; Earnings",
          "#38bdf8", "pages/01_Marktanalyse_News.py", "📰", "Marktanalyse / News")
with c2:
    _card("2", "FUNDAMENTALANALYSE",
          "PEG · KGV · Wachstum · ROE — Value Score A/B/C für die gesamte Watchlist",
          "#22c55e", "pages/02_Fundamentalanalyse.py", "💎", "Fundamentalanalyse")

# ── Zeile 2 ───────────────────────────────────────────────────────────────────
c3, c4 = st.columns(2, gap="large")
with c3:
    _card("3", "AKTIENANALYSE",
          "Tiefenanalyse: Optionen · Greeks · CRV · Chart · MACD · Stochastik · Fundamentals",
          "#9ca3af", "pages/03_Aktienanalyse.py", "📊", "Aktienanalyse")
with c4:
    _card("4", "WATCHLIST SCANNER",
          "225 Aktien · CRV-Score · Cash Covered Puts · Covered Calls · Bubble-Chart · CSV",
          "#d4a843", "pages/04_Watchlist_Scanner.py", "🔍", "Watchlist Scanner")

st.html('<div class="gold-line" style="margin:18px 0"></div>')

# ── Zeile 3 ───────────────────────────────────────────────────────────────────
c5, c6 = st.columns(2, gap="large")
with c5:
    _card("5", "TOP 9 TRADING IDEEN",
          "Top 3 pro IV-Klasse (Low/Mid/High) · TA-Begründung · Absicherungs-Ampel",
          "#d4a843", "pages/05_Top9_Trading_Ideen.py", "🏆", "Top 9 Trading Ideen")
with c6:
    _card("6", "ZUKUNFTSPROGNOSE",
          "Welche Aktien nähern sich einem Setup? · Indikator-Proximity · Konvergenz-Score",
          "#60a5fa", "pages/06_Zukunftsprognose.py", "🔭", "Zukunftsprognose")

# ── Zeile 4 ───────────────────────────────────────────────────────────────────
c7, c8 = st.columns(2, gap="large")
with c7:
    _card("7", "TRADE MANAGEMENT",
          "Offene Positionen bewerten · P&amp;L · Empfehlungen · IBKR Live-Import",
          "#a78bfa", "pages/07_Trade_Management.py", "⚖️", "Trade Management")
with c8:
    _card("8", "TREND SIGNALE",
          "Stillhalter Trend Model · Multi-Timeframe Confluence · Call/Put-Empfehlung mit Strike &amp; Prämie",
          "#f59e0b", "pages/08_Trend_Signale.py", "🎯", "Trend Signale")

st.html('<div class="gold-line" style="margin:18px 0"></div>')

# ── Zeile 5 ───────────────────────────────────────────────────────────────────
c9, c10 = st.columns(2, gap="large")
with c9:
    _card("9", "INVESTOREN CHECK",
          "Buffett · Lynch · Graham — Bewertung nach legendären Investoren-Kriterien",
          "#fb923c", "pages/09_Investoren_Check.py", "🦁", "Investoren Check")
with c10:
    _card("10", "OPTION OLLI CHAT",
          "KI-Assistent für Optionsstrategien · Persönliches Coaching · Wissens-Upload",
          "#e879f9", "pages/10_Option_Olli_Chat.py", "🤖", "Option Olli Chat")

# ── Zeile 6 ───────────────────────────────────────────────────────────────────
c11, c12 = st.columns(2, gap="large")
with c11:
    _card("11", "PROZESS",
          "Handelsregeln · Checklisten · Schritt-für-Schritt Stillhalter-Prozess",
          "#6b7280", "pages/11_Prozess.py", "📋", "Prozess")
with c12:
    _card("12", "IBKR INTEGRATION",
          "Interactive Brokers Live-Verbindung · Portfolio-Import · Automatische Positionserkennung",
          "#34d399", "pages/12_IBKR_Integration.py", "🔗", "IBKR Integration")

# ── Zeile 7 ───────────────────────────────────────────────────────────────────
c13, c14 = st.columns(2, gap="large")
with c13:
    _card("13", "DATENSCHUTZ & RECHTLICHES",
          "Datenschutzerklärung · Haftungsausschluss · Impressum",
          "#475569", "pages/13_Rechtliches.py", "⚖️", "Datenschutz & Rechtliches")
with c14:
    _card("14", "ORDER-PLANUNG",
          "Orders direkt in IBKR TWS platzieren · Held-Order Workflow · Freigabe in TWS",
          "#22c55e", "pages/14_Order_Planung.py", "📋", "Order-Planung")

# ── Zeile 8 ───────────────────────────────────────────────────────────────────
c15, c16 = st.columns(2, gap="large")
with c15:
    _card("15", "DATENQUELLEN",
          "Yahoo Finance vs. Massive.com · API-Konfiguration · Verbindungstest",
          "#3b82f6", "pages/15_Datenquellen.py", "📡", "Datenquellen")
with c16:
    _card("16", "SENTIMENT ANALYSE",
          "Chris Camillo Social Arbitrage · Reddit · Google Trends · X/Twitter · YouTube · Bullish/Bearish Signale",
          "#8b5cf6", "pages/16_Sentiment_Analyse.py", "🧭", "Sentiment Analyse")

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("---")
st.html("""
<div style='text-align:center;font-family:RedRose,sans-serif;font-size:0.78rem;color:#333;
            letter-spacing:0.08em'>
    STILLHALTER AI APP · Daten: Yahoo Finance ·
    Stillhalter MACD Pro · Stillhalter Dual Stochastik · Stillhalter Trend Model®
    &nbsp;·&nbsp;
    <a href='pages/13_Rechtliches.py' style='color:#444;text-decoration:none'>
        Datenschutz &amp; Impressum
    </a>
</div>
""")
