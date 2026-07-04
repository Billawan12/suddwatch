"""
ml_flood_detection.py — SuddWatch Machine Learning Flood Detector
=================================================================
Random Forest classifier for SAR-based flood detection.

Improves on the threshold-based FloodDetector by:
  - Using multiple spectral and texture features (not just backscatter)
  - Learning from labeled training data rather than fixed thresholds
  - Adapting to seasonal and regional backscatter variations
  - Producing calibrated probability outputs alongside binary masks

Feature set per pixel:
  1.  VH backscatter (dB)           — primary flood indicator
  2.  Local mean (3×3 window)       — smoothed backscatter
  3.  Local mean (7×7 window)       — neighbourhood context
  4.  Local standard deviation      — texture roughness
  5.  Local range (max - min)       — local contrast
  6.  Gradient magnitude            — edge strength
  7.  Sobel X                       — horizontal edge
  8.  Sobel Y                       — vertical edge
  9.  Laplacian                     — second-order edge
  10. Percentile rank (local)       — relative intensity position
  11. Z-score (local)               — standardised backscatter

Usage:
    from src.ml_flood_detection import MLFloodDetector

    detector = MLFloodDetector(config)

    # Train on labeled data (done once, model saved to disk)
    detector.train(training_scenes, training_masks)

    # Predict on new scene
    mask_path, flood_ha, prob_map = detector.predict(preprocessed_tif)

    # Or use the drop-in replacement for FloodDetector.detect()
    mask_path, flood_ha = detector.detect(preprocessed_tif)
"""

import logging
import pickle
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Feature names for logging and debugging
FEATURE_NAMES = [
    "vh_backscatter",
    "local_mean_3x3",
    "local_mean_7x7",
    "local_std_3x3",
    "local_range_5x5",
    "gradient_magnitude",
    "sobel_x",
    "sobel_y",
    "laplacian",
    "percentile_rank",
    "z_score",
]

N_FEATURES = len(FEATURE_NAMES)


