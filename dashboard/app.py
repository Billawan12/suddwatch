"""
app.py — SuddWatch Operational Dashboard
Run: streamlit run dashboard/app.py
"""
import sys, json, io, csv, sqlite3, hashlib
from datetime import datetime
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).parent))
import db
import styles as s
st.sidebar.write("checkpoint 1: imports OK")

# ── Dynamic theme patcher ─────────────────────────────────────────────────
# Patches the static styles module constants based on user theme preference.
# Called once per rerun in MAIN before any page renders.
_LIGHT = {
    "BG":       "#f6f8fa",
    "CARD":     "#ffffff",
    "MUTED_BG": "#f0f2f5",
    "BORDER":   "#d0d7de",
    "FG":       "#24292f",
    "MUTED":    "#57606a",
    "PRIMARY":  "#0969da",
    "ACCENT":   "#0969da",
    "GLOBAL_CSS": "",  # patched separately
}
_DARK = {
    "BG":       "#0d1117",
    "CARD":     "#161b22",
    "MUTED_BG": "#1c2128",
    "BORDER":   "#21262d",
    "FG":       "#c9d1d9",
    "MUTED":    "#8b949e",
    "PRIMARY":  "#0ea5e9",
    "ACCENT":   "#0ea5e9",
}

# Store original dark GLOBAL_CSS so we can always regenerate from it
_ORIGINAL_GLOBAL_CSS = None

def apply_theme():
    """Patch styles.* constants to match current theme. Inject GLOBAL_CSS."""
    global _ORIGINAL_GLOBAL_CSS

    # Capture the original dark CSS once on first run
    if _ORIGINAL_GLOBAL_CSS is None:
        _ORIGINAL_GLOBAL_CSS = s.GLOBAL_CSS

    choice = st.session_state.get("theme_choice", "dark")

    if choice == "light":
        for k, v in _LIGHT.items():
            if k != "GLOBAL_CSS":
                setattr(s, k, v)
        # Build light CSS fresh from the stored dark original
        light_css = (_ORIGINAL_GLOBAL_CSS
            .replace("#0d1117", "#f6f8fa")   # bg
            .replace("#161b22", "#ffffff")   # card
            .replace("#1c2128", "#f0f2f5")   # muted_bg
            .replace("#21262d", "#d0d7de")   # border
            .replace("#30363d", "#c8d0d9")   # border2
            .replace("#c9d1d9", "#24292f")   # text
            .replace("#f0f6fc", "#1c2128")   # text_h
            .replace("#8b949e", "#57606a")   # text_m
            .replace("#010409", "#f0f2f5")   # sidebar bg
        )
        # Inject additional light-mode overrides
        light_css += """
<style>
/* ═══════════════════════════════════════════════════════════
   LIGHT MODE — COMPLETE OVERRIDE
   All text must be dark. All backgrounds must be light.
   ═══════════════════════════════════════════════════════════ */

/* Page and app backgrounds */
html, body,
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
[data-testid="stMainBlockContainer"],
.main, .block-container { background: #f6f8fa !important; }

/* ── Text — targeted, not nuclear ──────────────────────────── */
/* Main content text */
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stMarkdownContainer"] h4,
[data-testid="stMarkdownContainer"] h5,
[data-testid="stMarkdownContainer"] h6,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] td,
[data-testid="stMarkdownContainer"] th,
[data-testid="stMarkdownContainer"] blockquote,
[data-testid="stMarkdownContainer"] code { color: #24292f !important; }

/* Muted/secondary text */
[data-testid="stMarkdownContainer"] small,
[data-testid="stCaptionContainer"],
.stCaption { color: #57606a !important; }

/* Metric values */
[data-testid="stMetricValue"] { color: #24292f !important; }
[data-testid="stMetricDelta"] { color: #24292f !important; }
[data-testid="stMetricLabel"] { color: #57606a !important; }

/* Headers */
[data-testid="stHeading"] { color: #1c2128 !important; }

/* Label text on widgets */
[data-testid="stWidgetLabel"] { color: #24292f !important; }
[data-testid="stText"] { color: #24292f !important; }

/* st.write() and st.text() output */
[data-testid="stMarkdownContainer"] span:not([style*="color:"]) { color: #24292f !important; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: #f0f2f5 !important;
    border-right: 1px solid #d0d7de !important;
}
[data-testid="stSidebar"] p,
[data-testid="stSidebar"] span:not([style*="color:#0"]):not([style*="color:#2"]):not([style*="color:#e"]):not([style*="color:#f"]),
[data-testid="stSidebar"] div:not([style]) {
    color: #24292f !important;
}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { color: #24292f !important; }
[data-testid="stSidebar"] button {
    background: #f0f2f5 !important;
    color: #24292f !important;
    border: 1px solid #d0d7de !important;
}
[data-testid="stSidebar"] button:hover {
    background: #ffffff !important;
    border-color: #0969da !important;
    color: #0969da !important;
}

/* Buttons */
[data-testid="stButton"] button {
    background: #ffffff !important;
    color: #24292f !important;
    border: 1px solid #d0d7de !important;
}
[data-testid="stButton"] button:hover {
    background: #f0f2f5 !important;
    border-color: #0969da !important;
    color: #0969da !important;
}
[data-testid="stButton"] button[kind="primary"],
[data-testid="stFormSubmitButton"] button {
    background: #0969da !important;
    color: #ffffff !important;
    border: none !important;
}
[data-testid="stButton"] button[kind="primary"]:hover {
    background: #0550ae !important;
    color: #ffffff !important;
}

/* Tabs */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: #f0f2f5 !important;
    border-bottom: 2px solid #d0d7de !important;
}
button[data-baseweb="tab"] {
    background: transparent !important;
    color: #57606a !important;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: #0969da !important;
    border-bottom-color: #0969da !important;
}
[data-testid="stTabPanel"] { background: #f6f8fa !important; }

/* Inputs and forms */
input, textarea, [data-baseweb="input"] input,
[data-baseweb="textarea"] textarea {
    background: #ffffff !important;
    color: #24292f !important;
    border: 1px solid #d0d7de !important;
}
input::placeholder, textarea::placeholder { color: #8c959f !important; }
[data-testid="stTextInput"] label,
[data-testid="stSelectbox"] label,
[data-testid="stSlider"] label,
[data-testid="stRadio"] label,
[data-testid="stCheckbox"] label { color: #24292f !important; }

/* Selectbox / dropdowns */
[data-testid="stSelectbox"] > div > div,
[data-baseweb="select"] > div {
    background: #ffffff !important;
    border: 1px solid #d0d7de !important;
    color: #24292f !important;
}
[data-baseweb="popover"] [role="option"],
[data-baseweb="menu"] li {
    background: #ffffff !important;
    color: #24292f !important;
}
[data-baseweb="popover"] [role="option"]:hover {
    background: #f0f2f5 !important;
}

/* Slider */
[data-testid="stSlider"] div[role="slider"] {
    background: #0969da !important;
}
[data-testid="stSlider"] .css-1inwz65,
[data-testid="stSlider"] [class*="StyledThumb"] {
    background: #0969da !important;
}

/* Alerts and info boxes */
[data-testid="stAlert"] {
    background: #f0f2f5 !important;
    border: 1px solid #d0d7de !important;
    color: #24292f !important;
}
[data-testid="stAlert"] * { color: #24292f !important; }

/* Expanders */
[data-testid="stExpander"] {
    background: #ffffff !important;
    border: 1px solid #d0d7de !important;
}
[data-testid="stExpander"] summary { color: #24292f !important; }
[data-testid="stExpander"] summary:hover { color: #0969da !important; }

/* Tables */
[data-testid="stTable"] table { background: #ffffff !important; }
[data-testid="stTable"] th { background: #f0f2f5 !important; color: #24292f !important; }
[data-testid="stTable"] td { color: #24292f !important; border-color: #d0d7de !important; }

/* Dataframe */
[data-testid="stDataFrame"] { background: #ffffff !important; }

/* Download button */
[data-testid="stDownloadButton"] button {
    background: #f0f2f5 !important;
    color: #24292f !important;
    border: 1px solid #d0d7de !important;
}

/* Dividers */
hr { border-color: #d0d7de !important; }

/* Plotly charts — backgrounds */
.js-plotly-plot .plotly .bg { fill: #ffffff !important; }
.js-plotly-plot .plotly .gridlayer path { stroke: #d0d7de !important; }
.js-plotly-plot .plotly .xtick text,
.js-plotly-plot .plotly .ytick text { fill: #24292f !important; }

/* Folium map frame */
iframe { border: 1px solid #d0d7de !important; border-radius: 8px !important; }

/* Spinner */
[data-testid="stSpinner"] { color: #24292f !important; }

/* Scrollbar (webkit) */
::-webkit-scrollbar { background: #f0f2f5 !important; }
::-webkit-scrollbar-thumb { background: #d0d7de !important; border-radius: 4px; }

</style>"""
        s.GLOBAL_CSS = light_css
    else:
        # Restore original dark values
        for k, v in _DARK.items():
            setattr(s, k, v)
        s.GLOBAL_CSS = _ORIGINAL_GLOBAL_CSS

# ── Page config ───────────────────────────────────────────────
st.set_page_config(page_title="SuddWatch", layout="wide",
                   initial_sidebar_state="expanded", page_icon="🌊")

# ── Init database ─────────────────────────────────────────────
db.init_db()

st.sidebar.write("checkpoint 2: constants OK")
# ── Cached DB accessors — TTL 60s so data stays fresh ─────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def _cached_active_event():       return db.get_active_event() or {}
@st.cache_data(ttl=60, show_spinner=False)
def _cached_villages(evt_id):     return db.get_villages(evt_id)
@st.cache_data(ttl=60, show_spinner=False)
def _cached_roads():              return db.get_roads()
@st.cache_data(ttl=60, show_spinner=False)
def _cached_health_facilities():  return db.get_health_facilities()
@st.cache_data(ttl=60, show_spinner=False)
def _cached_alerts():             return db.get_alerts()
@st.cache_data(ttl=60, show_spinner=False)
def _cached_data_sources():       return db.get_data_sources()
@st.cache_data(ttl=60, show_spinner=False)
def _cached_state_breakdown():    return db.get_state_breakdown()
@st.cache_data(ttl=60, show_spinner=False)
def _cached_all_events():         return db.get_all_events()
@st.cache_data(ttl=60, show_spinner=False)
def _cached_season_monthly():     return db.get_season_monthly()
@st.cache_data(ttl=120, show_spinner=False)
def _cached_performance_rows():   return db.get_performance_rows()
@st.cache_data(ttl=60, show_spinner=False)
def _cached_download_history():   return db.get_download_history()
# Note: s.GLOBAL_CSS is injected inside main() AFTER apply_theme()
# so it always reflects the current theme choice.

# ── Auto-refresh ──────────────────────────────────────────────
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=60_000, key="autorefresh")
except ImportError:
    pass  # optional dependency

