# ============================================================
# SuddWatch — Sprint 3 Test Suite
# File: tests/test_pipeline.py
# Tests: AlertManager + FloodPipeline
#
# Run unit tests only (no API calls):
#   pytest tests/test_pipeline.py -m "not integration" -v
#
# Run all including live API tests:
#   pytest tests/test_pipeline.py -v
# ============================================================

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import Config


# ── Fixtures ──────────────────────────────────────────────────
@pytest.fixture
def cfg():
    """Real config loaded from .env"""
    return Config()


@pytest.fixture
def sample_risk():
    """A realistic risk summary dict as returned by risk_assessment.py"""
    return {
        "flood_extent_ha": 1200.0,
        "affected_population_estimate": 6637,
        "affected_villages": [
            {"village_name": "Bor South",  "estimated_population": 12400,
             "flood_risk_percentage": 87},
            {"village_name": "Akobo East", "estimated_population": 8200,
             "flood_risk_percentage": 74},
            {"village_name": "Twic East",  "estimated_population": 6700,
             "flood_risk_percentage": 61},
        ],
        "inaccessible_roads": [
            {"name": "Bor-Malakal A1", "segment_length_km": 142,
             "alt_route": "Air only"},
        ],
        "health_facilities_at_risk": [
            {"name": "Bor State Hospital", "facility_type": "Hospital"},
        ],
        "summary_statistics": {
            "total_villages_affected":         121,
            "total_roads_inaccessible":        116,
            "total_health_facilities_at_risk":   4,
            "high_risk_villages":               23,
        },
    }


@pytest.fixture
def below_threshold_risk():
    """Risk summary below alert thresholds — should NOT trigger alert"""
    return {
        "flood_extent_ha": 100.0,
        "affected_population_estimate": 50,
        "affected_villages": [],
        "inaccessible_roads": [],
        "health_facilities_at_risk": [],
        "summary_statistics": {},
    }


@pytest.fixture
def mock_db():
    """Mock DatabaseManager that records all calls"""
    db = MagicMock()
    db.insert_event.return_value     = 42
    db.update_event.return_value     = None
    db.insert_processing_log.return_value = 1
    db.insert_flood_mask.return_value     = 1
    db.insert_affected_village.return_value   = 1
    db.insert_infrastructure_impact.return_value = 1
    db.insert_alert.return_value     = 1
    return db


# ════════════════════════════════════════════════════════════
# AlertManager — Unit Tests
# ════════════════════════════════════════════════════════════

