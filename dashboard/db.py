"""
db.py — SuddWatch dashboard data layer.

Every page of dashboard/app.py gets its data from the functions at the
bottom of this file. Each function decides where the data comes from:

  1. REAL mode — the pipeline database data/database/suddwatch.db,
     written by src/database.py. Used as soon as it contains at least one
     COMPLETED event that has a flood mask (i.e. the full pipeline ran).
  2. DEMO mode — seeded example data in dashboard/suddwatch_dash.db
     (created automatically on first use). Used only when there are no
     real results yet, so the dashboard can be demonstrated without
     running the pipeline. The dashboard shows a "DEMO DATA" banner in
     this mode — call data_mode() to find out which mode is active.

Real-mode functions return the SAME keys as the demo tables so app.py
does not need to know which mode it is in. A value that the pipeline does
not produce (e.g. IoU when no reference mask exists, people served by a
clinic) is returned as None and shown as "—" / "not validated".
"""
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

# ── Database paths ─────────────────────────────────────────
_ROOT     = Path(__file__).parent.parent          # ~/suddwatch/
_REAL_DB  = _ROOT / "data" / "database" / "suddwatch.db"
_DEMO_DB  = Path(__file__).parent / "suddwatch_dash.db"

SLA_MINUTES = 60
STAGES = ["data_acquisition", "preprocessing", "flood_detection",
          "risk_assessment", "alert_dispatch"]
_STAGE_KEYS = {"data_acquisition": "data_acq_s", "preprocessing": "preproc_s",
               "flood_detection": "flood_det_s", "risk_assessment": "risk_ass_s",
               "alert_dispatch": "alert_s"}


def _conn(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _real_has_events() -> bool:
    """
    True when the pipeline database holds at least one completed event
    with a flood mask. Test/stub rows without a mask are ignored.
    """
    if not Path(_REAL_DB).exists():
        return False
    try:
        conn = _conn(_REAL_DB)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM events e "
                "JOIN flood_masks fm ON fm.event_id = e.event_id "
                "WHERE e.status = 'completed'"
            ).fetchone()[0]
        finally:
            conn.close()
        return count > 0
    except sqlite3.Error:
        return False


def _use_real() -> bool:
    return _real_has_events()


def data_mode() -> str:
    """'real' if the dashboard is showing pipeline results, else 'demo'."""
    return "real" if _use_real() else "demo"


_demo_ready = False


def _demo_conn() -> sqlite3.Connection:
    """Connection to the demo DB, creating and seeding it on first use."""
    global _demo_ready
    if not _demo_ready or not Path(_DEMO_DB).exists():
        init_db()
        _demo_ready = True
    return _conn(_DEMO_DB)


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
# Map the src/database.py schema → the dashboard's field names
# ════════════════════════════════════════════════════════════

def _fmt_date(value) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return str(value)[:16] + " UTC"


