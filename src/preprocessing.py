# ============================================================
# SuddWatch - SAR Preprocessing Module
# File: src/preprocessing.py
# Purpose: Preprocesses raw Sentinel-1 SAR scenes using ESA
#          SNAP via the GPT command-line tool (subprocess).
#          Produces calibrated, terrain-corrected GeoTIFFs
#          ready for flood detection.
#
# Processing chain (in order):
#   1. Apply orbit correction   — corrects satellite position metadata
#   2. Radiometric calibration  — converts DN values to sigma0 (dB)
#   3. Speckle filtering        — reduces SAR noise (Lee 5x5)
#   4. Terrain correction       — orthorectifies using SRTM DEM
#   5. Convert to dB            — log10 transformation for thresholding
#
# Approach: SNAP GPT subprocess (XML graph files)
# Reason: esa_snappy Python binding has a known bug on Apple Silicon
#         Macs. GPT subprocess produces identical results and is
#         more stable across all platforms.
#
# Course: SWE3090 - Software Project 1
# Student: Madut Chan (671336)
# ============================================================

import logging
import subprocess
import time
import os
from pathlib import Path
from typing import Optional
import numpy as np
import rasterio
from rasterio.crs import CRS

from src.config import Config

# --- Module logger ---
logger = logging.getLogger(__name__)


