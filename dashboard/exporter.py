"""
exporter.py — builds real export files from pipeline results for the
dashboard's Export page (used only in REAL data mode).

Formats:
  GeoJSON          flood-extent polygons (from the latest flood mask) +
                   affected villages + health facilities, as features
  GeoTIFF          the latest flood mask itself (1 = flood, 0 = dry, 255 = no data)
  Shapefile (ZIP)  flood-extent polygons and villages as two shapefiles
  CSV Tabular      one row per affected village (with its event)
  PDF Report       plain-text situation report (.txt)

Road geometries are not stored in the database (only names/lengths), so
roads appear in CSV/report outputs but not as map features.
"""
import csv
import io
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).parent.parent
REAL_DB = ROOT / "data" / "database" / "suddwatch.db"
MAX_POLYGON_PIXELS = 2_000  # mask is downsampled to at most this many pixels per side


def _conn():
    c = sqlite3.connect(str(REAL_DB))
    c.row_factory = sqlite3.Row
    return c


def _latest_mask_path() -> Optional[Path]:
    con = _conn()
    try:
        row = con.execute(
            "SELECT fm.geotiff_path FROM flood_masks fm JOIN events e ON e.event_id = fm.event_id "
            "WHERE e.status = 'completed' ORDER BY e.event_timestamp DESC, e.event_id DESC LIMIT 1"
        ).fetchone()
    finally:
        con.close()
    if row and row[0] and Path(row[0]).exists():
        return Path(row[0])
    return None


def flood_polygons() -> list:
    """GeoJSON geometries of the latest flood extent (empty list if unavailable)."""
    path = _latest_mask_path()
    if path is None:
        return []
    try:
        import numpy as np
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.features import shapes
        from rasterio.transform import Affine
        from rasterio.warp import transform_geom
    except ImportError:
        return []
    with rasterio.open(str(path)) as src:
        scale = max(1, int(np.ceil(max(src.height, src.width) / MAX_POLYGON_PIXELS)))
        h, w = src.height // scale or 1, src.width // scale or 1
        data = src.read(1, out_shape=(h, w), resampling=Resampling.mode)
        t = src.transform
        transform = Affine(t.a * src.width / w, t.b, t.c, t.d, t.e * src.height / h, t.f)
        crs = src.crs
    geoms = []
    for geom, value in shapes((data == 1).astype("uint8"), mask=(data == 1), transform=transform):
        if value == 1:
            if crs and crs.to_epsg() != 4326:
                geom = transform_geom(crs, "EPSG:4326", geom)
            geoms.append(geom)
    return geoms


def _villages() -> list:
    con = _conn()
    try:
        return [dict(r) for r in con.execute(
            "SELECT a.*, e.event_label FROM affected_populations a "
            "JOIN events e ON e.event_id = a.event_id ORDER BY a.event_id DESC")]
    finally:
        con.close()


def _infra() -> list:
    con = _conn()
    try:
        return [dict(r) for r in con.execute(
            "SELECT i.*, e.event_label FROM infrastructure_impacts i "
            "JOIN events e ON e.event_id = i.event_id ORDER BY i.event_id DESC")]
    finally:
        con.close()


def _point(lon, lat):
    return {"type": "Point", "coordinates": [lon, lat]} if lon is not None and lat is not None else None


