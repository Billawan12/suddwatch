# ============================================================
# SuddWatch - Pytest Configuration
# File: tests/conftest.py
# Purpose: Shared fixtures and marks.
#
# IMPORTANT: every test uses an isolated, temporary project root.
# Earlier versions of the suite used the real Config(), which wrote
# fake events into data/database/suddwatch.db and overwrote the real
# data/downloaded_scenes.json. The `test_config` fixture prevents that.
# ============================================================

import os
import stat
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

ENV_KEYS = [
    "COPERNICUS_USER", "COPERNICUS_PASSWORD", "TWILIO_ACCOUNT_SID",
    "TWILIO_AUTH_TOKEN", "TWILIO_PHONE_NUMBER", "SMTP_USER", "SMTP_PASSWORD",
    "GITHUB_TOKEN", "SMS_RECIPIENTS", "EMAIL_RECIPIENTS", "SNAP_GPT_PATH",
    "BOUNDING_BOX_MIN_LAT", "BOUNDING_BOX_MIN_LON", "BOUNDING_BOX_MAX_LAT",
    "BOUNDING_BOX_MAX_LON", "ALERT_FLOOD_THRESHOLD_HA", "ALERT_POPULATION_THRESHOLD",
    "DASHBOARD_URL", "DRY_SEASON_BASELINE_PATH", "NEAR_FLOOD_BUFFER_M",
    "SCENE_SEARCH_DAYS", "DETECTION_METHOD",
]

TEST_ENV = """
COPERNICUS_USER=test_user
COPERNICUS_PASSWORD=test_password
TWILIO_ACCOUNT_SID=AC123456789
TWILIO_AUTH_TOKEN=abc123
TWILIO_PHONE_NUMBER=+1234567890
SMTP_USER=test@gmail.com
SMTP_PASSWORD=test_password
SMS_RECIPIENTS=+254700000001,+254700000002
EMAIL_RECIPIENTS=test1@test.com,test2@test.com
"""


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: tests that hit real external services and need real "
        "credentials in .env (run with: pytest -m integration)",
    )


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless explicitly selected with -m integration."""
    markexpr = config.getoption("-m") or ""
    if "integration" in markexpr and "not integration" not in markexpr:
        return
    skip = pytest.mark.skip(reason="integration test — run with: pytest -m integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Make sure the developer's shell variables never leak into tests."""
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def isolated_root(tmp_path, monkeypatch):
    """Temporary project root with a test .env and a fake SNAP gpt executable."""
    import src.config as cfg_mod

    (tmp_path / ".env").write_text(TEST_ENV)
    fake_gpt = tmp_path / "fake_snap" / "gpt"
    fake_gpt.parent.mkdir()
    fake_gpt.write_text("#!/bin/sh\nexit 0\n")
    fake_gpt.chmod(fake_gpt.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("SNAP_GPT_PATH", str(fake_gpt))
    monkeypatch.setattr(cfg_mod, "PROJECT_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def test_config(isolated_root):
    """A Config whose every path lives inside the temporary project root."""
    from src.config import Config
    return Config()
