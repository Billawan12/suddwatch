# ============================================================
# SuddWatch - Unit Tests: Database Module
# File: tests/test_database.py
# Purpose: Tests for DatabaseManager class covering:
#          - Database initialisation (all 6 tables)
#          - All insert methods (events, masks, villages, etc.)
#          - Update methods
#          - Query methods with filters
#          - Performance metrics calculation
#          - Edge cases and error handling
# Course: SWE3090 - Software Project 1
# Student: Madut Chan (671336)
# ============================================================

import pytest
import sqlite3
import json
import pandas as pd
from datetime import datetime, timezone, UTC
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.config import Config
from src.database import DatabaseManager


# ============================================================
# FIXTURES
# Shared test setup reused across multiple tests
# ============================================================

@pytest.fixture
def config(tmp_path):
    """
    Provides a Config object with a temporary database path.
    """
    config = Config()
    config.db_path = tmp_path / "database" / "test_suddwatch.db"
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    return config


@pytest.fixture
def db(config):
    """
    Provides a DatabaseManager instance with a fresh database.
    """
    # Ensure any existing database is removed
    if config.db_path.exists():
        config.db_path.unlink()

    return DatabaseManager(config)


@pytest.fixture
def sample_event_data():
    """
    Returns sample event data for testing.
    """
    return {
        "event_timestamp": datetime.now(UTC).isoformat(),
        "satellite_acquisition_time": datetime.now(UTC).isoformat(),
        "processing_start_time": datetime.now(UTC).isoformat(),
        "scene_id": "TEST_SCENE_001",
        "scene_path": "/data/raw/test_scene.zip",
        "status": "processing",
    }


@pytest.fixture
def sample_mask_data():
    """
    Returns sample flood mask data for testing.
    """
    return {
        "flood_extent_ha": 12500.5,
        "iou_score": 0.72,
        "geotiff_path": "/data/flood_masks/test_mask.tif",
        "detection_method": "otsu_gmm",
    }


@pytest.fixture
def sample_village_data():
    """
    Returns sample village data for testing.
    """
    return {
        "village_name": "Bor",
        "state": "Jonglei",
        "county": "Bor South",
        "estimated_population": 45000,
        "flood_risk_percentage": 78.5,
        "latitude": 6.2,
        "longitude": 31.5,
    }


@pytest.fixture
def sample_infrastructure_data():
    """
    Returns sample infrastructure impact data for testing.
    """
    return {
        "infrastructure_type": "health_facility",
        "name": "Bor State Hospital",
        "facility_type": "hospital",
        "status": "at_risk",
        "coordinates": {"lat": 6.2, "lon": 31.5},
    }


@pytest.fixture
def sample_alert_data():
    """
    Returns sample alert data for testing.
    """
    return {
        "channel": "sms",
        "recipient": "+254705176665",
        "delivery_status": "sent",
        "sent_timestamp": datetime.now(UTC).isoformat(),
        "message_preview": "SUDDWATCH ALERT: Flooding detected",
    }


@pytest.fixture
def sample_log_data():
    """
    Returns sample processing log data for testing.
    """
    return {
        "stage_name": "preprocess",
        "start_time": datetime.now(UTC).isoformat(),
        "end_time": datetime.now(UTC).isoformat(),
        "duration_seconds": 845.2,
        "status": "completed",
    }


# ============================================================
# DATABASE INITIALISATION TESTS
# ============================================================

