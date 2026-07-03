"""
db.py — SuddWatch dashboard database module.

Priority:
  1. Reads from the real pipeline database (data/database/suddwatch.db)
     populated by src/database.py when Sprint 3 pipeline runs.
  2. Falls back to seeded demo data (dashboard/suddwatch_dash.db)
     when the real database is empty or missing.

This means: once the pipeline runs, the dashboard automatically
shows real data with zero changes needed here.
"""

import sqlite3
import json
from pathlib import Path

# ── Database paths ─────────────────────────────────────────
_ROOT     = Path(__file__).parent.parent          # ~/suddwatch/
_REAL_DB  = _ROOT / "data" / "database" / "suddwatch.db"
_DEMO_DB  = Path(__file__).parent / "suddwatch_dash.db"


def _conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _real_has_events() -> bool:
    """Check if the real pipeline database has meaningful flood events.
    Only returns True when events have actual flood detection results
    (iou_score > 0), meaning the full pipeline has run successfully.
    Test/stub events with iou_score=0 are ignored."""
    if not _REAL_DB.exists():
        return False
    try:
        conn = _conn(_REAL_DB)
        count = conn.execute(
            "SELECT COUNT(*) FROM events WHERE iou_score > 0 AND flood_extent_ha > 0"
        ).fetchone()[0]
        conn.close()
        return count > 0
    except Exception:
        return False


def _use_real() -> bool:
    """Return True if we should use the real pipeline database."""
    return _real_has_events()


# ════════════════════════════════════════════════════════════
# DEMO DATABASE SETUP (used when pipeline hasn't run yet)
# ════════════════════════════════════════════════════════════

