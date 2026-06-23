# ============================================================
# SuddWatch - Unit Tests: Preprocessing Module
# File: tests/test_preprocessing.py
# Purpose: Tests for SARPreprocessor class covering
#          GPT graph generation, dB conversion, output
#          validation, and error handling — without
#          running actual SNAP processing.
# Course: SWE3090 - Software Project 1
# Student: Madut Chan (671336)
# ============================================================

import os
import pytest
import tempfile
import subprocess
import numpy as np
from pathlib import Path
from unittest.mock import MagicMock, patch

import rasterio
from rasterio.crs import CRS
from rasterio.transform import from_bounds

from src.config import Config
from src.preprocessing import SARPreprocessor


# ============================================================
# FIXTURES
# Shared test setup reused across multiple tests
# ============================================================

@pytest.fixture
def config():
    """
    Provides a real Config object for tests.
    """
    return Config()


@pytest.fixture
def preprocessor(config):
    """
    Provides a SARPreprocessor instance for tests.
    """
    return SARPreprocessor(config)


@pytest.fixture
def synthetic_sigma0_tif(tmp_path):
    """
    Creates a synthetic linear sigma0 GeoTIFF for dB conversion tests.
    Simulates a real preprocessed SAR scene over South Sudan.
    Uses pytest tmp_path fixture — safer than tempfile.TemporaryDirectory
    with yield, as tmp_path persists for the full duration of the test.
    """
    tif_path = str(tmp_path / "test_sigma0.tif")

    # Create realistic sigma0 values for South Sudan
    # Typical VH backscatter: 0.001 (water) to 0.3 (vegetation)
    data = np.array([
        [0.001, 0.005, 0.01, 0.02],   # Row 1: water/flood pixels
        [0.05,  0.10,  0.15, 0.20],   # Row 2: vegetation pixels
        [0.0,   0.001, 0.25, 0.30],   # Row 3: mixed (0.0 = nodata)
        [0.08,  0.12,  0.18, 0.22],   # Row 4: land pixels
    ], dtype=np.float32)

    # Write as a valid GeoTIFF covering part of South Sudan
    transform = from_bounds(29.0, 7.0, 30.0, 8.0, 4, 4)
    with rasterio.open(
        tif_path, 'w',
        driver='GTiff',
        height=4, width=4,
        count=1,
        dtype='float32',
        crs=CRS.from_epsg(4326),
        transform=transform,
    ) as dst:
        dst.write(data, 1)

    return tif_path  # tmp_path handles cleanup automatically


@pytest.fixture
def synthetic_db_tif(tmp_path):
    """
    Creates a synthetic dB GeoTIFF for validation tests.
    Simulates the final output of the preprocessing pipeline.
    Uses pytest tmp_path fixture for safe, automatic cleanup.
    """
    tif_path = str(tmp_path / "test_db.tif")

    # Realistic dB values for Sentinel-1 VH over South Sudan
    # Water: -20 to -15 dB, Vegetation: -12 to -6 dB
    data = np.array([
        [-20.0, -18.5, -16.0, -14.0],
        [-12.0, -10.5,  -9.0,  -8.0],
        [np.nan, -19.0,  -7.0,  -6.0],
        [-11.0,  -9.5,  -8.5,  -7.5],
    ], dtype=np.float32)

    transform = from_bounds(29.0, 7.0, 30.0, 8.0, 4, 4)
    with rasterio.open(
        tif_path, 'w',
        driver='GTiff',
        height=4, width=4,
        count=1,
        dtype='float32',
        crs=CRS.from_epsg(4326),
        transform=transform,
        nodata=np.nan,
    ) as dst:
        dst.write(data, 1)

    return tif_path  # tmp_path handles cleanup automatically


# ============================================================
# INITIALISATION TESTS
# Tests for SARPreprocessor.__init__
# ============================================================

