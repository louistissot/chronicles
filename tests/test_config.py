"""
Tests for config.py — get/set tokens and preferences.

Runs in a temp directory so it never touches the real
~/.config/dnd-whisperx/prefs.json.
"""
import json
import threading


class TestTokens:
    def test_get_token_returns_empty_by_default(self, config_file):
        import config
        assert config.get_token("claude_token") == ""

    def test_set_and_get_token_roundtrip(self, config_file):
        import config
        config.set_token("claude_token", "sk-ant-test123")
        assert config.get_token("claude_token") == "sk-ant-test123"

    def test_set_token_persists_to_disk(self, config_file):
        import config
        config.set_token("hf_token", "hf_abc123")
        # Reload by clearing module state and re-reading file
        assert config_file.exists()
        assert "hf_abc123" in config_file.read_text()

    def test_get_hf_token_shortcut(self, config_file):
        import config
        config.set_token("hf_token", "hf_test")
        assert config.get_hf_token() == "hf_test"

    def test_get_claude_token_shortcut(self, config_file):
        import config
        config.set_token("claude_token", "sk-claude")
        assert config.get_claude_token() == "sk-claude"

    def test_get_openai_token_shortcut(self, config_file):
        import config
        config.set_token("openai_token", "sk-openai")
        assert config.get_openai_token() == "sk-openai"

    def test_multiple_tokens_coexist(self, config_file):
        import config
        config.set_token("claude_token", "sk-ant-a")
        config.set_token("openai_token", "sk-openai-b")
        assert config.get_token("claude_token") == "sk-ant-a"
        assert config.get_token("openai_token") == "sk-openai-b"

    def test_get_gemini_token_shortcut(self, config_file):
        import config
        config.set_token("gemini_token", "AIza-test")
        assert config.get_gemini_token() == "AIza-test"

    def test_set_gemini_token_shortcut(self, config_file):
        import config
        config.set_gemini_token("AIza-test2")
        assert config.get_gemini_token() == "AIza-test2"


class TestPreferences:
    def test_get_pref_returns_default(self, config_file):
        import config
        assert config.get_pref("model") == "large-v2"

    def test_set_and_get_pref_roundtrip(self, config_file):
        import config
        config.set_pref("model", "medium")
        assert config.get_pref("model") == "medium"

    def test_set_pref_persists_to_disk(self, config_file):
        import config
        config.set_pref("llm_provider", "openai")
        assert config_file.exists()
        assert "openai" in config_file.read_text()

    def test_unknown_pref_returns_none(self, config_file):
        import config
        assert config.get_pref("nonexistent_key") is None

    def test_prefs_and_tokens_coexist(self, config_file):
        import config
        config.set_pref("model", "tiny")
        config.set_token("claude_token", "sk-test")
        assert config.get_pref("model") == "tiny"
        assert config.get_token("claude_token") == "sk-test"

    def test_config_dir_is_created(self, config_file):
        import config
        config.set_pref("num_speakers", "3")
        assert config_file.parent.exists()


class TestAtomicWrite:
    """Verify _save_prefs uses atomic write (tmp + rename)."""

    def test_no_tmp_file_left_after_write(self, config_file):
        import config
        config.set_pref("model", "large-v3")
        tmp = config_file.with_suffix(".tmp")
        assert not tmp.exists()

    def test_prefs_file_is_valid_json(self, config_file):
        import config
        config.set_pref("model", "large-v3")
        raw = config_file.read_text()
        data = json.loads(raw)
        assert data["model"] == "large-v3"


class TestConcurrentWrites:
    """The prefs.json race-condition fix: concurrent set_pref/set_token
    must not lose data or corrupt the file."""

    def test_concurrent_set_pref_no_data_loss(self, config_file):
        import config
        barrier = threading.Barrier(2)
        errors = []

        def writer(key, value):
            try:
                barrier.wait(timeout=5)
                config.set_pref(key, value)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=writer, args=("model", "large-v3"))
        t2 = threading.Thread(target=writer, args=("language", "fr"))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors
        assert config.get_pref("model") == "large-v3"
        assert config.get_pref("language") == "fr"

    def test_concurrent_token_and_pref_no_data_loss(self, config_file):
        import config
        barrier = threading.Barrier(2)
        errors = []

        def set_token():
            try:
                barrier.wait(timeout=5)
                config.set_hf_token("hf_concurrent")
            except Exception as e:
                errors.append(e)

        def set_pref_fn():
            try:
                barrier.wait(timeout=5)
                config.set_pref("language", "de")
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=set_token)
        t2 = threading.Thread(target=set_pref_fn)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not errors
        assert config.get_hf_token() == "hf_concurrent"
        assert config.get_pref("language") == "de"

    def test_many_concurrent_writes(self, config_file):
        """Stress test: 20 threads writing different keys simultaneously."""
        import config
        barrier = threading.Barrier(20)
        errors = []

        def writer(i):
            try:
                barrier.wait(timeout=10)
                config.set_pref("key_%d" % i, "val_%d" % i)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors
        for i in range(20):
            assert config.get_pref("key_%d" % i) == "val_%d" % i

    def test_prefs_valid_json_after_concurrent_writes(self, config_file):
        import config
        barrier = threading.Barrier(5)

        def writer(i):
            barrier.wait(timeout=5)
            config.set_pref("k%d" % i, "v%d" % i)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        raw = config_file.read_text()
        data = json.loads(raw)  # must not raise
        for i in range(5):
            assert data["k%d" % i] == "v%d" % i


class TestCorruptedFileRecovery:
    def test_corrupted_json_falls_back_to_defaults(self, config_file):
        import config
        config_file.write_text('{"model": "large-v3"}\n  "extra": "junk"\n}')
        assert config.get_pref("model") == "large-v2"  # default, not corrupted value

    def test_set_pref_overwrites_corrupted_file(self, config_file):
        import config
        config_file.write_text("not json at all!!!")
        config.set_pref("language", "es")
        raw = config_file.read_text()
        data = json.loads(raw)
        assert data["language"] == "es"
