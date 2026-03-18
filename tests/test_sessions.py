"""
Tests for sessions.py — register, update, delete, and list sessions.

Runs entirely in a temp directory so it never touches the real
~/.config/dnd-whisperx/sessions.json.
"""


def _make_session(sessions_file, **overrides):
    """Helper: register a minimal session and return its ID."""
    import sessions
    defaults = dict(
        campaign_id="camp-001",
        campaign_name="Test Campaign",
        season_id="season-001",
        season_number=1,
        session_dir="/tmp/fake-session",
        character_names=["DM", "Aragorn"],
    )
    defaults.update(overrides)
    return sessions.register_session(**defaults)


class TestRegisterSession:
    def test_register_returns_string_id(self, sessions_file):
        sid = _make_session(sessions_file)
        assert isinstance(sid, str)
        assert len(sid) > 0

    def test_register_persists_to_disk(self, sessions_file):
        _make_session(sessions_file)
        assert sessions_file.exists()

    def test_registered_session_appears_in_get_sessions(self, sessions_file):
        import sessions
        sid = _make_session(sessions_file)
        all_sessions = sessions.get_sessions()
        assert any(s["id"] == sid for s in all_sessions)

    def test_session_has_expected_fields(self, sessions_file):
        import sessions
        sid = _make_session(sessions_file, campaign_name="My Campaign", season_number=2)
        entry = next(s for s in sessions.get_sessions() if s["id"] == sid)
        assert entry["campaign_name"] == "My Campaign"
        assert entry["season_number"] == 2
        assert entry["character_names"] == ["DM", "Aragorn"]
        assert entry["output_dir"] == "/tmp/fake-session"

    def test_multiple_sessions_accumulate(self, sessions_file):
        import sessions
        sid1 = _make_session(sessions_file, campaign_name="Alpha")
        sid2 = _make_session(sessions_file, campaign_name="Beta")
        all_sessions = sessions.get_sessions()
        assert len(all_sessions) == 2
        ids = {s["id"] for s in all_sessions}
        assert sid1 in ids and sid2 in ids

    def test_get_sessions_returns_newest_first(self, sessions_file):
        import time

        import sessions
        _make_session(sessions_file)
        time.sleep(0.01)  # ensure distinct timestamps
        sid2 = _make_session(sessions_file)
        all_sessions = sessions.get_sessions()
        assert all_sessions[0]["id"] == sid2  # newest first

    def test_audio_path_optional(self, sessions_file):
        import sessions
        sid = _make_session(sessions_file)
        entry = next(s for s in sessions.get_sessions() if s["id"] == sid)
        assert entry["audio_path"] is None


class TestUpdateSession:
    def test_update_sets_field(self, sessions_file):
        import sessions
        sid = _make_session(sessions_file)
        sessions.update_session(sid, summary_path="/tmp/summary.md")
        entry = next(s for s in sessions.get_sessions() if s["id"] == sid)
        assert entry["summary_path"] == "/tmp/summary.md"

    def test_update_multiple_fields(self, sessions_file):
        import sessions
        sid = _make_session(sessions_file)
        sessions.update_session(sid, txt_path="/tmp/t.txt", srt_path="/tmp/t.srt")
        entry = next(s for s in sessions.get_sessions() if s["id"] == sid)
        assert entry["txt_path"] == "/tmp/t.txt"
        assert entry["srt_path"] == "/tmp/t.srt"

    def test_update_does_not_affect_other_sessions(self, sessions_file):
        import sessions
        sid1 = _make_session(sessions_file)
        sid2 = _make_session(sessions_file)
        sessions.update_session(sid1, summary_path="/tmp/s1.md")
        s2 = next(s for s in sessions.get_sessions() if s["id"] == sid2)
        assert s2["summary_path"] is None


