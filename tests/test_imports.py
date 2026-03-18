"""
Smoke tests — verify all Python modules import without syntax errors
and that key functions/classes exist.

These catch Python 3.9 syntax violations (e.g. str | None) and missing
exports early, before running the full app.
"""
import importlib
import sys
from unittest.mock import MagicMock, patch

# Modules that need heavy deps mocked out to import cleanly
_WEBVIEW_MOCK = MagicMock()
_SOUNDDEVICE_MOCK = MagicMock()


def _mock_imports():
    return patch.dict("sys.modules", {
        "webview": _WEBVIEW_MOCK,
        "sounddevice": _SOUNDDEVICE_MOCK,
    })


class TestPythonModuleImports:
    def test_postprocess_imports(self):
        import postprocess
        assert callable(postprocess.get_speakers)
        assert callable(postprocess.get_speaker_samples)
        assert callable(postprocess.get_name_mention_segments)
        assert callable(postprocess.apply_mapping)
        assert callable(postprocess.save_all)
        assert callable(postprocess.correct_transcript_terms)

    def test_campaigns_imports(self):
        import campaigns
        assert callable(campaigns.get_campaigns)
        assert callable(campaigns.create_campaign)
        assert callable(campaigns.add_season)
        assert callable(campaigns.update_season)
        assert callable(campaigns.update_campaign)
        assert callable(campaigns.delete_campaign)

    def test_config_imports(self):
        import config
        assert callable(config.get_token)
        assert callable(config.set_token)
        assert callable(config.get_hf_token)
        assert callable(config.get_claude_token)
        assert callable(config.get_openai_token)
        assert callable(config.get_pref)
        assert callable(config.set_pref)

    def test_llm_imports(self):
        import llm
        assert callable(llm.call_llm)
        assert callable(llm.stream_llm)

    def test_log_imports(self):
        import log
        assert callable(log.get_logger)

    def test_sessions_imports(self):
        import sessions
        assert callable(sessions.get_sessions)
        assert callable(sessions.register_session)
        assert callable(sessions.update_session)

    def test_backend_imports(self):
        with _mock_imports():
            import backend
            assert hasattr(backend, "API")
            api_cls = backend.API
            # Verify all campaign-related methods exist on API
            assert callable(getattr(api_cls, "get_campaigns", None))
            assert callable(getattr(api_cls, "create_campaign", None))
            assert callable(getattr(api_cls, "add_season", None))
            assert callable(getattr(api_cls, "update_season", None))
            assert callable(getattr(api_cls, "update_campaign", None))
            assert callable(getattr(api_cls, "delete_campaign", None))
            assert callable(getattr(api_cls, "open_path", None))
            # New methods: title generation, downloads
            assert callable(getattr(api_cls, "generate_session_title", None))
            assert callable(getattr(api_cls, "download_file", None))
            assert callable(getattr(api_cls, "download_session_zip", None))

    def test_characters_imports(self):
        import characters
        assert callable(characters.create_character)
        assert callable(characters.get_character)
        assert callable(characters.get_characters)
        assert callable(characters.update_character)
        assert callable(characters.delete_character)
        assert callable(characters.get_characters_by_ids)
        assert callable(characters.character_names_from_ids)
        assert callable(characters.migrate_from_campaign_chars)

    def test_beyond_imports(self):
        import beyond
        assert callable(beyond.extract_character_id)
        assert callable(beyond.fetch_beyond_character)
        assert callable(beyond.download_avatar)

    def test_entities_imports(self):
        import entities
        assert callable(entities.create_entity)
        assert callable(entities.get_entities)
        assert callable(entities.get_entity)
        assert callable(entities.find_entity_by_name)
        assert callable(entities.find_entity_fuzzy)
        assert callable(entities.update_entity)
        assert callable(entities.delete_entity)
        assert callable(entities.create_relationship)
        assert callable(entities.update_relationship)
        assert callable(entities.get_relationships)
        assert callable(entities.get_entity_timeline)
        assert callable(entities.get_entity_context_for_llm)
        assert callable(entities.migrate_glossary_to_entities)
        assert callable(entities.migrate_session_artifacts)
        assert callable(entities.ensure_migrated)
        assert callable(entities.process_extracted_entities)
        assert callable(entities.project_to_glossary)

    def test_maps_imports(self):
        import maps
        assert callable(maps.load_map)
        assert callable(maps.save_map)
        assert callable(maps.update_node_positions)

    def test_no_python310_union_syntax(self):
        """
        Ensure none of the Python files use X | Y union type hints —
        that syntax requires Python 3.10+ and will crash on 3.9 at import time.
        We verify indirectly by importing all modules successfully.
        """
        modules = [
            "campaigns", "config", "llm", "log", "sessions",
            "characters", "beyond", "postprocess",
            "image_gen", "llm_mapper", "entities", "maps",
        ]
        for name in modules:
            mod = sys.modules.get(name) or importlib.import_module(name)
            assert mod is not None, f"Failed to import {name}"

    def test_pyinstaller_spec_includes_all_app_modules(self):
        """Verify that DnDWhisperX.spec hiddenimports includes all app modules."""
        from pathlib import Path
        spec_path = Path(__file__).parent.parent / "DnDWhisperX.spec"
        spec_content = spec_path.read_text()
        required_modules = [
            "config", "runner", "postprocess", "llm_mapper", "llm",
            "sessions", "campaigns", "characters", "entities", "maps",
            "image_gen", "backend",
        ]
        for mod in required_modules:
            assert '"{}"'.format(mod) in spec_content, \
                "Module '{}' missing from DnDWhisperX.spec hiddenimports!".format(mod)