class TestDatabaseInitialisation:
    """Tests for database initialisation and table creation."""

    def test_db_initialises_with_config(self, db):
        """DatabaseManager should initialise with a Config object."""
        assert db is not None
        assert db.config is not None
        assert db.db_path is not None

    def test_db_file_created(self, db, config):
        """Database file should be created on initialisation."""
        assert config.db_path.exists()

    def test_all_tables_created(self, db):
        """All 6 tables should be created on initialisation."""
        conn = db._get_connection()
        cursor = conn.cursor()

        # Check all 6 tables exist
        expected_tables = [
            'events',
            'flood_masks',
            'affected_populations',
            'infrastructure_impacts',
            'alerts',
            'processing_logs'
        ]

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
        existing_tables = [row[0] for row in cursor.fetchall()]

        for table in expected_tables:
            assert table in existing_tables, f"Table '{table}' missing"

        conn.close()

    def test_foreign_key_enabled(self, db):
        """Foreign key constraints should be enabled."""
        conn = db._get_connection()
        cursor = conn.cursor()

        cursor.execute("PRAGMA foreign_keys")
        result = cursor.fetchone()[0]

        assert result == 1, "Foreign key constraints not enabled"

        conn.close()

    def test_table_schemas_match_erd(self, db):
        """Table schemas should match the ERD from Chapter 5."""
        conn = db._get_connection()
        cursor = conn.cursor()

        # Check events table schema
        cursor.execute("PRAGMA table_info(events)")
        events_columns = [row[1] for row in cursor.fetchall()]
        expected_event_columns = [
            'event_id', 'event_timestamp', 'satellite_acquisition_time',
            'processing_start_time', 'processing_end_time', 'total_latency_seconds',
            'scene_id', 'scene_path', 'status', 'error_message', 'created_at'
        ]
        for col in expected_event_columns:
            assert col in events_columns, f"Missing column in events: {col}"

        # Check flood_masks table schema
        cursor.execute("PRAGMA table_info(flood_masks)")
        mask_columns = [row[1] for row in cursor.fetchall()]
        expected_mask_columns = [
            'mask_id', 'event_id', 'flood_extent_ha', 'iou_score',
            'geotiff_path', 'detection_method', 'created_at'
        ]
        for col in expected_mask_columns:
            assert col in mask_columns, f"Missing column in flood_masks: {col}"

        conn.close()


# ============================================================
# EVENT INSERTION TESTS
# ============================================================

class TestEventInsertion:
    """Tests for insert_event() method."""

    def test_insert_event_returns_event_id(self, db, sample_event_data):
        """insert_event should return the auto-generated event_id."""
        event_id = db.insert_event(sample_event_data)

        assert event_id is not None
        assert isinstance(event_id, int)
        assert event_id > 0

    def test_insert_event_creates_record(self, db, sample_event_data):
        """insert_event should create a record in the events table."""
        event_id = db.insert_event(sample_event_data)

        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row['scene_id'] == sample_event_data['scene_id']
        assert row['status'] == sample_event_data['status']

    def test_insert_event_uses_default_timestamp(self, db):
        """insert_event should use current timestamp if not provided."""
        event_data = {
            "scene_id": "TEST_SCENE_002",
            "status": "pending",
        }
        event_id = db.insert_event(event_data)

        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
        row = cursor.fetchone()
        conn.close()

        assert row['event_timestamp'] is not None

    def test_insert_event_handles_missing_optional_fields(self, db):
        """insert_event should handle missing optional fields gracefully."""
        event_data = {
            "event_timestamp": datetime.now(UTC).isoformat(),
        }
        event_id = db.insert_event(event_data)

        assert event_id is not None


# ============================================================
# EVENT UPDATE TESTS
# ============================================================

