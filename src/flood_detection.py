# ============================================================
# SuddWatch - Flood Detection Module
# File: src/flood_detection.py
# Purpose: Detects flood extent from preprocessed Sentinel-1
#          SAR GeoTIFFs using a multi-stage detection pipeline:
#
#   Stage 1 — Otsu thresholding: automatic threshold from
#             image histogram separating water from land
#   Stage 2 — Loose threshold via GMM: Gaussian Mixture Model
#             finds the water cluster mean + std for a lower
#             threshold that catches partial/shallow flooding
#   Stage 3 — Change detection: compares current scene to a
#             dry-season baseline to isolate new flooding
#   Stage 4 — TPI filtering: removes pixels on ridges/hills
#             using Topographic Position Index from local DEM
#   Stage 5 — Exclusion masking: removes permanent water
#             bodies and urban areas from flood mask
#   Stage 6 — Morphological cleaning: removes noise and
#             fills holes using OpenCV closing + opening
#
# Output: binary uint8 GeoTIFF flood mask (1=flood, 0=no flood)
#         + flood extent in hectares
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
from scipy.ndimage import uniform_filter
from skimage.filters import threshold_otsu
from sklearn.mixture import GaussianMixture

from src.config import Config

# --- Module logger ---
logger = logging.getLogger(__name__)


