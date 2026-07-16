# ============================================================
# SuddWatch — Operational Flood Detection Dashboard
# dashboard/app.py  v4.0
#
# Flow:
#   Unauthenticated → Landing page → Sign In/Up → Dashboard
#   Sidebar: Dark / Light / Auto theme switcher
#   Roles: Admin (full access) | User (operational view)
#
# Course: SWE3090 | Student: Madut Chan (671336) | USIU-Africa
# ============================================================

import json, sys, logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

try:
    import folium
    from streamlit_folium import st_folium
    FOLIUM_OK = True
except ImportError:
    FOLIUM_OK = False

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import Config, setup_logging
from src.database import DatabaseManager

st.set_page_config(
    page_title="SuddWatch",
    page_icon="🌊",
    layout="wide",
    initial_sidebar_state="expanded",
)
setup_logging()
logger = logging.getLogger(__name__)

FONTS = """<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=Barlow+Condensed:wght@600;700;800&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">"""

# ════════════════════════════════════════════════════════════
# THEME SYSTEM — Dark / Light / Auto
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
            padding:12px 16px;font-family:Inter,sans-serif;font-size:13px;color:#c9d1d9;">
          <div style="font-weight:600;font-size:14px;margin-bottom:8px;">Map legend</div>
          <div>🔵 Flood extent</div><div>🔴 High risk — evacuate</div>
          <div>🟠 Medium risk — alert</div><div>🟢 Low risk — monitor</div><div>➕ Health facility at risk</div></div>"""
        m.get_root().html.add_child(folium.Element(legend))
        st_folium(m, height=440, use_container_width=True, returned_objects=[])
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

def is_logged_in():  return st.session_state.get("logged_in", False)
def current_user():  return st.session_state.get("user", {})
def logout():
    for k in ["logged_in", "user", "auth_page"]:
        st.session_state.pop(k, None)
    st.rerun()

# ════════════════════════════════════════════════════════════
# LANDING PAGE
# ════════════════════════════════════════════════════════════


# ════════════════════════════════════════════════════════════
# page_landing(t)  — SuddWatch landing page v5
# Drop-in replacement for the function in app.py
# ════════════════════════════════════════════════════════════


def page_landing(t):
    import streamlit.components.v1 as components
    from pathlib import Path

    # Kill every Streamlit wrapper element
    st.markdown("""<style>
* {box-sizing: border-box;}
html, body {margin:0;padding:0;overflow:hidden;}
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
[data-testid="stAppViewBlockContainer"],
[data-testid="stMainBlockContainer"],
[data-testid="stMain"],
[data-testid="stVerticalBlock"],
[data-testid="stVerticalBlockBorderWrapper"],
.main, .block-container, section {
    padding: 0 !important;
    margin: 0 !important;
    max-width: 100% !important;
    width: 100% !important;
}
#MainMenu, header, footer,
[data-testid="stToolbar"],
[data-testid="stDecoration"],
[data-testid="stStatusWidget"],
[data-testid="stBottom"],
[data-testid="stBottomBlockContainer"] {
    display: none !important;
    height: 0 !important;
    min-height: 0 !important;
    overflow: hidden !important;
    visibility: hidden !important;
}
/* The iframe itself */
iframe {
    display: block !important;
    border: none !important;
    margin: 0 !important;
    padding: 0 !important;
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    width: 100vw !important;
    height: 100vh !important;
    z-index: 9999 !important;
}
</style>""", unsafe_allow_html=True)

    html_path = Path(__file__).parent / 'landing.html'
    if not html_path.exists():
        html_path = Path('/home/claude/landing.html')

    html = html_path.read_text()

    current_theme = st.session_state.get("theme_choice", "dark")
    signin_script = """
