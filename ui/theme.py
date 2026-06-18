"""
Stillhalter AI App — Dual Theme System.

Themes:
  "dark"  → Schwarz + Gold (ursprüngliches Design)
  "green" → Weiß + Grün (Landingpage-Palette)

get_css() liest automatisch st.session_state.app_theme.
Kein Page-File muss geändert werden.
"""

import os
try:
    import streamlit as st
    _HAS_ST = True
except Exception:
    _HAS_ST = False

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


# ── Grün-Palette (identisch zur Landing Page) ─────────────────────────────────
_G = {
    "900": "#0d2318", "800": "#1b4332", "700": "#2d6a4f",
    "600": "#40916c", "500": "#52b788", "400": "#74c69d",
    "300": "#95d5b2", "200": "#b7e4c7", "100": "#DAEFEB",
    "50":  "#eef8f5", "25":  "#f6fdfb",
}
_INK  = "#0a1628"
_INK2 = "#1e293b"
_INK3 = "#475569"
_INK4 = "#94a3b8"


def _active_theme() -> str:
    if _HAS_ST:
        try:
            return st.session_state.get("app_theme", "dark")
        except Exception:
            pass
    return "dark"


def _load_b64(filename: str) -> str:
    path = os.path.join(STATIC_DIR, filename)
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return ""


def _font_face() -> str:
    rr_regular = _load_b64("RedRose-Regular.b64")
    rr_bold    = _load_b64("RedRose-Bold.b64")
    rr_light   = _load_b64("RedRose-Light.b64")
    rr_semi    = _load_b64("RedRose-SemiBold.b64")
    if not rr_regular:
        return ""
    return f"""
    @font-face {{
        font-family: 'RedRose';
        src: url('data:font/truetype;base64,{rr_light}') format('truetype');
        font-weight: 300;
    }}
    @font-face {{
        font-family: 'RedRose';
        src: url('data:font/truetype;base64,{rr_regular}') format('truetype');
        font-weight: 400;
    }}
    @font-face {{
        font-family: 'RedRose';
        src: url('data:font/truetype;base64,{rr_semi}') format('truetype');
        font-weight: 600;
    }}
    @font-face {{
        font-family: 'RedRose';
        src: url('data:font/truetype;base64,{rr_bold}') format('truetype');
        font-weight: 700;
    }}
    """


# ══════════════════════════════════════════════════════════════════════════════
# DARK THEME (Schwarz + Gold)
# ══════════════════════════════════════════════════════════════════════════════

