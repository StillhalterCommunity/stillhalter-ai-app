"""
Stillhalter AI App Brand Theme.
Red Rose Font + Green Professional Design (test/green-palette branch).

Grün-Palette:
  g900 #0d2318 | g800 #1b4332 | g700 #2d6a4f | g600 #40916c
  g500 #52b788 | g400 #74c69d | g300 #95d5b2 | g200 #b7e4c7
  g100 #DAEFEB | g50  #eef8f5 | g25  #f6fdfb
  ink  #0a1628 | ink2 #1e293b | ink3 #475569 | ink4 #94a3b8
"""

import base64
import os

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")


def _load_b64(filename: str) -> str:
    path = os.path.join(STATIC_DIR, filename)
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return ""


def get_logo_html(variant: str = "white", height: int = 40) -> str:
    """
    Rendert das STILLHALTER COMMUNITY Text-Logo.
    variant="white" → heller Text für dunklen Hintergrund (Login)
    variant="black" → dunkler Text für hellen Hintergrund
    """
    if variant == "white":
        top_color = "#ffffff"
        sub_color = "#95d5b2"   # g300 — sanftes Grün auf dunklem BG
    else:
        top_color = "#1b4332"   # g800
        sub_color = "#40916c"   # g600

    top_size = max(10, int(height * 0.44))
    sub_size = max(9,  int(height * 0.44))

    return f"""<div style="
        font-family:'RedRose','Inter',sans-serif;
        line-height:1.05;
        user-select:none;
        display:inline-block;
    ">
        <div style="
            font-weight:700;
            font-size:{top_size}px;
            color:{top_color};
            letter-spacing:0.10em;
            text-transform:uppercase;
        ">STILLHALTER</div>
        <div style="
            font-weight:300;
            font-size:{sub_size}px;
            color:{sub_color};
            letter-spacing:0.10em;
            text-transform:uppercase;
            margin-top:-2px;
        ">COMMUNITY</div>
    </div>"""