# ── Session state ─────────────────────────────────────────────
_defaults = {
    "page": "Home", "hist_state": "All",
    "hist_min_iou": 0.65, "hist_min_pop": 0,
    "export_scope": "Single Event", "export_fmt": "GeoJSON",
    "export_layers": {"Flood Extent Polygon","Affected Villages","Health Facilities at Risk"},
    "export_events": {"EVT-2025-047"}, "export_done": False,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ════════════════════════════════════════════════════════════
# AUTH LAYER — Landing page, sign-in, access requests
# ════════════════════════════════════════════════════════════

THEMES = {
    "dark": {
        "bg":       "#0d1117", "card":    "#161b22", "card2":   "#111927",
        "sidebar":  "#010409", "border":  "#21262d", "border2": "#30363d",
        "text":     "#c9d1d9", "text_h":  "#f0f6fc", "text_m":  "#8b949e",
        "accent":   "#0ea5e9", "accent2": "#0284c7",
        "success":  "#22c55e", "warning": "#f59e0b", "danger":  "#ef4444",
        "purple":   "#a855f7", "teal":    "#14b8a6",
        "plot_bg":  "#161b22", "plot_paper": "#0d1117",
        "input_bg": "#161b22", "topbar":  "#010409",
        "map_tile": "CartoDB dark_matter",
    },
    "light": {
        "bg":       "#f6f8fa", "card":    "#ffffff", "card2":   "#f0f2f5",
        "sidebar":  "#f0f2f5", "border":  "#d0d7de", "border2": "#b8c0cc",
        "text":     "#24292f", "text_h":  "#1c2128", "text_m":  "#57606a",
        "accent":   "#0969da", "accent2": "#0550ae",
        "success":  "#1a7f37", "warning": "#9a6700", "danger":  "#cf222e",
        "purple":   "#6639ba", "teal":    "#0f766e",
        "plot_bg":  "#ffffff", "plot_paper": "#f6f8fa",
        "input_bg": "#ffffff", "topbar":  "#f0f2f5",
        "map_tile": "OpenStreetMap",
    },
}

def get_theme():
    choice = st.session_state.get("theme_choice", "dark")
    return THEMES.get(choice if choice != "auto" else "dark", THEMES["dark"])

def css(t):
    return f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Barlow+Condensed:wght@600;700;800&family=DM+Mono:wght@400;500&display=swap');
html,body,[data-testid="stApp"]{{background:{t['bg']}!important;color:{t['text']}!important;font-family:'Inter',sans-serif!important;font-size:14px!important;}}
#MainMenu,footer,header,[data-testid="stToolbar"],[data-testid="stDecoration"]{{visibility:hidden!important;display:none!important;}}
[data-testid="stSidebar"]{{background:{t['sidebar']}!important;border-right:1px solid {t['border']}!important;min-width:230px!important;max-width:230px!important;}}
[data-testid="stSidebarContent"]{{padding:0!important;}}
[data-testid="stSidebar"] *{{color:{t['text_m']}!important;}}
[data-testid="stMainBlockContainer"],.block-container{{padding:0!important;max-width:100%!important;}}
h1,h2,h3{{font-family:'Barlow Condensed',sans-serif!important;color:{t['text_h']}!important;letter-spacing:.04em!important;}}
[data-testid="stRadio"] label{{font-family:'Inter',sans-serif!important;font-size:14px!important;color:{t['text_m']}!important;padding:8px 16px!important;display:flex!important;align-items:center!important;gap:8px!important;border-radius:6px!important;cursor:pointer!important;border-left:3px solid transparent!important;}}
[data-testid="stRadio"] label:hover{{color:{t['text']}!important;background:rgba(128,128,128,0.06)!important;}}
[data-testid="stRadio"] div[data-checked="true"] label,[data-testid="stRadio"] label[aria-checked="true"]{{color:{t['accent']}!important;border-left-color:{t['accent']}!important;background:rgba(14,165,233,0.07)!important;font-weight:500!important;}}
[data-testid="stTextInput"] input,[data-testid="stDateInput"] input,[data-testid="stNumberInput"] input{{background:{t['input_bg']}!important;border:1px solid {t['border2']}!important;color:{t['text']}!important;font-family:'Inter',sans-serif!important;font-size:14px!important;border-radius:6px!important;padding:9px 12px!important;}}
[data-testid="stSelectbox"] > div{{background:{t['input_bg']}!important;border:1px solid {t['border2']}!important;border-radius:6px!important;font-size:14px!important;}}
[data-testid="stButton"] button,[data-testid="stDownloadButton"] button{{background:{t['card']}!important;border:1px solid {t['border2']}!important;color:{t['text']}!important;font-family:'Inter',sans-serif!important;font-size:14px!important;border-radius:6px!important;padding:9px 16px!important;transition:all .15s!important;}}
[data-testid="stButton"] button:hover,[data-testid="stDownloadButton"] button:hover{{border-color:{t['accent']}!important;color:{t['accent']}!important;}}
[data-testid="stTabs"] [role="tablist"]{{border-bottom:1px solid {t['border']}!important;background:transparent!important;}}
[data-testid="stTabs"] [role="tab"]{{background:transparent!important;border:none!important;border-bottom:2px solid transparent!important;color:{t['text_m']}!important;font-family:'Inter',sans-serif!important;font-size:14px!important;padding:9px 18px!important;border-radius:0!important;}}
[data-testid="stTabs"] [role="tab"][aria-selected="true"]{{color:{t['accent']}!important;border-bottom-color:{t['accent']}!important;font-weight:500!important;}}
[data-testid="stExpander"]{{background:{t['card']}!important;border:1px solid {t['border']}!important;border-radius:8px!important;}}
[data-testid="stExpander"] summary{{color:{t['text']}!important;font-family:'Inter',sans-serif!important;font-size:14px!important;font-weight:500!important;}}
[data-testid="stCheckbox"] label{{font-family:'Inter',sans-serif!important;font-size:14px!important;color:{t['text']}!important;}}
[data-testid="stInfo"]{{background:{t['card']}!important;border-left:3px solid {t['accent']}!important;color:{t['text_m']}!important;font-size:14px!important;border-radius:8px!important;}}
hr{{border-color:{t['border']}!important;}}
</style>"""

# ════════════════════════════════════════════════════════════
# UI HELPERS
# ════════════════════════════════════════════════════════════
BADGE_STYLES = {
    "red":   ("#3d0f0f","#f85149"), "green": ("#0f2d1f","#3fb950"),
    "amber": ("#2d1f00","#d29922"), "blue":  ("#0a1929","#58a6ff"),
    "cyan":  ("#001f2d","#0ea5e9"), "grey":  ("#21262d","#8b949e"),
}

def badge(text, colour="grey"):
    bg, fg = BADGE_STYLES.get(colour, BADGE_STYLES["grey"])
    return (f"<span style='background:{bg};color:{fg};font-family:DM Mono,monospace;"
            f"font-size:12px;font-weight:600;padding:3px 10px;border-radius:4px;"
            f"border:1px solid {fg}44;white-space:nowrap;'>{text}</span>")

def lbl(text, col="#8b949e"):
    return (f"<span style='font-family:Inter,sans-serif;font-size:11px;"
            f"letter-spacing:.07em;text-transform:uppercase;color:{col};font-weight:600;'>{text}</span>")

def card(content, t, padding="14px 16px"):
    return (f"<div style='background:{t['card']};border:1px solid {t['border']};"
            f"border-radius:8px;padding:{padding};'>{content}</div>")

def card_header(title, t, right=""):
    r = f"<span style='font-size:13px;color:{t['text_m']};'>{right}</span>" if right else ""
    return (f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"padding-bottom:10px;border-bottom:1px solid {t['border']};margin-bottom:12px;'>"
            f"<span style='font-family:Barlow Condensed,sans-serif;font-size:15px;"
            f"letter-spacing:.07em;text-transform:uppercase;color:{t['text_h']};font-weight:700;'>{title}</span>{r}</div>")

def topbar(t, last_evt="—", user_info=""):
    ustr = f"<span style='font-size:13px;color:{t['text_m']};margin-right:16px;'>{user_info}</span>" if user_info else ""
    st.markdown(
        f"<div style='background:{t['topbar']};border-bottom:1px solid {t['border']};"
        f"padding:0 20px;height:52px;display:flex;align-items:center;justify-content:space-between;'>"
        f"<div style='display:flex;align-items:center;gap:12px;'>"
        f"<svg width='20' height='20' viewBox='0 0 28 28' fill='none'>"
        f"<path d='M14 4C14 4 8 11 8 16C8 19.3 10.7 22 14 22C17.3 22 20 19.3 20 16C20 11 14 4 14 4Z' fill='{t['accent']}' opacity='.9'/>"
        f"<path d='M3 23Q7 19.5 11 23Q15 26.5 19 23Q23 19.5 27 23' fill='none' stroke='{t['accent']}' stroke-width='1.6' stroke-linecap='round' opacity='.6'/>"
        f"</svg>"
        f"<span style='font-family:Barlow Condensed,sans-serif;font-size:20px;font-weight:800;"
        f"color:{t['text_h']};letter-spacing:.07em;'>SUDDWATCH</span>"
        f"<span style='color:{t['border2']};'>|</span>"
        f"<span style='font-size:13px;color:{t['text_m']};'>Operational Flood Detection</span></div>"
        f"<div style='display:flex;align-items:center;'>{ustr}"
        f"<span style='font-size:13px;color:{t['text_m']};'>Last event: "
        f"<strong style='color:{t['accent']};font-family:DM Mono,monospace;'>{last_evt}</strong></span></div></div>",
        unsafe_allow_html=True,
    )

def breadcrumb(text, t):
    st.markdown(
        f"<div style='padding:7px 20px;font-size:13px;color:{t['text_m']};"
        f"border-bottom:1px solid {t['border']};'>{text}</div>",
        unsafe_allow_html=True,
    )

def context_box(text, t):
    st.markdown(
        f"<div style='margin:10px 20px 0;padding:12px 16px;background:{t['card']};"
        f"border:1px solid {t['border']};border-left:4px solid {t['accent']};border-radius:8px;"
        f"font-size:14px;color:{t['text_m']};line-height:1.7;'>{text}</div>",
        unsafe_allow_html=True,
    )

def kpi_strip(items, t):
    cols = st.columns(len(items))
    for col, (title, value, sub, tip) in zip(cols, items):
        tip_html = (f"<div style='font-size:12px;color:{t['text_m']};margin-top:5px;"
                    f"font-style:italic;line-height:1.5;'>ℹ️ {tip}</div>") if tip else ""
        with col:
            st.markdown(
                card(
                    f"<div style='font-size:11px;letter-spacing:.07em;text-transform:uppercase;"
                    f"color:{t['text_m']};margin-bottom:6px;font-weight:600;'>{title}</div>"
                    f"<div style='font-family:Barlow Condensed,sans-serif;font-size:26px;"
                    f"font-weight:700;line-height:1.1;margin-bottom:4px;'>{value}</div>"
                    f"<div style='font-size:13px;color:{t['text_m']};'>{sub}</div>{tip_html}",
                    t, padding="14px 16px"
                ),
                unsafe_allow_html=True,
            )

def table_wrap(hdr, rows):
    return (f"<table style='width:100%;border-collapse:collapse;'>"
            f"<thead><tr>{hdr}</tr></thead><tbody>{rows}</tbody></table>")

def th(txt, t, align="left"):
    return (f"<th style='padding:7px 9px;font-size:12px;font-weight:600;letter-spacing:.04em;"
            f"color:{t['text_m']};border-bottom:1px solid {t['border2']};text-align:{align};'>{txt}</th>")

def td(txt, t, colour=None, align="left"):
    return (f"<td style='padding:7px 9px;font-size:13px;color:{colour or t['text']};"
            f"border-bottom:1px solid {t['border']};text-align:{align};'>{txt}</td>")

def pl(t):
    return dict(
        paper_bgcolor=t['plot_paper'], plot_bgcolor=t['plot_bg'],
        font=dict(family="Inter, sans-serif", size=13, color=t['text_m']),
        margin=dict(l=50, r=20, t=32, b=44),
        xaxis=dict(gridcolor=t['border'], linecolor=t['border2'], tickfont=dict(size=12)),
        yaxis=dict(gridcolor=t['border'], linecolor=t['border2'], tickfont=dict(size=12)),
    )

# ════════════════════════════════════════════════════════════
# GLOSSARY
# ════════════════════════════════════════════════════════════
GLOSSARY = {
    "IoU": ("Intersection over Union", "Measures how accurately the flood area was detected. Scores above 0.65 are good. 1.0 = perfect detection."),
    "SAR": ("Synthetic Aperture Radar", "A satellite sensor using radar waves that penetrate clouds and work at night — essential for South Sudan's rainy season."),
    "Sentinel-1": ("Sentinel-1 Satellite", "A free ESA satellite passing over South Sudan every 6 days, providing the radar images SuddWatch uses."),
    "SLA": ("Service Level Agreement", "The maximum allowed time from satellite pass to alert delivery. SuddWatch targets under 60 minutes."),
    "NFR": ("Non-Functional Requirement", "A performance standard: NFR1 = latency ≤ 60 min, NFR2 = IoU > 0.65, NFR3 = delivery > 95%."),
    "ha": ("Hectares", "Unit of area. 1 ha ≈ one football pitch. 1,000 ha ≈ 10 km²."),
    "Latency": ("Alert Latency", "Time from satellite pass to alert delivery, including download, processing, detection, and dispatch."),
    "Twilio": ("Twilio SMS Service", "The service SuddWatch uses to deliver SMS alerts to any phone — no internet required by the recipient."),
    "WorldPop": ("WorldPop Population Data", "A satellite-based dataset estimating population per 100m grid. SuddWatch loaded 13.1M records for South Sudan."),
    "OSM": ("OpenStreetMap", "Free community-built map data. SuddWatch uses it for roads, health facilities, and village boundaries."),
    "SNAP": ("ESA SNAP Toolbox", "Free ESA software that processes raw Sentinel-1 images into analysis-ready data."),
    "GeoJSON": ("GeoJSON Format", "A standard file format for geographic data, compatible with QGIS, ArcGIS, and web mapping tools."),
    "GeoTIFF": ("GeoTIFF Raster", "A satellite image file with geographic coordinates. The flood mask output uses this format (1=flooded, 0=dry)."),
}

def glossary_panel(t):
    with st.expander("📖 Glossary — plain-language explanations of technical terms", expanded=True):
        st.markdown(
            f"<div style='font-size:14px;color:{t['text_m']};margin-bottom:12px;line-height:1.6;'>"
            f"Every technical term used in SuddWatch explained in plain language.</div>",
            unsafe_allow_html=True,
        )
        rows = ""
        for k, (short, full) in GLOSSARY.items():
            rows += (f"<div style='padding:10px 0;border-bottom:1px solid {t['border']};'>"
                     f"<div style='font-weight:600;color:{t['accent']};font-size:14px;margin-bottom:4px;'>"
                     f"{k} <span style='font-weight:400;color:{t['text_m']};font-size:13px;'>— {short}</span></div>"
                     f"<div style='font-size:13px;color:{t['text']};line-height:1.6;'>{full}</div></div>")
        st.markdown(f"<div style='max-height:340px;overflow-y:auto;'>{rows}</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# MAP
# ════════════════════════════════════════════════════════════
try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_OK = True
except ImportError:
    FOLIUM_OK = False

def render_map(t):
    if FOLIUM_OK:
        tile = "CartoDB dark_matter" if t["bg"] == "#0d1117" else "OpenStreetMap"
        m = folium.Map(location=[8.5, 31.5], zoom_start=6, tiles=tile, control_scale=True)
        for zone in [
            {"name": "Jonglei Flood Zone", "coords": [[7.8,31.5],[8.0,32.5],[7.5,33.0],[7.0,32.5],[7.2,31.3]]},
            {"name": "Unity Flood Zone",   "coords": [[9.0,29.5],[9.5,30.5],[9.0,31.0],[8.5,30.5],[8.6,29.6]]},
            {"name": "Upper Nile Zone",    "coords": [[9.8,32.0],[10.5,32.8],[10.3,33.5],[9.7,33.2],[9.5,32.3]]},
        ]:
            folium.Polygon(locations=zone["coords"],
                popup=folium.Popup(f"<b>{zone['name']}</b><br>Active flood extent", max_width=200),
                tooltip=zone["name"], color="#0ea5e9", fill=True,
                fill_color="#0ea5e9", fill_opacity=0.22, weight=2, dash_array="6,4").add_to(m)
        icon_map = {"red":("red","exclamation-sign"),"orange":("orange","warning-sign"),"green":("green","ok-sign")}
        for name, lat, lon, rc, msg in [
            ("Malakal",9.53,31.66,"green","Low risk — monitor"),
            ("Bentiu",9.24,29.80,"orange","Medium risk — alert"),
            ("Bor",6.21,31.56,"red","HIGH RISK — evacuate"),
            ("Akobo",7.78,33.00,"orange","Medium risk — alert"),
            ("Leer",8.30,30.14,"red","HIGH RISK — evacuate"),
            ("Nasir",8.59,33.07,"orange","Medium risk — alert"),
            ("Twic East",7.50,32.10,"green","Low risk — monitor"),
        ]:
            ic, ig = icon_map[rc]
            folium.Marker([lat, lon],
                popup=folium.Popup(f"<b>{name}</b><br><span style='color:{'#f85149' if rc=='red' else '#d29922' if rc=='orange' else '#3fb950'};'>{msg}</span>", max_width=200),
                tooltip=f"{name} — {msg}",
                icon=folium.Icon(color=ic, icon=ig, prefix="glyphicon")).add_to(m)
        for hname, hlat, hlon in [
            ("Malakal Teaching Hospital",9.55,31.64),
            ("Bentiu State Hospital",9.26,29.82),
            ("Bor Civil Hospital",6.20,31.54),
        ]:
            folium.Marker([hlat, hlon],
                popup=folium.Popup(f"<b>🏥 {hname}</b><br><span style='color:#f85149;'>AT RISK</span>", max_width=200),
                tooltip=f"🏥 {hname} — at risk",
                icon=folium.Icon(color="red", icon="plus", prefix="glyphicon")).add_to(m)
        legend = """<div style="position:fixed;bottom:24px;left:24px;z-index:9999;
            background:rgba(22,27,34,0.94);border:1px solid #30363d;border-radius:8px;
            padding:14px 18px;font-family:Inter,sans-serif;font-size:13px;color:#c9d1d9;
            min-width:200px;">
          <div style="font-family:DM Mono,monospace;font-weight:600;font-size:11px;
            letter-spacing:.08em;text-transform:uppercase;color:#8b949e;margin-bottom:12px;">
            Map Legend</div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:7px;">
            <div style="width:14px;height:3px;background:#0ea5e9;border-radius:2px;"></div>
            Flood extent polygon</div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:7px;">
            <div style="width:10px;height:10px;border-radius:50%;background:#ef4444;"></div>
            High risk — evacuate</div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:7px;">
            <div style="width:10px;height:10px;border-radius:50%;background:#f59e0b;"></div>
            Medium risk — alert</div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:7px;">
            <div style="width:10px;height:10px;border-radius:50%;background:#22c55e;"></div>
            Low risk — monitor</div>
          <div style="display:flex;align-items:center;gap:8px;">
            <div style="width:10px;height:10px;border-radius:2px;background:#ef4444;opacity:.7;"></div>
            Health facility at risk</div>
          </div>"""
        m.get_root().html.add_child(folium.Element(legend))
        st_folium(m, height=680, use_container_width=True, returned_objects=[])
    else:
        st.info("💡 Install `folium` and `streamlit-folium` for the interactive OpenStreetMap.")

# ════════════════════════════════════════════════════════════
# AUTH — Demo credentials (replace with real DB in production)
# ════════════════════════════════════════════════════════════
DEMO_USERS = {
    "admin@suddwatch.org": {"password": "admin123", "role": "Admin",  "name": "System Administrator"},
    "coord@ocha.org":      {"password": "ocha2025",  "role": "User",   "name": "OCHA Coordinator"},
    "analyst@reach.org":   {"password": "reach2025", "role": "User",   "name": "REACH Analyst"},
}

# ── Auth database (separate from pipeline DB) ─────────────────────────────
AUTH_DB  = Path(__file__).parent / "auth.db"

def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()

def init_auth_db():
    """Create users and access_requests tables; seed demo accounts."""
    con = sqlite3.connect(AUTH_DB)
    cur = con.cursor()
    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT    UNIQUE NOT NULL,
            name        TEXT    NOT NULL,
            role        TEXT    NOT NULL DEFAULT 'User',
            pw_hash     TEXT    NOT NULL,
            active      INTEGER NOT NULL DEFAULT 1,
            created_at  TEXT    DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS access_requests (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            org         TEXT NOT NULL,
            email       TEXT NOT NULL,
            role        TEXT NOT NULL DEFAULT 'User',
            pw_hash     TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            submitted_at TEXT DEFAULT (datetime('now'))
        );
    """)
    # Seed/update demo users — always ensure correct password hash
    for email, d in DEMO_USERS.items():
        cur.execute(
            "INSERT OR IGNORE INTO users (email, name, role, pw_hash) VALUES (?,?,?,?)",
            (email, d["name"], d["role"], _hash(d["password"]))
        )
        # Always update hash in case it changed (e.g. hashing algorithm changed)
        cur.execute(
            "UPDATE users SET pw_hash=?, active=1 WHERE email=?",
            (_hash(d["password"]), email)
        )
    con.commit()
    con.close()

def auth_login(email: str, password: str):
    """Return user dict on success, None on failure."""
    em = email.strip().lower()
    # 1. Check demo accounts directly (always works, no DB needed)
    demo = DEMO_USERS.get(em)
    if demo and demo["password"] == password:
        return {"email": em, "name": demo["name"], "role": demo["role"]}
    # 2. Check auth.db for registered users
    try:
        con = sqlite3.connect(AUTH_DB)
        row = con.execute(
            "SELECT name, role FROM users WHERE lower(email)=? AND pw_hash=? AND active=1",
            (em, _hash(password))
        ).fetchone()
        con.close()
        if row:
            return {"email": em, "name": row[0], "role": row[1]}
    except Exception:
        pass
    return None

def auth_login_by_email(email: str):
    """Restore user from email alone (used for URL-based session restore)."""
    import sqlite3 as _sq
    try:
        con = _sq.connect(AUTH_DB)
        row = con.execute(
            "SELECT name, role FROM users WHERE email=? AND active=1",
            (email.strip().lower(),)
        ).fetchone()
        con.close()
        if row:
            return {"email": email.strip().lower(), "name": row[0], "role": row[1]}
    except Exception:
        pass
    return None

def auth_request(name: str, org: str, email: str, role: str, password: str):
    """Submit an access request. Returns (ok, message)."""
    con = sqlite3.connect(AUTH_DB)
    # Check no existing user or pending request
    existing = con.execute(
        "SELECT 1 FROM users WHERE email=?", (email.strip().lower(),)
    ).fetchone()
    pending = con.execute(
        "SELECT 1 FROM access_requests WHERE email=? AND status='pending'",
        (email.strip().lower(),)
    ).fetchone()
    if existing:
        con.close()
        return False, "An account with that email already exists."
    if pending:
        con.close()
        return False, "A request for that email is already pending approval."
    con.execute(
        "INSERT INTO access_requests (name, org, email, role, pw_hash) VALUES (?,?,?,?,?)",
        (name, org, email.strip().lower(), role, _hash(password))
    )
    con.commit()
    con.close()
    return True, f"Request submitted for {name} ({org}). An administrator will activate your account within 24 hours."

def auth_get_requests():
    """Return all pending access requests."""
    con = sqlite3.connect(AUTH_DB)
    rows = con.execute(
        "SELECT id, name, org, email, role, submitted_at FROM access_requests WHERE status='pending' ORDER BY submitted_at DESC"
    ).fetchall()
    con.close()
    return rows

def auth_approve(req_id: int):
    """Approve a request — create user account and mark request approved."""
    con = sqlite3.connect(AUTH_DB)
    row = con.execute(
        "SELECT name, email, role, pw_hash FROM access_requests WHERE id=?", (req_id,)
    ).fetchone()
    if row:
        name, email, role, pw_hash = row
        con.execute(
            "INSERT OR IGNORE INTO users (email, name, role, pw_hash) VALUES (?,?,?,?)",
            (email, name, role, pw_hash)
        )
        con.execute(
            "UPDATE access_requests SET status='approved' WHERE id=?", (req_id,)
        )
        con.commit()
    con.close()

def auth_reject(req_id: int):
    """Reject a request."""
    con = sqlite3.connect(AUTH_DB)
    con.execute("UPDATE access_requests SET status='rejected' WHERE id=?", (req_id,))
    con.commit()
    con.close()

def auth_get_users():
    """Return all active users."""
    con = sqlite3.connect(AUTH_DB)
    rows = con.execute(
        "SELECT email, name, role, created_at FROM users WHERE active=1 ORDER BY role DESC, name"
    ).fetchall()
    con.close()
    return rows

def is_logged_in():  return st.session_state.get("logged_in", False)
def current_user():  return st.session_state.get("user", {})
def logout():
    for k in ["logged_in","user","auth_page"]:
        st.session_state.pop(k, None)

def page_landing(t):
    import streamlit.components.v1 as components
    from pathlib import Path
    html_path = Path(__file__).parent / "landing.html"

    # Hide ALL Streamlit chrome - full screen landing
    st.markdown("""<style>
#MainMenu,footer,header,[data-testid="stToolbar"],
[data-testid="stDecoration"],[data-testid="stStatusWidget"],
[data-testid="stBottom"],[data-testid="stBottomBlockContainer"],
[data-testid="stSidebar"]{display:none!important;}
[data-testid="stMainBlockContainer"],.block-container,
section[data-testid="stMain"]{
    padding:0!important;margin:0!important;max-width:100%!important;}
/* Fixed Sign In button overlay */
.sw-signin-overlay{
    position:fixed;top:18px;right:24px;z-index:999999;
}
</style>""", unsafe_allow_html=True)

    # Landing page iframe — pure display, no JS navigation needed
    try:
        html = html_path.read_text()
    except Exception:
        st.error("landing.html not found in dashboard/")
        return

    for tok, col in [
        ('__CA2__', t['card2']), ('__AC__', t['accent']),
        ('__SU__', t['success']), ('__WA__', t['warning']),
        ('__DA__', t['danger']), ('__BG__', t['bg']),
        ('__CA__', t['card']),   ('__BO__', t['border']),
        ('__B2__', t['border2']),('__TH__', t['text_h']),
        ('__TM__', t['text_m']), ('__TX__', t['text']),
    ]:
        html = html.replace(tok, col)

    # Neutralise the iframe signin buttons — they can't navigate parent
    # Just scroll to top so user sees the Streamlit Sign In button
    html = html.replace(
        "window.parent.postMessage({cmd:'signin'}, '*');",
        "window.scrollTo(0,0);"
    )

    components.html(html, height=100000, scrolling=True)

    # Fixed Sign In button - appears as overlay top-right
    st.markdown("""<style>
div[data-testid="stButton"][data-key="landing_signin"] {
    position: fixed !important;
    top: 18px !important;
    right: 24px !important;
    z-index: 999999 !important;
}
div[data-testid="stButton"][data-key="landing_signin"] button {
    background: #0ea5e9 !important;
    color: #fff !important;
    border: none !important;
    padding: 10px 24px !important;
    font-size: 15px !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
    cursor: pointer !important;
    box-shadow: 0 4px 16px rgba(14,165,233,.4) !important;
}
</style>""", unsafe_allow_html=True)
    if st.button("Sign In", key="landing_signin"):
        st.session_state["auth_page"] = "login"
        st.rerun()


