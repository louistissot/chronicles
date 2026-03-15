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