class TestInitialisation:
    """Tests for preprocessor setup and validation."""

    def test_initialises_with_valid_config(self, config):
        """
        SARPreprocessor should initialise successfully when GPT exists.
        """
        preprocessor = SARPreprocessor(config)
        assert preprocessor is not None
        assert preprocessor.gpt_path == config.snap_gpt_path

    def test_raises_when_gpt_not_found(self, config):
        """
        Should raise FileNotFoundError if GPT path doesn't exist.
        Prevents silent failures when SNAP is not installed.
        """
        # Point to a non-existent GPT path
        config.snap_gpt_path = "/nonexistent/path/to/gpt"

        with pytest.raises(FileNotFoundError, match="SNAP GPT not found"):
            SARPreprocessor(config)

    def test_gpt_path_matches_config(self, preprocessor, config):
        """
        GPT path stored in preprocessor should match config value.
        """
        assert preprocessor.gpt_path == config.snap_gpt_path


# ============================================================
# XML GRAPH GENERATION TESTS
# Tests for _build_preprocessing_graph method
# ============================================================

class TestGraphGeneration:
    """Tests for SNAP GPT XML graph construction."""

    def test_graph_contains_all_six_operators(self, preprocessor):
        """
        Generated graph must contain all 6 required SNAP operators.
        Missing any operator breaks the preprocessing chain.
        """
        xml = preprocessor._build_preprocessing_graph(
            input_path="/data/raw/test.zip",
            output_path="/data/processed/test.tif",
        )

        required_operators = [
            "Read",
            "Apply-Orbit-File",
            "Calibration",
            "Speckle-Filter",
            "Terrain-Correction",
            "Write",
        ]

        for operator in required_operators:
            assert operator in xml, f"Operator '{operator}' missing from graph"

    def test_graph_contains_input_path(self, preprocessor):
        """
        Graph must reference the correct input scene path.
        """
        input_path = "/data/raw/S1A_test_scene.zip"
        xml = preprocessor._build_preprocessing_graph(
            input_path=input_path,
            output_path="/data/processed/output.tif",
        )

        assert input_path in xml

    def test_graph_contains_output_path(self, preprocessor):
        """
        Graph must reference the correct output file path.
        """
        output_path = "/data/processed/S1A_test_output.tif"
        xml = preprocessor._build_preprocessing_graph(
            input_path="/data/raw/test.zip",
            output_path=output_path,
        )

        assert output_path in xml

    def test_graph_uses_vh_polarisation(self, preprocessor):
        """
        Calibration operator must specify VH polarisation.
        VH is required for flood detection — VV gives poor water contrast.
        """
        xml = preprocessor._build_preprocessing_graph(
            input_path="/data/raw/test.zip",
            output_path="/data/processed/test.tif",
        )

        assert "VH" in xml

    def test_graph_uses_lee_speckle_filter(self, preprocessor):
        """
        Speckle filter must use Lee filter as specified in config.
        """
        xml = preprocessor._build_preprocessing_graph(
            input_path="/data/raw/test.zip",
            output_path="/data/processed/test.tif",
        )

        assert "Lee" in xml

    def test_graph_speckle_window_matches_config(self, preprocessor, config):
        """
        Speckle filter window size in graph must match config value (5).
        """
        xml = preprocessor._build_preprocessing_graph(
            input_path="/data/raw/test.zip",
            output_path="/data/processed/test.tif",
        )

        # Config has snap_speckle_size = 5
        assert str(config.snap_speckle_size) in xml

    def test_graph_nodatavalue_at_sea_is_false(self, preprocessor):
        """
        nodataValueAtSea must be false for South Sudan inland processing.
        True would incorrectly mask Sudd floodplain pixels as sea.
        """
        xml = preprocessor._build_preprocessing_graph(
            input_path="/data/raw/test.zip",
            output_path="/data/processed/test.tif",
        )

        assert "<nodataValueAtSea>false</nodataValueAtSea>" in xml

    def test_graph_projection_is_wgs84(self, preprocessor):
        """
        Terrain correction must output in WGS84 (EPSG:4326).
        All other data layers (WorldPop, DEM, OSM) are in WGS84.
        """
        xml = preprocessor._build_preprocessing_graph(
            input_path="/data/raw/test.zip",
            output_path="/data/processed/test.tif",
        )

        assert "WGS84" in xml

    def test_graph_is_valid_xml(self, preprocessor):
        """
        Generated graph must be parseable as valid XML.
        """
        import xml.etree.ElementTree as ET

        xml_str = preprocessor._build_preprocessing_graph(
            input_path="/data/raw/test.zip",
            output_path="/data/processed/test.tif",
        )

        # Should not raise any exception
        root = ET.fromstring(xml_str)
        assert root.tag == "graph"