def page_auth(t):
    ac=t['accent']; bg=t['bg']; ca=t['card']; ca2=t['card2']
    bo=t['border']; b2=t['border2']; th=t['text_h']; tm=t['text_m']
    da=t['danger']; su=t['success']

    # Full-page background
    st.markdown(f"""<style>
[data-testid="stApp"]{{background:{bg}!important;}}
[data-testid="stMainBlockContainer"],.block-container{{
  padding:0!important;margin:0!important;max-width:100%!important;}}
section[data-testid="stMain"]{{padding:0!important;}}
[data-testid="stSidebar"]{{display:none!important;}}
#MainMenu,footer,header,[data-testid="stToolbar"],
[data-testid="stDecoration"],[data-testid="stStatusWidget"],
[data-testid="stBottom"],[data-testid="stBottomBlockContainer"]{{
  display:none!important;}}
/* Tab styling */
[data-testid="stTabs"] [data-testid="stMarkdownContainer"] p{{margin:0;}}
button[data-baseweb="tab"]{{
  font-family:'Inter',sans-serif!important;
  font-size:15px!important;font-weight:500!important;
  color:{tm}!important;padding:12px 24px!important;
  border-bottom:2px solid transparent!important;background:none!important;}}
button[data-baseweb="tab"][aria-selected="true"]{{
  color:{ac}!important;border-bottom:2px solid {ac}!important;}}
[data-testid="stTabPanel"]{{padding:24px 0 0!important;}}
/* Input fields */
[data-testid="stTextInput"] input{{
  background:{ca2}!important;border:1px solid {b2}!important;
  border-radius:8px!important;color:{th}!important;
  font-size:15px!important;padding:10px 14px!important;}}
[data-testid="stTextInput"] input:focus{{
  border-color:{ac}!important;box-shadow:0 0 0 3px rgba(14,165,233,.12)!important;}}
[data-testid="stTextInput"] label{{
  color:{tm}!important;font-size:14px!important;font-weight:500!important;
  margin-bottom:6px!important;}}
/* Select/radio */
[data-testid="stSelectbox"] > div > div{{
  background:{ca2}!important;border:1px solid {b2}!important;
  border-radius:8px!important;color:{th}!important;}}
[data-testid="stRadio"] label{{color:{tm}!important;font-size:14px!important;}}
/* Primary button */
[data-testid="stButton"] button[kind="primary"]{{
  background:{ac}!important;border:none!important;border-radius:8px!important;
  font-size:15px!important;font-weight:600!important;
  padding:12px 0!important;letter-spacing:.01em!important;}}
[data-testid="stButton"] button[kind="primary"]:hover{{opacity:.88!important;}}
/* Secondary button */
[data-testid="stButton"] button[kind="secondary"]{{
  background:none!important;border:1px solid {b2}!important;
  border-radius:8px!important;color:{tm}!important;
  font-size:14px!important;padding:10px 0!important;}}
[data-testid="stButton"] button[kind="secondary"]:hover{{
  border-color:{ac}!important;color:{ac}!important;}}
/* Form submit button */
[data-testid="stFormSubmitButton"] button{{
  background:{ac}!important;border:none!important;border-radius:8px!important;
  font-size:15px!important;font-weight:600!important;
  padding:12px 0!important;width:100%!important;}}
[data-testid="stFormSubmitButton"] button:hover{{opacity:.88!important;}}
/* Error/success */
[data-testid="stAlert"]{{border-radius:8px!important;font-size:14px!important;}}
</style>""", unsafe_allow_html=True)

    # Centred layout
    _, mid, _ = st.columns([1, 1.6, 1])
    with mid:
        st.markdown("<div style='height:48px;'></div>", unsafe_allow_html=True)

        # Logo
        st.markdown(f"""
<div style='text-align:center;margin-bottom:32px;'>
  <div style='display:inline-flex;align-items:center;gap:10px;margin-bottom:8px;'>
    <svg width='32' height='32' viewBox='0 0 28 28' fill='none'>
      <path d='M14 4C14 4 8 11 8 16C8 19.3 10.7 22 14 22C17.3 22 20 19.3 20 16C20 11 14 4 14 4Z'
        fill='{ac}' opacity='.9'/>
      <path d='M3 23Q7 19.5 11 23Q15 26.5 19 23Q23 19.5 27 23'
        fill='none' stroke='{ac}' stroke-width='1.6' stroke-linecap='round' opacity='.6'/>
    </svg>
    <span style='font-family:Barlow Condensed,sans-serif;font-size:28px;
      font-weight:800;color:{th};letter-spacing:.08em;'>SUDDWATCH</span>
  </div>
  <div style='font-size:14px;color:{tm};letter-spacing:.02em;'>
    Flood Detection &amp; Alert System &mdash; Greater Upper Nile
  </div>
</div>""", unsafe_allow_html=True)

        # Card
        st.markdown(f"""<div style='background:{ca};border:1px solid {bo};
border-radius:14px;padding:32px 28px;'>""", unsafe_allow_html=True)

        tab_in, tab_up = st.tabs(["Sign In", "Request Access"])

        # ── SIGN IN ──────────────────────────────────────────────
        with tab_in:
            st.markdown(f"<p style='font-size:14px;color:{tm};margin-bottom:20px;'>"
                        "Enter your credentials to access the operational dashboard.</p>",
                        unsafe_allow_html=True)

            # st.form prevents reruns on every keystroke
            with st.form("signin_form", clear_on_submit=False):
                email    = st.text_input("Email address",
                    placeholder="you@organisation.org", key="li_email")
                password = st.text_input("Password", type="password",
                    placeholder="Your password", key="li_pw")
                submitted = st.form_submit_button("Sign in",
                    use_container_width=True)

            if submitted:
                user = auth_login(email, password)
                if user:
                    st.session_state["logged_in"] = True
                    st.session_state["user"] = user
                    st.session_state.pop("auth_page", None)
                    st.rerun()
                else:
                    st.error("Incorrect email or password.")

            # Demo credentials box
            st.markdown(f"""
<div style='margin-top:20px;padding:14px 16px;background:{bg};
  border:1px solid {bo};border-radius:8px;'>
  <div style='font-size:12px;font-family:DM Mono,monospace;
    color:{tm};letter-spacing:.06em;text-transform:uppercase;
    margin-bottom:10px;'>Demo accounts</div>
  <div style='font-size:13px;color:{tm};line-height:2;'>
    <span style='color:{th};font-weight:500;'>Admin</span>
    &nbsp;&nbsp;<code style='background:{ca2};padding:2px 7px;
    border-radius:4px;font-size:12px;'>admin@suddwatch.org</code>
    &nbsp;<code style='background:{ca2};padding:2px 7px;
    border-radius:4px;font-size:12px;'>admin123</code><br>
    <span style='color:{th};font-weight:500;'>User</span>
    &nbsp;&nbsp;&nbsp;&nbsp;<code style='background:{ca2};padding:2px 7px;
    border-radius:4px;font-size:12px;'>coord@ocha.org</code>
    &nbsp;<code style='background:{ca2};padding:2px 7px;
    border-radius:4px;font-size:12px;'>ocha2025</code>
  </div>
</div>""", unsafe_allow_html=True)

        # ── REQUEST ACCESS ────────────────────────────────────────
        with tab_up:
            st.markdown(f"<p style='font-size:14px;color:{tm};margin-bottom:20px;'>"
                        "New accounts are reviewed by an administrator before activation.</p>",
                        unsafe_allow_html=True)

            with st.form("signup_form", clear_on_submit=False):
                new_name  = st.text_input("Full name",
                    placeholder="Dr. Jane Doe", key="ru_name")
                new_org   = st.text_input("Organisation",
                    placeholder="UN OCHA / IFRC / MSF / REACH", key="ru_org")
                new_email = st.text_input("Work email",
                    placeholder="you@organisation.org", key="ru_email")
                new_role  = st.selectbox("Access level",
                    ["User — View operational data",
                     "Admin — Full system access"], key="ru_role")
                new_pw    = st.text_input("Password", type="password",
                    key="ru_pw")
                new_pw2   = st.text_input("Confirm password", type="password",
                    key="ru_pw2")
                submitted_up = st.form_submit_button("Submit request",
                    use_container_width=True)

            if submitted_up:
                if not all([new_name, new_org, new_email, new_pw]):
                    st.error("Please complete all required fields.")
                elif new_pw != new_pw2:
                    st.error("Passwords do not match.")
                elif "@" not in new_email:
                    st.error("Please enter a valid email address.")
                else:
                    ok, msg = auth_request(new_name, new_org, new_email, new_role, new_pw)
                    if ok:
                        st.success(msg)
                    else:
                        st.error(msg)

        st.markdown("</div>", unsafe_allow_html=True)

        # Back link
        st.markdown("<div style='height:16px;'></div>", unsafe_allow_html=True)
        if st.button("Back to home", key="btn_back",
                     use_container_width=True, type="secondary"):
            st.session_state.pop("auth_page", None)
            st.rerun()

        st.markdown("<div style='height:48px;'></div>", unsafe_allow_html=True)




# ── Plotly layout helper ──────────────────────────────────────
def _fig(h=220, **overrides):
    layout = dict(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor=s.CARD,
        font=dict(family="DM Mono, monospace", size=10, color=s.MUTED),
        margin=dict(t=8, r=8, b=36, l=36), height=h,
        xaxis=dict(gridcolor="rgba(48,54,61,0.8)", linecolor=s.BORDER,
                   tickfont=dict(size=10, color=s.MUTED)),
        yaxis=dict(gridcolor="rgba(48,54,61,0.8)", linecolor=s.BORDER,
                   tickfont=dict(size=10, color=s.MUTED)),
        legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)",
                    font=dict(size=10), orientation="h", y=-0.25),
    )
    layout.update(overrides)
    return layout

# ── SVG Map (pure HTML — no iframe, fills container natively) ─
MAP_HTML = """
<div style="position:relative;width:100%;padding-top:75%;
            background:#07111a;border:1px solid {s.BORDER};
            border-radius:4px;overflow:hidden;">
  <svg style="position:absolute;inset:0;width:100%;height:100%;opacity:0.08"
       xmlns="http://www.w3.org/2000/svg">
    <defs>
      <pattern id="g" width="40" height="40" patternUnits="userSpaceOnUse">
        <path d="M 40 0 L 0 0 0 40" fill="none" stroke="{s.PRIMARY}" stroke-width="0.5"/>
      </pattern>
    </defs>
    <rect width="100%" height="100%" fill="url(#g)"/>
  </svg>
  <svg style="position:absolute;inset:0;width:100%;height:100%"
       viewBox="0 0 560 420" preserveAspectRatio="xMidYMid meet"
       xmlns="http://www.w3.org/2000/svg">
    <polygon points="60,10 500,10 500,145 360,160 260,150 160,155 60,140"
             fill="{s.ACCENT}" fill-opacity="0.04"
             stroke="{s.ACCENT}" stroke-width="1" stroke-dasharray="5,3" opacity="0.6"/>
    <polygon points="20,130 180,125 200,150 195,310 160,340 20,330"
             fill="{s.PURPLE}" fill-opacity="0.05"
             stroke="{s.PURPLE}" stroke-width="1" stroke-dasharray="5,3" opacity="0.6"/>
    <polygon points="190,100 540,95 545,410 190,410"
             fill="{s.SUCCESS}" fill-opacity="0.03"
             stroke="{s.SUCCESS}" stroke-width="1" stroke-dasharray="5,3" opacity="0.5"/>
    <path d="M 300 10 C 290 50 310 90 295 135 C 278 185 265 220 270 270 C 275 315 260 355 265 410"
          fill="none" stroke="{s.PRIMARY}" stroke-width="4" opacity="0.7" stroke-linecap="round"/>
    <path d="M 500 60 C 450 70 400 80 360 100 C 330 115 305 125 295 135"
          fill="none" stroke="{s.PRIMARY}" stroke-width="2.5" opacity="0.5" stroke-linecap="round"/>
    <path d="M 20 200 C 60 195 100 200 140 210 C 180 220 240 230 270 250"
          fill="none" stroke="{s.PRIMARY}" stroke-width="2.5" opacity="0.5" stroke-linecap="round"/>
    <path d="M 270 270 C 290 290 310 310 305 350 C 300 380 295 395 295 410"
          fill="none" stroke="{s.PRIMARY}" stroke-width="3" opacity="0.5" stroke-linecap="round"/>
    <polygon points="240,55 380,50 410,110 340,130 220,120 215,80"
             fill="{s.ACCENT}" fill-opacity="0.22"
             stroke="{s.ACCENT}" stroke-width="1.5" stroke-dasharray="6,3"/>
    <polygon points="40,175 155,168 175,195 170,270 120,285 40,275"
             fill="{s.ACCENT}" fill-opacity="0.20"
             stroke="{s.ACCENT}" stroke-width="1.5" stroke-dasharray="6,3"/>
    <polygon points="245,175 390,165 430,210 420,305 360,340 280,325 245,270"
             fill="{s.ACCENT}" fill-opacity="0.18"
             stroke="{s.ACCENT}" stroke-width="1.5" stroke-dasharray="6,3"/>
    <line x1="280" y1="10" x2="280" y2="410" stroke="{s.MUTED}" stroke-width="1" stroke-dasharray="8,5" opacity="0.4"/>
    <line x1="20" y1="145" x2="545" y2="145" stroke="{s.MUTED}" stroke-width="1" stroke-dasharray="8,5" opacity="0.4"/>
    <circle cx="370" cy="90"  r="6" fill="{s.SUCCESS}" stroke="white" stroke-width="1.5"/>
    <text x="378" y="94"  fill="{s.FG}" font-size="9" font-family="DM Mono">Malakal</text>
    <circle cx="100" cy="205" r="6" fill="{s.WARNING}" stroke="white" stroke-width="1.5"/>
    <text x="108" y="209" fill="{s.FG}" font-size="9" font-family="DM Mono">Bentiu</text>
    <circle cx="320" cy="335" r="7" fill="{s.DANGER}"  stroke="white" stroke-width="1.5"/>
    <text x="330" y="340" fill="{s.FG}" font-size="9" font-family="DM Mono">Bor</text>
    <circle cx="460" cy="280" r="5" fill="{s.WARNING}" stroke="white" stroke-width="1.5"/>
    <text x="467" y="284" fill="{s.FG}" font-size="9" font-family="DM Mono">Akobo</text>
    <circle cx="480" cy="120" r="5" fill="{s.WARNING}" stroke="white" stroke-width="1.5"/>
    <text x="442" y="116" fill="{s.FG}" font-size="9" font-family="DM Mono">Nasir</text>
    <circle cx="130" cy="260" r="5" fill="{s.DANGER}"  stroke="white" stroke-width="1.5"/>
    <text x="138" y="264" fill="{s.FG}" font-size="9" font-family="DM Mono">Leer</text>
    <circle cx="390" cy="220" r="5" fill="{s.SUCCESS}" stroke="white" stroke-width="1.5"/>
    <text x="398" y="224" fill="{s.FG}" font-size="9" font-family="DM Mono">Twic E.</text>
    <g transform="translate(355,90)">
      <line x1="-5" y1="0" x2="5" y2="0" stroke="{s.DANGER}" stroke-width="2.5"/>
      <line x1="0" y1="-5" x2="0" y2="5" stroke="{s.DANGER}" stroke-width="2.5"/>
    </g>
    <g transform="translate(95,200)">
      <line x1="-5" y1="0" x2="5" y2="0" stroke="{s.DANGER}" stroke-width="2.5"/>
      <line x1="0" y1="-5" x2="0" y2="5" stroke="{s.DANGER}" stroke-width="2.5"/>
    </g>
    <g transform="translate(308,330)">
      <line x1="-5" y1="0" x2="5" y2="0" stroke="{s.DANGER}" stroke-width="2.5"/>
      <line x1="0" y1="-5" x2="0" y2="5" stroke="{s.DANGER}" stroke-width="2.5"/>
    </g>
    <text x="170" y="38" fill="{s.ACCENT}" font-size="10" font-family="Barlow Condensed, sans-serif"
          font-weight="700" letter-spacing="2" opacity="0.8">UPPER NILE</text>
    <text x="30" y="235" fill="{s.PURPLE}" font-size="10" font-family="Barlow Condensed, sans-serif"
          font-weight="700" letter-spacing="2" opacity="0.8"
          transform="rotate(-90,30,235)">UNITY</text>
    <text x="440" y="390" fill="{s.SUCCESS}" font-size="10" font-family="Barlow Condensed, sans-serif"
          font-weight="700" letter-spacing="2" opacity="0.8">JONGLEI</text>
  </svg>
  <div style="position:absolute;top:12px;left:12px;background:rgba(13,17,23,0.85);
              border:1px solid {s.BORDER};border-radius:4px;padding:4px 8px">
    <span style="font-family:'DM Mono',monospace;font-size:10px;color:{s.MUTED}">
      Greater Upper Nile — Jonglei · Unity · Upper Nile
    </span>
  </div>
  <div style="position:absolute;bottom:12px;left:12px;background:rgba(13,17,23,0.85);
              border:1px solid {s.BORDER};border-radius:4px;padding:8px 12px;
              display:flex;flex-direction:column;gap:5px">
    <div style="display:flex;align-items:center;gap:8px">
      <div style="width:14px;height:10px;border:1px dashed {s.ACCENT};
                  background:rgba(14,165,233,0.2);border-radius:2px"></div>
      <span style="font-family:'DM Mono',monospace;font-size:10px;color:{s.MUTED}">Flood extent</span>
    </div>
    <div style="display:flex;align-items:center;gap:8px">
      <div style="width:10px;height:10px;border-radius:50%;background:{s.DANGER}"></div>
      <span style="font-family:'DM Mono',monospace;font-size:10px;color:{s.MUTED}">High-risk</span>
    </div>
    <div style="display:flex;align-items:center;gap:8px">
      <div style="width:10px;height:10px;border-radius:50%;background:{s.WARNING}"></div>
      <span style="font-family:'DM Mono',monospace;font-size:10px;color:{s.MUTED}">Medium-risk</span>
    </div>
    <div style="display:flex;align-items:center;gap:8px">
      <div style="width:10px;height:10px;border-radius:50%;background:{s.SUCCESS}"></div>
      <span style="font-family:'DM Mono',monospace;font-size:10px;color:{s.MUTED}">Low-risk</span>
    </div>
    <div style="display:flex;align-items:center;gap:8px">
      <span style="color:{s.DANGER};font-size:12px;line-height:1">✕</span>
      <span style="font-family:'DM Mono',monospace;font-size:10px;color:{s.MUTED}">Health facility</span>
    </div>
  </div>
  <div style="position:absolute;bottom:12px;right:12px;background:rgba(13,17,23,0.85);
              border:1px solid {s.BORDER};border-radius:4px;padding:4px 8px;
              display:flex;align-items:center;gap:8px">
    <div style="width:48px;height:2px;background:rgba(230,237,243,0.6)"></div>
    <span style="font-family:'DM Mono',monospace;font-size:10px;color:{s.MUTED}">100 km</span>
  </div>

</div>
"""

# ════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════
def render_sidebar():
    _NAV_ICONS = {
        "Home":        """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>""",
        "History":     """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>""",
        "Performance": """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="20" x2="18" y2="10"/><line x1="12" y1="20" x2="12" y2="4"/><line x1="6" y1="20" x2="6" y2="14"/></svg>""",
        "Export":      """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>""",
        "Admin":       """<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>""",
    }

    user = st.session_state.get("sw_auth", {})
    role = user.get("role", "User")
    name = user.get("name", "User")
    email = user.get("email", "")
    initials = "".join(w[0].upper() for w in name.split()[:2])

    # Nav pages — Admin only shown to Admin role
    nav_pages = ["Home", "History", "Performance", "Export"]
    if role == "Admin":
        nav_pages.append("Admin")

    with st.sidebar:
        # ── Logo / brand ─────────────────────────────────
        st.markdown(f"""
<div style="padding:16px;border-bottom:1px solid {s.BORDER};">
  <div style="display:flex;align-items:center;gap:10px;">
    <div style="position:relative;width:36px;height:36px;border-radius:8px;
      background:rgba(14,165,233,0.1);border:1px solid rgba(14,165,233,0.25);
      display:flex;align-items:center;justify-content:center;flex-shrink:0;">
      <svg width="20" height="20" viewBox="0 0 28 28" fill="none">
        <path d="M14 4C14 4 8 11 8 16C8 19.3 10.7 22 14 22C17.3 22 20 19.3 20 16C20 11 14 4 14 4Z"
          fill="{s.ACCENT}" opacity=".9"/>
        <path d="M3 23Q7 19.5 11 23Q15 26.5 19 23Q23 19.5 27 23"
          fill="none" stroke="{s.ACCENT}" stroke-width="1.6" stroke-linecap="round" opacity=".6"/>
      </svg>
      <div style="position:absolute;bottom:-3px;right:-3px;width:8px;height:8px;
        border-radius:50%;background:{s.SUCCESS};border:1.5px solid {s.BG};"></div>
    </div>
    <div>
      <div style="font-family:'Barlow Condensed',sans-serif;font-size:16px;
        font-weight:700;color:{s.FG};letter-spacing:.05em;">SUDDWATCH</div>
      <div style="font-family:'DM Mono',monospace;font-size:9px;
        color:{s.MUTED};margin-top:1px;">Greater Upper Nile &middot; Flood Intel</div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

        # ── Navigation label ──────────────────────────────
        st.markdown(f"""
<div style="padding:14px 14px 4px;font-family:'DM Mono',monospace;font-size:10px;
  text-transform:uppercase;letter-spacing:.1em;color:{s.MUTED};">Navigation</div>""",
            unsafe_allow_html=True)

        # ── Nav buttons ───────────────────────────────────
        for pg in nav_pages:
            icon = _NAV_ICONS[pg]
            active = st.session_state.page == pg
            if active:
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:12px;"
                    f"background:rgba(14,165,233,.08);border-left:2px solid {s.ACCENT};"
                    f"padding:11px 16px;color:{s.ACCENT};font-family:Inter,sans-serif;"
                    f"font-size:14px;font-weight:500;border-radius:0 6px 6px 0;margin:1px 0;'>"
                    f"<span style='color:{s.ACCENT};'>{icon}</span>{pg}</div>",
                    unsafe_allow_html=True)
            else:
                if st.button(pg, key=f"nav_{pg}", use_container_width=True):
                    st.session_state.page = pg
                    st.session_state.export_done = False
                    st.rerun()

        # ── System status ─────────────────────────────────
        st.markdown(f"""
<div style="margin-top:20px;padding:14px 16px;border-top:1px solid {s.BORDER};
  border-bottom:1px solid {s.BORDER};">
  <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
    <div style="width:7px;height:7px;border-radius:50%;background:{s.SUCCESS};
      animation:pulse 1.5s ease-in-out infinite;flex-shrink:0;"></div>
    <span style="font-family:'Inter',sans-serif;font-size:12px;
      color:{s.MUTED};font-weight:500;">System operational</span>
  </div>
  <div style="font-family:'DM Mono',monospace;font-size:10px;
    color:{s.MUTED};line-height:1.6;">
    v2.4.1 &middot; Sudd Basin<br>
    Sentinel-1 &middot; 6-day pass
  </div>
</div>""", unsafe_allow_html=True)

        # ── Signed-in user ────────────────────────────────
        st.markdown(f"""
<div style="padding:14px 16px 8px;">
  <div style="font-family:'DM Mono',monospace;font-size:10px;
    text-transform:uppercase;letter-spacing:.1em;color:{s.MUTED};
    margin-bottom:10px;">Signed in as</div>
  <div style="display:flex;align-items:center;gap:10px;">
    <div style="width:32px;height:32px;border-radius:50%;
      background:rgba(14,165,233,.15);border:1px solid rgba(14,165,233,.25);
      display:flex;align-items:center;justify-content:center;
      font-family:'DM Mono',monospace;font-size:11px;
      font-weight:700;color:{s.ACCENT};flex-shrink:0;">{initials}</div>
    <div style="min-width:0;">
      <div style="font-size:13px;font-weight:500;color:{s.FG};
        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{name}</div>
      <div style="font-size:11px;color:{s.MUTED};
        white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{email}</div>
    </div>
  </div>
  <div style="margin-top:8px;">
    <span style="font-family:'DM Mono',monospace;font-size:10px;
      padding:2px 8px;border-radius:4px;font-weight:600;
      {'background:rgba(14,165,233,.12);color:' + s.ACCENT if role == 'Admin'
       else 'background:rgba(34,197,94,.1);color:' + s.SUCCESS};">{role}</span>
  </div>
</div>""", unsafe_allow_html=True)

        # ── Sign out ──────────────────────────────────────
        if st.button("Sign out", key="btn_signout", use_container_width=True):
            st.session_state.pop("sw_auth", None)
            st.rerun()


