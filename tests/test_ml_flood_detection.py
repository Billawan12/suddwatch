# ============================================================
# SuddWatch - Unit Tests: experimental Random Forest detector
# ============================================================

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds

from src.ml_flood_detection import MLFloodDetector, N_FEATURES


@pytest.fixture
def scene(tmp_path):
    rng = np.random.default_rng(5)
    data = rng.normal(-9.0, 2.0, (1100, 120)).astype(np.float32)  # > one 512-row tile
    data[600:, :] = rng.normal(-22.0, 1.5, (500, 120))
    path = tmp_path / "ml_scene_db.tif"
    with rasterio.open(str(path), "w", driver="GTiff", height=1100, width=120, count=1,
                       dtype="float32", crs="EPSG:4326",
                       transform=from_bounds(31.0, 7.0, 31.012, 7.11, 120, 1100),
                       nodata=np.nan) as d:
        d.write(data, 1)
    return path


def _trained(test_config):
    det = MLFloodDetector(test_config)
    X, y = det.generate_synthetic_training_data(n_scenes=3, scene_size=(80, 80))
    from sklearn.ensemble import RandomForestClassifier
    det.model = RandomForestClassifier(n_estimators=10, random_state=0).fit(X, y)
    return det


def test_model_path_comes_from_config(test_config):
    assert MLFloodDetector(test_config).model_path == test_config.ml_model_path


def test_feature_count(test_config):
    X = MLFloodDetector(test_config).extract_features(np.zeros((5, 6), np.float32))
    assert X.shape == (30, N_FEATURES)


def test_tiled_prediction_detects_water(test_config, scene):
    det = _trained(test_config)
    mask_path, ha, prob = det.predict(str(scene))
    with rasterio.open(mask_path) as src:
        mask = src.read(1)
    assert (mask[650:1050] == 1).mean() > 0.9
    assert (mask[50:550] == 1).mean() < 0.05
    # ~500 rows × 120 cols of ~11 m pixels ≈ 5.5 km × 1.3 km ≈ 730 ha
    assert 600 < ha < 850
    assert str(test_config.masks_dir) in mask_path


def test_detect_falls_back_without_model(test_config, scene):
    det = MLFloodDetector(test_config)
    det.model = None
    mask_path, ha = det.detect(str(scene))
    assert ha > 0