<script>
(function(){
    // Read saved theme from localStorage, fallback to server-rendered default
    var saved = localStorage.getItem('suddwatch_theme');
    var __theme = saved || '""" + current_theme + """';

    // Apply theme class immediately (before paint)
    if(__theme === 'light'){
        document.documentElement.classList.add('light-mode');
    } else {
        document.documentElement.classList.remove('light-mode');
    }

    // Sign in — form submit to _top
    window.__suddSignin = function(){
        var f = document.createElement('form');
        f.method = 'GET';
        f.action = (window.top || window.parent).location.href.split('?')[0];
        f.target = '_top';
        var i = document.createElement('input');
        i.type='hidden'; i.name='go'; i.value='signin';
        f.appendChild(i);
        var i2 = document.createElement('input');
        i2.type='hidden'; i2.name='theme'; i2.value=__theme;
        f.appendChild(i2);
        document.body.appendChild(f);
        f.submit();
        document.body.removeChild(f);
    };

    // Theme toggle — instant, no reload, no new tab
    window.__suddTheme = function(){
        var next = __theme === 'dark' ? 'light' : 'dark';
        __theme = next;
        localStorage.setItem('suddwatch_theme', next);
        if(next === 'light'){
            document.documentElement.classList.add('light-mode');
        } else {
            document.documentElement.classList.remove('light-mode');
        }
        // Update button icon
        var btn = document.getElementById('themeToggleBtn');
        if(btn){
            btn.innerHTML = next === 'dark'
                ? '<i class=\"ti ti-sun\"></i>'
                : '<i class=\"ti ti-moon\"></i>';
        }
    };

    // Set correct icon on load
    document.addEventListener('DOMContentLoaded', function(){
        var btn = document.getElementById('themeToggleBtn');
        if(btn){
            btn.innerHTML = __theme === 'dark'
                ? '<i class=\"ti ti-sun\"></i>'
                : '<i class=\"ti ti-moon\"></i>';
            btn.title = 'Toggle theme';
        }
    });
})();
</script>"""
    html = html.replace('</head>', signin_script + '</head>')
    html = html.replace(
        "window.parent.postMessage({cmd:'signin'}, '*');",
        "window.__suddSignin();"
    )

    html = (html
        .replace('__CA2__', t['card2'])
        .replace('__AC__',  t['accent'])
        .replace('__SU__',  t['success'])
        .replace('__WA__',  t['warning'])
        .replace('__DA__',  t['danger'])
        .replace('__BG__',  t['bg'])
        .replace('__CA__',  t['card'])
        .replace('__BO__',  t['border'])
        .replace('__B2__',  t['border2'])
        .replace('__TH__',  t['text_h'])
        .replace('__TM__',  t['text_m'])
        .replace('__TX__',  t['text'])
    )

    components.html(html, height=800, scrolling=True)


def page_auth(t):
    st.markdown(FONTS, unsafe_allow_html=True)
    st.markdown(css(t), unsafe_allow_html=True)

    _, mid, _ = st.columns([1, 1.4, 1])
    with mid:
        # Logo
        st.markdown(
            f"<div style='text-align:center;padding:40px 0 24px;'>"
            f"<div style='display:flex;align-items:center;justify-content:center;gap:10px;margin-bottom:6px;'>"
            f"<svg width='28' height='28' viewBox='0 0 28 28' fill='none'>"
            f"<path d='M14 4C14 4 8 11 8 16C8 19.3 10.7 22 14 22C17.3 22 20 19.3 20 16C20 11 14 4 14 4Z' fill='{t['accent']}' opacity='.9'/>"
            f"<path d='M3 23Q7 19.5 11 23Q15 26.5 19 23Q23 19.5 27 23' fill='none' stroke='{t['accent']}' stroke-width='1.6' stroke-linecap='round' opacity='.6'/>"
            f"</svg>"
            f"<span style='font-family:Barlow Condensed,sans-serif;font-size:26px;font-weight:800;"
            f"color:{t['text_h']};letter-spacing:.08em;'>SUDDWATCH</span></div>"
            f"<div style='font-size:13px;color:{t['text_m']};'>Flood Detection &amp; Alert System</div></div>",
            unsafe_allow_html=True,
        )

        # Card wrapper
        st.markdown(
            f"<div style='background:{t['card']};border:1px solid {t['border']};"
            f"border-radius:12px;padding:28px 24px;'>",
            unsafe_allow_html=True,
        )

        tab_in, tab_up = st.tabs(["🔐  Sign In", "✍️  Request Access"])

        with tab_in:
            st.markdown(
                f"<div style='font-size:14px;color:{t['text_m']};margin-bottom:16px;line-height:1.6;'>"
                f"Enter your credentials to access the operational dashboard.</div>",
                unsafe_allow_html=True,
            )
            email    = st.text_input("Email address", placeholder="you@organisation.org", key="li_email")
            password = st.text_input("Password", type="password", placeholder="Your password", key="li_pw")
            role_choice = st.selectbox(
                "Access level",
                ["👤  User — View operational data", "🔑  Admin — Full system access"],
                key="li_role",
            )
            if st.button("Sign in →", use_container_width=True, key="btn_li", type="primary"):
                rec = DEMO_USERS.get(email.strip().lower())
                if rec and rec["password"] == password:
                    if "Admin" in role_choice and rec["role"] != "Admin":
                        st.error("⚠️ Your account does not have Admin access.")
                    else:
                        st.session_state.update({
                            "logged_in": True,
                            "user": {"email": email, "name": rec["name"], "role": rec["role"]},
                        })
                        st.session_state.pop("auth_page", None)
                        st.rerun()
                else:
                    st.error("❌ Invalid email or password.")

            st.markdown(
                f"<div style='margin-top:14px;padding:12px 14px;background:{t['bg']};"
                f"border-radius:8px;border:1px solid {t['border']};"
                f"font-size:13px;color:{t['text_m']};line-height:1.8;'>"
                f"<strong style='color:{t['text_h']};'>Demo accounts</strong><br>"
                f"Admin: <code>admin@suddwatch.org</code> / <code>admin123</code><br>"
                f"User: <code>coord@ocha.org</code> / <code>ocha2025</code></div>",
                unsafe_allow_html=True,
            )

        with tab_up:
            st.markdown(
                f"<div style='font-size:14px;color:{t['text_m']};margin-bottom:16px;line-height:1.6;'>"
                f"New accounts are reviewed by an administrator before activation.</div>",
                unsafe_allow_html=True,
            )
            new_name  = st.text_input("Full name", placeholder="Dr. Jane Doe", key="ru_name")
            new_org   = st.text_input("Organisation", placeholder="UN OCHA / IFRC / REACH", key="ru_org")
            new_email = st.text_input("Work email", placeholder="you@organisation.org", key="ru_email")
            new_pw    = st.text_input("Password", type="password", key="ru_pw")
            new_pw2   = st.text_input("Confirm password", type="password", key="ru_pw2")
            st.radio("Requested access level",
                     ["👤  User — View operational data", "🔑  Admin — Full system management"],
                     key="ru_role")
            if st.button("Submit request", use_container_width=True, key="btn_ru"):
                if not all([new_name, new_org, new_email, new_pw]):
                    st.error("Please complete all fields.")
                elif new_pw != new_pw2:
                    st.error("Passwords do not match.")
                elif "@" not in new_email:
                    st.error("Please enter a valid email address.")
                else:
                    st.success(
                        f"✅ Request submitted for {new_name} ({new_org}). "
                        f"An administrator will activate your account within 24 hours."
                    )

        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        if st.button("← Back to home", key="btn_back", use_container_width=True):
            st.session_state.pop("auth_page", None)
            st.rerun()

# ════════════════════════════════════════════════════════════
# CACHED RESOURCES
# ════════════════════════════════════════════════════════════
@st.cache_resource
def get_config(): return Config()

@st.cache_resource
def get_db(_cfg): return DatabaseManager(_cfg)

@st.cache_data(ttl=300)
def load_latest(_db): return _db.get_latest_event() or {}

@st.cache_data(ttl=300)
def load_events(_db, filters=None): return _db.query_events(filters=filters)

@st.cache_data(ttl=300)
def load_metrics(_db): return _db.query_performance_metrics()

def load_summary(path):
    if not path or not Path(path).exists(): return {}
    try:
        with open(path) as f: return json.load(f)
    except Exception: return {}

# ════════════════════════════════════════════════════════════
# SIDEBAR — nav + theme switcher + glossary + user info
# ════════════════════════════════════════════════════════════
def render_sidebar(metrics, t):
    user = current_user()
    with st.sidebar:
        # Logo
        st.markdown(
            f"<div style='padding:18px 16px 10px;display:flex;align-items:center;gap:10px;'>"
            f"<svg width='22' height='22' viewBox='0 0 28 28' fill='none'>"
            f"<path d='M14 4C14 4 8 11 8 16C8 19.3 10.7 22 14 22C17.3 22 20 19.3 20 16C20 11 14 4 14 4Z' fill='{t['accent']}' opacity='.9'/>"
            f"<path d='M3 23Q7 19.5 11 23Q15 26.5 19 23Q23 19.5 27 23' fill='none' stroke='{t['accent']}' stroke-width='1.6' stroke-linecap='round' opacity='.6'/>"
            f"</svg>"
            f"<span style='font-family:Barlow Condensed,sans-serif;font-size:18px;"
            f"font-weight:800;color:{t['text_h']};letter-spacing:.07em;'>SUDDWATCH</span></div>",
            unsafe_allow_html=True,
        )

        # User info
        if user:
            rc = t['accent'] if user.get('role') == 'Admin' else t['success']
            st.markdown(
                f"<div style='padding:9px 16px;background:{t['bg']};"
                f"border-top:1px solid {t['border']};border-bottom:1px solid {t['border']};'>"
                f"<div style='font-size:14px;color:{t['text']};font-weight:500;'>{user.get('name','')}</div>"
                f"<div style='font-size:12px;color:{rc};'>{user.get('role','')} access</div></div>",
                unsafe_allow_html=True,
            )

        st.markdown(f"<div style='height:1px;background:{t['border']};margin:8px 0 10px;'></div>",
                    unsafe_allow_html=True)

        # Navigation
        st.markdown(
            f"<div style='padding:0 16px 6px;font-size:10px;letter-spacing:.1em;"
            f"text-transform:uppercase;color:{t['border2']};font-weight:700;'>NAVIGATION</div>",
            unsafe_allow_html=True,
        )
        nav_opts = ["🏠  Home", "📅  History", "📈  Performance", "📤  Export"]
        if user.get("role") == "Admin":
            nav_opts.append("⚙️  Admin")
        page = st.radio("nav", nav_opts, label_visibility="collapsed")

        st.markdown(f"<div style='height:1px;background:{t['border']};margin:10px 0;'></div>",
                    unsafe_allow_html=True)

        # ── THEME SWITCHER ──────────────────────────────────
        st.markdown(
            f"<div style='padding:0 16px 6px;font-size:10px;letter-spacing:.1em;"
            f"text-transform:uppercase;color:{t['border2']};font-weight:700;'>DISPLAY THEME</div>",
            unsafe_allow_html=True,
        )
        theme_labels = ["🌙  Dark", "☀️  Light", "🔄  Auto"]
        theme_keys   = ["dark",     "light",     "auto"]
        cur = st.session_state.get("theme_choice", "dark")
        cur_idx = theme_keys.index(cur) if cur in theme_keys else 0
        sel = st.radio("theme", theme_labels, label_visibility="collapsed",
                       key="theme_radio", index=cur_idx)
        new_t = theme_keys[theme_labels.index(sel)]
        if new_t != cur:
            st.session_state["theme_choice"] = new_t
            st.rerun()

        st.markdown(f"<div style='height:1px;background:{t['border']};margin:10px 0;'></div>",
                    unsafe_allow_html=True)

        # Glossary toggle
        st.markdown(
            f"<div style='padding:0 16px 6px;font-size:10px;letter-spacing:.1em;"
            f"text-transform:uppercase;color:{t['border2']};font-weight:700;'>HELP</div>",
            unsafe_allow_html=True,
        )
        st.checkbox("📖  Show glossary", key="show_glossary",
                    value=st.session_state.get("show_glossary", False))

        # System status
        total = int(metrics.get("total_events", 0) or 0)
        dot_c = t['success'] if total > 0 else t['text_m']
        st.markdown(
            f"<div style='padding:10px 16px 14px;'>"
            f"<div style='display:flex;align-items:center;gap:6px;'>"
            f"<div style='width:7px;height:7px;border-radius:50%;background:{dot_c};'></div>"
            f"<span style='font-size:13px;color:{dot_c};font-weight:500;'>"
            f"{'System operational' if total > 0 else 'Awaiting pipeline'}</span></div>"
            f"<div style='font-size:11px;color:{t['border2']};margin-top:3px;'>v4.0 · Sudd Basin</div></div>",
            unsafe_allow_html=True,
        )

        if st.button("🚪  Sign out", key="btn_logout", use_container_width=True):
            logout()

    return page

# ════════════════════════════════════════════════════════════
# PAGE — HOME
# ════════════════════════════════════════════════════════════
def page_home(cfg, db, t):
    latest  = load_latest(db) if db else {}
    metrics = load_metrics(db) if db else {}
    user    = current_user()

    last_evt = "—"
    if latest.get("event_timestamp"):
        try:
            dt = datetime.fromisoformat(str(latest["event_timestamp"]))
            last_evt = dt.strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            last_evt = str(latest["event_timestamp"])[:16]

    topbar(t, last_evt, f"{user.get('name','')} ({user.get('role','')})")
    breadcrumb("Dashboard — Live Flood Event", t)

    risk     = load_summary(str(latest.get("geotiff_path","")).replace("_flood_mask.tif","_flood_mask_risk_summary.json"))
    flood_ha = float(latest.get("flood_extent_ha") or 0)
    pop      = int(risk.get("affected_population_estimate") or 0)
    avg_lat  = float((metrics.get("avg_latency_seconds") or 0)) / 60
    iou_val  = float(metrics.get("avg_iou") or 0)
    total_ev = int(metrics.get("total_events") or 0)
    villages = risk.get("affected_villages", [])
    roads    = risk.get("inaccessible_roads", [])
    health   = risk.get("health_facilities_at_risk", [])

    if st.session_state.get("show_glossary"):
        glossary_panel(t)

    context_box(
        f"<strong style='color:{t['text_h']};'>What am I looking at?</strong> "
        f"Results of the latest automated flood detection cycle. "
        f"<span style='color:{t['danger']};'>Red</span> = urgent. "
        f"<span style='color:{t['warning']};'>Amber</span> = caution. "
        f"<span style='color:{t['success']};'>Green</span> = within target.", t
    )

    st.markdown("<div style='padding:10px 20px 0;'>", unsafe_allow_html=True)
    kpi_strip([
        ("Flood extent", f"<span style='color:{t['accent']};'>{flood_ha:,.0f} ha</span>",
         "Jonglei · Unity · Upper Nile",
         "Total flooded area. 1 hectare ≈ one football pitch."),
        ("Affected population", f"<span style='color:{t['warning']};'>{pop:,}</span>",
         "Estimated within flood area",
         "Estimated using WorldPop 100m population grid."),
        ("Alerts sent", f"<span style='color:{t['text']};'>{total_ev}</span>",
         "SMS + email this cycle",
         "Total alerts dispatched via Twilio SMS and Gmail SMTP."),
        ("Alert latency", f"<span style='color:{t['success'] if avg_lat<=60 else t['warning']};'>{avg_lat:.0f} min</span>",
         f"Target ≤ 60 min — {'✓ met' if avg_lat<=60 else '✗ exceeded'}",
         "Time from satellite pass to first alert delivery."),
        ("Detection accuracy", f"<span style='color:{t['success'] if iou_val>=0.65 else t['warning']};'>{iou_val:.2f}</span>",
         f"IoU score — {'✓ good' if iou_val>=0.65 else '✗ below target'}",
         "IoU measures how accurately the flood area was mapped. Above 0.65 is good."),
        ("Season events", f"<span style='color:{t['text']};'>{total_ev}</span>",
         "2025 flood season total",
         "Total flood detection cycles completed this season."),
    ], t)
    st.markdown("</div>", unsafe_allow_html=True)

    # Map + sidebar panels
    st.markdown("<div style='padding:10px 20px 0;'>", unsafe_allow_html=True)
    map_col, right_col = st.columns([5, 1], gap="small")

    with map_col:
        st.markdown(
            f"<div style='font-family:Barlow Condensed,sans-serif;font-size:15px;"
            f"letter-spacing:.06em;text-transform:uppercase;color:{t['text_h']};"
            f"font-weight:700;margin-bottom:8px;'>🗺️ Flood Extent Map — Greater Upper Nile</div>",
            unsafe_allow_html=True,
        )
        if FOLIUM_OK:
            st.markdown(f"<div style='font-size:13px;color:{t['text_m']};margin-bottom:8px;'>"
                        f"Click pins for village details. Click blue areas for flood zone info. Scroll to zoom.</div>",
                        unsafe_allow_html=True)
        render_map(t)
        st.markdown(
            f"<div style='font-size:13px;color:{t['text_m']};margin-top:8px;"
            f"padding:10px 14px;background:{t['card']};border:1px solid {t['border']};border-radius:8px;'>"
            f"<strong style='color:{t['text_h']};'>Map colours:</strong> "
            f"<span style='color:{t['danger']};'>● Red</span> = high risk (evacuate). "
            f"<span style='color:{t['warning']};'>● Orange</span> = medium risk (alert). "
            f"<span style='color:{t['success']};'>● Green</span> = low risk (monitor). "
            f"<span style='color:{t['accent']};'>■ Blue shading</span> = flood extent.</div>",
            unsafe_allow_html=True,
        )

    with right_col:
        def prog(label, pct, colour):
            return (f"<div style='margin-bottom:10px;'>"
                    f"<div style='display:flex;justify-content:space-between;margin-bottom:4px;'>"
                    f"<span style='font-size:13px;color:{t['text_m']};'>{label}</span>"
                    f"<span style='font-family:DM Mono,monospace;font-size:12px;color:{colour};'>{pct/100:.2f}</span></div>"
                    f"<div style='background:{t['border']};border-radius:3px;height:5px;'>"
                    f"<div style='background:{colour};width:{pct}%;height:5px;border-radius:3px;'></div></div></div>")

        iou_pct = int(iou_val * 100)
        st.markdown(card(
            card_header("Active event", t)
            + f"<div style='margin-bottom:10px;'>{lbl('Flood extent',t['text_m'])}<br>"
            + f"<span style='font-family:Barlow Condensed,sans-serif;font-size:22px;font-weight:700;color:{t['accent']};'>{flood_ha:,.0f} ha</span></div>"
            + f"<div style='margin-bottom:10px;'>{lbl('Affected population',t['text_m'])}<br>"
            + f"<span style='font-family:Barlow Condensed,sans-serif;font-size:22px;font-weight:700;color:{t['warning']};'>{pop:,}</span></div>"
            + f"<div style='margin-bottom:10px;'>{lbl('Alerts sent',t['text_m'])}<br>"
            + f"<span style='font-family:Barlow Condensed,sans-serif;font-size:22px;font-weight:700;color:{t['text']};'>{total_ev}</span></div>"
            + f"<div>{lbl('Latency',t['text_m'])}<br>"
            + f"<span style='font-family:Barlow Condensed,sans-serif;font-size:22px;font-weight:700;"
            + f"color:{t['success'] if avg_lat<=60 else t['warning']};'>{avg_lat:.0f} min</span></div>",
            t
        ), unsafe_allow_html=True)

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        st.markdown(card(
            card_header("Detection quality", t)
            + prog("IoU accuracy", iou_pct, t['accent'])
            + prog("Confidence", min(100, iou_pct+13), t['success'])
            + prog("Cloud cover", 12, t['warning']),
            t
        ), unsafe_allow_html=True)

        st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)
        stages = [("Data acquisition",True),("Preprocessing",True),
                  ("Flood detection",True),("Risk assessment",True),("Alert dispatch",True)]
        rows_s = "".join(
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:7px;'>"
            f"<span style='font-size:13px;color:{t['text_m']};'>{n}</span>"
            f"{badge('OK','green') if ok else badge('ERR','red')}</div>"
            for n, ok in stages
        )
        st.markdown(card(card_header("Pipeline status", t) + rows_s, t), unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # Data tables
    st.markdown("<div style='padding:10px 20px 16px;'>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3, gap="small")

    demo_v = [("Bor South",12400,82,"red"),("Leer",8200,71,"red"),
              ("Akobo",6100,58,"amber"),("Nasir",4300,31,"amber"),("Twic East",3200,18,"green")]
    with c1:
        st.markdown(card_header("Affected villages", t, f"{len(villages) or 5}"), unsafe_allow_html=True)
        hdr = th("Village",t)+th("Population",t,"right")+th("Risk",t,"center")+th("Action",t,"right")
        rows = ""
        for name, pop_v, rp, rc in demo_v:
            ac_badge = "red" if rp>=75 else "cyan" if rp>=50 else "blue"
            act = "Evacuate" if rp>=75 else "Alert" if rp>=50 else "Monitor"
            rows += (f"<tr>{td(name,t)}{td(f'{pop_v:,}',t,t['text_m'],'right')}"
                     f"<td style='padding:7px 9px;text-align:center;border-bottom:1px solid {t['border']};'>{badge(f'{rp}%',rc)}</td>"
                     f"<td style='padding:7px 9px;text-align:right;border-bottom:1px solid {t['border']};'>{badge(act,ac_badge)}</td></tr>")
        st.markdown(card(table_wrap(hdr, rows), t), unsafe_allow_html=True)

    demo_r = [("A1 Highway","Primary","Air only"),("Bor–Malakal Rd","Secondary","Boat"),
              ("Unity Rd B7","Track","Via D11"),("Nasir Access","Track","None")]
    with c2:
        st.markdown(card_header("Inaccessible roads", t, f"{len(roads) or 4}"), unsafe_allow_html=True)
        hdr = th("Road",t)+th("Type",t)+th("Alternative",t)
        rows = ""
        for name, rtype, alt in demo_r:
            rows += f"<tr>{td(name,t)}{td(rtype,t,t['text_m'])}{td(alt,t,t['text_m'])}</tr>"
        st.markdown(card(table_wrap(hdr, rows), t), unsafe_allow_html=True)

    demo_h = [("Malakal Teaching Hosp.","Hospital","At Risk"),("Bentiu State Hospital","Hospital","At Risk"),
              ("Akobo PHC","Health Post","At Risk"),("Leer Clinic","Clinic","Monitoring")]
    with c3:
        st.markdown(card_header("Health facilities", t, f"{len(health) or 4}"), unsafe_allow_html=True)
        hdr = th("Name",t)+th("Type",t)+th("Status",t)
        rows = ""
        for name, ftype, status in demo_h:
            sc = "red" if "Risk" in status else "amber"
            rows += (f"<tr>{td(name,t)}{td(ftype,t,t['text_m'])}"
                     f"<td style='padding:7px 9px;border-bottom:1px solid {t['border']};'>{badge(status,sc)}</td></tr>")
        st.markdown(card(table_wrap(hdr, rows), t), unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# PAGE — HISTORY
# ════════════════════════════════════════════════════════════
def page_history(cfg, db, t):
    events_df = load_events(db) if db else pd.DataFrame()
    user = current_user()
    topbar(t, "—", f"{user.get('name','')} ({user.get('role','')})")
    breadcrumb("History — Flood Events Archive", t)
    if st.session_state.get("show_glossary"): glossary_panel(t)
    context_box("An archive of every flood detection event this season. Click any row to expand its full details.", t)

    total = len(events_df)
    st.markdown("<div style='padding:10px 20px 0;'>", unsafe_allow_html=True)
    kpi_strip([
        ("Total events", f"<span style='color:{t['text']};'>{total}</span>", "2025 season", ""),
        ("Peak month", f"<span style='color:{t['warning']};'>August</span>", "12 events", ""),
        ("Max extent", f"<span style='color:{t['danger']};'>1,540 ha</span>", "Aug 2025", ""),
        ("Total affected", f"<span style='color:{t['text']};'>31,200</span>", "cumulative", ""),
    ], t)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='padding:10px 20px 0;'>", unsafe_allow_html=True)
    ch, fi = st.columns([2,1], gap="small")
    with fi:
        st.markdown(card_header("Filter events", t), unsafe_allow_html=True)
        st.date_input("From", value=datetime(2025,8,1).date(), label_visibility="visible", key="hd1")
        st.date_input("To", value=datetime(2025,10,31).date(), label_visibility="visible", key="hd2")
        st.radio("State", ["All","Jonglei","Unity","Upper Nile"], horizontal=True, key="hstate")
        st.slider("Min IoU accuracy", 0.0, 1.0, 0.0, 0.05, key="hiou")
        if st.button("Apply filters", key="hap", use_container_width=True): st.cache_data.clear()

    with ch:
        months=["May","Jun","Jul","Aug","Sep","Oct"]; ev_cnt=[2,5,8,12,10,6]; ha_tot=[800,1500,2200,3400,2800,1700]
        fig = go.Figure()
        fig.add_bar(x=months, y=ev_cnt, name="Events", marker_color=t['accent'], opacity=0.85, yaxis="y")
        fig.add_bar(x=months, y=ha_tot, name="Hectares", marker_color=t['accent2'], opacity=0.5, yaxis="y2")
        fig.update_layout(**pl(t), barmode="group", height=280,
                          yaxis=dict(title="Events", gridcolor=t['border']),
                          yaxis2=dict(title="Hectares flooded", overlaying="y", side="right", gridcolor=t['border']),
                          legend=dict(font=dict(size=13), bgcolor="transparent", orientation="h", y=-0.25))
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='padding:10px 20px 16px;'>", unsafe_allow_html=True)
    st.markdown(card_header("Event log", t, "click a row to expand"), unsafe_allow_html=True)
    for eid, edt, lat, iou_v, fha, fpop, state, county in [
        ("EVT-2025-047","2025-10-23 14:30 UTC",45,0.71,1200,5000,"Jonglei","Bor South"),
        ("EVT-2025-041","2025-10-08 09:15 UTC",52,0.68, 980,3800,"Jonglei","Akobo"),
        ("EVT-2025-033","2025-09-19 06:45 UTC",38,0.79,1540,7200,"Jonglei","Twic East"),
        ("EVT-2025-028","2025-09-02 11:20 UTC",61,0.63, 760,2900,"Unity",  "Leer"),
        ("EVT-2025-021","2025-08-14 16:55 UTC",44,0.74,1100,4400,"Upper Nile","Malakal"),
    ]:
        with st.expander(f"📅  {edt}  ·  {eid}  ·  {state}, {county}"):
            cols = st.columns(6)
            for col, (lbl_txt, val, color) in zip(cols, [
                ("Latency", f"{lat} min", t['success'] if lat<=60 else t['warning']),
                ("IoU accuracy", f"{iou_v:.2f}", t['success'] if iou_v>=0.65 else t['warning']),
                ("Flood extent", f"{fha:,} ha", t['accent']),
                ("Affected people", f"{fpop:,}", t['warning']),
                ("State", state, t['text']),
                ("County", county, t['text']),
            ]):
                col.markdown(f"{lbl(lbl_txt,t['text_m'])}<br>"
                             f"<span style='font-family:Barlow Condensed,sans-serif;font-size:20px;"
                             f"font-weight:700;color:{color};'>{val}</span>",
                             unsafe_allow_html=True)
            bc1, bc2, bc3 = st.columns(3)
            with bc1: st.button("📍 GeoJSON", key=f"geo_{eid}", disabled=True, use_container_width=True)
            with bc2: st.button("📄 PDF report", key=f"pdf_{eid}", disabled=True, use_container_width=True)
            with bc3: st.button("📊 CSV data", key=f"csv_{eid}", disabled=True, use_container_width=True)
    st.markdown("</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# PAGE — PERFORMANCE
# ════════════════════════════════════════════════════════════
def page_performance(cfg, db, t):
    metrics = load_metrics(db) if db else {}
    user = current_user()
    topbar(t, "—", f"{user.get('name','')} ({user.get('role','')})")
    breadcrumb("Performance — System Metrics", t)
    if st.session_state.get("show_glossary"): glossary_panel(t)
    context_box("Monitors whether SuddWatch is meeting its performance targets. Green = target met. Amber = borderline. Red = missed.", t)

    avg_lat   = float((metrics.get("avg_latency_seconds") or 0)) / 60
    avg_iou   = float(metrics.get("avg_iou") or 0)
    success_r = float(metrics.get("alert_success_rate") or 0)
    total_ev  = int(metrics.get("total_events") or 0)

    st.markdown("<div style='padding:10px 20px 0;'>", unsafe_allow_html=True)
    kpi_strip([
        ("Average latency", f"<span style='color:{t['success'] if avg_lat<=60 else t['warning']};'>{avg_lat:.0f} min</span>",
         f"Target ≤ 60 min — {'✓ met' if avg_lat<=60 else '✗ exceeded'}", ""),
        ("SLA compliance", f"<span style='color:{t['success']};'>91.5%</span>",
         f"{int(total_ev*0.915)} of {total_ev} events on time", ""),
        ("Avg IoU accuracy", f"<span style='color:{t['accent']};'>{avg_iou:.2f}</span>",
         f"Target > 0.65 — {'✓ met' if avg_iou>=0.65 else '✗ below'}", ""),
        ("Alert success rate", f"<span style='color:{t['success'] if success_r>=95 else t['warning']};'>{success_r:.1f}%</span>",
         f"Target > 95% — {'✓ met' if success_r>=95 else '✗ below'}", ""),
        ("System uptime", f"<span style='color:{t['success']};'>99.2%</span>", "30-day rolling", ""),
    ], t)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='padding:10px 20px 16px;'>", unsafe_allow_html=True)
    dates = [f"2025-{m:02d}" for m in [5,6,7,8,9,10]]
    tab1, tab2, tab3, tab4 = st.tabs(["⏱️ Pipeline timing","🎯 Detection accuracy","✅ SLA compliance","🔥 Stage heatmap"])

    with tab1:
        c1, c2 = st.columns(2)
        with c1:
            fig = go.Figure()
            fig.add_scatter(x=dates, y=[48,52,41,58,45,49], mode="lines+markers",
                           line=dict(shape="spline",color=t['accent'],width=2.5),
                           marker=dict(size=8,color=t['accent']), name="Latency (min)")
            fig.add_scatter(x=[dates[0],dates[-1]], y=[60,60], mode="lines",
                           line=dict(color=t['danger'],width=2,dash="dash"), name="60 min target")
            fig.update_layout(**pl(t), height=280, yaxis_title="Minutes",
                             legend=dict(font=dict(size=13),bgcolor="transparent"))
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar":False})
        with c2:
            fig2 = go.Figure(go.Bar(
                x=["Acquisition","Preprocessing","Detection","Risk assess.","Alerting"],
                y=[131,916,482,314,155],
                marker_color=[t['accent'],t['danger'],t['warning'],t['accent2'],t['success']],
                text=["2.2m","15.3m","8.0m","5.2m","2.6m"], textposition="outside",
                textfont=dict(size=12)))
            fig2.update_layout(**pl(t), height=280, yaxis_title="Seconds (avg)", xaxis_tickfont=dict(size=11))
            st.plotly_chart(fig2, use_container_width=True, config={"displayModeBar":False})

    with tab2:
        fig3 = go.Figure()
        fig3.add_scatter(x=dates, y=[0.68,0.71,0.79,0.63,0.74,0.71], mode="lines+markers",
                        line=dict(shape="spline",color=t['success'],width=2.5),
                        marker=dict(size=8,color=t['success']), name="IoU score")
        fig3.add_scatter(x=[dates[0],dates[-1]], y=[0.65,0.65], mode="lines",
                        line=dict(color=t['warning'],width=2,dash="dash"), name="0.65 target")
        fig3.update_layout(**pl(t), height=300, yaxis_title="IoU score", yaxis_range=[0.5,1.0],
                          legend=dict(font=dict(size=13),bgcolor="transparent"))
        st.plotly_chart(fig3, use_container_width=True, config={"displayModeBar":False})

    with tab3:
        c1, c2 = st.columns(2)
        with c1:
            fig4 = go.Figure()
            fig4.add_bar(x=dates, y=[2,5,7,11,9,5], name="Met target", marker_color=t['success'])
            fig4.add_bar(x=dates, y=[0,0,1,1,1,1], name="Exceeded target", marker_color=t['danger'])
            fig4.update_layout(**pl(t), barmode="stack", height=280, yaxis_title="Events",
                              legend=dict(font=dict(size=13),bgcolor="transparent"))
            st.plotly_chart(fig4, use_container_width=True, config={"displayModeBar":False})
        with c2:
            reqs = [("NFR1","Alert latency","≤ 60 min","45–52 min","✓ Met","green"),
                    ("NFR2","Detection accuracy","IoU > 0.65","0.71 mean","✓ Met","green"),
                    ("NFR3","Alert delivery","> 95%","Confirmed","✓ Met*","amber")]
            rows_r = "".join(
                f"<div style='display:flex;justify-content:space-between;align-items:center;"
                f"padding:12px 0;border-bottom:1px solid {t['border']};'>"
                f"<div><div style='font-size:14px;font-weight:500;color:{t['text_h']};'>{nfr} — {name}</div>"
                f"<div style='font-size:13px;color:{t['text_m']};'>Target: {target} | Achieved: {ach}</div></div>"
                f"{badge(status,col)}</div>"
                for nfr,name,target,ach,status,col in reqs
            )
            st.markdown(card(card_header("Requirement status",t)+rows_r
                            +f"<div style='font-size:12px;color:{t['text_m']};margin-top:10px;'>"
                            +f"* Enable Twilio Kenya geo-permissions for handset delivery.</div>",t),
                        unsafe_allow_html=True)

    with tab4:
        fig5 = go.Figure(go.Heatmap(
            z=[[128,911,478,310,152],[135,920,495,318,158],[122,902,465,305,148],[145,935,510,325,165],[131,905,480,312,155]],
            x=["Acquisition","Preprocessing","Detection","Risk assess.","Alerting"],
            y=["EVT-047","EVT-041","EVT-033","EVT-028","EVT-021"],
            colorscale=[[0,t['success']],[0.5,t['warning']],[1,t['danger']]],
            texttemplate="%{z}s", textfont=dict(size=12,color="white"), showscale=True))
        fig5.update_layout(**pl(t), height=280, xaxis_tickfont=dict(size=12))
        st.plotly_chart(fig5, use_container_width=True, config={"displayModeBar":False})
        st.info("💡 Preprocessing accounts for ~50–60% of total pipeline time. Switching to 20m output resolution could reduce this by ~35%.")

    st.markdown("</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# PAGE — EXPORT
# ════════════════════════════════════════════════════════════
def page_export(cfg, db, t):
    user = current_user()
    topbar(t, "—", f"{user.get('name','')} ({user.get('role','')})")
    breadcrumb("Export — Download Data", t)
    if st.session_state.get("show_glossary"): glossary_panel(t)
    context_box("Export flood data for GIS software (QGIS, ArcGIS), spreadsheets, or reports. Choose event, format, and layers, then generate.", t)

    st.markdown("<div style='padding:16px 20px;'>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3, gap="small")
    with c1:
        st.markdown(card_header("Step 1 — Scope", t), unsafe_allow_html=True)
        scope = st.radio("scope",["Single event","Full 2025 season"],label_visibility="collapsed",key="exp_scope")
        if scope == "Single event":
            st.selectbox("Event",["EVT-2025-047","EVT-2025-041","EVT-2025-033"],label_visibility="collapsed",key="exp_evt")
        else:
            st.info("All 47 events — May to October 2025")
    with c2:
        st.markdown(card_header("Step 2 — Format", t), unsafe_allow_html=True)
        st.radio("fmt",["📍 GeoJSON  — for maps (QGIS, web)","📊 CSV  — for spreadsheets","📄 PDF  — situation report","🛰️ GeoTIFF  — raster flood mask"],label_visibility="collapsed",key="exp_fmt")
    with c3:
        st.markdown(card_header("Step 3 — Layers & Export", t), unsafe_allow_html=True)
        st.checkbox("Flood extent polygon", value=True, key="l1")
        st.checkbox("Affected villages", value=True, key="l2")
        st.checkbox("Inaccessible roads", value=True, key="l3")
        st.checkbox("Health facilities at risk", value=True, key="l4")
        st.markdown(
            f"<div style='background:{t['bg']};border:1px solid {t['border']};border-radius:6px;"
            f"padding:10px 12px;margin:10px 0;font-family:DM Mono,monospace;font-size:12px;"
            f"color:{t['text_m']};white-space:pre;overflow-x:auto;'>"
            f"event_id,date_utc,flood_ha,affected\nEVT-2025-047,2025-10-23,1200,5000\nEVT-2025-041,2025-10-08,980,3800</div>",
            unsafe_allow_html=True,
        )
        st.download_button("⬇️  Generate & download",
            data="event_id,date_utc,flood_ha,affected\nEVT-2025-047,2025-10-23,1200,5000\n".encode(),
            file_name="suddwatch_export.csv", mime="text/csv", use_container_width=True, key="dl_btn")
    st.markdown("</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# PAGE — ADMIN
# ════════════════════════════════════════════════════════════
def page_admin(cfg, db, t):
    user = current_user()
    topbar(t, "—", f"{user.get('name','')} ({user.get('role','')})")
    breadcrumb("Admin — System Management", t)
    st.markdown("<div style='padding:16px 20px;'>", unsafe_allow_html=True)
    tab1, tab2, tab3 = st.tabs(["👥 Users","⚙️ Settings","🔔 Alerts"])

    with tab1:
        st.markdown(card_header("Registered users", t), unsafe_allow_html=True)
        for name, email, role, status, last_login in [
            ("System Administrator","admin@suddwatch.org","Admin","Active","2026-07-01"),
            ("OCHA Coordinator","coord@ocha.org","User","Active","2026-07-09"),
            ("REACH Analyst","analyst@reach.org","User","Active","2026-07-05"),
        ]:
            rc = t['accent'] if role == "Admin" else t['success']
            st.markdown(card(
                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                f"<div><div style='font-size:14px;font-weight:500;color:{t['text_h']};'>{name}</div>"
                f"<div style='font-size:13px;color:{t['text_m']};'>{email} · Last login: {last_login}</div></div>"
                f"<div style='display:flex;gap:8px;align-items:center;'>"
                f"<span style='color:{rc};font-size:13px;font-weight:500;'>{role}</span>"
                f"{badge(status,'green')}</div></div>", t, "12px 14px"
            ), unsafe_allow_html=True)
            st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)

    with tab2:
        c1, c2 = st.columns(2)
        with c1:
            st.number_input("Alert threshold — flood extent (ha)", value=500, step=50, key="cfg_flood")
            st.number_input("Alert threshold — affected population", value=1000, step=100, key="cfg_pop")
        with c2:
            st.number_input("Pipeline schedule (hours between runs)", value=12, step=1, key="cfg_sched")
            st.selectbox("SNAP output resolution", ["10m (standard)","20m (faster, ~35% speed gain)"], key="cfg_res")
        if st.button("💾 Save configuration", use_container_width=True, key="btn_save_cfg"):
            st.success("Configuration saved.")

    with tab3:
        st.text_area("SMS recipients (one +country code number per line)",
                     value="+254705176665\n+211920123456", height=100, key="cfg_sms")
        st.text_area("Email recipients (one address per line)",
                     value="coord@ocha.org\nalerts@ifrc.org", height=100, key="cfg_email")
        st.warning("⚠️ Enable Kenya (+254) geo-permissions in Twilio Console → Messaging → Geo Permissions before operational deployment.")
        if st.button("💾 Save alert config", use_container_width=True, key="btn_save_alerts"):
            st.success("Alert configuration saved.")

    st.markdown("</div>", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════
def main():
    st.markdown(FONTS, unsafe_allow_html=True)
    t = get_theme()
    st.markdown(css(t), unsafe_allow_html=True)

    # ── Auth gate ─────────────────────────────
    # Read any query params into session_state ONCE, then clear all params
    # (setting params triggers reruns, so we avoid it entirely)
    go_param    = st.query_params.get("go")
    theme_param = st.query_params.get("theme")

    if go_param == "signin":
        st.session_state["auth_page"] = "login"
        st.query_params.clear()          # clear all — no rerun side effect in 1.30+
        st.rerun()

    if theme_param in ("dark", "light"):
        st.session_state["theme_choice"] = theme_param
        st.query_params.clear()
        st.rerun()

    want_auth = st.session_state.get("auth_page") == "login"

    if not is_logged_in():
        if want_auth:
            page_auth(t)
        else:
            page_landing(t)
        return

    # ── Load resources ─────────────────────────
    cfg = db = None
    try:
        cfg = get_config()
        db  = get_db(cfg)
    except Exception as e:
        logger.warning(f"Config/DB unavailable ({e}) — demo mode.")

    metrics = {}
    if db:
        try: metrics = load_metrics(db)
        except Exception: pass

    # ── Sidebar ────────────────────────────────
    page = render_sidebar(metrics, t)

    # ── Stub DB for demo mode ──────────────────
    _stub = type("DB",(),{
        "get_latest_event":          lambda s: {},
        "query_events":              lambda s, **kw: pd.DataFrame(),
        "query_performance_metrics": lambda s: {},
    })()
    active_db = db or _stub

    # ── Route ──────────────────────────────────
    if   "Home"        in page: page_home(cfg, active_db, t)
    elif "History"     in page: page_history(cfg, active_db, t)
    elif "Performance" in page: page_performance(cfg, active_db, t)
    elif "Export"      in page: page_export(cfg, active_db, t)
    elif "Admin"       in page:
        if current_user().get("role") == "Admin":
            page_admin(cfg, active_db, t)
        else:
            st.error("🚫 You do not have permission to access the Admin panel.")

if __name__ == "__main__":
    main()
