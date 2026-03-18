"""
Shared pytest fixtures for DnD WhisperX tests.

Provides reusable mocks for heavy dependencies (webview, sounddevice)
so individual test files don't need to re-declare them.

IMPORTANT: The _guard_real_config_files fixture (autouse=True) verifies
that no test accidentally modifies real user config files. If a test fails
with "REAL CONFIG FILE MODIFIED", add proper isolation fixtures.
"""
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Safety net — detect real config file corruption by tests
# ---------------------------------------------------------------------------

_REAL_CONFIG_DIR = Path.home() / ".config" / "dnd-whisperx"
_GUARDED_FILES = [
    _REAL_CONFIG_DIR / "sessions.json",
    _REAL_CONFIG_DIR / "campaigns.json",
    _REAL_CONFIG_DIR / "characters.json",
]


@pytest.fixture(autouse=True)
def _guard_real_config_files():
    """Fail the test if any real config file is modified during the test."""
    snapshots = {}
    for f in _GUARDED_FILES:
        if f.exists():
            st = f.stat()
            snapshots[f] = (st.st_size, st.st_mtime_ns)
    yield
    for f in _GUARDED_FILES:
        if f not in snapshots:
            if f.exists():
                pytest.fail(
                    "REAL CONFIG FILE CREATED by test: %s — add isolation fixtures!" % f
                )
        else:
            if f.exists():
                st = f.stat()
                old_size, old_mtime = snapshots[f]
                if st.st_size != old_size or st.st_mtime_ns != old_mtime:
                    pytest.fail(
                        "REAL CONFIG FILE MODIFIED by test: %s (size %d→%d) — "
                        "add isolation fixtures!" % (f, old_size, st.st_size)
                    )

# ---------------------------------------------------------------------------
# Module-level mocks — prevent import errors for deps not installed in CI
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=False)
def mock_heavy_deps():
    """Patch webview and sounddevice so backend/main can be imported in tests."""
    mocks = {
        "webview": MagicMock(),
        "sounddevice": MagicMock(),
    }
    with patch.dict(sys.modules, mocks):
        yield mocks


# ---------------------------------------------------------------------------
# File isolation fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def campaigns_file(tmp_path, monkeypatch):
    """Redirect campaigns._CAMPAIGNS_FILE to a temp path for test isolation."""
    target = tmp_path / "campaigns.json"
    monkeypatch.setattr("campaigns._CAMPAIGNS_FILE", target)
    return target


@pytest.fixture
def sessions_file(tmp_path, monkeypatch):
    """Redirect sessions.REGISTRY_FILE to a temp path for test isolation."""
    import sessions
    target = tmp_path / "sessions.json"
    monkeypatch.setattr(sessions, "REGISTRY_FILE", target)
    return target


@pytest.fixture
def config_file(tmp_path, monkeypatch):
    """Redirect config.CONFIG_FILE (and CONFIG_DIR) to a temp path."""
    import config
    monkeypatch.setattr(config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config, "CONFIG_FILE", tmp_path / "prefs.json")
    return tmp_path / "prefs.json"


@pytest.fixture
def characters_file(tmp_path, monkeypatch):
    """Redirect characters storage to a temp path for test isolation."""
    import characters
    monkeypatch.setattr(characters, "_CHARACTERS_FILE", tmp_path / "characters.json")
    monkeypatch.setattr(characters, "_CHARACTERS_DIR", tmp_path / "characters")
    return tmp_path / "characters.json"