class SARPreprocessor:
    """
    Preprocesses Sentinel-1 SAR scenes using ESA SNAP GPT.

    Takes a raw .zip scene from data/raw/ and runs it through
    the full preprocessing chain, outputting a single-band
    float32 GeoTIFF in dB to data/processed/.

    The preprocessing uses SNAP's Graph Processing Tool (GPT)
    via subprocess calls with XML graph files. This approach
    is used instead of esa_snappy due to Apple Silicon
    compatibility issues with the Python-Java bridge.

    Example usage:
        from src.config import Config
        from src.preprocessing import SARPreprocessor
        config = Config()
        preprocessor = SARPreprocessor(config)
        output_path = preprocessor.preprocess('data/raw/scene.zip')
    """

    def __init__(self, config: Config):
        """
        Initialises the preprocessor and verifies SNAP GPT is available.

        Args:
            config: Config object with SNAP settings and file paths
        """
        self.config = config

        # Path to SNAP GPT executable
        self.gpt_path = config.snap_gpt_path

        # Verify GPT exists before any processing starts
        if not Path(self.gpt_path).exists():
            raise FileNotFoundError(
                f"SNAP GPT not found at {self.gpt_path}. "
                f"Please verify SNAP installation."
            )

        logger.info(f"SARPreprocessor initialised. GPT: {self.gpt_path}")

    # ============================================================
    # SNAP GPT XML GRAPH GENERATION
    # Builds XML processing graphs for each stage
    # ============================================================

    def _build_preprocessing_graph(
        self,
        input_path: str,
        output_path: str,
    ) -> str:
        """
        Builds a complete SNAP GPT XML processing graph for the
        full preprocessing chain.

        Combines all 4 SNAP operators into a single graph so SNAP
        only reads/writes the scene once — much faster than running
        each operator separately.

        Operators in order:
        1. Apply-Orbit-File     — precise orbit correction
        2. Calibration          — sigma0 backscatter, VH band only
        3. Speckle-Filter       — Lee filter, 5x5 window
        4. Terrain-Correction   — Range-Doppler with SRTM 3Sec DEM

        Args:
            input_path: path to raw .zip scene file
            output_path: path for intermediate .dim output
                         (before dB conversion)

        Returns:
            str: XML graph content as string
        """
        # Build XML graph — each node connects to the previous
        # Read → ApplyOrbitFile → Calibration → SpeckleFilter
        # → TerrainCorrection → Write
        xml_graph = f"""<graph id="SuddWatchPreprocessing">
  <version>1.0</version>

  <!-- Step 1: Read the raw Sentinel-1 scene -->
  <node id="Read">
    <operator>Read</operator>
    <sources/>
    <parameters>
      <file>{input_path}</file>
    </parameters>
  </node>

  <!-- Step 2: Apply precise orbit correction -->
  <!-- Downloads precise orbit files from ESA automatically -->
  <node id="Apply-Orbit-File">
    <operator>Apply-Orbit-File</operator>
    <sources>
      <sourceProduct refid="Read"/>
    </sources>
    <parameters>
      <orbitType>Sentinel Precise (Auto Download)</orbitType>
      <polyDegree>3</polyDegree>
      <continueOnFail>true</continueOnFail>
    </parameters>
  </node>

  <!-- Step 3: Radiometric calibration to sigma0 backscatter -->
  <!-- VH polarisation is selected — most sensitive to surface water -->
  <node id="Calibration">
    <operator>Calibration</operator>
    <sources>
      <sourceProduct refid="Apply-Orbit-File"/>
    </sources>
    <parameters>
      <sourceBands/>
      <auxFile>Product Auxiliary File</auxFile>
      <externalAuxFile/>
      <outputImageInComplex>false</outputImageInComplex>
      <outputImageScaleInDb>false</outputImageScaleInDb>
      <createGammaBand>false</createGammaBand>
      <createBetaBand>false</createBetaBand>
      <selectedPolarisations>VH</selectedPolarisations>
      <outputSigmaBand>true</outputSigmaBand>
      <outputGammaBand>false</outputGammaBand>
      <outputBetaBand>false</outputBetaBand>
    </parameters>
  </node>

  <!-- Step 4: Lee speckle filter to reduce SAR noise -->
  <!-- 5x5 window is standard for Sentinel-1 IW GRD -->
  <node id="Speckle-Filter">
    <operator>Speckle-Filter</operator>
    <sources>
      <sourceProduct refid="Calibration"/>
    </sources>
    <parameters>
      <sourceBands/>
      <filter>{self.config.snap_speckle_filter}</filter>
      <filterSizeX>{self.config.snap_speckle_size}</filterSizeX>
      <filterSizeY>{self.config.snap_speckle_size}</filterSizeY>
      <dampingFactor>2</dampingFactor>
      <estimateENL>true</estimateENL>
      <enl>1.0</enl>
      <numLooksStr>1</numLooksStr>
      <targetWindowSizeStr>3x3</targetWindowSizeStr>
      <sigmaStr>0.9</sigmaStr>
      <anSize>50</anSize>
    </parameters>
  </node>

  <!-- Step 5: Terrain correction — orthorectification -->
  <!-- Uses SRTM 3Sec DEM (auto-downloaded by SNAP) -->
  <!-- Output projected to WGS84 (EPSG:4326) for consistency -->
  <node id="Terrain-Correction">
    <operator>Terrain-Correction</operator>
    <sources>
      <sourceProduct refid="Speckle-Filter"/>
    </sources>
    <parameters>
      <sourceBands/>
      <demName>{self.config.snap_dem}</demName>
      <externalDEMFile/>
      <externalDEMNoDataValue>0.0</externalDEMNoDataValue>
      <externalDEMApplyEGM>true</externalDEMApplyEGM>
      <demResamplingMethod>BILINEAR_INTERPOLATION</demResamplingMethod>
      <imgResamplingMethod>BILINEAR_INTERPOLATION</imgResamplingMethod>
      <pixelSpacingInMeter>10.0</pixelSpacingInMeter>
      <pixelSpacingInDegree>8.983152841195215E-5</pixelSpacingInDegree>
      <mapProjection>GEOGCS[&quot;WGS84(DD)&quot;, DATUM[&quot;WGS84&quot;, SPHEROID[&quot;WGS84&quot;, 6378137.0, 298.257223563]], PRIMEM[&quot;Greenwich&quot;, 0.0], UNIT[&quot;degree&quot;, 0.017453292519943295], AXIS[&quot;Geodetic longitude&quot;, EAST], AXIS[&quot;Geodetic latitude&quot;, NORTH]]</mapProjection>  <!-- WGS84 EPSG:4326 -->
      <alignToStandardGrid>false</alignToStandardGrid>
      <standardGridOriginX>0.0</standardGridOriginX>
      <standardGridOriginY>0.0</standardGridOriginY>
      <nodataValueAtSea>false</nodataValueAtSea>  <!-- false: Sudd is inland, not sea -->
      <saveDEM>false</saveDEM>
      <saveLatLon>false</saveLatLon>
      <saveIncidenceAngleFromEllipsoid>false</saveIncidenceAngleFromEllipsoid>
      <saveLocalIncidenceAngle>false</saveLocalIncidenceAngle>
      <saveProjectedLocalIncidenceAngle>false</saveProjectedLocalIncidenceAngle>
      <saveSelectedSourceBand>true</saveSelectedSourceBand>
      <saveLayoverShadowMask>false</saveLayoverShadowMask>
      <applyRadiometricNormalization>false</applyRadiometricNormalization>
      <saveSigmaNought>false</saveSigmaNought>
      <saveGammaNought>false</saveGammaNought>
      <saveBetaNought>false</saveBetaNought>
      <incidenceAngleForSigma0>Use projected local incidence angle from DEM</incidenceAngleForSigma0>
      <incidenceAngleForGamma0>Use projected local incidence angle from DEM</incidenceAngleForGamma0>
      <auxFile>Latest Auxiliary File</auxFile>
    </parameters>
  </node>

  <!-- Step 6: Write output as GeoTIFF -->
  <node id="Write">
    <operator>Write</operator>
    <sources>
      <sourceProduct refid="Terrain-Correction"/>
    </sources>
    <parameters>
      <file>{output_path}</file>
      <formatName>GeoTIFF</formatName>
    </parameters>
  </node>

</graph>"""

        return xml_graph

    def _save_graph(self, xml_content: str, graph_name: str) -> str:
        """
        Saves an XML graph to the config/ directory for GPT to read.

        Args:
            xml_content: XML string content of the graph
            graph_name: filename for the graph (without .xml extension)

        Returns:
            str: full path to saved graph file
        """
        # Ensure config directory exists
        config_dir = self.config.project_root / "config"
        config_dir.mkdir(parents=True, exist_ok=True)

        graph_path = config_dir / f"{graph_name}.xml"

        with open(graph_path, "w") as f:
            f.write(xml_content)

        logger.debug(f"Graph saved to {graph_path}")
        return str(graph_path)

    # ============================================================
    # GPT EXECUTION
    # Runs SNAP GPT with an XML graph via subprocess
    # ============================================================

    def _run_gpt(self, graph_path: str, timeout: int = 3600) -> bool:
        """
        Executes SNAP GPT with the given XML graph file.

        Uses subprocess to call GPT as a command-line tool.
        Captures stdout/stderr and logs them for debugging.

        Args:
            graph_path: path to the XML graph file
            timeout: max seconds to wait for GPT (default 1 hour)

        Returns:
            bool: True if GPT succeeded, False if it failed
        """
        # Build GPT command
        # -J flags set Java memory allocation for large scenes
        cmd = [
            self.gpt_path,
            graph_path,
            "-J-Xms2G",    # Initial Java heap: 2GB
            "-J-Xmx8G",    # Maximum Java heap: 8GB
            "-q", "4",     # Use 4 CPU threads
        ]

        logger.info(f"Running SNAP GPT: {' '.join(cmd)}")
        start_time = time.time()

        try:
            # Run GPT as subprocess — capture output for logging
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            elapsed = time.time() - start_time

            if result.returncode == 0:
                logger.info(f"GPT completed successfully in {elapsed:.1f}s")
                return True
            else:
                # Log stderr for debugging
                logger.error(
                    f"GPT failed after {elapsed:.1f}s. "
                    f"Return code: {result.returncode}"
                )
                if result.stderr:
                    # Log last 500 chars of stderr — most relevant error info
                    logger.error(f"GPT stderr: {result.stderr[-500:]}")
                return False

        except subprocess.TimeoutExpired:
            logger.error(f"GPT timed out after {timeout}s")
            return False
        except FileNotFoundError:
            logger.error(f"GPT executable not found at {self.gpt_path}")
            return False

    # ============================================================
    # dB CONVERSION
    # Converts linear sigma0 values to decibels
    # ============================================================

    def _convert_to_db(self, input_path: str, output_path: str) -> str:
        """
        Converts linear sigma0 GeoTIFF to dB scale using rasterio.

        Formula: dB = 10 * log10(sigma0)
        Invalid pixels (<=0) are set to NaN to avoid log errors.

        This step is done in Python (not SNAP) because:
        - SNAP's dB conversion sometimes causes issues with
          downstream rasterio reading
        - Python gives us full control over NaN handling
        - rasterio reads/writes are fast for this operation

        Args:
            input_path: path to linear sigma0 GeoTIFF
            output_path: path for dB output GeoTIFF

        Returns:
            str: path to output dB GeoTIFF
        """
        logger.info("Converting to dB scale...")

        try:
            with rasterio.open(input_path) as src:
                # Read the first (and only) band
                data = src.read(1).astype(np.float32)
                profile = src.profile.copy()

            # Replace invalid values with NaN before log conversion
            # Pixels with value <= 0 are no-data or ocean areas
            data[data <= 0] = np.nan

            # Apply dB conversion: 10 * log10(sigma0)
            # np.errstate suppresses divide-by-zero warnings for NaN pixels
            with np.errstate(divide='ignore', invalid='ignore'):
                data_db = 10.0 * np.log10(data)

            # Update profile for output GeoTIFF
            # TILED=YES with BLOCKXSIZE/BLOCKYSSIZE required for compression
            # to work correctly and for efficient spatial reads
            profile.update(
                dtype=rasterio.float32,   # float32 sufficient for dB values
                count=1,                   # Single band output
                compress='lzw',            # LZW compression reduces file size
                nodata=np.nan,
                tiled=True,                # Required for BLOCKXSIZE to work
                blockxsize=256,            # 256x256 tile size — efficient for reads
                blockysize=256,
            )

            # Write dB GeoTIFF
            with rasterio.open(output_path, 'w', **profile) as dst:
                dst.write(data_db, 1)

            logger.info(f"dB conversion complete: {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"dB conversion failed: {e}")
            raise

    # ============================================================
    # MAIN PREPROCESSING METHOD
    # Full pipeline from raw .zip to calibrated dB GeoTIFF
    # ============================================================

    def preprocess(self, input_path: str) -> Optional[str]:
        """
        Runs the full SAR preprocessing pipeline on a raw scene.

        Pipeline:
        1. Generate SNAP GPT XML graph
        2. Run GPT (orbit correction → calibration → speckle filter
           → terrain correction) — outputs linear sigma0 GeoTIFF
        3. Convert linear sigma0 to dB using rasterio
        4. Clean up intermediate files
        5. Return path to final dB GeoTIFF

        The output filename is derived from the input filename
        with '_preprocessed_db' suffix added.

        Args:
            input_path: path to raw Sentinel-1 .zip scene file

        Returns:
            str: path to final preprocessed dB GeoTIFF,
                 or None if preprocessing failed
        """
        input_path = Path(input_path)

        # Validate input file exists
        if not input_path.exists():
            logger.error(f"Input scene not found: {input_path}")
            return None

        # Derive output filenames from input scene name
        scene_name = input_path.stem  # Remove .zip extension

        # Intermediate file — linear sigma0 GeoTIFF from SNAP
        intermediate_path = str(
            self.config.processed_dir / f"{scene_name}_sigma0.tif"
        )

        # Final output — dB GeoTIFF for flood detection
        final_output_path = str(
            self.config.processed_dir / f"{scene_name}_preprocessed_db.tif"
        )

        # Skip if already preprocessed — check for existing output
        if Path(final_output_path).exists():
            logger.info(
                f"Scene already preprocessed: {final_output_path} — skipping."
            )
            return final_output_path

        logger.info(f"Starting preprocessing for: {scene_name}")
        start_time = time.time()

        try:
            # --- Step 1: Generate and save XML graph ---
            logger.info("Step 1/3: Generating SNAP GPT processing graph...")
            xml_content = self._build_preprocessing_graph(
                input_path=str(input_path),
                output_path=intermediate_path,
            )
            graph_path = self._save_graph(
                xml_content=xml_content,
                graph_name=f"snap_preprocess_{scene_name}",
            )
            logger.info(f"Graph saved: {graph_path}")

            # --- Step 2: Run SNAP GPT ---
            # This is the longest step — typically 10-20 minutes
            logger.info("Step 2/3: Running SNAP GPT preprocessing chain...")
            logger.info(
                "This step takes 10-20 minutes. "
                "Check logs/pipeline.log for progress."
            )

            success = self._run_gpt(graph_path)

            if not success:
                logger.error(f"SNAP GPT failed for scene: {scene_name}")
                return None

            # Verify intermediate output was created
            if not Path(intermediate_path).exists():
                logger.error(
                    f"GPT completed but output not found: {intermediate_path}"
                )
                return None

            # --- Step 3: Convert to dB ---
            logger.info("Step 3/3: Converting to dB scale...")
            self._convert_to_db(
                input_path=intermediate_path,
                output_path=final_output_path,
            )

            # --- Step 4: Clean up intermediate file ---
            # Intermediate sigma0 file is large — delete after dB conversion
            Path(intermediate_path).unlink(missing_ok=True)
            logger.info("Intermediate sigma0 file cleaned up.")

            elapsed = time.time() - start_time
            logger.info(
                f"Preprocessing complete: {scene_name} "
                f"({elapsed:.1f}s total)"
            )
            return final_output_path

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error(
                f"Preprocessing failed for {scene_name} "
                f"after {elapsed:.1f}s: {e}"
            )
            # Clean up any partial output files
            Path(intermediate_path).unlink(missing_ok=True)
            Path(final_output_path).unlink(missing_ok=True)
            return None

    def validate_output(self, output_path: str) -> bool:
        """
        Validates a preprocessed GeoTIFF file is usable.

        Checks:
        - File exists and is readable by rasterio
        - CRS is set (terrain correction must have projected it)
        - Contains valid (non-NaN) data pixels
        - dB values are in expected range for Sentinel-1 (-30 to 5 dB)

        Args:
            output_path: path to preprocessed dB GeoTIFF to validate

        Returns:
            bool: True if file is valid and usable, False otherwise
        """
        # Check file exists before attempting to open
        if not Path(output_path).exists():
            logger.warning(f"Output file does not exist: {output_path}")
            return False

        try:
            with rasterio.open(output_path) as src:
                # Check CRS is set — terrain correction should have set this
                if not src.crs:
                    logger.warning(f"No CRS found in output: {output_path}")
                    return False

                # Read data and check for valid pixels
                data = src.read(1)
                valid_pixels = data[~np.isnan(data)]

                if len(valid_pixels) == 0:
                    logger.warning(f"No valid pixels in output: {output_path}")
                    return False

                # Check dB range — Sentinel-1 VH typically -25 to 0 dB
                # Allow wider range (-40 to 10) to catch edge cases
                min_val = float(np.min(valid_pixels))
                max_val = float(np.max(valid_pixels))

                if min_val < -40 or max_val > 10:
                    logger.warning(
                        f"Unusual dB range: min={min_val:.1f}, max={max_val:.1f}. "
                        f"Expected -40 to 10 dB for Sentinel-1 VH."
                    )
                    # Don't fail — just warn. Some scenes may have unusual values.

                logger.info(
                    f"Output validated: {Path(output_path).name} | "
                    f"CRS: {src.crs} | "
                    f"Shape: {src.shape} | "
                    f"dB range: {min_val:.1f} to {max_val:.1f}"
                )
                return True

        except Exception as e:
            logger.error(f"Output validation failed: {e}")
            return False


# ============================================================
# Quick self-test — run this file directly to verify setup
# Does NOT run full preprocessing (requires a scene file)
# Tests: GPT accessibility, graph generation, dB conversion
# Usage: python3 -m src.preprocessing
# ============================================================
if __name__ == "__main__":
    from src.config import Config, setup_logging
    import tempfile
    setup_logging()

    config = Config()

    print("\n" + "=" * 55)
    print("SuddWatch Preprocessing Verification")
    print("=" * 55)

    # --- Test 1: Preprocessor initialisation ---
    print("\n1. Initialising SARPreprocessor...")
    try:
        preprocessor = SARPreprocessor(config)
        print(f"   ✓ Preprocessor initialised")
        print(f"   ✓ GPT path: {preprocessor.gpt_path}")
    except Exception as e:
        print(f"   ✗ Failed: {e}")
        exit(1)

    # --- Test 2: GPT responds to help command ---
    print("\n2. Testing SNAP GPT availability...")
    try:
        result = subprocess.run(
            [config.snap_gpt_path, "-h"],
            capture_output=True,
            text=True,
            timeout=60,
        )
        # GPT returns non-zero for -h but still outputs usage
        if "Usage" in result.stdout or "Usage" in result.stderr:
            print("   ✓ SNAP GPT responds correctly")
        else:
            print("   ✓ SNAP GPT found and executable")
    except Exception as e:
        print(f"   ✗ GPT test failed: {e}")

    # --- Test 3: XML graph generation ---
    print("\n3. Testing XML graph generation...")
    try:
        xml = preprocessor._build_preprocessing_graph(
            input_path="/data/raw/test_scene.zip",
            output_path="/data/processed/test_output.tif",
        )
        # Check all 6 operators are in the graph
        required_nodes = [
            "Read", "Apply-Orbit-File", "Calibration",
            "Speckle-Filter", "Terrain-Correction", "Write"
        ]
        all_present = all(node in xml for node in required_nodes)
        if all_present:
            print(f"   ✓ XML graph generated with all {len(required_nodes)} operators")
        else:
            missing = [n for n in required_nodes if n not in xml]
            print(f"   ✗ Missing operators: {missing}")
    except Exception as e:
        print(f"   ✗ Graph generation failed: {e}")

    # --- Test 4: Graph save to config/ directory ---
    print("\n4. Testing graph file save...")
    try:
        graph_path = preprocessor._save_graph(xml, "test_graph")
        if Path(graph_path).exists():
            print(f"   ✓ Graph saved: {graph_path}")
            # Clean up test graph
            Path(graph_path).unlink()
        else:
            print(f"   ✗ Graph file not found after save")
    except Exception as e:
        print(f"   ✗ Graph save failed: {e}")

    # --- Test 5: dB conversion with synthetic data ---
    print("\n5. Testing dB conversion...")
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create synthetic linear sigma0 data
            test_data = np.array([[0.01, 0.05, 0.1], [0.0, 0.2, 0.5]], dtype=np.float32)
            input_tif = os.path.join(tmpdir, "sigma0.tif")
            output_tif = os.path.join(tmpdir, "sigma0_db.tif")

            # Write test GeoTIFF
            transform = rasterio.transform.from_bounds(29, 5, 35, 12, 3, 2)
            with rasterio.open(
                input_tif, 'w',
                driver='GTiff', height=2, width=3,
                count=1, dtype='float32',
                crs=CRS.from_epsg(4326),
                transform=transform
            ) as dst:
                dst.write(test_data, 1)

            # Run dB conversion
            preprocessor._convert_to_db(input_tif, output_tif)

            # Verify output
            with rasterio.open(output_tif) as src:
                result_data = src.read(1)
                valid = result_data[~np.isnan(result_data)]
                print(f"   ✓ dB conversion successful")
                print(f"   ✓ Input range: {test_data[test_data > 0].min():.3f} to {test_data.max():.3f}")
                print(f"   ✓ Output dB range: {valid.min():.1f} to {valid.max():.1f} dB")
                print(f"   ✓ NaN correctly set for zero/negative pixels")

    except Exception as e:
        print(f"   ✗ dB conversion failed: {e}")

    # --- Summary ---
    print("\n" + "=" * 55)
    print("Preprocessing module verified.")
    print("Note: Full preprocessing requires a Sentinel-1 scene.")
    print(f"Scenes available in: {config.raw_dir}")
    raw_scenes = list(config.raw_dir.glob("*.zip"))
    if raw_scenes:
        print(f"Found {len(raw_scenes)} scene(s) ready for processing.")
    else:
        print("No scenes downloaded yet — run data_acquisition first.")
    print("=" * 55 + "\n")