# ════════════════════════════════════════════════════════════
# TOPBAR
# ════════════════════════════════════════════════════════════
def render_topbar(last_evt: str):
    cl, cr = st.columns([4, 1])
    with cl:
        st.markdown(f"""
<div style="height:60px;display:flex;align-items:center;gap:12px;
  border-bottom:1px solid {s.BORDER};">
  <svg width="22" height="22" viewBox="0 0 28 28" fill="none">
    <path d="M14 4C14 4 8 11 8 16C8 19.3 10.7 22 14 22C17.3 22 20 19.3 20 16C20 11 14 4 14 4Z"
      fill="{s.ACCENT}" opacity=".9"/>
    <path d="M3 23Q7 19.5 11 23Q15 26.5 19 23Q23 19.5 27 23"
      fill="none" stroke="{s.ACCENT}" stroke-width="1.6" stroke-linecap="round" opacity=".6"/>
  </svg>
  <span style="font-family:'Barlow Condensed',sans-serif;font-size:20px;
    font-weight:700;color:{s.FG};letter-spacing:.04em;">SUDDWATCH</span>
  <span style="border-left:1px solid {s.BORDER};padding-left:12px;
    font-family:'DM Mono',monospace;font-size:11px;color:{s.MUTED}">
    Flood Detection &amp; Alert System &middot; Greater Upper Nile
  </span>
</div>""", unsafe_allow_html=True)

    with cr:
        cur_theme = st.session_state.get("theme_choice", "dark")
        theme_icon = "☀️" if cur_theme == "dark" else "🌙"
        theme_label = "Light mode" if cur_theme == "dark" else "Dark mode"

        st.markdown(f"""
<div style="height:60px;display:flex;align-items:center;justify-content:flex-end;
  gap:8px;border-bottom:1px solid {s.BORDER};padding-right:4px;">
  <span style="font-family:'DM Mono',monospace;font-size:11px;color:{s.MUTED};">
    Last event: <span style="color:{s.ACCENT};">{last_evt}</span>
  </span>
</div>""", unsafe_allow_html=True)

        # Three action buttons: Info | Theme | Refresh
        b1, b2, b3 = st.columns(3)
        with b1:
            if st.button("ⓘ", key="btn_info",
                         help="Show glossary — plain-language explanations of every technical term",
                         use_container_width=True):
                st.session_state["show_glossary"] = not st.session_state.get("show_glossary", False)
        with b2:
            if st.button(theme_icon, key="btn_theme",
                         help=theme_label,
                         use_container_width=True):
                st.session_state["theme_choice"] = "light" if cur_theme == "dark" else "dark"
                st.rerun()
        with b3:
            if st.button("⟳", key="btn_refresh",
                         help="Refresh data now",
                         use_container_width=True):
                st.rerun()

    # Glossary panel — shown inline below topbar when info button clicked
    if st.session_state.get("show_glossary", False):
        with st.expander("Glossary — plain-language explanations", expanded=True):
            rows = ""
            for k, (short, full) in GLOSSARY.items():
                rows += (
                    f"<div style='padding:10px 0;border-bottom:1px solid {s.BORDER};'>"
                    f"<div style='font-weight:600;color:{s.ACCENT};font-size:14px;"
                    f"margin-bottom:4px;'>{k} "
                    f"<span style='font-weight:400;color:{s.MUTED};font-size:13px;'>"
                    f"— {short}</span></div>"
                    f"<div style='font-size:13px;color:{s.FG};line-height:1.6;'>{full}</div>"
                    f"</div>"
                )
            st.markdown(
                f"<div style='max-height:320px;overflow-y:auto;padding:0 4px;'>"
                f"{rows}</div>",
                unsafe_allow_html=True
            )


