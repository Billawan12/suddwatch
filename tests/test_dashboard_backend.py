# ============================================================
# SuddWatch - Tests for the dashboard back-end helpers
# (accounts, admin actions, runtime settings). No Streamlit needed.
# ============================================================

import importlib
import json
import sys
from pathlib import Path

import pytest

DASH = Path(__file__).parent.parent / "dashboard"
sys.path.insert(0, str(DASH))


@pytest.fixture
def auth_mod(tmp_path, monkeypatch):
    import auth
    importlib.reload(auth)
    monkeypatch.setattr(auth, "AUTH_DB", tmp_path / "auth.db")
    return auth


class TestAuth:
    def test_demo_accounts_seeded_and_hashed(self, auth_mod):
        assert auth_mod.authenticate("admin@suddwatch.org", "admin123")["role"] == "Admin"
        assert auth_mod.authenticate("admin@suddwatch.org", "wrong") is None
        import sqlite3
        h = sqlite3.connect(auth_mod.AUTH_DB).execute(
            "SELECT pw_hash FROM users WHERE email='admin@suddwatch.org'").fetchone()[0]
        assert h.startswith("pbkdf2$") and "admin123" not in h

    def test_legacy_sha256_hash_still_works_and_is_upgraded(self, auth_mod):
        import hashlib, sqlite3
        auth_mod.init_auth()
        con = sqlite3.connect(auth_mod.AUTH_DB)
        con.execute("INSERT INTO users (email,name,role,pw_hash) VALUES (?,?,?,?)",
                    ("old@x.org", "Old", "User", hashlib.sha256(b"pw12345678").hexdigest()))
        con.commit()
        assert auth_mod.authenticate("old@x.org", "pw12345678")
        h = con.execute("SELECT pw_hash FROM users WHERE email='old@x.org'").fetchone()[0]
        assert h.startswith("pbkdf2$")

    def test_request_approve_flow(self, auth_mod):
        assert auth_mod.submit_request("Ann", "UNICEF", "ann@unicef.org", "secret123") == "ok"
        assert auth_mod.submit_request("Ann", "UNICEF", "ann@unicef.org", "secret123") == "pending"
        req = auth_mod.list_requests()[0]
        assert auth_mod.authenticate("ann@unicef.org", "secret123") is None
        assert auth_mod.decide_request(req["id"], approve=True)
        assert auth_mod.authenticate("ann@unicef.org", "secret123")["role"] == "User"
        assert auth_mod.list_requests() == []

    def test_reject(self, auth_mod):
        auth_mod.submit_request("Bob", "IOM", "bob@iom.int", "secret123")
        req = auth_mod.list_requests()[0]
        auth_mod.decide_request(req["id"], approve=False)
        assert auth_mod.authenticate("bob@iom.int", "secret123") is None
        assert auth_mod.list_requests("rejected")[0]["email"] == "bob@iom.int"


@pytest.fixture
def admin_mod(isolated_root, monkeypatch):
    import admin_actions
    importlib.reload(admin_actions)
    root = isolated_root
    monkeypatch.setattr(admin_actions, "ROOT", root)
    monkeypatch.setattr(admin_actions, "ENV_FILE", root / ".env")
    monkeypatch.setattr(admin_actions, "AUDIT_FILE", root / "logs" / "audit.jsonl")
    monkeypatch.setattr(admin_actions, "RUN_STATE", root / "logs" / "run.json")
    monkeypatch.setattr(admin_actions, "REAL_DB", root / "data" / "database" / "suddwatch.db")
    return admin_actions


class TestAdminActions:
    def test_save_recipients_writes_env(self, admin_mod):
        admin_mod.save_recipients(sms_text="+211921000001 - Chief A\n+211921000002",
                                  email_text="a@ocha.org\nb@reach.org")
        sms, email = admin_mod.get_recipients()
        assert sms == ["+211921000001", "+211921000002"]
        assert email == ["a@ocha.org", "b@reach.org"]

    def test_invalid_recipients_rejected(self, admin_mod):
        with pytest.raises(ValueError):
            admin_mod.save_recipients(sms_text="0921000001")
        with pytest.raises(ValueError):
            admin_mod.save_recipients(email_text="not-an-email")

    def test_thresholds_reach_pipeline_config(self, admin_mod):
        admin_mod.save_settings(alert_flood_threshold_ha=1500, alert_population_threshold=2500)
        from src.config import Config
        cfg = Config()
        assert cfg.alert_flood_threshold_ha == 1500
        assert cfg.alert_population_threshold == 2500

    def test_unknown_setting_refused(self, admin_mod):
        with pytest.raises(KeyError):
            admin_mod.save_settings(snap_gpt_path="/bin/sh")

    def test_audit_log_records_actions(self, admin_mod):
        admin_mod.record("admin@x.org", "TEST_ACTION", "hello", "info")
        log = admin_mod.audit_log()
        assert log[0][2] == "TEST_ACTION" and log[0][1] == "admin@x.org"

    def test_stage_status_reports_missing_setup(self, admin_mod):
        names = {n: st for n, st, _ in admin_mod.stage_status()}
        assert names["Risk Assessment"] == "Not configured"   # no WorldPop/OSM in temp root
        assert names["Flood Detection"] == "No runs yet"

    def test_launch_rejects_missing_scene(self, admin_mod):
        with pytest.raises(FileNotFoundError):
            admin_mod.launch_pipeline(scene="data/raw/missing.zip")

    def test_storage_lists_folders(self, admin_mod):
        names = [n for n, _, _ in admin_mod.storage()]
        assert "SQLite database" in names and "Log files" in names
