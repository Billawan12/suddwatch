"""
styles.py — Global CSS and HTML helpers for SuddWatch dashboard.
"""

BG       = "#0d1117"
CARD     = "#161b22"
CARD_DARK= "#0b131c"
BORDER   = "#30363d"
FG       = "#e6edf3"
MUTED    = "#8b949e"
PRIMARY  = "#1a7fd4"
ACCENT   = "#0ea5e9"
SUCCESS  = "#22c55e"
WARNING  = "#f59e0b"
DANGER   = "#f85149"
PURPLE   = "#a78bfa"
INPUT_BG = "#1c2128"
MUTED_BG = "#21262d"

GLOBAL_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=DM+Mono:wght@400;500&family=Barlow+Condensed:wght@600;700&display=swap');

html, body, [data-testid="stAppViewContainer"], .stApp {{
    background-color: {BG} !important;
    color: {FG} !important;
    font-family: 'Inter', sans-serif !important;
}}

#MainMenu, footer {{ visibility: hidden; }}
[data-testid="stToolbarActions"] {{ visibility: hidden; }}
[data-testid="stDecoration"] {{ display: none !important; }}
[data-testid="stAppDeployButton"] {{ display: none !important; }}
header[data-testid="stHeader"] {{
    height: 2.5rem !important;
    background: transparent !important;
}}

.block-container {{
    padding-top: 0 !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    max-width: 100% !important;
}}

[data-testid="stSidebar"] {{
    background-color: {BG} !important;
    border-right: 1px solid {BORDER} !important;
}}
[data-testid="stSidebar"] .stMarkdown p {{
    color: {MUTED} !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 10px !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 16px 12px 4px 12px;
    margin: 0;
}}

[data-testid="stSidebar"] .stButton > button {{
    width: 100% !important;
    background: transparent !important;
    border: none !important;
    border-left: 2px solid transparent !important;
    border-radius: 0 !important;
    color: {MUTED} !important;
    font-family: 'Inter', sans-serif !important;
    font-size: 14px !important;
    font-weight: 500 !important;
    text-align: left !important;
    padding: 12px 16px !important;
    transition: all 0.15s !important;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
    background: {MUTED_BG} !important;
    color: {FG} !important;
}}

button[kind="primary"], [data-testid="baseButton-primary"] {{
    background-color: {PRIMARY} !important;
    border: 1px solid {PRIMARY} !important;
    color: white !important;
    border-radius: 4px !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 11px !important;
    font-weight: 600 !important;
}}
button[kind="primary"]:hover, [data-testid="baseButton-primary"]:hover {{
    background-color: #1e8fe8 !important;
}}
button[kind="secondary"], [data-testid="baseButton-secondary"] {{
    background: transparent !important;
    border: 1px solid {BORDER} !important;
    color: {MUTED} !important;
    border-radius: 4px !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 11px !important;
}}
button[kind="secondary"]:hover, [data-testid="baseButton-secondary"]:hover {{
    background: {MUTED_BG} !important;
    color: {FG} !important;
}}
button[disabled] {{ opacity: 0.4 !important; cursor: not-allowed !important; }}

.stTextInput > div > div > input,
.stNumberInput > div > div > input {{
    background-color: {INPUT_BG} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 4px !important;
    color: {FG} !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 11px !important;
}}
.stNumberInput button {{ display: none !important; }}

.stSelectbox > div > div {{
    background-color: {INPUT_BG} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 4px !important;
    color: {FG} !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 11px !important;
}}

.stSlider > div > div > div > div {{
    background-color: {PRIMARY} !important;
}}
.stSlider > div > div > div {{
    background-color: {MUTED_BG} !important;
}}

.stTabs [data-baseweb="tab-list"] {{
    background-color: {CARD} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 4px !important;
    gap: 0 !important;
    padding: 0 !important;
}}
.stTabs [data-baseweb="tab"] {{
    background-color: transparent !important;
    border-right: 1px solid {BORDER} !important;
    border-radius: 0 !important;
    color: {MUTED} !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 11px !important;
    text-transform: uppercase !important;
    letter-spacing: 0.05em !important;
    padding: 8px 16px !important;
}}
.stTabs [aria-selected="true"] {{
    background-color: {PRIMARY} !important;
    color: white !important;
}}
.stTabs [data-baseweb="tab-highlight"] {{ background-color: transparent !important; }}
.stTabs [data-baseweb="tab-border"] {{ display: none !important; }}

[data-testid="stExpander"] {{
    background-color: {CARD} !important;
    border: 1px solid {BORDER} !important;
    border-radius: 4px !important;
    margin-bottom: 4px !important;
}}
[data-testid="stExpander"] summary {{
    color: {FG} !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 11px !important;
}}

[data-testid="stDownloadButton"] > button {{
    background-color: transparent !important;
    border: 1px solid {BORDER} !important;
    border-radius: 4px !important;
    color: {FG} !important;
    font-family: 'DM Mono', monospace !important;
    font-size: 11px !important;
    padding: 6px 12px !important;
    transition: background 0.15s !important;
}}
[data-testid="stDownloadButton"] > button:hover {{
    background-color: {MUTED_BG} !important;
}}

