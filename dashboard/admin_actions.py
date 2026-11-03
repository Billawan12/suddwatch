"""
admin_actions.py — the real actions behind the dashboard's Admin pages.

Every button on the Admin pages calls one of these functions, so the
pages change real settings instead of only showing a success message:

  Alert Config   → read/save SMS & email recipients (.env),
                   save alert thresholds (config/runtime_settings.json),
                   send a real test SMS + email
  Pipeline       → stage status from the database, launch run_pipeline.py
                   in the background, save calibration values
  Audit Log      → pipeline events + alerts from the database, plus
                   dashboard actions recorded in logs/dashboard_audit.jsonl
  System Health  → which credentials/data files are present, real folder
                   sizes, optional live connectivity test
"""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

REAL_DB = ROOT / "data" / "database" / "suddwatch.db"
AUDIT_FILE = ROOT / "logs" / "dashboard_audit.jsonl"
RUN_STATE = ROOT / "logs" / "dashboard_pipeline_run.json"
ENV_FILE = ROOT / ".env"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _config():
    from src.config import Config
    return Config()


# ── Audit trail ──────────────────────────────────────────────

def record(user: str, action: str, detail: str, kind: str = "info") -> None:
    """Append a dashboard action to logs/dashboard_audit.jsonl."""
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_FILE, "a") as f:
        f.write(json.dumps({"ts": _now(), "user": user or "—", "action": action,
                            "detail": detail, "type": kind}) + "\n")


def audit_log(limit: int = 200) -> list:
    """
    Chronological (newest first) list of (timestamp, user, action, detail, type)
    built from pipeline events, alert records and dashboard actions.
    """
    entries = []
    if AUDIT_FILE.exists():
        for line in AUDIT_FILE.read_text().splitlines():
            try:
                e = json.loads(line)
                entries.append((e["ts"], e["user"], e["action"], e["detail"], e["type"]))
            except (ValueError, KeyError):
                continue
    if REAL_DB.exists():
        import sqlite3
        try:
            conn = sqlite3.connect(str(REAL_DB))
            conn.row_factory = sqlite3.Row
            for r in conn.execute(
                    "SELECT e.*, fm.flood_extent_ha FROM events e "
                    "LEFT JOIN flood_masks fm ON fm.event_id = e.event_id "
                    "ORDER BY e.event_id DESC LIMIT ?", (limit,)):
                r = dict(r)
                label = r.get("event_label") or f"event {r['event_id']}"
                ts = _fmt(r.get("processing_end_time") or r.get("event_timestamp"))
                if r["status"] == "completed":
                    entries.append((ts, "pipeline", "PIPELINE_COMPLETE",
                                    f"{label} · {r.get('flood_extent_ha') or 0:,.0f} ha · "
                                    f"scene {r.get('scene_id')}", "success"))
                elif r["status"] == "failed":
                    entries.append((ts, "pipeline", "PIPELINE_FAILED",
                                    f"{label} · {(r.get('error_message') or 'see logs')[:160]}",
                                    "error"))
                else:
                    entries.append((ts, "pipeline", "PIPELINE_" + str(r["status"]).upper(),
                                    f"{label} · scene {r.get('scene_id')}", "info"))
            for r in conn.execute(
                    "SELECT a.*, e.event_label FROM alerts a "
                    "LEFT JOIN events e ON e.event_id = a.event_id "
                    "ORDER BY a.alert_id DESC LIMIT ?", (limit,)):
                status = r["delivery_status"]
                entries.append((_fmt(r["sent_timestamp"]), "pipeline",
                                f"ALERT_{str(status).upper()}",
                                f"{str(r['channel']).upper()} → {r['recipient']} "
                                f"({r['event_label'] or r['event_id']})",
                                {"failed": "error", "skipped": "info"}.get(status, "success")))
            conn.close()
        except sqlite3.Error:
            pass
    entries.sort(key=lambda e: e[0], reverse=True)
    return entries[:limit]


def _fmt(value) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return str(value)[:16]


# ── Recipients (.env) ────────────────────────────────────────

def get_recipients() -> tuple:
    cfg = _config()
    return list(cfg.sms_recipients), list(cfg.email_recipients)


def _parse_lines(text: str) -> list:
    """One entry per line; anything after ' - ' (e.g. a name) is ignored."""
    out = []
    for line in (text or "").splitlines():
        value = line.split(" - ")[0].split(",")[0].strip()
        if value:
            out.append(value)
    return out