class TestGetCampaignSessionCount:
    def test_returns_zero_for_empty_registry(self, sessions_file):
        import sessions
        assert sessions.get_campaign_session_count("camp-001") == 0

    def test_counts_sessions_with_txt_path(self, sessions_file):
        import time
        import sessions
        sid1 = _make_session(sessions_file, campaign_id="camp-A")
        sessions.update_session(sid1, txt_path="/tmp/t1.txt")
        time.sleep(1.1)  # ensure distinct session IDs (timestamp-based)
        sid2 = _make_session(sessions_file, campaign_id="camp-A")
        sessions.update_session(sid2, txt_path="/tmp/t2.txt")
        assert sessions.get_campaign_session_count("camp-A") == 2

    def test_ignores_sessions_without_txt_path(self, sessions_file):
        import time
        import sessions
        _make_session(sessions_file, campaign_id="camp-A")  # no txt_path
        time.sleep(1.1)
        sid2 = _make_session(sessions_file, campaign_id="camp-A")
        sessions.update_session(sid2, txt_path="/tmp/t.txt")
        assert sessions.get_campaign_session_count("camp-A") == 1

    def test_isolates_by_campaign_id(self, sessions_file):
        import time
        import sessions
        sid1 = _make_session(sessions_file, campaign_id="camp-A")
        sessions.update_session(sid1, txt_path="/tmp/a.txt")
        time.sleep(1.1)
        sid2 = _make_session(sessions_file, campaign_id="camp-B")
        sessions.update_session(sid2, txt_path="/tmp/b.txt")
        assert sessions.get_campaign_session_count("camp-A") == 1
        assert sessions.get_campaign_session_count("camp-B") == 1


class TestDeleteSession:
    def test_delete_removes_session(self, sessions_file):
        import sessions
        sid = _make_session(sessions_file)
        sessions.delete_session(sid)
        remaining = sessions.get_sessions()
        assert all(s["id"] != sid for s in remaining)

    def test_delete_returns_output_dir(self, sessions_file):
        import sessions
        sid = _make_session(sessions_file, session_dir="/tmp/my-session")
        output_dir = sessions.delete_session(sid)
        assert output_dir == "/tmp/my-session"

    def test_delete_nonexistent_returns_none(self, sessions_file):
        import sessions
        result = sessions.delete_session("ghost-id")
        assert result is None

    def test_delete_does_not_affect_other_sessions(self, sessions_file):
        import sessions
        sid1 = _make_session(sessions_file)
        sid2 = _make_session(sessions_file)
        sessions.delete_session(sid1)
        remaining = sessions.get_sessions()
        assert len(remaining) == 1
        assert remaining[0]["id"] == sid2


# ---------------------------------------------------------------------------
# Data loss prevention
# ---------------------------------------------------------------------------

class TestDataLossPrevention:
    def test_save_blocks_empty_overwrite(self, sessions_file):
        """_save([]) must NOT wipe a file that already has sessions."""
        import sessions
        _make_session(sessions_file)
        assert len(sessions._load()) == 1
        # Try to save empty list — should be blocked
        sessions._save([])
        assert len(sessions._load()) == 1  # data preserved

    def test_save_allows_empty_with_force(self, sessions_file):
        """_save([], force=True) should write even when it empties the file."""
        import sessions
        _make_session(sessions_file)
        sessions._save([], force=True)
        assert len(sessions._load()) == 0

    def test_update_nonexistent_id_preserves_data(self, sessions_file):
        """update_session with a ghost ID must not corrupt existing data."""
        import sessions
        sid = _make_session(sessions_file)
        sessions.update_session("ghost-id-does-not-exist", summary_path="/x")
        all_s = sessions.get_sessions()
        assert len(all_s) == 1
        assert all_s[0]["id"] == sid

    def test_save_creates_backup(self, sessions_file):
        """_save() should create a .bak file before overwriting."""
        import sessions
        sid = _make_session(sessions_file)
        # Second save triggers backup of the first
        sessions.update_session(sid, txt_path="/tmp/t.txt")
        bak = sessions_file.with_suffix(".json.bak")
        assert bak.exists()

    def test_atomic_write_uses_tmp(self, sessions_file):
        """After save, no .tmp file should remain (it was renamed)."""
        import sessions
        _make_session(sessions_file)
        tmp = sessions_file.with_suffix(".json.tmp")
        assert not tmp.exists()

    def test_delete_last_session_allowed(self, sessions_file):
        """delete_session (force=True) should work even when result is empty."""
        import sessions
        sid = _make_session(sessions_file)
        sessions.delete_session(sid)
        assert len(sessions._load()) == 0