def _css_dark() -> str:
    return f"""
    {_font_face()}

    [data-testid="stSidebarNav"] {{ display: none !important; }}

    [data-testid="stSidebar"] [data-testid="stPageLink"] > a {{
        border-radius: 6px !important; background: transparent !important;
        border: none !important; padding: 4px 8px !important;
        font-size: 0.82rem !important; color: #888 !important;
        width: 100% !important; display: block !important;
    }}
    [data-testid="stSidebar"] [data-testid="stPageLink"] > a:hover {{
        color: #d4a843 !important; background: #1a1a1a !important;
    }}
    [data-testid="stSidebar"] [data-testid="stPageLink"] > a[aria-current="page"] {{
        color: #d4a843 !important; background: #1a1a1a !important; font-weight: 600 !important;
    }}

    html, body, .stApp {{
        background-color: #0c0c0c !important;
        color: #e8e8e8;
        font-family: 'RedRose', 'Inter', sans-serif;
    }}
    .main .block-container {{ padding-top: 0.75rem; padding-bottom: 1rem; max-width: 1600px; }}

    h1, h2, h3, h4, h5 {{
        font-family: 'RedRose', sans-serif !important;
        color: #f0f0f0 !important; letter-spacing: 0.03em;
    }}
    h1 {{ font-weight: 700; font-size: 1.9rem !important; }}
    h2 {{ font-weight: 600; font-size: 1.4rem !important; }}
    h3 {{ font-weight: 600; font-size: 1.15rem !important; }}
    h4 {{ font-weight: 400; font-size: 1rem !important; }}
    p, label, span, div {{ font-family: 'RedRose', 'Inter', sans-serif; }}

    section[data-testid="stSidebar"] {{
        background-color: #111111 !important; border-right: 1px solid #1e1e1e;
    }}
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span {{
        font-family: 'RedRose', sans-serif; font-size: 0.85rem; color: #aaa;
    }}
    section[data-testid="stSidebar"] [data-testid="stMarkdown"] h2 {{
        font-size: 1rem !important; color: #d4a843 !important;
        text-transform: uppercase; letter-spacing: 0.1em;
    }}

    [data-testid="metric-container"] {{
        background: #141414 !important; border: 1px solid #222 !important;
        border-radius: 10px !important; padding: 12px 16px !important;
    }}
    [data-testid="metric-container"] [data-testid="stMetricLabel"] {{
        font-size: 0.75rem !important; color: #888 !important;
        text-transform: uppercase; letter-spacing: 0.08em;
    }}
    [data-testid="metric-container"] [data-testid="stMetricValue"] {{
        font-size: 1.4rem !important; font-weight: 700 !important; color: #f0f0f0 !important;
    }}

    .stTabs [data-baseweb="tab-list"] {{
        background: transparent; border-bottom: 1px solid #222; gap: 4px;
    }}
    .stTabs [data-baseweb="tab"] {{
        font-family: 'RedRose', sans-serif; font-weight: 600; font-size: 0.85rem;
        color: #666 !important; background: transparent;
        border-radius: 6px 6px 0 0; padding: 8px 16px;
        text-transform: uppercase; letter-spacing: 0.06em;
    }}
    .stTabs [aria-selected="true"] {{
        color: #d4a843 !important; border-bottom: 2px solid #d4a843 !important;
    }}

    .stButton > button {{
        font-family: 'RedRose', sans-serif; font-weight: 600; font-size: 0.85rem;
        letter-spacing: 0.05em; border-radius: 8px; border: 1px solid #2a2a2a;
        background: #1a1a1a; color: #e0e0e0; padding: 0.5rem 1.2rem; transition: all 0.2s;
    }}
    .stButton > button:hover {{ border-color: #d4a843; color: #d4a843; background: #1a1a1a; }}
    [data-testid="baseButton-primary"] > button,
    .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, #d4a843, #b8912f) !important;
        color: #0c0c0c !important; border: none !important; font-weight: 700 !important;
    }}

    .stSelectbox [data-baseweb="select"] > div,
    .stNumberInput input, .stTextInput input, .stTextArea textarea {{
        background: #141414 !important; border: 1px solid #252525 !important;
        border-radius: 8px !important; color: #e0e0e0 !important;
        font-family: 'RedRose', sans-serif;
    }}
    .stSelectbox [data-baseweb="select"] > div:focus-within {{ border-color: #d4a843 !important; }}

    [data-testid="stDataFrame"] {{ border: 1px solid #1e1e1e; border-radius: 10px; overflow: hidden; }}
    [data-testid="stDataFrame"] th {{
        background: #161616 !important; color: #d4a843 !important;
        font-family: 'RedRose', sans-serif; font-weight: 600; font-size: 0.8rem;
        text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid #252525;
    }}
    [data-testid="stDataFrame"] td {{
        background: #0e0e0e !important; color: #d8d8d8 !important;
        font-size: 0.85rem; border-bottom: 1px solid #161616;
    }}
    [data-testid="stDataFrame"] tr:hover td {{ background: #161616 !important; }}

    [data-testid="stAlert"] {{ border-radius: 8px !important; font-family: 'RedRose', sans-serif; font-size: 0.88rem; }}
    .stAlert[data-baseweb="notification"] {{ background: #141414 !important; }}

    [data-testid="stExpander"] {{
        background: #111 !important; border: 1px solid #1e1e1e !important; border-radius: 10px !important;
    }}
    [data-testid="stExpander"] summary {{ font-family: 'RedRose', sans-serif; font-weight: 600; color: #aaa; }}

    .stProgress > div > div > div {{
        background: linear-gradient(90deg, #d4a843, #f0c060) !important; border-radius: 4px;
    }}

    hr {{ border-color: #1e1e1e !important; margin: 1rem 0; }}

    .sc-header {{
        display: flex; align-items: center; gap: 16px; padding: 12px 0 8px 0;
        border-bottom: 1px solid #1e1e1e; margin-bottom: 16px;
    }}
    .sc-page-title {{ font-family: 'RedRose', sans-serif; font-weight: 700; font-size: 1.6rem; color: #f0f0f0; letter-spacing: 0.04em; flex: 1; }}
    .sc-page-subtitle {{ font-family: 'RedRose', sans-serif; font-weight: 300; font-size: 0.8rem; color: #666; text-transform: uppercase; letter-spacing: 0.1em; }}

    .market-open  {{ color: #22c55e; font-weight: 600; }}
    .market-closed {{ color: #f59e0b; font-weight: 600; }}

    .tag {{ display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.05em; margin-right: 4px; }}
    .tag-gold  {{ background: #1f1a0a; color: #d4a843; border: 1px solid #3a2f0a; }}
    .tag-green {{ background: #0a1f0a; color: #22c55e; border: 1px solid #1a3a1a; }}
    .tag-red   {{ background: #1f0a0a; color: #ef4444; border: 1px solid #3a1a1a; }}
    .tag-gray  {{ background: #1a1a1a; color: #888;    border: 1px solid #2a2a2a; }}
    .tag-blue  {{ background: #0a0f1f; color: #60a5fa; border: 1px solid #1a2a3a; }}

    .signal-card {{ background: #111; border: 1px solid #1e1e1e; border-radius: 10px; padding: 12px 16px; margin-bottom: 6px; }}
    .signal-card-bullish {{ border-left: 3px solid #22c55e !important; }}
    .signal-card-bearish {{ border-left: 3px solid #ef4444 !important; }}
    .signal-card-neutral {{ border-left: 3px solid #f59e0b !important; }}

    .crv-score-high {{ color: #d4a843; font-weight: 700; font-size: 1.1em; }}
    .crv-score-mid  {{ color: #888;    font-weight: 600; }}
    .crv-score-low  {{ color: #555;    font-weight: 400; }}

    .news-card {{ background: #111; border: 1px solid #1e1e1e; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; transition: border-color 0.2s; }}
    .news-card:hover {{ border-color: #2a2a2a; }}
    .news-title {{ font-weight: 600; color: #e0e0e0; font-size: 0.92rem; line-height: 1.4; }}
    .news-meta  {{ font-size: 0.78rem; color: #555; margin-top: 4px; }}

    .stCheckbox label {{ font-family: 'RedRose', sans-serif; font-size: 0.88rem; color: #aaa; }}
    .stCheckbox [data-testid="stCheckbox"] {{ accent-color: #d4a843; }}
    .stRadio label {{ font-family: 'RedRose', sans-serif; font-size: 0.85rem; color: #aaa; }}
    [data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stTickBar"] {{ color: #444; }}

    .gold-line {{ height: 2px; background: linear-gradient(90deg, #d4a843, transparent); margin: 12px 0; border: none; }}

    /* ── Dropdown-Popups (werden außerhalb des normalen DOM gerendert) ──── */
    [data-baseweb="popover"],
    [data-baseweb="menu"] {{
        background: #1a1a1a !important;
        border: 1px solid #2a2a2a !important;
        border-radius: 8px !important;
    }}
    [data-baseweb="menu"] [role="option"] {{
        background: #1a1a1a !important;
        color: #e0e0e0 !important;
        font-family: 'RedRose', sans-serif !important;
    }}
    [data-baseweb="menu"] [role="option"]:hover,
    [data-baseweb="menu"] [aria-selected="true"] {{
        background: #252525 !important;
        color: #d4a843 !important;
    }}
    [data-baseweb="select"] [data-testid="stSelectboxVirtualDropdown"] {{
        background: #1a1a1a !important;
    }}

    /* ── Multiselect-Chips ─────────────────────────────────────────────── */
    [data-baseweb="tag"] {{
        background: #2a2a2a !important;
        color: #e0e0e0 !important;
        border-radius: 4px !important;
    }}

    /* ── Tooltips ──────────────────────────────────────────────────────── */
    [data-baseweb="tooltip"] div {{
        background: #252525 !important;
        color: #e0e0e0 !important;
        border: 1px solid #333 !important;
        border-radius: 6px !important;
    }}
    """