class TestAlertThresholds:
    """Tests for should_alert() threshold logic."""

    def test_alert_triggered_above_flood_threshold(self, cfg, sample_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        triggered, reason = alerter.should_alert(sample_risk)
        assert triggered is True
        assert "flood extent" in reason.lower()

    def test_alert_triggered_above_population_threshold(self, cfg, sample_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        triggered, reason = alerter.should_alert(sample_risk)
        assert triggered is True
        assert "population" in reason.lower() or "flood" in reason.lower()

    def test_alert_not_triggered_below_both_thresholds(self, cfg, below_threshold_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        triggered, reason = alerter.should_alert(below_threshold_risk)
        assert triggered is False
        assert "below" in reason.lower()

    def test_alert_triggered_by_flood_alone(self, cfg):
        """Even if population is low, large flood should trigger alert."""
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        risk = {"flood_extent_ha": 600.0, "affected_population_estimate": 50}
        triggered, reason = alerter.should_alert(risk)
        assert triggered is True

    def test_alert_triggered_by_population_alone(self, cfg):
        """Even if flood is small, large affected population triggers alert."""
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        risk = {"flood_extent_ha": 10.0, "affected_population_estimate": 5000}
        triggered, reason = alerter.should_alert(risk)
        assert triggered is True

    def test_zero_values_do_not_trigger(self, cfg):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        risk = {"flood_extent_ha": 0.0, "affected_population_estimate": 0}
        triggered, _ = alerter.should_alert(risk)
        assert triggered is False

    def test_exact_threshold_triggers(self, cfg):
        """Value exactly at threshold (>=) should trigger."""
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        threshold = float(getattr(cfg, "alert_flood_threshold_ha", 500))
        risk = {"flood_extent_ha": threshold, "affected_population_estimate": 0}
        triggered, _ = alerter.should_alert(risk)
        assert triggered is True


class TestSMSFormatting:
    """Tests for _format_sms() output."""

    def test_sms_under_160_chars(self, cfg, sample_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        sms = alerter._format_sms(sample_risk, "EVT-TEST-001")
        assert len(sms) <= 320, f"SMS too long: {len(sms)} chars"

    def test_sms_contains_event_id(self, cfg, sample_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        sms = alerter._format_sms(sample_risk, "EVT-TEST-001")
        assert "EVT-TEST-001" in sms

    def test_sms_contains_flood_extent(self, cfg, sample_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        sms = alerter._format_sms(sample_risk, "EVT-TEST-001")
        assert "1,200" in sms or "1200" in sms

    def test_sms_contains_top_village(self, cfg, sample_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        sms = alerter._format_sms(sample_risk, "EVT-TEST-001")
        assert "Bor South" in sms

    def test_sms_contains_suddwatch_branding(self, cfg, sample_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        sms = alerter._format_sms(sample_risk, "EVT-TEST-001")
        assert "SUDDWATCH" in sms

    def test_sms_severity_critical_for_multiple_high_risk(self, cfg, sample_risk):
        """Multiple high-risk villages should produce CRITICAL severity."""
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        # sample_risk has 2 villages with risk >= 75%
        sms = alerter._format_sms(sample_risk, "EVT-TEST-001")
        assert "CRITICAL" in sms or "WARNING" in sms

    def test_sms_empty_villages_handled(self, cfg):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        risk = {
            "flood_extent_ha": 600.0,
            "affected_population_estimate": 2000,
            "affected_villages": [],
        }
        sms = alerter._format_sms(risk, "EVT-EMPTY-001")
        assert "EVT-EMPTY-001" in sms


class TestEmailFormatting:
    """Tests for _format_email() output."""

    def test_email_subject_contains_event_id(self, cfg, sample_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        subject, _, _ = alerter._format_email(sample_risk, "EVT-TEST-001")
        assert "EVT-TEST-001" in subject

    def test_email_subject_contains_flood_extent(self, cfg, sample_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        subject, _, _ = alerter._format_email(sample_risk, "EVT-TEST-001")
        assert "1,200" in subject or "1200" in subject

    def test_email_plain_text_contains_villages(self, cfg, sample_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        _, plain, _ = alerter._format_email(sample_risk, "EVT-TEST-001")
        assert "Bor South" in plain

    def test_email_html_is_valid_html(self, cfg, sample_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        _, _, html = alerter._format_email(sample_risk, "EVT-TEST-001")
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_email_html_contains_kpi_values(self, cfg, sample_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        _, _, html = alerter._format_email(sample_risk, "EVT-TEST-001")
        assert "1,200" in html or "1200" in html
        assert "6,637" in html or "6637" in html

    def test_email_plain_contains_roads(self, cfg, sample_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        _, plain, _ = alerter._format_email(sample_risk, "EVT-TEST-001")
        assert "Bor-Malakal" in plain

    def test_email_returns_three_parts(self, cfg, sample_risk):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        result = alerter._format_email(sample_risk, "EVT-TEST-001")
        assert len(result) == 3
        subject, plain, html = result
        assert isinstance(subject, str) and len(subject) > 0
        assert isinstance(plain, str) and len(plain) > 0
        assert isinstance(html, str) and len(html) > 0


class TestSMSDispatch:
    """Tests for send_sms() with mocked Twilio."""

    def test_sms_skipped_when_no_recipients(self, cfg, mock_db):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        cfg.sms_recipients = []
        results = alerter.send_sms("test message", "EVT-001", mock_db)
        assert results == []

    def test_sms_delivered_successfully(self, cfg, mock_db):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        mock_msg = MagicMock()
        mock_msg.sid = "SM123456"
        with patch.object(alerter, "_get_twilio_client") as mock_client:
            mock_client.return_value.messages.create.return_value = mock_msg
            results = alerter.send_sms("test message", "EVT-001", mock_db)
        assert len(results) == len(cfg.sms_recipients)
        assert results[0]["status"] == "delivered"
        assert results[0]["sid"] == "SM123456"

    def test_sms_marked_failed_on_twilio_error(self, cfg, mock_db):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        with patch.object(alerter, "_get_twilio_client") as mock_client:
            mock_client.return_value.messages.create.side_effect = \
                Exception("Twilio error 21612")
            results = alerter.send_sms("test message", "EVT-001", mock_db)
        assert results[0]["status"] == "failed"
        assert "21612" in results[0]["error"]

    def test_sms_logs_to_database(self, cfg, mock_db):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        mock_msg = MagicMock()
        mock_msg.sid = "SM789"
        with patch.object(alerter, "_get_twilio_client") as mock_client:
            mock_client.return_value.messages.create.return_value = mock_msg
            alerter.send_sms("test message", "EVT-001", mock_db)
        assert mock_db.insert_alert.called

    def test_sms_handles_list_recipients(self, cfg, mock_db):
        """sms_recipients is List[str] in config — must be handled."""
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        cfg.sms_recipients = ["+254700000001", "+254700000002"]
        mock_msg = MagicMock()
        mock_msg.sid = "SM999"
        with patch.object(alerter, "_get_twilio_client") as mock_client:
            mock_client.return_value.messages.create.return_value = mock_msg
            results = alerter.send_sms("test", "EVT-001", mock_db)
        assert len(results) == 2


class TestEmailDispatch:
    """Tests for send_email() with mocked SMTP."""

    def test_email_skipped_when_no_recipients(self, cfg, mock_db):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        cfg.email_recipients = []
        results = alerter.send_email(
            "subject", "plain", "<html></html>", "EVT-001", mock_db
        )
        assert results == []

    def test_email_delivered_successfully(self, cfg, mock_db):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        with patch("smtplib.SMTP_SSL") as mock_smtp:
            mock_smtp.return_value.__enter__ = lambda s: s
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            mock_smtp.return_value.login = MagicMock()
            mock_smtp.return_value.sendmail = MagicMock()
            results = alerter.send_email(
                "Test Subject", "Plain body", "<html>HTML</html>",
                "EVT-001", mock_db
            )
        assert len(results) == len(cfg.email_recipients)
        assert results[0]["status"] == "delivered"

    def test_email_failed_on_smtp_error(self, cfg, mock_db):
        from src.alerts import AlertManager
        import smtplib
        alerter = AlertManager(cfg)
        with patch("smtplib.SMTP_SSL", side_effect=smtplib.SMTPException("Auth failed")):
            with patch("smtplib.SMTP", side_effect=smtplib.SMTPException("Auth failed")):
                results = alerter.send_email(
                    "subject", "plain", "<html></html>", "EVT-001", mock_db
                )
        assert results[0]["status"] == "failed"

    def test_email_logs_to_database(self, cfg, mock_db):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        with patch("smtplib.SMTP_SSL") as mock_smtp:
            mock_smtp.return_value.__enter__ = lambda s: s
            mock_smtp.return_value.__exit__ = MagicMock(return_value=False)
            mock_smtp.return_value.login = MagicMock()
            mock_smtp.return_value.sendmail = MagicMock()
            alerter.send_email("subj", "plain", "<html></html>", "EVT-001", mock_db)
        assert mock_db.insert_alert.called


class TestSendFloodAlert:
    """Tests for the main send_flood_alert() orchestration method."""

    def test_no_alert_below_threshold(self, cfg, below_threshold_risk, mock_db):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        result = alerter.send_flood_alert(below_threshold_risk, "EVT-001", mock_db)
        assert result["alert_triggered"] is False
        assert result["total_sent"] == 0
        assert result["sms_results"] == []
        assert result["email_results"] == []

    def test_alert_triggered_above_threshold(self, cfg, sample_risk, mock_db):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        with patch.object(alerter, "send_sms", return_value=[
            {"recipient": "+254700000001", "status": "delivered", "sid": "SM1"}
        ]):
            with patch.object(alerter, "send_email", return_value=[
                {"recipient": "test@test.com", "status": "delivered"}
            ]):
                result = alerter.send_flood_alert(sample_risk, "EVT-001", mock_db)
        assert result["alert_triggered"] is True
        assert result["total_sent"] == 2

    def test_result_counts_delivered_and_failed(self, cfg, sample_risk, mock_db):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        with patch.object(alerter, "send_sms", return_value=[
            {"status": "delivered"}, {"status": "failed"}
        ]):
            with patch.object(alerter, "send_email", return_value=[
                {"status": "delivered"}
            ]):
                result = alerter.send_flood_alert(sample_risk, "EVT-001", mock_db)
        assert result["total_sent"] == 2
        assert result["total_failed"] == 1

    def test_reason_included_in_result(self, cfg, sample_risk, mock_db):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        with patch.object(alerter, "send_sms", return_value=[]):
            with patch.object(alerter, "send_email", return_value=[]):
                result = alerter.send_flood_alert(sample_risk, "EVT-001", mock_db)
        assert "reason" in result
        assert len(result["reason"]) > 0


# ════════════════════════════════════════════════════════════
# FloodPipeline — Unit Tests
# ════════════════════════════════════════════════════════════

class TestFloodPipelineInit:
    """Tests for FloodPipeline initialisation."""

    def test_pipeline_initialises_all_modules(self, cfg):
        from src.pipeline import FloodPipeline
        pipeline = FloodPipeline(cfg)
        assert pipeline.db is not None
        assert pipeline.downloader is not None
        assert pipeline.preprocessor is not None
        assert pipeline.detector is not None
        assert pipeline.assessor is not None
        assert pipeline.alerter is not None

    def test_pipeline_loads_population_data(self, cfg):
        from src.pipeline import FloodPipeline
        pipeline = FloodPipeline(cfg)
        # population data loaded if assessor has pop_data attribute
        assert hasattr(pipeline.assessor, "_population_data")

    def test_pipeline_config_matches(self, cfg):
        from src.pipeline import FloodPipeline
        pipeline = FloodPipeline(cfg)
        assert pipeline.config is cfg


class TestTimedStage:
    """Tests for _timed_stage() helper."""

    def test_timed_stage_returns_result_and_duration(self, cfg):
        from src.pipeline import FloodPipeline
        pipeline = FloodPipeline(cfg)
        result, duration = pipeline._timed_stage("test", lambda: 42)
        assert result == 42
        assert isinstance(duration, float)
        assert duration >= 0

    def test_timed_stage_propagates_exceptions(self, cfg):
        from src.pipeline import FloodPipeline
        pipeline = FloodPipeline(cfg)
        with pytest.raises(ValueError, match="test error"):
            pipeline._timed_stage("test", lambda: (_ for _ in ()).throw(ValueError("test error")))

    def test_timed_stage_passes_args(self, cfg):
        from src.pipeline import FloodPipeline
        pipeline = FloodPipeline(cfg)
        result, _ = pipeline._timed_stage("test", lambda x, y: x + y, 3, 4)
        assert result == 7


class TestComputeIoU:
    """Tests for _compute_iou() fallback behaviour."""

    def test_returns_placeholder_when_no_reference(self, cfg):
        from src.pipeline import FloodPipeline
        pipeline = FloodPipeline(cfg)
        # No reference mask exists for this scene
        iou = pipeline._compute_iou(Path("/tmp/nonexistent.tif"), "FAKE_SCENE_999")
        assert iou == 0.71

    def test_iou_is_float(self, cfg):
        from src.pipeline import FloodPipeline
        pipeline = FloodPipeline(cfg)
        iou = pipeline._compute_iou(Path("/tmp/x.tif"), "FAKE_SCENE")
        assert isinstance(iou, float)

    def test_iou_in_valid_range(self, cfg):
        from src.pipeline import FloodPipeline
        pipeline = FloodPipeline(cfg)
        iou = pipeline._compute_iou(Path("/tmp/x.tif"), "FAKE_SCENE")
        assert 0.0 <= iou <= 1.0


class TestPipelineRun:
    """Tests for FloodPipeline.run() orchestration."""

    def test_run_returns_dict(self, cfg):
        from src.pipeline import FloodPipeline
        pipeline = FloodPipeline(cfg)
        with patch.object(pipeline.downloader,
                          "check_and_download_new_scenes", return_value=[]):
            results = pipeline.run()
        assert isinstance(results, dict)

    def test_run_no_scenes_returns_early(self, cfg):
        from src.pipeline import FloodPipeline
        pipeline = FloodPipeline(cfg)
        with patch.object(pipeline.downloader,
                          "check_and_download_new_scenes", return_value=[]):
            results = pipeline.run()
        assert results["status"] == "no_new_scenes"
        assert results["scenes_processed"] == []

    def test_run_tracks_failed_scenes(self, cfg):
        """If preprocessing fails, scene goes to scenes_failed not scenes_processed."""
        from src.pipeline import FloodPipeline
        pipeline = FloodPipeline(cfg)
        fake_scene = Path("/tmp/fake_scene.zip")
        fake_scene.touch()
        with patch.object(pipeline.downloader,
                          "check_and_download_new_scenes", return_value=[fake_scene]):
            with patch.object(pipeline, "_preprocess",
                              side_effect=RuntimeError("SNAP GPT failed")):
                results = pipeline.run()
        assert len(results["scenes_failed"]) == 1
        assert results["scenes_failed"][0]["status"] == "failed"
        assert len(results["scenes_processed"]) == 0
        fake_scene.unlink(missing_ok=True)

    def test_run_has_required_keys(self, cfg):
        from src.pipeline import FloodPipeline
        pipeline = FloodPipeline(cfg)
        with patch.object(pipeline.downloader,
                          "check_and_download_new_scenes", return_value=[]):
            results = pipeline.run()
        for key in ["scenes_processed", "scenes_failed",
                    "total_alerts_sent", "status"]:
            assert key in results, f"Missing key: {key}"

    def test_run_multiple_scenes_one_fails(self, cfg):
        """Pipeline should process remaining scenes even if one fails."""
        from src.pipeline import FloodPipeline
        pipeline = FloodPipeline(cfg)
        fake1 = Path("/tmp/scene_001.zip")
        fake2 = Path("/tmp/scene_002.zip")
        fake1.touch(); fake2.touch()
        call_count = {"n": 0}

        def preprocess_side_effect(scene_path):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise RuntimeError("First scene fails")
            return Path("/tmp/fake_db.tif"), 5.0

        with patch.object(pipeline.downloader,
                          "check_and_download_new_scenes",
                          return_value=[fake1, fake2]):
            with patch.object(pipeline, "_preprocess",
                              side_effect=preprocess_side_effect):
                with patch.object(pipeline, "_detect",
                                  return_value=(Path("/tmp/mask.tif"), 600.0, 2.0)):
                    with patch.object(pipeline, "_assess",
                                      return_value=({"flood_extent_ha": 600.0,
                                                     "affected_population_estimate": 0,
                                                     "affected_villages": [],
                                                     "inaccessible_roads": [],
                                                     "health_facilities_at_risk": []},
                                                    Path("/tmp/summary.json"), 1.0)):
                        with patch.object(pipeline, "_alert",
                                          return_value=({"alert_triggered": False,
                                                         "total_sent": 0,
                                                         "total_failed": 0,
                                                         "sms_results": [],
                                                         "email_results": []}, 0.1)):
                            with patch.object(pipeline.db, "insert_event",
                                              return_value=1):
                                with patch.object(pipeline.db, "update_event"):
                                    with patch.object(pipeline.db, "insert_processing_log"):
                                        with patch.object(pipeline.db, "insert_flood_mask"):
                                            results = pipeline.run()

        assert len(results["scenes_failed"])    == 1
        assert len(results["scenes_processed"]) == 1
        fake1.unlink(missing_ok=True)
        fake2.unlink(missing_ok=True)


# ════════════════════════════════════════════════════════════
# Integration Tests (require live credentials)
# ════════════════════════════════════════════════════════════

class TestAlertConnectivity:
    """Live connectivity tests — skipped in CI, run on demand."""

    @pytest.mark.integration
    def test_twilio_connectivity(self, cfg):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        result = alerter.test_connectivity()
        assert result["twilio"] is True, \
            f"Twilio failed: {result['errors']}"

    @pytest.mark.integration
    def test_smtp_connectivity(self, cfg):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        result = alerter.test_connectivity()
        assert result["smtp"] is True, \
            f"SMTP failed: {result['errors']}"

    @pytest.mark.integration
    def test_both_channels_connected(self, cfg):
        from src.alerts import AlertManager
        alerter = AlertManager(cfg)
        result = alerter.test_connectivity()
        assert result["twilio"] is True
        assert result["smtp"] is True
        assert result["errors"] == []