class FloodDetector:
    """
    Detects flood extent from preprocessed Sentinel-1 SAR GeoTIFFs.

    Implements the multi-stage detection pipeline described in the
    proposal (Chapter 4, Section 4.3.2):
    1. Otsu thresholding
    2. Loose threshold via Gaussian Mixture Model
    3. Change detection against dry-season baseline
    4. TPI (Topographic Position Index) filtering
    5. Exclusion mask application
    6. Morphological cleaning

    The final threshold is min(otsu, loose) ensuring we capture
    both clear and marginal flooding. This approach reduces false
    negatives (missed floods) at the cost of slightly more false
    positives, which are then removed by TPI and exclusion masking.

    Example usage:
        from src.config import Config
        from src.flood_detection import FloodDetector
        config = Config()
        detector = FloodDetector(config)
        detector.set_baseline('data/processed/dry_season_scene_db.tif')
        mask_path, extent_ha = detector.detect('data/processed/current_scene_db.tif')
    """

    def __init__(self, config: Config):
        """
        Initialises the flood detector with config settings.

        Args:
            config: Config object with detection thresholds and file paths
        """
        self.config = config

        # Dry-season baseline image path — set via set_baseline()
        # Used for change detection in Stage 3
        self.baseline_path: Optional[str] = None

        logger.info(
            f"FloodDetector initialised. "
            f"TPI windows: inner={config.tpi_inner_window}, "
            f"outer={config.tpi_outer_window}. "
            f"Change detection threshold: {config.change_detection_threshold} dB."
        )

    def set_baseline(self, baseline_path: str) -> None:
        """
        Sets the dry-season baseline image for change detection.

        The baseline should be a preprocessed dB GeoTIFF from the
        dry season (typically Dec-Feb for South Sudan) when the
        Sudd wetland is at its minimum extent.

        Args:
            baseline_path: path to dry-season preprocessed dB GeoTIFF
        """
        if not Path(baseline_path).exists():
            logger.warning(
                f"Baseline file not found: {baseline_path}. "
                f"Change detection will be skipped."
            )
            return

        self.baseline_path = baseline_path
        logger.info(f"Baseline set: {baseline_path}")

    # ============================================================
    # STAGE 1: OTSU THRESHOLDING
    # Automatic threshold from image histogram
    # ============================================================

    def _compute_otsu(self, data: np.ndarray) -> float:
        """
        Computes the Otsu threshold for a SAR dB image.

        Otsu's method finds the threshold that minimises intra-class
        variance between water (low backscatter) and land (high
        backscatter). Works best when the histogram is bimodal.

        Args:
            data: 2D numpy array of valid (non-NaN) dB pixel values

        Returns:
            float: Otsu threshold in dB. Pixels below this are water.
        """
        # Flatten to 1D and remove NaN values for thresholding
        valid_pixels = data[~np.isnan(data)].flatten()

        if len(valid_pixels) == 0:
            logger.warning("No valid pixels for Otsu thresholding.")
            return -15.0  # Fallback threshold for VH backscatter

        # skimage threshold_otsu expects values in a reasonable range
        # SAR dB values are typically -25 to 0 for South Sudan
        otsu_threshold = threshold_otsu(valid_pixels)

        logger.debug(f"Otsu threshold: {otsu_threshold:.2f} dB")
        return float(otsu_threshold)

    # ============================================================
    # STAGE 2: LOOSE THRESHOLD VIA GAUSSIAN MIXTURE MODEL
    # Finds water cluster to capture shallow/partial flooding
    # ============================================================

    def _compute_loose_threshold(self, data: np.ndarray) -> float:
        """
        Computes a loose (lower) threshold using Gaussian Mixture Model.

        Fits a 2-component GMM to the dB histogram assuming two classes:
        water (lower mean) and land (higher mean). The loose threshold
        is the water component mean + 1 standard deviation.

        This captures pixels with intermediate backscatter values that
        Otsu would classify as land but are actually shallow flooding
        or mixed water-vegetation pixels (common in the Sudd wetland).

        Args:
            data: 2D numpy array of dB pixel values (may contain NaN)

        Returns:
            float: loose threshold in dB (water_mean + water_std)
        """
        # Extract valid pixels and reshape for sklearn GMM (needs 2D)
        valid_pixels = data[~np.isnan(data)].flatten().reshape(-1, 1)

        if len(valid_pixels) < 100:
            logger.warning(
                "Too few valid pixels for GMM. Using fallback threshold."
            )
            return -14.0  # Fallback loose threshold

        try:
            # Fit 2-component GMM — one component per class (water/land)
            gmm = GaussianMixture(
                n_components=2,
                covariance_type='full',
                max_iter=100,
                random_state=42,  # Fixed seed for reproducibility
            )
            gmm.fit(valid_pixels)

            # Extract component means and standard deviations
            means = gmm.means_.flatten()
            stds = np.sqrt(gmm.covariances_.flatten())

            # Water component has the LOWER mean (lower backscatter)
            water_idx = np.argmin(means)
            water_mean = means[water_idx]
            water_std = stds[water_idx]

            # Loose threshold = water mean + 1 std
            # Captures pixels within 1 std above water centre
            loose_threshold = float(water_mean + water_std)

            logger.debug(
                f"GMM: water_mean={water_mean:.2f} dB, "
                f"water_std={water_std:.2f} dB, "
                f"loose_threshold={loose_threshold:.2f} dB"
            )
            return loose_threshold

        except Exception as e:
            logger.warning(f"GMM fitting failed: {e}. Using fallback threshold.")
            return -14.0

    # ============================================================
    # STAGE 3: CHANGE DETECTION
    # Isolates new flooding by comparing to dry-season baseline
    # ============================================================

    def _change_detection(
        self,
        current_path: str,
    ) -> Optional[np.ndarray]:
        """
        Detects change between current scene and dry-season baseline.

        Computes pixel-wise difference (current - baseline) in dB.
        Significant negative differences indicate flooding — lower
        backscatter in current scene compared to baseline means water
        appeared where there was previously dry land.

        A difference more negative than -change_detection_threshold
        (default -2.0 dB) flags a pixel as newly flooded.

        Args:
            current_path: path to current preprocessed dB GeoTIFF

        Returns:
            np.ndarray: boolean change mask (True = newly flooded),
                        or None if baseline not set or loading fails
        """
        if not self.baseline_path:
            # No baseline set — skip change detection
            return None

        try:
            # Load current scene
            with rasterio.open(current_path) as src:
                current_data = src.read(1).astype(np.float32)
                current_profile = src.profile

            # Load baseline scene
            with rasterio.open(self.baseline_path) as src:
                baseline_data = src.read(
                    1,
                    out_shape=current_data.shape,
                    resampling=Resampling.bilinear,
                ).astype(np.float32)

            # Compute difference: current - baseline
            # Negative values = backscatter decreased = potential flooding
            difference = current_data - baseline_data

            # Flag pixels where difference is significantly negative
            # (backscatter dropped more than threshold dB)
            change_mask = difference < -self.config.change_detection_threshold

            valid_changes = np.sum(change_mask)
            logger.info(
                f"Change detection: {valid_changes} pixels showed "
                f">{self.config.change_detection_threshold} dB decrease "
                f"vs baseline."
            )
            return change_mask

        except Exception as e:
            logger.warning(f"Change detection failed: {e}. Skipping.")
            return None

    # ============================================================
    # STAGE 4: TPI FILTERING
    # Removes ridge/hill pixels using Topographic Position Index
    # ============================================================

    def _apply_tpi_filter(
        self,
        mask: np.ndarray,
        image_path: str,
    ) -> np.ndarray:
        """
        Removes topographically elevated pixels from the flood mask.

        TPI (Topographic Position Index) measures how elevated a pixel
        is relative to its surroundings. High TPI = ridge or hilltop —
        these cannot be flooded and must be excluded.

        TPI = DEM_pixel - mean(DEM in annular neighbourhood)
        Annular neighbourhood = outer_window mean - inner_window mean

        Pixels where TPI > tpi_threshold are removed from flood mask.

        Args:
            mask: binary flood mask (True = flood)
            image_path: path to current scene (used to get spatial extent
                        for resampling the DEM to match the scene)

        Returns:
            np.ndarray: flood mask with elevated pixels removed
        """
        # Check local DEM exists before attempting TPI
        if not self.config.local_dem_path.exists():
            logger.warning(
                "Local DEM not found. Skipping TPI filtering. "
                "TPI requires data/dem/south_sudan_dem.tif"
            )
            return mask

        try:
            # Load the DEM and resample to match the flood mask dimensions
            with rasterio.open(image_path) as scene_src:
                scene_shape = scene_src.shape
                scene_transform = scene_src.transform
                scene_crs = scene_src.crs

            with rasterio.open(str(self.config.local_dem_path)) as dem_src:
                # Resample DEM to match scene resolution and extent
                dem_data = dem_src.read(
                    1,
                    out_shape=scene_shape,
                    resampling=Resampling.bilinear,
                ).astype(np.float32)

            # Replace DEM nodata values with NaN
            dem_data[dem_data < -1000] = np.nan

            # --- Compute TPI using scipy uniform_filter ---
            # Inner window mean captures local elevation context
            inner_mean = uniform_filter(
                np.nan_to_num(dem_data, nan=0.0),
                size=self.config.tpi_inner_window,
            )

            # Outer window mean captures regional elevation context
            outer_mean = uniform_filter(
                np.nan_to_num(dem_data, nan=0.0),
                size=self.config.tpi_outer_window,
            )

            # TPI = pixel elevation - mean of annular neighbourhood
            # Positive TPI = above surroundings (ridge/hill)
            # Negative TPI = below surroundings (valley/depression)
            tpi = dem_data - (outer_mean - inner_mean)

            # Remove pixels with TPI above threshold (topographic highs)
            # These are ridges/hills that cannot flood
            elevated_pixels = tpi > self.config.tpi_threshold
            mask_filtered = mask & ~elevated_pixels

            removed = np.sum(mask) - np.sum(mask_filtered)
            logger.info(
                f"TPI filtering removed {removed} elevated pixels "
                f"(TPI > {self.config.tpi_threshold})."
            )
            return mask_filtered

        except Exception as e:
            logger.warning(f"TPI filtering failed: {e}. Skipping.")
            return mask

    # ============================================================
    # STAGE 5: EXCLUSION MASKING
    # Removes permanent water bodies and urban areas
    # ============================================================

    def _apply_exclusion_mask(
        self,
        mask: np.ndarray,
        image_path: str,
    ) -> np.ndarray:
        """
        Removes permanent water bodies and urban areas from flood mask.

        Exclusion masks prevent false positives from:
        - Permanent water bodies (Nile, permanent Sudd channels)
        - Urban areas (double-bounce scattering mimics water)
        - Dense vegetation (low backscatter but not water)

        Exclusion masks are pre-generated GeoTIFFs stored in
        data/exclusion_masks/. If none exist, this step is skipped.

        Args:
            mask: binary flood mask after TPI filtering
            image_path: path to current scene (for spatial reference)

        Returns:
            np.ndarray: flood mask with permanent features removed
        """
        exclusion_dir = self.config.exclusion_masks_dir

        # Find all exclusion mask files in the directory
        exclusion_files = list(exclusion_dir.glob("*.tif"))

        if not exclusion_files:
            logger.info(
                "No exclusion masks found in data/exclusion_masks/. "
                "Skipping exclusion masking."
            )
            return mask

        try:
            # Start with no exclusions
            combined_exclusion = np.zeros(mask.shape, dtype=bool)

            for excl_file in exclusion_files:
                with rasterio.open(str(excl_file)) as excl_src:
                    # Resample exclusion mask to match flood mask shape
                    excl_data = excl_src.read(
                        1,
                        out_shape=mask.shape,
                        resampling=Resampling.nearest,
                    )
                    # OR-combine all exclusion masks
                    # Any pixel excluded by ANY mask is removed
                    combined_exclusion |= excl_data.astype(bool)

            # Remove excluded pixels from flood mask
            mask_filtered = mask & ~combined_exclusion

            removed = np.sum(mask) - np.sum(mask_filtered)
            logger.info(
                f"Exclusion masking: removed {removed} pixels "
                f"using {len(exclusion_files)} exclusion mask(s)."
            )
            return mask_filtered

        except Exception as e:
            logger.warning(f"Exclusion masking failed: {e}. Skipping.")
            return mask

    # ============================================================
    # STAGE 6: MORPHOLOGICAL CLEANING
    # Removes noise and fills holes using OpenCV
    # ============================================================

    def _morphological_clean(self, mask: np.ndarray) -> np.ndarray:
        """
        Cleans the flood mask using morphological operations.

        Two operations applied in sequence:
        1. CLOSING (dilation then erosion): fills small holes within
           flooded areas — connects nearby flood pixels
        2. OPENING (erosion then dilation): removes small isolated
           noise pixels — cleans up speckle artifacts

        Uses an elliptical 3x3 kernel as specified in the proposal.

        Args:
            mask: binary flood mask as boolean or uint8 array

        Returns:
            np.ndarray: cleaned binary mask as uint8 (0 or 255)
        """
        # Convert boolean mask to uint8 for OpenCV (requires 0/255)
        mask_uint8 = mask.astype(np.uint8) * 255

        # Elliptical kernel — better than square for natural features
        kernel = cv2.getStructuringElement(
            cv2.MORPH_ELLIPSE,
            (3, 3),  # 3x3 kernel as per proposal specification
        )

        # Step 1: Closing — fills holes within flooded regions
        # Dilation expands flood pixels, erosion shrinks back
        # Net effect: small gaps within flood areas are filled
        mask_closed = cv2.morphologyEx(
            mask_uint8,
            cv2.MORPH_CLOSE,
            kernel,
        )

        # Step 2: Opening — removes isolated noise pixels
        # Erosion removes small objects, dilation restores larger ones
        # Net effect: isolated single pixels or small clusters removed
        mask_opened = cv2.morphologyEx(
            mask_closed,
            cv2.MORPH_OPEN,
            kernel,
        )

        # Convert back to binary (0 or 1) from OpenCV's 0/255 scale
        mask_clean = (mask_opened > 0).astype(np.uint8)

        removed = np.sum(mask.astype(np.uint8)) - np.sum(mask_clean)
        logger.debug(
            f"Morphological cleaning: net change = {removed} pixels "
            f"(positive = removed noise, negative = filled holes)."
        )
        return mask_clean

    # ============================================================
    # MASK SAVE
    # Writes binary flood mask as compressed GeoTIFF
    # ============================================================

    def _save_mask(
        self,
        mask: np.ndarray,
        profile: dict,
        input_path: str,
    ) -> str:
        """
        Saves the binary flood mask as a uint8 GeoTIFF with LZW compression.

        Output filename is derived from input scene name with
        '_flood_mask' suffix. Saved to data/flood_masks/.

        Args:
            mask: binary flood mask as uint8 array (0 or 1)
            profile: rasterio profile from the input scene
            input_path: path to input scene (used for output filename)

        Returns:
            str: path to saved flood mask GeoTIFF
        """
        scene_name = Path(input_path).stem
        output_path = str(
            self.config.masks_dir / f"{scene_name}_flood_mask.tif"
        )

        # Update profile for binary uint8 output
        profile.update(
            dtype=rasterio.uint8,     # Binary mask needs only uint8
            count=1,                   # Single band
            compress='lzw',            # Compression reduces file size
            nodata=255,                # 255 = no-data sentinel value
            tiled=True,                # Required for compression
            blockxsize=256,
            blockysize=256,
        )

        with rasterio.open(output_path, 'w', **profile) as dst:
            dst.write(mask, 1)

        logger.info(f"Flood mask saved: {output_path}")
        return output_path

    # ============================================================
    # FLOOD EXTENT CALCULATION
    # Converts pixel count to hectares
    # ============================================================

    def _calculate_flood_extent(
        self,
        mask: np.ndarray,
        profile: dict,
    ) -> float:
        """
        Calculates the flood extent in hectares from the binary mask.

        Uses the pixel resolution from the rasterio profile to convert
        pixel count to area. Assumes the scene is in a geographic CRS
        (degrees) and approximates area using the pixel size in degrees
        converted to metres at the scene's latitude.

        For South Sudan (lat ~7°N), 1 degree ≈ 111km, so:
        pixel_area_m2 = (pixel_size_deg * 111000)^2
        flood_extent_ha = flood_pixels * pixel_area_m2 / 10000

        Args:
            mask: binary flood mask (1 = flood, 0 = no flood)
            profile: rasterio profile containing transform info

        Returns:
            float: flood extent in hectares
        """
        # Count flooded pixels
        flood_pixel_count = int(np.sum(mask == 1))

        # Get pixel size from transform
        transform = profile.get('transform')
        if transform:
            # Pixel size in degrees (geographic CRS)
            pixel_size_deg = abs(transform.a)

            # Convert degrees to metres at ~7°N (South Sudan centroid)
            # 1 degree latitude ≈ 111,000 metres
            pixel_size_m = pixel_size_deg * 111_000

            # Area per pixel in square metres
            pixel_area_m2 = pixel_size_m ** 2

            # Convert to hectares (1 ha = 10,000 m²)
            flood_extent_ha = (flood_pixel_count * pixel_area_m2) / 10_000

        else:
            # Fallback: assume 10m resolution (SNAP terrain correction default)
            flood_extent_ha = (flood_pixel_count * 100) / 10_000

        logger.info(
            f"Flood extent: {flood_pixel_count} pixels = "
            f"{flood_extent_ha:.1f} hectares"
        )
        return round(flood_extent_ha, 2)

    # ============================================================
    # MAIN DETECTION METHOD
    # Full 6-stage pipeline from dB GeoTIFF to flood mask
    # ============================================================

    def detect(self, image_path: str) -> Tuple[str, float]:
        """
        Runs the full 6-stage flood detection pipeline.

        Takes a preprocessed dB GeoTIFF and produces a binary
        flood mask GeoTIFF plus the flood extent in hectares.

        Pipeline:
        1. Load preprocessed dB image
        2. Compute Otsu threshold
        3. Compute loose GMM threshold
        4. Select final threshold = min(otsu, loose)
        5. Create initial flood mask: pixels < final_threshold
        6. Apply change detection (if baseline set)
        7. Apply TPI filter (remove topographic highs)
        8. Apply exclusion masks (permanent water/urban)
        9. Morphological cleaning (remove noise, fill holes)
        10. Save mask and calculate extent

        Args:
            image_path: path to preprocessed dB GeoTIFF

        Returns:
            Tuple[str, float]: (mask_path, flood_extent_ha)
                mask_path: path to saved flood mask GeoTIFF
                flood_extent_ha: detected flood area in hectares

        Raises:
            FileNotFoundError: if input image does not exist
            ValueError: if image has no valid pixels
        """
        image_path = str(image_path)

        # Validate input exists
        if not Path(image_path).exists():
            raise FileNotFoundError(f"Input image not found: {image_path}")

        logger.info(f"Starting flood detection: {Path(image_path).name}")

        # --- Load preprocessed dB image ---
        with rasterio.open(image_path) as src:
            data = src.read(1).astype(np.float32)
            profile = src.profile.copy()

        # Validate data has valid pixels
        valid_count = np.sum(~np.isnan(data))
        if valid_count == 0:
            raise ValueError(f"No valid pixels in image: {image_path}")

        logger.info(f"Image loaded: shape={data.shape}, valid pixels={valid_count}")

        # --- Stage 1: Otsu threshold ---
        logger.info("Stage 1/6: Computing Otsu threshold...")
        otsu_threshold = self._compute_otsu(data)

        # --- Stage 2: Loose GMM threshold ---
        logger.info("Stage 2/6: Computing GMM loose threshold...")
        loose_threshold = self._compute_loose_threshold(data)

        # Final threshold = minimum of Otsu and loose
        # Lower threshold = more inclusive = catches marginal flooding
        # Apply relaxation factor from config (default 1.0 = no change)
        final_threshold = (
            min(otsu_threshold, loose_threshold)
            * self.config.otsu_relaxation_factor
        )

        logger.info(
            f"Thresholds — Otsu: {otsu_threshold:.2f} dB, "
            f"GMM loose: {loose_threshold:.2f} dB, "
            f"Final: {final_threshold:.2f} dB"
        )

        # --- Create initial flood mask ---
        # Pixels below threshold = low backscatter = water/flood
        flood_mask = data < final_threshold

        initial_pixels = np.sum(flood_mask)
        logger.info(f"Initial flood mask: {initial_pixels} pixels")

        # --- Stage 3: Change detection ---
        logger.info("Stage 3/6: Applying change detection...")
        change_mask = self._change_detection(image_path)

        if change_mask is not None:
            # Combine: pixel must be in initial mask AND show change
            # This removes permanent water bodies from the flood mask
            flood_mask = flood_mask & change_mask
            after_change = np.sum(flood_mask)
            logger.info(
                f"After change detection: {after_change} pixels "
                f"(removed {initial_pixels - after_change} permanent water pixels)"
            )

        # --- Stage 4: TPI filtering ---
        logger.info("Stage 4/6: Applying TPI filter...")
        flood_mask = self._apply_tpi_filter(flood_mask, image_path)

        # --- Stage 5: Exclusion masking ---
        logger.info("Stage 5/6: Applying exclusion masks...")
        flood_mask = self._apply_exclusion_mask(flood_mask, image_path)

        # --- Stage 6: Morphological cleaning ---
        logger.info("Stage 6/6: Applying morphological cleaning...")
        flood_mask_clean = self._morphological_clean(flood_mask)

        final_pixels = np.sum(flood_mask_clean)
        logger.info(f"Final flood mask: {final_pixels} pixels")

        # --- Save mask ---
        mask_path = self._save_mask(flood_mask_clean, profile, image_path)

        # --- Calculate flood extent ---
        flood_extent_ha = self._calculate_flood_extent(flood_mask_clean, profile)

        logger.info(
            f"Flood detection complete: {flood_extent_ha:.1f} ha detected. "
            f"Mask saved to: {mask_path}"
        )

        return mask_path, flood_extent_ha