# ============================================================
# GRAPH SAVE TESTS
# Tests for _save_graph method
# ============================================================

class TestGraphSave:
    """Tests for saving XML graphs to disk."""

    def test_save_graph_creates_file(self, preprocessor):
        """
        _save_graph should create an XML file at the expected path.
        """
        xml_content = "<graph><test/></graph>"
        graph_path = preprocessor._save_graph(xml_content, "test_save_graph")

        assert Path(graph_path).exists()
        assert graph_path.endswith(".xml")

        # Clean up
        Path(graph_path).unlink(missing_ok=True)

    def test_save_graph_content_matches(self, preprocessor):
        """
        Saved graph file content should exactly match input XML string.
        """
        xml_content = "<graph><node id='test'><operator>Read</operator></node></graph>"
        graph_path = preprocessor._save_graph(xml_content, "test_content_graph")

        with open(graph_path, "r") as f:
            saved_content = f.read()

        assert saved_content == xml_content

        # Clean up
        Path(graph_path).unlink(missing_ok=True)

    def test_save_graph_in_config_directory(self, preprocessor, config):
        """
        Graph should be saved in the project's config/ directory.
        """
        xml_content = "<graph/>"
        graph_path = preprocessor._save_graph(xml_content, "test_dir_graph")

        expected_dir = str(config.project_root / "config")
        assert expected_dir in graph_path

        # Clean up
        Path(graph_path).unlink(missing_ok=True)


# ============================================================
# dB CONVERSION TESTS
# Tests for _convert_to_db method
# ============================================================

