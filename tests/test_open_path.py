"""
Tests for backend.py open_path() — verifies URL vs filesystem routing.

Does NOT start the full pywebview API; only tests the routing logic.
"""
from unittest.mock import MagicMock, patch


def _make_api():
    """Return a minimal API instance without starting pywebview."""
    # Patch webview before import so the module doesn't try to open a window.
    webview_mock = MagicMock()
    with patch.dict("sys.modules", {"webview": webview_mock}):
        import backend
        # Provide a window_ref_holder with None so _window is None
        return backend.API([None])


class TestOpenPath:
    def test_http_url_calls_open_directly(self, tmp_path):
        api = _make_api()
        with patch("subprocess.Popen") as mock_popen:
            result = api.open_path("http://www.dndbeyond.com/campaigns/12345")
        mock_popen.assert_called_once_with(["open", "http://www.dndbeyond.com/campaigns/12345"])
        assert result["ok"] is True

    def test_https_url_calls_open_directly(self, tmp_path):
        api = _make_api()
        with patch("subprocess.Popen") as mock_popen:
            result = api.open_path("https://www.dndbeyond.com/campaigns/abc")
        mock_popen.assert_called_once_with(["open", "https://www.dndbeyond.com/campaigns/abc"])
        assert result["ok"] is True

    def test_filesystem_path_opens_parent_for_file(self, tmp_path):
        """For an existing file, open_path should open its parent directory."""
        test_file = tmp_path / "session.txt"
        test_file.write_text("hello")
        api = _make_api()
        with patch("subprocess.Popen") as mock_popen:
            result = api.open_path(str(test_file))
        mock_popen.assert_called_once_with(["open", str(tmp_path)])
        assert result["ok"] is True

    def test_filesystem_directory_opens_itself(self, tmp_path):
        """For a directory path, open_path should open the directory."""
        api = _make_api()
        with patch("subprocess.Popen") as mock_popen:
            result = api.open_path(str(tmp_path))
        mock_popen.assert_called_once_with(["open", str(tmp_path)])
        assert result["ok"] is True

    def test_url_does_not_go_through_path_resolution(self, tmp_path):
        """URL must not be wrapped in Path() — that would mangle it."""
        api = _make_api()
        url = "https://www.dndbeyond.com/campaigns/test"
        with patch("subprocess.Popen") as mock_popen:
            api.open_path(url)
        called_arg = mock_popen.call_args[0][0]
        # The second element must be exactly the URL, not a mangled path
        assert called_arg[1] == url

    def test_exception_returns_error_dict(self, tmp_path):
        api = _make_api()
        with patch("subprocess.Popen", side_effect=OSError("boom")):
            result = api.open_path("https://example.com")
        assert result["ok"] is False
        assert "boom" in result["error"]
