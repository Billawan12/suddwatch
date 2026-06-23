# ============================================================
# SuddWatch - Pytest Configuration
# File: tests/conftest.py
# Purpose: Registers custom pytest marks and shared config.
#          Prevents pytest warnings about unknown marks.
# ============================================================

import pytest


def pytest_configure(config):
    """
    Registers custom pytest marks used across the test suite.
    Without this, pytest warns about unrecognised marks.
    """
    config.addinivalue_line(
        "markers",
        "integration: marks tests that hit real APIs "
        "(deselect with '-m not integration')"
    )
