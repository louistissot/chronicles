"""
Tests for image_gen.py — Gemini image generation via google-genai SDK (gemini-2.5-flash-image).

All SDK calls are mocked via sys.modules patching of the lazy imports.
"""
import sys
from unittest.mock import MagicMock, patch

import pytest


# Force fresh import of image_gen for each test
@pytest.fixture(autouse=True)
def _fresh_image_gen():
    sys.modules.pop("image_gen", None)
    yield
    sys.modules.pop("image_gen", None)


def _build_sdk_mocks(image_bytes=b"PNGDATA"):
    """Return (mock_genai_module, mock_types, mock_client) with a working generate_content."""
    mock_genai = MagicMock()
    mock_types = MagicMock()

    mock_client = MagicMock()
    mock_genai.Client.return_value = mock_client

    # Build response: candidates[0].content.parts[0].inline_data.data
    mock_inline_data = MagicMock()
    mock_inline_data.data = image_bytes
    mock_inline_data.mime_type = "image/png"

    mock_part = MagicMock()
    mock_part.inline_data = mock_inline_data

    mock_content = MagicMock()
    mock_content.parts = [mock_part]

    mock_candidate = MagicMock()
    mock_candidate.content = mock_content

    mock_response = MagicMock()
    mock_response.candidates = [mock_candidate]
    mock_client.models.generate_content.return_value = mock_response

    return mock_genai, mock_types, mock_client


def _sdk_modules(mock_genai, mock_types):
    """Patch dict for sys.modules so `from google import genai` works."""
    mock_google = MagicMock()
    mock_google.genai = mock_genai
    return {
        "google": mock_google,
        "google.genai": mock_genai,
        "google.genai.types": mock_types,
    }


class TestGenerateIllustration:
    def test_happy_path(self, tmp_path):
        mock_genai, mock_types, mock_client = _build_sdk_mocks(b"TESTIMAGE")

        with patch.dict("sys.modules", _sdk_modules(mock_genai, mock_types)):
            import image_gen
            out = str(tmp_path / "illustration.png")
            ok = image_gen.generate_illustration(
                prompt="A dragon in a cave",
                api_key="test-key",
                output_path=out,
            )
        assert ok is True
        assert (tmp_path / "illustration.png").read_bytes() == b"TESTIMAGE"
        mock_client.models.generate_content.assert_called_once()

    def test_stop_check_before_api_call(self, tmp_path):
        # stop_check fires before any SDK call, so no SDK needed
        mock_genai, mock_types, _ = _build_sdk_mocks()
        with patch.dict("sys.modules", _sdk_modules(mock_genai, mock_types)):
            import image_gen
            ok = image_gen.generate_illustration(
                prompt="test",
                api_key="key",
                output_path=str(tmp_path / "out.png"),
                stop_check=lambda: True,
            )
        assert ok is False

    def test_stop_check_after_api_call(self, tmp_path):
        mock_genai, mock_types, _ = _build_sdk_mocks(b"DATA")
        call_count = [0]

        def stop_after_first():
            call_count[0] += 1
            return call_count[0] > 1

        with patch.dict("sys.modules", _sdk_modules(mock_genai, mock_types)):
            import image_gen
            ok = image_gen.generate_illustration(
                prompt="test",
                api_key="key",
                output_path=str(tmp_path / "out.png"),
                stop_check=stop_after_first,
            )
        assert ok is False

    def test_api_error_raises(self, tmp_path):
        mock_genai, mock_types, mock_client = _build_sdk_mocks()
        mock_client.models.generate_content.side_effect = Exception("API timeout")

        with patch.dict("sys.modules", _sdk_modules(mock_genai, mock_types)):
            import image_gen
            with pytest.raises(RuntimeError, match="(?i)failed"):
                image_gen.generate_illustration(
                    prompt="test", api_key="key",
                    output_path=str(tmp_path / "out.png"),
                )

    def test_no_candidates_raises(self, tmp_path):
        mock_genai, mock_types, mock_client = _build_sdk_mocks()
        mock_response = MagicMock()
        mock_response.candidates = []
        mock_client.models.generate_content.return_value = mock_response

        with patch.dict("sys.modules", _sdk_modules(mock_genai, mock_types)):
            import image_gen
            with pytest.raises(RuntimeError, match="(?i)no image"):
                image_gen.generate_illustration(
                    prompt="test", api_key="key",
                    output_path=str(tmp_path / "out.png"),
                )

    def test_no_image_part_raises(self, tmp_path):
        """Response has candidates but no inline_data parts."""
        mock_genai, mock_types, mock_client = _build_sdk_mocks()

        # Build response with text-only part (no inline_data)
        mock_part = MagicMock()
        mock_part.inline_data = None
        del mock_part.inline_data  # hasattr will return False

        mock_content = MagicMock()
        mock_content.parts = [mock_part]
        mock_candidate = MagicMock()
        mock_candidate.content = mock_content
        mock_response = MagicMock()
        mock_response.candidates = [mock_candidate]
        mock_client.models.generate_content.return_value = mock_response

        with patch.dict("sys.modules", _sdk_modules(mock_genai, mock_types)):
            import image_gen
            with pytest.raises(RuntimeError, match="(?i)no image data"):
                image_gen.generate_illustration(
                    prompt="test", api_key="key",
                    output_path=str(tmp_path / "out.png"),
                )

    def test_base64_string_data(self, tmp_path):
        """When inline_data.data is a base64 string instead of bytes."""
        import base64
        raw_bytes = b"HELLO_IMAGE"
        b64_str = base64.b64encode(raw_bytes).decode()

        mock_genai, mock_types, mock_client = _build_sdk_mocks()
        # Override inline_data.data to be a string
        mock_response = mock_client.models.generate_content.return_value
        mock_response.candidates[0].content.parts[0].inline_data.data = b64_str

        with patch.dict("sys.modules", _sdk_modules(mock_genai, mock_types)):
            import image_gen
            out = str(tmp_path / "out.png")
            ok = image_gen.generate_illustration(
                prompt="test", api_key="key", output_path=out,
            )
        assert ok is True
        assert (tmp_path / "out.png").read_bytes() == raw_bytes
