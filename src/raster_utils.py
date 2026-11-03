# ============================================================
# SuddWatch - Raster helper functions
# File: src/raster_utils.py
# Purpose: Small, shared helpers for putting different rasters
#          (DEM, exclusion masks, baseline scene, WorldPop) onto
#          the same pixel grid as a Sentinel-1 scene, and for
#          converting pixel counts into real-world areas.
#
# Why this exists: reading a raster with `out_shape=` only
# stretches the WHOLE file to the requested size — it does not
# cut out the part that overlaps the scene. Every overlay in the
# original code was therefore spatially misaligned. These helpers
# use rasterio.warp.reproject, which matches pixels by location.
#
# Course: SWE3090 - Software Project 1
# Student: Madut Chan (671336)
# ============================================================

import math
from typing import Optional, Tuple

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.enums import Resampling
from rasterio.transform import Affine, array_bounds
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import from_bounds as window_from_bounds
from scipy.ndimage import uniform_filter

WGS84 = CRS.from_epsg(4326)
M_PER_DEG_LAT = 110_574.0     # metres per degree of latitude
M_PER_DEG_LON_EQ = 111_320.0  # metres per degree of longitude at the equator


def grid_crs(profile: dict) -> CRS:
    """CRS from a rasterio profile, defaulting to WGS84 (SNAP's output)."""
    crs = profile.get("crs")
    return CRS.from_user_input(crs) if crs else WGS84


def grid_bounds(transform: Affine, height: int, width: int) -> Tuple[float, float, float, float]:
    """(left, bottom, right, top) of a grid."""
    west, south, east, north = array_bounds(height, width, transform)
    return west, south, east, north


def pixel_size_m(transform: Affine, crs: CRS, height: int = 1) -> float:
    """Approximate pixel edge length in metres (mean of x and y)."""
    if crs.is_geographic:
        _, south, _, north = grid_bounds(transform, height, 1)
        lat = math.radians((south + north) / 2.0)
        px = abs(transform.a) * M_PER_DEG_LON_EQ * math.cos(lat)
        py = abs(transform.e) * M_PER_DEG_LAT
        return (px + py) / 2.0
    return (abs(transform.a) + abs(transform.e)) / 2.0


def row_pixel_areas_m2(transform: Affine, crs: CRS, height: int) -> np.ndarray:
    """
    Area of one pixel in each row, in m².

    For a geographic (lat/lon) grid a pixel gets narrower further from the
    equator, so the area is computed per row using that row's latitude.
    For a projected grid every pixel has the same area.
    """
    if not crs.is_geographic:
        return np.full(height, abs(transform.a * transform.e), dtype=np.float64)
    rows = np.arange(height) + 0.5
    lats = transform.f + rows * transform.e
    width_m = abs(transform.a) * M_PER_DEG_LON_EQ * np.cos(np.radians(lats))
    height_m = abs(transform.e) * M_PER_DEG_LAT
    return width_m * height_m


def mask_area_ha(mask: np.ndarray, transform: Affine, crs: CRS) -> float:
    """Total area (hectares) of pixels where mask == 1."""
    per_row = (mask == 1).sum(axis=1).astype(np.float64)
    areas = row_pixel_areas_m2(transform, crs, mask.shape[0])
    return float((per_row * areas).sum() / 10_000.0)


def align_to_grid(
    src_path,
    dst_shape: Tuple[int, int],
    dst_transform: Affine,
    dst_crs: CRS,
    resampling: Resampling = Resampling.bilinear,
    fill_value: float = np.nan,
    dtype=np.float32,
) -> np.ndarray:
    """
    Read band 1 of `src_path` resampled onto the destination grid.

    Only the overlapping part of the source is used; destination pixels with
    no source data get `fill_value`.
    """
    dst = np.full(dst_shape, fill_value, dtype=dtype)
    with rasterio.open(str(src_path)) as src:
        src_crs = src.crs or WGS84
        reproject(
            source=rasterio.band(src, 1),
            destination=dst,
            src_transform=src.transform,
            src_crs=src_crs,
            src_nodata=src.nodata,
            dst_transform=dst_transform,
            dst_crs=dst_crs,
            dst_nodata=fill_value,
            resampling=resampling,
        )
    return dst


