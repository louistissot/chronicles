"""
Shared pytest fixtures for DnD WhisperX tests.

Provides reusable mocks for heavy dependencies (webview, sounddevice)
so individual test files don't need to re-declare them.
"""
import sys
from unittest.mock import MagicMock, patch

import pytest

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