class TestDbConversion:
    """Tests for linear sigma0 to decibel conversion."""

    def test_db_conversion_produces_output_file(self, preprocessor, synthetic_sigma0_tif):
        """
        _convert_to_db should create the output GeoTIFF file.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output_db.tif")
            preprocessor._convert_to_db(synthetic_sigma0_tif, output_path)
            assert Path(output_path).exists()

    def test_db_values_are_negative(self, preprocessor, synthetic_sigma0_tif):
        """
        dB values for Sentinel-1 VH should be negative.
        Typical range: -25 to -5 dB for South Sudan land cover.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output_db.tif")
            preprocessor._convert_to_db(synthetic_sigma0_tif, output_path)

            with rasterio.open(output_path) as src:
                data = src.read(1)
                valid = data[~np.isnan(data)]

            # All valid dB values should be negative for typical SAR backscatter
            assert np.all(valid < 0), "dB values should be negative for SAR backscatter"

    def test_zero_pixels_become_nan(self, preprocessor, synthetic_sigma0_tif):
        """
        Zero-value pixels in sigma0 (no-data) must become NaN in dB output.
        Zero cannot be log-converted and represents invalid data.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output_db.tif")
            preprocessor._convert_to_db(synthetic_sigma0_tif, output_path)

            with rasterio.open(output_path) as src:
                data = src.read(1)

            # The synthetic data has a 0.0 at position [2,0]
            # This should become NaN after dB conversion
            assert np.isnan(data[2, 0]), "Zero pixel should be NaN in dB output"

    def test_db_formula_is_correct(self, preprocessor):
        """
        dB conversion must use: dB = 10 * log10(sigma0).
        Verifies the mathematical formula is correctly applied.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create simple test data with known values
            input_path = os.path.join(tmpdir, "known_sigma0.tif")
            output_path = os.path.join(tmpdir, "known_db.tif")

            # sigma0 = 0.1 → dB should be 10 * log10(0.1) = -10.0
            # sigma0 = 1.0 → dB should be 10 * log10(1.0) = 0.0
            test_data = np.array([[0.1, 1.0]], dtype=np.float32)
            transform = from_bounds(29, 7, 30, 8, 2, 1)

            with rasterio.open(
                input_path, 'w',
                driver='GTiff', height=1, width=2,
                count=1, dtype='float32',
                crs=CRS.from_epsg(4326),
                transform=transform,
            ) as dst:
                dst.write(test_data, 1)

            preprocessor._convert_to_db(input_path, output_path)

            with rasterio.open(output_path) as src:
                result = src.read(1)

            # Check formula accuracy within floating point tolerance
            assert abs(result[0, 0] - (-10.0)) < 0.001, "10*log10(0.1) should be -10.0"
            assert abs(result[0, 1] - 0.0) < 0.001, "10*log10(1.0) should be 0.0"

    def test_output_is_float32(self, preprocessor, synthetic_sigma0_tif):
        """
        Output GeoTIFF must be float32 dtype.
        float32 is sufficient precision for dB values and saves disk space.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output_db.tif")
            preprocessor._convert_to_db(synthetic_sigma0_tif, output_path)

            with rasterio.open(output_path) as src:
                assert src.dtypes[0] == 'float32'

    def test_output_has_lzw_compression(self, preprocessor, synthetic_sigma0_tif):
        """
        Output GeoTIFF must use LZW compression to reduce file size.
        Uncompressed SAR scenes can be 2-3GB — compression is essential.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output_db.tif")
            preprocessor._convert_to_db(synthetic_sigma0_tif, output_path)

            with rasterio.open(output_path) as src:
                compression = src.profile.get('compress', '').lower()
                assert compression == 'lzw', f"Expected LZW compression, got {compression}"

    def test_output_crs_matches_input(self, preprocessor, synthetic_sigma0_tif):
        """
        Output GeoTIFF CRS must match input CRS (WGS84).
        CRS must be preserved through dB conversion.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "output_db.tif")
            preprocessor._convert_to_db(synthetic_sigma0_tif, output_path)

            with rasterio.open(synthetic_sigma0_tif) as src_in:
                input_crs = src_in.crs

            with rasterio.open(output_path) as src_out:
                output_crs = src_out.crs

            assert input_crs == output_crs


# ============================================================
# OUTPUT VALIDATION TESTS
# Tests for validate_output method
# ============================================================

class TestOutputValidation:
    """Tests for the preprocessed output validation method."""

    def test_validate_output_returns_true_for_valid_file(self, preprocessor, synthetic_db_tif):
        """
        validate_output should return True for a correctly formed dB GeoTIFF.
        """
        result = preprocessor.validate_output(synthetic_db_tif)
        assert result is True

    def test_validate_output_returns_false_for_missing_file(self, preprocessor):
        """
        validate_output should return False (not crash) for non-existent file.
        """
        result = preprocessor.validate_output("/nonexistent/path/output.tif")
        assert result is False

    def test_validate_output_returns_false_for_no_crs(self, preprocessor):
        """
        validate_output should return False if output has no CRS.
        A missing CRS means terrain correction failed or wasn't run.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tif_path = os.path.join(tmpdir, "no_crs.tif")

            # Create GeoTIFF without CRS
            data = np.array([[-10.0, -12.0], [-15.0, -18.0]], dtype=np.float32)
            with rasterio.open(
                tif_path, 'w',
                driver='GTiff', height=2, width=2,
                count=1, dtype='float32',
                # No CRS specified
            ) as dst:
                dst.write(data, 1)

            result = preprocessor.validate_output(tif_path)
            assert result is False

    def test_validate_output_returns_false_for_all_nan(self, preprocessor):
        """
        validate_output should return False if all pixels are NaN.
        An all-NaN output means processing failed silently.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            tif_path = os.path.join(tmpdir, "all_nan.tif")

            # Create GeoTIFF with all NaN values
            data = np.full((4, 4), np.nan, dtype=np.float32)
            transform = from_bounds(29, 7, 30, 8, 4, 4)
            with rasterio.open(
                tif_path, 'w',
                driver='GTiff', height=4, width=4,
                count=1, dtype='float32',
                crs=CRS.from_epsg(4326),
                transform=transform,
                nodata=np.nan,
            ) as dst:
                dst.write(data, 1)

            result = preprocessor.validate_output(tif_path)
            assert result is False


# ============================================================
# GPT EXECUTION TESTS
# Tests for _run_gpt method (mocked — no actual SNAP calls)
# ============================================================

class TestGptExecution:
    """Tests for SNAP GPT subprocess execution."""

    def test_run_gpt_returns_true_on_success(self, preprocessor):
        """
        _run_gpt should return True when GPT exits with code 0.
        """
        # Mock subprocess.run to simulate successful GPT execution
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("src.preprocessing.subprocess.run", return_value=mock_result):
            result = preprocessor._run_gpt("/config/test_graph.xml")

        assert result is True

    def test_run_gpt_returns_false_on_failure(self, preprocessor):
        """
        _run_gpt should return False when GPT exits with non-zero code.
        """
        # Mock subprocess.run to simulate GPT failure
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "Error: operator failed"

        with patch("src.preprocessing.subprocess.run", return_value=mock_result):
            result = preprocessor._run_gpt("/config/test_graph.xml")

        assert result is False

    def test_run_gpt_returns_false_on_timeout(self, preprocessor):
        """
        _run_gpt should return False when GPT times out.
        Long-running processes should not hang the pipeline indefinitely.
        """
        with patch("src.preprocessing.subprocess.run", side_effect=subprocess.TimeoutExpired("gpt", 60)):
            result = preprocessor._run_gpt("/config/test_graph.xml", timeout=60)

        assert result is False

    def test_run_gpt_command_includes_memory_flags(self, preprocessor):
        """
        GPT command must include Java memory flags.
        Without them, SNAP crashes on large Sentinel-1 scenes (out of memory).
        """
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""

        with patch("src.preprocessing.subprocess.run", return_value=mock_result) as mock_run:
            preprocessor._run_gpt("/config/test_graph.xml")

        # Get the command that was passed to subprocess.run
        cmd = mock_run.call_args[0][0]

        assert "-J-Xms2G" in cmd, "Initial heap flag missing from GPT command"
        assert "-J-Xmx8G" in cmd, "Max heap flag missing from GPT command"


# ============================================================
# PREPROCESS PIPELINE TESTS
# Tests for the main preprocess() method (mocked GPT)
# ============================================================

class TestPreprocessPipeline:
    """Tests for the full preprocess() orchestration method."""

    def test_preprocess_returns_none_for_missing_input(self, preprocessor):
        """
        preprocess should return None if input scene file doesn't exist.
        """
        result = preprocessor.preprocess("/nonexistent/scene.zip")
        assert result is None

    def test_preprocess_skips_already_processed_scene(self, preprocessor):
        """
        preprocess should skip (return existing path) if output already exists.
        Prevents re-processing scenes that were already completed.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create fake input and output files
            input_path = os.path.join(tmpdir, "scene.zip")
            Path(input_path).touch()  # Create empty input file

            # Create fake already-processed output
            output_path = os.path.join(
                str(preprocessor.config.processed_dir),
                "scene_preprocessed_db.tif"
            )
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            Path(output_path).touch()

            result = preprocessor.preprocess(input_path)

            # Should return existing output path without re-processing
            assert result == output_path

            # Clean up
            Path(output_path).unlink(missing_ok=True)

    def test_preprocess_returns_none_on_gpt_failure(self, preprocessor):
        """
        preprocess should return None if SNAP GPT fails.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a fake input .zip file
            input_path = os.path.join(tmpdir, "test_scene.zip")
            Path(input_path).touch()

            # Mock GPT to fail
            with patch.object(preprocessor, "_run_gpt", return_value=False):
                result = preprocessor.preprocess(input_path)

        assert result is None


# ============================================================
# Run tests directly
# Usage: python3 -m pytest tests/test_preprocessing.py -v
# ============================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