def render_breadcrumb(text: str):
    st.markdown(f"""
    <div style="border-bottom:1px solid {s.BORDER};padding:8px 0;margin-bottom:16px">
      <span style="font-family:'DM Mono',monospace;font-size:11px;color:{s.MUTED}">{text}</span>
    </div>""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# PAGE — HOME
# ════════════════════════════════════════════════════════════

def render_sat_timeline():
    """Horizontal strip showing last 14 days of Sentinel-1 passes."""
    from datetime import datetime, timedelta
    import json
    from pathlib import Path

    today = datetime.now()
    days = []
    for i in range(13, -1, -1):
        d = today - timedelta(days=i)
        day_of_cycle = i % 6
        if day_of_cycle == 0:   status = "clean"
        elif day_of_cycle == 1: status = "partial"
        else:                   status = "none"
        days.append({"date": d.strftime("%b %d"), "status": status})

    registry = Path("data/downloaded_scenes.json")
    if registry.exists():
        try:
            with open(registry) as f:
                scenes = json.load(f)
            scene_dates = set()
            for scene in scenes:
                if isinstance(scene, dict):
                    dt = scene.get("date", scene.get("acquisition_date", ""))
                    if dt: scene_dates.add(dt[:10])
            for i, day in enumerate(days):
                d_str = (today - timedelta(days=13-i)).strftime("%Y-%m-%d")
                if d_str in scene_dates:
                    day["status"] = "clean"
        except Exception:
            pass

    STATUS_COLORS = {"clean": s.ACCENT, "partial": s.WARNING, "none": s.BORDER}
    bar_w, bar_gap, height = 6, 3, 28
    bars = ""
    for i, day in enumerate(days):
        x = i * (bar_w + bar_gap)
        color = STATUS_COLORS[day["status"]]
        bar_h = 20 if day["status"] == "clean" else (12 if day["status"] == "partial" else 5)
        y = height - bar_h - 4
        bars += (
            f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" rx="1" ' +
            f'fill="{color}" opacity="{0.9 if day["status"]=="clean" else 0.5}">' +
            f'<title>{day["date"]} — {day["status"]}</title></rect>'
        )

    total_w = len(days) * (bar_w + bar_gap)
    clean_ct = sum(1 for d in days if d["status"] == "clean")
    st.markdown(
        f'<div style="background:{s.CARD};border-bottom:1px solid {s.BORDER};' +
        f'padding:5px 20px;display:flex;align-items:center;gap:16px;">' +
        f'<span style="font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};' +
        f'text-transform:uppercase;letter-spacing:0.08em;white-space:nowrap;">' +
        f'Sentinel-1 passes · last 14 days</span>' +
        f'<svg viewBox="0 0 {total_w} {height}" height="{height}" style="flex:1;max-width:280px;" ' +
        f'xmlns="http://www.w3.org/2000/svg">{bars}</svg>' +
        f'<div style="display:flex;align-items:center;gap:10px;flex-shrink:0;">' +
        f'<span style="display:flex;align-items:center;gap:4px;">' +
        f'<span style="width:6px;height:14px;background:{s.ACCENT};border-radius:1px;display:inline-block;"></span>' +
        f'<span style="font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};">acquired</span></span>' +
        f'<span style="display:flex;align-items:center;gap:4px;">' +
        f'<span style="width:6px;height:8px;background:{s.WARNING};border-radius:1px;display:inline-block;"></span>' +
        f'<span style="font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};">partial</span></span>' +
        f'<span style="display:flex;align-items:center;gap:4px;">' +
        f'<span style="width:6px;height:5px;background:{s.BORDER};border-radius:1px;display:inline-block;"></span>' +
        f'<span style="font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};">no pass</span></span>' +
        f'<span style="font-family:DM Mono,monospace;font-size:10px;color:{s.ACCENT};">' +
        f'{clean_ct}/14</span></div></div>',
        unsafe_allow_html=True,
    )


def make_sparkline(values: list, color: str, width: int = 60, height: int = 20) -> str:
    """Tiny inline SVG sparkline for KPI cards."""
    if not values or len(values) < 2:
        return ""
    mn, mx = min(values), max(values)
    rng = mx - mn or 1
    pad = 2
    pts = []
    for i, v in enumerate(values):
        x = int(i * (width - 1) / (len(values) - 1))
        y = int(pad + (1 - (v - mn) / rng) * (height - 2 * pad))
        pts.append((x, y))
    path_d = " ".join(f"{'M' if i==0 else 'L'}{x},{y}" for i,(x,y) in enumerate(pts))
    fill_d = (
        f"M{pts[0][0]},{height} "
        + " ".join(f"L{x},{y}" for x,y in pts)
        + f" L{pts[-1][0]},{height} Z"
    )
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" ' +
        f'xmlns="http://www.w3.org/2000/svg" style="display:block;">' +
        f'<path d="{fill_d}" fill="{color}" opacity="0.12"/>' +
        f'<path d="{path_d}" fill="none" stroke="{color}" stroke-width="1.5" ' +
        f'stroke-linecap="round" stroke-linejoin="round"/>' +
        f'<circle cx="{pts[-1][0]}" cy="{pts[-1][1]}" r="2.5" ' +
        f'fill="{color}" stroke="white" stroke-width="1"/>' +
        f'</svg>'
    )

def page_home():
    event     = _cached_active_event()
    villages  = _cached_villages(event.get("id"))
    roads     = _cached_roads()
    hf        = _cached_health_facilities()
    alerts    = _cached_alerts()
    sources   = _cached_data_sources()
    breakdown = _cached_state_breakdown()

    # ── Hero banner — pulls from live DB ─────────────────────
    evt_id    = event.get("event_id",   "EVT-2025-047")
    evt_loc   = event.get("location",   "Bor South, Jonglei State")
    evt_ha    = event.get("flood_ha",   1200)
    evt_pop   = event.get("affected",   6637)
    evt_ts    = event.get("date_utc",   "2025-10-23 14:17 UTC")
    evt_iou   = event.get("iou",        0.71)
    evt_lat   = event.get("latency_min",45)

    from datetime import datetime, timezone
    _now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    st.markdown(f"""
<div style="position:relative;width:100%;height:230px;overflow:hidden;
  border-radius:8px;margin-bottom:16px;border:1px solid {s.BORDER};">
  <img src="https://media.vaticannews.va/media/content/dam-archive/vaticannews/agenzie/images/reuters/2019/11/02/08/1572678106776.JPG/_jcr_content/renditions/cq5dam.thumbnail.cropped.1500.844.jpeg"
    style="width:100%;height:100%;object-fit:cover;object-position:center 55%;
    display:block;filter:brightness(.38);"
    onerror="this.style.display='none'"/>
  <div style="position:absolute;inset:0;padding:24px 32px;
    display:flex;flex-direction:column;justify-content:space-between;">
    <div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;">
      <div style="display:flex;align-items:center;gap:8px;">
        <div style="width:7px;height:7px;border-radius:50%;background:{s.DANGER};
          animation:pulse 1.5s ease-in-out infinite;"></div>
        <span style="font-family:DM Mono,monospace;font-size:11px;
          color:{s.DANGER};letter-spacing:.08em;text-transform:uppercase;
          background:rgba(239,68,68,.12);padding:3px 10px;border-radius:4px;">
          Live — {evt_id}</span>
      </div>
      <span style="font-family:DM Mono,monospace;font-size:11px;
        color:rgba(255,255,255,.5);">Last updated: {_now}</span>
    </div>
    <div>
      <div style="font-family:Barlow Condensed,sans-serif;
        font-size:clamp(22px,3vw,36px);font-weight:700;color:#fff;
        line-height:1.05;margin-bottom:10px;
        text-shadow:0 2px 16px rgba(0,0,0,.6);">
        {evt_loc}<br>
        <span style="color:#7dd3fc;">{evt_ha:,} ha flooded &middot; {evt_pop:,} people at risk</span>
      </div>
      <div style="display:flex;gap:0;flex-wrap:wrap;">
        <span style="font-family:DM Mono,monospace;font-size:11px;
          color:rgba(255,255,255,.7);background:rgba(0,0,0,.35);
          padding:5px 14px;border-right:1px solid rgba(255,255,255,.15);">
          Detected: {evt_ts}</span>
        <span style="font-family:DM Mono,monospace;font-size:11px;
          color:rgba(255,255,255,.7);background:rgba(0,0,0,.35);
          padding:5px 14px;border-right:1px solid rgba(255,255,255,.15);">
          Alert latency: {evt_lat} min</span>
        <span style="font-family:DM Mono,monospace;font-size:11px;
          color:rgba(255,255,255,.7);background:rgba(0,0,0,.35);
          padding:5px 14px;border-right:1px solid rgba(255,255,255,.15);">
          Sentinel-1 IW GRD</span>
        <span style="font-family:DM Mono,monospace;font-size:11px;
          color:rgba(255,255,255,.7);background:rgba(0,0,0,.35);
          padding:5px 14px;">
          IoU: {evt_iou}</span>
      </div>
    </div>
  </div>
</div>""", unsafe_allow_html=True)

    # ── Real-time status bar ──────────────────────────────────
    from datetime import datetime, timezone
    _refresh_ts = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
    st.markdown(
        f"<div style='display:flex;align-items:center;justify-content:space-between;"
        f"padding:7px 14px;background:{s.CARD};border:1px solid {s.BORDER};"
        f"border-radius:6px;margin-bottom:12px;'>"
        f"<div style='display:flex;align-items:center;gap:8px;'>"
        f"<div style='width:6px;height:6px;border-radius:50%;background:{s.SUCCESS};"
        f"animation:pulse 1.5s ease-in-out infinite;'></div>"
        f"<span style='font-family:DM Mono,monospace;font-size:11px;color:{s.SUCCESS};'>"
        f"Live &middot; auto-refreshes every 60 seconds</span></div>"
        f"<span style='font-family:DM Mono,monospace;font-size:11px;color:{s.MUTED};'>"
        f"Last updated: {_refresh_ts}</span>"
        f"</div>",
        unsafe_allow_html=True
    )

    render_sat_timeline()
    cols = st.columns(6, gap="small")
    kpis = [
        ("TOTAL FLOOD EXTENT", "2,220 ha",   "across 3 states",   s.ACCENT),
        ("AFFECTED POPULATION","7,990",       "est. at risk",      s.WARNING),
        ("ACTIVE ALERTS",      "41",          "24h window",        s.DANGER),
        ("AVG ALERT LATENCY",  "45 min",      "vs 60 min SLA",     s.SUCCESS),
        ("DETECTION IOU",      "0.71",        "last acquisition",  s.SUCCESS),
        ("SEASON EVENTS",      "47",          "2025 flood season", s.FG),
    ]
    spark_data = {
        "TOTAL FLOOD EXTENT":  [980, 1100, 850, 1400, 1200, 2220],
        "AFFECTED POPULATION": [3800, 4200, 3100, 5500, 5000, 7990],
        "ACTIVE ALERTS":       [24, 31, 18, 38, 28, 41],
        "AVG ALERT LATENCY":   [52, 48, 44, 56, 50, 45],
        "DETECTION IOU":       [0.68, 0.71, 0.74, 0.66, 0.70, 0.71],
        "SEASON EVENTS":       [8, 10, 11, 9, 12, 47],
    }
    # Trend arrows — compare last two spark values
    def _trend(vals):
        if len(vals) < 2: return ""
        up = vals[-1] > vals[-2]
        col_t = s.SUCCESS if up else s.DANGER
        arrow = "&#8593;" if up else "&#8595;"
        return f"<span style='color:{col_t};font-size:13px;margin-left:4px;'>{arrow}</span>"

    for col, (label, value, sub, color) in zip(cols, kpis):
        spark_vals = spark_data.get(label, [])
        sparkline  = make_sparkline(spark_vals, color) if spark_vals else ""
        trend      = _trend(spark_vals)
        with col:
            col.markdown(
                f"<div style='background:{s.CARD};border:1px solid {s.BORDER};"
                f"border-radius:6px;padding:16px 14px;height:100%;'>"
                f"<div style='font-family:DM Mono,monospace;font-size:10px;"
                f"text-transform:uppercase;letter-spacing:0.07em;"
                f"color:{s.MUTED};margin-bottom:10px;'>{label}</div>"
                f"<div style='display:flex;align-items:baseline;margin-bottom:4px;'>"
                f"<span style='font-family:Barlow Condensed,sans-serif;font-size:30px;"
                f"font-weight:700;line-height:1;color:{color};'>{value}</span>"
                f"{trend}</div>"
                f"<div style='display:flex;justify-content:space-between;align-items:flex-end;margin-top:8px;'>"
                f"<div style='font-family:Inter,sans-serif;font-size:11px;color:{s.MUTED};'>{sub}</div>"
                f"{sparkline}</div></div>",
                unsafe_allow_html=True,
            )

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    map_col, panel_col = st.columns([3, 1], gap="small")
    with map_col:
        # Real-time interactive map — Folium/OpenStreetMap
        t = {"bg": s.BG}  # pass theme hint to render_map
        render_map(t)
        # Human cost annotation strip below map
        annotations = [
            ("①", "Bor South",   "12,400 people",   "Evacuation in progress", s.DANGER),
            ("②", "Bentiu IDP",  "109,000 displaced","Dyke risk — monitor",    s.WARNING),
            ("③", "Akobo East",  "8,200 people",     "Road access cut off",    s.WARNING),
            ("④", "Leer County", "50,000 people",    "All payams submerged",   s.DANGER),
        ]
        ann_html = "".join(
            f"<div style='display:flex;align-items:flex-start;gap:8px;padding:6px 10px;"
            f"border-left:2px solid {color};background:rgba(7,17,26,0.6);border-radius:0 3px 3px 0;'>"
            f"<span style='font-family:DM Mono,monospace;font-size:11px;color:{color};font-weight:700;flex-shrink:0;'>{num}</span>"
            f"<div>"
            f"<div style='font-family:DM Mono,monospace;font-size:10px;color:{s.FG};font-weight:600;'>{name} "
            f"<span style='color:{s.MUTED};font-weight:400;'>— {pop}</span></div>"
            f"<div style='font-family:Inter,sans-serif;font-size:10px;color:{s.MUTED};'>{status}</div>"
            f"</div></div>"
            for num, name, pop, status, color in annotations
        )
        st.markdown(
            f"<div style='margin-top:6px;background:{s.CARD};border:1px solid {s.BORDER};"
            f"border-radius:4px;overflow:hidden;'>"
            f"<div style='padding:5px 10px;border-bottom:1px solid {s.BORDER};"
            f"font-family:DM Mono,monospace;font-size:9px;color:{s.MUTED};"
            f"text-transform:uppercase;letter-spacing:0.08em;'>Human Cost · Priority Locations</div>"
            f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:1px;background:{s.BORDER};'>"
            f"{ann_html}"
            f"</div></div>",
            unsafe_allow_html=True,
        )
    with panel_col:
        st.markdown(s.card_wrap(
            s.section_label("Active Event · EVT-2025-047")
            + s.progress_bar("Flood extent",     1200/3000, s.ACCENT,   "1,200 ha")
            + s.progress_bar("Affected pop.",     5000/10000,s.WARNING,  "5,000")
            + s.progress_bar("Alerts sent",       24/50,     s.FG,       "24")
            + s.progress_bar("Detection latency", 45/60,     s.SUCCESS,  "45 min"),
            "padding:12px"
        ), unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        st.markdown(s.card_wrap(
            s.section_label("Detection QA")
            + s.progress_bar("IoU score",   0.71, s.SUCCESS)
            + s.progress_bar("Confidence",  0.84, s.ACCENT)
            + s.progress_bar("Cloud cover", 0.12, s.WARNING),
            "padding:12px"
        ), unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        alert_rows = "".join(
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
            f'<div style="display:flex;align-items:center;gap:6px">'
            f'<div style="width:6px;height:6px;border-radius:50%;background:{c}"></div>'
            f'<span style="font-family:Inter,sans-serif;font-size:11px;color:{s.MUTED}">{lbl}</span>'
            f'</div><span style="font-family:DM Mono,monospace;font-size:11px;color:{s.FG}">{cnt}</span></div>'
            for lbl, cnt, c in [("SMS",24,s.SUCCESS),("Email",12,s.ACCENT),("Pending",3,s.WARNING),("Failed",1,s.DANGER)]
        )
        st.markdown(s.card_wrap(s.section_label("Alert Delivery") + alert_rows, "padding:12px"), unsafe_allow_html=True)

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        pipe_rows = "".join(
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">'
            f'<span style="font-family:Inter,sans-serif;font-size:11px;color:{s.MUTED}">{stage}</span>'
            f'{s.badge("OK","OK")}</div>'
            for stage in ["Data Acquisition","Preprocessing","Flood Detection","Risk Assessment","Alert Dispatch"]
        )
        st.markdown(s.card_wrap(s.section_label("Pipeline Status") + pipe_rows, "padding:12px"), unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # State breakdown
    state_html = ""
    for i, row in enumerate(breakdown):
        border = f"border-right:1px solid {s.BORDER};" if i < 2 else ""
        state_html += (
            f'<div style="flex:1;padding:16px 20px;{border}">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">'
            f'<span style="font-family:Inter,sans-serif;font-size:14px;font-weight:600;color:{s.FG}">{row["state"]}</span>'
            f'{s.badge(row["risk"])}</div>'
            f'<div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px">'
            f'<div><div style="font-size:10px;color:{s.MUTED}">Flood</div>'
            f'<div style="font-family:Barlow Condensed,sans-serif;font-size:16px;font-weight:700;color:{s.ACCENT}">{row["flood_ha"]:,} ha</div></div>'
            f'<div><div style="font-size:10px;color:{s.MUTED}">Affected</div>'
            f'<div style="font-family:Barlow Condensed,sans-serif;font-size:16px;font-weight:700;color:{s.WARNING}">{row["affected"]:,}</div></div>'
            f'<div><div style="font-size:10px;color:{s.MUTED}">Alerts</div>'
            f'<div style="font-family:Barlow Condensed,sans-serif;font-size:16px;font-weight:700;color:{s.FG}">{row["alerts"]}</div></div>'
            f'</div></div>'
        )
    st.markdown(s.card_wrap(
        s.card_header("State-Level Breakdown","Current event · 2025-10-23 14:30 UTC")
        + f'<div style="display:flex">{state_html}</div>'
    ), unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    t1, t2, t3 = st.columns(3, gap="small")
    with t1:
        body = ""
        for v in villages:
            vpop = f"{v['population']:,}"
            body += (
                f'<tr style="border-bottom:1px solid rgba(48,54,61,0.5)">'
                + s.table_cell(v["village"],extra="font-weight:500")
                + s.table_cell(vpop, "right", s.MUTED, "mono")
                + f'<td style="padding:8px 12px;text-align:right;border-bottom:1px solid rgba(48,54,61,0.5)">{s.risk_badge(v["risk_pct"])}</td>'
                + s.table_cell(v["action"],"right",s.ACCENT,"mono","10px")
                + "</tr>"
            )
        st.markdown(s.card_wrap(
            s.card_header("Affected Villages",f"{len(villages)} records")
            + f'<table style="width:100%;border-collapse:collapse"><thead>'
            + s.table_header_row(("Village","left"),("Pop.","right"),("Risk","right"),("Action","right"))
            + f'</thead><tbody>{body}</tbody></table>'
        ), unsafe_allow_html=True)
    with t2:
        body = "".join(
            f'<tr>{s.table_cell(r["road"],extra="font-weight:500")}'
            f'{s.table_cell(r["type"],color=s.MUTED)}'
            f'{s.table_cell(r["length_km"],"right",s.MUTED,"mono")}'
            f'{s.table_cell(r["alt_route"],color=s.MUTED)}</tr>'
            for r in roads
        )
        st.markdown(s.card_wrap(
            s.card_header("Inaccessible Roads",f"{len(roads)} roads")
            + f'<table style="width:100%;border-collapse:collapse"><thead>'
            + s.table_header_row(("Road","left"),("Type","left"),("Length","right"),("Alt Route","left"))
            + f'</thead><tbody>{body}</tbody></table>'
        ), unsafe_allow_html=True)
    with t3:
        body = ""
        for h in hf:
            hserved = f"{h['served']:,}"
            body += (
                f"<tr>"
                + s.table_cell(h["name"],extra="font-weight:500")
                + s.table_cell(h["type"],color=s.MUTED,size="10px")
                + f'<td style="padding:8px 12px;border-bottom:1px solid rgba(48,54,61,0.5)">{s.badge(h["status"])}</td>'
                + s.table_cell(hserved,"right",s.MUTED,"mono")
                + "</tr>"
            )
        st.markdown(s.card_wrap(
            s.card_header("Health Facilities at Risk",f"{len(hf)} facilities")
            + f'<table style="width:100%;border-collapse:collapse"><thead>'
            + s.table_header_row(("Name","left"),("Type","left"),("Status","left"),("Served","right"))
            + f'</thead><tbody>{body}</tbody></table>'
        ), unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    al_col, ds_col = st.columns(2, gap="small")
    with al_col:
        live = (f'<div style="display:flex;align-items:center;gap:6px">'
                f'<div style="width:6px;height:6px;border-radius:50%;background:{s.DANGER};'
                f'animation:pulse 1.5s ease-in-out infinite"></div>'
                f'<span style="font-family:DM Mono,monospace;font-size:10px;color:{s.DANGER}">LIVE</span></div>')
        rows = "".join(
            f'<div style="display:flex;align-items:flex-start;gap:12px;padding:10px 16px;'
            f'border-bottom:1px solid rgba(48,54,61,0.5)">'
            f'<span style="font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};'
            f'width:40px;flex-shrink:0;padding-top:2px">{a["time_utc"]}</span>'
            f'{s.badge(a["alert_type"])}'
            f'<span style="font-family:Inter,sans-serif;font-size:11px;color:{s.FG};flex:1">{a["message"]}</span>'
            f'<span style="font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};flex-shrink:0">{a["state"]}</span>'
            f'</div>'
            for a in alerts
        )
        st.markdown(s.card_wrap(s.card_header("Recent System Alerts", live) + rows), unsafe_allow_html=True)
    with ds_col:
        body = "".join(
            f'<tr>{s.table_cell(src["name"],extra="font-weight:500")}'
            f'{s.table_cell(src["provider"],color=s.MUTED)}'
            f'{s.table_cell(src["resolution"],"right",s.MUTED,"mono")}'
            f'{s.table_cell(src["last_update"],color=s.MUTED,font="mono",size="10px")}'
            f'<td style="padding:8px 12px;text-align:center;border-bottom:1px solid rgba(48,54,61,0.5)">'
            f'{s.badge(src["status"])}</td></tr>'
            for src in sources
        )
        st.markdown(s.card_wrap(
            s.card_header("Data Sources","Ingestion status")
            + f'<table style="width:100%;border-collapse:collapse"><thead>'
            + s.table_header_row(("Source","left"),("Provider","left"),("Res.","right"),("Last Update","left"),("Status","center"))
            + f'</thead><tbody>{body}</tbody></table>'
        ), unsafe_allow_html=True)

    # ── Media — Field Evidence & Video ────────────────────────
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    st.markdown(s.card_wrap(
        s.card_header("Field Evidence & Media", "Greater Upper Nile · 2025 flood season")
    ), unsafe_allow_html=True)

    # Video row
    vid_col1, vid_col2 = st.columns(2, gap="small")
    with vid_col1:
        st.markdown(
            f"<div style='background:{s.CARD};border:1px solid {s.BORDER};border-radius:4px;overflow:hidden;'>"
            f"<div style='position:relative;padding-bottom:56.25%;height:0;overflow:hidden;'>"
            f"<iframe src='https://www.youtube.com/embed/wAC5JqO4qwA' "
            f"style='position:absolute;top:0;left:0;width:100%;height:100%;border:none;' "
            f"allow='accelerometer;autoplay;clipboard-write;encrypted-media;gyroscope;picture-in-picture' "
            f"allowfullscreen></iframe></div>"
            f"<div style='padding:10px 14px;font-family:Inter,sans-serif;font-size:12px;color:{s.MUTED};'>"
            f"Flooding in Greater Upper Nile &middot; Field footage</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    with vid_col2:
        st.markdown(
            f"<div style='background:{s.CARD};border:1px solid {s.BORDER};border-radius:4px;overflow:hidden;'>"
            f"<div style='position:relative;padding-bottom:56.25%;height:0;overflow:hidden;'>"
            f"<iframe src='https://www.youtube.com/embed/96QOyr4mrLE' "
            f"style='position:absolute;top:0;left:0;width:100%;height:100%;border:none;' "
            f"allow='accelerometer;autoplay;clipboard-write;encrypted-media;gyroscope;picture-in-picture' "
            f"allowfullscreen></iframe></div>"
            f"<div style='padding:10px 14px;font-family:Inter,sans-serif;font-size:12px;color:{s.MUTED};'>"
            f"Flood impact documentation &middot; Greater Upper Nile</div>"
            f"</div>",
            unsafe_allow_html=True
        )

    st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

    # Photo row — World Vision field images
    img_col1, img_col2, img_col3, img_col4 = st.columns(4, gap="small")
    images = [
        ("https://www.wvi.org/sites/default/files/inline-images/IMG_20191116_085944_edits_0.jpg",
         "World Vision — flood-affected community, Upper Nile"),
        ("https://www.wvi.org/sites/default/files/styles/4_3_1440x1080/public/2019-12/IMG_9466_edits.webp?itok=yVnPLQ3b",
         "World Vision — field response team, South Sudan"),
        ("https://img.msf.org/AssetLink/6ffuum75pgskde5hoidarhl457rqj4rw.jpg",
         "MSF — medical response after flooding"),
        ("https://img.msf.org/Doc_Prod/TR1/f/8/0/6/MSB139578.jpg?d0",
         "MSF — field teams in flooded areas"),
    ]
    for col, (img_url, caption) in zip([img_col1, img_col2, img_col3, img_col4], images):
        with col:
            st.markdown(
                f"<div style='background:{s.CARD};border:1px solid {s.BORDER};"
                f"border-radius:4px;overflow:hidden;'>"
                f"<img src='{img_url}' alt='Field image' "
                f"style='width:100%;height:140px;object-fit:cover;display:block;filter:brightness(.85);' "
                f"onerror='this.parentElement.style.display=\"none\"'/>"
                f"<div style='padding:8px 10px;font-family:Inter,sans-serif;"
                f"font-size:11px;color:{s.MUTED};line-height:1.5;'>{caption}</div>"
                f"</div>",
                unsafe_allow_html=True
            )

    # ── Intelligence Feed ─────────────────────────────────────
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    render_intelligence_feed()


# ════════════════════════════════════════════════════════════
# PAGE — HISTORY
def page_history():
    # ── Session state ──────────────────────────────────────
    ss = st.session_state
    if "hist_state"   not in ss: ss.hist_state   = "All"
    if "hist_page"    not in ss: ss.hist_page     = 1
    if "hist_start"   not in ss: ss.hist_start    = None
    if "hist_end"     not in ss: ss.hist_end      = None
    if "hist_min_iou" not in ss: ss.hist_min_iou  = 0.65
    if "hist_min_pop" not in ss: ss.hist_min_pop  = 0

    # ── KPI strip ─────────────────────────────────────────
    cols = st.columns(4, gap="small")
    for col, (l, v, sub) in zip(cols, [
        ("TOTAL EVENTS",     "47",       "2025 flood season"),
        ("PEAK MONTH",       "August",   "12 events recorded"),
        ("MAX FLOOD EXTENT", "3,400 ha", "Aug 2025 combined"),
        ("TOTAL AFFECTED",   "31,200",   "cumulative season"),
    ]):
        col.markdown(s.kpi_tile(l, v, sub), unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # ── Chart + Filter (2/3 + 1/3) ────────────────────────
    cc, fc = st.columns([2, 1], gap="small")

    with cc:
        monthly = _cached_season_monthly()
        fig = go.Figure()
        fig.add_bar(
            x=[r["month"] for r in monthly],
            y=[r["events"] for r in monthly],
            name="Events", marker_color=s.PRIMARY, yaxis="y",
            hovertemplate="<b>%{x}</b><br>Events: %{y}<extra></extra>",
        )
        fig.add_bar(
            x=[r["month"] for r in monthly],
            y=[r["total_ha"] for r in monthly],
            name="Total ha", marker_color=s.ACCENT, opacity=0.5, yaxis="y2",
            hovertemplate="<b>%{x}</b><br>Total ha: %{y:,}<extra></extra>",
        )
        fig.update_layout(**_fig(220, barmode="group",
            hoverlabel=dict(bgcolor=s.CARD, bordercolor=s.BORDER,
                            font=dict(family="DM Mono, monospace", size=11, color=s.FG)),
            yaxis=dict(title="Events", gridcolor="rgba(48,54,61,0.8)",
                       tickfont=dict(size=10, color=s.MUTED)),
            yaxis2=dict(title="Ha", overlaying="y", side="right",
                        showgrid=False, tickfont=dict(size=10, color=s.MUTED)),
        ))
        with st.container(border=True):
            _evt = _cached_active_event()
            _year = str(_evt.get("date_utc","2025"))[:4] if _evt else "2025"
            _hdr_col, _btn_col = st.columns([3,1])
            with _hdr_col:
                st.markdown(s.card_header(f"Flood Events by Month — {_year} Season", "events · hectares"),
                            unsafe_allow_html=True)
            with _btn_col:
                _compare = st.toggle("Compare 2024", key="hist_compare", value=False)
            if _compare:
                # 2024 season data overlay
                _months_2024 = ["Jun","Jul","Aug","Sep","Oct"]
                _events_2024 = [4, 7, 11, 8, 5]
                _ha_2024     = [820, 1650, 2900, 1980, 1100]
                fig.add_scatter(
                    x=_months_2024, y=_events_2024, name="2024 Events",
                    mode="lines+markers",
                    line=dict(color=s.MUTED, width=2, dash="dash"),
                    marker=dict(color=s.MUTED, size=6),
                    yaxis="y",
                    hovertemplate="<b>%{x} 2024</b><br>Events: %{y}<extra></extra>",
                )
                fig.add_scatter(
                    x=_months_2024, y=_ha_2024, name="2024 Ha",
                    mode="lines",
                    line=dict(color=s.PURPLE, width=1.5, dash="dot"),
                    yaxis="y2",
                    hovertemplate="<b>%{x} 2024</b><br>Total ha: %{y:,}<extra></extra>",
                )
            fig.update_layout(height=360)
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with fc:
        with st.container(border=True):
            st.markdown(s.card_header("Filter Events"), unsafe_allow_html=True)
            st.markdown(f"<div style='font-size:11px;color:{s.MUTED};margin-bottom:4px;'>Date range</div>", unsafe_allow_html=True)
            dc1, dc2 = st.columns([1, 1])
            with dc1:
                start_d = st.date_input("From", value=ss.hist_start,
                                        format="YYYY-MM-DD",
                                        label_visibility="collapsed",
                                        key="hist_start_input")
            with dc2:
                end_d = st.date_input("To", value=ss.hist_end,
                                      format="YYYY-MM-DD",
                                      label_visibility="collapsed",
                                      key="hist_end_input")
            st.markdown(f"<div style='font-size:11px;color:{s.MUTED};margin:10px 0 6px;'>State</div>", unsafe_allow_html=True)
            sb = st.columns(4)
            for col, state in zip(sb, ["All", "Jonglei", "Unity", "Upper Nile"]):
                lbl = {"All":"All","Jonglei":"Jon.","Unity":"Uni.","Upper Nile":"U.N."}[state]
                if col.button(lbl, key=f"hs_{state}", width="stretch",
                              type="primary" if ss.hist_state == state else "secondary",
                              help=state):
                    ss.hist_state = state
                    ss.hist_page  = 1
                    st.rerun()
            st.markdown(
                f"<div style='font-size:11px;color:{s.MUTED};margin:12px 0 2px;'>Min IoU</div>",
                unsafe_allow_html=True,
            )
            min_iou = st.slider("iou", 0.0, 1.0, ss.hist_min_iou, 0.05,
                                label_visibility="collapsed", key="iou_sl",
                                format="%.2f")
            st.markdown(f"<div style='font-size:11px;color:{s.MUTED};margin:10px 0 2px;'>Min affected pop.</div>", unsafe_allow_html=True)
            min_pop = st.number_input("pop", 0, value=ss.hist_min_pop, step=100,
                                      label_visibility="collapsed", key="pop_ni")
            st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)
            if st.button("⌕ Apply Filters", key="apply_f", width="stretch", type="primary"):
                ss.hist_start   = start_d
                ss.hist_end     = end_d
                ss.hist_min_iou = min_iou
                ss.hist_min_pop = min_pop
                ss.hist_page    = 1
                st.rerun()

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # ── Load + filter events ───────────────────────────────
    all_events = _cached_all_events()

    # Date filter (applied in Python since db.py doesn't take dates yet)
    if ss.hist_start:
        from datetime import date as _date
        all_events = [e for e in all_events
                      if e["date_utc"][:10] >= str(ss.hist_start)]
    if ss.hist_end:
        all_events = [e for e in all_events
                      if e["date_utc"][:10] <= str(ss.hist_end)]

    total      = len(all_events)
    PAGE_SIZE  = 5
    total_pages = max(1, -(-total // PAGE_SIZE))
    cur_page    = min(ss.hist_page, total_pages)
    page_rows   = all_events[(cur_page-1)*PAGE_SIZE : cur_page*PAGE_SIZE]

    # ── Event Log card ─────────────────────────────────────
    with st.container(border=True):
        st.markdown(s.card_header(
            "Event Log",
            f"{total} events · showing page {cur_page} of {total_pages}"
        ), unsafe_allow_html=True)

    if total == 0:
        st.markdown(
            f"<div style='padding:24px;text-align:center;font-family:DM Mono,monospace;"
            f"font-size:11px;color:{s.MUTED};'>No events match the current filters.</div>",
            unsafe_allow_html=True,
        )
    else:
        for i, evt in enumerate(page_rows):
            dot_c = s.DANGER  if evt["affected"] > 5000 else (s.WARNING if evt["affected"] > 3000 else s.SUCCESS)
            lat_c = s.WARNING if evt["latency_min"] > 55 else (s.SUCCESS if evt["latency_min"] <= 45 else s.FG)
            iou_c = s.WARNING if evt["iou"] < 0.65 else (s.SUCCESS if evt["iou"] >= 0.70 else s.FG)
            rk    = f"{cur_page}_{i}_{evt['id']}"

            with st.expander(
                f"{evt['date_utc']}   ·   {evt['id']}   ·   {evt['state']} / {evt['county']}"
            ):
                mc, dc = st.columns([1, 4], gap="small")

                # Mini SVG map — unique per state/county
                # State-specific mini-map configurations
                STATE_MAP = {
                    "Jonglei":    {"flood_cx":"95","flood_cy":"90","river":"M90,5 C88,40 92,75 88,110 C85,130 88,145 88,150","county_x":"70","county_y":"95","label_c":s.SUCCESS},
                    "Unity":      {"flood_cx":"55","flood_cy":"75","river":"M90,5 C88,35 92,65 88,95 C85,120 88,140 88,150","county_x":"35","county_y":"80","label_c":s.PURPLE},
                    "Upper Nile": {"flood_cx":"110","flood_cy":"45","river":"M90,5 C88,30 92,55 88,80 C85,105 88,130 88,150","county_x":"85","county_y":"50","label_c":s.ACCENT},
                }
                sm = STATE_MAP.get(evt["state"], STATE_MAP["Jonglei"])
                with mc:
                    st.markdown(s.card_wrap(
                        f'<svg style="width:100%;height:150px" viewBox="0 0 180 150"' +
                        f' xmlns="http://www.w3.org/2000/svg">' +
                        f'<rect width="180" height="150" fill="#07111a"/>' +
                        f'<path d="{sm["river"]} fill="none" stroke="{s.PRIMARY}" stroke-width="3" opacity="0.6"/>' +
                        f'<polygon points="35,25 {int(sm["flood_cx"])+50},20 {int(sm["flood_cx"])+65},{int(sm["flood_cy"])+20} {int(sm["flood_cx"])+45},{int(sm["flood_cy"])+45} {int(sm["flood_cx"])},{int(sm["flood_cy"])+50} {int(sm["flood_cx"])-40},{int(sm["flood_cy"])+30} {int(sm["flood_cx"])-50},{int(sm["flood_cy"])}" fill="{s.ACCENT}" fill-opacity="0.2" stroke="{s.ACCENT}" stroke-width="1.5" stroke-dasharray="4,2"/>' +
                        f'<circle cx="{sm["flood_cx"]}" cy="{sm["flood_cy"]}" r="6" fill="{dot_c}" stroke="white" stroke-width="1.5"/>' +
                        f'<circle cx="{int(sm["county_x"])+30}" cy="{int(sm["county_y"])-20}" r="4" fill="{s.WARNING}" stroke="white" stroke-width="1"/>' +
                        f'<circle cx="{int(sm["county_x"])-20}" cy="{int(sm["county_y"])+25}" r="4" fill="{s.SUCCESS}" stroke="white" stroke-width="1"/>' +
                        f'<line x1="{int(sm["flood_cx"])-5}" y1="{sm["flood_cy"]}" x2="{int(sm["flood_cx"])+5}" y2="{sm["flood_cy"]}" stroke="{s.DANGER}" stroke-width="2"/>' +
                        f'<line x1="{sm["flood_cx"]}" y1="{int(sm["flood_cy"])-5}" x2="{sm["flood_cx"]}" y2="{int(sm["flood_cy"])+5}" stroke="{s.DANGER}" stroke-width="2"/>' +
                        f'<rect x="0" y="133" width="180" height="17" fill="rgba(7,17,26,0.7)"/>' +
                        f'<text x="6" y="144" fill="{sm["label_c"]}" font-family="DM Mono" font-size="8" font-weight="600">{evt["state"]}</text>' +
                        f'<text x="6" y="144" fill="{s.MUTED}" font-family="DM Mono" font-size="8" dx="{len(evt["state"])*5+4}"> · {evt["county"]}</text>' +
                        f'</svg>'
                    ), unsafe_allow_html=True)

                with dc:
                    # 4 metric tiles
                    c1, c2, c3, c4 = st.columns(4)
                    for col, lbl, val, vc in [
                        (c1, "Latency",      f"{evt['latency_min']} min", lat_c),
                        (c2, "IoU",          f"{evt['iou']:.2f}",         iou_c),
                        (c3, "Flood Extent", f"{evt['flood_ha']:,} ha",   s.FG),
                        (c4, "Affected Pop.",f"{evt['affected']:,}",       s.WARNING),
                    ]:
                        col.markdown(
                            f"<span style='font-size:10px;color:{s.MUTED};'>{lbl}</span><br>"
                            f"<span style='font-family:DM Mono,monospace;font-size:14px;"
                            f"font-weight:600;color:{vc};'>{val}</span>",
                            unsafe_allow_html=True,
                        )

                    # Pipeline timing tiles
                    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
                    t1, t2, t3, t4 = st.columns(4)
                    for col, lbl, val in [
                        (t1, "Data Acquisition", evt.get("data_acq_s", 120)),
                        (t2, "Preprocessing",    evt.get("preproc_s",  900)),
                        (t3, "Flood Detection",  evt.get("flood_det_s",450)),
                        (t4, "Risk Assessment",  evt.get("risk_ass_s", 300)),
                    ]:
                        col.markdown(
                            f"<div style='background:rgba(33,38,45,0.3);border:1px solid rgba(48,54,61,0.5);"
                            f"border-radius:4px;padding:8px 10px;'>"
                            f"<div style='font-family:DM Mono,monospace;font-size:9px;color:{s.MUTED};'>{lbl}</div>"
                            f"<div style='font-family:DM Mono,monospace;font-size:14px;font-weight:600;"
                            f"color:{s.FG};margin-top:2px;'>{val} s</div></div>",
                            unsafe_allow_html=True,
                        )

                    # Top affected villages — pulled from demo db for this event
                    villages = _cached_villages("EVT-2025-047")
                    if villages:
                        vill_str = "  ·  ".join(
                            f"<span style='color:{s.ACCENT};'>●</span> "
                            f"<span style='color:{s.FG};'>{v['village']}</span> "
                            f"<span style='color:{s.MUTED};'>({v['population']:,})</span>"
                            for v in villages[:3]
                        )
                        st.markdown(
                            f"<div style='margin-top:12px;font-family:DM Mono,monospace;font-size:10px;"
                            f"text-transform:uppercase;letter-spacing:0.1em;color:{s.MUTED};'>"
                            f"Top Affected Villages</div>"
                            f"<div style='font-size:11px;margin-top:4px;'>{vill_str}</div>",
                            unsafe_allow_html=True,
                        )

                    # Download buttons
                    st.markdown("<div style='height:10px;'></div>", unsafe_allow_html=True)
                    b1, b2, b3 = st.columns(3)

                    # Build richer export data
                    geo_data = json.dumps({
                        "type": "FeatureCollection",
                        "event_id": evt["id"],
                        "event_date": evt["date_utc"],
                        "properties": {
                            "flood_ha": evt["flood_ha"],
                            "affected": evt["affected"],
                            "state": evt["state"],
                            "county": evt["county"],
                            "iou": evt["iou"],
                            "latency_min": evt["latency_min"],
                        },
                        "features": [],
                    }, indent=2)

                    csv_data = (
                        "event_id,date_utc,latency_min,iou,flood_ha,affected,state,county,"
                        "data_acq_s,preproc_s,flood_det_s,risk_ass_s,alert_s\n"
                        f"{evt['id']},{evt['date_utc']},{evt['latency_min']},{evt['iou']:.2f},"
                        f"{evt['flood_ha']},{evt['affected']},{evt['state']},{evt['county']},"
                        f"{evt.get('data_acq_s',120)},{evt.get('preproc_s',900)},"
                        f"{evt.get('flood_det_s',450)},{evt.get('risk_ass_s',300)},"
                        f"{evt.get('alert_s',150)}\n"
                    )

                    pdf_data = (
                        f"SUDDWATCH SITUATION REPORT\n"
                        f"{'='*40}\n"
                        f"Event ID:         {evt['id']}\n"
                        f"Date:             {evt['date_utc']}\n"
                        f"State / County:   {evt['state']} / {evt['county']}\n"
                        f"\nFLOOD METRICS\n{'-'*40}\n"
                        f"Flood Extent:     {evt['flood_ha']:,} ha\n"
                        f"Affected Pop.:    {evt['affected']:,}\n"
                        f"Detection IoU:    {evt['iou']:.2f}\n"
                        f"Alert Latency:    {evt['latency_min']} min\n"
                        f"\nPIPELINE TIMING\n{'-'*40}\n"
                        f"Data Acquisition: {evt.get('data_acq_s',120)} s\n"
                        f"Preprocessing:    {evt.get('preproc_s',900)} s\n"
                        f"Flood Detection:  {evt.get('flood_det_s',450)} s\n"
                        f"Risk Assessment:  {evt.get('risk_ass_s',300)} s\n"
                        f"Alert Dispatch:   {evt.get('alert_s',150)} s\n"
                        f"\nGenerated by SuddWatch v2.4.1 — Sudd Basin\n"
                    )

                    b1.download_button(
                        "⬇ GeoJSON", data=geo_data,
                        file_name=f"{evt['id']}_flood_extent.geojson",
                        mime="application/geo+json",
                        key=f"geo_{rk}", width="stretch",
                    )
                    b2.download_button(
                        "⬇ PDF Report", data=pdf_data,
                        file_name=f"{evt['id']}_situation_report.txt",
                        mime="text/plain",
                        key=f"pdf_{rk}", width="stretch",
                    )
                    b3.download_button(
                        "⬇ CSV Data", data=csv_data,
                        file_name=f"{evt['id']}_data.csv",
                        mime="text/csv",
                        key=f"csv_{rk}", width="stretch",
                    )

    # ── Pagination ─────────────────────────────────────────
    if total > 0:
        st.markdown(f"<div style='height:1px;background:{s.BORDER};margin:14px 0;'></div>", unsafe_allow_html=True)
        left_col, right_col = st.columns([1, 1])
        with left_col:
            st.markdown(
                f"<div style='font-family:DM Mono,monospace;font-size:11px;color:{s.MUTED};"
                f"padding:6px 0;'>Showing {len(page_rows)} of {total} events</div>",
                unsafe_allow_html=True,
            )
        with right_col:
            # Build compact pagination — only show needed columns
            num_cols = 2 + min(total_pages, 5)  # prev + pages + next
            pg = st.columns(num_cols)
            with pg[0]:
                if st.button("‹", key="h_prev", disabled=(cur_page<=1), width="stretch"):
                    ss.hist_page = cur_page - 1; st.rerun()
            for i in range(1, min(total_pages, 5) + 1):
                with pg[i]:
                    if st.button(str(i), key=f"h_p{i}", width="stretch",
                                 type="primary" if i==cur_page else "secondary"):
                        ss.hist_page = i; st.rerun()
            with pg[-1]:
                if st.button("›", key="h_next", disabled=(cur_page>=total_pages), width="stretch"):
                    ss.hist_page = cur_page + 1; st.rerun()



def page_performance():
    cols = st.columns(5, gap="small")
    for col, (l, v, sub, good) in zip(cols, [
        ("AVG TOTAL LATENCY",  "48 min", "↓ 12% vs last season", True),
        ("SLA COMPLIANCE",     "91.5%",  "43 of 47 events",      True),
        ("AVG IOU SCORE",      "0.71",   "↑ 0.04 vs last season",True),
        ("ALERT SUCCESS RATE", "91.3%",  "last 30 days",         False),
        ("SYSTEM UPTIME",      "99.2%",  "30-day rolling",       True),
    ]):
        col.markdown(s.kpi_tile(l, v, sub, s.SUCCESS if good else s.WARNING),
                     unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    tab1, tab2, tab3, tab4 = st.tabs(["Pipeline Timing", "Detection Quality", "SLA Compliance", "Stage Heatmap"])

    dates  = ["Aug 14", "Sep 02", "Sep 19", "Oct 08", "Oct 23"]
    lat_y  = [44, 61, 38, 52, 45]
    iou_y  = [0.74, 0.63, 0.79, 0.68, 0.71]

    # ── TAB 1: Pipeline Timing ─────────────────────────────
    with tab1:
        c1, c2 = st.columns(2, gap="small")

        with c1:
            with st.container(border=True):
                st.markdown(
                    s.card_header("Total Latency Over Time", "minutes · SLA = 60 min"),
                    unsafe_allow_html=True,
                )
                fig = go.Figure()
                fig.add_scatter(
                    x=dates, y=lat_y, mode="lines+markers",
                    line=dict(color=s.ACCENT, width=2, shape="spline", smoothing=1.3),
                    marker=dict(color=s.ACCENT, size=7, line=dict(color=s.BG, width=1.5)),
                    name="Latency (min)",
                    hovertemplate="<b>%{x}</b><br>Latency: %{y} min<extra></extra>",
                )
                fig.add_hline(
                    y=60, line_dash="dash", line_color=s.WARNING, line_width=1.5,
                    annotation_text="SLA 60 min",
                    annotation_position="top right",
                    annotation_font=dict(color=s.WARNING, size=10),
                )
                fig.update_layout(**_fig(220, showlegend=False,
                    hoverlabel=dict(bgcolor=s.CARD, bordercolor=s.BORDER,
                                    font=dict(family="DM Mono, monospace", size=11)),
                    xaxis=dict(gridcolor="rgba(48,54,61,0.8)", tickfont=dict(size=10, color=s.MUTED)),
                    yaxis=dict(gridcolor="rgba(48,54,61,0.8)", tickfont=dict(size=10, color=s.MUTED),
                               title=dict(text="Minutes", font=dict(size=10, color=s.MUTED))),
                ))
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        with c2:
            stages  = ["Data Acq", "Preproc", "Detection", "Risk Ass", "Alerting"]
            avg_s   = [131, 916, 482, 314, 155]
            min_s   = [95,  780, 390, 250, 120]
            max_s   = [180, 1100, 580, 410, 200]
            with st.container(border=True):
                st.markdown(
                    s.card_header("Avg Stage Duration", "seconds · min / max range"),
                    unsafe_allow_html=True,
                )
                fig = go.Figure()
                # Error bars showing min/max range
                fig.add_bar(
                    x=stages, y=avg_s, name="Avg (s)",
                    marker_color=s.PRIMARY, marker_line_width=0,
                    error_y=dict(
                        type="data", symmetric=False,
                        array=[mx - av for mx, av in zip(max_s, avg_s)],
                        arrayminus=[av - mn for av, mn in zip(avg_s, min_s)],
                        color=s.MUTED, thickness=1.5, width=6,
                    ),
                    hovertemplate="<b>%{x}</b><br>Avg: %{y} s<extra></extra>",
                )
                fig.update_layout(**_fig(220,
                    hoverlabel=dict(bgcolor=s.CARD, bordercolor=s.BORDER,
                                    font=dict(family="DM Mono, monospace", size=11)),
                    xaxis=dict(gridcolor="rgba(48,54,61,0.8)", tickfont=dict(size=10, color=s.MUTED)),
                    yaxis=dict(gridcolor="rgba(48,54,61,0.8)", tickfont=dict(size=10, color=s.MUTED),
                               title=dict(text="Seconds", font=dict(size=10, color=s.MUTED))),
                    showlegend=False,
                ))
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)

        # Pipeline timing table
        perf = _cached_performance_rows()
        body = ""
        for r in perf:
            lat_c = s.WARNING if r["latency_min"] > 55 else s.SUCCESS
            sla   = "PASS" if r["latency_min"] <= 60 else "BREACH"
            body += (
                f"<tr>"
                + s.table_cell(r["id"],              color=s.ACCENT, font="mono")
                + s.table_cell(r["date_utc"][:10],   color=s.MUTED,  font="mono")
                + s.table_cell(str(r.get("data_acq_s", 120)), font="mono")
                + s.table_cell(str(r.get("preproc_s",  900)), font="mono")
                + s.table_cell(str(r.get("flood_det_s",450)), font="mono")
                + s.table_cell(str(r.get("risk_ass_s", 300)), font="mono")
                + s.table_cell(str(r.get("alert_s",    150)), font="mono")
                + s.table_cell(str(r["latency_min"]),
                               color=lat_c, font="mono", extra="font-weight:600")
                + f'<td style="padding:8px 12px;border-bottom:1px solid rgba(48,54,61,0.5)">'
                + s.badge(sla) + "</td></tr>"
            )
        st.markdown(s.card_wrap(
            s.card_header("Pipeline Timing — Per Event",
                          "seconds per stage · total in minutes")
            + f'<table style="width:100%;border-collapse:collapse"><thead>'
            + s.table_header_row(
                ("Event ID","left"), ("Date","left"),
                ("Data Acq(s)","left"), ("Preproc(s)","left"),
                ("Flood Det(s)","left"), ("Risk Ass(s)","left"),
                ("Alert(s)","left"), ("Total(min)","left"), ("SLA","left"),
              )
            + f'</thead><tbody>{body}</tbody></table>'
            + f'<div style="padding:8px 16px;border-top:1px solid {s.BORDER};'
            + f'font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};">'
            + 'Data sourced from SQLite database · wall-clock duration per pipeline stage'
            + '</div>'
        ), unsafe_allow_html=True)

    # ── TAB 2: Detection Quality ───────────────────────────
    with tab2:
        c1, c2 = st.columns(2, gap="small")

        with c1:
            with st.container(border=True):
                st.markdown(
                    s.card_header("IoU Score Over Time", "0 – 1 · threshold = 0.65"),
                    unsafe_allow_html=True,
                )
                fig = go.Figure()
                fig.add_scatter(
                    x=dates, y=iou_y, mode="lines+markers",
                    line=dict(color=s.SUCCESS, width=2, shape="spline", smoothing=1.3),
                    marker=dict(color=s.SUCCESS, size=7, line=dict(color=s.BG, width=1.5)),
                    name="IoU",
                    hovertemplate="<b>%{x}</b><br>IoU: %{y:.2f}<extra></extra>",
                )
                fig.add_hline(
                    y=0.65, line_dash="dash", line_color=s.WARNING, line_width=1.5,
                    annotation_text="Threshold 0.65",
                    annotation_position="top right",
                    annotation_font=dict(color=s.WARNING, size=10),
                )
                # Shade below threshold
                fig.add_scatter(
                    x=dates + dates[::-1],
                    y=[0.65]*len(dates) + iou_y[::-1],
                    fill="toself",
                    fillcolor=f"rgba(245,158,11,0.06)",
                    line=dict(width=0),
                    showlegend=False,
                    hoverinfo="skip",
                )
                fig.update_layout(**_fig(220, showlegend=False,
                    hoverlabel=dict(bgcolor=s.CARD, bordercolor=s.BORDER,
                                    font=dict(family="DM Mono, monospace", size=11)),
                    xaxis=dict(gridcolor="rgba(48,54,61,0.8)", tickfont=dict(size=10, color=s.MUTED)),
                    yaxis=dict(range=[0.5, 0.9],
                               gridcolor="rgba(48,54,61,0.8)",
                               tickfont=dict(size=10, color=s.MUTED),
                               title=dict(text="IoU Score", font=dict(size=10, color=s.MUTED))),
                ))
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        with c2:
            with st.container(border=True):
                st.markdown(
                    s.card_header("Latency vs IoU Correlation", "per event"),
                    unsafe_allow_html=True,
                )
                fig = go.Figure()
                fig.add_scatter(
                    x=lat_y, y=iou_y, mode="markers",
                    marker=dict(color=s.ACCENT, size=10,
                                line=dict(color=s.BG, width=1.5)),
                    text=["EVT-2025-021","EVT-2025-028","EVT-2025-033","EVT-2025-041","EVT-2025-047"],
                    hovertemplate=(
                        "<b>%{text}</b><br>"
                        "Latency: %{x} min<br>"
                        "IoU: %{y:.2f}<extra></extra>"
                    ),
                )
                # Quadrant lines
                fig.add_hline(y=0.65, line_dash="dash", line_color=s.WARNING, line_width=1)
                fig.add_vline(x=60,   line_dash="dash", line_color=s.WARNING, line_width=1)
                # Quadrant annotations
                for txt, ax_, ay_ in [
                    ("✓ Fast & Accurate", 35, 0.80),
                    ("⚠ Slow & Accurate", 68, 0.80),
                    ("⚠ Fast & Inaccurate", 35, 0.58),
                    ("✗ Slow & Inaccurate", 68, 0.58),
                ]:
                    fig.add_annotation(x=ax_, y=ay_, text=txt, showarrow=False,
                                       font=dict(size=8, color=s.MUTED),
                                       xanchor="center")
                fig.update_layout(**_fig(220, showlegend=False,
                    hoverlabel=dict(bgcolor=s.CARD, bordercolor=s.BORDER,
                                    font=dict(family="DM Mono, monospace", size=11)),
                    xaxis=dict(range=[30, 75], title=dict(text="Latency (min)", font=dict(size=10, color=s.MUTED)),
                               gridcolor="rgba(48,54,61,0.8)", tickfont=dict(size=10, color=s.MUTED)),
                    yaxis=dict(range=[0.55, 0.85], title=dict(text="IoU Score", font=dict(size=10, color=s.MUTED)),
                               gridcolor="rgba(48,54,61,0.8)", tickfont=dict(size=10, color=s.MUTED)),
                ))
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        # Alert delivery bars
        st.markdown("<div style='height:8px'></div>", unsafe_allow_html=True)
        bars = "".join(
            f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
            f'<span style="font-family:DM Mono,monospace;font-size:11px;color:{s.MUTED};'
            f'width:90px;flex-shrink:0">{lbl}</span>'
            f'<div style="flex:1;background:{s.MUTED_BG};height:8px;border-radius:9999px">'
            f'<div style="width:{pct}%;height:8px;background:'
            f'{s.SUCCESS if pct==100 else s.ACCENT if pct>=95 else s.WARNING};'
            f'border-radius:9999px"></div></div>'
            f'<span style="font-family:DM Mono,monospace;font-size:11px;'
            f'color:{s.FG};width:40px;text-align:right">{pct}%</span></div>'
            for lbl, pct in [
                ("Data Acq", 100), ("Preproc", 100),
                ("Detection", 97), ("Risk Ass", 95), ("Alerting", 91),
            ]
        )
        st.markdown(s.card_wrap(
            s.card_header("Alert Delivery by Stage", "% success rate")
            + f'<div style="padding:16px">{bars}</div>'
        ), unsafe_allow_html=True)

    # ── TAB 3: SLA Compliance ─────────────────────────────
    with tab3:
        c1, c2 = st.columns(2, gap="small")

        with c1:
            with st.container(border=True):
                st.markdown(
                    s.card_header("SLA Compliance by Month",
                                  "events passing 60-min SLA"),
                    unsafe_allow_html=True,
                )
                months  = ["Jun", "Jul", "Aug", "Sep", "Oct"]
                within  = [5, 8, 10, 9, 6]
                breach  = [0, 1, 2, 2, 1]
                fig = go.Figure()
                fig.add_bar(
                    x=months, y=within, name="Within SLA",
                    marker_color=s.SUCCESS, marker_line_width=0,
                    hovertemplate="<b>%{x}</b><br>Within SLA: %{y}<extra></extra>",
                )
                fig.add_bar(
                    x=months, y=breach, name="SLA Breach",
                    marker_color=s.DANGER, marker_line_width=0,
                    hovertemplate="<b>%{x}</b><br>Breach: %{y}<extra></extra>",
                )
                fig.update_layout(**_fig(300, barmode="stack",
                    hoverlabel=dict(bgcolor=s.CARD, bordercolor=s.BORDER,
                                    font=dict(family="DM Mono, monospace", size=11)),
                    xaxis=dict(gridcolor="rgba(48,54,61,0.8)", tickfont=dict(size=10, color=s.MUTED)),
                    yaxis=dict(gridcolor="rgba(48,54,61,0.8)", tickfont=dict(size=10, color=s.MUTED),
                               title=dict(text="Events", font=dict(size=10, color=s.MUTED))),
                    legend=dict(orientation="h", y=-0.2, font=dict(size=10),
                                bgcolor="rgba(0,0,0,0)"),
                ))
                st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

        with c2:
            thresholds = [
                ("Total pipeline latency", "≤ 60 min",  "48 min avg",   True),
                ("Flood detection IoU",    "≥ 0.65",    "0.71 avg",     True),
                ("Alert delivery rate",    "≥ 95%",     "91.3%",        False),
                ("System availability",    "≥ 99%",     "99.2%",        True),
                ("Data acquisition gap",   "≤ 6 days",  "3.2 days avg", True),
            ]
            rows = "".join(
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:12px 0;border-bottom:1px solid {s.BORDER}">'
                f'<div>'
                f'<div style="font-family:Inter,sans-serif;font-size:11px;'
                f'color:{s.FG};margin-bottom:2px">{metric}</div>'
                f'<div style="font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED}">'
                f'Target: {tgt} · Actual: {act}</div>'
                f'</div>'
                f'{s.badge("PASS" if passed else "FAIL")}</div>'
                for metric, tgt, act, passed in thresholds
            )
            st.markdown(s.card_wrap(
                s.card_header("SLA Thresholds")
                + f'<div style="padding:0 16px 4px">{rows}</div>'
            ), unsafe_allow_html=True)



    # ── TAB 4: Stage Duration Heatmap ────────────────────
    with tab4:
        st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown(
                s.card_header("Stage Duration Heatmap", "seconds per stage · colour = duration"),
                unsafe_allow_html=True,
            )
            # Heatmap data — reads from real DB, falls back to demo
            stages_h  = ["Data Acq","Preproc","Flood Det","Risk Ass","Alert"]
            _perf = _cached_performance_rows()
            if _perf and any(r.get("data_acq_s",0) > 0 for r in _perf):
                events_h = [r["id"] for r in _perf]
                z_data   = [
                    [r.get("data_acq_s",120), r.get("preproc_s",900),
                     r.get("flood_det_s",450), r.get("risk_ass_s",300),
                     r.get("alert_s",150)]
                    for r in _perf
                ]
            else:
                events_h = ["EVT-2025-021","EVT-2025-028","EVT-2025-033","EVT-2025-041","EVT-2025-047"]
                z_data   = [
                    [95,  780, 390, 250, 120],
                    [142, 1050, 520, 380, 165],
                    [88,  820, 410, 260, 110],
                    [165, 980, 480, 350, 145],
                    [131, 916, 482, 314, 155],
                ]
            # Colour scale: green=fast, amber=medium, red=slow
            fig_h = go.Figure(data=go.Heatmap(
                z=z_data,
                x=stages_h,
                y=events_h,
                colorscale=[
                    [0.0, s.SUCCESS],
                    [0.5, s.WARNING],
                    [1.0, s.DANGER],
                ],
                showscale=True,
                colorbar=dict(
                    title=dict(text="Seconds", font=dict(size=10, color=s.MUTED)),
                    tickfont=dict(size=10, color=s.MUTED),
                    bgcolor=s.CARD,
                    bordercolor=s.BORDER,
                    thickness=12,
                ),
                hoverongaps=False,
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Stage: %{x}<br>"
                    "Duration: %{z} s<extra></extra>"
                ),
                text=[[str(v) + "s" for v in row] for row in z_data],
                texttemplate="%{text}",
                textfont=dict(size=10, color="white"),
            ))
            fig_h.update_layout(**_fig(280,
                hoverlabel=dict(bgcolor=s.CARD, bordercolor=s.BORDER,
                                font=dict(family="DM Mono, monospace", size=11, color=s.FG)),
                xaxis=dict(side="top", tickfont=dict(size=11, color=s.MUTED),
                           gridcolor="rgba(0,0,0,0)"),
                yaxis=dict(tickfont=dict(size=10, color=s.MUTED),
                           gridcolor="rgba(0,0,0,0)"),
                margin=dict(l=120, r=60, t=40, b=10),
            ))
            st.plotly_chart(fig_h, width="stretch", config={"displayModeBar": False})

            # Insight callout
            st.markdown(
                f"<div style='padding:10px 16px;background:{s.MUTED_BG};"
                f"border-left:3px solid {s.WARNING};border-radius:0 4px 4px 0;"
                f"font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};'>"
                f"<strong style='color:{s.FG};'>Bottleneck:</strong> "
                f"Preprocessing consistently accounts for 50–60% of total pipeline latency. "
                f"SNAP GPT terrain correction on 10m resolution is the primary driver. "
                f"Switching to 20m output would reduce preprocessing time by ~35%.</div>",
                unsafe_allow_html=True,
            )


def page_export():
    cols = st.columns(4, gap="small")
    for col, (l, v, sub) in zip(cols, [
        ("TOTAL EXPORTS (SEASON)", "312",    "all formats combined"),
        ("PDF REPORTS GENERATED",  "47",     "one per event"),
        ("GEOJSON DOWNLOADS",      "138",    "flood layers"),
        ("AVG EXPORT SIZE",        "8.2 MB", "across all formats"),
    ]):
        col.markdown(s.kpi_tile(l, v, sub), unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    all_events = _cached_all_events()
    FORMATS = {
        "GeoJSON":        ("Flood extent polygons, village points, road features",   "~2.4 MB"),
        "Shapefile (ZIP)":("ESRI Shapefile bundle — compatible with ArcGIS / QGIS",  "~3.1 MB"),
        "CSV Tabular":    ("Villages, roads, health facilities — one row per feature", "~180 KB"),
        "PDF Report":     ("Formatted situation report with map, tables, QA metrics",  "~4.8 MB"),
        "GeoTIFF":        ("Flood mask raster at 10 m resolution (Sentinel-1 derived)","~48 MB"),
    }
    LAYERS = {
        "Flood Extent Polygon":      ["GeoJSON","Shapefile (ZIP)","GeoTIFF"],
        "Affected Villages":         ["GeoJSON","Shapefile (ZIP)","CSV Tabular"],
        "Inaccessible Roads":        ["GeoJSON","Shapefile (ZIP)","CSV Tabular"],
        "Health Facilities at Risk": ["GeoJSON","Shapefile (ZIP)","CSV Tabular"],
        "Administrative Boundaries": ["GeoJSON","Shapefile (ZIP)"],
        "Affected Population Grid":  ["GeoJSON","GeoTIFF"],
    }
    EXT = {"GeoJSON":".geojson","Shapefile (ZIP)":".zip",
           "CSV Tabular":".csv","PDF Report":".pdf","GeoTIFF":".tif"}

    fmt = st.session_state.export_fmt
    ext = EXT.get(fmt, "")

    s1, s2, s3 = st.columns(3, gap="small")

    # ── Step 1 ────────────────────────────────────────────
    with s1:
        with st.container(border=True):
            st.markdown(s.card_header("Step 1 — Select Scope"), unsafe_allow_html=True)

            scope = st.radio("scope", ["Single Event","Full Season"],
                             horizontal=True, label_visibility="collapsed",
                             key="ex_scope_r",
                             index=0 if st.session_state.export_scope=="Single Event" else 1)
            st.session_state.export_scope = scope

            if scope == "Single Event":
                st.markdown(
                    f"<div style='font-size:11px;color:{s.MUTED};margin:10px 0 6px;'>"
                    f"Select events to export</div>",
                    unsafe_allow_html=True,
                )
                for ei, evt in enumerate(all_events):
                    sel = evt["id"] in st.session_state.export_events
                    bg  = f"rgba(26,127,212,0.12)" if sel else "transparent"
                    bc  = s.PRIMARY if sel else s.BORDER
                    chk = "☑" if sel else "☐"
                    # Render as styled HTML row — clicking the button toggles selection
                    if st.button(
                        f"{chk}  {evt['id']} · {evt['date_utc'][:10]} · {evt['county']}",
                        key=f"ev_{ei}_{evt['id']}", width="stretch",
                        type="primary" if sel else "secondary",
                    ):
                        if sel: st.session_state.export_events.discard(evt["id"])
                        else:   st.session_state.export_events.add(evt["id"])
                        st.rerun()
                st.markdown("<div style='flex:1;'></div>", unsafe_allow_html=True)
            else:
                st.markdown(
                    f"<div style='font-size:11px;color:{s.MUTED};margin:10px 0 4px;'>Season date range</div>",
                    unsafe_allow_html=True,
                )
                dc1, dc2 = st.columns(2)
                with dc1:
                    st.date_input("From", value=None, format="YYYY-MM-DD",
                                  label_visibility="collapsed", key="ex_from")
                with dc2:
                    st.date_input("To", value=None, format="YYYY-MM-DD",
                                  label_visibility="collapsed", key="ex_to")
                st.markdown(
                    f"<div style='padding:8px 10px;background:{s.MUTED_BG};"
                    f"border:1px solid {s.BORDER};border-radius:4px;margin-top:8px;"
                    f"font-family:DM Mono,monospace;font-size:11px;color:{s.MUTED};'>"
                    f"47 events matched · all states</div>",
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f"<div style='font-size:11px;color:{s.MUTED};margin:10px 0 4px;'>Filter by state</div>",
                    unsafe_allow_html=True,
                )
                st.selectbox("State",
                             ["All states","Jonglei only","Unity only","Upper Nile only"],
                             label_visibility="collapsed", key="ex_state")

    # ── Step 2 ────────────────────────────────────────────
    with s2:
        with st.container(border=True):
            st.markdown(s.card_header("Step 2 — Format & Layers"), unsafe_allow_html=True)
            st.markdown(
                f"<div style='font-size:11px;color:{s.MUTED};margin-bottom:8px;'>Export format</div>",
                unsafe_allow_html=True,
            )
            for fi, (fname_opt, (fdesc, fsize)) in enumerate(FORMATS.items()):
                sel  = st.session_state.export_fmt == fname_opt
                bg   = f"rgba(26,127,212,0.10)" if sel else "transparent"
                bc   = s.PRIMARY if sel else s.BORDER
                dot  = f"<span style='display:inline-block;width:8px;height:8px;border-radius:50%;background:{s.PRIMARY};margin-right:6px;flex-shrink:0;'></span>" if sel else f"<span style='display:inline-block;width:8px;height:8px;border-radius:50%;border:1.5px solid {s.BORDER};margin-right:6px;flex-shrink:0;'></span>"
                st.markdown(
                    f"<div style='background:{bg};border:1px solid {bc};border-radius:4px;"
                    f"padding:8px 12px;margin-bottom:4px;'>"
                    f"<div style='display:flex;align-items:center;margin-bottom:2px;'>"
                    f"{dot}"
                    f"<span style='font-family:Inter,sans-serif;font-size:12px;font-weight:600;"
                    f"color:{s.FG};'>{fname_opt}</span>"
                    f"<span style='font-family:DM Mono,monospace;font-size:10px;color:{s.ACCENT};"
                    f"margin-left:auto;'>{fsize}</span></div>"
                    f"<div style='font-family:Inter,sans-serif;font-size:10px;color:{s.MUTED};"
                    f"margin-left:14px;'>{fdesc}</div></div>",
                    unsafe_allow_html=True,
                )
                if st.button(f"Select {fname_opt}", key=f"fmt_{fi}", width="stretch"):
                    st.session_state.export_fmt = fname_opt
                    st.session_state.export_done = False
                    st.rerun()

    # ── Step 3 ────────────────────────────────────────────
    with s3:
        with st.container(border=True):
            fmt = st.session_state.export_fmt
            ext = EXT.get(fmt, "")
            st.markdown(
                s.card_header("Step 3 — Select Layers & Export")
                + f"<div style='font-size:11px;color:{s.MUTED};margin-bottom:8px;'>"
                + f"Layers available for "
                + f"<span style='font-family:DM Mono,monospace;color:{s.ACCENT};'>{ext}</span>"
                + f"</div>",
                unsafe_allow_html=True,
            )
            for layer, compat in LAYERS.items():
                avail   = fmt in compat
                checked = layer in st.session_state.export_layers and avail
                toggled = st.checkbox(
                    layer + ("" if avail else " (unavailable)"),
                    value=checked, disabled=not avail,
                    key=f"layer_{layer}",
                )
                if avail:
                    if toggled: st.session_state.export_layers.add(layer)
                    else:       st.session_state.export_layers.discard(layer)

            n_ev  = (len(st.session_state.export_events)
                     if st.session_state.export_scope == "Single Event" else 47)
            n_lay = len([l for l in st.session_state.export_layers
                         if fmt in LAYERS.get(l, [])])

            st.markdown(
                f"<div style='padding:10px 12px;background:rgba(33,38,45,0.3);"
                f"border:1px solid rgba(48,54,61,0.7);border-radius:4px;"
                f"margin:12px 0 8px;font-family:DM Mono,monospace;font-size:11px;'>"
                + "".join(
                    f"<div style='display:flex;justify-content:space-between;margin-bottom:3px;'>"
                    f"<span style='color:{s.MUTED};'>{k}</span>"
                    f"<span style='color:{vc};'>{v}</span></div>"
                    for k, v, vc in [
                        ("Format",   fmt,            s.FG),
                        ("Events",   str(n_ev),      s.FG),
                        ("Layers",   str(n_lay),     s.FG),
                        ("Est. size", FORMATS[fmt][1], s.ACCENT),
                    ]
                )
                + "</div>",
                unsafe_allow_html=True,
            )

            # Live preview before generating
            if not st.session_state.export_done:
                PREVIEW_DATA = {
                    "CSV Tabular": (
                        "event_id,date_utc,flood_ha,affected,state,county\n"
                        "EVT-2025-047,2025-10-23,1200,5000,Jonglei,Bor South\n"
                        "EVT-2025-041,2025-10-08,980,4200,Unity,Leer\n"
                        "EVT-2025-033,2025-09-19,850,3100,Upper Nile,Malakal\n"
                        "... ({} more rows)",
                    ),
                    "GeoJSON": (
                        '{{"type":"FeatureCollection","features":[\n'
                        '  {{"type":"Feature","properties":{{"event_id":"EVT-2025-047",\n'
                        '    "flood_ha":1200,"affected":5000,"state":"Jonglei"}},\n'
                        '    "geometry":null}},\n'
                        '  ... ({} more features)\n'
                        ']}}',
                    ),
                    "PDF Report": (
                        "SUDDWATCH FLOOD SITUATION REPORT\n"
                        "══════════════════════════════════\n"
                        "Event: EVT-2025-047  |  2025-10-23\n"
                        "Flood Extent: 1,200 ha\n"
                        "Affected: 5,000 people\n"
                        "State: Jonglei / Bor South\n"
                        "... (full report: {} pages)",
                    ),
                    "GeoTIFF": (
                        "Binary raster — 10m resolution\n"
                        "CRS: WGS84 (EPSG:4326)\n"
                        "Bands: 1 (flood mask: 0=dry, 1=flood)\n"
                        "Extent: Sudd Basin AOI\n"
                        "Size: ~{} MB per scene",
                    ),
                    "Shapefile (ZIP)": (
                        "flood_extent.shp + .dbf + .prj + .shx\n"
                        "Compatible: ArcGIS, QGIS, GRASS GIS\n"
                        "CRS: WGS84 (EPSG:4326)\n"
                        "Features: {} flood polygons\n"
                        "Attributes: event_id, date, area_ha, risk",
                    ),
                }
                _preview_tmpl = PREVIEW_DATA.get(fmt, ("Preview not available",))[0]
                _n = n_ev if n_ev else 1
                try:
                    _preview_txt = _preview_tmpl.format(_n)
                except Exception:
                    _preview_txt = _preview_tmpl
                st.markdown(
                    f"<div style='margin-bottom:8px;'>"
                    f"<div style='font-family:DM Mono,monospace;font-size:9px;"
                    f"color:{s.MUTED};text-transform:uppercase;letter-spacing:0.08em;"
                    f"margin-bottom:4px;'>Preview · {ext}</div>"
                    f"<div style='background:#010409;border:1px solid {s.BORDER};"
                    f"border-radius:4px;padding:8px 10px;font-family:DM Mono,monospace;"
                    f"font-size:9px;color:{s.MUTED};white-space:pre;line-height:1.6;"
                    f"max-height:100px;overflow:hidden;'>{_preview_txt}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )
                if st.button("⬇ Generate Export", key="gen_exp",
                             width="stretch", type="primary"):
                    with st.spinner("Preparing export…"):
                        import time; time.sleep(1)
                    st.session_state.export_done = True
                    st.rerun()
            else:
                st.success("✅ Export ready")
                # Build actual export data
                if fmt == "CSV Tabular":
                    buf = io.StringIO()
                    w   = csv.writer(buf)
                    w.writerow(["event_id","date","flood_ha","affected","state","county"])
                    for e in all_events:
                        w.writerow([e["id"],e["date_utc"],e["flood_ha"],
                                    e["affected"],e["state"],e["county"]])
                    data  = buf.getvalue().encode()
                    fname = "suddwatch_export.csv"
                    mime  = "text/csv"
                elif fmt == "GeoJSON":
                    data  = json.dumps({
                        "type": "FeatureCollection",
                        "features": [{"type":"Feature","properties":e,"geometry":None}
                                     for e in all_events],
                    }, indent=2).encode()
                    fname = "suddwatch_export.geojson"
                    mime  = "application/json"
                elif fmt == "PDF Report":
                    lines_txt = [
                        "SUDDWATCH FLOOD SITUATION REPORT",
                        "=" * 50,
                        f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
                        f"Season: 2025 Flood Season",
                        "",
                        "EVENTS INCLUDED",
                        "-" * 50,
                    ]
                    for e in all_events:
                        lines_txt.append(
                            f"{e['id']}  |  {e['date_utc']}  |  "
                            f"{e['flood_ha']:,} ha  |  {e['affected']:,} affected  |  "
                            f"{e['state']} / {e['county']}"
                        )
                    data  = "\n".join(lines_txt).encode()
                    fname = "suddwatch_situation_report.txt"
                    mime  = "text/plain"
                else:
                    data  = (f"SuddWatch Export — {fmt}\n"
                             f"Generated: {datetime.now(timezone.utc)}\n"
                             f"Events: {n_ev} | Layers: {n_lay}").encode()
                    fname = f"suddwatch_export{ext}"
                    mime  = "application/octet-stream"

                st.download_button(
                    f"⬇ Download {ext}", data=data,
                    file_name=fname, mime=mime,
                    key="do_dl", width="stretch",
                )
                if st.button("↺ Reset", key="reset_exp", width="stretch"):
                    st.session_state.export_done = False
                    st.rerun()

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # ── Download History ──────────────────────────────────
    hist = _cached_download_history()

    # Build preview content for each file type
    def _preview(filename: str) -> str:
        if filename.endswith(".geojson"):
            return json.dumps({"type":"FeatureCollection","note":"Preview — full file available via Re-download","features":[]}, indent=2)
        elif filename.endswith(".csv"):
            return "event_id,date,flood_ha,affected,state,county\nEVT-2025-047,2025-10-23,1200,5000,Jonglei,Bor South\n..."
        elif filename.endswith(".pdf") or filename.endswith(".txt"):
            return "SUDDWATCH FLOOD SITUATION REPORT\n" + "="*50 + "\nPreview — full report available via Re-download"
        return f"File: {filename}\nPreview not available for this format."

    def _mime(filename: str) -> str:
        if filename.endswith(".geojson"): return "application/json"
        if filename.endswith(".csv"):     return "text/csv"
        return "text/plain"

    # Download History
    st.markdown(
        s.card_wrap(s.card_header("Download History", "Last 30 days")),
        unsafe_allow_html=True,
    )
    # Column headers
    h1,h2,h3,h4,h5,h6 = st.columns([3,1,2,1,1,1])
    h1.markdown(f"<span style='font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};text-transform:uppercase;letter-spacing:0.05em;'>Filename</span>", unsafe_allow_html=True)
    h2.markdown(f"<span style='font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};text-transform:uppercase;letter-spacing:0.05em;'>User</span>", unsafe_allow_html=True)
    h3.markdown(f"<span style='font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};text-transform:uppercase;letter-spacing:0.05em;'>Date</span>", unsafe_allow_html=True)
    h4.markdown(f"<span style='font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};text-transform:uppercase;letter-spacing:0.05em;'>Size</span>", unsafe_allow_html=True)
    h5.markdown(f"<span style='font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};text-transform:uppercase;letter-spacing:0.05em;'>Status</span>", unsafe_allow_html=True)
    h6.markdown(f"<span style='font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};text-transform:uppercase;letter-spacing:0.05em;'>Re-download</span>", unsafe_allow_html=True)
    st.markdown(f"<hr style='margin:4px 0;border-color:rgba(48,54,61,0.8);'>", unsafe_allow_html=True)
    for h in hist:
        fname = h["filename"]
        if fname.endswith(".geojson"):
            fdata, fmime = json.dumps({"type":"FeatureCollection","features":[]}).encode(), "application/json"
        elif fname.endswith(".csv"):
            fdata, fmime = b"event_id,date\n", "text/csv"
        else:
            fdata, fmime = fname.encode(), "text/plain"
        c1, c2, c3, c4, c5, c6 = st.columns([3, 1, 2, 1, 1, 1])
        c1.markdown(
            f"<span style='font-family:DM Mono,monospace;font-size:11px;"
            f"color:{s.ACCENT};'>{fname}</span>", unsafe_allow_html=True)
        c2.markdown(
            f"<span style='font-family:DM Mono,monospace;font-size:11px;"
            f"color:{s.MUTED};'>{h['username']}</span>", unsafe_allow_html=True)
        c3.markdown(
            f"<span style='font-family:DM Mono,monospace;font-size:11px;"
            f"color:{s.MUTED};'>{h['date_utc']}</span>", unsafe_allow_html=True)
        c4.markdown(
            f"<span style='font-family:DM Mono,monospace;font-size:11px;"
            f"color:{s.MUTED};'>{h['size_label']}</span>", unsafe_allow_html=True)
        with c5:
            st.markdown(s.badge(h["status"]), unsafe_allow_html=True)
        with c6:
            st.download_button(
                "⬇ Re-download", data=fdata, file_name=fname, mime=fmime,
                key="redl_" + str(h["id"]), width="stretch",
            )
        st.markdown(f"<hr style='margin:4px 0;border-color:rgba(48,54,61,0.4);'>",
                    unsafe_allow_html=True)
# ════════════════════════════════════════════════════════════
# INTELLIGENCE FEED — ReliefWeb API
# ════════════════════════════════════════════════════════════
@st.cache_data(ttl=1800)
def _fetch_reliefweb() -> list:
    """
    Fetch latest South Sudan flood reports from ReliefWeb API.
    Cached for 30 minutes. Silent fallback on failure.
    No API key required — ReliefWeb is a free public API by OCHA.
    """
    import json, urllib.request
    url = "https://api.reliefweb.int/v2/reports?appname=usiu-suddwatch-swe3090-2026"
    def _shorten_src(name):
        return (name
            .replace("UN Office for the Coordination of Humanitarian Affairs", "OCHA")
            .replace("International Federation of Red Cross and Red Crescent Societies", "IFRC")
            .replace("Famine Early Warning System Network", "FEWS NET")
            .replace("United Nations Children's Fund", "UNICEF")
            .replace("World Food Programme", "WFP")
            .replace("Food and Agriculture Organization of the United Nations", "FAO")
            .replace("International Organization for Migration", "IOM")
            .replace("UN High Commissioner for Refugees", "UNHCR")
            .replace("European Commission's Directorate-General for European Civil Protection", "ECHO")
            .replace("UN Mission in South Sudan", "UNMISS")
        )

    try:
        import requests as _req
        seen_titles = set()
        all_articles = []

        # Query 1: flood-specific articles (2025 season data)
        r1 = _req.post(url, json={
            "filter": {"field": "country.name", "value": "South Sudan"},
            "query": {"value": "floods", "fields": ["title"]},
            "fields": {"include": ["title","date.created","source.name","url"]},
            "sort": ["date.created:desc"], "limit": 6,
        }, timeout=8)
        if r1.ok:
            for item in r1.json().get("data", []):
                f = item.get("fields", {})
                src = f.get("source", [{}])
                title = f.get("title", "—")
                if title not in seen_titles:
                    seen_titles.add(title)
                    all_articles.append({
                        "title":  title,
                        "date":   f.get("date", {}).get("created", "")[:10],
                        "source": _shorten_src(src[0].get("name", "ReliefWeb") if src else "ReliefWeb"),
                        "url":    f.get("url", "https://reliefweb.int"),
                        "desc":   "",
                    })

        # Query 2: latest 2026 humanitarian updates
        r2 = _req.post(url, json={
            "filter": {"field": "country.name", "value": "South Sudan"},
            "query": {"value": "humanitarian flooding food insecurity 2026", "fields": ["title","body"]},
            "fields": {"include": ["title","date.created","source.name","url"]},
            "sort": ["date.created:desc"], "limit": 6,
        }, timeout=8)
        if r2.ok:
            for item in r2.json().get("data", []):
                f = item.get("fields", {})
                src = f.get("source", [{}])
                title = f.get("title", "—")
                if title not in seen_titles:
                    seen_titles.add(title)
                    all_articles.append({
                        "title":  title,
                        "date":   f.get("date", {}).get("created", "")[:10],
                        "source": _shorten_src(src[0].get("name", "ReliefWeb") if src else "ReliefWeb"),
                        "url":    f.get("url", "https://reliefweb.int"),
                        "desc":   "",
                    })

        # Sort by date descending and return top 9
        all_articles.sort(key=lambda x: x["date"], reverse=True)
        return all_articles[:9]
    except Exception:
        return []


SOURCE_IMGS = {
    "OCHA": "data:image/svg+xml;base64,PHN2ZyB2aWV3Qm94PSIwIDAgMTIwIDYwIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSIxMjAiIGhlaWdodD0iNjAiIGZpbGw9IiMwNzExMWEiLz48cGF0aCBkPSJNNSA0NSBRMjAgMTUgMzUgMzUgUTUwIDU1IDY1IDI1IFE4MCA1IDk1IDIwIFExMDggMzIgMTE4IDIyIiBmaWxsPSJub25lIiBzdHJva2U9IiMwZWE1ZTkiIHN0cm9rZS13aWR0aD0iMi41IiBvcGFjaXR5PSIwLjkiLz48cGF0aCBkPSJNNSA1MCBRMjAgMjAgMzUgNDAgUTUwIDYwIDY1IDMwIFE4MCAxMCA5NSAyNSBRMTA4IDM3IDExOCAyNyIgZmlsbD0iIzBlYTVlOSIgZmlsbC1vcGFjaXR5PSIwLjA4Ii8+PGNpcmNsZSBjeD0iMzUiIGN5PSIzNSIgcj0iNCIgZmlsbD0iI2Y4NTE0OSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIxIi8+PGNpcmNsZSBjeD0iNjUiIGN5PSIyNSIgcj0iNCIgZmlsbD0iI2Y1OWUwYiIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIxIi8+PGNpcmNsZSBjeD0iOTUiIGN5PSIyMCIgcj0iNCIgZmlsbD0iIzIyYzU1ZSIgc3Ryb2tlPSJ3aGl0ZSIgc3Ryb2tlLXdpZHRoPSIxIi8+PC9zdmc+",
    "UNHCR": "data:image/svg+xml;base64,PHN2ZyB2aWV3Qm94PSIwIDAgMTIwIDYwIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSIxMjAiIGhlaWdodD0iNjAiIGZpbGw9IiMwNzExMWEiLz48Y2lyY2xlIGN4PSI2MCIgY3k9IjMwIiByPSIyMiIgZmlsbD0ibm9uZSIgc3Ryb2tlPSIjYTc4YmZhIiBzdHJva2Utd2lkdGg9IjEiIG9wYWNpdHk9IjAuMyIvPjxjaXJjbGUgY3g9IjYwIiBjeT0iMzAiIHI9IjE0IiBmaWxsPSJub25lIiBzdHJva2U9IiNhNzhiZmEiIHN0cm9rZS13aWR0aD0iMSIgb3BhY2l0eT0iMC41Ii8+PGNpcmNsZSBjeD0iNjAiIGN5PSIzMCIgcj0iNiIgZmlsbD0iI2E3OGJmYSIgb3BhY2l0eT0iMC43Ii8+PGxpbmUgeDE9IjEwIiB5MT0iMzAiIHgyPSIzOCIgeTI9IjMwIiBzdHJva2U9IiNhNzhiZmEiIHN0cm9rZS13aWR0aD0iMSIgb3BhY2l0eT0iMC40IiBzdHJva2UtZGFzaGFycmF5PSIzLDIiLz48bGluZSB4MT0iODIiIHkxPSIzMCIgeDI9IjExMCIgeTI9IjMwIiBzdHJva2U9IiNhNzhiZmEiIHN0cm9rZS13aWR0aD0iMSIgb3BhY2l0eT0iMC40IiBzdHJva2UtZGFzaGFycmF5PSIzLDIiLz48L3N2Zz4=",
    "WFP": "data:image/svg+xml;base64,PHN2ZyB2aWV3Qm94PSIwIDAgMTIwIDYwIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSIxMjAiIGhlaWdodD0iNjAiIGZpbGw9IiMwNzExMWEiLz48cmVjdCB4PSI4IiB5PSIzOCIgd2lkdGg9IjE0IiBoZWlnaHQ9IjE2IiBmaWxsPSIjZjU5ZTBiIiBvcGFjaXR5PSIwLjYiIHJ4PSIxIi8+PHJlY3QgeD0iMjgiIHk9IjI4IiB3aWR0aD0iMTQiIGhlaWdodD0iMjYiIGZpbGw9IiNmNTllMGIiIG9wYWNpdHk9IjAuNyIgcng9IjEiLz48cmVjdCB4PSI0OCIgeT0iMTgiIHdpZHRoPSIxNCIgaGVpZ2h0PSIzNiIgZmlsbD0iI2Y1OWUwYiIgb3BhY2l0eT0iMC44NSIgcng9IjEiLz48cmVjdCB4PSI2OCIgeT0iMjIiIHdpZHRoPSIxNCIgaGVpZ2h0PSIzMiIgZmlsbD0iI2Y1OWUwYiIgb3BhY2l0eT0iMC43NSIgcng9IjEiLz48cmVjdCB4PSI4OCIgeT0iMzIiIHdpZHRoPSIxNCIgaGVpZ2h0PSIyMiIgZmlsbD0iI2Y1OWUwYiIgb3BhY2l0eT0iMC42IiByeD0iMSIvPjwvc3ZnPg==",
    "default": "data:image/svg+xml;base64,PHN2ZyB2aWV3Qm94PSIwIDAgMTIwIDYwIiB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciPjxyZWN0IHdpZHRoPSIxMjAiIGhlaWdodD0iNjAiIGZpbGw9IiMwNzExMWEiLz48cGF0aCBkPSJNMCA0MiBRMjAgMzAgNDAgMzggUTYwIDQ2IDgwIDI4IFExMDAgMTIgMTIwIDIyIiBmaWxsPSIjMGVhNWU5MmEiIHN0cm9rZT0iIzBlYTVlOSIgc3Ryb2tlLXdpZHRoPSIxLjUiLz48cGF0aCBkPSJNMCA1MCBRMjAgMzggNDAgNDYgUTYwIDU0IDgwIDM2IFExMDAgMjAgMTIwIDMwIiBmaWxsPSIjMGVhNWU5MTUiLz48Y2lyY2xlIGN4PSI0MCIgY3k9IjM4IiByPSI0IiBmaWxsPSIjZjg1MTQ5IiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjEuMiIvPjxjaXJjbGUgY3g9IjgwIiBjeT0iMjgiIHI9IjQiIGZpbGw9IiNmNTllMGIiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMS4yIi8+PC9zdmc+",
}

def render_intelligence_feed():
    """
    Render Intelligence Feed as a card grid — 3 cards per row.
    Each card shows source badge, title, date, description snippet,
    and a Read More link. Uses ReliefWeb RSS feed (no API key needed).
    Falls back to real OCHA articles when offline.
    """
    FALLBACK = [
        {"title": "South Sudan: Crisis, Conflict and Climate — ICG Analysis",
         "date": "2025-10-15", "source": "Crisis Group",
         "desc": "International Crisis Group monitors South Sudan's overlapping crises — conflict, displacement and flooding that compound humanitarian vulnerability.",
         "url": "https://southsudan.crisisgroup.org"},
        {"title": "UNICEF South Sudan: Climate Change and Flooding Response",
         "date": "2025-09-20", "source": "UNICEF",
         "desc": "UNICEF works to protect children from flooding in South Sudan, providing clean water, nutrition support and emergency education across affected states.",
         "url": "https://www.unicef.org/southsudan/what-we-do/climate-change-and-flooding"},
        {"title": "IFRC Emergency: South Sudan Floods — Appeal and Response",
         "date": "2025-09-12", "source": "IFRC",
         "desc": "Red Cross launched an emergency appeal as flooding displaced hundreds of thousands across Jonglei, Unity and Upper Nile states during the 2025 season.",
         "url": "https://www.ifrc.org/emergency/south-sudan-floods-0"},
        {"title": "UN News: Floods leave trail of destruction across South Sudan",
         "date": "2025-09-05", "source": "UN News",
         "desc": "UN agencies report severe flooding affecting over 900,000 people, destroying crops, homes and health infrastructure ahead of the lean season.",
         "url": "https://news.un.org/en/story/2025/09/1165841"},
        {"title": "South Sudan Crisis Explained — Concern Worldwide",
         "date": "2025-08-18", "source": "Concern",
         "desc": "Annual flooding, conflict and food insecurity push millions to the brink. Concern explains the compounding humanitarian crisis facing South Sudan.",
         "url": "https://concernusa.org/news/south-sudan-crisis-explained/"},
        {"title": "CLARE: Early Flood Warning Strengthens Community Resilience",
         "date": "2025-07-30", "source": "CLARE",
         "desc": "Community-based early warning systems for flooding in South Sudan are saving lives and enabling faster evacuation decisions across high-risk counties.",
         "url": "https://clareprogramme.org/impact/story-of-change-strengthening-early-warnings-about-flooding-in-south-sudan/"},
        {"title": "OCHA Flash Update #9: 1,024,500 affected across 29 counties — Oct 2025",
         "date": "2025-10-31", "source": "OCHA",
         "desc": "Jonglei and Unity account for 87% of those impacted. 355,000 displaced. Crops destroyed, health facilities damaged, roads impassable across six states.",
         "url": "https://www.unocha.org/publications/report/south-sudan/south-sudan-flooding-situation-flash-update-no-9-31-october-2025"},
        {"title": "OCHA Floods Snapshot: 960,600 people affected in 26 counties — Oct 23",
         "date": "2025-10-23", "source": "OCHA",
         "desc": "143 health facilities affected since September, 44 fully submerged. IOM and Ministry of Water signed agreement to bolster flood defences in Bor Town.",
         "url": "https://www.unocha.org/publications/report/south-sudan/south-sudan-floods-snapshot-23-october-2025"},
        {"title": "OCHA Snapshot: 1.35 million affected across 39 counties — Nov 13",
         "date": "2025-11-13", "source": "OCHA",
         "desc": "Jonglei, Unity and Lakes most affected. Waterborne diseases rising — cholera, hepatitis E, malaria. Schools and health facilities lost essential supplies.",
         "url": "https://www.unocha.org/publications/report/south-sudan/south-sudan-floods-snapshot-13-november-2025"},
    ]
    articles = _fetch_reliefweb()
    is_live  = len(articles) > 0
    if not articles:
        articles = FALLBACK

    # Source colour mapping
    SOURCE_COLORS = {
        "OCHA":   ("#0ea5e9", "rgba(14,165,233,0.12)"),
        "UNHCR":  ("#a78bfa", "rgba(167,139,250,0.12)"),
        "WFP":    ("#f59e0b", "rgba(245,158,11,0.12)"),
        "UNICEF": ("#22c55e", "rgba(34,197,94,0.12)"),
        "IOM":    ("#0ea5e9", "rgba(14,165,233,0.12)"),
        "WHO":    ("#22c55e", "rgba(34,197,94,0.12)"),
        "MSF":    ("#f85149", "rgba(248,81,73,0.12)"),
        "IFRC":   ("#f85149", "rgba(248,81,73,0.12)"),
    }

    # Status badge
    if is_live:
        status = (f"<span style='font-family:DM Mono,monospace;font-size:10px;"
                  f"color:{s.SUCCESS};padding:2px 8px;background:rgba(34,197,94,0.1);"
                  f"border:1px solid rgba(34,197,94,0.3);border-radius:4px;'>● live</span>")
    else:
        status = (f"<span style='font-family:DM Mono,monospace;font-size:10px;"
                  f"color:{s.MUTED};padding:2px 8px;background:{s.MUTED_BG};"
                  f"border:1px solid {s.BORDER};border-radius:4px;'>offline</span>")

    # Build cards — 3 per row using CSS grid
    cards_html = ""
    for a in articles:
        title = a["title"] if len(a["title"]) <= 72 else a["title"][:69] + "..."
        desc  = a.get("desc", "")
        if desc and len(desc) > 120:
            desc = desc[:117] + "..."
        src_color, src_bg = SOURCE_COLORS.get(a["source"], (s.MUTED, f"{s.MUTED_BG}"))
        url_   = a["url"]
        title_ = a["title"] if len(a["title"]) <= 72 else a["title"][:69] + "..."
        desc_  = a.get("desc", "")
        if desc_ and len(desc_) > 120:
            desc_ = desc_[:117] + "..."
        src_color, src_bg = SOURCE_COLORS.get(a["source"], (s.MUTED, s.MUTED_BG))
        src_   = a["source"]
        date_  = a["date"]
        img_src = SOURCE_IMGS.get(src_, SOURCE_IMGS["default"])
        cards_html += (
            f'<a href="{url_}" target="_blank" style="text-decoration:none;display:block;">'
            f'<div style="background:{s.CARD};border:1px solid {s.BORDER};'
            f'border-radius:4px;overflow:hidden;height:100%;box-sizing:border-box;">'
            f'<div style="width:100%;background:#0a1520;border-bottom:1px solid {s.BORDER};'
            f'display:flex;align-items:center;justify-content:center;padding:4px 0;">'
            f'<img src="{img_src}" style="width:100%;height:60px;object-fit:cover;display:block;"/>'
            f'</div>'
            f'<div style="padding:12px;">'
            f'<div style="display:flex;justify-content:space-between;'
            f'align-items:center;margin-bottom:8px;">'
            f'<span style="font-family:DM Mono,monospace;font-size:10px;font-weight:600;'
            f'color:{src_color};background:{src_bg};padding:2px 8px;border-radius:4px;">{src_}</span>'
            f'<span style="font-family:DM Mono,monospace;font-size:10px;color:{s.MUTED};">{date_}</span>'
            f'</div>'
            f'<div style="font-family:Inter,sans-serif;font-size:12px;font-weight:600;'
            f'color:{s.FG};line-height:1.5;margin-bottom:6px;">{title_}</div>'
            f'<div style="font-family:Inter,sans-serif;font-size:11px;color:{s.MUTED};'
            f'line-height:1.5;margin-bottom:10px;">{desc_}</div>'
            f'<div style="font-family:DM Mono,monospace;font-size:10px;color:{s.ACCENT};">'
            f'Read more ↗</div>'
            f'</div></div></a>'
        )

    grid_html = (
        f"<div style='display:grid;grid-template-columns:repeat(3,1fr);"
        f"gap:12px;padding:16px;'>"
        + cards_html +
        f"</div>"
    )

    sub_header = (
        f"<div style='font-family:DM Mono,monospace;font-size:10px;"
        f"color:{s.MUTED};padding:4px 16px 8px;"
        f"border-bottom:1px solid {s.BORDER};'>"
        f"South Sudan · Floods · via ReliefWeb OCHA</div>"
    )

    st.markdown(
        s.card_wrap(
            s.card_header("Intelligence Feed", status)
            + sub_header
            + grid_html
        ),
        unsafe_allow_html=True,
    )

# ════════════════════════════════════════════════════════════

# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════
st.sidebar.write("checkpoint 3: functions OK — MAIN reached")

for _k, _v in {
    "page": "Home", "hist_state": "All",
    "hist_min_iou": 0.65, "hist_min_pop": 0,
    "export_scope": "Single Event", "export_fmt": "GeoJSON",
    "export_layers": {"Flood Extent Polygon","Affected Villages","Health Facilities at Risk"},
    "export_events": {"EVT-2025-047"}, "export_done": False,
    "show_glossary": False,
}.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

if not st.session_state.get("sw_auth"):
    st.markdown("""<style>
[data-testid="stSidebar"]{display:none!important;}
#MainMenu,footer,header,[data-testid="stToolbar"],
[data-testid="stDecoration"],[data-testid="stStatusWidget"],
[data-testid="stBottom"]{display:none!important;}
</style>""", unsafe_allow_html=True)

    _, mid, _ = st.columns([1, 1, 1])
    with mid:
        st.markdown(f"""
<div style='text-align:center;margin:60px 0 28px;'>
  <div style='font-family:Barlow Condensed,sans-serif;font-size:36px;
    font-weight:800;color:{s.FG};letter-spacing:.08em;'>SUDDWATCH</div>
  <div style='font-size:13px;color:{s.MUTED};margin-top:4px;'>
    Flood Detection &amp; Alert System &middot; Greater Upper Nile</div>
</div>""", unsafe_allow_html=True)

        _email = st.text_input("Email", placeholder="you@organisation.org",
                               key="sw_email_input")
        _pass  = st.text_input("Password", type="password",
                               key="sw_pass_input")

        if st.button("Sign in", use_container_width=True,
                     type="primary", key="sw_signin_btn"):
            _u = DEMO_USERS.get(_email.strip().lower())
            if _u and _u["password"] == _pass:
                st.session_state["sw_auth"] = {
                    "email": _email.strip().lower(),
                    "name":  _u["name"],
                    "role":  _u["role"],
                }
                st.rerun()
            else:
                st.error("Incorrect email or password.")

        st.markdown(f"""
<div style='margin-top:12px;padding:12px;background:{s.CARD};
  border:1px solid {s.BORDER};border-radius:8px;
  font-size:12px;color:{s.MUTED};'>
  <div style='font-size:10px;font-family:DM Mono,monospace;
    text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;'>
    Demo accounts</div>
  <div style='margin-bottom:3px;'>
    <code style='color:{s.FG};'>admin@suddwatch.org</code>
    &nbsp;/&nbsp;<code style='color:{s.FG};'>admin123</code></div>
  <div>
    <code style='color:{s.FG};'>coord@ocha.org</code>
    &nbsp;/&nbsp;<code style='color:{s.FG};'>ocha2025</code></div>
</div>""", unsafe_allow_html=True)

    st.stop()

st.write("A: after auth gate")
st.markdown(s.GLOBAL_CSS, unsafe_allow_html=True)
st.write("B: GLOBAL_CSS ok")
render_sidebar()
st.write("C: render_sidebar ok")
event = _cached_active_event()
st.write("D: db ok")
last_evt = event.get("date_utc", "—") if event else "—"
render_topbar(last_evt)
st.write("E: topbar ok")
render_breadcrumb({"Home":"Home"}.get(st.session_state.page,""))
st.write("F: breadcrumb ok")
page = st.session_state.page
if   page == "Home":        page_home()
elif page == "History":     page_history()
elif page == "Performance": page_performance()
elif page == "Export":      page_export()
st.write("G: done")
