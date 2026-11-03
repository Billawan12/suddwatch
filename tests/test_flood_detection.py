# ============================================================
# SuddWatch - Unit Tests: Flood Detection + raster helpers
# File: tests/test_flood_detection.py
# Uses synthetic rasters only — no real data or SNAP needed.
# ============================================================

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from src import raster_utils as ru
from src.flood_detection import FloodDetector, MASK_NODATA


def _write(path, data, bounds, dtype="float32", nodata=None):
    h, w = data.shape
    with rasterio.open(
        str(path), "w", driver="GTiff", height=h, width=w, count=1, dtype=dtype,
        crs="EPSG:4326", transform=from_bounds(*bounds, w, h), nodata=nodata,
    ) as dst:
        dst.write(data.astype(dtype), 1)
    return path


# Scene: ~2.2 km × 2.2 km at ~11 m pixels near Bor (31.5°E, 6.2°N)
SCENE_BOUNDS = (31.50, 6.20, 31.52, 6.22)


@pytest.fixture
def scene(tmp_path):
    """Bottom 40% of the scene is water (-21 dB), the rest land (-8 dB)."""
    rng = np.random.default_rng(1)
    data = rng.normal(-8.0, 1.0, (200, 200))
    data[120:, :] = rng.normal(-21.0, 1.0, (80, 200))
    data[:3, :] = np.nan  # no-data border
    return _write(tmp_path / "scene_preprocessed_db.tif", data, SCENE_BOUNDS, nodata=np.nan)


@pytest.fixture
def detector(test_config):
    return FloodDetector(test_config)


class TestThresholds:
    def test_otsu_between_classes(self, detector):
        rng = np.random.default_rng(0)
        data = np.concatenate([rng.normal(-21, 1, 5000), rng.normal(-8, 1, 5000)])
        t = detector._compute_otsu(data)
        assert -19 < t < -10

    def test_gmm_threshold_near_water_class(self, detector):
        rng = np.random.default_rng(0)
        data = np.concatenate([rng.normal(-21, 1, 5000), rng.normal(-8, 1, 5000)])
        t = detector._compute_loose_threshold(data)
        assert -21 < t < -18  # water mean + ~1 std

    def test_fallbacks_on_empty_input(self, detector):
        empty = np.full((10, 10), np.nan)
        assert detector._compute_otsu(empty) == -15.0
        assert detector._compute_loose_threshold(empty) == -14.0


class TestDetect:
    def test_detects_water_without_dem(self, detector, scene):
        mask_path, ha = detector.detect(scene)
        with rasterio.open(mask_path) as src:
            mask = src.read(1)
        flood_rows = (mask[125:195] == 1).mean()
        land_rows = (mask[10:110] == 1).mean()
        assert flood_rows > 0.9
        assert land_rows < 0.01
        assert ha > 0

    def test_nodata_pixels_marked_nodata(self, detector, scene):
        mask_path, _ = detector.detect(scene)
        with rasterio.open(mask_path) as src:
            mask = src.read(1)
            assert src.nodata == MASK_NODATA
        assert (mask[:3] == MASK_NODATA).all()

    def test_extent_matches_geometry(self, detector, scene):
        """80 of 200 rows flooded over a ~2.2 × 2.2 km box ≈ 40% of ~490 ha."""
        _, ha = detector.detect(scene)
        assert 170 < ha < 220

    def test_missing_input_raises(self, detector):
        with pytest.raises(FileNotFoundError):
            detector.detect("/nonexistent/scene.tif")

    def test_all_nan_raises(self, detector, tmp_path):
        p = _write(tmp_path / "nan.tif", np.full((20, 20), np.nan), SCENE_BOUNDS, nodata=np.nan)
        with pytest.raises(ValueError):
            detector.detect(p)

    def test_run_stats_recorded(self, detector, scene):
        detector.detect(scene)
        s = detector.last_run_stats
        assert s["pixels_final"] > 0
        assert s["final_threshold_db"] < -10


