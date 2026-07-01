# ============================================================
# SuddWatch — Operational Flood Detection Dashboard
# File: dashboard/app.py
# Streamlit 1.58.0
# Course: SWE3090 — Software Project 1
# Student: Madut Chan (671336)
# ============================================================

import json
import sys
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

sys.path.insert(0, str(Path(__file__).parent.parent))
from src.config import Config, setup_logging
from src.database import DatabaseManager

# ── Page config — must be first Streamlit call ──────────────
st.set_page_config(
    page_title="SuddWatch",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Fonts ─────────────────────────────────────────────────────
st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Inter:wght@400;500;600&family=DM+Mono:wght@400;500&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

# ── CSS — minimal, only what's needed, nothing that hides content ──
st.markdown("""
<style>
html, body, [data-testid="stApp"] {
    background: #0d1117 !important;
    color: #c9d1d9 !important;
    font-family: 'Inter', sans-serif !important;
}
#MainMenu {display: none !important;} footer {display: none !important;} [data-testid="stDecoration"] {display: none !important;} [data-testid="stAppDeployButton"] {display: none !important;} header[data-testid="stHeader"] {height: 2.5rem !important; background: transparent !important;}
[data-testid="stSidebar"] {
    background: #010409 !important;
    border-right: 1px solid #21262d !important;
    min-width: 270px !important;
    max-width: 270px !important;
}
[data-testid="stSidebar"] > div:first-child {
    width: 270px !important;
}
[data-testid="stMainBlockContainer"] {
    padding: 0 !important;
    max-width: 100% !important;
}
section[data-testid="stMain"] {background: #0d1117 !important;}

button[kind="secondary"], button[data-testid="baseButton-secondary"] {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    color: #c9d1d9 !important;
    border-radius: 5px !important;
}
button[kind="secondary"]:hover, button[data-testid="baseButton-secondary"]:hover {
    border-color: #0ea5e9 !important;
    color: #0ea5e9 !important;
}
button[kind="primary"], button[data-testid="baseButton-primary"] {
    background: #0ea5e9 !important;
    border: 1px solid #0ea5e9 !important;
    color: #0d1117 !important;
    border-radius: 5px !important;
    font-weight: 600 !important;
}
button[kind="primary"]:hover, button[data-testid="baseButton-primary"]:hover {
    background: #38bdf8 !important;
    border-color: #38bdf8 !important;
}
button[disabled] {
    opacity: 0.4 !important;
    cursor: not-allowed !important;
}

[data-testid="stTabs"] [role="tablist"] {border-bottom: 1px solid #21262d !important;}
[data-testid="stTabs"] [role="tab"] {
    color: #8b949e !important;
    font-family: 'Barlow Condensed', sans-serif !important;
    font-size: 13px !important;
    letter-spacing: .05em !important;
    text-transform: uppercase !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #0ea5e9 !important;
    border-bottom-color: #0ea5e9 !important;
}

[data-testid="stExpander"] {
    background: #161b22 !important;
    border: 1px solid #21262d !important;
    border-radius: 6px !important;
}

[data-testid="stDateInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextInput"] input {
    background: #161b22 !important;
    border: 1px solid #30363d !important;
    color: #c9d1d9 !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 12px !important;
}
[data-testid="stNumberInput"] button {
    display: none !important;
}
[data-testid="stDateInput"] svg {
    fill: #6e7681 !important;
}
hr {border-color: #21262d !important;}
iframe {width: 100% !important;}
iframe[title="st.iframe"], iframe { width: 100% !important; }
</style>
""", unsafe_allow_html=True)

# ── Colours ───────────────────────────────────────────────────
BG, CARD, BORDER = "#0d1117", "#161b22", "#21262d"
ACCENT, PRIMARY  = "#0ea5e9", "#1a7fd4"
MUTED, TEXT      = "#8b949e", "#c9d1d9"
RED, GREEN, AMBER = "#f85149", "#3fb950", "#d29922"


def pl(h=260):
    """Base Plotly layout. Does NOT include xaxis/yaxis to avoid kwarg clashes."""
    return dict(
        paper_bgcolor=BG, plot_bgcolor=CARD,
        font=dict(family="DM Mono, monospace", size=11, color=MUTED),
        margin=dict(l=40, r=16, t=32, b=36), height=h,
    )


def ax():
    return dict(gridcolor=BORDER, linecolor=BORDER, tickfont=dict(size=10))


# ── HTML helpers ──────────────────────────────────────────────
def badge(text, colour="grey"):
    styles = {
        "red": ("#3d0f0f", RED), "green": ("#0f2d1f", GREEN),
        "amber": ("#2d1f00", AMBER), "grey": (BORDER, MUTED),
    }
    bg, fg = styles.get(colour, styles["grey"])
    return (f"<span style='background:{bg};color:{fg};font-family:DM Mono,monospace;"
            f"font-size:10px;font-weight:600;padding:2px 8px;border-radius:4px;'>{text}</span>")


def card(html, padding="16px 18px"):
    return (f"<div style='background:{CARD};border:1px solid {BORDER};"
            f"border-radius:6px;padding:{padding};'>{html}</div>")


def header(title, right=""):
    r = f"<span style='font-family:DM Mono,monospace;font-size:10px;color:{MUTED};'>{right}</span>" if right else ""
    return (f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"margin-bottom:12px;'><span style='font-family:Inter,sans-serif;font-size:12px;"
            f"font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:{TEXT};'>"
            f"{title}</span>{r}</div>")


def th(t, align="left"):
    return (f"<th style='padding:6px 10px;font-family:Inter,sans-serif;font-size:10px;"
            f"font-weight:600;text-transform:uppercase;color:{MUTED};"
            f"border-bottom:1px solid #30363d;text-align:{align};'>{t}</th>")


def td(t, colour=None, align="left"):
    c = colour or TEXT
    return (f"<td style='padding:6px 10px;font-family:DM Mono,monospace;font-size:11px;"
            f"color:{c};border-bottom:1px solid {BORDER};text-align:{align};'>{t}</td>")


def table(hdr, body):
    return (f"<table style='width:100%;border-collapse:collapse;'>"
            f"<thead><tr>{hdr}</tr></thead><tbody>{body}</tbody></table>")


def kpi_row(items):
    cols = st.columns(len(items), gap="small")
    for col, (title, value, sub) in zip(cols, items):
        with col:
            st.markdown(card(
                f"<div style='font-size:9px;text-transform:uppercase;color:{MUTED};"
                f"margin-bottom:5px;letter-spacing:.08em;'>{title}</div>"
                f"<div style='font-family:Barlow Condensed,sans-serif;font-size:22px;"
                f"font-weight:700;margin-bottom:4px;'>{value}</div>"
                f"<div style='font-family:DM Mono,monospace;font-size:10px;color:{MUTED};'>{sub}</div>",
                padding="14px 16px",
            ), unsafe_allow_html=True)


def topbar(last_evt):
    st.markdown(
        f"<div style='background:#010409;border-bottom:1px solid {BORDER};"
        f"padding:0 16px;height:48px;display:flex;align-items:center;"
        f"justify-content:space-between;'>"
        f"<div style='display:flex;align-items:center;gap:10px;'>"
        f"<div style='width:7px;height:7px;border-radius:50%;background:{ACCENT};'></div>"
        f"<span style='font-family:Barlow Condensed,sans-serif;font-size:17px;"
        f"font-weight:700;color:#f0f6fc;letter-spacing:.03em;'>SUDDWATCH</span>"
        f"<span style='color:#30363d;'>|</span>"
        f"<span style='font-size:12px;color:{MUTED};'>Operational Flood Detection &amp; Alert System</span>"
        f"</div>"
        f"<div style='display:flex;align-items:center;gap:14px;'>"
        f"<span style='font-size:11px;color:{MUTED};'>Last event: "
        f"<span style='font-family:DM Mono,monospace;color:{ACCENT};'>{last_evt}</span></span>"
        f"</div></div>", unsafe_allow_html=True,
    )
    col_spacer, col_btn = st.columns([10, 1])
    with col_btn:
        if st.button("⟳ Refresh", key="topbar_refresh", use_container_width=True):
            st.cache_data.clear()
            st.rerun()


def breadcrumb(text):
    st.markdown(
        f"<div style='padding:6px 16px;font-size:12px;color:{MUTED};"
        f"border-bottom:1px solid {BORDER};'>{text}</div>",
        unsafe_allow_html=True,
    )


# ── SVG Map ───────────────────────────────────────────────────
def svg_map():
    return """<!DOCTYPE html><html><head>
<style>*{margin:0;padding:0;box-sizing:border-box;}
body{background:#07111a;overflow:hidden;border:1px solid #21262d;border-radius:8px;box-sizing:border-box;}
svg{width:100%;height:830px;display:block;}</style></head><body>
<svg viewBox="0 0 960 830" xmlns="http://www.w3.org/2000/svg">
<rect width="960" height="830" fill="#07111a"/>
<polygon points="80,7 790,7 790,235 610,254 340,240 80,204" fill="#051828" stroke="#1a7fd4" stroke-width="1.5" stroke-dasharray="7,4" opacity="0.9"/>
<polygon points="8,204 275,204 285,448 220,544 8,525" fill="#140a28" stroke="#7c3aed" stroke-width="1.5" stroke-dasharray="7,4" opacity="0.9"/>
<polygon points="275,204 790,235 815,548 365,553 285,448" fill="#051a0a" stroke="#16a34a" stroke-width="1.5" stroke-dasharray="7,4" opacity="0.9"/>
<polygon points="150,26 660,26 675,204 455,219 145,208" fill="#0ea5e922" stroke="#0ea5e9" stroke-width="1.5" stroke-dasharray="6,3"/>
<polygon points="28,226 255,231 262,430 182,496 24,485" fill="#0ea5e922" stroke="#0ea5e9" stroke-width="1.5" stroke-dasharray="6,3"/>
<polygon points="310,240 705,235 725,496 475,515 322,417" fill="#0ea5e922" stroke="#0ea5e9" stroke-width="1.5" stroke-dasharray="6,3"/>
<path d="M 252,11 L 246,276 L 270,548" fill="none" stroke="#374151" stroke-width="2" stroke-dasharray="10,5" opacity="0.6"/>
<path d="M 8,294 L 425,288 L 808,281" fill="none" stroke="#374151" stroke-width="2" stroke-dasharray="10,5" opacity="0.6"/>
<path d="M 432,11 C 444,84 430,165 434,255 C 438,345 420,420 412,548" fill="none" stroke="#1a7fd4" stroke-width="5" opacity="0.9" stroke-linecap="round"/>
<circle cx="522" cy="193" r="8" fill="#3fb950" stroke="#07111a" stroke-width="2"/>
<text x="536" y="197" fill="#3fb950" font-family="DM Mono,monospace" font-size="12">Malakal</text>
<circle cx="144" cy="322" r="8" fill="#d29922" stroke="#07111a" stroke-width="2"/>
<text x="158" y="326" fill="#d29922" font-family="DM Mono,monospace" font-size="12">Bentiu</text>
<circle cx="460" cy="438" r="8" fill="#f85149" stroke="#07111a" stroke-width="2"/>
<text x="474" y="442" fill="#f85149" font-family="DM Mono,monospace" font-size="12">Bor</text>
<circle cx="665" cy="412" r="8" fill="#d29922" stroke="#07111a" stroke-width="2"/>
<text x="650" y="407" fill="#d29922" font-family="DM Mono,monospace" font-size="12" text-anchor="end">Akobo</text>
<circle cx="675" cy="232" r="8" fill="#d29922" stroke="#07111a" stroke-width="2"/>
<text x="660" y="226" fill="#d29922" font-family="DM Mono,monospace" font-size="12" text-anchor="end">Nasir</text>
<circle cx="190" cy="412" r="8" fill="#f85149" stroke="#07111a" stroke-width="2"/>
<text x="204" y="418" fill="#f85149" font-family="DM Mono,monospace" font-size="12">Leer</text>
<circle cx="398" cy="337" r="8" fill="#3fb950" stroke="#07111a" stroke-width="2"/>
<text x="412" y="328" fill="#3fb950" font-family="DM Mono,monospace" font-size="12">Twic E.</text>
<text x="452" y="89" fill="#1a7fd4" opacity="0.55" font-family="Barlow Condensed,sans-serif" font-size="16" letter-spacing="5" text-anchor="middle" font-weight="700">UPPER NILE</text>
<text x="92" y="334" fill="#7c3aed" opacity="0.55" font-family="Barlow Condensed,sans-serif" font-size="14" letter-spacing="4" text-anchor="middle" font-weight="700" transform="rotate(-90,92,411)">UNITY</text>
<text x="614" y="487" fill="#16a34a" opacity="0.5" font-family="Barlow Condensed,sans-serif" font-size="16" letter-spacing="5" text-anchor="middle" font-weight="700">JONGLEI</text>
<rect x="8" y="7" width="290" height="20" rx="3" fill="#161b22" opacity="0.92"/>
<text x="14" y="20" fill="#8b949e" font-family="DM Mono,monospace" font-size="10">Greater Upper Nile — Jonglei · Unity · Upper Nile</text>
<rect x="8" y="642" width="155" height="126" rx="4" fill="#161b22" stroke="#21262d" stroke-width="1" opacity="0.96"/>
<rect x="15" y="650" width="13" height="9" rx="2" fill="#0ea5e922" stroke="#0ea5e9" stroke-width="1"/>
<text x="35" y="655" fill="#8b949e" font-family="DM Mono,monospace" font-size="9">Flood extent</text>
<circle cx="21" cy="667" r="5" fill="#f85149"/>
<text x="35" y="670" fill="#8b949e" font-family="DM Mono,monospace" font-size="9">High-risk</text>
<circle cx="21" cy="681" r="5" fill="#d29922"/>
<text x="35" y="684" fill="#8b949e" font-family="DM Mono,monospace" font-size="9">Medium-risk</text>
<circle cx="21" cy="695" r="5" fill="#3fb950"/>
<text x="35" y="698" fill="#8b949e" font-family="DM Mono,monospace" font-size="9">Low-risk</text>
<line x1="800" y1="800" x2="900" y2="800" stroke="#8b949e" stroke-width="1.5"/>
<line x1="800" y1="794" x2="800" y2="806" stroke="#8b949e" stroke-width="1.5"/>
<line x1="900" y1="794" x2="900" y2="806" stroke="#8b949e" stroke-width="1.5"/>
<text x="850" y="790" fill="#8b949e" font-family="DM Mono,monospace" font-size="9" text-anchor="middle">100 km</text>
</svg></body></html>"""


# ── Caching ───────────────────────────────────────────────────
@st.cache_resource
def get_config():
    return Config()

@st.cache_resource
def get_db(_cfg):
    return DatabaseManager(_cfg)

@st.cache_data(ttl=300)
def load_latest(_db):
    return _db.get_latest_event() or {}

@st.cache_data(ttl=300)
def load_events(_db, filters=None):
    if filters:
        return _db.query_events(filters=filters)
    return _db.query_events()

@st.cache_data(ttl=300)
def load_metrics(_db):
    return _db.query_performance_metrics()

def load_summary(path):
    if not path or not Path(path).exists():
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


# ── Sidebar navigation ───────────────────────────────────────
def render_sidebar(metrics):
    nav_icons = {
        "Home": "⌂", "History": "↻", "Performance": "▤", "Export": "⇩",
    }
    with st.sidebar:
        st.markdown(
            f"<div style='padding:16px 14px 8px;'>"
            f"<span style='font-family:Barlow Condensed,sans-serif;font-size:16px;"
            f"font-weight:700;color:#f0f6fc;'>● SUDDWATCH</span>"
            f"<div style='font-size:9px;color:#30363d;margin-top:2px;'>FLOOD DETECTION SYSTEM</div>"
            f"</div>", unsafe_allow_html=True,
        )
        st.markdown(f"<hr style='margin:4px 0;'>", unsafe_allow_html=True)
        st.markdown(
            f"<div style='padding:0 14px 6px;font-size:9px;font-weight:600;"
            f"letter-spacing:.1em;color:#30363d;'>NAVIGATION</div>",
            unsafe_allow_html=True,
        )

        if "page" not in st.session_state:
            st.session_state.page = "Home"

        for item in ["Home", "History", "Performance", "Export"]:
            icon = nav_icons[item]
            if st.session_state.page == item:
                st.markdown(
                    f"<div style='background:rgba(14,165,233,.12);border-left:3px solid {ACCENT};"
                    f"padding:8px 11px;margin:2px 8px;border-radius:4px;"
                    f"font-size:13px;color:{ACCENT};font-weight:600;'>{icon}&nbsp;&nbsp;{item}</div>",
                    unsafe_allow_html=True,
                )
            else:
                if st.button(f"{icon}   {item}", key=f"nav_{item}", width="stretch"):
                    st.session_state.page = item
                    st.rerun()

        # Spacer pushes the footer to the bottom of the sidebar
        st.markdown(
            "<div style='height:60px;'></div>",
            unsafe_allow_html=True,
        )
        st.markdown(f"<hr style='margin:8px 0;'>", unsafe_allow_html=True)
        total = int(metrics.get("total_events") or 0)
        dc = GREEN if total > 0 else MUTED
        st.markdown(
            f"<div style='padding:0 14px 14px;'>"
            f"<span style='font-size:10px;color:{dc};'>● "
            f"{'System operational' if total else 'Awaiting pipeline'}</span>"
            f"<div style='font-size:9px;color:#30363d;margin-top:3px;'>v2.4.1 — Sudd Basin</div>"
            f"</div>", unsafe_allow_html=True,
        )

    return st.session_state.page


# ════════════════════════════════════════════════════════════
# PAGE — HOME
# ════════════════════════════════════════════════════════════
def page_home(cfg, db):
    latest = load_latest(db)
    metrics = load_metrics(db)

    last_evt = "—"
    if latest.get("event_timestamp"):
        try:
            last_evt = datetime.fromisoformat(str(latest["event_timestamp"])).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            last_evt = str(latest["event_timestamp"])[:16]

    topbar(last_evt)
    breadcrumb("Dashboard — Live Event")

    gp = str(latest.get("geotiff_path") or "")
    sp = gp.replace("_flood_mask.tif", "_flood_mask_risk_summary.json") if gp else ""
    risk = load_summary(sp)

    flood_ha = float(latest.get("flood_extent_ha") or 2220)
    pop = int(risk.get("affected_population_estimate") or 7990)
    avg_lat = float((metrics.get("avg_latency_seconds") or 2700)) / 60
    iou_val = float(metrics.get("avg_iou") or 0.71)
    total_ev = int(metrics.get("total_events") or 47)

    villages = risk.get("affected_villages") or [
        {"village_name": "Bor South", "estimated_population": 12400, "flood_risk_percentage": 87},
        {"village_name": "Akobo East", "estimated_population": 8200, "flood_risk_percentage": 74},
        {"village_name": "Twic East", "estimated_population": 6700, "flood_risk_percentage": 61},
    ]
    roads = risk.get("inaccessible_roads") or [
        {"name": "Bor-Malakal A1", "facility_type": "Primary", "segment_length_km": 142, "alt_route": "Air only"},
        {"name": "Akobo-Pochalla B4", "facility_type": "Secondary", "segment_length_km": 88, "alt_route": "Boat route"},
    ]
    health = risk.get("health_facilities_at_risk") or [
        {"name": "Bor State Hospital", "facility_type": "Hospital", "status": "at_risk", "served": "45,000"},
    ]

    iou_pct = int(iou_val * 100)
    conf_pct = min(100, iou_pct + 13)

    st.markdown("<div style='padding:18px 20px 0;'>", unsafe_allow_html=True)
    kpi_row([
        ("📍 Total Flood Extent", f"<span style='color:{ACCENT};'>{flood_ha:,.0f} ha</span>", "across 3 states"),
        ("👥 Affected Population", f"<span style='color:{AMBER};'>{pop:,}</span>", "est. at risk"),
        ("⚠ Active Alerts", f"<span style='color:{RED};'>{total_ev}</span>", "24h window"),
        ("⏱ Avg Alert Latency", f"<span style='color:{GREEN if avg_lat<=60 else AMBER};'>{avg_lat:.0f} min</span>", "vs 60 min SLA"),
        ("◎ Detection IoU", f"<span style='color:{GREEN if iou_val>=0.65 else AMBER};'>{iou_val:.2f}</span>", "last acquisition"),
        ("📊 Season Events", f"<span>{total_ev}</span>", "2025 flood season"),
    ])
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='padding:18px 20px 0;'>", unsafe_allow_html=True)
    map_col, right_col = st.columns([4, 1], gap="small")
    with map_col:
        components.html(svg_map(), height=834, width=None, scrolling=False)
    with right_col:
        st.markdown(card(
            header("Active Event")
            + f"<div style='margin-bottom:8px;'><span style='font-size:10px;color:{MUTED};'>Flood extent</span><br>"
            + f"<span style='font-family:DM Mono,monospace;font-size:15px;color:{ACCENT};font-weight:600;'>{flood_ha:,.0f} ha</span></div>"
            + f"<div style='margin-bottom:8px;'><span style='font-size:10px;color:{MUTED};'>Affected pop.</span><br>"
            + f"<span style='font-family:DM Mono,monospace;font-size:15px;color:{AMBER};font-weight:600;'>{pop:,}</span></div>"
            + f"<div style='margin-bottom:8px;'><span style='font-size:10px;color:{MUTED};'>Alerts sent</span><br>"
            + f"<span style='font-family:DM Mono,monospace;font-size:15px;font-weight:600;'>{total_ev}</span></div>"
            + f"<div><span style='font-size:10px;color:{MUTED};'>Detection latency</span><br>"
            + f"<span style='font-family:DM Mono,monospace;font-size:15px;font-weight:600;'>{avg_lat:.0f} min</span></div>",
            padding="12px 12px",
        ), unsafe_allow_html=True)

        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

        def qa_row(label_txt, pct, colour):
            return (f"<div style='margin-bottom:8px;'>"
                    f"<div style='display:flex;justify-content:space-between;margin-bottom:3px;'>"
                    f"<span style='font-size:10px;color:{MUTED};'>{label_txt}</span>"
                    f"<span style='font-family:DM Mono,monospace;font-size:10px;color:{colour};'>{pct/100:.2f}</span></div>"
                    f"<div style='background:{BORDER};border-radius:2px;height:3px;'>"
                    f"<div style='background:{colour};width:{pct}%;height:3px;border-radius:2px;'></div></div></div>")

        st.markdown(card(
            header("Detection QA")
            + qa_row("IoU score", iou_pct, ACCENT)
            + qa_row("Confidence", conf_pct, GREEN)
            + qa_row("Cloud cover", 12, AMBER),
            padding="12px 12px",
        ), unsafe_allow_html=True)

        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

        def alert_row(dot_colour, label_txt, count):
            return (f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:5px;'>"
                    f"<span style='font-size:11px;color:{dot_colour};'>● {label_txt}</span>"
                    f"<span style='font-family:DM Mono,monospace;font-size:11px;'>{count}</span></div>")

        st.markdown(card(
            header("Alert Delivery")
            + alert_row(GREEN, "SMS", total_ev)
            + alert_row(GREEN, "Email", max(0, total_ev - 12))
            + alert_row(AMBER, "Pending", 3)
            + alert_row(RED, "Failed", 1),
            padding="12px 12px",
        ), unsafe_allow_html=True)

        st.markdown("<div style='height:6px;'></div>", unsafe_allow_html=True)

        pipeline = [("Data Acquisition", True), ("Preprocessing", True), ("Flood Detection", True),
                    ("Risk Assessment", True), ("Alert Dispatch", True)]
        rows = "".join(
            f"<div style='display:flex;justify-content:space-between;margin-bottom:4px;'>"
            f"<span style='font-size:10px;color:{MUTED};'>{n}</span>{badge('OK','green') if ok else badge('ERR','red')}</div>"
            for n, ok in pipeline
        )
        st.markdown(card(header("Pipeline Status") + rows, padding="12px 12px"), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # State-level breakdown banner
    st.markdown("<div style='padding:18px 20px 0;'>", unsafe_allow_html=True)
    j_ha, j_pop = flood_ha * 0.54, int(pop * 0.63)
    u_ha, u_pop = flood_ha * 0.29, int(pop * 0.26)
    n_ha, n_pop = flood_ha * 0.17, int(pop * 0.11)

    def state_block(name, fha, fpop, alerts, risk_lvl, risk_colour, border_left=False):
        bl = f"border-left:1px solid {BORDER};padding-left:16px;" if border_left else ""
        return (
            f"<div style='{bl}'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;'>"
            f"<span style='font-size:13px;font-weight:600;'>{name}</span>{badge(risk_lvl, risk_colour)}</div>"
            f"<div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;'>"
            f"<div><span style='font-size:10px;color:{MUTED};'>Flood</span><br>"
            f"<span style='font-family:DM Mono,monospace;font-size:13px;color:{ACCENT};font-weight:600;'>{fha:,.0f} ha</span></div>"
            f"<div><span style='font-size:10px;color:{MUTED};'>Affected</span><br>"
            f"<span style='font-family:DM Mono,monospace;font-size:13px;color:{AMBER};font-weight:600;'>{fpop:,}</span></div>"
            f"<div><span style='font-size:10px;color:{MUTED};'>Alerts</span><br>"
            f"<span style='font-family:DM Mono,monospace;font-size:13px;font-weight:600;'>{alerts}</span></div>"
            f"</div></div>"
        )

    st.markdown(card(
        f"<div style='display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;'>"
        f"<span style='font-size:12px;font-weight:600;text-transform:uppercase;letter-spacing:.05em;'>State-Level Breakdown</span>"
        f"<span style='font-family:DM Mono,monospace;font-size:10px;color:{MUTED};'>Current event · {last_evt}</span></div>"
        f"<div style='display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;'>"
        + state_block("Jonglei", j_ha, j_pop, 24, "HIGH", "red")
        + state_block("Unity", u_ha, u_pop, 11, "MEDIUM", "amber", border_left=True)
        + state_block("Upper Nile", n_ha, n_pop, 6, "LOW", "green", border_left=True)
        + "</div>",
        padding="16px 18px",
    ), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='padding:18px 20px 0;'>", unsafe_allow_html=True)
    t1, t2, t3 = st.columns(3, gap="small")
    with t1:
        st.markdown(header("Affected Villages", f"{len(villages)} records"), unsafe_allow_html=True)
        hdr = th("Village") + th("Pop.", "right") + th("Risk", "right") + th("Action", "right")
        body = ""
        for v in villages[:5]:
            vname = v.get("village_name", "")
            vpop = v.get("estimated_population", 0)
            vrisk = int(v.get("flood_risk_percentage", 0))
            rcolor = "red" if vrisk >= 75 else "amber" if vrisk >= 40 else "green"
            action = "Evacuate" if vrisk >= 75 else "Monitor" if vrisk >= 40 else "Watch"
            body += (
                f"<tr>{td(vname)}{td(f'{vpop:,}', MUTED, 'right')}"
                f"<td style='padding:6px 10px;text-align:right;border-bottom:1px solid {BORDER};'>{badge(f'{vrisk}%', rcolor)}</td>"
                f"{td(action, ACCENT, 'right')}</tr>"
            )
        st.markdown(card(table(hdr, body)), unsafe_allow_html=True)
    with t2:
        st.markdown(header("Inaccessible Roads", f"{len(roads)} roads"), unsafe_allow_html=True)
        hdr = th("Road") + th("Type") + th("Length", "right") + th("Alt Route")
        body = ""
        for r in roads[:5]:
            rname = r.get("name", "")
            rtype = r.get("facility_type", "Road")
            rkm = r.get("segment_length_km", 0)
            ralt = r.get("alt_route", "—")
            body += f"<tr>{td(rname)}{td(rtype, MUTED)}{td(f'{rkm:.0f} km', MUTED, 'right')}{td(ralt, MUTED)}</tr>"
        st.markdown(card(table(hdr, body)), unsafe_allow_html=True)
    with t3:
        st.markdown(header("Health Facilities at Risk", f"{len(health)} at risk"), unsafe_allow_html=True)
        hdr = th("Name") + th("Type") + th("Status") + th("Served", "right")
        body = ""
        for h in health[:5]:
            hname = h.get("name", "")
            htype = h.get("facility_type", "Clinic")
            hstatus = h.get("status", "at_risk").replace("_", " ").title()
            hserved = h.get("served", "—")
            body += (
                f"<tr>{td(hname)}{td(htype, MUTED)}"
                f"<td style='padding:6px 10px;border-bottom:1px solid {BORDER};'>{badge(hstatus, 'red')}</td>"
                f"{td(hserved, MUTED, 'right')}</tr>"
            )
        st.markdown(card(table(hdr, body)), unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Recent System Alerts + Data Sources
    st.markdown("<div style='padding:18px 20px 18px;'>", unsafe_allow_html=True)
    b1, b2 = st.columns([3, 2], gap="small")

    alerts_demo = [
        ("14:32", "CRITICAL", "Bor South — evacuation order issued", "Jonglei"),
        ("14:18", "WARNING", "Leer flood extent +12% in 6 h", "Unity"),
        ("13:55", "INFO", "Sentinel-1 acquisition complete — scene 047", "System"),
        ("13:40", "WARNING", "A1 highway submerged at km 234", "Jonglei"),
        ("13:15", "INFO", "SMS batch delivered — 24/24 recipients", "System"),
        ("12:50", "WARNING", "Akobo PHC access route cut", "Jonglei"),
        ("12:30", "INFO", "Risk assessment model run completed", "System"),
    ]
    alert_colour = {"CRITICAL": "red", "WARNING": "amber", "INFO": "grey"}
    with b1:
        alert_rows = "".join(
            f"<div style='display:flex;align-items:center;gap:10px;padding:6px 0;"
            f"border-bottom:1px solid {BORDER};'>"
            f"<span style='font-family:DM Mono,monospace;font-size:10px;color:{MUTED};flex-shrink:0;'>{t}</span>"
            f"{badge(lvl, alert_colour[lvl])}"
            f"<span style='font-size:11px;flex:1;'>{msg}</span>"
            f"<span style='font-family:DM Mono,monospace;font-size:10px;color:{MUTED};flex-shrink:0;'>{state}</span>"
            f"</div>"
            for t, lvl, msg, state in alerts_demo
        )
        st.markdown(card(
            header("Recent System Alerts", f"<span style='color:{RED};'>● LIVE</span>") + alert_rows
        ), unsafe_allow_html=True)

    ds_demo = [
        ("Sentinel-1 SAR", "ESA Copernicus", "10 m", "2025-10-23 13:10", True),
        ("CHIRPS Rainfall", "UCSB / FEWS", "5 km", "2025-10-23 06:00", True),
        ("DEM (SRTM)", "NASA / USGS", "30 m", "Static baseline", True),
        ("Population Grid", "WorldPop", "100 m", "2020 baseline", True),
        ("OSM Road Network", "OpenStreetMap", "Vector", "2025-09-01", False),
    ]
    with b2:
        hdr2 = th("Source") + th("Provider") + th("Res.") + th("Last Update") + th("Status", "right")
        body2 = "".join(
            f"<tr>{td(s)}{td(p, MUTED)}{td(r, MUTED)}{td(u, MUTED)}"
            f"<td style='padding:6px 10px;text-align:right;border-bottom:1px solid {BORDER};'>"
            f"{badge('OK', 'green') if ok else badge('STALE', 'amber')}</td></tr>"
            for s, p, r, u, ok in ds_demo
        )
        st.markdown(card(
            header("Data Sources", "Ingestion status") + table(hdr2, body2)
        ), unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# PAGE — HISTORY
# ════════════════════════════════════════════════════════════
def page_history(cfg, db):
    latest = load_latest(db)
    last_evt = "—"
    if latest.get("event_timestamp"):
        try:
            last_evt = datetime.fromisoformat(str(latest["event_timestamp"])).strftime("%Y-%m-%d %H:%M UTC")
        except Exception:
            last_evt = str(latest["event_timestamp"])[:16]

    topbar(last_evt)
    breadcrumb("History — Flood Events Archive")

    # ── Filter state (session) ──────────────────────────────
    if "hist_state" not in st.session_state:
        st.session_state.hist_state = "All"
    if "hist_page" not in st.session_state:
        st.session_state.hist_page = 1
    if "hist_start" not in st.session_state:
        st.session_state.hist_start = datetime(2025, 8, 1).date()
    if "hist_end" not in st.session_state:
        st.session_state.hist_end = datetime(2025, 10, 31).date()
    if "hist_min_iou" not in st.session_state:
        st.session_state.hist_min_iou = 0.0
    if "hist_min_pop" not in st.session_state:
        st.session_state.hist_min_pop = 0

    demo = [
        ("2025-10-23 14:30 UTC", "EVT-2025-047", 45, 0.71, 1200, 5000, "Jonglei", "Bor South",
         ["Bor South", "Akobo East", "Twic East"], [3200, 1100, 700], [120, 900, 450, 300]),
        ("2025-10-08 09:15 UTC", "EVT-2025-041", 52, 0.68, 980, 3800, "Jonglei", "Akobo",
         ["Akobo East", "Nasir"], [2100, 900], [110, 860, 420, 280]),
        ("2025-09-19 06:45 UTC", "EVT-2025-033", 38, 0.79, 1540, 7200, "Unity", "Leer",
         ["Leer", "Bentiu"], [3400, 1800], [95, 780, 380, 250]),
        ("2025-09-02 11:05 UTC", "EVT-2025-028", 61, 0.66, 2200, 6100, "Upper Nile", "Malakal",
         ["Malakal", "Nasir"], [4100, 2000], [130, 990, 510, 340]),
        ("2025-08-14 22:10 UTC", "EVT-2025-021", 41, 0.73, 1750, 4900, "Jonglei", "Twic East",
         ["Twic East", "Bor South"], [2900, 2000], [105, 840, 400, 260]),
    ]

    events_df = load_events(db)
    use_real = (not events_df.empty) and "scene_id" in events_df.columns
    rows_all = demo
    if use_real and len(events_df) >= len(demo):
        real_rows = []
        for _, r in events_df.iterrows():
            real_rows.append((
                str(r.get("event_timestamp",""))[:16] + " UTC",
                str(r.get("scene_id",""))[:12],
                float(r.get("total_latency_seconds",0) or 0)/60,
                float(r.get("iou_score",0) or 0),
                float(r.get("flood_extent_ha",0) or 0),
                0, "—", "—", [], [], [0,0,0,0],
            ))
        rows_all = real_rows

    season_total = 47 if rows_all is demo else len(rows_all)
    season_max_extent = 3400.0 if rows_all is demo else max((r[4] for r in rows_all), default=0)

    st.markdown("<div style='padding:16px 20px 0;'>", unsafe_allow_html=True)
    kpi_row([
        ("◷ Total Events", f"{season_total}", "2025 flood season"),
        ("◔ Peak Month", f"<span style='color:{AMBER};'>August</span>", "12 events recorded"),
        ("▲ Max Flood Extent", f"<span style='color:{RED};'>{season_max_extent:,.0f} ha</span>", "Aug 2025 combined"),
        ("◉ Total Affected", "31,200", "cumulative season"),
    ])
    st.markdown("</div>", unsafe_allow_html=True)

    def row_matches(row):
        edt, eid, lat, iou, fha, fpop, state, county = row[0], row[1], row[2], row[3], row[4], row[5], row[6], row[7]
        try:
            row_date = datetime.strptime(edt[:10], "%Y-%m-%d").date()
        except Exception:
            row_date = None
        if row_date:
            if row_date < st.session_state.hist_start or row_date > st.session_state.hist_end:
                return False
        if st.session_state.hist_state != "All" and state != st.session_state.hist_state:
            return False
        if iou < st.session_state.hist_min_iou:
            return False
        if fpop < st.session_state.hist_min_pop:
            return False
        return True

    filtered_rows = [r for r in rows_all if row_matches(r)]
    filtered_total = len(filtered_rows)

    st.markdown("<div style='padding:16px 20px 0;'>", unsafe_allow_html=True)
    chart_col, filter_col = st.columns([7, 3], gap="medium")

    with chart_col:
        st.markdown(card(
            header("Flood Events by Month — 2025 Season", "events · hectares"),
            padding="16px 18px 6px",
        ), unsafe_allow_html=True)
        months = ["May", "Jun", "Jul", "Aug", "Sep", "Oct"]
        ev_counts = [2, 5, 8, 12, 10, 6]
        ha_totals = [800, 1500, 2200, 3400, 2800, 1700]
        fig = go.Figure()
        fig.add_bar(x=months, y=ev_counts, name="Events", marker_color=ACCENT, yaxis="y")
        fig.add_bar(x=months, y=ha_totals, name="Total ha", marker_color=PRIMARY, opacity=0.55, yaxis="y2")
        fig.update_layout(
            **pl(330),
            xaxis=ax(),
            yaxis=dict(gridcolor=BORDER, linecolor=BORDER, tickfont=dict(size=10), title="Events"),
            yaxis2=dict(overlaying="y", side="right", showgrid=False, tickfont=dict(size=10), title="Hectares"),
            barmode="group",
            legend=dict(orientation="h", y=-0.15, font=dict(size=10), bgcolor="rgba(0,0,0,0)"),
        )
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with filter_col:
        st.markdown(card(header("Filter Events"), padding="16px 18px 8px"), unsafe_allow_html=True)

        st.markdown(f"<div style='font-size:10px;color:{MUTED};margin:0 0 4px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;'>Date range</div>", unsafe_allow_html=True)
        dc1, dc2 = st.columns(2)
        with dc1:
            start_date = st.date_input("Start", value=st.session_state.hist_start,
                                       format="YYYY-MM-DD",
                                       label_visibility="collapsed", key="hist_start_input")
        with dc2:
            end_date = st.date_input("End", value=st.session_state.hist_end,
                                     format="YYYY-MM-DD",
                                     label_visibility="collapsed", key="hist_end_input")

        st.markdown(f"<div style='font-size:10px;color:{MUTED};margin:14px 0 6px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;'>State</div>", unsafe_allow_html=True)
        state_options = ["All", "Jonglei", "Unity", "Upper Nile"]
        sb_cols = st.columns(4)
        clicked_state = None
        for col, s in zip(sb_cols, state_options):
            with col:
                is_active = st.session_state.hist_state == s
                short = {"All": "All", "Jonglei": "Jon.", "Unity": "Unity", "Upper Nile": "U.N."}[s]
                if st.button(short, key=f"state_btn_{s}", width="stretch",
                           type="primary" if is_active else "secondary", help=s):
                    clicked_state = s
        if clicked_state:
            st.session_state.hist_state = clicked_state
            st.session_state.hist_page = 1
            st.rerun()

        st.markdown(
            f"<div style='display:flex;justify-content:space-between;margin:14px 0 2px;'>"
            f"<span style='font-size:10px;color:{MUTED};font-weight:600;text-transform:uppercase;letter-spacing:.04em;'>Min IoU</span>"
            f"<span style='font-family:DM Mono,monospace;font-size:11px;color:{ACCENT};'>{st.session_state.hist_min_iou:.2f}</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        min_iou = st.slider("min_iou_slider", 0.0, 1.0, st.session_state.hist_min_iou, 0.05,
                            label_visibility="collapsed", key="hist_iou_input")

        st.markdown(f"<div style='font-size:10px;color:{MUTED};margin:14px 0 4px;font-weight:600;text-transform:uppercase;letter-spacing:.04em;'>Min affected population</div>", unsafe_allow_html=True)
        min_pop = st.number_input("Min pop", min_value=0, value=st.session_state.hist_min_pop, step=100,
                                  label_visibility="collapsed", key="hist_pop_input")

        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
        if st.button("⌕ Apply Filters", key="hist_apply", width="stretch", type="primary"):
            st.session_state.hist_start = start_date
            st.session_state.hist_end = end_date
            st.session_state.hist_min_iou = min_iou
            st.session_state.hist_min_pop = min_pop
            st.session_state.hist_page = 1
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='padding:20px 20px 18px;'>", unsafe_allow_html=True)

    PAGE_SIZE = 2
    total_pages = max(1, -(-filtered_total // PAGE_SIZE)) if filtered_total > 0 else 1
    cur_page = min(st.session_state.hist_page, total_pages)

    st.markdown(header("Event Log", f"{filtered_total} events · showing page {cur_page} of {total_pages}"), unsafe_allow_html=True)

    if filtered_total == 0:
        st.markdown(card(
            f"<div style='text-align:center;padding:24px;color:{MUTED};font-size:12px;'>"
            f"No events match the current filters. Try widening the date range or lowering Min IoU.</div>"
        ), unsafe_allow_html=True)
    else:
        page_start = (cur_page - 1) * PAGE_SIZE
        page_rows = filtered_rows[page_start:page_start + PAGE_SIZE]

        for idx, (edt, eid, lat, iou, fha, fpop, state, county, top_villages, top_pops, stage_times) in enumerate(page_rows):
            lat_colour = GREEN if lat <= 60 else AMBER
            iou_colour = GREEN if iou >= 0.65 else AMBER
            row_key = f"{cur_page}_{idx}_{eid}"

            with st.expander(f"{edt}   ·   {eid}   ·   {state} / {county}"):
                st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
                mc, dc = st.columns([1, 4], gap="medium")
                with mc:
                    st.markdown(card(
                        f"<div style='font-size:9px;color:{MUTED};text-align:center;line-height:1.7;'>"
                        f"📍<br><span style='font-weight:600;color:#c9d1d9;'>{county}</span><br>"
                        f"<span style='color:{MUTED};'>{state}</span></div>",
                        padding="24px 8px",
                    ), unsafe_allow_html=True)
                with dc:
                    c1, c2, c3, c4 = st.columns(4)
                    with c1: st.markdown(f"<span style='font-size:10px;color:{MUTED};'>Latency</span><br><span style='font-family:DM Mono,monospace;font-size:14px;color:{lat_colour};font-weight:600;'>{lat:.0f} min</span>", unsafe_allow_html=True)
                    with c2: st.markdown(f"<span style='font-size:10px;color:{MUTED};'>IoU</span><br><span style='font-family:DM Mono,monospace;font-size:14px;color:{iou_colour};font-weight:600;'>{iou:.2f}</span>", unsafe_allow_html=True)
                    with c3: st.markdown(f"<span style='font-size:10px;color:{MUTED};'>Flood Extent</span><br><span style='font-family:DM Mono,monospace;font-size:14px;font-weight:600;'>{fha:,.0f} ha</span>", unsafe_allow_html=True)
                    with c4: st.markdown(f"<span style='font-size:10px;color:{MUTED};'>Affected Pop.</span><br><span style='font-family:DM Mono,monospace;font-size:14px;color:{AMBER};font-weight:600;'>{fpop:,}</span>", unsafe_allow_html=True)

                    if stage_times and any(stage_times):
                        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
                        s1, s2, s3, s4 = st.columns(4)
                        stage_labels = ["Data Acquisition", "Preprocessing", "Flood Detection", "Risk Assessment"]
                        for scol, slabel, sval in zip([s1, s2, s3, s4], stage_labels, stage_times):
                            with scol:
                                st.markdown(
                                    f"<span style='font-size:10px;color:{MUTED};'>{slabel}</span><br>"
                                    f"<span style='font-family:DM Mono,monospace;font-size:13px;font-weight:600;'>{sval} s</span>",
                                    unsafe_allow_html=True,
                                )

                    if top_villages:
                        villages_html = "  ·  ".join(f"{v} ({p:,})" for v, p in zip(top_villages, top_pops))
                        st.markdown(
                            f"<div style='margin-top:16px;font-size:10px;color:{MUTED};font-weight:600;"
                            f"text-transform:uppercase;letter-spacing:.04em;'>Top affected villages</div>"
                            f"<div style='font-family:DM Mono,monospace;font-size:11px;margin-top:2px;'>{villages_html}</div>",
                            unsafe_allow_html=True,
                        )

                    st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)
                    b1, b2, b3 = st.columns(3)
                    geojson_payload = json.dumps({"event_id": eid, "type": "FeatureCollection", "features": []}, indent=2)
                    csv_payload = (
                        "event_id,timestamp,latency_min,iou,flood_ha,affected_pop\n"
                        f"{eid},{edt},{lat:.0f},{iou:.2f},{fha:.0f},{fpop}\n"
                    )
                    pdf_payload = f"Situation Report — {eid}\n{edt}\nFlood extent: {fha:.0f} ha\nAffected: {fpop}"
                    with b1:
                        st.download_button("⬇ GeoJSON", data=geojson_payload,
                                          file_name=f"{eid}_flood_extent.geojson", mime="application/geo+json",
                                          key=f"geo_{row_key}", width="stretch")
                    with b2:
                        st.download_button("⬇ PDF Report", data=pdf_payload,
                                          file_name=f"{eid}_situation_report.txt", mime="text/plain",
                                          key=f"pdf_{row_key}", width="stretch")
                    with b3:
                        st.download_button("⬇ CSV Data", data=csv_payload,
                                          file_name=f"{eid}_data.csv", mime="text/csv",
                                          key=f"csv_{row_key}", width="stretch")

        st.markdown(f"<div style='height:1px;background:{BORDER};margin-top:14px;'></div>", unsafe_allow_html=True)
        st.markdown("<div style='height:14px;'></div>", unsafe_allow_html=True)

        pg1, pg2, pg3, pg4, pg5, pg6, pg7 = st.columns([3, 1, 1, 1, 1, 1, 3])
        with pg2:
            if st.button("‹ Prev", key="hist_prev", disabled=(cur_page <= 1), width="stretch"):
                st.session_state.hist_page = cur_page - 1
                st.rerun()
        page_buttons = [pg3, pg4, pg5]
        for i, col in enumerate(page_buttons[:total_pages], start=1):
            with col:
                if st.button(str(i), key=f"hist_pg_{i}", width="stretch",
                           type="primary" if i == cur_page else "secondary"):
                    st.session_state.hist_page = i
                    st.rerun()
        with pg6:
            if st.button("Next ›", key="hist_next", disabled=(cur_page >= total_pages), width="stretch"):
                st.session_state.hist_page = cur_page + 1
                st.rerun()

        st.markdown(
            f"<div style='text-align:center;font-family:DM Mono,monospace;font-size:11px;"
            f"color:{MUTED};margin-top:8px;'>Showing {len(page_rows)} of {filtered_total} events</div>",
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)


def page_performance(cfg, db):
    metrics = load_metrics(db)
    topbar("—")
    breadcrumb("Performance — System Metrics")

    avg_lat = float((metrics.get("avg_latency_seconds") or 2880)) / 60
    avg_iou = float(metrics.get("avg_iou") or 0.71)
    total_ev = int(metrics.get("total_events") or 47)

    st.markdown("<div style='padding:18px 20px 0;'>", unsafe_allow_html=True)
    kpi_row([
        ("Avg Total Latency", f"<span style='color:{GREEN if avg_lat<=60 else AMBER};'>{avg_lat:.0f} min</span>", "vs 60 min SLA"),
        ("SLA Compliance", f"<span style='color:{GREEN};'>91.5%</span>", f"of {total_ev} events"),
        ("Avg IoU Score", f"<span style='color:{ACCENT};'>{avg_iou:.2f}</span>", "season avg"),
        ("Alert Success Rate", f"<span style='color:{GREEN};'>91.3%</span>", "last 30 days"),
        ("System Uptime", f"<span style='color:{GREEN};'>99.2%</span>", "30-day rolling"),
    ])
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='padding:18px 20px 16px;'>", unsafe_allow_html=True)
    tab1, tab2, tab3 = st.tabs(["Pipeline Timing", "Detection Quality", "SLA Compliance"])
    dates = ["Aug 14", "Sep 02", "Sep 19", "Oct 08", "Oct 23"]

    with tab1:
        fig = go.Figure()
        fig.add_scatter(x=dates, y=[44, 61, 38, 52, 45], mode="lines+markers", line=dict(color=ACCENT, width=2.5))
        fig.add_hline(y=60, line_dash="dot", line_color=AMBER)
        fig.update_layout(**pl(260), xaxis=ax(), yaxis=ax(), showlegend=False)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with tab2:
        fig = go.Figure()
        fig.add_scatter(x=dates, y=[0.74, 0.63, 0.79, 0.68, 0.71], mode="lines+markers", line=dict(color=GREEN, width=2.5))
        fig.add_hline(y=0.65, line_dash="dot", line_color=AMBER)
        fig.update_layout(**pl(260), xaxis=ax(), yaxis=dict(range=[0.55, 0.85], gridcolor=BORDER), showlegend=False)
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

    with tab3:
        ms = ["Jun", "Jul", "Aug", "Sep", "Oct"]
        fig = go.Figure()
        fig.add_bar(x=ms, y=[4,7,10,9,5], name="Within SLA", marker_color=GREEN)
        fig.add_bar(x=ms, y=[1,1,2,1,1], name="Breach", marker_color=RED)
        fig.update_layout(**pl(260), barmode="stack", xaxis=ax(), yaxis=ax())
        st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# PAGE — EXPORT
# ════════════════════════════════════════════════════════════
def page_export(cfg, db):
    events_df = load_events(db)
    topbar("—")
    breadcrumb("Export — Data & Reports")

    st.markdown("<div style='padding:18px 20px 0;'>", unsafe_allow_html=True)
    kpi_row([
        ("Total Exports", "312", "all formats"),
        ("PDF Reports", "47", "one per event"),
        ("GeoJSON Downloads", "138", "flood layers"),
        ("Avg Export Size", "8.2 MB", "across formats"),
    ])
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div style='padding:18px 20px 16px;'>", unsafe_allow_html=True)
    st.markdown(header("Generate Export"), unsafe_allow_html=True)
    fmt = st.selectbox("Format", ["GeoJSON", "CSV Tabular", "PDF Report", "GeoTIFF"])
    csv_data = events_df.to_csv(index=False) if not events_df.empty else "event_id,timestamp\n"
    st.download_button(
        "Generate Export", data=csv_data,
        file_name=f"suddwatch_export_{datetime.now().strftime('%Y%m%d')}.csv",
        mime="text/csv",
    )
    st.markdown("</div>", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════
def main():
    setup_logging("WARNING")
    cfg = get_config()
    db = get_db(cfg)
    metrics = load_metrics(db)
    page = render_sidebar(metrics)

    if   page == "Home":        page_home(cfg, db)
    elif page == "History":     page_history(cfg, db)
    elif page == "Performance": page_performance(cfg, db)
    elif page == "Export":      page_export(cfg, db)


if __name__ == "__main__":
    main()
