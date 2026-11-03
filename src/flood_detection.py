# ============================================================
# SuddWatch - Flood Detection Module
# File: src/flood_detection.py
# Purpose: Detects flood extent from a preprocessed Sentinel-1
#          VH backscatter GeoTIFF (in dB).
#
# Open water reflects the radar pulse away from the satellite, so
# it appears DARK (low dB). The detector finds a dB threshold that
# separates water from land, then removes false positives:
#
#   Stage 1 — Otsu threshold from the image histogram
#   Stage 2 — GMM threshold: mean + 1 std of the "water" component
#             of a 2-component Gaussian Mixture Model
#             → final threshold = the LOWER (stricter) of the two,
#               × otsu_relaxation_factor
#   Stage 3 — Change detection vs a dry-season baseline (optional):
#             keep only pixels whose backscatter dropped > N dB,
#             which removes permanent water
#   Stage 4 — TPI filter: remove pixels on local high ground
#             (TPI > tpi_threshold metres) using the local DEM
#   Stage 5 — Exclusion masks: remove permanent water / urban areas
#   Stage 6 — Morphological close + open to fill holes / remove speckle
#
# Every auxiliary raster (baseline, DEM, exclusion masks) is
# reprojected onto the scene's pixel grid before use, so pixels line
# up geographically.
#
# Output: uint8 GeoTIFF (1 = flood, 0 = not flood, 255 = no data)
#         + flood extent in hectares.
#
# Course: SWE3090 - Software Project 1
# Student: Madut Chan (671336)
# ============================================================

import logging
import os
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import from_bounds
from skimage.filters import threshold_otsu
from sklearn.mixture import GaussianMixture

from src.config import Config
from src import raster_utils as ru

logger = logging.getLogger(__name__)

# Thresholds are estimated from a random sample of pixels: the histogram of
# a million pixels is indistinguishable from that of the full scene, and
# fitting a GMM to ~400 million pixels would take far too long.
THRESHOLD_SAMPLE_SIZE = 1_000_000

# Scene pixel size the TPI window settings are expressed in (metres)
TPI_WINDOW_PIXEL_M = 10.0

MASK_NODATA = 255