class TestBackendAPIShape:
    """Verify the API class has the right method signatures (arity checks)."""

    def _get_api(self):
        with _mock_imports():
            import backend
            return backend.API([None])

    def test_update_campaign_signature(self):
        import inspect
        with _mock_imports():
            import backend
        sig = inspect.signature(backend.API.update_campaign)
        params = list(sig.parameters.keys())
        # (self, campaign_id, name, beyond_url)
        assert "campaign_id" in params
        assert "name" in params
        assert "beyond_url" in params

    def test_open_path_signature(self):
        import inspect
        with _mock_imports():
            import backend
        sig = inspect.signature(backend.API.open_path)
        params = list(sig.parameters.keys())
        assert "path" in params

    def test_generate_session_title_signature(self):
        import inspect
        with _mock_imports():
            import backend
        sig = inspect.signature(backend.API.generate_session_title)
        params = list(sig.parameters.keys())
        assert "session_id" in params

    def test_download_file_signature(self):
        import inspect
        with _mock_imports():
            import backend
        sig = inspect.signature(backend.API.download_file)
        params = list(sig.parameters.keys())
        assert "path" in params

    def test_download_session_zip_signature(self):
        import inspect
        with _mock_imports():
            import backend
        sig = inspect.signature(backend.API.download_session_zip)
        params = list(sig.parameters.keys())
        assert "session_id" in params

    def test_entity_api_methods_exist(self):
        with _mock_imports():
            import backend
        api_cls = backend.API
        assert callable(getattr(api_cls, "get_entities", None))
        assert callable(getattr(api_cls, "get_entity_detail", None))
        assert callable(getattr(api_cls, "get_entity_relationships", None))
        assert callable(getattr(api_cls, "get_entity_timeline", None))
        assert callable(getattr(api_cls, "migrate_campaign_entities", None))

    def test_digest_api_methods_exist(self):
        with _mock_imports():
            import backend
        api_cls = backend.API
        assert callable(getattr(api_cls, "get_season_digest", None))
        assert callable(getattr(api_cls, "generate_season_digest", None))

    def test_entity_review_api_methods_exist(self):
        with _mock_imports():
            import backend
        api_cls = backend.API
        assert callable(getattr(api_cls, "complete_entity_review", None))
        assert callable(getattr(api_cls, "_request_entity_review", None))
        assert callable(getattr(api_cls, "_strip_confidence", None))
        assert callable(getattr(api_cls, "_strip_confidence_loot", None))
        assert callable(getattr(api_cls, "_stage_to_entity_type", None))
        assert callable(getattr(api_cls, "_compute_entity_diff", None))
