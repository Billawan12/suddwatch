# ============================================================
# SuddWatch - Database Management Module
# File: src/database.py
# Purpose: Creates and manages the SQLite database with all
#          6 tables from the proposal ERD. Handles all
#          insert, update, and query operations for the
#          entire pipeline.
# Course: SWE3090 - Software Project 1
# Student: Madut Chan (671336)
# ============================================================

import sqlite3
import json
import logging
from datetime import datetime, timezone, UTC
from pathlib import Path
from typing import Optional, Dict, List
import pandas as pd

from src.config import Config

# --- Module logger ---
# Inherits handlers set up by setup_logging() in config.py
logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Manages all SQLite database operations for SuddWatch.

    Creates 6 tables matching the proposal ERD:
    - events: one record per Sentinel-1 scene processed
    - flood_masks: flood extent results per event
    - affected_populations: villages and population estimates per event
    - infrastructure_impacts: roads and health facilities at risk per event
    - alerts: SMS and email alert delivery records per event
    - processing_logs: stage-by-stage timing and status per event

    All insert methods use parameterised queries to prevent SQL injection.
    All operations are wrapped in try-except for graceful error handling.

    Example usage:
        from src.config import Config
        from src.database import DatabaseManager
        config = Config()
        db = DatabaseManager(config)
        event_id = db.insert_event({...})
    """

    def __init__(self, config: Config):
        """
        Initialises the database manager and creates all tables.

        Args:
            config: Config object containing db_path and other settings
        """
        # Store config reference for path access
        self.config = config

        # Ensure the database directory exists before connecting
        config.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Store path as string for sqlite3 compatibility
        self.db_path = str(config.db_path)

        # Create all 6 tables on first run (safe to call repeatedly)
        self._init_database()

        logger.info(f"DatabaseManager initialised. DB path: {self.db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """
        Creates and returns a new SQLite connection.

        Uses row_factory so results are accessible by column name
        e.g. row['event_id'] instead of row[0].

        Returns:
            sqlite3.Connection with row_factory set
        """
        # Connect to the SQLite database file
        conn = sqlite3.connect(self.db_path)

        # Enable column-name access on result rows
        conn.row_factory = sqlite3.Row

        # Enable foreign key enforcement (off by default in SQLite)
        conn.execute("PRAGMA foreign_keys = ON")

        return conn

    def _init_database(self) -> None:
        """
        Creates all 6 tables if they don't already exist.

        Uses IF NOT EXISTS so this is safe to call on every startup
        without wiping existing data.

        Tables match the ERD from Chapter 5 of the proposal document.
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # ------------------------------------------------
            # Table 1: events
            # One record per Sentinel-1 scene processed.
            # Central table — all other tables foreign-key to this.
            # ------------------------------------------------
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS events (
                    event_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_timestamp           TEXT NOT NULL,
                    satellite_acquisition_time TEXT,
                    processing_start_time     TEXT,
                    processing_end_time       TEXT,
                    total_latency_seconds     REAL,
                    scene_id                  TEXT,
                    scene_path                TEXT,
                    status                    TEXT DEFAULT 'pending',
                    error_message             TEXT,
                    created_at                TEXT DEFAULT (datetime('now'))
                )
            """)
            # status values: 'pending', 'processing', 'completed', 'failed'
            logger.debug("Table 'events' ready.")

            # ------------------------------------------------
            # Table 2: flood_masks
            # Flood detection results for each event.
            # Stores the flood extent and accuracy metric (IoU).
            # ------------------------------------------------
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS flood_masks (
                    mask_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id         INTEGER NOT NULL,
                    flood_extent_ha  REAL,
                    iou_score        REAL,
                    geotiff_path     TEXT,
                    detection_method TEXT DEFAULT 'otsu_gmm',
                    created_at       TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (event_id) REFERENCES events(event_id)
                )
            """)
            # detection_method: 'otsu_gmm' (primary) or 'random_forest' (ML)
            logger.debug("Table 'flood_masks' ready.")

            # ------------------------------------------------
            # Table 3: affected_populations
            # Villages and estimated population at risk per event.
            # One row per village found within flood extent.
            # ------------------------------------------------
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS affected_populations (
                    record_id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id               INTEGER NOT NULL,
                    village_name           TEXT,
                    state                  TEXT,
                    county                 TEXT,
                    estimated_population   INTEGER,
                    flood_risk_percentage  REAL,
                    latitude               REAL,
                    longitude              REAL,
                    created_at             TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (event_id) REFERENCES events(event_id)
                )
            """)
            logger.debug("Table 'affected_populations' ready.")

            # ------------------------------------------------
            # Table 4: infrastructure_impacts
            # Roads and health facilities at risk per event.
            # One row per infrastructure feature affected.
            # ------------------------------------------------
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS infrastructure_impacts (
                    impact_id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id           INTEGER NOT NULL,
                    infrastructure_type TEXT NOT NULL,
                    name               TEXT,
                    facility_type      TEXT,
                    segment_length_km  REAL,
                    status             TEXT DEFAULT 'at_risk',
                    coordinates        TEXT,
                    created_at         TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (event_id) REFERENCES events(event_id)
                )
            """)
            # infrastructure_type: 'road' or 'health_facility'
            # status: 'at_risk', 'inaccessible', 'flooded'
            logger.debug("Table 'infrastructure_impacts' ready.")

            # ------------------------------------------------
            # Table 5: alerts
            # SMS and email alert delivery records per event.
            # One row per recipient per channel.
            # ------------------------------------------------
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id           INTEGER NOT NULL,
                    channel            TEXT NOT NULL,
                    recipient          TEXT NOT NULL,
                    delivery_status    TEXT DEFAULT 'pending',
                    sent_timestamp     TEXT,
                    delivered_timestamp TEXT,
                    error_reason       TEXT,
                    message_preview    TEXT,
                    created_at         TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (event_id) REFERENCES events(event_id)
                )
            """)
            # channel: 'sms' or 'email'
            # delivery_status: 'pending', 'sent', 'delivered', 'failed'
            logger.debug("Table 'alerts' ready.")

            # ------------------------------------------------
            # Table 6: processing_logs
            # Stage-by-stage timing and status per event.
            # One row per pipeline stage per event.
            # Used for latency tracking and debugging.
            # ------------------------------------------------
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS processing_logs (
                    log_id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id      INTEGER NOT NULL,
                    stage_name    TEXT NOT NULL,
                    start_time    TEXT,
                    end_time      TEXT,
                    duration_seconds REAL,
                    status        TEXT DEFAULT 'running',
                    error_message TEXT,
                    created_at    TEXT DEFAULT (datetime('now')),
                    FOREIGN KEY (event_id) REFERENCES events(event_id)
                )
            """)
            # stage_name: 'download', 'preprocess', 'detect', 'assess', 'alert', 'export'
            # status: 'running', 'completed', 'failed'
            logger.debug("Table 'processing_logs' ready.")

            # Commit all table creation statements
            conn.commit()
            logger.info("All 6 database tables initialised successfully.")

        except sqlite3.Error as e:
            logger.error(f"Failed to initialise database: {e}")
            raise
        finally:
            # Always close connection — even if an error occurred
            conn.close()

    # ============================================================
    # INSERT METHODS
    # One method per table for clean, testable code
    # ============================================================

    def insert_event(self, event_data: dict) -> int:
        """
        Inserts a new event record when a scene starts processing.

        Args:
            event_data: dict with keys matching the events table columns.
                        Required: 'event_timestamp'
                        Optional: 'satellite_acquisition_time', 'scene_id',
                                  'scene_path', 'processing_start_time'

        Returns:
            event_id (int): the auto-generated ID of the new record.
                            Used as foreign key in all other insert methods.

        Example:
            event_id = db.insert_event({
                'event_timestamp': datetime.now(UTC).isoformat(),
                'scene_id': 'S1A_IW_GRDH_...',
                'processing_start_time': datetime.now(UTC).isoformat(),
                'status': 'processing'
            })
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Parameterised query — safe against SQL injection
            cursor.execute("""
                INSERT INTO events (
                    event_timestamp,
                    satellite_acquisition_time,
                    processing_start_time,
                    scene_id,
                    scene_path,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                event_data.get("event_timestamp", datetime.now(UTC).isoformat()),
                event_data.get("satellite_acquisition_time"),
                event_data.get("processing_start_time"),
                event_data.get("scene_id"),
                event_data.get("scene_path"),
                event_data.get("status", "pending"),
            ))

            conn.commit()
            event_id = cursor.lastrowid  # Get auto-generated ID
            logger.info(f"Event inserted: event_id={event_id}, scene={event_data.get('scene_id', 'unknown')}")
            return event_id

        except sqlite3.Error as e:
            logger.error(f"Failed to insert event: {e}")
            raise
        finally:
            conn.close()

    def update_event(self, event_id: int, event_data: dict) -> None:
        """
        Updates an existing event record with processing results.

        Called at end of pipeline to record completion time and latency.

        Args:
            event_id: ID of the event to update
            event_data: dict with fields to update. Recognised keys:
                        'processing_end_time', 'total_latency_seconds',
                        'status', 'error_message'
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                UPDATE events SET
                    processing_end_time    = ?,
                    total_latency_seconds  = ?,
                    status                 = ?,
                    error_message          = ?
                WHERE event_id = ?
            """, (
                event_data.get("processing_end_time"),
                event_data.get("total_latency_seconds"),
                event_data.get("status", "completed"),
                event_data.get("error_message"),
                event_id,
            ))

            conn.commit()
            logger.info(f"Event updated: event_id={event_id}, status={event_data.get('status')}")

        except sqlite3.Error as e:
            logger.error(f"Failed to update event {event_id}: {e}")
            raise
        finally:
            conn.close()

    def insert_flood_mask(self, event_id: int, mask_data: dict) -> int:
        """
        Inserts flood detection results for an event.

        Args:
            event_id: foreign key linking to events table
            mask_data: dict with flood detection results. Keys:
                       'flood_extent_ha', 'iou_score', 'geotiff_path',
                       'detection_method'

        Returns:
            mask_id (int): auto-generated ID of the new record
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO flood_masks (
                    event_id,
                    flood_extent_ha,
                    iou_score,
                    geotiff_path,
                    detection_method
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                event_id,
                mask_data.get("flood_extent_ha"),
                mask_data.get("iou_score"),
                mask_data.get("geotiff_path"),
                mask_data.get("detection_method", "otsu_gmm"),
            ))

            conn.commit()
            mask_id = cursor.lastrowid
            logger.info(f"Flood mask inserted: mask_id={mask_id}, extent={mask_data.get('flood_extent_ha')}ha")
            return mask_id

        except sqlite3.Error as e:
            logger.error(f"Failed to insert flood mask for event {event_id}: {e}")
            raise
        finally:
            conn.close()

    def insert_affected_village(self, event_id: int, village_data: dict) -> int:
        """
        Inserts one affected village record for an event.

        Called once per village found within the flood extent.

        Args:
            event_id: foreign key linking to events table
            village_data: dict with village details. Keys:
                          'village_name', 'state', 'county',
                          'estimated_population', 'flood_risk_percentage',
                          'latitude', 'longitude'

        Returns:
            record_id (int): auto-generated ID of the new record
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO affected_populations (
                    event_id,
                    village_name,
                    state,
                    county,
                    estimated_population,
                    flood_risk_percentage,
                    latitude,
                    longitude
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                village_data.get("village_name"),
                village_data.get("state"),
                village_data.get("county"),
                village_data.get("estimated_population"),
                village_data.get("flood_risk_percentage"),
                village_data.get("latitude"),
                village_data.get("longitude"),
            ))

            conn.commit()
            record_id = cursor.lastrowid
            logger.debug(f"Village inserted: {village_data.get('village_name')} (event {event_id})")
            return record_id

        except sqlite3.Error as e:
            logger.error(f"Failed to insert village for event {event_id}: {e}")
            raise
        finally:
            conn.close()

    def insert_infrastructure_impact(self, event_id: int, impact_data: dict) -> int:
        """
        Inserts one infrastructure impact record for an event.

        Called once per road segment or health facility at risk.

        Args:
            event_id: foreign key linking to events table
            impact_data: dict with impact details. Keys:
                         'infrastructure_type', 'name', 'facility_type',
                         'segment_length_km', 'status', 'coordinates'

        Returns:
            impact_id (int): auto-generated ID of the new record
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Serialise coordinates dict/list to JSON string for storage
            coordinates = impact_data.get("coordinates")
            if coordinates and not isinstance(coordinates, str):
                coordinates = json.dumps(coordinates)

            cursor.execute("""
                INSERT INTO infrastructure_impacts (
                    event_id,
                    infrastructure_type,
                    name,
                    facility_type,
                    segment_length_km,
                    status,
                    coordinates
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                impact_data.get("infrastructure_type"),
                impact_data.get("name"),
                impact_data.get("facility_type"),
                impact_data.get("segment_length_km"),
                impact_data.get("status", "at_risk"),
                coordinates,
            ))

            conn.commit()
            impact_id = cursor.lastrowid
            logger.debug(f"Infrastructure impact inserted: {impact_data.get('name')} (event {event_id})")
            return impact_id

        except sqlite3.Error as e:
            logger.error(f"Failed to insert infrastructure impact for event {event_id}: {e}")
            raise
        finally:
            conn.close()

    def insert_alert(self, event_id: int, alert_data: dict) -> int:
        """
        Inserts one alert delivery record for an event.

        Called once per recipient per channel (SMS + email).

        Args:
            event_id: foreign key linking to events table
            alert_data: dict with alert details. Keys:
                        'channel', 'recipient', 'delivery_status',
                        'sent_timestamp', 'error_reason', 'message_preview'

        Returns:
            alert_id (int): auto-generated ID of the new record
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO alerts (
                    event_id,
                    channel,
                    recipient,
                    delivery_status,
                    sent_timestamp,
                    error_reason,
                    message_preview
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                alert_data.get("channel"),
                alert_data.get("recipient"),
                alert_data.get("delivery_status", "pending"),
                alert_data.get("sent_timestamp"),
                alert_data.get("error_reason"),
                alert_data.get("message_preview", "")[:160],  # Truncate to SMS length
            ))

            conn.commit()
            alert_id = cursor.lastrowid
            logger.info(f"Alert inserted: {alert_data.get('channel')} to {alert_data.get('recipient')} (event {event_id})")
            return alert_id

        except sqlite3.Error as e:
            logger.error(f"Failed to insert alert for event {event_id}: {e}")
            raise
        finally:
            conn.close()

    def insert_processing_log(self, event_id: int, log_data: dict) -> int:
        """
        Inserts one processing stage log record for an event.

        Called at start and end of each pipeline stage for latency tracking.

        Args:
            event_id: foreign key linking to events table
            log_data: dict with stage details. Keys:
                      'stage_name', 'start_time', 'end_time',
                      'duration_seconds', 'status', 'error_message'

        Returns:
            log_id (int): auto-generated ID of the new record
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO processing_logs (
                    event_id,
                    stage_name,
                    start_time,
                    end_time,
                    duration_seconds,
                    status,
                    error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                log_data.get("stage_name"),
                log_data.get("start_time"),
                log_data.get("end_time"),
                log_data.get("duration_seconds"),
                log_data.get("status", "completed"),
                log_data.get("error_message"),
            ))

            conn.commit()
            log_id = cursor.lastrowid
            logger.debug(f"Processing log inserted: stage={log_data.get('stage_name')}, status={log_data.get('status')}")
            return log_id

        except sqlite3.Error as e:
            logger.error(f"Failed to insert processing log for event {event_id}: {e}")
            raise
        finally:
            conn.close()

    # ============================================================
    # QUERY METHODS
    # For dashboard display and performance reporting
    # ============================================================

    def query_events(self, filters: Optional[dict] = None) -> pd.DataFrame:
        """
        Queries the events table with optional filters.

        Used by the Streamlit dashboard History page to list past events.

        Args:
            filters: optional dict with filter criteria. Supported keys:
                     'start_date' (str ISO), 'end_date' (str ISO),
                     'state' (str), 'status' (str), 'min_iou' (float)

        Returns:
            pd.DataFrame with matching event records joined to flood_masks.
            Empty DataFrame if no results found.
        """
        try:
            conn = self._get_connection()

            # Base query joins events with flood_masks for IoU data
            query = """
                SELECT
                    e.event_id,
                    e.event_timestamp,
                    e.satellite_acquisition_time,
                    e.total_latency_seconds,
                    e.status,
                    e.scene_id,
                    fm.flood_extent_ha,
                    fm.iou_score,
                    fm.geotiff_path
                FROM events e
                LEFT JOIN flood_masks fm ON e.event_id = fm.event_id
                WHERE 1=1
            """

            params = []

            # Apply optional filters dynamically
            if filters:
                if filters.get("start_date"):
                    query += " AND e.event_timestamp >= ?"
                    params.append(filters["start_date"])

                if filters.get("end_date"):
                    query += " AND e.event_timestamp <= ?"
                    params.append(filters["end_date"])

                if filters.get("status"):
                    query += " AND e.status = ?"
                    params.append(filters["status"])

                if filters.get("min_iou"):
                    query += " AND fm.iou_score >= ?"
                    params.append(filters["min_iou"])

                # Filter by state — checks affected_populations subquery
                if filters.get("state"):
                    query += """
                        AND e.event_id IN (
                            SELECT DISTINCT event_id
                            FROM affected_populations
                            WHERE state = ?
                        )
                    """
                    params.append(filters["state"])

            # Always return most recent first
            query += " ORDER BY e.event_timestamp DESC"

            df = pd.read_sql_query(query, conn, params=params)
            logger.info(f"Query returned {len(df)} events.")
            return df

        except sqlite3.Error as e:
            logger.error(f"Failed to query events: {e}")
            return pd.DataFrame()  # Return empty DataFrame on failure
        finally:
            conn.close()

    def query_performance_metrics(self) -> dict:
        """
        Calculates system-wide performance metrics for the dashboard.

        Returns metrics used on the Performance page:
        - average end-to-end latency
        - IoU trend over last 10 events
        - alert delivery success rate

        Returns:
            dict with keys: 'avg_latency_seconds', 'avg_iou',
                            'alert_success_rate', 'total_events',
                            'completed_events'
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Average latency across all completed events
            cursor.execute("""
                SELECT AVG(total_latency_seconds) as avg_latency
                FROM events
                WHERE status = 'completed'
            """)
            avg_latency = cursor.fetchone()["avg_latency"] or 0

            # Average IoU score across all flood masks
            cursor.execute("""
                SELECT AVG(iou_score) as avg_iou
                FROM flood_masks
                WHERE iou_score IS NOT NULL
            """)
            avg_iou = cursor.fetchone()["avg_iou"] or 0

            # Alert delivery success rate
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN delivery_status = 'sent' THEN 1 ELSE 0 END) as sent
                FROM alerts
            """)
            alert_row = cursor.fetchone()
            total_alerts = alert_row["total"] or 0
            sent_alerts = alert_row["sent"] or 0
            success_rate = (sent_alerts / total_alerts * 100) if total_alerts > 0 else 0

            # Total and completed event counts
            cursor.execute("SELECT COUNT(*) as total FROM events")
            total_events = cursor.fetchone()["total"]

            cursor.execute("SELECT COUNT(*) as completed FROM events WHERE status = 'completed'")
            completed_events = cursor.fetchone()["completed"]

            metrics = {
                "avg_latency_seconds": round(avg_latency, 1),
                "avg_iou": round(avg_iou, 3),
                "alert_success_rate": round(success_rate, 1),
                "total_events": total_events,
                "completed_events": completed_events,
            }

            logger.info(f"Performance metrics calculated: {metrics}")
            return metrics

        except sqlite3.Error as e:
            logger.error(f"Failed to calculate performance metrics: {e}")
            return {}
        finally:
            conn.close()

    def get_latest_event(self) -> Optional[dict]:
        """
        Returns the most recent completed event with all related data.

        Used by the dashboard main page to display current flood status.

        Returns:
            dict with event details, or None if no completed events exist
        """
        try:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Get most recent completed event
            cursor.execute("""
                SELECT e.*, fm.flood_extent_ha, fm.iou_score, fm.geotiff_path
                FROM events e
                LEFT JOIN flood_masks fm ON e.event_id = fm.event_id
                WHERE e.status = 'completed'
                ORDER BY e.event_timestamp DESC
                LIMIT 1
            """)

            row = cursor.fetchone()
            if row:
                # Convert Row object to plain dict
                return dict(row)
            return None

        except sqlite3.Error as e:
            logger.error(f"Failed to get latest event: {e}")
            return None
        finally:
            conn.close()

    def get_event_villages(self, event_id: int) -> pd.DataFrame:
        """
        Returns all affected villages for a specific event.

        Used by dashboard and alert message generation.

        Args:
            event_id: ID of the event to query

        Returns:
            pd.DataFrame with village records for the event
        """
        try:
            conn = self._get_connection()
            df = pd.read_sql_query(
                "SELECT * FROM affected_populations WHERE event_id = ? ORDER BY estimated_population DESC",
                conn,
                params=(event_id,)
            )
            return df
        except sqlite3.Error as e:
            logger.error(f"Failed to get villages for event {event_id}: {e}")
            return pd.DataFrame()
        finally:
            conn.close()

    def get_event_infrastructure(self, event_id: int) -> pd.DataFrame:
        """
        Returns all infrastructure impacts for a specific event.

        Used by dashboard tables and alert message generation.

        Args:
            event_id: ID of the event to query

        Returns:
            pd.DataFrame with infrastructure impact records
        """
        try:
            conn = self._get_connection()
            df = pd.read_sql_query(
                "SELECT * FROM infrastructure_impacts WHERE event_id = ?",
                conn,
                params=(event_id,)
            )
            return df
        except sqlite3.Error as e:
            logger.error(f"Failed to get infrastructure for event {event_id}: {e}")
            return pd.DataFrame()
        finally:
            conn.close()


