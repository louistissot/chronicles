"""
Tests for postprocess.py — transcript writing, save_all directory creation,
and speaker sample extraction.

Ensures the mkdir-before-write fixes don't regress.
"""
import json

import pytest

# ---------------------------------------------------------------------------
# Minimal WhisperX JSON fixture
# ---------------------------------------------------------------------------

def _make_whisperx_json(speakers=None):
    """Return a minimal WhisperX-format dict with two speakers."""
    if speakers is None:
        speakers = ["SPEAKER_00", "SPEAKER_01"]
    segments = [
        {
            "start": 0.0, "end": 2.0,
            "text": "Hello from speaker zero.",
            "speaker": speakers[0],
            "words": [{"word": "Hello", "start": 0.0, "end": 0.5, "score": 0.9}],
        },
        {
            "start": 2.5, "end": 5.0,
            "text": "And I am speaker one.",
            "speaker": speakers[1],
            "words": [{"word": "And", "start": 2.5, "end": 2.8, "score": 0.9}],
        },
        {
            "start": 5.5, "end": 7.0,
            "text": "Back to speaker zero again.",
            "speaker": speakers[0],
            "words": [],
        },
    ]
    return {"segments": segments}


@pytest.fixture
def whisperx_json(tmp_path):
    """Write a minimal WhisperX JSON to a temp file and return its path."""
    data = _make_whisperx_json()
    p = tmp_path / "session.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


MAPPING = {"SPEAKER_00": "Alice", "SPEAKER_01": "Bob"}


# ---------------------------------------------------------------------------
# get_speakers / get_speaker_samples
# ---------------------------------------------------------------------------

class TestGetSpeakers:
    def test_returns_sorted_unique_ids(self, whisperx_json):
        from postprocess import get_speakers, load_json
        data = load_json(whisperx_json)
        assert get_speakers(data) == ["SPEAKER_00", "SPEAKER_01"]

    def test_empty_segments(self):
        from postprocess import get_speakers
        assert get_speakers({"segments": []}) == []

    def test_missing_speaker_key_ignored(self):
        from postprocess import get_speakers
        data = {"segments": [{"text": "no speaker key"}]}
        assert get_speakers(data) == []


class TestGetSpeakerSamples:
    def test_returns_lines_per_speaker(self, whisperx_json):
        from postprocess import get_speaker_samples, load_json
        data = load_json(whisperx_json)
        samples = get_speaker_samples(data)
        assert "SPEAKER_00" in samples
        assert "SPEAKER_01" in samples
        assert len(samples["SPEAKER_00"]) >= 1
        all_lines = " ".join(samples["SPEAKER_00"])
        assert "speaker zero" in all_lines.lower()

    def test_n_samples_limit(self, tmp_path):
        from postprocess import get_speaker_samples
        # 10 segments for one speaker
        segs = [{"text": f"Line {i}", "speaker": "SPEAKER_00"} for i in range(10)]
        data = {"segments": segs}
        samples = get_speaker_samples(data, n_samples=3)
        assert len(samples["SPEAKER_00"]) <= 3


# ---------------------------------------------------------------------------
# write_transcript / write_srt
# ---------------------------------------------------------------------------

class TestWriteTranscript:
    def test_creates_file(self, tmp_path, whisperx_json):
        from postprocess import apply_mapping, load_json, write_transcript
        data = load_json(whisperx_json)
        mapped = apply_mapping(data, MAPPING)
        out = tmp_path / "transcript.txt"
        write_transcript(mapped, out)
        assert out.exists()

    def test_contains_speaker_names(self, tmp_path, whisperx_json):
        from postprocess import apply_mapping, load_json, write_transcript
        data = load_json(whisperx_json)
        mapped = apply_mapping(data, MAPPING)
        out = tmp_path / "transcript.txt"
        write_transcript(mapped, out)
        content = out.read_text(encoding="utf-8")
        assert "Alice" in content
        assert "Bob" in content

    def test_contains_timestamps(self, tmp_path, whisperx_json):
        """Transcript must include MM:SS timestamps for timeline generation."""
        from postprocess import apply_mapping, load_json, write_transcript
        data = load_json(whisperx_json)
        mapped = apply_mapping(data, MAPPING)
        out = tmp_path / "transcript.txt"
        write_transcript(mapped, out)
        content = out.read_text(encoding="utf-8")
        # First segment starts at 0.0 → "(00:00)"
        assert "(00:00)" in content
        # Second speaker starts at 2.5 → "(00:02)"
        assert "(00:02)" in content


# ---------------------------------------------------------------------------
# save_all — critical: must create output_dir if it doesn't exist
# ---------------------------------------------------------------------------

class TestSaveAll:
    def test_creates_output_dir_when_missing(self, tmp_path, whisperx_json):
        """save_all must succeed even when output_dir doesn't exist yet."""
        from postprocess import save_all
        out_dir = tmp_path / "deep" / "nested" / "session"
        assert not out_dir.exists()
        txt, srt = save_all(whisperx_json, MAPPING, output_dir=out_dir)
        assert out_dir.exists()
        assert txt is not None and txt.exists()

    def test_writes_txt_by_default(self, tmp_path, whisperx_json):
        from postprocess import save_all
        txt, _ = save_all(whisperx_json, MAPPING, output_dir=tmp_path)
        assert txt is not None
        content = txt.read_text(encoding="utf-8")
        assert "Alice" in content or "Bob" in content

    def test_writes_srt_by_default(self, tmp_path, whisperx_json):
        from postprocess import save_all
        _, srt = save_all(whisperx_json, MAPPING, output_dir=tmp_path)
        assert srt is not None and srt.exists()
        content = srt.read_text(encoding="utf-8")
        assert "-->" in content  # SRT timestamp format

    def test_skip_txt(self, tmp_path, whisperx_json):
        from postprocess import save_all
        txt, srt = save_all(whisperx_json, MAPPING, output_dir=tmp_path, write_txt=False)
        assert txt is None

    def test_skip_srt(self, tmp_path, whisperx_json):
        from postprocess import save_all
        txt, srt = save_all(whisperx_json, MAPPING, output_dir=tmp_path, do_srt=False)
        assert srt is None

    def test_default_output_dir_is_json_parent(self, tmp_path, whisperx_json):
        """When output_dir is omitted, files should land next to the JSON."""
        from postprocess import save_all
        txt, srt = save_all(whisperx_json, MAPPING)
        assert txt.parent == whisperx_json.parent

    def test_idempotent_on_existing_dir(self, tmp_path, whisperx_json):
        """Running save_all twice on the same dir should not raise."""
        from postprocess import save_all
        save_all(whisperx_json, MAPPING, output_dir=tmp_path)
        save_all(whisperx_json, MAPPING, output_dir=tmp_path)  # no exception