def _real_events(conn, limit=None) -> list:
    """Completed events with their mask, newest first, in dashboard format."""
    q = """
        SELECT e.*, fm.flood_extent_ha, fm.iou_score, fm.detection_method
        FROM events e
        JOIN flood_masks fm ON fm.event_id = e.event_id
        WHERE e.status = 'completed'
        ORDER BY e.event_timestamp DESC, e.event_id DESC
    """
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = [dict(r) for r in conn.execute(q).fetchall()]
    if not rows:
        return []
    ids = [r["event_id"] for r in rows]
    marks = ",".join("?" * len(ids))

    stage_s = defaultdict(dict)
    for r in conn.execute(
            f"SELECT event_id, stage_name, SUM(duration_seconds) AS d FROM processing_logs "
            f"WHERE event_id IN ({marks}) GROUP BY event_id, stage_name", ids):
        stage_s[r["event_id"]][r["stage_name"]] = r["d"] or 0

    states = defaultdict(Counter)
    top_village = {}
    for r in conn.execute(
            f"SELECT event_id, village_name, state, flood_risk_percentage, estimated_population "
            f"FROM affected_populations WHERE event_id IN ({marks}) "
            f"ORDER BY flood_risk_percentage DESC, estimated_population DESC", ids):
        states[r["event_id"]][r["state"] or "Unknown"] += 1
        top_village.setdefault(r["event_id"], r["village_name"])

    out = []
    for r in rows:
        eid = r["event_id"]
        st = states[eid].most_common(1)[0][0] if states[eid] else "Unknown"
        latency = r.get("total_latency_seconds")
        iou = r.get("iou_score")
        out.append({
            "id": r.get("event_label") or f"EVT-{eid:03d}",
            "event_id": eid,
            "scene_id": r.get("scene_id") or "—",
            "date_utc": _fmt_date(r.get("event_timestamp")),
            "acquired_utc": _fmt_date(r.get("satellite_acquisition_time")),
            "latency_min": int(round((latency or 0) / 60)),
            "processing_min": round((r.get("processing_seconds") or 0) / 60, 1),
            "latency_is_end_to_end": bool(r.get("satellite_acquisition_time")),
            "iou": float(iou) if iou is not None else None,
            "flood_ha": int(round(r.get("flood_extent_ha") or 0)),
            "affected": int(r.get("affected_population") or 0),
            "state": st,
            "county": top_village.get(eid, "—") or "—",
            "location": (top_village[eid] + (f", {st}" if st != "Unknown" else "")
                         if eid in top_village else f"Scene {r.get('scene_id') or eid}"),
            "detection_method": r.get("detection_method") or "otsu_gmm",
            **{_STAGE_KEYS[sn]: int(round(stage_s[eid].get(sn, 0))) for sn in STAGES},
        })
    return out


def _real_latest_event_id(conn):
    ev = _real_events(conn, limit=1)
    return ev[0]["event_id"] if ev else None


def _with_real(fn, default):
    """Run fn(conn) against the real DB, returning `default` on any DB error."""
    try:
        conn = _conn(_REAL_DB)
        try:
            return fn(conn)
        finally:
            conn.close()
    except sqlite3.Error:
        return default


def _demo_events_to_perf(rows):
    return [dict(r, processing_min=r.get("latency_min"), latency_is_end_to_end=True)
            for r in rows]


# ════════════════════════════════════════════════════════════
# PUBLIC API — called by app.py
# ════════════════════════════════════════════════════════════

def get_active_event() -> dict:
    """Most recent event (dashboard banner)."""
    if _use_real():
        ev = _with_real(lambda c: _real_events(c, limit=1), [])
        return ev[0] if ev else {}
    conn = _demo_conn()
    row = conn.execute("SELECT * FROM events ORDER BY date_utc DESC LIMIT 1").fetchone()
    conn.close()
    if not row:
        return {}
    d = dict(row)
    d.setdefault("event_id", d["id"])
    d.setdefault("location", f"{d.get('county', '—')}, {d.get('state', '—')}")
    return d