# ============================================================
# Quick self-test — run this file directly to verify database
# Usage: python3 src/database.py
# ============================================================
if __name__ == "__main__":
    from src.config import Config, setup_logging
    setup_logging()

    config = Config()
    db = DatabaseManager(config)

    print("\n" + "=" * 55)
    print("SuddWatch Database Verification")
    print("=" * 55)

    # --- Test: insert a dummy event ---
    event_id = db.insert_event({
        "event_timestamp": datetime.now(UTC).isoformat(),
        "satellite_acquisition_time": datetime.now(UTC).isoformat(),
        "processing_start_time": datetime.now(UTC).isoformat(),
        "scene_id": "TEST_SCENE_001",
        "scene_path": "/data/raw/test.zip",
        "status": "processing",
    })
    print(f"  ✓ Event inserted: event_id={event_id}")

    # --- Test: insert a flood mask ---
    mask_id = db.insert_flood_mask(event_id, {
        "flood_extent_ha": 12500.5,
        "iou_score": 0.72,
        "geotiff_path": "/data/flood_masks/test_mask.tif",
        "detection_method": "otsu_gmm",
    })
    print(f"  ✓ Flood mask inserted: mask_id={mask_id}")

    # --- Test: insert an affected village ---
    village_id = db.insert_affected_village(event_id, {
        "village_name": "Bor",
        "state": "Jonglei",
        "county": "Bor South",
        "estimated_population": 45000,
        "flood_risk_percentage": 78.5,
        "latitude": 6.2,
        "longitude": 31.5,
    })
    print(f"  ✓ Village inserted: record_id={village_id}")

    # --- Test: insert an infrastructure impact ---
    impact_id = db.insert_infrastructure_impact(event_id, {
        "infrastructure_type": "health_facility",
        "name": "Bor State Hospital",
        "facility_type": "hospital",
        "status": "at_risk",
        "coordinates": {"lat": 6.2, "lon": 31.5},
    })
    print(f"  ✓ Infrastructure impact inserted: impact_id={impact_id}")

    # --- Test: insert an alert record ---
    alert_id = db.insert_alert(event_id, {
        "channel": "sms",
        "recipient": "+254705176665",
        "delivery_status": "sent",
        "sent_timestamp": datetime.now(UTC).isoformat(),
        "message_preview": "SUDDWATCH ALERT: Flooding detected in Jonglei",
    })
    print(f"  ✓ Alert inserted: alert_id={alert_id}")

    # --- Test: insert a processing log ---
    log_id = db.insert_processing_log(event_id, {
        "stage_name": "preprocess",
        "start_time": datetime.now(UTC).isoformat(),
        "end_time": datetime.now(UTC).isoformat(),
        "duration_seconds": 845.2,
        "status": "completed",
    })
    print(f"  ✓ Processing log inserted: log_id={log_id}")

    # --- Test: update the event to completed ---
    db.update_event(event_id, {
        "processing_end_time": datetime.now(UTC).isoformat(),
        "total_latency_seconds": 2847.5,
        "status": "completed",
    })
    print(f"  ✓ Event updated to completed")

    # --- Test: query events ---
    df = db.query_events()
    print(f"  ✓ Query returned {len(df)} event(s)")

    # --- Test: performance metrics ---
    metrics = db.query_performance_metrics()
    print(f"  ✓ Performance metrics: {metrics}")

    # --- Test: latest event ---
    latest = db.get_latest_event()
    print(f"  ✓ Latest event: scene_id={latest.get('scene_id')}")

    print("=" * 55)
    print(f"Database path: {config.db_path}")
    print("All database tests passed.\n")