def get_css() -> str:
    """Vollständiges CSS mit Red Rose Font + Stillhalter AI App Branding (Grün-Palette)."""
    rr_regular = _load_b64("RedRose-Regular.b64")
    rr_bold    = _load_b64("RedRose-Bold.b64")
    rr_light   = _load_b64("RedRose-Light.b64")
    rr_semi    = _load_b64("RedRose-SemiBold.b64")

    font_face = f"""
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
    """ if rr_regular else ""

    return f"""
    {font_face}

    /* ── Automatische Streamlit-Seitennavigation ausblenden ── */
    [data-testid="stSidebarNav"] {{
        display: none !important;
    }}

    /* ── Sidebar Page-Links ── */
    [data-testid="stSidebar"] [data-testid="stPageLink"] > a {{
        border-radius: 6px !important;
        background: transparent !important;
        border: none !important;
        padding: 4px 8px !important;
        font-size: 0.82rem !important;
        color: #475569 !important;
        width: 100% !important;
        display: block !important;
    }}
    [data-testid="stSidebar"] [data-testid="stPageLink"] > a:hover {{
        color: #2d6a4f !important;
        background: #eef8f5 !important;
    }}
    [data-testid="stSidebar"] [data-testid="stPageLink"] > a[aria-current="page"] {{
        color: #1b4332 !important;
        background: #b7e4c7 !important;
        font-weight: 600 !important;
    }}

    /* ── Base ── */
    html, body, .stApp {{
        background-color: #ffffff !important;
        color: #0a1628;
        font-family: 'RedRose', 'Inter', sans-serif;
    }}
    .main .block-container {{
        padding-top: 0.75rem;
        padding-bottom: 1rem;
        max-width: 1600px;
    }}

    /* ── Typography ── */
    h1, h2, h3, h4, h5 {{
        font-family: 'RedRose', sans-serif !important;
        color: #0d2318 !important;
        letter-spacing: 0.03em;
    }}
    h1 {{ font-weight: 700; font-size: 1.9rem !important; }}
    h2 {{ font-weight: 600; font-size: 1.4rem !important; }}
    h3 {{ font-weight: 600; font-size: 1.15rem !important; }}
    h4 {{ font-weight: 400; font-size: 1rem !important; }}
    p, label, span, div {{ font-family: 'RedRose', 'Inter', sans-serif; }}

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {{
        background-color: #f6fdfb !important;
        border-right: 1px solid #b7e4c7;
    }}
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span {{
        font-family: 'RedRose', sans-serif;
        font-size: 0.85rem;
        color: #475569;
    }}
    section[data-testid="stSidebar"] [data-testid="stMarkdown"] h2 {{
        font-size: 1rem !important;
        color: #2d6a4f !important;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }}

    /* ── Metric Cards ── */
    [data-testid="metric-container"] {{
        background: #f6fdfb !important;
        border: 1px solid #b7e4c7 !important;
        border-radius: 10px !important;
        padding: 12px 16px !important;
    }}
    [data-testid="metric-container"] [data-testid="stMetricLabel"] {{
        font-size: 0.75rem !important;
        color: #475569 !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }}
    [data-testid="metric-container"] [data-testid="stMetricValue"] {{
        font-size: 1.4rem !important;
        font-weight: 700 !important;
        color: #0d2318 !important;
    }}
    [data-testid="metric-container"] [data-testid="stMetricDelta"] {{
        font-size: 0.8rem !important;
    }}

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {{
        background: transparent;
        border-bottom: 1px solid #b7e4c7;
        gap: 4px;
    }}
    .stTabs [data-baseweb="tab"] {{
        font-family: 'RedRose', sans-serif;
        font-weight: 600;
        font-size: 0.85rem;
        color: #94a3b8 !important;
        background: transparent;
        border-radius: 6px 6px 0 0;
        padding: 8px 16px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }}
    .stTabs [aria-selected="true"] {{
        color: #2d6a4f !important;
        border-bottom: 2px solid #40916c !important;
    }}

    /* ── Buttons ── */
    .stButton > button {{
        font-family: 'RedRose', sans-serif;
        font-weight: 600;
        font-size: 0.85rem;
        letter-spacing: 0.05em;
        border-radius: 8px;
        border: 1px solid #b7e4c7;
        background: #eef8f5;
        color: #1b4332;
        padding: 0.5rem 1.2rem;
        transition: all 0.2s;
    }}
    .stButton > button:hover {{
        border-color: #40916c;
        color: #1b4332;
        background: #daefeb;
    }}
    [data-testid="baseButton-primary"] > button,
    .stButton [kind="primary"] {{
        background: linear-gradient(135deg, #40916c, #2d6a4f) !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 700 !important;
    }}
    .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, #40916c, #2d6a4f) !important;
        color: #ffffff !important;
        border: none !important;
        font-weight: 700 !important;
    }}

    /* ── Inputs ── */
    .stSelectbox [data-baseweb="select"] > div,
    .stNumberInput input,
    .stTextInput input {{
        background: #f6fdfb !important;
        border: 1px solid #b7e4c7 !important;
        border-radius: 8px !important;
        color: #0a1628 !important;
        font-family: 'RedRose', sans-serif;
    }}
    .stSelectbox [data-baseweb="select"] > div:focus-within {{
        border-color: #40916c !important;
    }}

    /* ── DataFrames ── */
    [data-testid="stDataFrame"] {{
        border: 1px solid #b7e4c7;
        border-radius: 10px;
        overflow: hidden;
    }}
    [data-testid="stDataFrame"] th {{
        background: #eef8f5 !important;
        color: #2d6a4f !important;
        font-family: 'RedRose', sans-serif;
        font-weight: 600;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        border-bottom: 1px solid #b7e4c7;
    }}
    [data-testid="stDataFrame"] td {{
        background: #ffffff !important;
        color: #1e293b !important;
        font-size: 0.85rem;
        border-bottom: 1px solid #eef8f5;
    }}
    [data-testid="stDataFrame"] tr:hover td {{
        background: #f6fdfb !important;
    }}

    /* ── Info / Warning / Success boxes ── */
    [data-testid="stAlert"] {{
        border-radius: 8px !important;
        font-family: 'RedRose', sans-serif;
        font-size: 0.88rem;
    }}

    /* ── Expander ── */
    [data-testid="stExpander"] {{
        background: #f6fdfb !important;
        border: 1px solid #b7e4c7 !important;
        border-radius: 10px !important;
    }}
    [data-testid="stExpander"] summary {{
        font-family: 'RedRose', sans-serif;
        font-weight: 600;
        color: #475569;
    }}

    /* ── Progress bar ── */
    .stProgress > div > div > div {{
        background: linear-gradient(90deg, #40916c, #74c69d) !important;
        border-radius: 4px;
    }}

    /* ── Divider ── */
    hr {{ border-color: #b7e4c7 !important; margin: 1rem 0; }}

    /* ── Custom Components ── */
    .sc-header {{
        display: flex; align-items: center; gap: 16px;
        padding: 12px 0 8px 0;
        border-bottom: 1px solid #b7e4c7;
        margin-bottom: 16px;
    }}
    .sc-page-title {{
        font-family: 'RedRose', sans-serif;
        font-weight: 700;
        font-size: 1.6rem;
        color: #0d2318;
        letter-spacing: 0.04em;
        flex: 1;
    }}
    .sc-page-subtitle {{
        font-family: 'RedRose', sans-serif;
        font-weight: 300;
        font-size: 0.8rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }}
    .market-open  {{ color: #22c55e; font-weight: 600; }}
    .market-closed {{ color: #f59e0b; font-weight: 600; }}

    .tag {{
        display: inline-block; padding: 2px 10px;
        border-radius: 20px; font-size: 0.75rem; font-weight: 600;
        letter-spacing: 0.05em; margin-right: 4px;
    }}
    .tag-gold    {{ background: #eef8f5; color: #2d6a4f; border: 1px solid #74c69d; }}
    .tag-green   {{ background: #dcfce7; color: #16a34a; border: 1px solid #86efac; }}
    .tag-red     {{ background: #fee2e2; color: #ef4444; border: 1px solid #fca5a5; }}
    .tag-gray    {{ background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }}
    .tag-blue    {{ background: #eff6ff; color: #3b82f6; border: 1px solid #93c5fd; }}

    .signal-card {{
        background: #f6fdfb; border: 1px solid #b7e4c7; border-radius: 10px;
        padding: 12px 16px; margin-bottom: 6px;
    }}
    .signal-card-bullish {{ border-left: 3px solid #22c55e !important; }}
    .signal-card-bearish {{ border-left: 3px solid #ef4444 !important; }}
    .signal-card-neutral {{ border-left: 3px solid #f59e0b !important; }}

    .crv-score-high {{ color: #2d6a4f; font-weight: 700; font-size: 1.1em; }}
    .crv-score-mid  {{ color: #475569; font-weight: 600; }}
    .crv-score-low  {{ color: #94a3b8; font-weight: 400; }}

    .news-card {{
        background: #f6fdfb; border: 1px solid #b7e4c7; border-radius: 8px;
        padding: 12px 16px; margin-bottom: 8px;
        transition: border-color 0.2s;
    }}
    .news-card:hover {{ border-color: #40916c; }}
    .news-title {{ font-weight: 600; color: #0a1628; font-size: 0.92rem; line-height: 1.4; }}
    .news-meta  {{ font-size: 0.78rem; color: #94a3b8; margin-top: 4px; }}

    /* ── Checkbox ── */
    .stCheckbox label {{
        font-family: 'RedRose', sans-serif;
        font-size: 0.88rem;
        color: #475569;
    }}
    .stCheckbox [data-testid="stCheckbox"] {{
        accent-color: #40916c;
    }}

    /* ── Radio ── */
    .stRadio label {{
        font-family: 'RedRose', sans-serif;
        font-size: 0.85rem;
        color: #475569;
    }}

    /* ── Slider ── */
    [data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stTickBar"] {{
        color: #94a3b8;
    }}

    /* Green accent line (ehem. gold-line) */
    .gold-line {{
        height: 2px;
        background: linear-gradient(90deg, #40916c, transparent);
        margin: 12px 0;
        border: none;
    }}
    """