def compute_tpi_on_grid(
    dem_path,
    dst_shape: Tuple[int, int],
    dst_transform: Affine,
    dst_crs: CRS,
    inner_m: float,
    outer_m: float,
) -> np.ndarray:
    """
    Topographic Position Index on the destination grid, in metres.

        TPI = elevation − mean elevation of the ring between an inner
              window (inner_m wide) and an outer window (outer_m wide)

    Positive TPI = higher than the surroundings (ridge / mound).
    Negative TPI = lower than the surroundings (channel / depression).

    The DEM is read only for the scene's area (plus a margin of outer_m so
    the edges have a full neighbourhood) and at a resolution of about
    inner_m / 10, which is plenty for kilometre-scale windows and keeps
    memory use small. The result is then resampled onto the scene grid.
    Pixels outside the DEM are NaN.
    """
    height, width = dst_shape
    with rasterio.open(str(dem_path)) as dem:
        dem_crs = dem.crs or WGS84
        bounds = transform_bounds(dst_crs, dem_crs, *grid_bounds(dst_transform, height, width))

        # Margin in DEM units
        if dem_crs.is_geographic:
            lat = math.radians((bounds[1] + bounds[3]) / 2.0)
            pad_x = outer_m / (M_PER_DEG_LON_EQ * max(math.cos(lat), 0.01))
            pad_y = outer_m / M_PER_DEG_LAT
        else:
            pad_x = pad_y = outer_m
        left = max(bounds[0] - pad_x, dem.bounds.left)
        bottom = max(bounds[1] - pad_y, dem.bounds.bottom)
        right = min(bounds[2] + pad_x, dem.bounds.right)
        top = min(bounds[3] + pad_y, dem.bounds.top)
        if left >= right or bottom >= top:
            return np.full(dst_shape, np.nan, dtype=np.float32)

        window = window_from_bounds(left, bottom, right, top, dem.transform)
        window = window.round_offsets().round_lengths()
        win_transform = dem.window_transform(window)
        native_res_m = pixel_size_m(win_transform, dem_crs, max(int(window.height), 1))

        # Work resolution: no finer than the DEM, no finer than inner_m/10
        work_res_m = max(native_res_m, inner_m / 10.0)
        scale = work_res_m / native_res_m
        out_h = max(int(round(window.height / scale)), 1)
        out_w = max(int(round(window.width / scale)), 1)

        elev = dem.read(
            1, window=window, out_shape=(out_h, out_w),
            resampling=Resampling.average, masked=True,
        ).astype(np.float32).filled(np.nan)
        sx, sy = window.width / out_w, window.height / out_h
        work_transform = Affine(win_transform.a * sx, win_transform.b, win_transform.c,
                                win_transform.d, win_transform.e * sy, win_transform.f)

    elev[elev < -1000] = np.nan  # treat junk/void values as no-data
    work_res_m = pixel_size_m(work_transform, dem_crs, out_h)

    inner_px = max(1, int(round(inner_m / work_res_m)))
    outer_px = max(inner_px + 2, int(round(outer_m / work_res_m)))

    valid = np.isfinite(elev)
    z = np.where(valid, elev, 0.0).astype(np.float64)
    v = valid.astype(np.float64)
    sum_outer = uniform_filter(z, size=outer_px, mode="nearest") * outer_px ** 2
    cnt_outer = uniform_filter(v, size=outer_px, mode="nearest") * outer_px ** 2
    sum_inner = uniform_filter(z, size=inner_px, mode="nearest") * inner_px ** 2
    cnt_inner = uniform_filter(v, size=inner_px, mode="nearest") * inner_px ** 2

    ring_cnt = cnt_outer - cnt_inner
    with np.errstate(invalid="ignore", divide="ignore"):
        ring_mean = np.where(ring_cnt > 0.5, (sum_outer - sum_inner) / ring_cnt, np.nan)
    tpi_work = (elev - ring_mean).astype(np.float32)

    tpi = np.full(dst_shape, np.nan, dtype=np.float32)
    reproject(
        source=tpi_work, destination=tpi,
        src_transform=work_transform, src_crs=dem_crs, src_nodata=np.nan,
        dst_transform=dst_transform, dst_crs=dst_crs, dst_nodata=np.nan,
        resampling=Resampling.bilinear,
    )
    return tpi


def apply_affine(aff: Affine, x, y):
    """Apply an affine transform to coordinates (works with scalars and arrays)."""
    return (aff.a * x + aff.b * y + aff.c, aff.d * x + aff.e * y + aff.f)


def sample_points(
    xs: np.ndarray, ys: np.ndarray, transform: Affine, shape: Tuple[int, int]
) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Convert map coordinates to (row, col) indices on a grid.

    Returns (rows, cols, inside) where `inside` is a boolean array saying
    which points fall within the grid.
    """
    inv = ~transform
    cols_f, rows_f = apply_affine(inv, np.asarray(xs, dtype=np.float64),
                                  np.asarray(ys, dtype=np.float64))
    rows = np.floor(rows_f).astype(np.int64)
    cols = np.floor(cols_f).astype(np.int64)
    inside = (rows >= 0) & (rows < shape[0]) & (cols >= 0) & (cols < shape[1])
    return rows, cols, inside


def any_in_radius(mask: np.ndarray, rows: np.ndarray, cols: np.ndarray, radius_px: int) -> np.ndarray:
    """
    For each (row, col), True if any mask == 1 pixel lies within a square of
    ±radius_px pixels. Looks at a small window per point, so memory use does
    not depend on the scene size.
    """
    h, w = mask.shape
    out = np.zeros(len(rows), dtype=bool)
    for i, (r, c) in enumerate(zip(rows, cols)):
        r0, r1 = max(r - radius_px, 0), min(r + radius_px + 1, h)
        c0, c1 = max(c - radius_px, 0), min(c + radius_px + 1, w)
        if r0 < r1 and c0 < c1:
            out[i] = bool((mask[r0:r1, c0:c1] == 1).any())
    return out
