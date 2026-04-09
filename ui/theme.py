"""
Stillhalter AI App Brand Theme.
Red Rose Font + Dark Professional Design.
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
    STILLHALTER = fett | COMMUNITY = leicht/grau
    variant="white" → heller Text für dunklen Hintergrund
    variant="black" → dunkler Text für hellen Hintergrund
    """
    if variant == "white":
        top_color = "#ffffff"
        sub_color = "#888888"
    else:
        top_color = "#0c0c0c"
        sub_color = "#888888"

    # Schriftgröße proportional zur übergebenen Höhe
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
    """Vollständiges CSS mit Red Rose Font + Stillhalter AI App Branding."""
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
    /* Versteckt die auto-generierte Dateinamen-Liste oben in der Sidebar */
    [data-testid="stSidebarNav"] {{
        display: none !important;
    }}

    /* ── Sidebar Page-Links: einheitliches Styling ── */
    [data-testid="stSidebar"] [data-testid="stPageLink"] > a {{
        border-radius: 6px !important;
        background: transparent !important;
        border: none !important;
        padding: 4px 8px !important;
        font-size: 0.82rem !important;
        color: #888 !important;
        width: 100% !important;
        display: block !important;
    }}
    [data-testid="stSidebar"] [data-testid="stPageLink"] > a:hover {{
        color: #d4a843 !important;
        background: #1a1a1a !important;
    }}
    /* Aktive Seite hervorheben */
    [data-testid="stSidebar"] [data-testid="stPageLink"] > a[aria-current="page"] {{
        color: #d4a843 !important;
        background: #1a1a1a !important;
        font-weight: 600 !important;
    }}

    /* ── Base ── */
    html, body, .stApp {{
        background-color: #0c0c0c !important;
        color: #e8e8e8;
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
        color: #f0f0f0 !important;
        letter-spacing: 0.03em;
    }}
    h1 {{ font-weight: 700; font-size: 1.9rem !important; }}
    h2 {{ font-weight: 600; font-size: 1.4rem !important; }}
    h3 {{ font-weight: 600; font-size: 1.15rem !important; }}
    h4 {{ font-weight: 400; font-size: 1rem !important; }}
    p, label, span, div {{ font-family: 'RedRose', 'Inter', sans-serif; }}

    /* ── Sidebar ── */
    section[data-testid="stSidebar"] {{
        background-color: #111111 !important;
        border-right: 1px solid #1e1e1e;
    }}
    section[data-testid="stSidebar"] .stSelectbox label,
    section[data-testid="stSidebar"] p,
    section[data-testid="stSidebar"] span {{
        font-family: 'RedRose', sans-serif;
        font-size: 0.85rem;
        color: #aaa;
    }}
    section[data-testid="stSidebar"] [data-testid="stMarkdown"] h2 {{
        font-size: 1rem !important;
        color: #d4a843 !important;
        text-transform: uppercase;
        letter-spacing: 0.1em;
    }}

    /* ── Metric Cards ── */
    [data-testid="metric-container"] {{
        background: #141414 !important;
        border: 1px solid #222 !important;
        border-radius: 10px !important;
        padding: 12px 16px !important;
    }}
    [data-testid="metric-container"] [data-testid="stMetricLabel"] {{
        font-size: 0.75rem !important;
        color: #888 !important;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }}
    [data-testid="metric-container"] [data-testid="stMetricValue"] {{
        font-size: 1.4rem !important;
        font-weight: 700 !important;
        color: #f0f0f0 !important;
    }}
    [data-testid="metric-container"] [data-testid="stMetricDelta"] {{
        font-size: 0.8rem !important;
    }}

    /* ── Tabs ── */
    .stTabs [data-baseweb="tab-list"] {{
        background: transparent;
        border-bottom: 1px solid #222;
        gap: 4px;
    }}
    .stTabs [data-baseweb="tab"] {{
        font-family: 'RedRose', sans-serif;
        font-weight: 600;
        font-size: 0.85rem;
        color: #666 !important;
        background: transparent;
        border-radius: 6px 6px 0 0;
        padding: 8px 16px;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }}
    .stTabs [aria-selected="true"] {{
        color: #d4a843 !important;
        border-bottom: 2px solid #d4a843 !important;
    }}

    /* ── Buttons ── */
    .stButton > button {{
        font-family: 'RedRose', sans-serif;
        font-weight: 600;
        font-size: 0.85rem;
        letter-spacing: 0.05em;
        border-radius: 8px;
        border: 1px solid #2a2a2a;
        background: #1a1a1a;
        color: #e0e0e0;
        padding: 0.5rem 1.2rem;
        transition: all 0.2s;
    }}
    .stButton > button:hover {{
        border-color: #d4a843;
        color: #d4a843;
        background: #1a1a1a;
    }}
    [data-testid="baseButton-primary"] > button,
    .stButton [kind="primary"] {{
        background: linear-gradient(135deg, #d4a843, #b8912f) !important;
        color: #0c0c0c !important;
        border: none !important;
        font-weight: 700 !important;
    }}
    .stButton > button[kind="primary"] {{
        background: linear-gradient(135deg, #d4a843, #b8912f) !important;
        color: #0c0c0c !important;
        border: none !important;
        font-weight: 700 !important;
    }}

    /* ── Inputs ── */
    .stSelectbox [data-baseweb="select"] > div,
    .stNumberInput input,
    .stTextInput input {{
        background: #141414 !important;
        border: 1px solid #252525 !important;
        border-radius: 8px !important;
        color: #e0e0e0 !important;
        font-family: 'RedRose', sans-serif;
    }}
    .stSelectbox [data-baseweb="select"] > div:focus-within {{
        border-color: #d4a843 !important;
    }}

    /* ── DataFrames ── */
    [data-testid="stDataFrame"] {{
        border: 1px solid #1e1e1e;
        border-radius: 10px;
        overflow: hidden;
    }}
    [data-testid="stDataFrame"] th {{
        background: #161616 !important;
        color: #d4a843 !important;
        font-family: 'RedRose', sans-serif;
        font-weight: 600;
        font-size: 0.8rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        border-bottom: 1px solid #252525;
    }}
    [data-testid="stDataFrame"] td {{
        background: #0e0e0e !important;
        color: #d8d8d8 !important;
        font-size: 0.85rem;
        border-bottom: 1px solid #161616;
    }}
    [data-testid="stDataFrame"] tr:hover td {{
        background: #161616 !important;
    }}

    /* ── Info / Warning / Success boxes ── */
    [data-testid="stAlert"] {{
        border-radius: 8px !important;
        font-family: 'RedRose', sans-serif;
        font-size: 0.88rem;
    }}
    .stAlert[data-baseweb="notification"] {{
        background: #141414 !important;
    }}

    /* ── Expander ── */
    [data-testid="stExpander"] {{
        background: #111 !important;
        border: 1px solid #1e1e1e !important;
        border-radius: 10px !important;
    }}
    [data-testid="stExpander"] summary {{
        font-family: 'RedRose', sans-serif;
        font-weight: 600;
        color: #aaa;
    }}

    /* ── Progress bar ── */
    .stProgress > div > div > div {{
        background: linear-gradient(90deg, #d4a843, #f0c060) !important;
        border-radius: 4px;
    }}

    /* ── Divider ── */
    hr {{ border-color: #1e1e1e !important; margin: 1rem 0; }}

    /* ── Custom Components ── */
    .sc-header {{
        display: flex; align-items: center; gap: 16px;
        padding: 12px 0 8px 0;
        border-bottom: 1px solid #1e1e1e;
        margin-bottom: 16px;
    }}
    .sc-page-title {{
        font-family: 'RedRose', sans-serif;
        font-weight: 700;
        font-size: 1.6rem;
        color: #f0f0f0;
        letter-spacing: 0.04em;
        flex: 1;
    }}
    .sc-page-subtitle {{
        font-family: 'RedRose', sans-serif;
        font-weight: 300;
        font-size: 0.8rem;
        color: #666;
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
    .tag-gold    {{ background: #1f1a0a; color: #d4a843; border: 1px solid #3a2f0a; }}
    .tag-green   {{ background: #0a1f0a; color: #22c55e; border: 1px solid #1a3a1a; }}
    .tag-red     {{ background: #1f0a0a; color: #ef4444; border: 1px solid #3a1a1a; }}
    .tag-gray    {{ background: #1a1a1a; color: #888;    border: 1px solid #2a2a2a; }}
    .tag-blue    {{ background: #0a0f1f; color: #60a5fa; border: 1px solid #1a2a3a; }}

    .signal-card {{
        background: #111; border: 1px solid #1e1e1e; border-radius: 10px;
        padding: 12px 16px; margin-bottom: 6px;
    }}
    .signal-card-bullish {{ border-left: 3px solid #22c55e !important; }}
    .signal-card-bearish {{ border-left: 3px solid #ef4444 !important; }}
    .signal-card-neutral {{ border-left: 3px solid #f59e0b !important; }}

    .crv-score-high {{ color: #d4a843; font-weight: 700; font-size: 1.1em; }}
    .crv-score-mid  {{ color: #888;    font-weight: 600; }}
    .crv-score-low  {{ color: #555;    font-weight: 400; }}

    .news-card {{
        background: #111; border: 1px solid #1e1e1e; border-radius: 8px;
        padding: 12px 16px; margin-bottom: 8px;
        transition: border-color 0.2s;
    }}
    .news-card:hover {{ border-color: #2a2a2a; }}
    .news-title {{ font-weight: 600; color: #e0e0e0; font-size: 0.92rem; line-height: 1.4; }}
    .news-meta  {{ font-size: 0.78rem; color: #555; margin-top: 4px; }}

    /* ── Checkbox ── */
    .stCheckbox label {{
        font-family: 'RedRose', sans-serif;
        font-size: 0.88rem;
        color: #aaa;
    }}
    .stCheckbox [data-testid="stCheckbox"] {{
        accent-color: #d4a843;
    }}

    /* ── Radio ── */
    .stRadio label {{
        font-family: 'RedRose', sans-serif;
        font-size: 0.85rem;
        color: #aaa;
    }}

    /* ── Slider ── */
    [data-testid="stSlider"] [data-baseweb="slider"] [data-testid="stTickBar"] {{
        color: #444;
    }}

    /* Gold line separator */
    .gold-line {{
        height: 2px;
        background: linear-gradient(90deg, #d4a843, transparent);
        margin: 12px 0;
        border: none;
    }}
    """