def save_recipients(sms_text: Optional[str] = None, email_text: Optional[str] = None) -> dict:
    """Write SMS_RECIPIENTS / EMAIL_RECIPIENTS into .env. Returns what was saved."""
    from dotenv import set_key
    ENV_FILE.touch(exist_ok=True)
    saved = {}
    if sms_text is not None:
        sms = _parse_lines(sms_text)
        bad = [n for n in sms if not (n.startswith("+") and n[1:].isdigit() and len(n) >= 8)]
        if bad:
            raise ValueError(f"Not in E.164 format (+countrycode…): {', '.join(bad)}")
        set_key(str(ENV_FILE), "SMS_RECIPIENTS", ",".join(sms), quote_mode="never")
        saved["sms"] = sms
    if email_text is not None:
        emails = _parse_lines(email_text)
        bad = [e for e in emails if "@" not in e or "." not in e.split("@")[-1]]
        if bad:
            raise ValueError(f"Invalid email address: {', '.join(bad)}")
        set_key(str(ENV_FILE), "EMAIL_RECIPIENTS", ",".join(emails), quote_mode="never")
        saved["email"] = emails
    return saved


# ── Thresholds / calibration (config/runtime_settings.json) ──

def get_settings() -> dict:
    cfg = _config()
    return {
        "alert_flood_threshold_ha": cfg.alert_flood_threshold_ha,
        "alert_population_threshold": cfg.alert_population_threshold,
        "tpi_threshold": cfg.tpi_threshold,
        "change_detection_threshold": cfg.change_detection_threshold,
        "otsu_relaxation_factor": cfg.otsu_relaxation_factor,
        "min_flood_area_ha": cfg.min_flood_area_ha,
    }


def save_settings(**values) -> Path:
    from src.config import save_runtime_settings
    return save_runtime_settings(values, ROOT / "config" / "runtime_settings.json")


# ── Test alert ───────────────────────────────────────────────

def send_test_alert() -> dict:
    """Send a clearly-labelled TEST SMS and email to every configured recipient."""
    from src.alerts import AlertManager
    cfg = _config()
    alerter = AlertManager(cfg)
    stamp = _now()
    sms = alerter.send_sms(f"[SUDDWATCH TEST] Test message sent {stamp}. "
                           f"No flood event — please ignore.", "TEST")
    email = alerter.send_email(
        "[SuddWatch] TEST alert — please ignore",
        f"This is a test message from the SuddWatch dashboard, sent {stamp}.",
        f"<!DOCTYPE html><html><body><p>This is a <b>test</b> message from the "
        f"SuddWatch dashboard, sent {stamp}. No flood event.</p></body></html>",
        "TEST")
    return {"sms": sms, "email": email}


# ── Pipeline launch ──────────────────────────────────────────

def pipeline_status() -> dict:
    """State of the last pipeline run started from the dashboard."""
    if not RUN_STATE.exists():
        return {"running": False}
    try:
        state = json.loads(RUN_STATE.read_text())
    except ValueError:
        return {"running": False}
    pid = state.get("pid")
    running = False
    if pid:
        try:
            os.kill(pid, 0)
            running = True
            # A finished child that hasn't been reaped is a zombie — check
            try:
                waited, _ = os.waitpid(pid, os.WNOHANG)
                running = waited == 0
            except ChildProcessError:
                pass
        except (ProcessLookupError, PermissionError, OSError):
            running = False
    state["running"] = running
    log = Path(state.get("log", ""))
    if log.exists():
        state["log_tail"] = "\n".join(log.read_text(errors="replace").splitlines()[-15:])
    return state


def launch_pipeline(scene: str = "", no_alerts: bool = False, user: str = "") -> dict:
    """
    Start run_pipeline.py in the background (non-blocking).
    `scene` may be a path to a local scene file; empty = check Copernicus.
    """
    if pipeline_status().get("running"):
        raise RuntimeError("A pipeline run started from the dashboard is still running.")
    cmd = [sys.executable, str(ROOT / "run_pipeline.py")]
    scene = (scene or "").strip()
    if scene:
        path = Path(scene)
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            raise FileNotFoundError(f"Scene file not found: {path}")
        cmd += ["--scene", str(path)]
    if no_alerts:
        cmd.append("--no-alerts")
    log = ROOT / "logs" / f"dashboard_run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with open(log, "w") as out:
        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=out, stderr=subprocess.STDOUT,
                                start_new_session=True)
    state = {"pid": proc.pid, "started": _now(), "log": str(log), "cmd": " ".join(cmd[1:])}
    RUN_STATE.write_text(json.dumps(state))
    record(user, "PIPELINE_START",
           f"Manual run · {'scene ' + Path(scene).name if scene else 'Copernicus check'}"
           f"{' · alerts not sent' if no_alerts else ''}", "info")
    return state


# ── Stage status ─────────────────────────────────────────────

STAGE_LABELS = [
    ("data_acquisition", "Data Acquisition"),
    ("preprocessing", "Preprocessing (SNAP)"),
    ("flood_detection", "Flood Detection"),
    ("risk_assessment", "Risk Assessment"),
    ("alert_dispatch", "Alert Dispatch"),
]