def get_all_events(state="All", min_iou=0.0, min_affected=0) -> list:
    """
    All events, newest first. Events without a validated IoU (None) are
    kept regardless of min_iou — they have no score to filter on.
    """
    if _use_real():
        events = _with_real(_real_events, [])
        return [e for e in events
                if (state == "All" or e["state"] == state)
                and (e["iou"] is None or e["iou"] >= min_iou)
                and e["affected"] >= min_affected]
    conn = _demo_conn()
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
    """Affected villages for an event (default: the latest event)."""
    if _use_real():
        def q(conn):
            eid = event_id if isinstance(event_id, int) else _real_latest_event_id(conn)
            if eid is None:
                return []
            rows = conn.execute(
                "SELECT * FROM affected_populations WHERE event_id = ? "
                "ORDER BY flood_risk_percentage DESC, estimated_population DESC", (eid,))
            out = []
            for r in rows:
                r = dict(r)
                pct = r.get("flood_risk_percentage") or 0
                out.append({
                    # keys used by the tables
                    "village": r.get("village_name") or "—",
                    "state": r.get("state") or "Unknown",
                    "population": int(r.get("estimated_population") or 0),
                    "risk_pct": int(round(pct)),
                    "action": r.get("recommended_action") or ("Evacuate" if pct >= 75 else "Monitor"),
                    # keys used by the map
                    "village_name": r.get("village_name"),
                    "latitude": r.get("latitude"),
                    "longitude": r.get("longitude"),
                    "flood_risk_percentage": pct,
                    "estimated_population": int(r.get("estimated_population") or 0),
                    "risk_level": r.get("risk_level") or ("High" if pct >= 75 else "Medium"),
                })
            return out
        return _with_real(q, [])
    conn = _demo_conn()
    rows = conn.execute("SELECT * FROM villages WHERE event_id = ?", ("EVT-2025-047",)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_roads() -> list:
    """Roads crossing flood water in the latest event."""
    if _use_real():
        def q(conn):
            eid = _real_latest_event_id(conn)
            rows = conn.execute(
                "SELECT * FROM infrastructure_impacts WHERE event_id = ? "
                "AND infrastructure_type = 'road' ORDER BY flooded_length_km DESC", (eid,))
            return [{
                "road": r["name"] or "Unnamed road",
                "type": (r["facility_type"] or "road").replace("_", " ").title(),
                "length_km": f"{(r['flooded_length_km'] or 0):.1f} km flooded",
                "alt_route": "—",
            } for r in rows]
        return _with_real(q, [])
    conn = _demo_conn()
    rows = conn.execute("SELECT * FROM roads").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_health_facilities() -> list:
    """Health facilities flooded or near flooding in the latest event."""
    if _use_real():
        def q(conn):
            eid = _real_latest_event_id(conn)
            rows = conn.execute(
                "SELECT * FROM infrastructure_impacts WHERE event_id = ? "
                "AND infrastructure_type = 'health_facility'", (eid,))
            return [{
                "name": r["name"] or "Unnamed facility",
                "type": (r["facility_type"] or "health facility").replace("_", " ").title(),
                "status": "Flooded" if r["status"] == "flooded" else "At Risk",
                "served": None,  # catchment population is not in the source data
            } for r in rows]
        return _with_real(q, [])
    conn = _demo_conn()
    rows = conn.execute("SELECT * FROM health_facilities").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_alerts() -> list:
    """Latest alert dispatch records (SMS/email)."""
    if _use_real():
        def q(conn):
            rows = conn.execute(
                "SELECT a.*, e.event_label FROM alerts a "
                "LEFT JOIN events e ON e.event_id = a.event_id "
                "ORDER BY a.alert_id DESC LIMIT 12")
            out = []
            for r in rows:
                status = (r["delivery_status"] or "").lower()
                when = _fmt_date(r["sent_timestamp"])
                out.append({
                    "time_utc": when[11:16] if len(when) >= 16 else when,
                    "alert_type": {"failed": "WARNING", "skipped": "INFO"}.get(status, "INFO"),
                    "message": (f"{(r['channel'] or '').upper()} {status} → {r['recipient']}"
                                + (" (dry run)" if status == "skipped" else "")
                                + (f" — {r['error_reason']}" if status == "failed" and r["error_reason"] else "")),
                    "state": r["event_label"] or f"event {r['event_id']}",
                })
            return out
        return _with_real(q, [])
    conn = _demo_conn()
    rows = conn.execute("SELECT * FROM alerts ORDER BY time_utc DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_data_sources() -> list:
    """Reference list of the datasets SuddWatch uses."""
    if _use_real():
        last = get_active_event().get("acquired_utc", "—")
        return [
            {"name": "Sentinel-1 SAR", "provider": "ESA Copernicus", "resolution": "10 m",
             "last_update": last, "status": "OK"},
            {"name": "DEM (Copernicus 30 m)", "provider": "ESA", "resolution": "30 m",
             "last_update": "Static baseline", "status": "OK"},
            {"name": "Population Grid", "provider": "WorldPop", "resolution": "1 km",
             "last_update": "2020 baseline", "status": "OK"},
            {"name": "OSM roads / villages / clinics", "provider": "OpenStreetMap",
             "resolution": "Vector", "last_update": "See data/osm", "status": "OK"},
        ]
    conn = _demo_conn()
    rows = conn.execute("SELECT * FROM data_sources").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_state_breakdown() -> list:
    """
    Per-state summary for the latest event. In real mode, villages are
    counted per state; flood area per state is only known when the whole
    event falls in one state (otherwise None → "—").
    """
    if _use_real():
        def q(conn):
            ev = _real_events(conn, limit=1)
            if not ev:
                return []
            ev = ev[0]
            rows = conn.execute(
                "SELECT COALESCE(state,'Unknown') AS state, COUNT(*) AS n, "
                "SUM(estimated_population) AS pop, MAX(flood_risk_percentage) AS maxrisk "
                "FROM affected_populations WHERE event_id = ? GROUP BY 1 ORDER BY pop DESC",
                (ev["event_id"],)).fetchall()
            n_alerts = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE event_id = ?", (ev["event_id"],)).fetchone()[0]
            single = len(rows) == 1
            return [{
                "state": r["state"],
                "flood_ha": ev["flood_ha"] if single else None,
                "affected": ev["affected"] if single else int(r["pop"] or 0),
                "alerts": n_alerts if single else "—",
                "risk": "HIGH" if (r["maxrisk"] or 0) >= 75 else "MEDIUM",
                "villages": r["n"],
            } for r in rows] or [{
                "state": ev["state"], "flood_ha": ev["flood_ha"], "affected": ev["affected"],
                "alerts": n_alerts, "risk": "LOW", "villages": 0,
            }]
        return _with_real(q, [])
    return [
        {"state": "Jonglei",    "flood_ha": 1200, "affected": 5000, "alerts": 24, "risk": "HIGH"},
        {"state": "Unity",      "flood_ha": 640,  "affected": 2100, "alerts": 11, "risk": "MEDIUM"},
        {"state": "Upper Nile", "flood_ha": 380,  "affected": 890,  "alerts": 6,  "risk": "LOW"},
    ]


def get_season_monthly() -> list:
    """Events and flooded area per month (keys: month, events, total_ha, flood_ha, affected)."""
    if _use_real():
        events = _with_real(_real_events, [])
        by_month = {}
        for e in sorted(events, key=lambda e: e["date_utc"]):
            key = e["date_utc"][:7]
            m = by_month.setdefault(key, {"month": key, "events": 0, "total_ha": 0, "affected": 0})
            m["events"] += 1
            m["total_ha"] += e["flood_ha"]
            m["affected"] += e["affected"]
        out = []
        for key, m in by_month.items():
            try:
                m["month"] = datetime.strptime(key, "%Y-%m").strftime("%b %Y")
            except ValueError:
                pass
            m["flood_ha"] = m["total_ha"]
            out.append(m)
        return out
    rows = [
        {"month": "May", "events": 3,  "total_ha": 420,  "affected": 1300},
        {"month": "Jun", "events": 5,  "total_ha": 890,  "affected": 2900},
        {"month": "Jul", "events": 9,  "total_ha": 2100, "affected": 7600},
        {"month": "Aug", "events": 12, "total_ha": 3400, "affected": 12800},
        {"month": "Sep", "events": 11, "total_ha": 3100, "affected": 11500},
        {"month": "Oct", "events": 7,  "total_ha": 1820, "affected": 6700},
    ]
    for r in rows:
        r["flood_ha"] = r["total_ha"]
    return rows


def get_performance_rows() -> list:
    """Per-event stage timings and latency (newest first)."""
    if _use_real():
        return _with_real(_real_events, [])
    conn = _demo_conn()
    rows = conn.execute(
        "SELECT id, date_utc, data_acq_s, preproc_s, flood_det_s, "
        "risk_ass_s, alert_s, latency_min, iou FROM events ORDER BY date_utc DESC"
    ).fetchall()
    conn.close()
    return _demo_events_to_perf([dict(r) for r in rows])


def get_performance_summary() -> dict:
    """
    Headline numbers for the Performance page, computed from the same
    rows the charts use (real or demo).
    """
    rows = get_performance_rows()
    n = len(rows)
    lat = [r["latency_min"] for r in rows]
    ious = [r["iou"] for r in rows if r.get("iou") is not None]
    within = sum(1 for v in lat if v <= SLA_MINUTES)

    alert_sent = alert_total = None
    stage_ok = {}
    if _use_real():
        def q(conn):
            a = conn.execute(
                "SELECT SUM(CASE WHEN delivery_status IN ('sent','delivered') THEN 1 ELSE 0 END), "
                "COUNT(*) FROM alerts WHERE delivery_status != 'skipped'").fetchone()
            s = {r["stage_name"]: (r["ok"], r["n"]) for r in conn.execute(
                "SELECT stage_name, SUM(status='completed') AS ok, COUNT(*) AS n "
                "FROM processing_logs GROUP BY stage_name")}
            return a, s
        (alert_sent, alert_total), stage_ok = _with_real(q, ((None, None), {}))
    else:
        alert_sent, alert_total = 21, 23   # demo figures
        stage_ok = {sn: (n, n) for sn in STAGES}

    monthly = defaultdict(lambda: [0, 0])
    for r in rows:
        key = str(r["date_utc"])[:7]
        monthly[key][0 if r["latency_min"] <= SLA_MINUTES else 1] += 1

    return {
        "n_events": n,
        "avg_latency_min": round(sum(lat) / n) if n else None,
        "sla_within": within,
        "sla_pct": round(100 * within / n, 1) if n else None,
        "avg_iou": round(sum(ious) / len(ious), 2) if ious else None,
        "n_validated": len(ious),
        "alert_success_pct": (round(100 * alert_sent / alert_total, 1)
                              if alert_total else None),
        "alert_total": alert_total or 0,
        "stage_success_pct": {sn: (round(100 * ok / tot) if tot else None)
                              for sn, (ok, tot) in stage_ok.items()},
        "sla_by_month": [(k, v[0], v[1]) for k, v in sorted(monthly.items())],
        "mode": data_mode(),
    }


def get_alert_counts() -> dict:
    """Message counts for the Home page 'Alert Delivery' card."""
    if _use_real():
        def q(conn):
            c = {"SMS sent": 0, "Email sent": 0, "Dry run": 0, "Failed": 0}
            for r in conn.execute("SELECT channel, delivery_status, COUNT(*) AS n "
                                  "FROM alerts GROUP BY 1, 2"):
                st = (r["delivery_status"] or "").lower()
                if st == "failed":
                    c["Failed"] += r["n"]
                elif st == "skipped":
                    c["Dry run"] += r["n"]
                elif r["channel"] == "sms":
                    c["SMS sent"] += r["n"]
                else:
                    c["Email sent"] += r["n"]
            return c
        return _with_real(q, {"SMS sent": 0, "Email sent": 0, "Dry run": 0, "Failed": 0})
    return {"SMS sent": 24, "Email sent": 12, "Dry run": 3, "Failed": 1}


def get_download_history() -> list:
    """Export download history (demo only — downloads are not logged yet)."""
    conn = _demo_conn()
    rows = conn.execute("SELECT * FROM download_history ORDER BY date_utc DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]