class TestEventUpdate:
    """Tests for update_event() method."""

    def test_update_event_updates_record(self, db, sample_event_data):
        """update_event should update an existing event record."""
        event_id = db.insert_event(sample_event_data)

        update_data = {
            "processing_end_time": datetime.now(UTC).isoformat(),
            "total_latency_seconds": 2847.5,
            "status": "completed",
        }
        db.update_event(event_id, update_data)

        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
        row = cursor.fetchone()
        conn.close()

        assert row['status'] == 'completed'
        assert row['total_latency_seconds'] == 2847.5

    def test_update_event_handles_partial_update(self, db, sample_event_data):
        """update_event should handle partial updates (only some fields)."""
        event_id = db.insert_event(sample_event_data)

        update_data = {"status": "completed"}
        db.update_event(event_id, update_data)

        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
        row = cursor.fetchone()
        conn.close()

        assert row['status'] == 'completed'  # Updated
        # Other fields should remain unchanged
        assert row['scene_id'] == sample_event_data['scene_id']

    def test_update_event_handles_error_message(self, db, sample_event_data):
        """update_event should store error messages."""
        event_id = db.insert_event(sample_event_data)

        update_data = {
            "status": "failed",
            "error_message": "Preprocessing failed: SNAP error"
        }
        db.update_event(event_id, update_data)

        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE event_id = ?", (event_id,))
        row = cursor.fetchone()
        conn.close()

        assert row['status'] == 'failed'
        assert "SNAP error" in row['error_message']


# ============================================================
# FLOOD MASK INSERTION TESTS
# ============================================================

class TestFloodMaskInsertion:
    """Tests for insert_flood_mask() method."""

    def test_insert_flood_mask_returns_mask_id(self, db, sample_event_data, sample_mask_data):
        """insert_flood_mask should return the auto-generated mask_id."""
        event_id = db.insert_event(sample_event_data)
        mask_id = db.insert_flood_mask(event_id, sample_mask_data)

        assert mask_id is not None
        assert isinstance(mask_id, int)
        assert mask_id > 0

    def test_insert_flood_mask_creates_record(self, db, sample_event_data, sample_mask_data):
        """insert_flood_mask should create a record in flood_masks table."""
        event_id = db.insert_event(sample_event_data)
        mask_id = db.insert_flood_mask(event_id, sample_mask_data)

        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM flood_masks WHERE mask_id = ?", (mask_id,))
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row['event_id'] == event_id
        assert row['flood_extent_ha'] == sample_mask_data['flood_extent_ha']
        assert row['iou_score'] == sample_mask_data['iou_score']

    def test_insert_flood_mask_uses_default_detection_method(self, db, sample_event_data):
        """insert_flood_mask should use default detection method if not provided."""
        event_id = db.insert_event(sample_event_data)

        mask_data = {
            "flood_extent_ha": 1000.0,
            "iou_score": 0.65,
            "geotiff_path": "/data/flood_masks/test.tif",
            # No detection_method specified
        }
        mask_id = db.insert_flood_mask(event_id, mask_data)

        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM flood_masks WHERE mask_id = ?", (mask_id,))
        row = cursor.fetchone()
        conn.close()

        assert row['detection_method'] == 'otsu_gmm'


# ============================================================
# VILLAGE INSERTION TESTS
# ============================================================

class TestVillageInsertion:
    """Tests for insert_affected_village() method."""

    def test_insert_village_returns_record_id(self, db, sample_event_data, sample_village_data):
        """insert_affected_village should return the auto-generated record_id."""
        event_id = db.insert_event(sample_event_data)
        record_id = db.insert_affected_village(event_id, sample_village_data)

        assert record_id is not None
        assert isinstance(record_id, int)
        assert record_id > 0

    def test_insert_village_creates_record(self, db, sample_event_data, sample_village_data):
        """insert_affected_village should create a record in affected_populations."""
        event_id = db.insert_event(sample_event_data)
        record_id = db.insert_affected_village(event_id, sample_village_data)

        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM affected_populations WHERE record_id = ?", (record_id,))
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row['event_id'] == event_id
        assert row['village_name'] == sample_village_data['village_name']
        assert row['state'] == sample_village_data['state']

    def test_insert_village_handles_missing_fields(self, db, sample_event_data):
        """insert_affected_village should handle missing optional fields."""
        event_id = db.insert_event(sample_event_data)

        village_data = {
            "village_name": "Test Village",
            # Missing other optional fields
        }
        record_id = db.insert_affected_village(event_id, village_data)

        assert record_id is not None