def stage_status() -> list:
    """
    (name, status, detail) per stage from processing_logs, plus readiness
    checks (SNAP installed, credentials present, data files present).
    status ∈ {"Operational", "Degraded", "Not configured", "No runs yet"}
    """
    cfg = _config()
    stats = {}
    if REAL_DB.exists():
        import sqlite3
        try:
            conn = sqlite3.connect(str(REAL_DB))
            for row in conn.execute(
                    "SELECT stage_name, COUNT(*), AVG(duration_seconds), MAX(end_time), "
                    "SUM(status='completed') FROM processing_logs GROUP BY stage_name"):
                stats[row[0]] = row[1:]
            conn.close()
        except sqlite3.Error:
            pass

    ready = {
        "data_acquisition": (bool(cfg.copernicus_user and cfg.copernicus_password),
                             "Copernicus credentials missing in .env"),
        "preprocessing": (Path(cfg.snap_gpt_path).exists(),
                          f"SNAP gpt not found at {cfg.snap_gpt_path}"),
        "flood_detection": (True, ""),
        "risk_assessment": (cfg.worldpop_path.exists() and cfg.osm_villages_path.exists(),
                            "WorldPop / OSM data files missing"),
        "alert_dispatch": (bool(cfg.twilio_account_sid and cfg.smtp_user),
                           "Twilio / SMTP credentials missing in .env"),
    }
    out = []
    for key, label in STAGE_LABELS:
        ok, why = ready[key]
        if not ok:
            out.append((label, "Not configured", why))
            continue
        if key not in stats:
            out.append((label, "No runs yet", "Ready"))
            continue
        n, avg, last, n_ok = stats[key]
        status = "Operational" if n_ok == n else "Degraded"
        out.append((label, status, f"{n} runs · avg {avg or 0:.0f} s · last {_fmt(last)}"))
    return out


# ── System health ────────────────────────────────────────────

def _folder_size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return total


def _human(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


def storage() -> list:
    """(name, human size, % of the largest item) for the main data folders."""
    items = [
        ("SQLite database", ROOT / "data" / "database"),
        ("Raw Sentinel-1 scenes", ROOT / "data" / "raw"),
        ("Preprocessed scenes", ROOT / "data" / "processed"),
        ("Flood masks & summaries", ROOT / "data" / "flood_masks"),
        ("Static data (DEM, WorldPop, OSM)", ROOT / "data"),
        ("Log files", ROOT / "logs"),
    ]
    sizes = [(name, _folder_size(p) if p.exists() else 0) for name, p in items]
    # "Static data" = data/ minus the other data sub-folders
    data_total = dict(sizes)["Static data (DEM, WorldPop, OSM)"]
    others = sum(v for k, v in sizes[:4])
    sizes[4] = (sizes[4][0], max(data_total - others, 0))
    biggest = max((v for _, v in sizes), default=1) or 1
    return [(name, _human(v), int(100 * v / biggest)) for name, v in sizes]


def service_readiness() -> list:
    """(service, status, note) based on configuration — no network calls."""
    cfg = _config()
    def row(name, ok, note_ok, note_bad):
        return (name, "Configured" if ok else "Not configured", note_ok if ok else note_bad)
    return [
        row("Copernicus Data Space", cfg.copernicus_user and cfg.copernicus_password,
            f"User {cfg.copernicus_user[:4]}…", "Set COPERNICUS_USER / _PASSWORD"),
        row("Twilio SMS", cfg.twilio_account_sid and cfg.twilio_auth_token,
            f"{len(cfg.sms_recipients)} recipient(s)", "Set TWILIO_* in .env"),
        row("Gmail SMTP", cfg.smtp_user and cfg.smtp_password,
            f"{len(cfg.email_recipients)} recipient(s)", "Set SMTP_USER / _PASSWORD"),
        row("ESA SNAP GPT", Path(cfg.snap_gpt_path).exists(), cfg.snap_gpt_path,
            f"Not found at {cfg.snap_gpt_path}"),
        row("Local DEM", cfg.local_dem_path.exists(), cfg.local_dem_path.name,
            "data/dem/south_sudan_dem.tif missing"),
        row("WorldPop 2020", cfg.worldpop_path.exists(), cfg.worldpop_path.name,
            "data/worldpop/… missing"),
        row("OpenStreetMap layers", cfg.osm_roads_path.exists() and cfg.osm_villages_path.exists(),
            "roads / villages / health facilities", "data/osm/… missing"),
    ]


def connectivity_test() -> dict:
    """Live Twilio + SMTP login test (no messages sent)."""
    from src.alerts import AlertManager
    return AlertManager(_config()).test_connectivity()