class MLFloodDetector:
    """
    Random Forest pixel classifier for SAR flood detection.

    Integrates with the SuddWatch pipeline as a drop-in replacement
    for the threshold-based FloodDetector. Falls back to threshold
    detection automatically when no trained model is available.

    Architecture:
        - sklearn RandomForestClassifier (200 trees, balanced class weights)
        - 11 spectral + texture features per pixel
        - Subsampled training (max 500k pixels) for memory efficiency
        - Model persisted to data/models/random_forest.pkl
        - Probability threshold: 0.45 (tuned for high recall on floods)

    Why Random Forest for SAR flood detection:
        - Handles non-linear backscatter relationships
        - Robust to outliers from speckle noise
        - Built-in feature importance ranking
        - No gradient computation — fast inference on large rasters
        - Balanced class weights handle flood/non-flood imbalance

    Design decisions:
        - Train/predict split is explicit — model must be trained before use
        - If model file missing, falls back to FloodDetector (threshold)
        - Training data is accumulated across scenes for continuous improvement
        - IoU is computed against threshold-based mask if no ground truth
    """

    def __init__(self, config):
        """
        Initialise the ML flood detector.

        Args:
            config: Config instance providing:
                    - project_root: base path for model storage
                    - All other pipeline configuration

        On init:
            - Sets model storage path to data/models/random_forest.pkl
            - Creates model directory if it doesn't exist
            - Loads existing model from disk if available
            - Sets probability threshold to 0.45 (tuned for high recall)
        """
        self.config      = config
        self.model       = None
        self.model_path  = config.project_root / "data" / "models" / "random_forest.pkl"
        self.model_path.parent.mkdir(parents=True, exist_ok=True)

        # Probability threshold — lower = higher recall (catch more floods)
        # 0.45 slightly favours recall over precision for humanitarian context
        self.threshold   = 0.45

        # Training data accumulation
        self._train_X: list = []
        self._train_y: list = []

        # Load model if it exists
        if self.model_path.exists():
            self._load_model()
            logger.info(f"MLFloodDetector ready — model loaded from {self.model_path}")
        else:
            logger.info(
                "MLFloodDetector initialised — no trained model found. "
                "Run train() or detect() will fall back to threshold method."
            )

    # ── Feature extraction ────────────────────────────────────
    def extract_features(self, data: np.ndarray) -> np.ndarray:
        """
        Extract 11 spectral and texture features from a SAR backscatter array.

        Args:
            data: 2D float32 array of VH backscatter values in dB.
                  NaN values are handled gracefully.

        Returns:
            Feature matrix of shape (H*W, N_FEATURES).
            Rows correspond to flattened pixels in row-major order.
        """
        from scipy import ndimage

        H, W = data.shape

        # Replace NaN with scene median for computation
        scene_median = float(np.nanmedian(data))
        scene_std    = float(np.nanstd(data))
        data_filled  = np.where(np.isnan(data), scene_median, data)

        features = []

        # 1. Raw backscatter
        features.append(data_filled.ravel())

        # 2. Local mean 3×3
        mean_3 = ndimage.uniform_filter(data_filled, size=3)
        features.append(mean_3.ravel())

        # 3. Local mean 7×7
        mean_7 = ndimage.uniform_filter(data_filled, size=7)
        features.append(mean_7.ravel())

        # 4. Local standard deviation 3×3
        mean_sq = ndimage.uniform_filter(data_filled ** 2, size=3)
        local_std = np.sqrt(np.clip(mean_sq - mean_3 ** 2, 0, None))
        features.append(local_std.ravel())

        # 5. Local range 5×5 (max - min)
        local_max = ndimage.maximum_filter(data_filled, size=5)
        local_min = ndimage.minimum_filter(data_filled, size=5)
        local_range = local_max - local_min
        features.append(local_range.ravel())

        # 6–8. Gradient (Sobel)
        sobel_x = ndimage.sobel(data_filled, axis=1)
        sobel_y = ndimage.sobel(data_filled, axis=0)
        gradient = np.sqrt(sobel_x ** 2 + sobel_y ** 2)
        features.append(gradient.ravel())
        features.append(sobel_x.ravel())
        features.append(sobel_y.ravel())

        # 9. Laplacian (second-order edges)
        laplacian = ndimage.laplace(data_filled)
        features.append(laplacian.ravel())

        # 10. Percentile rank (local 15×15 window)
        # Approximated as (value - local_min) / local_range
        local_max_15 = ndimage.maximum_filter(data_filled, size=15)
        local_min_15 = ndimage.minimum_filter(data_filled, size=15)
        local_range_15 = local_max_15 - local_min_15 + 1e-6
        pct_rank = (data_filled - local_min_15) / local_range_15
        features.append(pct_rank.ravel())

        # 11. Z-score (global scene normalisation)
        z_score = (data_filled - scene_median) / (scene_std + 1e-6)
        features.append(z_score.ravel())

        X = np.column_stack(features).astype(np.float32)
        logger.debug(f"Features extracted: shape={X.shape}")
        return X

    # ── Model persistence ─────────────────────────────────────
    def _save_model(self):
        """Save trained model to disk."""
        with open(self.model_path, "wb") as f:
            pickle.dump(self.model, f)
        logger.info(f"Model saved to {self.model_path}")

    def _load_model(self):
        """Load trained model from disk."""
        try:
            with open(self.model_path, "rb") as f:
                self.model = pickle.load(f)
            logger.info(f"Model loaded from {self.model_path}")
        except Exception as e:
            logger.warning(f"Failed to load model: {e}")
            self.model = None

    # ── Training ──────────────────────────────────────────────
    def add_training_scene(self, image_path: str, mask_path: str):
        """
        Add one scene to the training buffer.

        Args:
            image_path: preprocessed dB GeoTIFF (input features)
            mask_path:  binary flood mask GeoTIFF (ground truth labels)
                        1 = flood, 0 = non-flood

        The scene is subsampled to max 50,000 pixels to keep
        memory usage bounded across many training scenes.
        """
        import rasterio

        logger.info(f"Adding training scene: {Path(image_path).name}")

        with rasterio.open(image_path) as src:
            data = src.read(1).astype(np.float32)
        with rasterio.open(mask_path) as src:
            mask = src.read(1).astype(np.uint8)

        X = self.extract_features(data)
        y = mask.ravel()

        # Remove NaN rows
        valid = np.isfinite(X).all(axis=1)
        X, y  = X[valid], y[valid]

        # Subsample to max 50k pixels for memory efficiency
        MAX_PIXELS = 50_000
        if len(X) > MAX_PIXELS:
            idx = np.random.choice(len(X), MAX_PIXELS, replace=False)
            X, y = X[idx], y[idx]

        flood_pct = 100 * y.mean()
        logger.info(
            f"  Scene: {len(X)} pixels, "
            f"{flood_pct:.1f}% flood"
        )

        self._train_X.append(X)
        self._train_y.append(y)

    def train(self, image_paths: list = None, mask_paths: list = None,
              n_estimators: int = 200) -> dict:
        """
        Train the Random Forest classifier.

        If image_paths and mask_paths are provided, they are added to
        the training buffer first. Otherwise, uses whatever is already
        in the buffer from previous add_training_scene() calls.

        Args:
            image_paths:   list of preprocessed dB GeoTIFF paths
            mask_paths:    list of corresponding flood mask paths
            n_estimators:  number of trees (default 200)

        Returns:
            dict with training metrics: n_samples, n_features,
            flood_pct, oob_score, feature_importances
        """
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import cross_val_score

        # Add new scenes if provided
        if image_paths and mask_paths:
            for img, msk in zip(image_paths, mask_paths):
                self.add_training_scene(img, msk)

        if not self._train_X:
            raise RuntimeError(
                "No training data available. Call add_training_scene() first "
                "or pass image_paths and mask_paths to train()."
            )

        X = np.vstack(self._train_X)
        y = np.concatenate(self._train_y)

        # Remove any remaining NaN/inf
        valid = np.isfinite(X).all(axis=1)
        X, y  = X[valid], y[valid]

        flood_pct = 100 * y.mean()
        logger.info(
            f"Training Random Forest: {len(X):,} pixels, "
            f"{N_FEATURES} features, {flood_pct:.1f}% flood"
        )

        # Train with balanced class weights — critical for flood detection
        # where non-flood pixels vastly outnumber flood pixels
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=20,
            min_samples_leaf=10,
            n_jobs=-1,                # use all CPU cores
            class_weight="balanced",  # compensate for class imbalance
            oob_score=True,           # out-of-bag accuracy estimate
            random_state=42,
        )
        self.model.fit(X, y)
        self._save_model()

        # Feature importance ranking
        importances = dict(zip(
            FEATURE_NAMES,
            self.model.feature_importances_.tolist()
        ))
        importances_ranked = dict(
            sorted(importances.items(), key=lambda x: x[1], reverse=True)
        )

        metrics = {
            "n_samples":          len(X),
            "n_features":         N_FEATURES,
            "flood_pct":          round(flood_pct, 2),
            "oob_score":          round(self.model.oob_score_, 4),
            "n_trees":            n_estimators,
            "feature_importances": importances_ranked,
            "trained_at":         datetime.now().isoformat(),
        }

        logger.info(
            f"Training complete — OOB accuracy: {self.model.oob_score_:.4f}, "
            f"top feature: {list(importances_ranked.keys())[0]}"
        )

        # Log top 3 features
        for i, (feat, imp) in enumerate(list(importances_ranked.items())[:3]):
            logger.info(f"  #{i+1} {feat}: {imp:.4f}")

        return metrics

    # ── Prediction ────────────────────────────────────────────
    def predict(self, image_path: str) -> tuple:
        """
        Predict flood mask for a new scene.

        Args:
            image_path: preprocessed dB GeoTIFF path

        Returns:
            (mask_path, flood_extent_ha, probability_map)
            - mask_path:       path to saved binary flood mask GeoTIFF
            - flood_extent_ha: detected flood area in hectares
            - probability_map: 2D float32 array of flood probabilities (0–1)

        Raises:
            RuntimeError: if no trained model is available
            FileNotFoundError: if input image does not exist
        """
        import rasterio
        from rasterio.transform import from_bounds

        if self.model is None:
            raise RuntimeError(
                "No trained model available. "
                "Call train() first or ensure model file exists at "
                f"{self.model_path}"
            )

        image_path = str(image_path)
        if not Path(image_path).exists():
            raise FileNotFoundError(f"Input image not found: {image_path}")

        logger.info(f"ML flood detection: {Path(image_path).name}")

        with rasterio.open(image_path) as src:
            data    = src.read(1).astype(np.float32)
            profile = src.profile.copy()
            pixel_area_m2 = abs(src.transform.a * src.transform.e)

        H, W = data.shape
        valid_mask = ~np.isnan(data)

        # Extract features
        X = self.extract_features(data)

        # Predict in chunks to handle large rasters
        CHUNK_SIZE  = 500_000
        n_pixels    = H * W
        probs       = np.zeros(n_pixels, dtype=np.float32)

        for start in range(0, n_pixels, CHUNK_SIZE):
            end          = min(start + CHUNK_SIZE, n_pixels)
            chunk        = X[start:end]
            chunk_probs  = self.model.predict_proba(chunk)[:, 1]
            probs[start:end] = chunk_probs

        prob_map = probs.reshape(H, W)

        # Apply threshold
        flood_mask = (prob_map >= self.threshold).astype(np.uint8)

        # Zero out NaN pixels
        flood_mask[~valid_mask] = 0

        # Calculate flood extent
        flood_pixels   = flood_mask.sum()
        flood_extent_ha = (flood_pixels * pixel_area_m2) / 10_000

        logger.info(
            f"ML prediction: {flood_pixels:,} flood pixels, "
            f"{flood_extent_ha:,.1f} ha, "
            f"mean prob={prob_map[valid_mask].mean():.3f}"
        )

        # Save flood mask GeoTIFF
        mask_path = self._save_mask(image_path, flood_mask, profile)

        # Save probability map alongside mask
        prob_path = str(mask_path).replace("_flood_mask.tif", "_flood_probs.tif")
        prob_profile = profile.copy()
        prob_profile.update(dtype="float32", count=1, compress="lzw")
        with rasterio.open(prob_path, "w", **prob_profile) as dst:
            dst.write(prob_map, 1)
        logger.info(f"Probability map saved: {prob_path}")

        return str(mask_path), round(flood_extent_ha, 2), prob_map

    def _save_mask(self, image_path: str, mask: np.ndarray,
                   profile: dict) -> Path:
        """Save binary flood mask GeoTIFF with matching georeference."""
        import rasterio

        image_path = Path(image_path)
        mask_dir   = image_path.parent / "flood_masks"
        mask_dir.mkdir(parents=True, exist_ok=True)
        mask_path  = mask_dir / image_path.name.replace(
            ".tif", "_flood_mask.tif"
        ).replace(".zip", "_flood_mask.tif")

        out_profile = profile.copy()
        out_profile.update(
            dtype="uint8", count=1, compress="lzw", nodata=255
        )

        import rasterio
        with rasterio.open(str(mask_path), "w", **out_profile) as dst:
            dst.write(mask, 1)

        logger.info(f"Flood mask saved: {mask_path}")
        return mask_path

    # ── Drop-in replacement for FloodDetector.detect() ───────
    def detect(self, image_path: str) -> tuple:
        """
        Drop-in replacement for FloodDetector.detect().

        Uses ML prediction if a trained model is available,
        falls back to threshold-based detection otherwise.

        Args:
            image_path: preprocessed dB GeoTIFF path

        Returns:
            (mask_path, flood_extent_ha) — same as FloodDetector.detect()
        """
        if self.model is not None:
            logger.info("Using ML Random Forest detector")
            mask_path, flood_ha, _ = self.predict(image_path)
            return mask_path, flood_ha
        else:
            logger.warning(
                "No trained model — falling back to threshold-based detection"
            )
            from src.flood_detection import FloodDetector
            fallback = FloodDetector(self.config)
            return fallback.detect(image_path)

    # ── Model evaluation ──────────────────────────────────────
    def evaluate(self, image_path: str, reference_mask_path: str) -> dict:
        """
        Evaluate model performance against a reference (ground truth) mask.

        Computes standard binary classification metrics:
          - IoU (Intersection over Union) — primary SuddWatch metric
          - F1 score — harmonic mean of precision and recall
          - Precision — of predicted floods, how many are real?
          - Recall — of real floods, how many did we catch?
          - Accuracy — overall pixel accuracy

        Args:
            image_path:          preprocessed dB GeoTIFF
            reference_mask_path: ground truth binary mask GeoTIFF

        Returns:
            dict with all metrics
        """
        import rasterio

        mask_path, flood_ha, prob_map = self.predict(image_path)

        with rasterio.open(str(mask_path)) as src:
            predicted = src.read(1).astype(bool)
        with rasterio.open(reference_mask_path) as src:
            reference = src.read(1).astype(bool)

        tp = (predicted & reference).sum()
        fp = (predicted & ~reference).sum()
        fn = (~predicted & reference).sum()
        tn = (~predicted & ~reference).sum()

        iou       = tp / (tp + fp + fn + 1e-6)
        precision = tp / (tp + fp + 1e-6)
        recall    = tp / (tp + fn + 1e-6)
        f1        = 2 * precision * recall / (precision + recall + 1e-6)
        accuracy  = (tp + tn) / (tp + fp + fn + tn + 1e-6)

        metrics = {
            "iou":            round(float(iou),       4),
            "f1":             round(float(f1),        4),
            "precision":      round(float(precision), 4),
            "recall":         round(float(recall),    4),
            "accuracy":       round(float(accuracy),  4),
            "flood_extent_ha": flood_ha,
            "true_positives":  int(tp),
            "false_positives": int(fp),
            "false_negatives": int(fn),
        }

        logger.info(
            f"Evaluation: IoU={iou:.4f}, F1={f1:.4f}, "
            f"Precision={precision:.4f}, Recall={recall:.4f}"
        )
        return metrics

    # ── Synthetic training data generator ────────────────────
    def generate_synthetic_training_data(self,
                                          n_scenes: int = 5,
                                          scene_size: tuple = (200, 200),
                                          seed: int = 42) -> tuple:
        """
        Generate synthetic SAR + mask pairs for testing and demonstration.

        Simulates realistic SAR backscatter statistics:
          - Non-flood land:  mean -10 dB, std 3 dB
          - Flood/water:     mean -22 dB, std 2 dB (lower backscatter)
          - Permanent water: mean -25 dB, std 1 dB

        Args:
            n_scenes:   number of synthetic scenes to generate
            scene_size: (H, W) pixel dimensions per scene
            seed:       random seed for reproducibility

        Returns:
            (X_train, y_train) ready for sklearn fit()
        """
        rng = np.random.default_rng(seed)
        H, W = scene_size
        all_X, all_y = [], []

        for i in range(n_scenes):
            # Create scene with random flood regions
            data = rng.normal(-10.0, 3.0, (H, W)).astype(np.float32)
            mask = np.zeros((H, W), dtype=np.uint8)

            # Add 2-4 flood patches
            n_patches = rng.integers(2, 5)
            for _ in range(n_patches):
                cy  = rng.integers(20, H - 20)
                cx  = rng.integers(20, W - 20)
                rh  = rng.integers(10, 40)
                rw  = rng.integers(10, 60)
                y1, y2 = max(0, cy-rh), min(H, cy+rh)
                x1, x2 = max(0, cx-rw), min(W, cx+rw)
                data[y1:y2, x1:x2] = rng.normal(-22.0, 2.0, (y2-y1, x2-x1))
                mask[y1:y2, x1:x2] = 1

            X = self.extract_features(data)
            y = mask.ravel()
            all_X.append(X)
            all_y.append(y)

        X_all = np.vstack(all_X)
        y_all = np.concatenate(all_y)

        flood_pct = 100 * y_all.mean()
        logger.info(
            f"Generated {n_scenes} synthetic scenes: "
            f"{len(X_all):,} pixels, {flood_pct:.1f}% flood"
        )
        return X_all, y_all

    # ── Feature importance report ─────────────────────────────
    def feature_importance_report(self) -> str:
        """Return a formatted feature importance report."""
        if self.model is None:
            return "No trained model available."

        importances = self.model.feature_importances_
        ranked      = sorted(
            zip(FEATURE_NAMES, importances),
            key=lambda x: x[1], reverse=True
        )
        lines = ["Feature Importance Report", "=" * 40]
        for i, (name, imp) in enumerate(ranked, 1):
            bar = "█" * int(imp * 50)
            lines.append(f"  #{i:2d}  {name:25s}  {imp:.4f}  {bar}")
        return "\n".join(lines)


# ── Module self-test ──────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.config import Config, setup_logging

    setup_logging("INFO")
    cfg     = Config()
    detector = MLFloodDetector(cfg)

    print("\nSuddWatch ML Flood Detector — Self Test")
    print("=" * 50)
    print(f"Model path:  {detector.model_path}")
    print(f"Model loaded: {detector.model is not None}")
    print(f"Features:    {N_FEATURES}")
    print(f"Threshold:   {detector.threshold}")

    print("\nGenerating synthetic training data...")
    X_train, y_train = detector.generate_synthetic_training_data(
        n_scenes=10, scene_size=(150, 150)
    )
    print(f"Training samples: {len(X_train):,}")

    print("\nTraining Random Forest...")
    detector._train_X = [X_train]
    detector._train_y = [y_train]
    metrics = detector.train()

    print(f"\nTraining results:")
    print(f"  OOB accuracy:    {metrics['oob_score']:.4f}")
    print(f"  Flood %:         {metrics['flood_pct']:.1f}%")
    print(f"  Samples:         {metrics['n_samples']:,}")
    print(f"\n{detector.feature_importance_report()}")
    print("\nML Flood Detector self-test complete ✓")