class FloodDetector:
    """
    Detects flood extent from preprocessed Sentinel-1 SAR GeoTIFFs.

    Example:
        detector = FloodDetector(Config())
        mask_path, extent_ha = detector.detect('data/processed/scene_preprocessed_db.tif')
    """

    def __init__(self, config: Config):
        self.config = config
        self.baseline_path: Optional[str] = None
        self.last_run_stats: dict = {}

        # Use the configured dry-season baseline automatically if it exists
        baseline = getattr(config, "baseline_path", None)
        if baseline and Path(baseline).exists():
            self.set_baseline(str(baseline))

        logger.info(
            f"FloodDetector initialised. "
            f"TPI windows: inner={config.tpi_inner_window}, "
            f"outer={config.tpi_outer_window} (×{TPI_WINDOW_PIXEL_M:.0f} m). "
            f"Change detection threshold: {config.change_detection_threshold} dB. "
            f"Baseline: {'set' if self.baseline_path else 'not set'}."
        )

    def set_baseline(self, baseline_path: str) -> None:
        """
        Set the dry-season baseline (a preprocessed dB GeoTIFF from
        Dec–Feb, when the Sudd is at its smallest) for change detection.
        """
        if not Path(baseline_path).exists():
            logger.warning(
                f"Baseline file not found: {baseline_path}. "
                f"Change detection will be skipped."
            )
            return
        self.baseline_path = str(baseline_path)
        logger.info(f"Baseline set: {baseline_path}")

    # ------------------------------------------------------------
    # Threshold estimation
    # ------------------------------------------------------------

    @staticmethod
    def _sample_valid(data: np.ndarray, n: int = THRESHOLD_SAMPLE_SIZE) -> np.ndarray:
        """Up to n finite pixel values, sampled reproducibly."""
        valid = data[np.isfinite(data)]
        if valid.size > n:
            rng = np.random.default_rng(42)
            valid = rng.choice(valid, size=n, replace=False)
        return valid.astype(np.float64)

    def _compute_otsu(self, data: np.ndarray) -> float:
        """
        Stage 1 — Otsu threshold (dB). Chooses the value that best splits
        the histogram into two classes (water = low dB, land = high dB).
        """
        valid = self._sample_valid(data)
        if valid.size == 0:
            logger.warning("No valid pixels for Otsu thresholding.")
            return -15.0
        if np.all(valid == valid[0]):
            return float(valid[0])
        t = float(threshold_otsu(valid))
        logger.debug(f"Otsu threshold: {t:.2f} dB")
        return t

    def _compute_loose_threshold(self, data: np.ndarray) -> float:
        """
        Stage 2 — GMM threshold (dB) = mean + 1 std of the lower ("water")
        component of a 2-component Gaussian Mixture Model.
        """
        valid = self._sample_valid(data).reshape(-1, 1)
        if len(valid) < 100:
            logger.warning("Too few valid pixels for GMM. Using fallback threshold.")
            return -14.0
        try:
            gmm = GaussianMixture(n_components=2, covariance_type="full",
                                  max_iter=100, random_state=42)
            gmm.fit(valid)
            means = gmm.means_.flatten()
            stds = np.sqrt(gmm.covariances_.flatten())
            w = int(np.argmin(means))
            t = float(means[w] + stds[w])
            logger.debug(f"GMM: water_mean={means[w]:.2f}, water_std={stds[w]:.2f}, threshold={t:.2f}")
            return t
        except Exception as e:
            logger.warning(f"GMM fitting failed: {e}. Using fallback threshold.")
            return -14.0

    # ------------------------------------------------------------
    # Stage 3 — change detection
    # ------------------------------------------------------------

    def _change_detection(self, current_data: np.ndarray, profile: dict) -> Optional[np.ndarray]:
        """
        Pixels whose backscatter fell by more than change_detection_threshold
        dB compared with the dry-season baseline (True = newly wet).
        Returns None if no baseline is set or it cannot be read.
        Where the baseline has no data the pixel is kept (True), so a
        partial baseline never deletes detections outside its footprint.
        """
        if not self.baseline_path:
            return None
        try:
            baseline = ru.align_to_grid(
                self.baseline_path, current_data.shape, profile["transform"],
                ru.grid_crs(profile), resampling=Resampling.bilinear,
            )
            diff = current_data - baseline
            change = diff < -self.config.change_detection_threshold
            change |= ~np.isfinite(baseline)
            logger.info(
                f"Change detection: {int(np.sum(change & np.isfinite(baseline)))} pixels "
                f"dropped > {self.config.change_detection_threshold} dB vs baseline."
            )
            return change
        except Exception as e:
            logger.warning(f"Change detection failed: {e}. Skipping.")
            return None

    # ------------------------------------------------------------
    # Stage 4 — TPI filter
    # ------------------------------------------------------------

    def _apply_tpi_filter(self, mask: np.ndarray, profile: dict) -> np.ndarray:
        """
        Remove flood pixels on local high ground (TPI > tpi_threshold m).
        Pixels where the DEM has no data are left unchanged.
        """
        dem_path = self.config.local_dem_path
        if not Path(dem_path).exists():
            logger.warning(
                f"Local DEM not found at {dem_path}. Skipping TPI filtering."
            )
            return mask
        try:
            tpi = ru.compute_tpi_on_grid(
                dem_path, mask.shape, profile["transform"], ru.grid_crs(profile),
                inner_m=self.config.tpi_inner_window * TPI_WINDOW_PIXEL_M,
                outer_m=self.config.tpi_outer_window * TPI_WINDOW_PIXEL_M,
            )
            elevated = np.isfinite(tpi) & (tpi > self.config.tpi_threshold)
            filtered = mask & ~elevated
            removed = int(np.sum(mask) - np.sum(filtered))
            logger.info(
                f"TPI filtering removed {removed} of {int(np.sum(mask))} flood pixels "
                f"(TPI > {self.config.tpi_threshold} m)."
            )
            return filtered
        except Exception as e:
            logger.warning(f"TPI filtering failed: {e}. Skipping.")
            return mask

    # ------------------------------------------------------------
    # Stage 5 — exclusion masks
    # ------------------------------------------------------------

    def _apply_exclusion_mask(self, mask: np.ndarray, profile: dict) -> np.ndarray:
        """
        Remove pixels flagged (value ≥ 1) in any GeoTIFF in
        data/exclusion_masks/ — e.g. permanent water (JRC GSW) or urban areas.
        """
        files = sorted(Path(self.config.exclusion_masks_dir).glob("*.tif"))
        if not files:
            logger.info("No exclusion masks found in data/exclusion_masks/. Skipping.")
            return mask
        try:
            combined = np.zeros(mask.shape, dtype=bool)
            for f in files:
                excl = ru.align_to_grid(
                    f, mask.shape, profile["transform"], ru.grid_crs(profile),
                    resampling=Resampling.nearest, fill_value=0, dtype=np.float32,
                )
                combined |= excl >= 1
            filtered = mask & ~combined
            logger.info(
                f"Exclusion masking removed {int(np.sum(mask) - np.sum(filtered))} pixels "
                f"using {len(files)} mask(s)."
            )
            return filtered
        except Exception as e:
            logger.warning(f"Exclusion masking failed: {e}. Skipping.")
            return mask

    # ------------------------------------------------------------
    # Stage 6 — morphological cleaning
    # ------------------------------------------------------------

    def _morphological_clean(self, mask: np.ndarray) -> np.ndarray:
        """
        Closing (fills small holes) then opening (removes isolated
        specks) with a 3×3 elliptical kernel. Returns uint8 0/1.
        """
        m = mask.astype(np.uint8) * 255
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel)
        return (m > 0).astype(np.uint8)

    # ------------------------------------------------------------
    # Output
    # ------------------------------------------------------------

    def _save_mask(self, mask: np.ndarray, profile: dict, input_path: str) -> str:
        """Write the mask as an LZW-compressed uint8 GeoTIFF in data/flood_masks/."""
        out = str(Path(self.config.masks_dir) / f"{Path(input_path).stem}_flood_mask.tif")
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        p = profile.copy()
        p.update(driver="GTiff", dtype=rasterio.uint8, count=1, compress="lzw",
                 nodata=MASK_NODATA, tiled=True, blockxsize=256, blockysize=256)
        if mask.shape[0] < 256 or mask.shape[1] < 256:
            p.update(tiled=False)
            p.pop("blockxsize", None)
            p.pop("blockysize", None)
        with rasterio.open(out, "w", **p) as dst:
            dst.write(mask, 1)
        logger.info(f"Flood mask saved: {out}")
        return out

    def _calculate_flood_extent(self, mask: np.ndarray, profile: dict) -> float:
        """Flood extent in hectares, using the true area of each pixel row."""
        transform = profile.get("transform")
        if transform is None:
            # Fallback: assume 10 m pixels (SNAP terrain-correction default)
            return round(float(np.sum(mask == 1)) * 100 / 10_000, 2)
        ha = ru.mask_area_ha(mask, transform, ru.grid_crs(profile))
        logger.info(f"Flood extent: {int(np.sum(mask == 1))} pixels = {ha:.1f} hectares")
        return round(ha, 2)

    # ------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------

    def detect(self, image_path: str) -> Tuple[str, float]:
        """
        Run all six stages on a preprocessed dB GeoTIFF.

        Returns:
            (mask_path, flood_extent_ha)
        Raises:
            FileNotFoundError: input missing
            ValueError: input has no valid pixels
        """
        image_path = str(image_path)
        if not Path(image_path).exists():
            raise FileNotFoundError(f"Input image not found: {image_path}")

        logger.info(f"Starting flood detection: {Path(image_path).name}")
        with rasterio.open(image_path) as src:
            data = src.read(1).astype(np.float32)
            profile = src.profile.copy()
            if src.nodata is not None and np.isfinite(src.nodata):
                data[data == src.nodata] = np.nan

        valid = np.isfinite(data)
        valid_count = int(valid.sum())
        if valid_count == 0:
            raise ValueError(f"No valid pixels in image: {image_path}")
        logger.info(f"Image loaded: shape={data.shape}, valid pixels={valid_count}")

        logger.info("Stage 1/6: Otsu threshold...")
        otsu_t = self._compute_otsu(data)
        logger.info("Stage 2/6: GMM threshold...")
        gmm_t = self._compute_loose_threshold(data)

        # The lower of the two thresholds is the stricter one (fewer pixels
        # fall below it). otsu_relaxation_factor < 1 moves a negative dB
        # threshold upwards, i.e. makes detection MORE inclusive.
        final_t = min(otsu_t, gmm_t) * self.config.otsu_relaxation_factor
        logger.info(f"Thresholds — Otsu: {otsu_t:.2f} dB, GMM: {gmm_t:.2f} dB, Final: {final_t:.2f} dB")

        flood = valid & (data < final_t)
        n_initial = int(flood.sum())
        logger.info(f"Initial flood mask: {n_initial} pixels")

        logger.info("Stage 3/6: Change detection...")
        change = self._change_detection(data, profile)
        if change is not None:
            flood &= change
        n_change = int(flood.sum())

        logger.info("Stage 4/6: TPI filter...")
        flood = self._apply_tpi_filter(flood, profile)
        n_tpi = int(flood.sum())

        logger.info("Stage 5/6: Exclusion masks...")
        flood = self._apply_exclusion_mask(flood, profile)
        n_excl = int(flood.sum())

        logger.info("Stage 6/6: Morphological cleaning...")
        clean = self._morphological_clean(flood)
        clean[~valid] = MASK_NODATA
        n_final = int((clean == 1).sum())
        logger.info(f"Final flood mask: {n_final} pixels")

        mask_path = self._save_mask(clean, profile, image_path)
        extent_ha = self._calculate_flood_extent(clean, profile)

        self.last_run_stats = {
            "otsu_threshold_db": round(otsu_t, 3),
            "gmm_threshold_db": round(gmm_t, 3),
            "final_threshold_db": round(final_t, 3),
            "pixels_initial": n_initial,
            "pixels_after_change_detection": n_change,
            "pixels_after_tpi": n_tpi,
            "pixels_after_exclusion": n_excl,
            "pixels_final": n_final,
            "change_detection_applied": change is not None,
        }
        logger.info(f"Flood detection complete: {extent_ha:.1f} ha. Mask: {mask_path}")
        return mask_path, extent_ha


# Self-test on a synthetic scene: python3 -m src.flood_detection
if __name__ == "__main__":
    import tempfile
    from src.config import setup_logging

    setup_logging()
    detector = FloodDetector(Config())
    with tempfile.TemporaryDirectory() as tmpdir:
        test_scene = os.path.join(tmpdir, "synthetic_scene_db.tif")
        rows, cols = 200, 200
        rng = np.random.default_rng(0)
        data = rng.normal(-8.0, 1.0, (rows, cols)).astype(np.float32)
        data[120:, :] = rng.normal(-21.0, 1.0, (80, cols))
        transform = from_bounds(31.0, 7.0, 31.02, 7.02, cols, rows)
        with rasterio.open(test_scene, "w", driver="GTiff", height=rows, width=cols,
                           count=1, dtype="float32", crs="EPSG:4326",
                           transform=transform, nodata=np.nan) as dst:
            dst.write(data, 1)
        detector.config.masks_dir = Path(tmpdir)
        mask_path, extent_ha = detector.detect(test_scene)
        print(f"Mask: {mask_path}\nExtent: {extent_ha:.1f} ha\nStats: {detector.last_run_stats}")
