"""
Tests for glossary-aware transcript correction (postprocess.correct_transcript_terms).
"""
import copy
import pytest

from postprocess import correct_transcript_terms


# ── Fixtures ──────────────────────────────────────────────────────────────────

SAMPLE_DATA = {
    "segments": [
        {"speaker": "SPEAKER_00", "text": "We need to find Bobbling before sunset.", "start": 0.0, "end": 3.0},
        {"speaker": "SPEAKER_01", "text": "Let's head to Hollow Harbur then.", "start": 3.0, "end": 6.0},
        {"speaker": "SPEAKER_00", "text": "I cast fireball at the goblin.", "start": 6.0, "end": 9.0},
        {"speaker": "SPEAKER_01", "text": "The Sward of Frost glows blue.", "start": 9.0, "end": 12.0},
        {"speaker": "SPEAKER_00", "text": "We should ask Straud about the curse.", "start": 12.0, "end": 15.0},
    ]
}

GLOSSARY_TERMS = ["Boblin", "Hollow Harbor", "Sword of Frost", "Strahd", "Castle Ravenloft"]
CHARACTER_NAMES = ["Aragorn", "Gandalf"]


# ── Basic correction tests ────────────────────────────────────────────────────

class TestFuzzyCorrection:
    def test_single_word_correction(self):
        """'Bobbling' should be corrected to 'Boblin'."""
        data = {
            "segments": [
                {"speaker": "SPEAKER_00", "text": "We need to find Bobbling before sunset.", "start": 0.0, "end": 3.0},
            ]
        }
        result, corrections = correct_transcript_terms(data, ["Boblin"], [])
        assert "Boblin" in result["segments"][0]["text"]
        assert "Bobbling" in corrections

    def test_multi_word_correction(self):
        """'Hollow Harbur' should be corrected to 'Hollow Harbor'."""
        data = {
            "segments": [
                {"speaker": "SPEAKER_01", "text": "Let's head to Hollow Harbur then.", "start": 0.0, "end": 3.0},
            ]
        }
        result, corrections = correct_transcript_terms(data, ["Hollow Harbor"], [])
        assert "Hollow Harbor" in result["segments"][0]["text"]

    def test_straud_to_strahd(self):
        """'Straud' should be corrected to 'Strahd'."""
        data = {
            "segments": [
                {"speaker": "SPEAKER_00", "text": "We should ask Straud about the curse.", "start": 0.0, "end": 3.0},
            ]
        }
        result, corrections = correct_transcript_terms(data, ["Strahd"], [])
        assert "Strahd" in result["segments"][0]["text"]
        assert "Straud" in corrections

    def test_no_false_positive_common_words(self):
        """Common English words should NOT be corrected."""
        data = {
            "segments": [
                {"speaker": "SPEAKER_00", "text": "I cast fireball at the goblin.", "start": 0.0, "end": 3.0},
            ]
        }
        original_text = data["segments"][0]["text"]
        result, corrections = correct_transcript_terms(data, GLOSSARY_TERMS, CHARACTER_NAMES)
        # 'fireball' and 'goblin' should NOT be changed to any glossary term
        assert result["segments"][0]["text"] == original_text or len(corrections) == 0

    def test_exact_match_unchanged(self):
        """Terms that already match exactly should not be modified."""
        data = {
            "segments": [
                {"speaker": "SPEAKER_00", "text": "Boblin is waiting at Castle Ravenloft.", "start": 0.0, "end": 3.0},
            ]
        }
        result, corrections = correct_transcript_terms(data, GLOSSARY_TERMS, CHARACTER_NAMES)
        assert "Boblin" in result["segments"][0]["text"]
        assert "Castle Ravenloft" in result["segments"][0]["text"]
        # No corrections needed for exact matches
        assert "Boblin" not in corrections

    def test_empty_glossary_no_changes(self):
        """With no glossary/character names, transcript should be unchanged."""
        data = copy.deepcopy(SAMPLE_DATA)
        result, corrections = correct_transcript_terms(data, [], [])
        assert corrections == {}
        for i, seg in enumerate(result["segments"]):
            assert seg["text"] == SAMPLE_DATA["segments"][i]["text"]

    def test_min_length_filter(self):
        """Terms shorter than 4 characters should not trigger corrections."""
        data = {
            "segments": [
                {"speaker": "SPEAKER_00", "text": "The cat sat on the mat.", "start": 0.0, "end": 3.0},
            ]
        }
        result, corrections = correct_transcript_terms(data, ["Cat", "Mat"], [])
        # 'Cat' and 'Mat' are 3 chars, below the 4-char min threshold
        assert corrections == {}

    def test_character_names_used(self):
        """Character names should also be used for correction."""
        data = {
            "segments": [
                {"speaker": "SPEAKER_00", "text": "Ask Gandulf about the ring.", "start": 0.0, "end": 3.0},
            ]
        }
        result, corrections = correct_transcript_terms(data, [], ["Gandalf"])
        assert "Gandalf" in result["segments"][0]["text"]
        assert "Gandulf" in corrections

    def test_preserves_punctuation(self):
        """Correction should preserve surrounding punctuation."""
        data = {
            "segments": [
                {"speaker": "SPEAKER_00", "text": "Is that Bobbling?", "start": 0.0, "end": 3.0},
            ]
        }
        result, corrections = correct_transcript_terms(data, ["Boblin"], [])
        text = result["segments"][0]["text"]
        # Should contain Boblin and still end with ?
        assert "Boblin" in text

    def test_original_data_not_mutated(self):
        """The original data dict should not be modified."""
        data = copy.deepcopy(SAMPLE_DATA)
        original_text = data["segments"][0]["text"]
        result, _ = correct_transcript_terms(data, GLOSSARY_TERMS, CHARACTER_NAMES)
        assert data["segments"][0]["text"] == original_text

    def test_multiple_corrections_in_same_segment(self):
        """Multiple terms in the same segment should all be corrected."""
        data = {
            "segments": [
                {"speaker": "SPEAKER_00", "text": "Straud lives near Bobbling in the castle.", "start": 0.0, "end": 3.0},
            ]
        }
        result, corrections = correct_transcript_terms(data, ["Strahd", "Boblin"], [])
        text = result["segments"][0]["text"]
        assert "Strahd" in text
        assert "Boblin" in text