def init_db():
    """Create and seed the demo database if it doesn't exist."""
    conn = _conn(_DEMO_DB)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE IF NOT EXISTS events (
            id TEXT PRIMARY KEY, date_utc TEXT, latency_min INTEGER,
            iou REAL, flood_ha INTEGER, affected INTEGER,
            state TEXT, county TEXT,
            data_acq_s INTEGER, preproc_s INTEGER,
            flood_det_s INTEGER, risk_ass_s INTEGER, alert_s INTEGER
        );
        CREATE TABLE IF NOT EXISTS villages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT, village TEXT, state TEXT,
            population INTEGER, risk_pct INTEGER, action TEXT
        );
        CREATE TABLE IF NOT EXISTS roads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            road TEXT, type TEXT, length_km TEXT, alt_route TEXT
        );
        CREATE TABLE IF NOT EXISTS health_facilities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, type TEXT, status TEXT, served INTEGER
        );
        CREATE TABLE IF NOT EXISTS alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            time_utc TEXT, alert_type TEXT, message TEXT, state TEXT
        );
        CREATE TABLE IF NOT EXISTS data_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT, provider TEXT, resolution TEXT,
            last_update TEXT, status TEXT
        );
        CREATE TABLE IF NOT EXISTS download_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            filename TEXT, username TEXT, date_utc TEXT,
            size_label TEXT, status TEXT
        );
    """)
    if c.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0:
        _seed(c)
    conn.commit()
    conn.close()


def _seed(c):
    c.executemany("INSERT OR IGNORE INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        ("EVT-2025-047","2025-10-23 14:30 UTC",45,0.71,1200,5000,"Jonglei","Bor South",120,900,450,300,150),
        ("EVT-2025-041","2025-10-08 09:15 UTC",52,0.68,980,3800,"Jonglei","Akobo",145,980,510,320,165),
        ("EVT-2025-033","2025-09-19 06:45 UTC",38,0.79,1540,7200,"Jonglei","Twic East",95,820,390,250,120),
        ("EVT-2025-028","2025-09-02 11:20 UTC",61,0.63,760,2900,"Unity","Leer",180,1100,580,410,200),
        ("EVT-2025-021","2025-08-14 16:55 UTC",44,0.74,1100,4400,"Upper Nile","Malakal",115,880,440,290,140),
    ])
    c.executemany(
        "INSERT INTO villages (event_id,village,state,population,risk_pct,action) VALUES (?,?,?,?,?,?)", [
        ("EVT-2025-047","Bor South","Jonglei",12400,87,"Evacuate"),
        ("EVT-2025-047","Akobo East","Jonglei",8200,74,"Alert"),
        ("EVT-2025-047","Twic East","Jonglei",6700,61,"Monitor"),
        ("EVT-2025-047","Duk Padiet","Jonglei",3900,45,"Monitor"),
        ("EVT-2025-047","Nyirol","Jonglei",2100,32,"Watch"),
    ])
    c.executemany("INSERT INTO roads (road,type,length_km,alt_route) VALUES (?,?,?,?)", [
        ("Bor–Malakal A1","Primary","142 km","Air only"),
        ("Akobo–Pochalla B4","Secondary","88 km","Boat route"),
        ("Twic Loop C9","Tertiary","34 km","Detour via D11"),
        ("Duk Feeder F2","Feeder","19 km","None"),
    ])
    c.executemany("INSERT INTO health_facilities (name,type,status,served) VALUES (?,?,?,?)", [
        ("Bor State Hospital","Hospital","At Risk",45000),
        ("Akobo PHC","Primary HC","Flooded",12000),
        ("Twic Health Post","Health Post","Operational",4200),
        ("Duk Clinic","Clinic","At Risk",3100),
    ])
    c.executemany("INSERT INTO alerts (time_utc,alert_type,message,state) VALUES (?,?,?,?)", [
        ("14:32","CRITICAL","Bor South — evacuation order issued","Jonglei"),
        ("14:18","WARNING","Leer flood extent +12% in 6 h","Unity"),
        ("13:55","INFO","Sentinel-1 acquisition complete — scene 047","System"),
        ("13:40","WARNING","A1 highway submerged at km 234","Jonglei"),
        ("13:15","INFO","SMS batch delivered — 24/24 recipients","System"),
        ("12:50","WARNING","Akobo PHC access route cut","Jonglei"),
        ("12:30","INFO","Risk assessment model run completed","System"),
    ])
    c.executemany(
        "INSERT INTO data_sources (name,provider,resolution,last_update,status) VALUES (?,?,?,?,?)", [
        ("Sentinel-1 SAR","ESA Copernicus","10 m","2025-10-23 13:10","OK"),
        ("CHIRPS Rainfall","UCSB / FEWS","5 km","2025-10-23 06:00","OK"),
        ("DEM (SRTM)","NASA / USGS","30 m","Static baseline","OK"),
        ("Population Grid","WorldPop","100 m","2020 baseline","OK"),
        ("OSM Road Network","OpenStreetMap","Vector","2025-09-01","STALE"),
    ])
    c.executemany(
        "INSERT INTO download_history (filename,username,date_utc,size_label,status) VALUES (?,?,?,?,?)", [
        ("EVT-2025-047_flood_extent.geojson","ops-user-1","2025-10-23 15:02","2.4 MB","complete"),
        ("EVT-2025-047_situation_report.pdf","ops-user-2","2025-10-23 14:55","4.8 MB","complete"),
        ("EVT-2025-041_affected_villages.csv","ops-user-1","2025-10-09 11:30","94 KB","complete"),
        ("EVT-2025-033_flood_extent.tif","ops-user-3","2025-09-20 08:14","48 MB","complete"),
        ("season_2025_all_events.csv","ops-user-2","2025-10-22 16:40","620 KB","complete"),
    ])


# ════════════════════════════════════════════════════════════
# REAL DATABASE ADAPTERS
# Maps our src/database.py schema → dashboard's expected format
# ════════════════════════════════════════════════════════════

def _real_get_active_event() -> dict:
    """Read latest event from real pipeline database."""
    conn = _conn(_REAL_DB)
    try:
        # src/database.py events table columns:
        # id, scene_id, event_timestamp, status, flood_extent_ha,
        # iou_score, total_latency_seconds, geotiff_path, risk_summary_path
        row = conn.execute(
            "SELECT * FROM events ORDER BY event_timestamp DESC LIMIT 1"
        ).fetchone()
        if not row:
            return {}
        r = dict(row)
        return {
            "id":          r.get("scene_id", r.get("id", "—")),
            "date_utc":    str(r.get("event_timestamp",""))[:16] + " UTC",
            "latency_min": int((r.get("total_latency_seconds") or 0) / 60),
            "iou":         float(r.get("iou_score") or 0),
            "flood_ha":    int(r.get("flood_extent_ha") or 0),
            "affected":    0,
            "state":       "—",
            "county":      "—",
            "data_acq_s":  0,
            "preproc_s":   0,
            "flood_det_s": 0,
            "risk_ass_s":  0,
            "alert_s":     0,
        }
    except Exception:
        return {}
    finally:
        conn.close()


def _real_get_all_events(state="All", min_iou=0.0, min_affected=0) -> list:
    """Read all events from real pipeline database."""
    conn = _conn(_REAL_DB)
    try:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY event_timestamp DESC"
        ).fetchall()
        result = []
        for r in rows:
            r = dict(r)
            iou = float(r.get("iou_score") or 0)
            if iou < min_iou:
                continue
            result.append({
                "id":          r.get("scene_id", "—"),
                "date_utc":    str(r.get("event_timestamp",""))[:16] + " UTC",
                "latency_min": int((r.get("total_latency_seconds") or 0) / 60),
                "iou":         iou,
                "flood_ha":    int(r.get("flood_extent_ha") or 0),
                "affected":    0,
                "state":       "—",
                "county":      "—",
                "data_acq_s":  0,
                "preproc_s":   0,
                "flood_det_s": 0,
                "risk_ass_s":  0,
                "alert_s":     0,
            })
        return result
    except Exception:
        return []
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════
# PUBLIC API — called by app.py
# Auto-routes to real DB or demo DB
# ════════════════════════════════════════════════════════════

def get_active_event() -> dict:
    if _use_real():
        return _real_get_active_event()
    conn = _conn(_DEMO_DB)
    row = conn.execute(
        "SELECT * FROM events ORDER BY date_utc DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_all_events(state="All", min_iou=0.0, min_affected=0) -> list:
    if _use_real():
        return _real_get_all_events(state, min_iou, min_affected)
    conn = _conn(_DEMO_DB)
    q = "SELECT * FROM events WHERE iou >= ? AND affected >= ?"
    p = [min_iou, min_affected]
    if state != "All":
        q += " AND state = ?"
        p.append(state)
    q += " ORDER BY date_utc DESC"
    rows = conn.execute(q, p).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_villages(event_id=None) -> list:
    # Always use demo DB — real pipeline villages come from risk_assessment JSON
    # which Sprint 3 will wire in. The demo event_id is EVT-2025-047.
    # When real pipeline runs, use the first demo event's villages as fallback.
    conn = _conn(_DEMO_DB)
    event_id = "EVT-2025-047"  # always show demo villages until Sprint 3
    if event_id:
        rows = conn.execute(
            "SELECT * FROM villages WHERE event_id = ?", (event_id,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM villages").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_roads() -> list:
    conn = _conn(_DEMO_DB)
    rows = conn.execute("SELECT * FROM roads").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_health_facilities() -> list:
    conn = _conn(_DEMO_DB)
    rows = conn.execute("SELECT * FROM health_facilities").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_alerts() -> list:
    # Real alerts will come from src/database.py alerts table in Sprint 3
    # For now always use demo
    conn = _conn(_DEMO_DB)
    rows = conn.execute(
        "SELECT * FROM alerts ORDER BY time_utc DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_data_sources() -> list:
    conn = _conn(_DEMO_DB)
    rows = conn.execute("SELECT * FROM data_sources").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_state_breakdown() -> list:
    """Always uses computed demo breakdown for now.
    Sprint 3 will wire this to real event data via risk_assessment.py."""
    return [
        {"state":"Jonglei",    "flood_ha":1200,"affected":5000,"alerts":24,"risk":"HIGH"},
        {"state":"Unity",      "flood_ha":640, "affected":2100,"alerts":11,"risk":"MEDIUM"},
        {"state":"Upper Nile", "flood_ha":380, "affected":890, "alerts":6, "risk":"LOW"},
    ]


def get_season_monthly() -> list:
    return [
        {"month":"May","events":3, "total_ha":420},
        {"month":"Jun","events":5, "total_ha":890},
        {"month":"Jul","events":9, "total_ha":2100},
        {"month":"Aug","events":12,"total_ha":3400},
        {"month":"Sep","events":11,"total_ha":3100},
        {"month":"Oct","events":7, "total_ha":1820},
    ]


def get_performance_rows() -> list:
    if _use_real():
        return _real_get_all_events()
    conn = _conn(_DEMO_DB)
    rows = conn.execute(
        "SELECT id, date_utc, data_acq_s, preproc_s, flood_det_s, "
        "risk_ass_s, alert_s, latency_min FROM events ORDER BY date_utc DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_download_history() -> list:
    conn = _conn(_DEMO_DB)
    rows = conn.execute(
        "SELECT * FROM download_history ORDER BY date_utc DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