# ============================================================
# Quick self-test — run this file directly to verify
# Creates a synthetic SAR scene and runs full detection
# Usage: python3 -m src.flood_detection
# ============================================================
if __name__ == "__main__":
    import tempfile
    from src.config import Config, setup_logging

    setup_logging()
    config = Config()
    detector = FloodDetector(config)

    print("\n" + "=" * 55)
    print("SuddWatch Flood Detection Verification")
    print("=" * 55)

    # --- Create synthetic dB scene for testing ---
    print("\nCreating synthetic SAR scene...")
    with tempfile.TemporaryDirectory() as tmpdir:
        test_scene = os.path.join(tmpdir, "test_scene_preprocessed_db.tif")

        # Create realistic dB values:
        # Bottom half: water-like pixels (-22 to -18 dB)
        # Top half: land-like pixels (-10 to -6 dB)
        rows, cols = 100, 100
        data = np.full((rows, cols), -8.0, dtype=np.float32)
        data[60:, :] = -20.0  # Lower portion = flooded area

        # Add some NaN pixels (no-data border)
        data[:5, :] = np.nan
        data[-5:, :] = np.nan

        transform = from_bounds(29.0, 7.0, 30.0, 8.0, cols, rows)
        with rasterio.open(
            test_scene, 'w',
            driver='GTiff', height=rows, width=cols,
            count=1, dtype='float32',
            crs=rasterio.CRS.from_epsg(4326),
            transform=transform,
            nodata=np.nan,
        ) as dst:
            dst.write(data, 1)

        print(f"   ✓ Synthetic scene created: {rows}x{cols} pixels")
        print(f"   ✓ Flood area: lower 40 rows ({40*cols} pixels)")

        # --- Run flood detection ---
        print("\nRunning flood detection pipeline...")
        try:
            mask_path, extent_ha = detector.detect(test_scene)
            print(f"   ✓ Detection complete")
            print(f"   ✓ Mask saved: {Path(mask_path).name}")
            print(f"   ✓ Flood extent: {extent_ha:.1f} hectares")

            # Verify mask
            with rasterio.open(mask_path) as src:
                mask_data = src.read(1)
                flood_pixels = np.sum(mask_data == 1)
                print(f"   ✓ Flood pixels in mask: {flood_pixels}")
                print(f"   ✓ Mask dtype: {src.dtypes[0]}")
                print(f"   ✓ Mask CRS: {src.crs}")

        except Exception as e:
            print(f"   ✗ Detection failed: {e}")
            raise

    print("\n" + "=" * 55)
    print("Flood detection module verified successfully.")
    print("=" * 55 + "\n")