class TestTPIFilter:
    """Regression tests for the bug where TPI removed every flood pixel."""

    def test_flat_floodplain_keeps_flood(self, detector, scene, test_config):
        # Flat terrain at 420 m — the old formula gave TPI ≈ 420 and
        # removed 100% of flood pixels.
        rng = np.random.default_rng(2)
        dem = 420 + rng.normal(0, 0.05, (300, 300))
        _write(test_config.local_dem_path, dem, (31.45, 6.15, 31.57, 6.27))
        _, ha = detector.detect(scene)
        assert ha > 150
        assert detector.last_run_stats["pixels_after_tpi"] > 0.9 * detector.last_run_stats["pixels_initial"]

    def test_mound_is_removed(self, detector, test_config, tmp_path):
        """A 10 m high mound inside the flooded area should be filtered out."""
        rng = np.random.default_rng(3)
        data = rng.normal(-21.0, 0.5, (200, 200))  # everything looks wet
        data[:40, :] = rng.normal(-8.0, 0.5, (40, 200))  # some land for Otsu
        scene = _write(tmp_path / "wet_db.tif", data, SCENE_BOUNDS, nodata=np.nan)

        # DEM covering exactly the scene: flat 420 m with a 10 m mound in the middle
        dem = np.full((200, 200), 420.0)
        yy, xx = np.mgrid[0:200, 0:200]
        dem[(yy - 120) ** 2 + (xx - 100) ** 2 < 15 ** 2] = 430.0
        _write(test_config.local_dem_path, dem, SCENE_BOUNDS)

        # Small windows so the test scene is several windows wide
        test_config.tpi_inner_window = 2   # 20 m
        test_config.tpi_outer_window = 30  # 300 m
        mask_path, _ = detector.detect(scene)
        with rasterio.open(mask_path) as src:
            mask = src.read(1)
        assert mask[120, 100] == 0       # mound centre removed
        assert mask[180, 20] == 1        # flat flooded area kept

    def test_tpi_values_flat_terrain_near_zero(self, tmp_path):
        dem = np.full((100, 100), 420.0)
        p = _write(tmp_path / "dem.tif", dem, SCENE_BOUNDS)
        tpi = ru.compute_tpi_on_grid(p, (50, 50), from_bounds(*SCENE_BOUNDS, 50, 50),
                                     ru.WGS84, inner_m=50, outer_m=500)
        assert np.nanmax(np.abs(tpi)) < 0.01


class TestAlignment:
    """Overlays must be matched by location, not stretched."""

    def test_align_to_grid_uses_overlap_only(self, tmp_path):
        # Source covers a much larger area; only its top-left quarter = 1
        src = np.zeros((100, 100))
        src[:50, :50] = 1
        p = _write(tmp_path / "big.tif", src, (30.0, 6.0, 32.0, 8.0))
        # Destination is a small box entirely inside the top-left quarter
        out = ru.align_to_grid(p, (10, 10), from_bounds(30.2, 7.5, 30.4, 7.7, 10, 10),
                               ru.WGS84, resampling=rasterio.enums.Resampling.nearest)
        assert np.all(out == 1)

    def test_exclusion_mask_aligned(self, detector, scene, test_config):
        # Exclusion raster covering a large area; flag only the scene's lower half
        excl = np.zeros((400, 400), dtype="uint8")
        # big raster bounds 31.4–31.6, 6.1–6.3 → scene rows 120-200 lie at lat 6.20–6.208
        big_bounds = (31.4, 6.1, 31.6, 6.3)
        # rows for lat 6.200–6.208 in big raster: (6.3-6.208)/0.0005=184 → (6.3-6.2)/0.0005=200
        excl[184:200, :] = 1
        _write(test_config.exclusion_masks_dir / "permanent_water.tif", excl, big_bounds,
               dtype="uint8")
        _, ha = detector.detect(scene)
        assert ha < 20  # nearly all of the flooded strip is excluded


class TestArea:
    def test_area_shrinks_with_latitude(self):
        t_eq = from_bounds(30.0, 0.0, 30.01, 0.01, 1, 1)
        t_60 = from_bounds(30.0, 60.0, 30.01, 60.01, 1, 1)
        m = np.ones((1, 1), dtype=np.uint8)
        assert ru.mask_area_ha(m, t_60, ru.WGS84) < 0.55 * ru.mask_area_ha(m, t_eq, ru.WGS84)

    def test_area_one_km_square(self):
        # 0.009° × 0.009° near 7°N ≈ 0.993 km × 0.995 km ≈ 99 ha
        t = from_bounds(31.0, 7.0, 31.009, 7.009, 1, 1)
        ha = ru.mask_area_ha(np.ones((1, 1), dtype=np.uint8), t, ru.WGS84)
        assert 95 < ha < 102