# ══════════════════════════════════════════════════════════════════════════════
# GREEN THEME (Weiß + Grün — Landingpage-Palette)
# ══════════════════════════════════════════════════════════════════════════════

def _css_green() -> str:
    g = _G
    return f"""
    {_font_face()}

    [data-testid="stSidebarNav"] {{ display: none !important; }}

    [data-testid="stSidebar"] [data-testid="stPageLink"] > a {{
        border-radius: 6px !important; background: transparent !important;
        border: none !important; padding: 4px 8px !important;
        font-size: 0.82rem !important; color: {_INK3} !important;
        width: 100% !important; display: block !important;
    }}
    [data-testid="stSidebar"] [data-testid="stPageLink"] > a:hover {{
        color: {g["700"]} !important; background: {g["50"]} !important;
    }}
    [data-testid="stSidebar"] [data-testid="stPageLink"] > a[aria-current="page"] {{
        color: {g["800"]} !important; background: {g["200"]} !important; font-weight: 600 !important;
    }}

    html, body, .stApp {{
        background-color: #ffffff !important;
        color: {_INK} !important;
        font-family: 'RedRose', 'Inter', sans-serif;
    }}
    .main .block-container {{ padding-top: 0.75rem; padding-bottom: 1rem; max-width: 1600px; }}

    /* Allgemeiner Text — sicherstellen dass alles dunkel und lesbar ist */
    p, label, span, div, li, td, th {{
        font-family: 'RedRose', 'Inter', sans-serif;
        color: {_INK2};
    }}

    h1, h2, h3, h4, h5 {{
        font-family: 'RedRose', sans-serif !important;
        color: {g["900"]} !important; letter-spacing: 0.03em;
    }}
    h1 {{ font-weight: 700; font-size: 1.9rem !important; }}
    h2 {{ font-weight: 600; font-size: 1.4rem !important; }}
    h3 {{ font-weight: 600; font-size: 1.15rem !important; }}
    h4 {{ font-weight: 400; font-size: 1rem !important; }}

    section[data-testid="stSidebar"] {{
        background-color: {g["25"]} !important; border-right: 1px solid {g["200"]};
    }}
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span {{
        font-family: 'RedRose', sans-serif; font-size: 0.85rem; color: {_INK3} !important;
    }}
    section[data-testid="stSidebar"] [data-testid="stMarkdown"] h2 {{
        font-size: 1rem !important; color: {g["700"]} !important;
        text-transform: uppercase; letter-spacing: 0.1em;
    }}

    /* ── Metric-Karten ─────────────────────────────────────────────────── */
    [data-testid="metric-container"] {{
        background: {g["50"]} !important; border: 1px solid {g["200"]} !important;
        border-radius: 10px !important; padding: 12px 16px !important;
    }}
    [data-testid="metric-container"] [data-testid="stMetricLabel"],
    [data-testid="metric-container"] [data-testid="stMetricLabel"] *,
    [data-testid="metric-container"] [data-testid="stMetricLabel"] p {{
        font-size: 0.75rem !important; color: {_INK3} !important;
        text-transform: uppercase; letter-spacing: 0.08em;
    }}
    [data-testid="metric-container"] [data-testid="stMetricValue"],
    [data-testid="metric-container"] [data-testid="stMetricValue"] *,
    [data-testid="metric-container"] [data-testid="stMetricValue"] div {{
        font-size: 1.4rem !important; font-weight: 700 !important;
        color: {g["900"]} !important;
    }}
    [data-testid="metric-container"] [data-testid="stMetricDelta"],
    [data-testid="metric-container"] [data-testid="stMetricDelta"] * {{
        font-size: 0.85rem !important;
    }}

    /* ── Tabs ──────────────────────────────────────────────────────────── */
    .stTabs [data-baseweb="tab-list"] {{
        background: transparent; border-bottom: 1px solid {g["200"]}; gap: 4px;
    }}
    .stTabs [data-baseweb="tab"] {{
        font-family: 'RedRose', sans-serif; font-weight: 600; font-size: 0.85rem;
        color: {_INK4} !important; background: transparent;
        border-radius: 6px 6px 0 0; padding: 8px 16px;
        text-transform: uppercase; letter-spacing: 0.06em;
    }}
    .stTabs [aria-selected="true"] {{
        color: {g["700"]} !important; border-bottom: 2px solid {g["600"]} !important;
    }}

    /* ── Buttons — exakte Landing-Page-Vorlage ─────────────────────────── */
    /* Alle Buttons: helles Grün-Weiß wie landing .channel-btn */
    .stButton button,
    button[data-testid="baseButton-secondary"],
    [data-testid="baseButton-secondary"] {{
        font-family: 'RedRose', sans-serif !important;
        font-weight: 600 !important; font-size: 0.85rem !important;
        letter-spacing: 0.04em !important; border-radius: 8px !important;
        border: 1px solid {g["200"]} !important;
        background: {g["25"]} !important; color: {g["800"]} !important;
        padding: 0.5rem 1.2rem !important; transition: all 0.18s !important;
        box-shadow: none !important;
    }}
    .stButton button:hover,
    button[data-testid="baseButton-secondary"]:hover {{
        border-color: {g["600"]} !important;
        background: {g["50"]} !important;
        color: {g["800"]} !important;
    }}
    /* Primary: dunkelgrün + weißer Text — wie landing .nav-cta / .submit-btn */
    button[data-testid="baseButton-primary"],
    [data-testid="baseButton-primary"],
    .stButton button[kind="primary"] {{
        background: {g["800"]} !important;   /* #1b4332 */
        color: #ffffff !important;
        border: none !important;
        font-weight: 700 !important;
        box-shadow: 0 2px 8px rgba(27,67,50,.25) !important;
    }}
    /* Text-Elemente IM Primary-Button zwingend weiß (Streamlit rendert das Label
       in einem inneren <p>/<div>, das sonst die dunkle Standardfarbe erbt) */
    button[data-testid="baseButton-primary"] *,
    [data-testid="baseButton-primary"] *,
    .stButton button[kind="primary"] * {{
        color: #ffffff !important;
    }}
    button[data-testid="baseButton-primary"]:hover,
    .stButton button[kind="primary"]:hover {{
        background: {g["900"]} !important;   /* #0d2318 — noch dunkler */
        color: #ffffff !important;
        box-shadow: 0 4px 16px rgba(27,67,50,.35) !important;
    }}
    button[data-testid="baseButton-primary"]:hover *,
    .stButton button[kind="primary"]:hover * {{
        color: #ffffff !important;
    }}

    /* ── Eingabefelder: GENAU EIN sauberer Rahmen pro Feld ─────────────────
       Der Rahmen sitzt nur am äußeren BaseWeb-Container; alle inneren
       Elemente sind transparent + randlos → keine Doppelränder mehr.       */
    .stSelectbox [data-baseweb="select"],
    .stTextInput [data-baseweb="input"],
    .stTextInput [data-baseweb="base-input"],
    .stNumberInput [data-baseweb="input"],
    .stNumberInput [data-baseweb="base-input"],
    .stTextArea [data-baseweb="textarea"],
    .stTextArea [data-baseweb="base-input"] {{
        background: #ffffff !important;
        border: 1px solid {g["200"]} !important;
        border-radius: 8px !important;
        overflow: hidden !important;        /* rundet auch die ±-Buttons sauber ab */
        box-shadow: none !important;
    }}
    /* Innen alles randlos + transparent */
    .stSelectbox [data-baseweb="select"] > div,
    .stSelectbox [data-baseweb="select"] > div > div,
    .stNumberInput [data-baseweb="input"] > div,
    .stNumberInput input,
    [data-testid="stNumberInput"] input,
    [data-testid="stNumberInputField"],
    .stTextInput input, .stTextArea textarea {{
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        color: {_INK} !important;
        font-family: 'RedRose', sans-serif !important;
    }}
    .stNumberInput input {{ font-weight: 600 !important; }}
    /* Fokus: ein dezenter grüner Rahmen + Glow am Container */
    .stSelectbox [data-baseweb="select"]:focus-within,
    .stTextInput [data-baseweb="input"]:focus-within,
    .stNumberInput [data-baseweb="input"]:focus-within,
    .stTextArea [data-baseweb="textarea"]:focus-within {{
        border-color: {g["600"]} !important;
        box-shadow: 0 0 0 2px rgba(64,145,108,0.18) !important;
    }}
    /* Ausgewählter Wert + Platzhalter im Select dunkel + Pfeil grün */
    .stSelectbox [data-baseweb="select"] span,
    .stSelectbox [data-baseweb="select"] div {{ color: {_INK} !important; }}
    .stSelectbox [data-baseweb="select"] svg {{ fill: {g["700"]} !important; color: {g["700"]} !important; }}

    /* ± / Stepper-Buttons im Number Input — bündig im Rahmen */
    .stNumberInput button,
    [data-testid="stNumberInput"] button {{
        background: {g["50"]} !important; color: {g["700"]} !important;
        border: none !important; border-left: 1px solid {g["200"]} !important;
        border-radius: 0 !important;
    }}
    .stNumberInput button:hover {{
        background: {g["100"]} !important; color: {g["800"]} !important;
    }}
    .stNumberInput button svg {{ fill: {g["700"]} !important; }}

    /* ── Tabellen ──────────────────────────────────────────────────────── */
    [data-testid="stDataFrame"] {{ border: 1px solid {g["200"]}; border-radius: 10px; overflow: hidden; }}
    [data-testid="stDataFrame"] th {{
        background: {g["100"]} !important; color: {g["800"]} !important;
        font-family: 'RedRose', sans-serif; font-weight: 700; font-size: 0.8rem;
        text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 1px solid {g["200"]};
    }}
    [data-testid="stDataFrame"] td {{
        background: #ffffff !important; color: {_INK2} !important;
        font-size: 0.85rem; border-bottom: 1px solid {g["50"]};
    }}
    [data-testid="stDataFrame"] tr:hover td {{ background: {g["25"]} !important; }}

    /* ── Alerts / Warnings ─────────────────────────────────────────────── */
    [data-testid="stAlert"] {{
        border-radius: 8px !important; font-family: 'RedRose', sans-serif;
        font-size: 0.88rem; color: {_INK2} !important;
    }}
    [data-testid="stAlert"] * {{ color: {_INK2} !important; }}

    /* ── Expander — dunkelgrün Header, helle Schrift ───────────────────── */
    [data-testid="stExpander"] {{
        background: #ffffff !important; border: 1px solid {g["300"]} !important;
        border-radius: 10px !important; overflow: hidden !important;
    }}
    [data-testid="stExpander"] details summary,
    [data-testid="stExpander"] > details > summary {{
        background: {g["800"]} !important; color: #ffffff !important;
        font-family: 'RedRose', sans-serif !important; font-weight: 600 !important;
        padding: 10px 16px !important; border-radius: 8px 8px 0 0 !important;
    }}
    [data-testid="stExpander"] details:not([open]) summary {{
        border-radius: 8px !important;
    }}
    [data-testid="stExpander"] details summary:hover {{
        background: {g["700"]} !important;
    }}
    [data-testid="stExpander"] details summary * {{
        color: #ffffff !important;
    }}
    [data-testid="stExpander"] details summary svg {{
        stroke: #ffffff !important; fill: #ffffff !important;
    }}
    [data-testid="stExpander"] details > div {{
        background: #ffffff !important; padding: 12px 16px !important;
    }}

    /* ── Fortschrittsbalken ────────────────────────────────────────────── */
    .stProgress > div > div > div {{
        background: linear-gradient(90deg, {g["600"]}, {g["400"]}) !important;
        border-radius: 4px;
    }}
    .stProgress > div > div {{
        background: {g["100"]} !important;
    }}

    hr {{ border-color: {g["200"]} !important; margin: 1rem 0; }}

    /* ── Seiten-Header ─────────────────────────────────────────────────── */
    .sc-header {{
        display: flex; align-items: center; gap: 16px; padding: 12px 0 8px 0;
        border-bottom: 1px solid {g["200"]}; margin-bottom: 16px;
    }}
    .sc-page-title {{
        font-family: 'RedRose', sans-serif; font-weight: 700; font-size: 1.6rem;
        color: {g["900"]} !important; letter-spacing: 0.04em; flex: 1;
    }}
    .sc-page-subtitle {{
        font-family: 'RedRose', sans-serif; font-weight: 300; font-size: 0.8rem;
        color: {_INK4} !important; text-transform: uppercase; letter-spacing: 0.1em;
    }}

    .market-open  {{ color: #16a34a !important; font-weight: 600; }}
    .market-closed {{ color: #d97706 !important; font-weight: 600; }}

    /* ── Tags ──────────────────────────────────────────────────────────── */
    .tag {{ display: inline-block; padding: 2px 10px; border-radius: 20px; font-size: 0.75rem; font-weight: 600; letter-spacing: 0.05em; margin-right: 4px; }}
    .tag-gold  {{ background: {g["100"]}; color: {g["800"]}; border: 1px solid {g["300"]}; }}
    .tag-green {{ background: #dcfce7;   color: #15803d;   border: 1px solid #86efac; }}
    .tag-red   {{ background: #fee2e2;   color: #b91c1c;   border: 1px solid #fca5a5; }}
    .tag-gray  {{ background: #f1f5f9;   color: {_INK3};   border: 1px solid #cbd5e1; }}
    .tag-blue  {{ background: #eff6ff;   color: #1d4ed8;   border: 1px solid #93c5fd; }}

    /* ── Signal Cards ──────────────────────────────────────────────────── */
    .signal-card {{ background: {g["25"]}; border: 1px solid {g["200"]}; border-radius: 10px; padding: 12px 16px; margin-bottom: 6px; }}
    .signal-card-bullish {{ border-left: 3px solid #16a34a !important; }}
    .signal-card-bearish {{ border-left: 3px solid #ef4444 !important; }}
    .signal-card-neutral {{ border-left: 3px solid #d97706 !important; }}

    .crv-score-high {{ color: {g["700"]} !important; font-weight: 700; font-size: 1.1em; }}
    .crv-score-mid  {{ color: {_INK3}   !important; font-weight: 600; }}
    .crv-score-low  {{ color: {_INK4}   !important; font-weight: 400; }}

    /* ── News Cards ────────────────────────────────────────────────────── */
    .news-card {{ background: {g["25"]}; border: 1px solid {g["200"]}; border-radius: 8px; padding: 12px 16px; margin-bottom: 8px; transition: border-color 0.2s; }}
    .news-card:hover {{ border-color: {g["500"]}; }}
    .news-title {{ font-weight: 600; color: {_INK} !important; font-size: 0.92rem; line-height: 1.4; }}
    .news-meta  {{ font-size: 0.78rem; color: {_INK4} !important; margin-top: 4px; }}

    /* ── Checkboxen / Radio / Slider ───────────────────────────────────── */
    .stCheckbox label, .stCheckbox label span {{ font-family: 'RedRose', sans-serif; font-size: 0.88rem; color: {_INK2} !important; }}
    .stRadio label, .stRadio label span {{ font-family: 'RedRose', sans-serif; font-size: 0.85rem; color: {_INK2} !important; }}
    /* Checkbox-Kästchen: heller Rand auf weiß, grün wenn ausgewählt
       (BaseWeb-dark macht es sonst dunkelgrau/golden) */
    .stCheckbox [data-baseweb="checkbox"] span[data-baseweb="checkmark"],
    .stCheckbox [data-baseweb="checkbox"] > span:first-child {{
        background-color: #ffffff !important;
        border-color: {g["300"]} !important;
    }}
    .stCheckbox [data-baseweb="checkbox"] input:checked + span,
    .stCheckbox [data-baseweb="checkbox"][aria-checked="true"] span[data-baseweb="checkmark"],
    .stCheckbox [data-baseweb="checkbox"] span[aria-checked="true"] {{
        background-color: {g["600"]} !important;
        border-color: {g["600"]} !important;
    }}
    /* Radio-Punkte grün statt gold */
    .stRadio [data-baseweb="radio"] div[aria-checked="true"],
    .stRadio [role="radiogroup"] [aria-checked="true"] > div:first-child {{
        background-color: {g["600"]} !important; border-color: {g["600"]} !important;
    }}
    .stRadio [data-baseweb="radio"] div:first-child {{ border-color: {g["300"]} !important; }}
    /* Slider: Track hell, gefüllter Teil + Knopf grün */
    [data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stTickBar"] {{ color: {_INK4} !important; }}
    [data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {{ background: {g["600"]} !important; }}
    [data-testid="stSlider"] [data-baseweb="slider"] div[data-testid="stThumbValue"] {{ color: {g["800"]} !important; }}
    [data-testid="stSlider"] [data-baseweb="slider"] > div > div {{ background: {g["200"]} !important; }}
    [data-testid="stSlider"] [data-baseweb="slider"] > div > div > div {{ background: {g["600"]} !important; }}

    /* Trennlinie */
    .gold-line {{ height: 2px; background: linear-gradient(90deg, {g["600"]}, transparent); margin: 12px 0; border: none; }}

    /* ── Dropdown-Popups (Portal außerhalb der App; BaseWeb rendert sie wegen
       config.toml base="dark" dunkel → hier hart auf hell überschreiben) ──
       li[role="option"] hat höhere Spezifität als BaseWebs Emotion-Klassen,
       deshalb gewinnen diese Regeln zuverlässig.                            */
    [data-baseweb="popover"],
    [data-baseweb="popover"] > div,
    [data-baseweb="popover"] [data-baseweb="menu"],
    [data-baseweb="menu"],
    ul[role="listbox"],
    [data-baseweb="popover"] ul,
    [data-testid="stSelectboxVirtualDropdown"],
    [data-testid="stSelectboxVirtualDropdown"] ul,
    [data-testid="stVirtualDropdown"],
    [data-testid="stVirtualDropdown"] ul {{
        background-color: #ffffff !important;
        border-color: {g["200"]} !important;
        border-radius: 8px !important;
    }}
    li[role="option"],
    [data-baseweb="menu"] li,
    [data-baseweb="popover"] li[role="option"],
    [role="option"] {{
        background-color: #ffffff !important;
        color: {_INK} !important;
        font-family: 'RedRose', sans-serif !important;
    }}
    li[role="option"] *,
    [role="option"] * {{ color: {_INK} !important; }}
    li[role="option"]:hover,
    li[role="option"][aria-selected="true"],
    [data-baseweb="menu"] li:hover,
    [role="option"]:hover,
    [role="option"][aria-selected="true"] {{
        background-color: {g["50"]} !important;
        color: {g["800"]} !important;
    }}
    li[role="option"]:hover *,
    li[role="option"][aria-selected="true"] *,
    [role="option"]:hover * {{ color: {g["800"]} !important; }}

    /* ── Multiselect-Chips ─────────────────────────────────────────────── */
    [data-baseweb="tag"] {{
        background: {g["100"]} !important;
        color: {g["800"]} !important;
        border-radius: 4px !important;
    }}
    [data-baseweb="tag"] span, [data-baseweb="tag"] div {{ color: {g["800"]} !important; }}
    [data-baseweb="tag"] svg {{ fill: {g["800"]} !important; }}

    /* ── Tooltips ──────────────────────────────────────────────────────── */
    [data-baseweb="tooltip"] div {{
        background: {g["900"]} !important;
        color: #ffffff !important;
        border-radius: 6px !important;
    }}
    """


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