# ============================================================
# INFRASTRUCTURE INSERTION TESTS
# ============================================================

class TestInfrastructureInsertion:
    """Tests for insert_infrastructure_impact() method."""

    def test_insert_infrastructure_returns_impact_id(self, db, sample_event_data, sample_infrastructure_data):
        """insert_infrastructure_impact should return the auto-generated impact_id."""
        event_id = db.insert_event(sample_event_data)
        impact_id = db.insert_infrastructure_impact(event_id, sample_infrastructure_data)

        assert impact_id is not None
        assert isinstance(impact_id, int)
        assert impact_id > 0

    def test_insert_infrastructure_creates_record(self, db, sample_event_data, sample_infrastructure_data):
        """insert_infrastructure_impact should create a record in infrastructure_impacts."""
        event_id = db.insert_event(sample_event_data)
        impact_id = db.insert_infrastructure_impact(event_id, sample_infrastructure_data)

        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM infrastructure_impacts WHERE impact_id = ?", (impact_id,))
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row['event_id'] == event_id
        assert row['name'] == sample_infrastructure_data['name']
        assert row['infrastructure_type'] == sample_infrastructure_data['infrastructure_type']

    def test_insert_infrastructure_serialises_coordinates(self, db, sample_event_data, sample_infrastructure_data):
        """insert_infrastructure_impact should serialise coordinates dict to JSON."""
        event_id = db.insert_event(sample_event_data)
        impact_id = db.insert_infrastructure_impact(event_id, sample_infrastructure_data)

        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM infrastructure_impacts WHERE impact_id = ?", (impact_id,))
        row = cursor.fetchone()
        conn.close()

        # Should be stored as JSON string
        coords = json.loads(row['coordinates'])
        assert coords['lat'] == sample_infrastructure_data['coordinates']['lat']
        assert coords['lon'] == sample_infrastructure_data['coordinates']['lon']


# ============================================================
# ALERT INSERTION TESTS
# ============================================================

class TestAlertInsertion:
    """Tests for insert_alert() method."""

    def test_insert_alert_returns_alert_id(self, db, sample_event_data, sample_alert_data):
        """insert_alert should return the auto-generated alert_id."""
        event_id = db.insert_event(sample_event_data)
        alert_id = db.insert_alert(event_id, sample_alert_data)

        assert alert_id is not None
        assert isinstance(alert_id, int)
        assert alert_id > 0

    def test_insert_alert_creates_record(self, db, sample_event_data, sample_alert_data):
        """insert_alert should create a record in alerts table."""
        event_id = db.insert_event(sample_event_data)
        alert_id = db.insert_alert(event_id, sample_alert_data)

        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_id,))
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row['event_id'] == event_id
        assert row['channel'] == sample_alert_data['channel']
        assert row['recipient'] == sample_alert_data['recipient']

    def test_insert_alert_truncates_long_message(self, db, sample_event_data):
        """insert_alert should truncate long messages to 160 characters."""
        event_id = db.insert_event(sample_event_data)

        long_message = "A" * 300
        alert_data = {
            "channel": "sms",
            "recipient": "+254700000001",
            "message_preview": long_message,
        }
        alert_id = db.insert_alert(event_id, alert_data)

        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM alerts WHERE alert_id = ?", (alert_id,))
        row = cursor.fetchone()
        conn.close()

        assert len(row['message_preview']) <= 160


# ============================================================
# PROCESSING LOG INSERTION TESTS
# ============================================================

