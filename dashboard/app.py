"""
app.py — SuddWatch Operational Dashboard
Run: streamlit run dashboard/app.py
"""
import sys, json, io, csv
from datetime import datetime
from pathlib import Path

import streamlit as st
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).parent))
import db
import styles as s

# ── Page config ───────────────────────────────────────────────
st.set_page_config(page_title="SuddWatch", layout="wide",
                   initial_sidebar_state="expanded", page_icon="🌊")

# ── Init database ─────────────────────────────────────────────
db.init_db()
st.markdown(s.GLOBAL_CSS, unsafe_allow_html=True)

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
MAP_HTML = f"""
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
        "Home": """<svg width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/>
          <polyline points="9 22 9 12 15 12 15 22"/></svg>""",
        "History": """<svg width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/>
          <polyline points="12 6 12 12 16 14"/></svg>""",
        "Performance": """<svg width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <line x1="18" y1="20" x2="18" y2="10"/>
          <line x1="12" y1="20" x2="12" y2="4"/>
          <line x1="6" y1="20" x2="6" y2="14"/></svg>""",
        "Export": """<svg width="14" height="14" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
          <polyline points="7 10 12 15 17 10"/>
          <line x1="12" y1="15" x2="12" y2="3"/></svg>""",
    }
    with st.sidebar:
        st.markdown(f"""
        <div style="padding:16px;border-bottom:1px solid {s.BORDER}">
          <div style="display:flex;align-items:center;gap:8px">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                 stroke="{s.ACCENT}" stroke-width="2" stroke-linecap="round">
              <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
            </svg>
            <span style="font-family:'Barlow Condensed',sans-serif;font-size:18px;
                         font-weight:700;letter-spacing:0.025em;color:{s.FG}">SUDDWATCH</span>
          </div>
          <div style="font-family:'DM Mono',monospace;font-size:10px;
                      color:{s.MUTED};margin-top:4px">Flood Detection &amp; Alert System</div>
        </div>
        <div style="padding:16px 12px 4px;font-family:'DM Mono',monospace;font-size:10px;
                    text-transform:uppercase;letter-spacing:0.1em;color:{s.MUTED}">
          Navigation
        </div>""", unsafe_allow_html=True)

        for name in ["Home","History","Performance","Export"]:
            icon = _NAV_ICONS[name]
            active = st.session_state.page == name
            if active:
                st.markdown(
                    f"<div style='display:flex;align-items:center;gap:12px;"
                    f"background:#1c2a38;border-left:2px solid {s.PRIMARY};"
                    f"padding:12px 16px;color:{s.ACCENT};font-family:Inter,sans-serif;"
                    f"font-size:14px;font-weight:500;'>"
                    f"<span style='color:{s.ACCENT};'>{icon}</span>{name}</div>",
                    unsafe_allow_html=True,
                )
            else:
                if st.button(f"{name}", key=f"nav_{name}", width="stretch"):
                    st.session_state.page = name
                    st.session_state.export_done = False
                    st.rerun()

        st.markdown(f"""
        <div style="margin-top:32px;padding:16px;border-top:1px solid {s.BORDER}">
          <div style="display:flex;align-items:center;gap:8px">
            <div style="width:8px;height:8px;border-radius:50%;background:{s.SUCCESS};
                        animation:pulse 1.5s ease-in-out infinite"></div>
            <span style="font-family:'Inter',sans-serif;font-size:11px;color:{s.MUTED}">
              System operational</span>
          </div>
          <div style="font-family:'DM Mono',monospace;font-size:10px;
                      color:{s.MUTED};margin-top:6px">v2.4.1 — Sudd Basin</div>
        </div>""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# TOPBAR
# ════════════════════════════════════════════════════════════
def render_topbar(last_evt: str):
    cl, cr = st.columns([4, 1])
    with cl:
        st.markdown(f"""
        <div style="height:60px;display:flex;align-items:center;gap:12px;
                    border-bottom:1px solid {s.BORDER};">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
               stroke="{s.ACCENT}" stroke-width="2" stroke-linecap="round">
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>
          </svg>
          <span style="font-family:'Barlow Condensed',sans-serif;font-size:18px;
                       font-weight:700;color:{s.FG}">SUDDWATCH</span>
          <span style="border-left:1px solid {s.BORDER};padding-left:12px;
                       font-family:'DM Mono',monospace;font-size:12px;color:{s.MUTED}">
            Operational Flood Detection &amp; Alert System
          </span>
        </div>""", unsafe_allow_html=True)
    with cr:
        st.markdown(f"""
        <div style="height:60px;display:flex;align-items:center;justify-content:flex-end;
                    gap:12px;border-bottom:1px solid {s.BORDER}">
          <span style="font-family:'DM Mono',monospace;font-size:12px;color:{s.MUTED}">
            Last event: <span style="color:{s.ACCENT}">{last_evt}</span>
          </span>
        </div>""", unsafe_allow_html=True)
        if st.button("⟳ Refresh", key="refresh", width="stretch"):
            st.rerun()