def get_css() -> str:
    """Gibt das komplette CSS für das aktive Theme zurück (liest session_state)."""
    return _css_green() if _active_theme() == "green" else _css_dark()


def get_logo_html(variant: str = "auto", height: int = 40) -> str:
    """
    Rendert das STILLHALTER COMMUNITY Text-Logo.
    variant="auto"  → passt sich dem aktiven Theme an
    variant="white" → heller Text (für dunkle Hintergründe)
    variant="black" → dunkler Text (für helle Hintergründe)
    """
    if variant == "auto":
        variant = "black" if _active_theme() == "green" else "white"

    if variant == "white":
        top_color = "#ffffff"
        sub_color = "#888888"
    else:
        top_color = _G["800"]    # dunkelgrün auf hellem BG
        sub_color = _G["600"]

    top_size = max(10, int(height * 0.44))
    sub_size = max(9,  int(height * 0.44))

    return f"""<div style="
        font-family:'RedRose','Inter',sans-serif;
        line-height:1.05; user-select:none; display:inline-block;
    ">
        <div style="font-weight:700; font-size:{top_size}px; color:{top_color};
                    letter-spacing:0.10em; text-transform:uppercase;">STILLHALTER</div>
        <div style="font-weight:300; font-size:{sub_size}px; color:{sub_color};
                    letter-spacing:0.10em; text-transform:uppercase; margin-top:-2px;">COMMUNITY</div>
    </div>"""