def build(fmt: str, events: list, layers: set):
    """Return (bytes, filename, mime) for the chosen format, or None if not possible."""
    if not REAL_DB.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    layers = set(layers or [])

    if fmt == "GeoTIFF":
        path = _latest_mask_path()
        if path is None:
            return None
        return path.read_bytes(), f"suddwatch_flood_mask_{stamp}.tif", "image/tiff"

    if fmt == "CSV Tabular":
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["event_id", "village", "state", "latitude", "longitude",
                    "risk_pct", "risk_level", "population_1km_cell", "action"])
        for v in _villages():
            w.writerow([v["event_label"], v["village_name"], v["state"], v["latitude"],
                        v["longitude"], v["flood_risk_percentage"], v.get("risk_level"),
                        v["estimated_population"], v.get("recommended_action")])
        return buf.getvalue().encode(), f"suddwatch_villages_{stamp}.csv", "text/csv"

    if fmt == "GeoJSON":
        feats = []
        if not layers or "Flood Extent Polygon" in layers:
            for g in flood_polygons():
                feats.append({"type": "Feature", "geometry": g,
                              "properties": {"layer": "flood_extent"}})
        if not layers or "Affected Villages" in layers:
            for v in _villages():
                feats.append({"type": "Feature",
                              "geometry": _point(v["longitude"], v["latitude"]),
                              "properties": {"layer": "village", "event": v["event_label"],
                                             "name": v["village_name"], "state": v["state"],
                                             "risk_pct": v["flood_risk_percentage"],
                                             "population_1km_cell": v["estimated_population"]}})
        if not layers or "Health Facilities at Risk" in layers:
            for i in _infra():
                if i["infrastructure_type"] != "health_facility":
                    continue
                c = json.loads(i["coordinates"]) if i.get("coordinates") else {}
                feats.append({"type": "Feature", "geometry": _point(c.get("lon"), c.get("lat")),
                              "properties": {"layer": "health_facility", "event": i["event_label"],
                                             "name": i["name"], "type": i["facility_type"],
                                             "status": i["status"]}})
        data = json.dumps({"type": "FeatureCollection", "features": feats}, indent=1)
        return data.encode(), f"suddwatch_export_{stamp}.geojson", "application/geo+json"

    if fmt == "Shapefile (ZIP)":
        try:
            import geopandas as gpd
            from shapely.geometry import shape, Point
        except ImportError:
            return None
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            polys = flood_polygons()
            if polys:
                gpd.GeoDataFrame({"layer": ["flood"] * len(polys)},
                                 geometry=[shape(g) for g in polys], crs="EPSG:4326"
                                 ).to_file(tmp / "flood_extent.shp")
            vil = [v for v in _villages() if v["longitude"] is not None]
            if vil:
                gpd.GeoDataFrame(
                    {"event": [v["event_label"] for v in vil],
                     "name": [v["village_name"] for v in vil],
                     "risk_pct": [v["flood_risk_percentage"] for v in vil],
                     "pop_cell": [v["estimated_population"] for v in vil]},
                    geometry=[Point(v["longitude"], v["latitude"]) for v in vil],
                    crs="EPSG:4326").to_file(tmp / "villages.shp")
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
                for f in tmp.iterdir():
                    z.write(f, f.name)
        return buf.getvalue(), f"suddwatch_shapefiles_{stamp}.zip", "application/zip"

    if fmt == "PDF Report":
        lines = ["SUDDWATCH FLOOD SITUATION REPORT", "=" * 50,
                 f"Generated: {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}", "",
                 "EVENTS", "-" * 50]
        for e in events:
            iou = e.get("iou")
            lines.append(f"{e['id']} | {e['date_utc']} | {e['flood_ha']:,} ha | "
                         f"{e['affected']:,} people | IoU "
                         f"{f'{iou:.2f}' if iou is not None else 'not validated'}")
        lines += ["", "AFFECTED VILLAGES", "-" * 50]
        for v in _villages()[:200]:
            lines.append(f"{v['event_label']} | {v['village_name']} | {v['state']} | "
                         f"risk {v['flood_risk_percentage']:.0f}% | "
                         f"{v['estimated_population']} people in 1 km cell")
        lines += ["", "INFRASTRUCTURE", "-" * 50]
        for i in _infra()[:200]:
            extra = (f"{i['flooded_length_km']:.1f} km flooded"
                     if i.get("flooded_length_km") else i["status"])
            lines.append(f"{i['event_label']} | {i['infrastructure_type']} | {i['name']} | {extra}")
        return "\n".join(lines).encode(), f"suddwatch_situation_report_{stamp}.txt", "text/plain"

    return None