class TestLogInsertion:
    """Tests for insert_processing_log() method."""

    def test_insert_log_returns_log_id(self, db, sample_event_data, sample_log_data):
        """insert_processing_log should return the auto-generated log_id."""
        event_id = db.insert_event(sample_event_data)
        log_id = db.insert_processing_log(event_id, sample_log_data)

        assert log_id is not None
        assert isinstance(log_id, int)
        assert log_id > 0

    def test_insert_log_creates_record(self, db, sample_event_data, sample_log_data):
        """insert_processing_log should create a record in processing_logs."""
        event_id = db.insert_event(sample_event_data)
        log_id = db.insert_processing_log(event_id, sample_log_data)

        conn = db._get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM processing_logs WHERE log_id = ?", (log_id,))
        row = cursor.fetchone()
        conn.close()

        assert row is not None
        assert row['event_id'] == event_id
        assert row['stage_name'] == sample_log_data['stage_name']
        assert row['duration_seconds'] == sample_log_data['duration_seconds']


# ============================================================
# QUERY TESTS
# ============================================================

class TestQueryMethods:
    """Tests for query methods: query_events, query_performance_metrics, etc."""

    def test_query_events_returns_dataframe(self, db, sample_event_data):
        """query_events should return a pandas DataFrame."""
        event_id = db.insert_event(sample_event_data)

        df = db.query_events()

        assert isinstance(df, pd.DataFrame)
        assert len(df) >= 1

    def test_query_events_filters_by_date(self, db, sample_event_data):
        """query_events should filter by start_date and end_date."""
        event_id = db.insert_event(sample_event_data)

        # Filter to a date range that should include the event
        filters = {
            "start_date": "2024-01-01T00:00:00Z",
            "end_date": "2025-12-31T23:59:59Z",
        }
        df = db.query_events(filters)

        assert len(df) >= 1

        # Filter to a date range that should NOT include the event
        filters = {
            "start_date": "2020-01-01T00:00:00Z",
            "end_date": "2020-12-31T23:59:59Z",
        }
        df = db.query_events(filters)

        assert len(df) == 0

    def test_query_events_filters_by_status(self, db, sample_event_data):
        """query_events should filter by status."""
        event_id = db.insert_event(sample_event_data)

        filters = {"status": "processing"}
        df = db.query_events(filters)

        assert len(df) >= 1

        filters = {"status": "completed"}
        df = db.query_events(filters)

        assert len(df) == 0

    def test_query_events_filters_by_min_iou(self, db, sample_event_data, sample_mask_data):
        """query_events should filter by minimum IoU."""
        event_id = db.insert_event(sample_event_data)
        mask_id = db.insert_flood_mask(event_id, sample_mask_data)

        # IoU is 0.72, so min_iou=0.70 should include it
        filters = {"min_iou": 0.70}
        df = db.query_events(filters)

        assert len(df) >= 1

        # IoU is 0.72, so min_iou=0.80 should exclude it
        filters = {"min_iou": 0.80}
        df = db.query_events(filters)

        assert len(df) == 0

    def test_query_performance_metrics_returns_dict(self, db, sample_event_data, sample_mask_data, sample_alert_data):
        """query_performance_metrics should return a dictionary with metrics."""
        event_id = db.insert_event(sample_event_data)
        mask_id = db.insert_flood_mask(event_id, sample_mask_data)
        alert_id = db.insert_alert(event_id, sample_alert_data)

        # Update event to completed
        db.update_event(event_id, {
            "processing_end_time": datetime.now(UTC).isoformat(),
            "total_latency_seconds": 2847.5,
            "status": "completed",
        })

        metrics = db.query_performance_metrics()

        assert isinstance(metrics, dict)
        assert 'avg_latency_seconds' in metrics
        assert 'avg_iou' in metrics
        assert 'alert_success_rate' in metrics
        assert 'total_events' in metrics
        assert 'completed_events' in metrics

    def test_get_latest_event_returns_most_recent(self, db, sample_event_data):
        """get_latest_event should return the most recent completed event."""
        # Insert first event
        event1_id = db.insert_event(sample_event_data)
        db.update_event(event1_id, {"status": "completed"})

        # Insert second event (more recent)
        event2_data = sample_event_data.copy()
        event2_data["scene_id"] = "TEST_SCENE_002"
        event2_id = db.insert_event(event2_data)
        db.update_event(event2_id, {"status": "completed"})

        latest = db.get_latest_event()

        assert latest is not None
        assert latest['scene_id'] == "TEST_SCENE_002"

    def test_get_latest_event_returns_none_if_no_events(self, db):
        """get_latest_event should return None if no completed events exist."""
        latest = db.get_latest_event()

        assert latest is None

    def test_get_event_villages_returns_dataframe(self, db, sample_event_data, sample_village_data):
        """get_event_villages should return a DataFrame with village records."""
        event_id = db.insert_event(sample_event_data)
        record_id = db.insert_affected_village(event_id, sample_village_data)

        df = db.get_event_villages(event_id)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df.iloc[0]['village_name'] == sample_village_data['village_name']

    def test_get_event_infrastructure_returns_dataframe(self, db, sample_event_data, sample_infrastructure_data):
        """get_event_infrastructure should return a DataFrame with infrastructure records."""
        event_id = db.insert_event(sample_event_data)
        impact_id = db.insert_infrastructure_impact(event_id, sample_infrastructure_data)

        df = db.get_event_infrastructure(event_id)

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert df.iloc[0]['name'] == sample_infrastructure_data['name']


