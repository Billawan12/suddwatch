"""
pipeline.py — SuddWatch End-to-End Pipeline Orchestrator
=========================================================
Runs the complete flood detection workflow for every new scene:

  1. Data acquisition  — download new Sentinel-1 scenes (Copernicus)
  2. Preprocessing     — SNAP GPT: orbit, thermal noise, calibration,
                         speckle filter, terrain correction → dB
  3. Flood detection   — 6-stage SAR flood classifier
  4. Risk assessment   — WorldPop + OSM overlay
  5. Alert dispatch    — SMS + email if thresholds are met
  6. Database logging  — every step is written to SQLite for the dashboard

Usage:
    python run_pipeline.py                         # scheduled run
    python run_pipeline.py --scene path/to/S1A_...zip
    python run_pipeline.py --scene data/processed/x_preprocessed_db.tif --no-alerts

    from src.pipeline import FloodPipeline
    FloodPipeline().run()
"""

import logging
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_time(value) -> Optional[datetime]:
    """ISO-8601 string → aware datetime (UTC), or None."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


class FloodPipeline:
    """
    End-to-end flood detection and alert pipeline.

    Each run() checks for new Sentinel-1 scenes (or processes the scenes
    you pass in), and for each one: preprocess → detect → assess → alert,
    logging everything to the database. A failure in one scene is recorded
    and the pipeline moves on to the next.
    """

    def __init__(self, config=None):
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from src.config import Config, setup_logging
        from src.database import DatabaseManager
        from src.data_acquisition import SentinelDownloader
        from src.preprocessing import SARPreprocessor
        from src.flood_detection import FloodDetector
        from src.risk_assessment import RiskAssessor
        from src.alerts import AlertManager

        # Only configure logging if the caller hasn't (run_pipeline.py does)
        if not logging.getLogger().handlers:
            setup_logging("INFO")

        self.config = config or Config()

        self.db         = DatabaseManager(self.config)
        self.downloader = SentinelDownloader(self.config)
        try:
            self.preprocessor = SARPreprocessor(self.config)
        except FileNotFoundError as e:
            # Lets already-preprocessed .tif scenes be processed on
            # machines without SNAP; raw .zip scenes will fail clearly.
            logger.warning(f"{e} — raw scenes cannot be preprocessed.")
            self.preprocessor = None
        self.detection_method = getattr(self.config, "detection_method", "threshold")
        if self.detection_method == "random_forest":
            from src.ml_flood_detection import MLFloodDetector
            self.detector = MLFloodDetector(self.config)
            if self.detector.model is None:
                self.detection_method = "otsu_gmm (fallback: no ML model)"
            logger.warning("Using the EXPERIMENTAL Random Forest detector")
        else:
            self.detector = FloodDetector(self.config)
            self.detection_method = "otsu_gmm"
        self.assessor = RiskAssessor(self.config)
        self.alerter  = AlertManager(self.config)

        # Static datasets are loaded once (expensive I/O). Missing files
        # are reported but don't stop the pipeline.
        logger.info("Loading population and OSM datasets...")
        try:
            self.assessor.load_population_data()
        except FileNotFoundError as e:
            logger.warning(f"{e} — affected population will be reported as 0.")
        self.assessor.load_osm_data()
        logger.info("Datasets loaded — pipeline ready")

    # ── Stage timing helper ───────────────────────────────────
    def _timed_stage(self, stage_name: str, func, *args, **kwargs):
        """Run a stage and return (result, duration_seconds); re-raises errors."""
        logger.info(f"[STAGE] {stage_name} — starting")
        t0 = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - t0
            logger.info(f"[STAGE] {stage_name} — completed in {duration:.1f}s")
            return result, duration
        except Exception as e:
            duration = time.time() - t0
            logger.error(f"[STAGE] {stage_name} — FAILED after {duration:.1f}s: {e}")
            raise

    def _log_stage(self, event_id: int, stage: str, duration: float, status="completed",
                   error: Optional[str] = None) -> None:
        end = _utcnow()
        start = datetime.fromtimestamp(end.timestamp() - duration, tz=timezone.utc)
        try:
            self.db.insert_processing_log(event_id, {
                "stage_name": stage, "start_time": start.isoformat(),
                "end_time": end.isoformat(), "duration_seconds": duration,
                "status": status, "error_message": error,
            })
        except Exception as e:
            logger.warning(f"Could not log stage {stage}: {e}")

    # ── Stage 1: Data acquisition ─────────────────────────────
    def _acquire(self):
        """Download new scenes. Returns (list_of_paths, duration_seconds)."""
        new_scenes, duration = self._timed_stage(
            "Data Acquisition", self.downloader.check_and_download_new_scenes)
        if not new_scenes:
            logger.info("No new scenes available — nothing to process")
        else:
            logger.info(f"Downloaded {len(new_scenes)} new scene(s)")
        return new_scenes, duration

    # ── Stage 2: Preprocessing ────────────────────────────────
    def _run_preprocessor(self, scene_path):
        """SNAP preprocessing; a .tif input is assumed to be preprocessed already."""
        scene_path = Path(scene_path)
        if scene_path.suffix.lower() in (".tif", ".tiff"):
            logger.info(f"{scene_path.name} is already a GeoTIFF — skipping SNAP preprocessing")
            return str(scene_path)
        if self.preprocessor is None:
            raise RuntimeError(
                "SNAP GPT is not available, so raw scenes cannot be preprocessed. "
                "Install SNAP or set SNAP_GPT_PATH in .env.")
        out = self.preprocessor.preprocess(scene_path)
        if not out:
            raise RuntimeError(f"SNAP preprocessing failed for {scene_path.name} "
                               f"(see the GPT errors above in the log)")
        return out

    def _preprocess(self, scene_path):
        """Returns (preprocessed_db_tif_path, duration_seconds)."""
        return self._timed_stage("Preprocessing", self._run_preprocessor, scene_path)

    # ── Stage 3: Flood detection ──────────────────────────────
    def _detect(self, db_path):
        """Returns (flood_mask_path, flood_extent_ha, duration_seconds)."""
        (mask_path, flood_ha), duration = self._timed_stage(
            "Flood Detection", self.detector.detect, db_path)
        logger.info(f"Flood extent: {flood_ha:,.1f} ha")
        return mask_path, flood_ha, duration

    # ── Stage 4: Risk assessment ──────────────────────────────
    def _assess(self, mask_path, flood_ha: float):
        """Returns (risk_summary_dict, risk_summary_json_path, duration_seconds)."""
        (risk_summary, summary_path), duration = self._timed_stage(
            "Risk Assessment", self.assessor.assess, mask_path, flood_ha)
        stats = risk_summary.get("summary_statistics", {})
        logger.info(
            f"Risk assessment: {risk_summary.get('affected_population_estimate', 0):,} affected, "
            f"{stats.get('total_villages_affected', 0)} villages, "
            f"{stats.get('total_roads_inaccessible', 0)} roads, "
            f"{stats.get('total_health_facilities_at_risk', 0)} health facilities"
        )
        return risk_summary, summary_path, duration

    # ── Stage 5: Alert dispatch ───────────────────────────────
    def _alert(self, risk_summary: dict, event_id: int, event_label: Optional[str] = None,
               dry_run: bool = False):
        """Returns (alert_results_dict, duration_seconds)."""
        min_area = float(getattr(self.config, "min_flood_area_ha", 0) or 0)
        if min_area and float(risk_summary.get("flood_extent_ha", 0)) < min_area:
            reason = (f"flood extent {risk_summary.get('flood_extent_ha', 0):,.0f} ha "
                      f"below minimum area {min_area:,.0f} ha")
            logger.info(f"Alert suppressed: {reason}")
            return ({"alert_triggered": False, "reason": reason, "sms_results": [],
                     "email_results": [], "total_sent": 0, "total_failed": 0}, 0.0)
        return self._timed_stage(
            "Alert Dispatch", self.alerter.send_flood_alert,
            risk_summary, event_id, self.db, event_label=event_label, dry_run=dry_run)

    # ── IoU ───────────────────────────────────────────────────
    def _compute_iou(self, mask_path, scene_id: str) -> Optional[float]:
        """
        Intersection over Union against a hand-labelled reference mask:

            IoU = |predicted ∩ reference| / |predicted ∪ reference|

        Looks for data/reference_masks/<scene_id>_reference.tif (any grid —
        it is aligned to the prediction first). Returns None when no
        reference exists: an unvalidated detection has NO IoU, and the
        dashboard shows it as "not validated" rather than a made-up number.
        """
        ref_dir = Path(getattr(self.config, "reference_masks_dir",
                               self.config.project_root / "data" / "reference_masks"))
        reference_path = ref_dir / f"{scene_id}_reference.tif"
        if not reference_path.exists():
            logger.info(f"No reference mask for {scene_id} — IoU not computed (not validated)")
            return None
        try:
            import numpy as np
            import rasterio
            from rasterio.enums import Resampling
            from src import raster_utils as ru

            with rasterio.open(str(mask_path)) as src:
                pred_raw = src.read(1)
                profile = src.profile
            ref = ru.align_to_grid(reference_path, pred_raw.shape, profile["transform"],
                                   ru.grid_crs(profile), resampling=Resampling.nearest,
                                   fill_value=255, dtype=np.float32)
            valid = (pred_raw != 255) & (ref != 255)
            predicted = (pred_raw == 1) & valid
            reference = (ref == 1) & valid
            union = np.logical_or(predicted, reference).sum()
            if union == 0:
                return 1.0
            iou = round(float(np.logical_and(predicted, reference).sum()) / float(union), 4)
            logger.info(f"IoU vs reference: {iou:.4f}")
            return iou
        except Exception as e:
            logger.warning(f"IoU computation failed: {e}")
            return None

    # ── One scene ─────────────────────────────────────────────
    def process_scene(self, scene_path, acq_duration: float = 0.0,
                      dry_run_alerts: bool = False) -> dict:
        """Process one scene end-to-end. Raises on failure (caller records it)."""
        scene_path = Path(scene_path)
        scene_id = scene_path.name
        for suffix in (".zip", ".tif", ".tiff"):
            if scene_id.lower().endswith(suffix):
                scene_id = scene_id[: -len(suffix)]
        for tail in ("_preprocessed_db",):
            if scene_id.endswith(tail):
                scene_id = scene_id[: -len(tail)]

        from src.data_acquisition import acquisition_time_from_name
        info = getattr(self.downloader, "scene_info", {}).get(str(scene_path), {})
        acq_time = info.get("acquisition_time") or acquisition_time_from_name(scene_path.name)

        result = {"scene_id": scene_id, "status": "started", "timings": {},
                  "satellite_acquisition_time": acq_time}
        start = _utcnow()
        event_id = self.db.insert_event({
            "event_timestamp": start.isoformat(),
            "satellite_acquisition_time": acq_time,
            "processing_start_time": start.isoformat(),
            "scene_id": scene_id,
            "scene_path": str(scene_path),
            "status": "processing",
        })
        label = f"EVT-{start.year}-{event_id:03d}"
        result["event_id"], result["event_label"] = event_id, label
        self.db.update_event(event_id, {"event_label": label})
        logger.info(f"Event {label} (id {event_id}) — scene {scene_id}")
        if acq_duration:
            self._log_stage(event_id, "data_acquisition", acq_duration)

        try:
            db_path, d_pre = self._preprocess(scene_path)
            result["timings"]["preprocessing_s"] = round(d_pre)
            self._log_stage(event_id, "preprocessing", d_pre)

            mask_path, flood_ha, d_det = self._detect(db_path)
            result["timings"]["flood_detection_s"] = round(d_det)
            result["flood_extent_ha"] = flood_ha
            self._log_stage(event_id, "flood_detection", d_det)

            iou = self._compute_iou(mask_path, scene_id)
            result["iou_score"] = iou
            self.db.insert_flood_mask(event_id, {
                "flood_extent_ha": flood_ha, "iou_score": iou,
                "geotiff_path": str(mask_path), "detection_method": self.detection_method,
            })

            risk, summary_path, d_ass = self._assess(mask_path, flood_ha)
            result["timings"]["risk_assessment_s"] = round(d_ass)
            self._log_stage(event_id, "risk_assessment", d_ass)
            self.db.update_event(event_id, {
                "affected_population": int(risk.get("affected_population_estimate", 0)),
                "risk_summary_path": str(summary_path),
            })

            for v in risk.get("affected_villages", []):
                self.db.insert_affected_village(event_id, v)
            for road in risk.get("inaccessible_roads", []):
                self.db.insert_infrastructure_impact(event_id, {
                    "infrastructure_type": "road",
                    "name": road.get("name", ""),
                    "facility_type": road.get("facility_type", "road"),
                    "segment_length_km": road.get("segment_length_km"),
                    "flooded_length_km": road.get("flooded_length_km"),
                    "status": road.get("status", "inaccessible"),
                })
            for hf in risk.get("health_facilities_at_risk", []):
                self.db.insert_infrastructure_impact(event_id, {
                    "infrastructure_type": "health_facility",
                    "name": hf.get("name", ""),
                    "facility_type": hf.get("facility_type", ""),
                    "status": hf.get("status", "at_risk"),
                    "coordinates": hf.get("coordinates"),
                })

            alerts, d_alert = self._alert(risk, event_id, event_label=label,
                                          dry_run=dry_run_alerts)
            result["timings"]["alert_dispatch_s"] = round(d_alert)
            result["alert_triggered"] = alerts.get("alert_triggered", False)
            result["alert_reason"] = alerts.get("reason", "")
            result["alerts_sent"] = alerts.get("total_sent", 0)
            result["alerts_failed"] = alerts.get("total_failed", 0)
            self._log_stage(event_id, "alert_dispatch", d_alert)

            # Latency:
            #  processing = time our own stages took (download → alerts)
            #  end-to-end = satellite sensing time → alerts finished
            #               (this is what the 60-minute SLA refers to)
            end = _utcnow()
            processing_s = acq_duration + d_pre + d_det + d_ass + d_alert
            acq_dt = _parse_time(acq_time)
            end_to_end_s = (end - acq_dt).total_seconds() if acq_dt else None
            total_s = end_to_end_s if end_to_end_s is not None else processing_s
            result["timings"]["processing_s"] = round(processing_s)
            result["timings"]["end_to_end_latency_s"] = (
                round(end_to_end_s) if end_to_end_s is not None else None)
            result["timings"]["total_latency_min"] = round(total_s / 60, 1)

            self.db.update_event(event_id, {
                "status": "completed",
                "processing_end_time": end.isoformat(),
                "processing_seconds": processing_s,
                "total_latency_seconds": total_s,
            })
            result["status"] = "completed"
            logger.info(
                f"{label} completed — {flood_ha:,.0f} ha, "
                f"processing {processing_s/60:.1f} min, "
                + (f"end-to-end {end_to_end_s/60:.1f} min, " if end_to_end_s is not None
                   else "end-to-end n/a (acquisition time unknown), ")
                + f"IoU {iou if iou is not None else 'not validated'}"
            )
            return result

        except Exception as e:
            try:
                self.db.update_event(event_id, {
                    "status": "failed",
                    "processing_end_time": _utcnow().isoformat(),
                    "error_message": str(e)[:500],
                })
            except Exception:
                pass
            raise

    # ── Main run ──────────────────────────────────────────────
    def run(self, scene_paths: Optional[Iterable] = None,
            dry_run_alerts: bool = False) -> dict:
        """
        Process new scenes (downloaded now) or the given `scene_paths`.

        Returns a summary dict:
          scenes_processed, scenes_failed, total_alerts_sent, status, ...
        """
        pipeline_start = time.time()
        logger.info("=" * 60)
        logger.info("SuddWatch Pipeline Run Starting")
        logger.info(f"Time: {_utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        logger.info("=" * 60)

        results = {
            "pipeline_start": _utcnow().isoformat(),
            "scenes_processed": [],
            "scenes_failed": [],
            "total_alerts_sent": 0,
        }

        if scene_paths:
            new_scenes, acq_duration = [Path(p) for p in scene_paths], 0.0
            logger.info(f"Processing {len(new_scenes)} scene(s) given on the command line")
        else:
            try:
                new_scenes, acq_duration = self._acquire()
            except Exception as e:
                logger.error(f"Data acquisition failed: {e}")
                results["acquisition_error"] = str(e)
                results["status"] = "acquisition_failed"
                return results

        if not new_scenes:
            logger.info("Pipeline complete — no new scenes to process")
            results["status"] = "no_new_scenes"
            return results

        for scene_path in new_scenes:
            try:
                scene_result = self.process_scene(
                    scene_path, acq_duration=acq_duration, dry_run_alerts=dry_run_alerts)
                results["scenes_processed"].append(scene_result)
                results["total_alerts_sent"] += scene_result.get("alerts_sent", 0)
            except Exception as e:
                logger.error(f"Pipeline failed for scene {Path(scene_path).name}: {e}\n"
                             + traceback.format_exc())
                results["scenes_failed"].append({
                    "scene_id": Path(scene_path).stem, "status": "failed", "error": str(e)})
            # Download time is shared by the batch — count it once
            acq_duration = 0.0

        total = time.time() - pipeline_start
        results["pipeline_end"] = _utcnow().isoformat()
        results["total_duration_s"] = round(total)
        results["status"] = "completed" if results["scenes_processed"] else "no_successes"
        logger.info("=" * 60)
        logger.info(
            f"Pipeline complete — {len(results['scenes_processed'])} processed, "
            f"{len(results['scenes_failed'])} failed, "
            f"{results['total_alerts_sent']} alerts sent, {total:.1f}s total")
        logger.info("=" * 60)
        return results


if __name__ == "__main__":
    print("Use run_pipeline.py to run the pipeline:  python run_pipeline.py --help")