@keyframes pulse {{
    0%,100% {{opacity:1}} 50% {{opacity:0.4}}
}}
</style>
"""


def badge(text: str, btype: str = "") -> str:
    styles = {
        "HIGH":        "color:#f85149;background:rgba(248,81,73,0.1);border:1px solid rgba(248,81,73,0.3)",
        "MEDIUM":      "color:#f59e0b;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3)",
        "LOW":         "color:#22c55e;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3)",
        "CRITICAL":    "color:#f85149;background:rgba(248,81,73,0.1);border:1px solid rgba(248,81,73,0.3)",
        "WARNING":     "color:#f59e0b;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3)",
        "INFO":        "color:#8b949e;background:rgba(33,38,45,0.3);border:1px solid #30363d",
        "OK":          "color:#22c55e;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3)",
        "STALE":       "color:#f59e0b;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3)",
        "AT RISK":     "color:#f59e0b;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3)",
        "At Risk":     "color:#f59e0b;background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3)",
        "FLOODED":     "color:#f85149;background:rgba(248,81,73,0.1);border:1px solid rgba(248,81,73,0.3)",
        "Flooded":     "color:#f85149;background:rgba(248,81,73,0.1);border:1px solid rgba(248,81,73,0.3)",
        "OPERATIONAL": "color:#22c55e;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3)",
        "Operational": "color:#22c55e;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3)",
        "PASS":        "color:#22c55e;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3)",
        "BREACH":      "color:#f85149;background:rgba(248,81,73,0.1);border:1px solid rgba(248,81,73,0.3)",
        "FAIL":        "color:#f85149;background:rgba(248,81,73,0.1);border:1px solid rgba(248,81,73,0.3)",
        "complete":    "color:#22c55e;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3)",
        "COMPLETE":    "color:#22c55e;background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3)",
        "ERR":         "color:#f85149;background:rgba(248,81,73,0.1);border:1px solid rgba(248,81,73,0.3)",
    }
    s = styles.get(text, styles.get(btype, styles["INFO"]))
    return (f'<span style="display:inline-block;padding:2px 6px;border-radius:4px;'
            f'font-family:\'DM Mono\',monospace;font-size:10px;{s}">{text}</span>')


def risk_badge(pct: int) -> str:
    if pct >= 75: return badge("HIGH")
    if pct >= 50: return badge("MEDIUM")
    return badge("LOW")


def card_header(title: str, right: str = "") -> str:
    return (f'<div style="display:flex;align-items:center;justify-content:space-between;'
            f'padding:10px 16px;border-bottom:1px solid {BORDER};margin-bottom:0">'
            f'<span style="font-family:\'Inter\',sans-serif;font-size:12px;font-weight:600;'
            f'color:{FG}">{title}</span>'
            f'<span style="font-family:\'DM Mono\',monospace;font-size:10px;color:{MUTED}">'
            f'{right}</span></div>')


def card_wrap(content: str, extra_style: str = "") -> str:
    return (f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:4px;'
            f'overflow:hidden;{extra_style}">{content}</div>')


def kpi_tile(label: str, value: str, sub: str, value_color: str = FG) -> str:
    return (f'<div style="background:{CARD};border:1px solid {BORDER};border-radius:4px;'
            f'padding:12px;display:flex;flex-direction:column;gap:6px">'
            f'<span style="font-family:\'DM Mono\',monospace;font-size:10px;text-transform:uppercase;'
            f'letter-spacing:0.05em;color:{MUTED}">{label}</span>'
            f'<span style="font-family:\'Barlow Condensed\',sans-serif;font-size:24px;'
            f'font-weight:700;line-height:1;color:{value_color}">{value}</span>'
            f'<span style="font-family:\'Inter\',sans-serif;font-size:10px;color:{MUTED}">{sub}</span>'
            f'</div>')


def section_label(text: str) -> str:
    return (f'<div style="font-family:\'DM Mono\',monospace;font-size:10px;text-transform:uppercase;'
            f'letter-spacing:0.1em;color:{MUTED};border-bottom:1px solid {BORDER};'
            f'padding-bottom:8px;margin-bottom:10px">{text}</div>')


def progress_bar(label: str, value: float, color: str, value_label: str = "") -> str:
    pct = min(100, value * 100)
    display = value_label or f"{value:.2f}"
    return (f'<div style="margin-bottom:10px">'
            f'<div style="display:flex;justify-content:space-between;margin-bottom:4px">'
            f'<span style="font-family:\'Inter\',sans-serif;font-size:11px;color:{MUTED}">{label}</span>'
            f'<span style="font-family:\'DM Mono\',monospace;font-size:11px;color:{color}">{display}</span>'
            f'</div>'
            f'<div style="width:100%;height:4px;background:{MUTED_BG};border-radius:9999px">'
            f'<div style="width:{pct:.0f}%;height:4px;background:{color};border-radius:9999px">'
            f'</div></div></div>')


def table_header_row(*cols) -> str:
    cells = ""
    for col in cols:
        label, align = col[0], col[1]
        cells += (f'<th style="text-align:{align};padding:8px 12px;font-family:\'DM Mono\','
                  f'monospace;font-size:10px;color:{MUTED};font-weight:400;white-space:nowrap">'
                  f'{label}</th>')
    return (f'<tr style="background:rgba(33,38,45,0.2);border-bottom:1px solid {BORDER}">'
            f'{cells}</tr>')


def table_cell(value: str, align: str = "left", color: str = FG,
               font: str = "Inter", size: str = "11px", extra: str = "") -> str:
    ff = "'DM Mono',monospace" if font == "mono" else "'Inter',sans-serif"
    return (f'<td style="padding:8px 12px;text-align:{align};font-family:{ff};'
            f'font-size:{size};color:{color};border-bottom:1px solid rgba(48,54,61,0.5);'
            f'{extra}">{value}</td>')
