# ============================================================
# SuddWatch - End-to-end test
# File: tests/test_end_to_end.py
# Runs the REAL pipeline (no mocks) on a synthetic preprocessed
# scene with synthetic DEM, WorldPop and OSM layers, then checks
# that the database and the dashboard reader see the results.
# Alerts run in dry-run mode, so nothing is sent.
# ============================================================

import importlib
import sqlite3
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds
from shapely.geometry import LineString, Point

# Scene near Bor: 0.03° × 0.03° (~3.3 km square), 300 × 300 pixels (~11 m)
BOUNDS = (31.50, 6.20, 31.53, 6.23)
SCENE_NAME = "S1A_IW_GRDH_1SDV_20260901T033430_20260901T033455_060000_077777_ABCD_preprocessed_db.tif"


def _write_tif(path, data, bounds, dtype="float32", nodata=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    h, w = data.shape
    with rasterio.open(str(path), "w", driver="GTiff", height=h, width=w, count=1,
                       dtype=dtype, crs="EPSG:4326", transform=from_bounds(*bounds, w, h),
                       nodata=nodata) as d:
        d.write(data.astype(dtype), 1)


@pytest.fixture
def world(test_config):
    """Synthetic inputs: west half of the scene is flooded."""
    cfg = test_config
    rng = np.random.default_rng(7)
    scene = rng.normal(-8.0, 1.0, (300, 300))
    scene[:, :150] = rng.normal(-21.0, 1.0, (300, 150))
    scene_path = cfg.processed_dir / SCENE_NAME
    _write_tif(scene_path, scene, BOUNDS, nodata=np.nan)

    # Flat DEM (420 m) — the old TPI bug would have erased every flood pixel
    _write_tif(cfg.local_dem_path, 420 + rng.normal(0, 0.05, (200, 200)),
               (31.45, 6.15, 31.58, 6.28))

    # WorldPop-like grid: 0.01° cells with 100 people each
    _write_tif(cfg.worldpop_path, np.full((20, 20), 100.0), (31.45, 6.15, 31.65, 6.35),
               nodata=-99999)

    cfg.osm_dir.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame({"name": ["Wet Village", "Dry Village"], "place": ["village", "village"],
                      "geometry": [Point(31.505, 6.215), Point(31.528, 6.215)]},
                     crs="EPSG:4326").to_file(cfg.osm_villages_path, driver="GeoJSON")
    gpd.GeoDataFrame({"name": ["Cross Road", "East Track"], "highway": ["primary", "track"],
                      "geometry": [LineString([(31.501, 6.21), (31.529, 6.21)]),
                                   LineString([(31.525, 6.201), (31.525, 6.229)])]},
                     crs="EPSG:4326").to_file(cfg.osm_roads_path, driver="GeoJSON")
    gpd.GeoDataFrame({"name": ["Wet Clinic"], "other_tags": ['"amenity"=>"clinic"'],
                      "geometry": [Point(31.51, 6.22)]},
                     crs="EPSG:4326").to_file(cfg.osm_health_path, driver="GeoJSON")
    return cfg, scene_path


def test_full_pipeline_run(world):
    cfg, scene_path = world
    from src.pipeline import FloodPipeline

    pipeline = FloodPipeline(cfg)
    results = pipeline.run(scene_paths=[scene_path], dry_run_alerts=True)

    assert results["status"] == "completed", results
    r = results["scenes_processed"][0]
    # West half of a ~3.3 × 3.3 km box ≈ 550 ha
    assert 450 < r["flood_extent_ha"] < 650
    assert r["iou_score"] is None                      # no reference mask
    assert r["alert_triggered"] is True                # ≥ 500 ha
    assert r["alerts_sent"] == 0                       # dry run
    assert r["satellite_acquisition_time"].startswith("2026-09-01T03:34:30")

    con = sqlite3.connect(cfg.db_path)
    con.row_factory = sqlite3.Row
    ev = con.execute("SELECT * FROM events").fetchone()
    assert ev["status"] == "completed"
    assert ev["event_label"].startswith("EVT-")
    assert 400 < ev["affected_population"] < 700       # ~half of ~11 cells × 100
    assert ev["processing_seconds"] > 0
    fm = con.execute("SELECT * FROM flood_masks").fetchone()
    assert fm["event_id"] == ev["event_id"] and fm["flood_extent_ha"] > 400

    villages = [row["village_name"] for row in con.execute("SELECT * FROM affected_populations")]
    assert villages == ["Wet Village"]                 # the dry village is NOT listed

    infra = {row["name"]: dict(row) for row in con.execute("SELECT * FROM infrastructure_impacts")}
    assert "Cross Road" in infra and "East Track" not in infra
    assert 1.0 < infra["Cross Road"]["flooded_length_km"] < 2.2
    assert infra["Wet Clinic"]["status"] == "flooded"

    alerts = con.execute("SELECT * FROM alerts").fetchall()
    assert len(alerts) == 4                            # 2 SMS + 2 email recipients
    assert all(a["event_id"] == ev["event_id"] for a in alerts)
    assert all(a["delivery_status"] == "skipped" for a in alerts)

    stages = {row["stage_name"] for row in con.execute("SELECT stage_name FROM processing_logs")}
    assert {"preprocessing", "flood_detection", "risk_assessment", "alert_dispatch"} <= stages


def test_dashboard_reads_real_results(world, monkeypatch):
    cfg, scene_path = world
    from src.pipeline import FloodPipeline
    FloodPipeline(cfg).run(scene_paths=[scene_path], dry_run_alerts=True)

    sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))
    import db as dash_db
    importlib.reload(dash_db)
    monkeypatch.setattr(dash_db, "_REAL_DB", cfg.db_path)

    assert dash_db.data_mode() == "real"
    evt = dash_db.get_active_event()
    assert evt["id"].startswith("EVT-")
    assert evt["flood_ha"] > 400
    assert evt["iou"] is None
    vil = dash_db.get_villages(evt["event_id"])
    assert [v["village"] for v in vil] == ["Wet Village"]
    assert any(r["road"] == "Cross Road" for r in dash_db.get_roads())
    assert dash_db.get_health_facilities()[0]["name"] == "Wet Clinic"
    assert len(dash_db.get_alerts()) >= 1
    perf = dash_db.get_performance_rows()
    assert perf and perf[0]["flood_det_s"] >= 0


def test_dashboard_falls_back_to_demo(tmp_path, monkeypatch):
    sys.path.insert(0, str(Path(__file__).parent.parent / "dashboard"))
    import db as dash_db
    importlib.reload(dash_db)
    monkeypatch.setattr(dash_db, "_REAL_DB", tmp_path / "missing.db")
    monkeypatch.setattr(dash_db, "_DEMO_DB", tmp_path / "demo.db")
    dash_db.init_db()
    assert dash_db.data_mode() == "demo"
    assert dash_db.get_active_event()["id"].startswith("EVT-2025")