def render_breadcrumb(text: str):
    st.markdown(f"""
    <div style="border-bottom:1px solid {s.BORDER};padding:8px 0;margin-bottom:16px">
      <span style="font-family:'DM Mono',monospace;font-size:11px;color:{s.MUTED}">{text}</span>
    </div>""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# PAGE — HOME
# ════════════════════════════════════════════════════════════
def page_home():
    event     = db.get_active_event()
    villages  = db.get_villages(event.get("id"))
    roads     = db.get_roads()
    hf        = db.get_health_facilities()
    alerts    = db.get_alerts()
    sources   = db.get_data_sources()
    breakdown = db.get_state_breakdown()

    cols = st.columns(6, gap="small")
    kpis = [
        ("TOTAL FLOOD EXTENT", "2,220 ha",   "across 3 states",   s.ACCENT),
        ("AFFECTED POPULATION","7,990",       "est. at risk",      s.WARNING),
        ("ACTIVE ALERTS",      "41",          "24h window",        s.DANGER),
        ("AVG ALERT LATENCY",  "45 min",      "vs 60 min SLA",     s.SUCCESS),
        ("DETECTION IOU",      "0.71",        "last acquisition",  s.SUCCESS),
        ("SEASON EVENTS",      "47",          "2025 flood season", s.FG),
    ]
    for col, (label, value, sub, color) in zip(cols, kpis):
        col.markdown(s.kpi_tile(label, value, sub, color), unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    map_col, panel_col = st.columns([3, 1], gap="small")
    with map_col:
        st.markdown(MAP_HTML, unsafe_allow_html=True)
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


# ════════════════════════════════════════════════════════════
# PAGE — HISTORY
# ════════════════════════════════════════════════════════════
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
        monthly = db.get_season_monthly()
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
            _evt = db.get_active_event()
            _year = str(_evt.get("date_utc","2025"))[:4] if _evt else "2025"
            st.markdown(s.card_header(f"Flood Events by Month — {_year} Season", "events · hectares"),
                        unsafe_allow_html=True)
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
    all_events = db.get_all_events(ss.hist_state, ss.hist_min_iou, ss.hist_min_pop)

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
                state_colors = {"Jonglei": s.SUCCESS, "Unity": s.PURPLE, "Upper Nile": s.ACCENT}
                dot_color = state_colors.get(evt["state"], s.ACCENT)
                with mc:
                    st.markdown(s.card_wrap(
                        f'<svg style="width:100%;height:150px" viewBox="0 0 180 150"'
                        f' xmlns="http://www.w3.org/2000/svg">'
                        f'<rect width="180" height="150" fill="#07111a"/>'
                        # River
                        f'<path d="M 90 5 C 85 35 95 60 88 90 C 82 115 88 135 88 148"'
                        f' fill="none" stroke="{s.PRIMARY}" stroke-width="3" opacity="0.6"/>'
                        # Flood zone
                        f'<polygon points="45,30 130,25 145,70 135,110 95,125 55,115 40,75"'
                        f' fill="{s.ACCENT}" fill-opacity="0.2"'
                        f' stroke="{s.ACCENT}" stroke-width="1.5" stroke-dasharray="4,2"/>'
                        # State dot (main affected area)
                        f'<circle cx="88" cy="75" r="6" fill="{dot_c}" stroke="white" stroke-width="1.5"/>'
                        # Other village dots
                        f'<circle cx="115" cy="55" r="4" fill="{s.WARNING}" stroke="white" stroke-width="1"/>'
                        f'<circle cx="65" cy="105" r="4" fill="{s.SUCCESS}" stroke="white" stroke-width="1"/>'
                        # Health cross
                        f'<line x1="83" y1="72" x2="93" y2="72" stroke="{s.DANGER}" stroke-width="2"/>'
                        f'<line x1="88" y1="67" x2="88" y2="77" stroke="{s.DANGER}" stroke-width="2"/>'
                        # Label
                        f'<text x="6" y="144" fill="{s.MUTED}" font-family="DM Mono" font-size="8">'
                        f'{evt["county"]} · {evt["state"]}</text>'
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
                    villages = db.get_villages("EVT-2025-047")
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
    tab1, tab2, tab3 = st.tabs(["Pipeline Timing", "Detection Quality", "SLA Compliance"])

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
        perf = db.get_performance_rows()
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

    all_events = db.get_all_events()
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

            if not st.session_state.export_done:
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
                        f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
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
                             f"Generated: {datetime.utcnow()}\n"
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
    hist = db.get_download_history()

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
# MAIN
# ════════════════════════════════════════════════════════════
render_sidebar()
event    = db.get_active_event()
last_evt = event.get("date_utc","—") if event else "—"
render_topbar(last_evt)
render_breadcrumb({
    "Home":"Dashboard — Live Event",
    "History":"History — Flood Events Archive",
    "Performance":"Performance — System Metrics",
    "Export":"Export — Data & Reports",
}.get(st.session_state.page,""))

page = st.session_state.page
if   page == "Home":        page_home()
elif page == "History":     page_history()
elif page == "Performance": page_performance()
elif page == "Export":      page_export()