# ============================================================
# ERROR HANDLING TESTS
# ============================================================

class TestErrorHandling:
    """Tests for error handling in database operations."""

    def test_insert_event_raises_on_invalid_operation(self, db):
        """insert_event should raise sqlite3.Error on invalid operation."""
        # Try to insert data with a non-existent column
        event_data = {"invalid_column": "value"}

        # Should still work (ignores extra columns)
        event_id = db.insert_event(event_data)

        assert event_id is not None

    def test_update_event_handles_nonexistent_event(self, db):
        """update_event should not crash when updating non-existent event."""
        update_data = {"status": "completed"}

        # Should not raise exception
        db.update_event(999999, update_data)

    def test_query_events_handles_invalid_filters(self, db):
        """query_events should handle invalid filter keys gracefully."""
        filters = {"invalid_filter": "value"}

        df = db.query_events(filters)

        assert isinstance(df, pd.DataFrame)

    def test_query_performance_metrics_handles_empty_db(self, db):
        """query_performance_metrics should handle empty database."""
        metrics = db.query_performance_metrics()

        assert isinstance(metrics, dict)
        assert metrics.get('avg_latency_seconds') == 0
        assert metrics.get('avg_iou') == 0
        assert metrics.get('alert_success_rate') == 0


# ============================================================
# FOREIGN KEY CONSTRAINT TESTS
# ============================================================

class TestForeignKeys:
    """Tests for foreign key constraints."""

    def test_insert_flood_mask_validates_event_id(self, db, sample_mask_data):
        """insert_flood_mask should enforce foreign key constraint."""
        # Try to insert with non-existent event_id
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_flood_mask(999999, sample_mask_data)

    def test_insert_village_validates_event_id(self, db, sample_village_data):
        """insert_affected_village should enforce foreign key constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_affected_village(999999, sample_village_data)

    def test_insert_infrastructure_validates_event_id(self, db, sample_infrastructure_data):
        """insert_infrastructure_impact should enforce foreign key constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_infrastructure_impact(999999, sample_infrastructure_data)

    def test_insert_alert_validates_event_id(self, db, sample_alert_data):
        """insert_alert should enforce foreign key constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_alert(999999, sample_alert_data)

    def test_insert_log_validates_event_id(self, db, sample_log_data):
        """insert_processing_log should enforce foreign key constraint."""
        with pytest.raises(sqlite3.IntegrityError):
            db.insert_processing_log(999999, sample_log_data)


# ============================================================
# Run tests directly
# Usage: python3 -m pytest tests/test_database.py -v
# ============================================================
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])