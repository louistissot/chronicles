"""
pywebview API class — all methods callable from JavaScript via window.pywebview.api
"""
import atexit
import json
import re
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import List, Optional

import webview  # type: ignore

from campaigns import (
    add_season as _add_season,
)
from campaigns import (
    get_glossary as _get_glossary,
    merge_glossary as _merge_glossary,
    smart_merge_glossary as _smart_merge_glossary,
    update_glossary as _update_glossary,
)
from campaigns import (
    create_campaign as _create_campaign,
)
from campaigns import (
    delete_campaign as _delete_campaign,
)
from campaigns import (
    get_campaigns as _get_campaigns,
)
from campaigns import (
    update_campaign as _update_campaign,
)
from campaigns import (
    update_season as _update_season,
)
from campaigns import character_names as _extract_char_names
from characters import (
    add_history_entry as _add_history_entry,
    create_character as _create_character,
    delete_character as _delete_character,
    get_character as _get_character,
    get_characters as _get_characters,
    get_characters_by_ids as _get_characters_by_ids,
    get_npcs as _get_npcs,
    set_beyond_data as _set_beyond_data,
    set_history_summary as _set_history_summary,
    update_character as _update_character,
    update_history_manual_text as _update_history_manual_text,
)
from config import (
    get_claude_token,
    get_gemini_token,
    get_hf_token,
    get_openai_token,
    get_pref,
    set_claude_token,
    set_gemini_token,
    set_hf_token,
    set_openai_token,
    set_pref,
)
from llm import stream_llm
from llm_mapper import suggest_mapping as _llm_suggest
from log import get_logger
from postprocess import (
    get_name_mention_segments,
    get_review_samples,
    get_speaker_samples,
    get_speakers,
    load_json,
    save_all,
)
from runner import TranscriptionJob
from sessions import (
    create_session_folder,
    get_campaign_session_count,
    get_sessions,
    register_session,
    update_session,
)
from sessions import (
    delete_session as _delete_session,
)
from entities import (
    ensure_migrated as _ensure_entities_migrated,
    find_entity_by_name as _find_entity,
    find_entity_fuzzy as _find_entity_fuzzy,
    get_entities as _get_entities,
    get_entity as _get_entity,
    get_entity_context_for_llm as _get_entity_context,
    get_entity_timeline as _get_entity_timeline,
    get_relationships as _get_relationships,
    migrate_glossary_to_entities as _migrate_glossary,
    migrate_session_artifacts as _migrate_session_artifacts,
    process_extracted_entities as _process_entities,
    project_to_glossary as _project_glossary,
    create_entity as _create_entity,
    update_entity as _update_entity,
)

_log = get_logger("backend")


class _Recorder:
    """
    Records audio from the default microphone directly to disk.
    Supports pause/resume. Crash-safe: writes raw PCM incrementally;
    atexit handler converts to WAV if the app exits without a clean stop().
    Auto-saves a checkpoint WAV every 20 minutes.
    """

    SAMPLERATE = 16000
    CHANNELS = 1
    DTYPE = "int16"
    BLOCKSIZE = 4096  # ~256ms per block — larger blocks for long recordings
    AUTOSAVE_INTERVAL = 20 * 60  # 20 minutes in seconds

    def __init__(self) -> None:
        self._recording = False
        self._paused = False
        self._thread: Optional[threading.Thread] = None
        self._start_time: float = 0.0
        self._pause_start: float = 0.0
        self._total_paused: float = 0.0
        self._output_path: Optional[Path] = None
        self._raw_path: Optional[Path] = None
        self._raw_file = None
        self._error: Optional[str] = None
        self._last_autosave: float = 0.0
        self._amplitude: float = 0.0
        self._bytes_written: int = 0
        atexit.register(self._atexit_finalize)

    def _atexit_finalize(self) -> None:
        """Called on any app exit — convert raw PCM to WAV if recording was active."""
        if not self._raw_path or not self._raw_path.exists():
            return
        try:
            self._recording = False
            self._paused = False
            if self._raw_file:
                try:
                    self._raw_file.flush()
                    self._raw_file.close()
                except Exception:
                    pass
                self._raw_file = None
            if self._output_path:
                self._raw_to_wav(self._raw_path, self._output_path)
                _log.info("atexit: raw recording saved to %s", self._output_path)
        except Exception as e:
            _log.error("atexit finalize failed: %s", e)

    def _raw_to_wav(self, raw_path: Path, wav_path: Path) -> None:
        raw_data = raw_path.read_bytes()
        with wave.open(str(wav_path), "w") as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(2)  # int16 = 2 bytes
            wf.setframerate(self.SAMPLERATE)
            wf.writeframes(raw_data)
        try:
            raw_path.unlink()
        except Exception:
            pass

    def _autosave_checkpoint(self) -> None:
        """Save a checkpoint WAV without stopping the recording."""
        if not self._raw_path or not self._raw_path.exists() or not self._output_path:
            return
        try:
            # Flush current data
            if self._raw_file:
                self._raw_file.flush()
            checkpoint_path = self._output_path.with_name(
                self._output_path.stem + "_checkpoint.wav"
            )
            raw_data = self._raw_path.read_bytes()
            with wave.open(str(checkpoint_path), "w") as wf:
                wf.setnchannels(self.CHANNELS)
                wf.setsampwidth(2)
                wf.setframerate(self.SAMPLERATE)
                wf.writeframes(raw_data)
            _log.info("Auto-save checkpoint → %s (%d bytes)", checkpoint_path, len(raw_data))
        except Exception as e:
            _log.error("Auto-save checkpoint failed: %s", e)

    def start(self, output_path: Path) -> None:
        import sounddevice as sd  # lazy import
        self._recording = False
        self._paused = False
        self._total_paused = 0.0
        self._pause_start = 0.0
        self._output_path = output_path
        self._raw_path = output_path.with_suffix(".raw")
        self._start_time = 0.0
        self._error = None
        self._last_autosave = 0.0
        self._amplitude = 0.0
        self._bytes_written = 0

        # Open raw file immediately so frames are on disk from the first block
        self._raw_file = open(self._raw_path, "wb")

        ready = threading.Event()

        def _loop():
            try:
                with sd.InputStream(
                    samplerate=self.SAMPLERATE,
                    channels=self.CHANNELS,
                    dtype=self.DTYPE,
                    blocksize=self.BLOCKSIZE,
                ) as stream:
                    self._start_time = time.monotonic()
                    self._last_autosave = time.monotonic()
                    self._recording = True
                    ready.set()
                    while self._recording:
                        data, _ = stream.read(self.BLOCKSIZE)
                        raw = data.tobytes()
                        # When paused, read from stream but discard data
                        if not self._paused and self._raw_file:
                            self._raw_file.write(raw)
                            self._raw_file.flush()
                            self._bytes_written += len(raw)
                        # Compute amplitude for visualization (even when paused)
                        try:
                            import numpy as np
                            arr = np.frombuffer(raw, dtype=np.int16)
                            self._amplitude = float(np.abs(arr).mean()) / 32768.0
                        except Exception:
                            pass
                        # Auto-save checkpoint every 20 minutes
                        now = time.monotonic()
                        if now - self._last_autosave >= self.AUTOSAVE_INTERVAL:
                            self._last_autosave = now
                            self._autosave_checkpoint()
            except Exception as e:
                self._error = str(e)
                ready.set()

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()
        ready.wait(timeout=3)
        if self._error:
            if self._raw_file:
                try:
                    self._raw_file.close()
                except Exception:
                    pass
                self._raw_file = None
            raise RuntimeError(f"Microphone error: {self._error}")

    def pause(self) -> None:
        """Pause recording. Audio stream keeps reading to prevent buffer overflow."""
        if self._recording and not self._paused:
            self._paused = True
            self._pause_start = time.monotonic()
            _log.info("Recording paused")

    def resume(self) -> None:
        """Resume recording after pause."""
        if self._recording and self._paused:
            self._total_paused += time.monotonic() - self._pause_start
            self._paused = False
            _log.info("Recording resumed")

    def stop(self) -> Path:
        if self._paused:
            self._total_paused += time.monotonic() - self._pause_start
            self._paused = False
        self._recording = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._raw_file:
            self._raw_file.flush()
            self._raw_file.close()
            self._raw_file = None
        if not self._raw_path or not self._raw_path.exists():
            raise RuntimeError("No audio recorded.")
        if not self._output_path:
            raise RuntimeError("No output path set.")
        self._raw_to_wav(self._raw_path, self._output_path)
        # Clean up checkpoint file
        checkpoint = self._output_path.with_name(
            self._output_path.stem + "_checkpoint.wav"
        )
        if checkpoint.exists():
            try:
                checkpoint.unlink()
            except Exception:
                pass
        self._raw_path = None
        return self._output_path

    def duration(self) -> float:
        """Active recording duration, excluding paused time."""
        if not self._recording:
            return 0.0
        elapsed = time.monotonic() - self._start_time - self._total_paused
        if self._paused:
            elapsed -= (time.monotonic() - self._pause_start)
        return max(0.0, elapsed)

    def is_recording(self) -> bool:
        return self._recording

    def is_paused(self) -> bool:
        return self._paused

    def get_info(self) -> dict:
        """Return recording info: duration, amplitude (0.0-1.0), file_size_bytes, paused."""
        return {
            "duration": self.duration(),
            "amplitude": self._amplitude,
            "file_size": self._bytes_written,
            "paused": self._paused,
        }


def _get_llm_config() -> tuple:
    provider = get_pref("llm_provider") or "anthropic"
    if provider == "openai":
        api_key = get_openai_token()
        model = get_pref("openai_model") or "gpt-4o"
    else:
        api_key = get_claude_token()
        model = "claude-sonnet-4-6"
    return provider, api_key, model



class API:
    """All public methods are exposed to JavaScript as window.pywebview.api.<method>"""

    def __init__(self, window_ref_holder: list) -> None:
        self._window_ref = window_ref_holder
        self._job: Optional[TranscriptionJob] = None
        self._job_lock = threading.Lock()
        self._recorder = _Recorder()

        # Current session state (set by create_session)
        self._current_session_id: Optional[str] = None
        self._current_session_dir: Optional[Path] = None
        self._current_campaign_id: Optional[str] = None
        self._current_character_names: List[str] = []
        self._current_character_ids: List[str] = []
        self._current_npc_chars: List[dict] = []

        # Pending pipeline state (when speaker mapping needs manual review)
        self._pending_pipeline_json: Optional[str] = None

        # LLM streaming control: stages in this set will stop streaming
        self._stop_llm_stages: set = set()
        # LLM skip control: stages in this set will be skipped entirely
        self._skipped_stages: set = set()

        # Entity review state (human-in-the-loop for low-confidence entities)
        self._pending_entity_reviews = {}  # type: Dict[str, threading.Event]
        self._entity_review_decisions = {}  # type: Dict[str, list]

        # Fact review state (human-in-the-loop for extracted facts)
        self._pending_fact_review = None  # type: Optional[threading.Event]
        self._fact_review_decisions = []  # type: List[dict]

    @property
    def _window(self) -> Optional[webview.Window]:
        return self._window_ref[0] if self._window_ref else None

    def _js(self, script: str) -> None:
        w = self._window
        if w:
            w.evaluate_js(script)

    def _notify_stage(self, stage: str, status: str, data) -> None:
        """Push a pipeline stage update to the frontend."""
        data_json = json.dumps(data) if data is not None else "null"
        self._js(
            f"window._onPipelineStage && window._onPipelineStage"
            f"('{stage}', '{status}', {data_json})"
        )

    # ── Session lifecycle ─────────────────────────────────────────────────────

    def create_session(
        self,
        campaign_id: str,
        season_id: str,
        date_override: Optional[str] = None,
    ) -> dict:
        """
        Create a timestamped session folder and register the session.
        date_override — optional YYYY-MM-DD string for importing past transcripts.
        Returns {ok, session_dir, session_id}.
        """
        _log.info("create_session  campaign=%s  season=%s  date=%s", campaign_id, season_id, date_override)
        try:
            campaigns = _get_campaigns()
            campaign = next((c for c in campaigns if c["id"] == campaign_id), None)
            if not campaign:
                return {"ok": False, "error": "Campaign not found"}
            season = next((s for s in campaign["seasons"] if s["id"] == season_id), None)
            if not season:
                return {"ok": False, "error": "Season not found"}

            folder = create_session_folder(campaign["name"], season["number"], date_override=date_override)
            character_names = _extract_char_names(season["characters"])
            # DM is always present in sessions — auto-include if missing
            if not any(n.lower() in ("dm", "dungeon master") for n in character_names):
                character_names = ["DM"] + character_names

            session_id = register_session(
                campaign_id=campaign_id,
                campaign_name=campaign["name"],
                season_id=season_id,
                season_number=season["number"],
                session_dir=str(folder),
                character_names=character_names,
                date_override=date_override,
            )
            self._current_session_id = session_id
            self._current_session_dir = folder
            self._current_campaign_id = campaign_id
            self._current_character_names = character_names
            self._current_character_ids = season["characters"]
            update_session(session_id, character_ids=list(season["characters"]))

            _log.info("Session created  id=%s  dir=%s", session_id, folder)
            return {"ok": True, "session_dir": str(folder), "session_id": session_id}
        except Exception as e:
            _log.error("create_session failed: %s", e, exc_info=True)
            return {"ok": False, "error": str(e)}

    def copy_audio_to_session(self, audio_path: str, session_dir: str) -> dict:
        """Copy an uploaded audio file into the session folder."""
        _log.info("copy_audio_to_session  src=%s  dst_dir=%s", audio_path, session_dir)
        try:
            src = Path(audio_path)
            dst = Path(session_dir) / src.name
            if src == dst:
                return {"ok": True, "path": str(dst)}
            shutil.copy2(str(src), str(dst))
            if self._current_session_id:
                update_session(self._current_session_id, audio_path=str(dst))
            _log.info("Audio copied → %s", dst)
            return {"ok": True, "path": str(dst)}
        except Exception as e:
            _log.error("copy_audio_to_session failed: %s", e)
            return {"ok": False, "error": str(e)}

    # ── Dialogs ──────────────────────────────────────────────────────────────
    # NOTE: pywebview's create_file_dialog cannot be called from js_api handlers
    # (they run on a background thread). We use osascript instead, which works
    # from any thread and shows a native macOS file picker.

    @staticmethod
    def _osascript_pick(prompt: str, file_types: list[str]) -> Optional[str]:
        """Show a native macOS open-file dialog via osascript. Thread-safe."""
        type_list = ", ".join(f'"{t}"' for t in file_types)
        script = f'''
try
    set f to (choose file with prompt "{prompt}" of type {{{type_list}}})
    return POSIX path of f
on error
    return ""
end try
'''
        try:
            r = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=300,
            )
            path = r.stdout.strip()
            return path if path else None
        except Exception as e:
            _log.error("osascript pick failed: %s", e)
            return None

    def pick_audio_file(self) -> Optional[str]:
        _log.debug("pick_audio_file called")
        picked = self._osascript_pick(
            "Select an audio recording",
            ["m4a", "mp3", "wav", "ogg", "flac", "aac", "wma"],
        )
        _log.info("pick_audio_file → %s", picked or "(cancelled)")
        return picked

    def pick_transcript_file(self) -> Optional[str]:
        _log.debug("pick_transcript_file called")
        picked = self._osascript_pick(
            "Select a transcript file",
            ["json", "txt", "srt"],
        )
        _log.info("pick_transcript_file → %s", picked or "(cancelled)")
        return picked

    def pick_character_portrait(self) -> Optional[str]:
        _log.debug("pick_character_portrait called")
        picked = self._osascript_pick(
            "Select a character portrait",
            ["png", "jpg", "jpeg", "gif", "webp", "bmp", "tiff"],
        )
        _log.info("pick_character_portrait → %s", picked or "(cancelled)")
        return picked

    # ── Tokens / settings ────────────────────────────────────────────────────

    def get_hf_token(self) -> str:
        val = get_hf_token() or ""
        _log.debug("get_hf_token → %s", "set" if val else "empty")
        return val

    def set_hf_token(self, token: str) -> None:
        _log.info("set_hf_token (len=%d)", len(token))
        set_hf_token(token)

    def get_claude_token(self) -> str:
        val = get_claude_token() or ""
        _log.debug("get_claude_token → %s", "set" if val else "empty")
        return val

    def set_claude_token(self, token: str) -> None:
        _log.info("set_claude_token (len=%d)", len(token))
        set_claude_token(token)

    def get_openai_token(self) -> str:
        val = get_openai_token() or ""
        _log.debug("get_openai_token → %s", "set" if val else "empty")
        return val

    def set_openai_token(self, token: str) -> None:
        _log.info("set_openai_token (len=%d)", len(token))
        set_openai_token(token)

    def get_gemini_token(self) -> str:
        val = get_gemini_token() or ""
        _log.debug("get_gemini_token → %s", "set" if val else "empty")
        return val

    def set_gemini_token(self, token: str) -> None:
        _log.info("set_gemini_token (len=%d)", len(token))
        set_gemini_token(token)

    def get_pref(self, key: str, fallback: str = "") -> str:
        val = get_pref(key) or fallback
        _log.debug("get_pref  key=%s → %r", key, val)
        return val

    def set_pref(self, key: str, value: str) -> None:
        _log.debug("set_pref  key=%s  value=%r", key, value)
        set_pref(key, value)

    # ── Audio recording ───────────────────────────────────────────────────────

    def start_recording(self, session_dir: str) -> dict:
        if self._recorder.is_recording():
            _log.warning("start_recording called but already recording")
            return {"ok": False, "error": "Already recording."}
        try:
            path = Path(session_dir) / "recording.wav"
            self._recorder.start(path)
            if self._current_session_id:
                update_session(self._current_session_id, audio_path=str(path))
            _log.info("Recording started → %s", path)
            return {"ok": True, "path": str(path)}
        except Exception as e:
            _log.error("start_recording failed: %s", e, exc_info=True)
            return {"ok": False, "error": str(e)}

    def stop_recording(self) -> dict:
        if not self._recorder.is_recording():
            _log.warning("stop_recording called but not recording")
            return {"ok": False, "error": "Not recording."}
        try:
            path = self._recorder.stop()
            size_mb = path.stat().st_size / 1_048_576
            _log.info("Recording stopped → %s (%.2f MB)", path, size_mb)
            return {"ok": True, "path": str(path)}
        except Exception as e:
            _log.error("stop_recording failed: %s", e, exc_info=True)
            return {"ok": False, "error": str(e)}

    def get_recording_duration(self) -> float:
        return self._recorder.duration()

    def get_recording_info(self) -> dict:
        if not self._recorder.is_recording():
            return {"duration": 0, "amplitude": 0, "file_size": 0, "paused": False}
        return self._recorder.get_info()

    def pause_recording(self) -> dict:
        if not self._recorder.is_recording():
            return {"ok": False, "error": "Not recording."}
        if self._recorder.is_paused():
            return {"ok": False, "error": "Already paused."}
        try:
            self._recorder.pause()
            return {"ok": True}
        except Exception as e:
            _log.error("pause_recording failed: %s", e, exc_info=True)
            return {"ok": False, "error": str(e)}

    def resume_recording(self) -> dict:
        if not self._recorder.is_recording():
            return {"ok": False, "error": "Not recording."}
        if not self._recorder.is_paused():
            return {"ok": False, "error": "Not paused."}
        try:
            self._recorder.resume()
            return {"ok": True}
        except Exception as e:
            _log.error("resume_recording failed: %s", e, exc_info=True)
            return {"ok": False, "error": str(e)}

    def is_recording_paused(self) -> bool:
        return self._recorder.is_paused()

    # ── Transcription job ────────────────────────────────────────────────────

    def start_job(
        self,
        audio_path: str,
        model: str,
        num_speakers: int,
        character_names: list,
        language: str = "auto",
    ) -> dict:
        # Use current session dir; fall back to audio file's own folder so output
        # always lands next to the audio even if session state was lost on restart.
        if self._current_session_dir:
            output_dir = str(self._current_session_dir)
        else:
            output_dir = str(Path(audio_path).parent)

        _log.info(
            "start_job  audio=%s  model=%s  speakers=%d  language=%s  output=%s",
            audio_path, model, num_speakers, language, output_dir,
        )
        hf_token = get_hf_token()
        if not hf_token:
            _log.error("start_job aborted: HuggingFace token not set")
            return {"ok": False, "error": "HuggingFace token not set. Check Settings."}

        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            return {"ok": False, "error": f"Cannot create output folder: {e}"}

        # Store character names for auto-pipeline
        self._current_character_names = character_names

        with self._job_lock:
            if self._job and self._job.is_running():
                return {"ok": False, "error": "A transcription job is already running."}

            def on_line(line: str, is_stderr: bool = False) -> None:
                safe = line.replace("\\", "\\\\").replace("`", "\\`").replace("'", "\\'")
                self._js(
                    f"if(window._receiveLog) window._receiveLog(`{safe}`, {'true' if is_stderr else 'false'})"
                )

            def on_done(success: bool, json_path) -> None:
                if success and json_path:
                    _log.info("Transcription done → %s", json_path)
                    if self._current_session_id:
                        update_session(self._current_session_id, json_path=str(json_path))
                    self._notify_stage("transcription", "done", None)
                    # Kick off the automated post-processing pipeline
                    threading.Thread(
                        target=self._auto_pipeline,
                        args=(Path(json_path),),
                        daemon=True,
                    ).start()
                else:
                    _log.error("Transcription failed")
                    self._notify_stage("transcription", "error", {"error": "Transcription failed"})

            self._job = TranscriptionJob(
                audio_path=audio_path,
                output_dir=output_dir,
                model=model,
                num_speakers=num_speakers,
                hf_token=hf_token,
                on_line=on_line,
                on_done=on_done,
                language=language,
            )
            self._notify_stage("transcription", "running", None)
            self._job.start()

        return {"ok": True}

    def stop_job(self) -> None:
        _log.info("stop_job requested")
        with self._job_lock:
            if self._job:
                self._job.stop()

    def retry_transcription(self, session_id, model=None, language=None):
        # type: (str, Optional[str], Optional[str]) -> dict
        """Re-trigger transcription for an existing session that has audio but no transcript."""
        _log.info("retry_transcription  session_id=%s  model=%s  language=%s", session_id, model, language)
        try:
            session = next((s for s in get_sessions() if s.get("id") == session_id), None)
            if not session:
                return {"ok": False, "error": "Session not found"}

            audio_path = session.get("audio_path", "")
            if not audio_path or not Path(audio_path).exists():
                return {"ok": False, "error": "Audio file not found on disk"}

            # Restore session context
            self._current_session_id = session_id
            self._current_session_dir = Path(session.get("output_dir", ""))
            self._current_campaign_id = session.get("campaign_id", "")

            # Restore character names from session
            char_names = list(session.get("character_names", []))

            # Resolve character IDs from season
            self._current_character_ids = []
            season_id = session.get("season_id", "")
            if season_id and self._current_campaign_id:
                try:
                    for camp in _get_campaigns():
                        if camp["id"] == self._current_campaign_id:
                            for s in camp.get("seasons", []):
                                if s["id"] == season_id:
                                    self._current_character_ids = s.get("characters", [])
                                    # Rebuild char names from IDs if session didn't have them
                                    if not char_names:
                                        for cid in self._current_character_ids:
                                            ch = _get_character(cid)
                                            if ch:
                                                char_names.append(ch.get("name", ""))
                                    break
                            break
                except Exception:
                    pass
            self._current_character_names = [n for n in char_names if n]

            # Use passed-in values or fall back to saved prefs
            if not model:
                model = get_pref("whisperx_model", "") or get_pref("model", "large-v2")
            if not language:
                language = get_pref("whisperx_language", "") or get_pref("language", "auto")
            num_speakers = max(1, len(self._current_character_names))

            return self.start_job(audio_path, model, num_speakers,
                                  self._current_character_names, language)
        except Exception as e:
            _log.error("retry_transcription failed: %s", e)
            return {"ok": False, "error": str(e)}

    def start_pipeline_from_transcript(self, transcript_path: str, diarized: bool = True) -> dict:
        """
        Import an existing transcript file and run the appropriate pipeline stages.

        - .json (WhisperX format): transcription marked done → speaker mapping → save → DM notes → scenes
        - .txt / .srt (already processed): transcription + speaker_mapping + saving_transcript marked
          done immediately → DM notes → scenes

        Args:
            transcript_path: Path to the transcript file.
            diarized: Whether the transcript includes speaker diarization.
                      When False, speaker mapping is skipped entirely.
        """
        _log.info("start_pipeline_from_transcript  path=%s  diarized=%s", transcript_path, diarized)
        try:
            src = Path(transcript_path)
            if not src.exists():
                return {"ok": False, "error": f"File not found: {transcript_path}"}

            # Copy into session dir if we have one and the file isn't already there
            if self._current_session_dir:
                dst = self._current_session_dir / src.name
                if src.resolve() != dst.resolve():
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(str(src), str(dst))
                    _log.info("Transcript copied → %s", dst)
                path = dst
            else:
                path = src

            ext = path.suffix.lower()

            if ext == ".json":
                # WhisperX JSON — run full post-transcription pipeline
                if self._current_session_id:
                    update_session(self._current_session_id, json_path=str(path))
                self._notify_stage("transcription", "done", {"imported": True})
                threading.Thread(
                    target=self._auto_pipeline,
                    args=(path,),
                    kwargs={"diarized": diarized},
                    daemon=True,
                ).start()

            else:
                # Already-labeled .txt or .srt — skip straight to DM notes & scenes
                txt_path = path if ext == ".txt" else None
                if self._current_session_id and txt_path:
                    update_session(self._current_session_id, txt_path=str(txt_path))

                # New stage order: transcription → saving_transcript → speaker_mapping
                self._notify_stage("transcription", "done", {"imported": True})
                self._notify_stage("saving_transcript", "done", {
                    "jsonPath": None,
                    "txtPath": str(txt_path) if txt_path else None,
                    "srtPath": str(path) if ext == ".srt" else None,
                })
                self._notify_stage("speaker_mapping", "done", {"imported": True})
                self._notify_stage("updating_transcript", "done", {"imported": True})

                if txt_path:
                    threading.Thread(
                        target=self._run_dm_and_scenes,
                        args=(str(txt_path),),
                        daemon=True,
                    ).start()
                else:
                    # SRT only — can still try DM notes/scenes but transcript text is limited
                    self._notify_stage("summary", "error", {
                        "error": "Summary requires a .txt transcript. Re-import as .txt or run from audio."
                    })
                    self._notify_stage("dm_notes", "error", {
                        "error": "DM notes require a .txt transcript. Re-import as .txt or run from audio."
                    })
                    self._notify_stage("scenes", "error", {
                        "error": "Scene extraction requires a .txt transcript."
                    })
                    self._notify_stage("timeline", "error", {
                        "error": "Timeline requires a .txt transcript."
                    })

            return {"ok": True}
        except Exception as e:
            _log.error("start_pipeline_from_transcript failed: %s", e, exc_info=True)
            return {"ok": False, "error": str(e)}

    def _run_dm_and_scenes(self, txt_path: str) -> None:
        """Run DM notes and scene extraction on an already-saved transcript."""
        self._run_llm_stages(txt_path, self._current_character_names or [])

    # ── Automated pipeline ────────────────────────────────────────────────────

    def _auto_pipeline(self, json_path: Path, diarized: bool = True) -> None:
        """
        Runs automatically after transcription completes:
        1. Save raw transcript JSON path → saving_transcript done
        2. Speaker mapping via LLM → speaker_mapping done/needs_review
        3. Apply mapping → updating_transcript done (in _continue_pipeline)
        4. LLM stages: timeline → summary → dm_notes → scenes

        Args:
            json_path: Path to the WhisperX JSON transcript.
            diarized: Whether the transcript includes speaker diarization.
                      When False, speaker mapping is skipped.
        """
        character_names = self._current_character_names or []
        _log.info("Auto-pipeline starting  json=%s  chars=%s  diarized=%s", json_path, character_names, diarized)

        # ── Step 1: Register raw transcript ──────────────────────────────────
        self._notify_stage("saving_transcript", "running", None)
        if self._current_session_id:
            update_session(self._current_session_id, json_path=str(json_path))
        self._notify_stage("saving_transcript", "done", {
            "jsonPath": str(json_path),
        })
        _log.info("Raw transcript registered → %s", json_path)

        # ── Step 1b: Transcript correction (glossary-aware) ──────────────────
        self._notify_stage("transcript_correction", "running", None)
        try:
            glossary_terms = []  # type: List[str]
            if self._current_campaign_id:
                try:
                    gl = _get_glossary(self._current_campaign_id)
                    glossary_terms = list(gl.keys()) if gl else []
                except Exception:
                    pass
                # Also include NPC names and location names (since they're no longer in glossary)
                try:
                    npc_names = [c.get("name", "") for c in _get_npcs(self._current_campaign_id) if c.get("name")]
                    glossary_terms.extend(npc_names)
                except Exception:
                    pass
                try:
                    loc_entities = _get_entities(self._current_campaign_id, "location")
                    loc_names = [e.get("name", "") for e in loc_entities if e.get("name")]
                    glossary_terms.extend(loc_names)
                except Exception:
                    pass

            if glossary_terms or character_names:
                from postprocess import correct_transcript_terms, load_json as _load_json
                raw_data = _load_json(str(json_path))
                corrected_data, corrections = correct_transcript_terms(
                    raw_data, glossary_terms, character_names
                )
                if corrections:
                    # Overwrite the JSON with corrected version
                    json_path.write_text(
                        json.dumps(corrected_data, indent=2, ensure_ascii=False),
                        encoding="utf-8"
                    )
                    _log.info("Transcript correction: %d terms fixed — %s",
                              len(corrections), corrections)
                    self._notify_stage("transcript_correction", "done", {
                        "corrections": corrections,
                        "count": len(corrections),
                    })
                else:
                    _log.info("Transcript correction: no corrections needed")
                    self._notify_stage("transcript_correction", "done", {
                        "corrections": {},
                        "count": 0,
                    })
            else:
                _log.info("Transcript correction: skipped (no glossary or character names)")
                self._notify_stage("transcript_correction", "done", {"skipped": True})
        except Exception as e:
            _log.warning("Transcript correction failed (non-fatal): %s", e)
            self._notify_stage("transcript_correction", "done", {"skipped": True, "error": str(e)})

        # ── Step 2: Speaker mapping ──────────────────────────────────────────

        # Skip speaker mapping for non-diarized transcripts
        if not diarized:
            _log.info("Non-diarized transcript — skipping speaker mapping")
            self._notify_stage("speaker_mapping", "done", {"skipped": True, "reason": "no_diarization"})
            self._continue_pipeline(json_path, {})
            return

        self._notify_stage("speaker_mapping", "running", None)
        try:
            provider, api_key, model = _get_llm_config()
            if not api_key:
                raise RuntimeError(
                    "LLM API key not set — go to Settings to add your Claude or OpenAI key."
                )
            data = load_json(str(json_path))
            samples = get_speaker_samples(data)
            if not samples:
                # No speakers found — skip mapping and proceed
                _log.info("No speakers detected in transcript — skipping speaker mapping")
                self._notify_stage("speaker_mapping", "done", {"skipped": True, "reason": "no_speakers"})
                self._continue_pipeline(json_path, {})
                return
            name_mentions = get_name_mention_segments(data, character_names)

            stage = "speaker_mapping"
            self._stop_llm_stages.discard(stage)

            def _sm_chunk(text: str) -> None:
                escaped = json.dumps(text)
                self._js(f"window._onLLMChunk && window._onLLMChunk('{stage}', {escaped})")

            def _sm_stop() -> bool:
                return stage in self._stop_llm_stages

            # Build character detail context for better speaker identification
            char_details = None  # type: Optional[dict]
            if character_names and self._current_character_ids:
                try:
                    chars = _get_characters_by_ids(self._current_character_ids)
                    char_details = {}
                    for ch in chars:
                        bd = ch.get("beyond_data") or {}
                        detail = {
                            "race": ch.get("race", ""),
                            "class_name": ch.get("class_name", ""),
                            "backstory": bd.get("backstory", ""),
                            "personality_traits": bd.get("personality_traits", ""),
                            "spells": bd.get("spells", []),
                            "equipment": bd.get("equipment", []),
                        }  # type: dict
                        # Add history context
                        if ch.get("history_summary"):
                            detail["history_summary"] = ch["history_summary"]
                        history = ch.get("history", [])
                        if history:
                            recent = [
                                e.get("auto_text", "")
                                for e in history[-3:]
                                if e.get("auto_text")
                            ]
                            if recent:
                                detail["recent_events"] = recent
                        char_details[ch["name"]] = detail
                except Exception as e:
                    _log.warning("Could not load character details for speaker mapping: %s", e)

            # Build glossary context for speaker identification
            glossary_context = None  # type: Optional[str]
            if self._current_campaign_id:
                try:
                    glossary = _get_glossary(self._current_campaign_id)
                    if glossary:
                        terms = sorted(glossary.keys())[:50]
                        parts = []
                        for t in terms:
                            cat = glossary[t].get("category", "")
                            defn = glossary[t].get("definition", "")
                            if defn:
                                parts.append("  {} ({}): {}".format(t, cat, defn))
                            else:
                                parts.append("  {} ({})".format(t, cat))
                        glossary_context = "\n".join(parts)
                except Exception as e:
                    _log.warning("Could not load glossary for speaker mapping: %s", e)

            # Build review-quality samples for manual review UI
            glossary_term_list = list(_get_glossary(self._current_campaign_id).keys()) if self._current_campaign_id else []
            review_samples = get_review_samples(data, character_names, glossary_terms=glossary_term_list)

            CONFIDENCE_THRESHOLD = 90
            mapping, confidences, evidence = _llm_suggest(
                samples, character_names, api_key,
                provider=provider, model=model,
                on_chunk=_sm_chunk, stop_check=_sm_stop,
                name_mentions=name_mentions,
                character_details=char_details,
                glossary_context=glossary_context,
            )

            if stage in self._stop_llm_stages:
                # Stopped by user — fall back to manual review
                _log.info("Speaker mapping stopped by user")
                try:
                    all_speakers = get_speakers(load_json(str(json_path)))
                except Exception:
                    all_speakers = []
                self._pending_pipeline_json = str(json_path)
                self._notify_stage("speaker_mapping", "needs_review", {
                    "jsonPath": str(json_path),
                    "partialMapping": mapping if mapping else {},
                    "unmappedSpeakers": all_speakers,
                    "characterNames": character_names,
                    "sampleLines": review_samples,
                    "confidences": confidences if confidences else {},
                    "evidence": evidence if evidence else {},
                    "error": "Stopped by user — please assign speakers manually.",
                })
                return

            # Check for low-confidence speakers and retry with more samples
            low_conf = [
                sp for sp, conf in confidences.items()
                if conf < CONFIDENCE_THRESHOLD and mapping.get(sp) != "Unknown"
            ]
            if low_conf and not _sm_stop():
                _log.info("Low confidence speakers %s (scores: %s) — retrying with more samples",
                          low_conf, {sp: confidences[sp] for sp in low_conf})
                extra_samples = get_speaker_samples(data, n_samples=15)
                retry_mapping, retry_conf, retry_evidence = _llm_suggest(
                    samples, character_names, api_key,
                    provider=provider, model=model,
                    on_chunk=_sm_chunk, stop_check=_sm_stop,
                    name_mentions=name_mentions,
                    extra_samples={sp: extra_samples.get(sp, []) for sp in low_conf},
                    character_details=char_details,
                    glossary_context=glossary_context,
                )
                # Merge: use retry results for low-conf speakers if improved
                for sp in low_conf:
                    if sp in retry_conf and retry_conf[sp] >= confidences.get(sp, 0):
                        mapping[sp] = retry_mapping[sp]
                        confidences[sp] = retry_conf[sp]
                        evidence[sp] = retry_evidence.get(sp, "")
                _log.info("After retry — confidences: %s", confidences)

            # Always send to review — let user confirm/adjust all mappings
            all_speakers = list(mapping.keys())
            _log.info("Speaker mapping done — sending all %d speakers for review: %s",
                       len(all_speakers), mapping)
            self._pending_pipeline_json = str(json_path)
            self._notify_stage("speaker_mapping", "needs_review", {
                "jsonPath": str(json_path),
                "partialMapping": mapping,
                "unmappedSpeakers": all_speakers,
                "characterNames": character_names,
                "sampleLines": review_samples,
                "confidences": confidences,
                "evidence": evidence,
            })
            return  # resumed via complete_speaker_mapping()

        except Exception as e:
            _log.error("Speaker mapping failed: %s", e, exc_info=True)
            ex_samples = {}  # type: dict
            try:
                data = load_json(str(json_path))
                all_speakers = get_speakers(data)
                gl_terms = list(_get_glossary(self._current_campaign_id).keys()) if self._current_campaign_id else []
                ex_samples = get_review_samples(data, character_names, glossary_terms=gl_terms)
            except Exception:
                all_speakers = []
            self._pending_pipeline_json = str(json_path)
            self._notify_stage("speaker_mapping", "needs_review", {
                "jsonPath": str(json_path),
                "partialMapping": {},
                "unmappedSpeakers": all_speakers,
                "characterNames": character_names,
                "sampleLines": ex_samples,
                "error": str(e),
            })
            return

    def _continue_pipeline(self, json_path: Path, mapping: dict) -> None:
        """Apply speaker mapping → save labeled transcript → run LLM stages.

        Called after speaker mapping completes (either auto or manual review).
        """
        character_names = self._current_character_names or []

        # ── Guard: JSON file must exist ──────────────────────────────────────
        if not json_path.exists():
            _log.error("Transcript JSON not found: %s", json_path)
            self._notify_stage("updating_transcript", "error", {
                "error": f"Transcript file not found: {json_path}. Re-import the file to reprocess."
            })
            return

        # ── Speaker mapping confirmed ────────────────────────────────────────
        self._notify_stage("speaker_mapping", "done", {"mapping": mapping})

        # ── Apply mapping and save labeled .txt / .srt ───────────────────────
        self._notify_stage("updating_transcript", "running", None)
        try:
            fmt = get_pref("output_format") or "both"
            write_txt = fmt in ("both", "txt")
            write_srt = fmt in ("both", "srt")
            txt_path, srt_path = save_all(
                str(json_path), mapping, json_path.parent,
                write_txt=write_txt, do_srt=write_srt,
            )
            if self._current_session_id:
                update_session(
                    self._current_session_id,
                    txt_path=str(txt_path) if txt_path else None,
                    srt_path=str(srt_path) if srt_path else None,
                )
            _log.info("Labeled transcript saved → txt=%s  srt=%s", txt_path, srt_path)
            self._notify_stage("updating_transcript", "done", {
                "txtPath": str(txt_path) if txt_path else None,
                "srtPath": str(srt_path) if srt_path else None,
            })
        except Exception as e:
            _log.error("save_labeled_transcript failed: %s", e, exc_info=True)
            self._notify_stage("updating_transcript", "error", {"error": f"Failed to save transcript: {e}"})
            return

        if not txt_path:
            self._notify_stage("timeline", "error", {"error": "No text transcript produced"})
            self._notify_stage("summary", "error", {"error": "No text transcript produced"})
            self._notify_stage("dm_notes", "error", {"error": "No text transcript produced"})
            self._notify_stage("scenes", "error", {"error": "No text transcript produced"})
            return

        # ── Fact extraction (LLM) + Fact review (human-in-the-loop) ────
        if "fact_extraction" not in self._skipped_stages:
            try:
                transcript_text = Path(txt_path).read_text(encoding="utf-8")
                self._notify_stage("fact_extraction", "running", None)
                raw = self._generate_fact_extraction_streaming(
                    str(txt_path), character_names, transcript=transcript_text,
                )
                facts = self._repair_json_array(raw)
                if not facts:
                    raise ValueError("Could not parse facts JSON from LLM output")

                # Assign UUIDs to facts that don't have them
                import uuid as _uuid
                for f in facts:
                    if not f.get("id"):
                        f["id"] = str(_uuid.uuid4())

                # Save raw facts
                out_dir = json_path.parent
                facts_path = out_dir / "facts.json"
                facts_path.write_text(
                    json.dumps(facts, indent=2, ensure_ascii=False),
                    encoding="utf-8",
                )
                if self._current_session_id:
                    update_session(self._current_session_id, facts_path=str(facts_path))

                # Adaptive confidence threshold
                threshold = self._get_fact_review_threshold()
                auto_applied = [f for f in facts if f.get("confidence", 0) >= threshold]
                review_queue = [f for f in facts if f.get("confidence", 0) < threshold]

                _log.info(
                    "Fact extraction done — %d facts, threshold=%d, "
                    "%d auto-applied, %d need review",
                    len(facts), threshold, len(auto_applied), len(review_queue),
                )
                self._notify_stage("fact_extraction", "done", {
                    "factCount": len(facts),
                    "reviewCount": len(review_queue),
                    "threshold": threshold,
                })

                # Fact review (human-in-the-loop)
                if "fact_review" not in self._skipped_stages:
                    corrections, name_corrections = self._request_fact_review(
                        review_queue, auto_applied, str(json_path), mapping, str(txt_path),
                    )
                    if corrections:
                        from postprocess import apply_fact_corrections
                        new_txt, new_srt = apply_fact_corrections(
                            str(json_path), mapping, corrections,
                            json_path.parent,
                        )
                        if new_txt:
                            txt_path = new_txt
                            if self._current_session_id:
                                update_session(
                                    self._current_session_id,
                                    txt_path=str(new_txt),
                                    srt_path=str(new_srt) if new_srt else None,
                                )
                            _log.info("Transcript corrected from fact review → %s", new_txt)
                    # Apply name corrections (find/replace in transcript text)
                    if name_corrections:
                        try:
                            txt_content = Path(txt_path).read_text(encoding="utf-8")
                            for old_name, new_name in name_corrections.items():
                                txt_content = txt_content.replace(old_name, new_name)
                            Path(txt_path).write_text(txt_content, encoding="utf-8")
                            _log.info("Applied %d name correction(s) to transcript: %s",
                                      len(name_corrections), name_corrections)
                            # Inject corrections into glossary context for downstream stages
                            notes = "\n".join(
                                "Note: '{}' is correctly spelled '{}'".format(old, new)
                                for old, new in name_corrections.items()
                            )
                            self._name_corrections = name_corrections
                            # Prepend to glossary context so all LLM stages see it
                            existing_ctx = getattr(self, '_glossary_context', '') or ''
                            self._glossary_context = "\n" + notes + existing_ctx
                        except Exception as e:
                            _log.error("Failed to apply name corrections: %s", e)
                else:
                    self._notify_stage("fact_review", "done", {"skipped": True})

            except Exception as e:
                _log.error("Fact extraction failed: %s", e, exc_info=True)
                self._notify_stage("fact_extraction", "error", {"error": str(e)})
                # Continue anyway — don't block the pipeline on extraction errors
        else:
            self._notify_stage("fact_extraction", "done", {"skipped": True})
            self._notify_stage("fact_review", "done", {"skipped": True})

        # Build facts-as-context for downstream LLM stages
        self._facts_context = ""
        try:
            facts_file = txt_path.parent / "facts.json"
            if facts_file.exists():
                all_facts = json.loads(facts_file.read_text(encoding="utf-8"))
                # Only include accepted/high-confidence facts
                relevant = [f for f in all_facts if f.get("confidence", 0) >= 70]
                if relevant:
                    lines = []
                    for f in relevant:
                        who = f.get("who", "")
                        what = f.get("what", "")
                        when = f.get("when", "")
                        ftype = f.get("type", "")
                        line = "- [{type}] {who}: {what}".format(type=ftype, who=who, what=what)
                        if when:
                            line += " (when: {})".format(when)
                        lines.append(line)
                    self._facts_context = "\n\n## Key Events Summary (extracted facts)\n" + "\n".join(lines)
                    _log.info("Facts context built (%d facts, %d chars)", len(relevant), len(self._facts_context))
        except Exception as e:
            _log.warning("Could not build facts context: %s", e)

        self._run_llm_stages(str(txt_path), character_names)

    def complete_speaker_mapping(self, json_path: str, mapping: dict) -> dict:
        """
        Called from the frontend when the user finishes manually assigning
        the speakers that the LLM couldn't identify. Resumes the pipeline.
        Note: speaker_mapping 'done' is emitted by _continue_pipeline after saving files.
        """
        _log.info("complete_speaker_mapping  json=%s  mapping=%s", json_path, mapping)
        self._pending_pipeline_json = None
        threading.Thread(
            target=self._continue_pipeline,
            args=(Path(json_path), mapping),
            daemon=True,
        ).start()
        return {"ok": True}

    def complete_fact_review(self, decisions):
        # type: (list) -> dict
        """Resume pipeline after user reviews/edits extracted facts.

        decisions: list of {id, action: 'accept'|'edit'|'decline', edited?: {...}}
        """
        _log.info("complete_fact_review  decisions=%d", len(decisions))
        self._fact_review_decisions = decisions
        event = self._pending_fact_review
        if event:
            event.set()
        return {"ok": True}

    def _get_fact_review_threshold(self):
        # type: () -> int
        """Adaptive confidence threshold based on completed campaign sessions."""
        if not self._current_campaign_id:
            return 0  # review everything if no campaign
        count = get_campaign_session_count(self._current_campaign_id)
        if count <= 1:
            return 101  # review ALL facts (nothing can be >= 101)
        elif count == 2:
            return 98
        elif count == 3:
            return 95
        else:
            return 90

    def _request_fact_review(self, review_queue, auto_applied, json_path, mapping, txt_path):
        # type: (list, list, str, dict, str) -> list
        """Block pipeline until user reviews extracted facts. Returns speaker corrections."""
        cards = []
        for fact in review_queue:
            cards.append({
                "id": fact.get("id", ""),
                "type": fact.get("type", "event"),
                "who": fact.get("who", ""),
                "what": fact.get("what", ""),
                "why": fact.get("why", ""),
                "when": fact.get("when", ""),
                "speaker": fact.get("speaker", ""),
                "segment_indices": fact.get("segment_indices", []),
                "original_text": fact.get("original_text", ""),
                "confidence": fact.get("confidence", 50),
                "reasoning": fact.get("reasoning", ""),
            })

        auto_summary = []
        for fact in auto_applied:
            auto_summary.append({
                "id": fact.get("id", ""),
                "who": fact.get("who", ""),
                "what": fact.get("what", ""),
                "confidence": fact.get("confidence", 100),
            })

        review_payload = {
            "stage": "fact_review",
            "cards": cards,
            "auto_applied": auto_summary,
            "json_path": json_path,
            "txt_path": txt_path,
            "character_names": self._current_character_names or [],
        }

        self._pending_fact_review = threading.Event()
        self._fact_review_decisions = []

        self._notify_stage("fact_review", "needs_review", review_payload)
        _log.info(
            "Fact review requested — %d cards, %d auto-applied. Waiting for DM...",
            len(cards), len(auto_summary),
        )
        self._pending_fact_review.wait()

        decisions = list(self._fact_review_decisions)
        self._pending_fact_review = None
        self._fact_review_decisions = []

        _log.info("Fact review completed — %d decisions", len(decisions))
        self._notify_stage("fact_review", "done", {"decisions": len(decisions)})

        # Extract speaker corrections from edited facts
        corrections = []  # type: List[dict]
        name_corrections = {}  # type: Dict[str, str]  # old_name -> new_name
        for d in decisions:
            if d.get("action") == "decline":
                continue
            edited = d.get("edited") or {}
            # Collect name corrections (who field edits)
            original_who = d.get("who", "")
            edited_who = edited.get("who", "")
            if edited_who and original_who and edited_who != original_who:
                name_corrections[original_who] = edited_who
            segment_indices = d.get("segment_indices", [])
            if not segment_indices:
                continue
            correction = {"segment_indices": segment_indices}
            has_change = False
            if edited.get("corrected_speaker"):
                correction["corrected_speaker"] = edited["corrected_speaker"]
                has_change = True
            if edited.get("corrected_text"):
                correction["corrected_text"] = edited["corrected_text"]
                has_change = True
            # Also handle speaker correction from the 'speaker' field edit
            if edited.get("speaker") and edited["speaker"] != d.get("speaker"):
                correction["corrected_speaker"] = edited["speaker"]
                has_change = True
            if has_change:
                corrections.append(correction)

        if name_corrections:
            _log.info("Fact review name corrections: %s", name_corrections)

        return corrections, name_corrections

    # ── LLM helpers (internal) ────────────────────────────────────────────────

    def _llm_stream(self, prompt: str, stage: str, max_tokens: int = 4096) -> str:
        """Call LLM with streaming, pushing token chunks to the frontend via _onLLMChunk."""
        provider, api_key, model = _get_llm_config()
        if not api_key:
            pname = "Claude" if provider == "anthropic" else "OpenAI"
            raise RuntimeError(f"{pname} API key not set. Check Settings.")

        self._stop_llm_stages.discard(stage)
        # Batch small chunks before sending to JS to reduce evaluate_js overhead
        _buf: list = []

        def _flush() -> None:
            if _buf:
                text = "".join(_buf)
                _buf.clear()
                escaped = json.dumps(text)
                self._js(f"window._onLLMChunk && window._onLLMChunk('{stage}', {escaped})")

        def on_chunk(text: str) -> None:
            _buf.append(text)
            if len("".join(_buf)) >= 30:
                _flush()

        def stop_check() -> bool:
            return stage in self._stop_llm_stages

        MAX_RETRIES = 3
        for attempt in range(MAX_RETRIES + 1):
            try:
                result = stream_llm(
                    prompt, provider=provider, api_key=api_key, model=model,
                    max_tokens=max_tokens, on_chunk=on_chunk, stop_check=stop_check,
                )
                _flush()  # flush any remaining buffered text
                return result
            except Exception as e:
                err_str = str(e).lower()
                is_rate_limited = any(k in err_str for k in (
                    "429", "rate_limit", "rate limit", "too many requests",
                ))
                is_retryable = is_rate_limited or any(k in err_str for k in (
                    "internal server error", "overloaded", "529", "500",
                ))
                if attempt < MAX_RETRIES and is_retryable:
                    wait_time = 60 if is_rate_limited else 3
                    retry_msg = "Rate limited" if is_rate_limited else "Retryable error"
                    _log.warning(
                        "%s (attempt %d/%d), waiting %ds: %s",
                        retry_msg, attempt + 1, MAX_RETRIES, wait_time, e,
                    )
                    _buf.clear()
                    notice = "\n[Rate limited — waiting 60s before retry...]\n" if is_rate_limited else "\n[Retrying...]\n"
                    self._js(
                        f"window._onLLMChunk && window._onLLMChunk('{stage}', "
                        + json.dumps(notice) + ")"
                    )
                    time.sleep(wait_time)
                    continue
                raise
        return ""  # unreachable, keeps linter happy

    def stop_llm_stage(self, stage: str) -> None:
        """Signal an active LLM streaming stage to stop."""
        _log.info("stop_llm_stage  stage=%s", stage)
        self._stop_llm_stages.add(stage)

    def skip_llm_stage(self, stage: str) -> None:
        """Mark an LLM stage to be skipped. If it's idle/waiting, it will be
        skipped when its turn comes. If it's already running, it will be stopped."""
        _log.info("skip_llm_stage  stage=%s", stage)
        self._skipped_stages.add(stage)
        self._stop_llm_stages.add(stage)
        self._notify_stage(stage, "done", {"skipped": True})

    def set_skipped_stages(self, stages: list) -> dict:
        """Pre-populate _skipped_stages before pipeline runs (for optional artifacts)."""
        _log.info("set_skipped_stages  stages=%s", stages)
        self._skipped_stages = set(stages)
        return {"ok": True}

    def run_single_stage(self, session_id: str, stage: str) -> dict:
        """Run a single LLM stage on-demand for an existing session.

        Spawns a background thread so the UI remains responsive.
        """
        _log.info("run_single_stage  session_id=%s  stage=%s", session_id, stage)
        sessions = get_sessions()
        session = None
        for s in sessions:
            if s["id"] == session_id:
                session = s
                break
        if not session:
            return {"ok": False, "error": "Session not found"}

        txt_path = session.get("txt_path")
        if not txt_path or not Path(txt_path).exists():
            return {"ok": False, "error": "No transcript available for this session"}

        valid_stages = ["timeline", "summary", "dm_notes", "character_updates", "glossary", "leaderboard", "locations", "npcs", "loot", "missions", "scenes", "illustration"]
        if stage not in valid_stages:
            return {"ok": False, "error": "Invalid stage: {}".format(stage)}

        character_names = session.get("character_names", [])
        out_dir = Path(session["output_dir"])
        out_dir.mkdir(parents=True, exist_ok=True)

        # Save current session context and set campaign for glossary
        prev_session_id = self._current_session_id
        prev_campaign_id = self._current_campaign_id
        prev_character_ids = self._current_character_ids
        self._current_session_id = session_id
        self._current_campaign_id = session.get("campaign_id")
        # Resolve character IDs from season
        self._current_character_ids = []
        if self._current_campaign_id:
            try:
                for camp in _get_campaigns():
                    if camp["id"] == self._current_campaign_id:
                        season_id = session.get("season_id", "")
                        for s in camp.get("seasons", []):
                            if s["id"] == season_id:
                                self._current_character_ids = s.get("characters", [])
                                break
                        break
            except Exception:
                pass
        self._glossary_context = self._build_glossary_context()
        self._entity_context = ""  # Clear to prevent cross-session bleed during single-stage reprocessing
        self._session_date = session.get("date", "")
        self._stop_llm_stages.discard(stage)

        def _run():
            # type: () -> None
            try:
                if stage == "illustration":
                    self._run_illustration_stage(txt_path, character_names, out_dir)
                else:
                    generate_fns = {
                        "timeline": self._generate_timeline_streaming,
                        "summary": self._generate_summary_streaming,
                        "dm_notes": self._generate_dm_notes_streaming,
                        "character_updates": self._generate_character_updates_streaming,
                        "glossary": self._generate_glossary_streaming,
                        "leaderboard": self._generate_leaderboard_streaming,
                        "locations": self._generate_locations_streaming,
                        "npcs": self._generate_npcs_streaming,
                        "loot": self._generate_loot_streaming,
                        "missions": self._generate_missions_streaming,
                    }
                    save_fns = {
                        "timeline": self._save_timeline,
                        "summary": self._save_summary,
                        "dm_notes": self._save_dm_notes,
                        "character_updates": self._save_character_updates,
                        "glossary": self._save_glossary,
                        "leaderboard": self._save_leaderboard,
                        "locations": self._save_locations,
                        "npcs": self._save_npcs,
                        "loot": self._save_loot,
                        "missions": self._save_missions,
                    }
                    self._notify_stage(stage, "running", None)
                    result = generate_fns[stage](txt_path, character_names)
                    if not result or not result.strip():
                        self._notify_stage(stage, "error", {"error": "No content generated"})
                        return
                    save_fns[stage](result.strip(), out_dir)
            except Exception as e:
                _log.error("run_single_stage '%s' failed: %s", stage, e, exc_info=True)
                self._notify_stage(stage, "error", {"error": str(e)})
            finally:
                self._current_session_id = prev_session_id
                self._current_campaign_id = prev_campaign_id
                self._current_character_ids = prev_character_ids
                self._glossary_context = ""
                self._entity_context = ""
                self._session_date = ""

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return {"ok": True}

    def stop_pipeline(self) -> None:
        """Stop the entire pipeline — transcription job + all LLM stages."""
        _log.info("stop_pipeline requested")
        with self._job_lock:
            if self._job:
                self._job.stop()
        all_stages = ["transcript_correction", "speaker_mapping", "updating_transcript", "fact_extraction", "fact_review", "timeline", "summary", "dm_notes", "character_updates", "glossary", "leaderboard", "locations", "npcs", "loot", "missions", "illustration"]
        for stage in all_stages:
            self._stop_llm_stages.add(stage)
        # Unblock any pending entity reviews to prevent zombie threads
        for event in self._pending_entity_reviews.values():
            event.set()
        self._pending_entity_reviews.clear()
        # Unblock pending fact review
        if self._pending_fact_review:
            self._pending_fact_review.set()
            self._pending_fact_review = None

    # ── Entity Review (Human-in-the-Loop) ─────────────────────────────────

    _ENTITY_REVIEW_THRESHOLD = 95

    def _request_entity_review(self, stage, review_items, auto_applied):
        # type: (str, list, list) -> list
        """Block pipeline thread until the DM reviews low-confidence entities.

        Returns the list of user decisions (accept/edit/decline per card).
        """
        import uuid as _uuid

        # Build review cards
        cards = []
        for item in review_items:
            entity_name = item.get("name") or item.get("item") or "Unknown"
            existing = None
            entity_type = self._stage_to_entity_type(stage)
            if self._current_campaign_id and entity_type:
                existing = _find_entity_fuzzy(self._current_campaign_id, entity_name, entity_type)

            card = {
                "id": str(_uuid.uuid4()),
                "action": "update" if existing else "create",
                "entity_type": entity_type or stage,
                "name": entity_name,
                "confidence": item.get("confidence", 50),
                "reasoning": item.get("reasoning", ""),
                "current_state": existing if existing else None,
                "proposed": {k: v for k, v in item.items() if k not in ("confidence", "reasoning")},
            }
            if existing:
                card["diff"] = self._compute_entity_diff(existing, item)
            cards.append(card)

        review_payload = {
            "stage": stage,
            "campaign_id": self._current_campaign_id or "",
            "session_id": self._current_session_id or "",
            "cards": cards,
            "auto_applied": auto_applied,
            "character_names": list(self._current_character_names) if hasattr(self, '_current_character_names') and self._current_character_names else [],
        }

        # Create blocking event
        event = threading.Event()
        self._pending_entity_reviews[stage] = event

        # Notify frontend
        self._notify_stage(stage, "needs_review", review_payload)

        # Block indefinitely until user responds or pipeline is stopped
        _log.info("Entity review requested for %s — %d cards, %d auto-applied. Waiting for DM...",
                   stage, len(cards), len(auto_applied))
        event.wait()

        # Retrieve decisions
        decisions = self._entity_review_decisions.pop(stage, [])
        self._pending_entity_reviews.pop(stage, None)

        _log.info("Entity review completed for %s — %d decisions received", stage, len(decisions))
        return decisions

    def complete_entity_review(self, stage, decisions):
        # type: (str, list) -> dict
        """Frontend sends user's accept/edit/decline decisions for entity review cards."""
        _log.info("complete_entity_review  stage=%s  decisions=%d", stage, len(decisions))
        self._entity_review_decisions[stage] = decisions
        event = self._pending_entity_reviews.get(stage)
        if event:
            event.set()  # unblock the waiting pipeline thread
        return {"ok": True}

    @staticmethod
    def _stage_to_entity_type(stage):
        # type: (str) -> Optional[str]
        """Map pipeline stage name to entity type."""
        return {
            "locations": "location",
            "loot": "item",
            "missions": "mission",
            "character_updates": None,  # character updates go through characters.py history
            "npcs": None,  # NPCs go through characters.py, not entities
            "glossary": None,  # glossary goes through campaigns.py
        }.get(stage)

    @staticmethod
    def _compute_entity_diff(existing, proposed_item):
        # type: (dict, dict) -> dict
        """Build {field: {old, new}} diff dict for an entity update."""
        diff = {}
        desc_old = existing.get("description", "")
        desc_new = proposed_item.get("description", "")
        if desc_old != desc_new and desc_new:
            diff["description"] = {"old": desc_old, "new": desc_new}
        # Compare properties
        old_props = existing.get("properties", {})
        for key in ("connections", "relative_position", "status", "race", "role",
                     "attitude", "actions", "current_status", "objectives", "rewards_mentioned"):
            old_val = old_props.get(key, "")
            new_val = proposed_item.get(key, "")
            if old_val != new_val and new_val:
                diff[key] = {"old": old_val, "new": new_val}
        return diff

    def _apply_entity_decisions(self, stage, decisions, all_items_with_conf):
        # type: (str, list, list) -> None
        """Apply accepted/edited entity decisions to the entity registry."""
        if not self._current_campaign_id:
            return

        # Build lookup: card_id → original item with confidence
        card_lookup = {}
        for item in all_items_with_conf:
            name = item.get("name") or item.get("item") or ""
            card_lookup[name.lower()] = item

        for decision in decisions:
            action = decision.get("action", "decline")
            if action == "decline":
                continue

            # Use edited data if provided, otherwise original proposed data
            item_data = decision.get("edited") or decision.get("proposed", {})
            entity_type = self._stage_to_entity_type(stage)
            name = item_data.get("name") or decision.get("name", "")
            if not name:
                continue

            try:
                if entity_type:
                    existing = _find_entity_fuzzy(self._current_campaign_id, name, entity_type)
                    if existing:
                        _update_entity(
                            self._current_campaign_id, existing["id"],
                            self._current_session_id or "",
                            session_date=getattr(self, '_session_date', ''),
                            description=item_data.get("description", ""),
                            properties={k: v for k, v in item_data.items()
                                       if k not in ("name", "description", "confidence", "reasoning")},
                            change_summary="DM-reviewed update",
                        )
                    else:
                        _create_entity(
                            campaign_id=self._current_campaign_id,
                            entity_type=entity_type,
                            name=name,
                            session_id=self._current_session_id or "",
                            session_date=getattr(self, '_session_date', ''),
                            definition=item_data.get("description", "")[:200],
                            description=item_data.get("description", ""),
                            properties={k: v for k, v in item_data.items()
                                       if k not in ("name", "description", "confidence", "reasoning")},
                        )
            except Exception as e:
                _log.error("Failed to apply entity decision for %s/%s: %s", stage, name, e)

    def _generate_summary_streaming(self, txt_path: str, character_names: List[str],
                                     transcript: Optional[str] = None) -> str:
        _log.info("generate_summary (streaming)  txt=%s", txt_path)
        if transcript is None:
            transcript = Path(txt_path).read_text(encoding="utf-8")
        names_str = ", ".join(character_names) if character_names else "Unknown"
        glossary_ctx = getattr(self, '_glossary_context', '') or self._build_glossary_context()
        entity_ctx = getattr(self, '_entity_context', '')
        if entity_ctx:
            glossary_ctx = glossary_ctx + entity_ctx
        session_date = getattr(self, '_session_date', '')
        prompt = f"""You are a Dungeon Master's assistant. Write a **recap summary** of this D&D session.

The summary will be read aloud at the start of the next session to remind players what happened. Write it in second person ("The party...") in a vivid, engaging narrative style — like the opening of a fantasy novel chapter. Aim for 3–5 paragraphs covering the key events chronologically.

Do NOT use bullet points or headers. Write flowing prose only.

## Session Context
This session took place on {session_date}. Extract information ONLY from THIS session's transcript.

## Characters
{names_str}{glossary_ctx}

## Session Transcript
{transcript}"""
        return self._llm_stream(prompt, "summary", max_tokens=1024)

    def _build_glossary_context(self):
        # type: () -> str
        """Build a formatted glossary block for injection into LLM prompts.

        Includes glossary terms + NPC names from characters.json + location names
        from entity registry, so all known names are available for accurate spelling.
        """
        if not self._current_campaign_id:
            return ""
        try:
            parts = []

            # Glossary terms (Faction, Item, Spell, Other — NPCs/Locations excluded)
            glossary = _get_glossary(self._current_campaign_id)
            for term in sorted(glossary.keys()):
                info = glossary[term]
                if not isinstance(info, dict):
                    continue
                cat = info.get("category", "")
                if cat.upper() in ("NPC", "LOCATION"):
                    continue  # These have dedicated sources below
                defn = info.get("definition", "")
                desc = info.get("description", "")
                line = "- {} ({})".format(term, cat)
                if defn:
                    line += ": {}".format(defn)
                if desc:
                    truncated = desc[:200] + "..." if len(desc) > 200 else desc
                    line += " [Details: {}]".format(truncated)
                parts.append(line)

            # NPC names from character registry
            npcs = _get_npcs(self._current_campaign_id)
            for npc in npcs:
                name = npc.get("name", "")
                desc = npc.get("npc_description", "")
                line = "- {} (NPC)".format(name)
                if desc:
                    truncated = desc[:150] + "..." if len(desc) > 150 else desc
                    line += ": {}".format(truncated)
                parts.append(line)

            # Location names from entity registry
            try:
                loc_entities = _get_entities(self._current_campaign_id, "location")
                for ent in loc_entities:
                    name = ent.get("name", "")
                    defn = ent.get("current", {}).get("definition", "")
                    line = "- {} (Location)".format(name)
                    if defn:
                        truncated = defn[:150] + "..." if len(defn) > 150 else defn
                        line += ": {}".format(truncated)
                    parts.append(line)
            except Exception:
                pass

            if not parts:
                return ""
            return "\n\n## Campaign Glossary (known NPCs, locations, factions, items — use these for accurate naming)\n{}".format(
                "\n".join(parts)
            )
        except Exception as e:
            _log.warning("Could not build glossary context: %s", e)
            return ""

    def _run_llm_stages(self, txt_path: str, character_names: List[str]) -> None:
        """Run sequential LLM calls: timeline → summary → dm_notes → scenes → illustration.

        Each stage gets its own streaming call with an independent prompt.
        Stages run one after another so we stay under rate limits.
        """
        _log.info("_run_llm_stages  txt=%s", txt_path)

        out_dir = Path(txt_path).parent
        out_dir.mkdir(parents=True, exist_ok=True)

        # Read transcript once for all stages (avoid 9 redundant disk reads)
        transcript = Path(txt_path).read_text(encoding="utf-8")
        _log.info("Transcript loaded once (%d chars)", len(transcript))

        # Look up session date for prompt anchoring
        self._session_date = ""
        if self._current_session_id:
            for _s in get_sessions():
                if _s.get("id") == self._current_session_id:
                    self._session_date = _s.get("date", "")
                    break

        # Ensure entity registry is migrated for this campaign
        if self._current_campaign_id:
            try:
                glossary = _get_glossary(self._current_campaign_id)
                sessions = get_sessions()
                _ensure_entities_migrated(self._current_campaign_id, glossary, sessions)
            except Exception as e:
                _log.error("Entity migration at pipeline start failed: %s", e)

        # Load glossary context once for all stages
        self._glossary_context = self._build_glossary_context()
        # Prepend facts context if available
        facts_ctx = getattr(self, '_facts_context', '')
        if facts_ctx:
            self._glossary_context = facts_ctx + (self._glossary_context or "")
        if self._glossary_context:
            _log.info("Glossary+facts context loaded (%d chars) — will inject into LLM stages",
                      len(self._glossary_context))

        # Load entity context once for all stages
        self._entity_context = ""
        if self._current_campaign_id:
            try:
                from entities import get_entity_context_for_llm as _get_entity_context
                self._entity_context = _get_entity_context(self._current_campaign_id)
                if self._entity_context:
                    _log.info("Entity context loaded (%d chars)", len(self._entity_context))
            except Exception as e:
                _log.error("Could not load entity context: %s", e)

        stages = [
            ("timeline", self._generate_timeline_streaming, self._save_timeline),
            ("summary", self._generate_summary_streaming, self._save_summary),
            ("dm_notes", self._generate_dm_notes_streaming, self._save_dm_notes),
            ("character_updates", self._generate_character_updates_streaming, self._save_character_updates),
            ("glossary", self._generate_glossary_streaming, self._save_glossary),
            ("leaderboard", self._generate_leaderboard_streaming, self._save_leaderboard),
            ("locations", self._generate_locations_streaming, self._save_locations),
            ("npcs", self._generate_npcs_streaming, self._save_npcs),
            ("loot", self._generate_loot_streaming, self._save_loot),
            ("missions", self._generate_missions_streaming, self._save_missions),
        ]

        for stage_name, generate_fn, save_fn in stages:
            if stage_name in self._skipped_stages:
                _log.info("Skipping stage '%s' (user requested)", stage_name)
                self._notify_stage(stage_name, "done", {"skipped": True})
                continue
            self._notify_stage(stage_name, "running", None)
            try:
                result = generate_fn(txt_path, character_names, transcript=transcript)
                if not result or not result.strip():
                    self._notify_stage(stage_name, "error", {"error": "No content generated"})
                    continue
                save_fn(result.strip(), out_dir)
            except Exception as e:
                _log.error("LLM stage '%s' failed: %s", stage_name, e, exc_info=True)
                self._notify_stage(stage_name, "error", {"error": str(e)})

        # Illustration stage — uses Gemini image generation
        self._run_illustration_stage(txt_path, character_names, out_dir, transcript=transcript)

        # Auto-generate session title if not already set
        if self._current_session_id:
            try:
                sessions = get_sessions()
                for s in sessions:
                    if s["id"] == self._current_session_id:
                        if not s.get("display_name"):
                            result = self.generate_session_title(self._current_session_id)
                            if result.get("ok"):
                                _log.info("Auto-generated title: %s", result.get("title"))
                        break
            except Exception as e:
                _log.error("Auto-title generation failed (non-fatal): %s", e)

    def _run_illustration_stage(
        self, txt_path: str, character_names: List[str], out_dir: Path,
        transcript: Optional[str] = None,
    ) -> None:
        """Generate an illustration for the session using LLM prompt + Gemini Imagen."""
        stage = "illustration"
        if stage in self._skipped_stages:
            _log.info("Skipping stage '%s' (user requested)", stage)
            self._notify_stage(stage, "done", {"skipped": True})
            return

        gemini_key = get_gemini_token()
        if not gemini_key:
            _log.info("No Gemini API key configured — skipping illustration")
            self._notify_stage(stage, "done", {"skipped": True})
            return

        self._notify_stage(stage, "running", None)
        try:
            # Step 1: Generate a detailed illustration prompt via LLM
            img_prompt = self._generate_illustration_prompt_streaming(
                txt_path, character_names, transcript=transcript,
            )
            if not img_prompt or not img_prompt.strip():
                self._notify_stage(stage, "error", {"error": "No illustration prompt generated"})
                return

            if stage in self._stop_llm_stages:
                _log.info("Illustration stage stopped after prompt generation")
                self._notify_stage(stage, "done", {"skipped": True})
                return

            # Step 2: Call Gemini Imagen to generate the image
            from image_gen import generate_illustration

            out_path = out_dir / "illustration.png"

            def _stop() -> bool:
                return stage in self._stop_llm_stages

            ok = generate_illustration(
                prompt=img_prompt.strip(),
                api_key=gemini_key,
                output_path=str(out_path),
                stop_check=_stop,
            )
            if not ok:
                _log.info("Illustration generation cancelled")
                self._notify_stage(stage, "done", {"skipped": True})
                return

            # Step 3: Update session registry
            if self._current_session_id:
                update_session(self._current_session_id, illustration_path=str(out_path))
            _log.info("Illustration saved → %s", out_path)
            self._notify_stage(stage, "done", {"illustration": str(out_path)})

        except Exception as e:
            _log.error("Illustration stage failed: %s", e, exc_info=True)
            self._notify_stage(stage, "error", {"error": str(e)})

    def _generate_illustration_prompt_streaming(
        self, txt_path: str, character_names: List[str],
        transcript: Optional[str] = None,
    ) -> str:
        """Use the current LLM to create a single detailed image prompt from the session."""
        _log.info("generate_illustration_prompt (streaming)  txt=%s", txt_path)
        if transcript is None:
            transcript = Path(txt_path).read_text(encoding="utf-8")
        # Truncate very long transcripts — skip the beginning recap (usually
        # covers the previous session) and focus on the core/climax of this session
        if len(transcript) > 15000:
            skip_start = len(transcript) // 5  # skip first 20% (recap)
            transcript = transcript[skip_start:]
            if len(transcript) > 15000:
                transcript = transcript[-15000:]
            transcript = "[... earlier session recap omitted ...]\n\n" + transcript

        names_str = ", ".join(character_names) if character_names else "Unknown"
        prompt = f"""You are a concept artist for a fantasy tabletop RPG. Based on the D&D session transcript below, write ONE detailed image generation prompt that captures the most dramatic, climactic, or visually striking moment from the session.

IMPORTANT: The beginning of the transcript is usually a recap of the previous session — SKIP it. Focus on the CORE of THIS session: the highlight moment that players would remember most. Choose a moment from the middle or climax of the session — a pivotal battle, a dramatic reveal, a tense confrontation, or a breathtaking discovery.

The prompt should describe a single cinematic scene suitable for a 16:9 landscape illustration in a painterly fantasy art style. Include:
- The setting/environment in vivid detail
- Character positions, actions, and expressions
- Lighting, atmosphere, and mood
- Color palette suggestions
- Art style: epic fantasy illustration, detailed, dramatic lighting

Do NOT include any text, labels, or UI elements in the prompt. Write ONLY the image prompt — no preamble, no explanation, no quotes.

## Characters
{names_str}

## Session Transcript
{transcript}"""
        return self._llm_stream(prompt, "illustration", max_tokens=512)

    def _save_summary(self, text: str, out_dir: Path) -> None:
        out_path = out_dir / "summary.md"
        out_path.write_text(text, encoding="utf-8")
        if self._current_session_id:
            update_session(self._current_session_id, summary_path=str(out_path))
        _log.info("Summary saved → %s", out_path)
        self._notify_stage("summary", "done", {"summary": text})

    def _save_dm_notes(self, text: str, out_dir: Path) -> None:
        out_path = out_dir / "dm_notes.md"
        out_path.write_text(text, encoding="utf-8")
        if self._current_session_id:
            update_session(self._current_session_id, dm_notes_path=str(out_path))
        _log.info("DM notes saved → %s", out_path)
        self._notify_stage("dm_notes", "done", {"notes": text})

    @staticmethod
    def _extract_json_object(text: str) -> Optional[dict]:
        """Extract the first JSON object from LLM output text.

        Strips markdown fences, finds valid { ... } JSON and parses it.
        If the first { / last } pair fails, scans all { positions to find
        the actual JSON object (handles LLM prose wrapping).
        Returns None if no valid JSON object is found.
        """
        import re
        stripped = text.strip()
        # Strip markdown fences (```json ... ``` or ``` ... ```)
        if stripped.startswith("```"):
            parts = stripped.split("```")
            if len(parts) >= 3:
                inner = parts[1]
                # Remove optional language tag (e.g. "json")
                if inner.startswith("json"):
                    inner = inner[4:]
                stripped = inner.strip()
            elif len(parts) >= 2:
                inner = parts[1]
                if inner.startswith("json"):
                    inner = inner[4:]
                stripped = inner.strip()

        def _try_parse(candidate):
            # type: (str) -> Optional[dict]
            """Try parsing candidate as JSON, with trailing-comma repair."""
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                cleaned = re.sub(r',\s*}', '}', candidate)
                cleaned = re.sub(r',\s*]', ']', cleaned)
                try:
                    return json.loads(cleaned)
                except json.JSONDecodeError:
                    return None

        # First attempt: outermost { ... }
        start = stripped.find("{")
        end = stripped.rfind("}") + 1
        if start == -1 or end == 0:
            _log.debug("_extract_json_object: no braces found in text (len=%d)", len(text))
            return None

        result = _try_parse(stripped[start:end])
        if result is not None:
            return result

        # Second attempt: scan all { positions (handles prose with { before JSON)
        pos = start
        while pos < len(stripped):
            pos = stripped.find("{", pos)
            if pos == -1:
                break
            # Find matching } by trying from the end backwards
            for end_pos in range(len(stripped), pos, -1):
                if stripped[end_pos - 1] == "}":
                    candidate = stripped[pos:end_pos]
                    result = _try_parse(candidate)
                    if result is not None:
                        return result
                    break  # Try next { position
            pos += 1

        _log.debug("_extract_json_object: no valid JSON found (len=%d, first 500 chars: %s)",
                   len(text), text[:500])
        return None

    @staticmethod
    def _repair_json_array(text: str) -> Optional[list]:
        """Best-effort repair of LLM-produced JSON arrays.

        Handles: markdown fences, trailing commas, surrounding prose.
        Returns parsed list or None on failure.
        """
        stripped = text.strip()
        # 1. Strip markdown fences
        if stripped.startswith("```"):
            parts = stripped.split("```")
            if len(parts) >= 2:
                stripped = parts[1]
                if stripped.startswith("json"):
                    stripped = stripped[4:]
                stripped = stripped.strip()

        # 2. Try direct parse first
        try:
            result = json.loads(stripped)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

        # 3. Strip trailing commas and retry
        cleaned = re.sub(r',\s*([}\]])', r'\1', stripped)
        try:
            result = json.loads(cleaned)
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass

        # 4. Regex-extract outermost [...] block
        m = re.search(r'\[.*\]', stripped, re.DOTALL)
        if m:
            block = re.sub(r',\s*([}\]])', r'\1', m.group())
            try:
                result = json.loads(block)
                if isinstance(result, list):
                    return [item for item in result if isinstance(item, dict)]
            except json.JSONDecodeError:
                pass

        # 5. Try wrapping bare {…}{…} objects in brackets
        if stripped.startswith('{'):
            # Join with commas, wrap in array
            bracketed = '[' + re.sub(r'\}\s*\{', '},{', stripped) + ']'
            bracketed = re.sub(r',\s*([}\]])', r'\1', bracketed)
            try:
                result = json.loads(bracketed)
                if isinstance(result, list):
                    return [item for item in result if isinstance(item, dict)]
            except json.JSONDecodeError:
                pass

        # 6. Extract individual {…} objects via regex
        objects = re.findall(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', stripped)
        if objects:
            items = []
            for obj_str in objects:
                try:
                    parsed = json.loads(obj_str)
                    if isinstance(parsed, dict):
                        items.append(parsed)
                except json.JSONDecodeError:
                    pass
            if items:
                return items

        return None

    def _save_timeline(self, text: str, out_dir: Path) -> None:
        timeline = self._repair_json_array(text)
        if timeline is None:
            _log.error("Timeline JSON parse failed for text: %s…", text[:200])
            (out_dir / "timeline.raw").write_text(text, encoding="utf-8")
            self._notify_stage("timeline", "error", {"error": "Could not parse timeline JSON. Raw output saved."})
            return
        out_path = out_dir / "timeline.json"
        out_path.write_text(json.dumps(timeline, indent=2, ensure_ascii=False), encoding="utf-8")
        if self._current_session_id:
            update_session(self._current_session_id, timeline_path=str(out_path))
        _log.info("Timeline saved → %s (%d events)", out_path, len(timeline))
        self._notify_stage("timeline", "done", {"timeline": timeline})

    def _generate_dm_notes_streaming(self, txt_path: str, character_names: List[str],
                                      transcript: Optional[str] = None) -> str:
        _log.info("generate_dm_notes (streaming)  txt=%s", txt_path)
        if transcript is None:
            transcript = Path(txt_path).read_text(encoding="utf-8")
        names_str = ", ".join(character_names) if character_names else "Unknown"
        glossary_ctx = getattr(self, '_glossary_context', '') or self._build_glossary_context()
        entity_ctx = getattr(self, '_entity_context', '')
        if entity_ctx:
            glossary_ctx = glossary_ctx + entity_ctx
        session_date = getattr(self, '_session_date', '')
        prompt = f"""You are an expert Dungeon Master's assistant. Analyze this D&D session transcript and produce structured DM notes.

Be thorough, specific, and practical. The DM will use these notes to prepare future sessions.

## Session Context
This session took place on {session_date}. Extract information ONLY from THIS session's transcript.

Format your response in Markdown with exactly these sections:

## Key Events & Timeline
A concise chronological bullet list of what happened, including location changes and major decisions.

## NPCs Encountered
For each NPC: name, role/description, attitude toward the party, any promises made or threats issued, and current status/location.

## Items & Loot
List EVERY item found, looted, purchased, received, gifted, consumed, or mentioned in the session. For each: who received/used it, what it does (if known), and whether it's identified. Include ALL gold/currency transactions (gained and spent). Be thorough — missing loot is the most common error in DM notes.

## Character Development
Notable moments per character: decisions made, personal arcs advanced, relationships changed, any leveling or ability use worth noting.

## World-Building & Lore
Locations visited or described, factions mentioned, history or lore revealed, hooks planted.

## Open Plot Threads
Unresolved questions, cliffhangers, mysteries, and promises that need follow-up.

## DM Action Items for Next Session
A concrete to-do list: NPCs to prepare, locations to flesh out, rules to look up, consequences to plan, player rewards pending.

## Characters in This Session
{names_str}{glossary_ctx}

## Session Transcript
{transcript}"""
        return self._llm_stream(prompt, "dm_notes")

    def _generate_character_updates_streaming(self, txt_path: str, character_names: List[str],
                                               transcript: Optional[str] = None) -> str:
        """Generate per-character development updates from the session."""
        _log.info("generate_character_updates (streaming)  txt=%s", txt_path)
        if not self._current_character_ids:
            _log.info("No character IDs — skipping character_updates")
            return ""
        if transcript is None:
            transcript = Path(txt_path).read_text(encoding="utf-8")
        # Build character context with existing history
        chars = _get_characters_by_ids(self._current_character_ids)
        if not chars:
            return ""
        char_block_parts = []
        for ch in chars:
            parts = ["Name: {}".format(ch["name"])]
            if ch.get("race"):
                parts.append("Race: {}".format(ch["race"]))
            if ch.get("class_name"):
                parts.append("Class: {}".format(ch["class_name"]))
            bd = ch.get("beyond_data") or {}
            if bd.get("backstory"):
                bs = bd["backstory"]
                if len(bs) > 400:
                    bs = bs[:400] + "..."
                parts.append("Backstory: {}".format(bs))
            if ch.get("history_summary"):
                parts.append("Previous arc summary: {}".format(ch["history_summary"]))
            elif ch.get("history"):
                recent = ch["history"][-3:]
                recent_texts = [h.get("auto_text", "") for h in recent if h.get("auto_text")]
                if recent_texts:
                    parts.append("Recent history: {}".format(" | ".join(recent_texts)))
            char_block_parts.append("\n".join(parts))
        char_block = "\n\n---\n\n".join(char_block_parts)

        # Load campaign NPCs for history tracking
        npc_block = ""
        self._current_npc_chars = []
        if self._current_campaign_id:
            from characters import get_npcs as _get_npcs_list
            self._current_npc_chars = _get_npcs_list(self._current_campaign_id)
        if self._current_npc_chars:
            npc_parts = []
            for npc in self._current_npc_chars:
                parts = ["Name: {}".format(npc["name"])]
                if npc.get("npc_description"):
                    parts.append("Description: {}".format(npc["npc_description"]))
                if npc.get("history"):
                    recent = npc["history"][-2:]
                    recent_texts = [h.get("auto_text", "") for h in recent if h.get("auto_text")]
                    if recent_texts:
                        parts.append("Recent history: {}".format(" | ".join(recent_texts)))
                npc_parts.append("\n".join(parts))
            npc_block = "\n\n## NPCs (only include those who ACTUALLY appear in or are referenced in this session)\n\n" + "\n\n---\n\n".join(npc_parts)

        session_date = getattr(self, '_session_date', '')
        glossary_ctx = getattr(self, '_glossary_context', '') or self._build_glossary_context()
        entity_ctx = getattr(self, '_entity_context', '')
        if entity_ctx:
            glossary_ctx = glossary_ctx + entity_ctx
        prompt = """You are a D&D campaign chronicler. For each player character below, write a 2-3 sentence update describing how they developed, what they did, and any notable moments in this session.

Also write updates for any NPCs that ACTUALLY APPEAR or are DIRECTLY REFERENCED in this session's transcript. Skip NPCs that are not mentioned at all.

Return ONLY a valid JSON object (no markdown, no explanation) mapping character/NPC names to an object with text, confidence (0-100), and reasoning:
{{
  "CharacterName": {{
    "text": "2-3 sentence development update for this session...",
    "confidence": 90,
    "reasoning": "Brief explanation of why this update is accurate"
  }},
  ...
}}

Confidence guidelines:
- 95-100: Directly stated or clearly shown in transcript (character says/does something explicitly)
- 80-94: Strongly implied by context and dialogue
- 60-79: Inferred or partially supported by transcript
- Below 60: Speculative, should be reviewed

Focus on: character growth, key decisions, relationships, combat highlights, role-play moments, new abilities or items used. For NPCs, focus on what they did, how they interacted with the party, and any new information revealed.

## Session Context
This session took place on {date}. Extract information ONLY from THIS session's transcript.

## Player Characters

{chars}
{npcs}{glossary}

## Session Transcript
{transcript}""".format(date=session_date, chars=char_block, npcs=npc_block, glossary=glossary_ctx, transcript=transcript)
        return self._llm_stream(prompt, "character_updates", max_tokens=4096)

    def _save_character_updates(self, text: str, out_dir: Path) -> None:
        """Parse character updates JSON and save to each character's history.

        Supports both new format (with confidence/reasoning) and flat string format.
        Low-confidence updates go through entity review.
        """
        updates = self._extract_json_object(text)
        if updates is None:
            _log.error("character_updates: no valid JSON object found")
            self._notify_stage("character_updates", "error", {"error": "Could not parse updates"})
            return

        # Normalise: support both new {text, confidence, reasoning} and flat string formats
        updates_with_conf = {}  # type: Dict[str, Dict[str, Any]]
        flat_updates = {}  # type: Dict[str, str]  # for saving to file
        for char_name, val in updates.items():
            if isinstance(val, dict) and "text" in val:
                updates_with_conf[char_name] = val
                flat_updates[char_name] = val["text"]
            else:
                # Backward compat: flat string
                updates_with_conf[char_name] = {
                    "text": str(val),
                    "confidence": 100,
                    "reasoning": "Direct format (no confidence provided)",
                }
                flat_updates[char_name] = str(val)

        # Split by confidence threshold
        threshold = self._ENTITY_REVIEW_THRESHOLD
        auto_apply = {k: v for k, v in updates_with_conf.items() if v.get("confidence", 100) >= threshold}
        review_queue = {k: v for k, v in updates_with_conf.items() if v.get("confidence", 100) < threshold}

        # Save to file (flat format for backward compat)
        out_path = out_dir / "character_updates.json"
        out_path.write_text(json.dumps(flat_updates, indent=2, ensure_ascii=False), encoding="utf-8")
        if self._current_session_id:
            update_session(self._current_session_id, character_updates_path=str(out_path))

        # Get session metadata
        chars = _get_characters_by_ids(self._current_character_ids)
        name_to_id = {ch["name"]: ch["id"] for ch in chars}
        session_id = self._current_session_id or ""
        session_date = ""
        campaign_name = ""
        season_number = 0
        if session_id:
            from sessions import get_sessions
            for s in get_sessions():
                if s.get("id") == session_id:
                    session_date = s.get("date", "")
                    campaign_name = s.get("campaign_name", "")
                    season_number = s.get("season_number", 0)
                    break

        npc_name_to_id = {}  # type: Dict[str, str]
        if self._current_npc_chars:
            npc_name_to_id = {npc["name"]: npc["id"] for npc in self._current_npc_chars}

        def _apply_update(char_name, update_text):
            # type: (str, str) -> bool
            """Apply a single character update to history. Returns True if saved."""
            char_id = name_to_id.get(char_name)
            if not char_id:
                for n, cid in name_to_id.items():
                    if n.lower() == char_name.lower():
                        char_id = cid
                        break
            if not char_id:
                # Try NPC
                npc_id = npc_name_to_id.get(char_name)
                if not npc_id:
                    for n, nid in npc_name_to_id.items():
                        if n.lower() == char_name.lower():
                            npc_id = nid
                            break
                if npc_id and update_text:
                    _add_history_entry(npc_id, session_id, session_date, campaign_name, season_number, update_text)
                    return True
                return False
            if char_id and update_text:
                _add_history_entry(char_id, session_id, session_date, campaign_name, season_number, update_text)
                return True
            return False

        # Auto-apply high-confidence updates
        saved_count = 0
        for char_name, val in auto_apply.items():
            if _apply_update(char_name, val["text"]):
                saved_count += 1

        # Entity review for low-confidence updates
        if review_queue:
            _log.info("Character updates: %d auto-applied, %d need review", len(auto_apply), len(review_queue))
            review_items = [
                {
                    "name": char_name,
                    "text": val["text"],
                    "confidence": val.get("confidence", 50),
                    "reasoning": val.get("reasoning", ""),
                }
                for char_name, val in review_queue.items()
            ]
            auto_applied_summary = [
                {"name": k, "action": "update", "confidence": v.get("confidence", 100)}
                for k, v in auto_apply.items()
            ]
            decisions = self._request_entity_review("character_updates", review_items, auto_applied_summary)

            # Apply accepted/edited decisions
            for d in decisions:
                action = d.get("action", "decline")
                if action == "decline":
                    continue
                name = d.get("name", "")
                if action == "edit" and d.get("edited"):
                    update_text = d["edited"].get("text", "")
                else:
                    # Accept: use original proposed text
                    proposed = d.get("proposed", {})
                    update_text = proposed.get("text", "")
                if update_text and name:
                    if _apply_update(name, update_text):
                        saved_count += 1
                    # Update flat file too
                    flat_updates[name] = update_text

            # Re-save file with any edits applied
            out_path.write_text(json.dumps(flat_updates, indent=2, ensure_ascii=False), encoding="utf-8")

        _log.info("Character updates saved for %d/%d characters", saved_count, len(updates))
        self._notify_stage("character_updates", "done", {"updates": flat_updates})

    def _generate_glossary_streaming(self, txt_path: str, character_names: List[str],
                                      transcript: Optional[str] = None) -> str:
        _log.info("generate_glossary (streaming)  txt=%s", txt_path)
        if transcript is None:
            transcript = Path(txt_path).read_text(encoding="utf-8")
        names_str = ", ".join(character_names) if character_names else "Unknown"

        # Load existing glossary with full definitions for smart merge
        existing_glossary = {}  # type: dict
        if self._current_campaign_id:
            try:
                existing_glossary = _get_glossary(self._current_campaign_id)
            except Exception as e:
                _log.warning("Could not load existing glossary: %s", e)

        existing_block = ""
        if existing_glossary:
            parts = []
            for term in sorted(existing_glossary.keys()):
                info = existing_glossary[term]
                cat = info.get("category", "")
                defn = info.get("definition", "")
                desc = info.get("description", "")
                entry = '"category": "{}", "definition": "{}"'.format(
                    cat, defn.replace('"', '\\"')
                )
                if desc:
                    entry += ', "description": "{}"'.format(desc.replace('"', '\\"'))
                parts.append('  "{}": {{{}}}'.format(term, entry))
            existing_block = "\n\n## Existing Campaign Glossary\nReview each existing term below. If this transcript provides richer context, corrections, or new details, output the term with IMPROVED definition and/or description. If the existing entry is already good, SKIP that term.\n\nAlso check for NEAR-DUPLICATES: if a new term is a variant (different casing, abbreviation, nickname) of an existing term, do NOT add a new entry — instead enrich the existing one. Report duplicates in the _merges field.\n{{\n{}\n}}".format(
                ",\n".join(parts)
            )

        session_date = getattr(self, '_session_date', '')
        prompt = """You are a D&D campaign glossary extractor. Extract proper nouns and D&D-specific terms from this session transcript.

## Session Context
This session took place on {date}. Extract information ONLY from THIS session's transcript.

## Rules
- Extract: NPC names, location names, faction names, item names, spell names, and other D&D-specific terms
- Do NOT include player character names: {names}
- Do NOT include generic D&D terms (e.g. "attack", "damage", "hit points")
- Only include terms that are SPECIFIC to this campaign
- Each term needs: category, definition (1-2 factual sentences), and description (richer cumulative context)
- "definition" = concise factual summary (who/what it is)
- "description" = richer context that grows over sessions (relationships, events, significance)
- For NEW terms: add them with category, definition, and description
- For EXISTING terms where this transcript provides significantly richer context: output them with improved definition and/or description
- For existing terms where the entry is already complete: SKIP them (do not output)

## Deduplication
- Check for near-duplicates: same entity with different casing, abbreviation, or nickname
- If you find duplicates in the existing glossary, report them in the "_merges" field
- Format: "_merges": [{{"keep": "Full Proper Name", "remove": "Variant/Abbreviation"}}, ...]
- The "keep" term gets the enriched content; the "remove" term will be deleted{existing}

## Output Format
Return a JSON object where each key is the term and the value is an object with "category", "definition", "description", "confidence" (0-100), and "reasoning":
{{
  "Strahd von Zarovich": {{"category": "NPC", "definition": "Vampire lord ruling over Barovia from Castle Ravenloft.", "description": "Ancient vampire who made a pact with dark powers. Obsessed with Ireena Kolyana.", "confidence": 95, "reasoning": "Named multiple times in dialogue"}},
  "Vallaki": {{"category": "Location", "definition": "Walled town in Barovia, governed by Baron Vallakovich.", "description": "The party arrived seeking refuge. The Baron enforces mandatory festivals.", "confidence": 85, "reasoning": "Referenced as destination but details are from context"}},
  "_merges": [{{"keep": "Castle Ravenloft", "remove": "Castle R."}}]
}}

Confidence guidelines:
- 95-100: Named explicitly and clearly described in transcript
- 80-94: Named in transcript but details are partly inferred
- 60-79: Mentioned briefly or inferred from context
- Below 60: Uncertain — may be misheard or ambiguous

Categories: NPC, Location, Faction, Item, Spell, Other

Return ONLY the JSON object. No markdown fences, no explanation.

## Session Transcript
{transcript}""".format(
            date=session_date,
            names=names_str,
            existing=existing_block,
            transcript=transcript,
        )
        return self._llm_stream(prompt, "glossary", max_tokens=4096)

    def _save_glossary(self, text: str, out_dir: Path) -> None:
        glossary = self._extract_json_object(text)
        if glossary is None:
            _log.error("glossary: no valid JSON object found")
            self._notify_stage("glossary", "error", {"error": "Could not parse glossary"})
            return

        # Detect flat entry: LLM sometimes returns a single entry's fields as top-level keys
        _ENTRY_FIELDS = {"category", "definition", "description", "confidence", "reasoning"}
        if glossary and glossary.keys() <= _ENTRY_FIELDS:
            _log.error("glossary: LLM returned a single flat entry instead of a glossary dict — skipping")
            self._notify_stage("glossary", "error", {"error": "LLM returned malformed glossary (flat entry instead of {term: {fields}})"})
            return

        # Extract and process merge directives before saving
        merges = glossary.pop("_merges", None)
        if merges and isinstance(merges, list):
            _log.info("Glossary LLM suggested %d merge(s): %s", len(merges), merges)

        # Normalise entries: LLM sometimes returns strings instead of dicts
        for term in list(glossary.keys()):
            info = glossary[term]
            if not isinstance(info, dict):
                glossary[term] = {"category": "Other", "definition": str(info), "description": "", "confidence": 100, "reasoning": ""}
            elif "description" not in info:
                info["description"] = ""

        # Route NPC and Location entries to their dedicated registries
        npc_entries = {}  # type: Dict[str, dict]
        location_entries = {}  # type: Dict[str, dict]
        for term in list(glossary.keys()):
            cat = glossary[term].get("category", "").upper()
            if cat == "NPC":
                npc_entries[term] = glossary.pop(term)
            elif cat == "LOCATION":
                location_entries[term] = glossary.pop(term)

        if npc_entries:
            _log.info("Glossary: routing %d NPC entries to character registry", len(npc_entries))
        if location_entries:
            _log.info("Glossary: routing %d Location entries to entity registry", len(location_entries))

        # NPC entries → character registry via _sync_npcs_from_glossary
        if npc_entries and self._current_campaign_id:
            self._sync_npcs_from_glossary(npc_entries, self._current_campaign_id)

        # Determine which terms are genuinely NEW vs existing enrichments
        existing_glossary = {}  # type: dict
        if self._current_campaign_id:
            try:
                existing_glossary = _get_glossary(self._current_campaign_id)
            except Exception:
                pass
        existing_lower = {k.lower() for k in existing_glossary}

        threshold = self._ENTITY_REVIEW_THRESHOLD
        new_low_conf = {}  # type: Dict[str, dict]  # genuinely new terms with low confidence
        auto_terms = {}  # type: Dict[str, dict]  # terms to auto-apply (existing enrichments + high-conf new)

        for term, info in glossary.items():
            is_existing = term.lower() in existing_lower
            conf = info.get("confidence", 100) if isinstance(info, dict) else 100
            if is_existing:
                # Existing term enrichment: always auto-apply via smart_merge
                auto_terms[term] = info
            elif conf >= threshold:
                # New term with high confidence: auto-apply
                auto_terms[term] = info
            else:
                # New term with low confidence: needs review
                new_low_conf[term] = info

        # Strip confidence/reasoning from saved artifact file
        clean_glossary = {}  # type: Dict[str, dict]
        for term, info in glossary.items():
            if isinstance(info, dict):
                clean_glossary[term] = {k: v for k, v in info.items() if k not in ("confidence", "reasoning")}
            else:
                clean_glossary[term] = info

        # Save to file (without confidence/reasoning)
        out_path = out_dir / "glossary.json"
        out_path.write_text(json.dumps(clean_glossary, indent=2, ensure_ascii=False), encoding="utf-8")

        # Update session registry
        if self._current_session_id:
            update_session(self._current_session_id, glossary_path=str(out_path))

        # Smart merge auto-apply terms into campaign glossary
        if self._current_campaign_id and auto_terms:
            # Strip confidence before merging
            merge_terms = {t: {k: v for k, v in info.items() if k not in ("confidence", "reasoning")} for t, info in auto_terms.items()}
            added, updated = _smart_merge_glossary(self._current_campaign_id, merge_terms)
            _log.info("Glossary merge result: %d added, %d updated (campaign=%s, auto_terms=%d, review_terms=%d)",
                      added, updated, self._current_campaign_id, len(auto_terms), len(new_low_conf))
        elif not self._current_campaign_id:
            _log.warning("Glossary save: no _current_campaign_id set — skipping merge")

        # Entity review for low-confidence NEW terms
        if new_low_conf and self._current_campaign_id:
            _log.info("Glossary: %d new terms need review (threshold=%d%%)", len(new_low_conf), threshold)
            review_items = [
                {
                    "name": term,
                    "category": info.get("category", "Other"),
                    "definition": info.get("definition", ""),
                    "description": info.get("description", ""),
                    "confidence": info.get("confidence", 50),
                    "reasoning": info.get("reasoning", ""),
                }
                for term, info in new_low_conf.items()
            ]
            auto_applied_summary = [
                {"name": t, "action": "update" if t.lower() in existing_lower else "create", "confidence": info.get("confidence", 100)}
                for t, info in auto_terms.items()
            ]
            decisions = self._request_entity_review("glossary", review_items, auto_applied_summary)

            # Apply accepted/edited glossary terms
            accepted_terms = {}  # type: Dict[str, dict]
            for d in decisions:
                action = d.get("action", "decline")
                if action == "decline":
                    continue
                name = d.get("name", "")
                if action == "edit" and d.get("edited"):
                    entry = d["edited"]
                else:
                    entry = d.get("proposed", {})
                if name and entry:
                    accepted_terms[name] = {
                        "category": entry.get("category", "Other"),
                        "definition": entry.get("definition", ""),
                        "description": entry.get("description", ""),
                    }
            if accepted_terms:
                _smart_merge_glossary(self._current_campaign_id, accepted_terms)
                # Also add to clean_glossary so NPC sync and entity migration see them
                clean_glossary.update(accepted_terms)
                _log.info("Glossary review: %d terms accepted/edited, merged into campaign", len(accepted_terms))

        # Apply merge directives (deduplication)
        if merges and isinstance(merges, list) and self._current_campaign_id:
            from campaigns import apply_glossary_merges
            merge_count = apply_glossary_merges(self._current_campaign_id, merges)
            if merge_count:
                _log.info("Applied %d glossary merge(s)", merge_count)

        # Sync NPCs from glossary entries
        if self._current_campaign_id:
            self._sync_npcs_from_glossary(clean_glossary, self._current_campaign_id)

        # Migrate glossary terms into entity registry
        if self._current_campaign_id:
            try:
                count = _migrate_glossary(self._current_campaign_id, clean_glossary)
                if count:
                    _log.info("Migrated %d glossary terms to entity registry", count)
            except Exception as e:
                _log.error("Entity migration from glossary failed: %s", e)

        # Refresh cached glossary context for subsequent stages
        self._glossary_context = self._build_glossary_context()

        _log.info("Glossary saved → %s (%d terms)", out_path, len(glossary))
        self._notify_stage("glossary", "done", {"glossary": clean_glossary})

    def _sync_npcs_from_glossary(self, glossary, campaign_id):
        # type: (dict, str) -> None
        """Create or update NPC characters from glossary entries with category='NPC'."""
        from characters import find_npc_by_name, create_npc, update_npc_description, get_characters
        from campaigns import add_campaign_npc

        # Get existing player character names to avoid creating NPC duplicates
        all_chars = get_characters()
        pc_names = set()
        for c in all_chars:
            if not c.get("is_npc"):
                pc_names.add(c.get("name", "").lower().strip())

        new_npcs = []   # type: List[str]
        updated_npcs = []  # type: List[str]

        for term, info in glossary.items():
            if not isinstance(info, dict):
                continue
            category = info.get("category", "").upper()
            if category != "NPC":
                continue

            name = term.strip()
            if not name:
                continue

            # Skip if this matches a player character or DM
            if name.lower() in pc_names:
                continue

            definition = info.get("definition", "")
            existing = find_npc_by_name(name, campaign_id)

            if existing:
                # Update description if the new one is richer
                old_desc = existing.get("npc_description", "")
                if definition and len(definition) > len(old_desc):
                    update_npc_description(existing["id"], definition)
                    updated_npcs.append(name)
                    _log.info("Updated NPC '%s' description", name)
            else:
                # Also check globally (NPC might exist in another campaign)
                global_existing = find_npc_by_name(name)
                if global_existing:
                    # Add this campaign to the NPC's campaign_ids
                    cids = global_existing.get("campaign_ids", [])
                    if campaign_id not in cids:
                        cids.append(campaign_id)
                        from characters import update_character
                        update_character(global_existing["id"], campaign_ids=cids)
                    if definition and len(definition) > len(global_existing.get("npc_description", "")):
                        update_npc_description(global_existing["id"], definition)
                    updated_npcs.append(name)
                else:
                    # Create new NPC
                    npc = create_npc(name, definition, campaign_id)
                    add_campaign_npc(campaign_id, npc["id"])
                    new_npcs.append(name)
                    _log.info("Created NPC '%s' from glossary", name)

        if new_npcs or updated_npcs:
            # Notify frontend
            data = json.dumps({"new": new_npcs, "updated": updated_npcs})
            self._js("window._onNpcSync && window._onNpcSync({})".format(data))
            _log.info("NPC sync: %d new, %d updated", len(new_npcs), len(updated_npcs))

    def _sync_npcs_from_session_data(self, npcs_data, session_id, session_date, campaign_id):
        # type: (List[dict], str, str, str) -> int
        """Create/enrich NPC characters from rich session NPC data.

        Returns count of NPCs created.
        """
        from characters import (
            find_npc_by_name, create_npc, enrich_npc, get_characters,
        )
        from campaigns import add_campaign_npc

        # Get player character names to avoid creating NPC duplicates
        all_chars = get_characters()
        pc_names = set()
        for c in all_chars:
            if not c.get("is_npc"):
                pc_names.add(c.get("name", "").lower().strip())

        created = 0
        for npc in npcs_data:
            if not isinstance(npc, dict):
                continue
            name = (npc.get("name") or "").strip()
            if not name or name.lower() in pc_names:
                continue

            race = npc.get("race", "")
            role = npc.get("role", "")
            desc = npc.get("description", "")
            attitude = npc.get("attitude", "")
            actions = npc.get("actions", "")
            if isinstance(actions, list):
                actions = " ".join(actions)
            current_status = npc.get("current_status", "")

            existing = find_npc_by_name(name, campaign_id)
            if existing:
                enrich_npc(
                    existing["id"], session_id=session_id, session_date=session_date,
                    race=race, role=role, description=desc, attitude=attitude,
                    actions=actions, current_status=current_status, campaign_id=campaign_id,
                )
            else:
                # Check globally too
                global_existing = find_npc_by_name(name)
                if global_existing:
                    enrich_npc(
                        global_existing["id"], session_id=session_id, session_date=session_date,
                        race=race, role=role, description=desc, attitude=attitude,
                        actions=actions, current_status=current_status, campaign_id=campaign_id,
                    )
                else:
                    new_npc = create_npc(
                        name, description=desc, campaign_id=campaign_id,
                        race=race, role=role, attitude=attitude, current_status=current_status,
                    )
                    add_campaign_npc(campaign_id, new_npc["id"])
                    # Also store initial session history
                    if session_id:
                        enrich_npc(
                            new_npc["id"], session_id=session_id, session_date=session_date,
                            race=race, role=role, description=desc, attitude=attitude,
                            actions=actions, current_status=current_status, campaign_id=campaign_id,
                        )
                    created += 1
                    _log.info("Created NPC '%s' from session data", name)

        return created

    # ── Leaderboard ───────────────────────────────────────────────────

    def _generate_leaderboard_streaming(self, txt_path: str, character_names: List[str],
                                        transcript: Optional[str] = None) -> str:
        _log.info("generate_leaderboard (streaming)  txt=%s", txt_path)
        if transcript is None:
            transcript = Path(txt_path).read_text(encoding="utf-8")
        names_str = ", ".join(character_names) if character_names else "Unknown"
        glossary_ctx = getattr(self, '_glossary_context', '') or self._build_glossary_context()
        entity_ctx = getattr(self, '_entity_context', '')
        if entity_ctx:
            glossary_ctx = glossary_ctx + entity_ctx

        session_date = getattr(self, '_session_date', '')
        prompt = """You are a D&D combat statistician. Extract combat stats per hero from this session transcript.

## Session Context
This session took place on {date}. Extract information ONLY from THIS session's transcript.

## CRITICAL RULES
- Only count numbers/rolls that are **explicitly mentioned** in the transcript
- Do NOT infer, estimate, or calculate anything that is not directly stated
- If a stat is not mentioned for a character, use 0
- "kills" = enemies explicitly killed by this character
- "assists" = enemies this character damaged but someone else killed
- "total_damage" = sum of all damage numbers explicitly stated for this character
- "avg_d20" = average of all d20 rolls explicitly stated (0 if none mentioned)
- "nat_20s" = count of natural 20s explicitly mentioned
- "nat_1s" = count of natural 1s explicitly mentioned
- Only include player characters, not NPCs or the DM

## Characters
{names}

## Confidence Scoring
- Include a "confidence" field (0-100) for each hero indicating how reliable the stats are:
  - 90-100: explicit dice rolls and damage numbers clearly stated in transcript
  - 50-89: some stats partially inferred from context
  - 0-49: mostly guessing, very few explicit numbers in transcript

## Output Format
Return ONLY a JSON object (no markdown, no explanation):
{{
  "CharName": {{"kills": 0, "assists": 0, "total_damage": 0, "avg_d20": 0, "nat_20s": 0, "nat_1s": 0, "confidence": 75}}
}}{glossary}

## Session Transcript
{transcript}""".format(
            date=session_date,
            names=names_str,
            glossary=glossary_ctx,
            transcript=transcript,
        )
        return self._llm_stream(prompt, "leaderboard", max_tokens=2048)

    def _save_leaderboard(self, text: str, out_dir: Path) -> None:
        leaderboard = self._extract_json_object(text)
        if leaderboard is None:
            _log.error("leaderboard: no valid JSON object found")
            self._notify_stage("leaderboard", "error", {"error": "Could not parse leaderboard"})
            return
        out_path = out_dir / "leaderboard.json"
        out_path.write_text(json.dumps(leaderboard, indent=2, ensure_ascii=False), encoding="utf-8")
        if self._current_session_id:
            update_session(self._current_session_id, leaderboard_path=str(out_path))
        _log.info("Leaderboard saved → %s (%d characters)", out_path, len(leaderboard))
        self._notify_stage("leaderboard", "done", {"leaderboard": leaderboard})

    # ── Locations ─────────────────────────────────────────────────────

    def _generate_locations_streaming(self, txt_path: str, character_names: List[str],
                                      transcript: Optional[str] = None) -> str:
        _log.info("generate_locations (streaming)  txt=%s", txt_path)
        if transcript is None:
            transcript = Path(txt_path).read_text(encoding="utf-8")
        names_str = ", ".join(character_names) if character_names else "Unknown"
        glossary_ctx = getattr(self, '_glossary_context', '') or self._build_glossary_context()
        entity_ctx = getattr(self, '_entity_context', '')
        if entity_ctx:
            glossary_ctx = glossary_ctx + entity_ctx

        session_date = getattr(self, '_session_date', '')
        prompt = """You are a D&D cartographer and world-builder. Extract all locations from this session transcript.

## Session Context
This session took place on {date}. Extract information ONLY from THIS session's transcript.

## Rules
- ONLY include locations the party DEFINITIVELY visited during this session
- "description" = what the party learned about this place (appearance, atmosphere, hazards)
- "connections" = other locations this place connects to, including directional relationship (e.g. "north of X", "2 hours walk east")
- "relative_position" = MUST be based on transcript evidence only — distances, travel times, directions explicitly mentioned. Do NOT guess spatial relationships
- "visit_order" = number each location by order of first visit during the session (1 = first visited)
- Number each location by order of first visit during the session (1 = first visited)

## Characters
{names}

## Classification
For each location, also classify:
- "region_type": terrain/environment around this location. One of: sea, coast, plains, forest, jungle, mountains, desert, swamp, underground, urban, ruins, arctic
- "location_type": what kind of place it is. One of: city, town, village, inn, temple, ship, dock, farm, camp, cave, ruins, fortress, tower, clearing, bridge, crossroads, dungeon, shrine, market, manor, other

## Output Format
Return ONLY a valid JSON array (no markdown, no explanation):
[
  {{
    "name": "Location Name",
    "description": "What the party knows about this place.",
    "connections": ["north of Connected Location 1", "2 hours walk east to Connected Location 2"],
    "relative_position": "Spatial relationship based on transcript evidence only",
    "visit_order": 1,
    "region_type": "coast",
    "location_type": "city",
    "confidence": 90,
    "reasoning": "Why you believe this location extraction is accurate"
  }}
]

## Confidence Score Rules
- "confidence" = 0-100 integer. How certain are you that this location was actually visited and the details are correct?
- "reasoning" = brief explanation of your confidence (what transcript evidence supports this)
- 95-100 = explicitly described location with clear details in transcript
- 70-94 = mentioned but some details inferred or ambiguous
- below 70 = barely mentioned or heavily inferred{glossary}

## Session Transcript
{transcript}""".format(
            date=session_date,
            names=names_str,
            glossary=glossary_ctx,
            transcript=transcript,
        )
        return self._llm_stream(prompt, "locations", max_tokens=4096)

    @staticmethod
    def _strip_confidence(items):
        # type: (List[Dict]) -> List[Dict]
        """Strip confidence/reasoning fields from entity items before saving artifact files."""
        for item in items:
            item.pop("confidence", None)
            item.pop("reasoning", None)
        return items

    @staticmethod
    def _strip_confidence_loot(loot):
        # type: (Dict) -> Dict
        """Strip confidence/reasoning from loot items and gold entries."""
        for item in loot.get("items", []):
            item.pop("confidence", None)
            item.pop("reasoning", None)
        for gold in loot.get("gold", []):
            gold.pop("confidence", None)
            gold.pop("reasoning", None)
        return loot

    def _save_locations(self, text: str, out_dir: Path) -> None:
        locations = self._repair_json_array(text)
        if locations is None:
            _log.error("Locations JSON parse failed for text: %s…", text[:200])
            (out_dir / "locations.raw").write_text(text, encoding="utf-8")
            self._notify_stage("locations", "error", {"error": "Could not parse locations JSON. Raw output saved."})
            return
        # Preserve confidence data for review, strip from saved artifact
        import copy as _copy
        locations_with_conf = _copy.deepcopy(locations)
        self._strip_confidence(locations)
        out_path = out_dir / "locations.json"
        out_path.write_text(json.dumps(locations, indent=2, ensure_ascii=False), encoding="utf-8")
        if self._current_session_id:
            update_session(self._current_session_id, locations_path=str(out_path))

        # Split by confidence: auto-apply high, review low
        threshold = self._ENTITY_REVIEW_THRESHOLD
        auto_apply = [loc for loc in locations_with_conf if loc.get("confidence", 100) >= threshold]
        review_queue = [loc for loc in locations_with_conf if loc.get("confidence", 100) < threshold]

        # Auto-apply high-confidence entities
        if self._current_campaign_id:
            try:
                for loc in auto_apply:
                    self._apply_location_entity(loc)
            except Exception as e:
                _log.error("Entity registry update for locations failed: %s", e)

        auto_applied_summary = [
            {"name": loc.get("name", ""), "action": "update" if (_find_entity_fuzzy(self._current_campaign_id, loc.get("name", ""), "location") if self._current_campaign_id else None) else "create", "confidence": loc.get("confidence", 100)}
            for loc in auto_apply
        ]

        if review_queue:
            _log.info("Locations: %d auto-applied, %d need review", len(auto_apply), len(review_queue))
            decisions = self._request_entity_review("locations", review_queue, auto_applied_summary)
            self._apply_entity_decisions("locations", decisions, locations_with_conf)

        _log.info("Locations saved → %s (%d locations)", out_path, len(locations))
        self._notify_stage("locations", "done", {"locations": locations})

    def _apply_location_entity(self, loc):
        # type: (dict) -> None
        """Apply a single location to the entity registry."""
        if not self._current_campaign_id:
            return
        name = loc.get("name", "")
        if not name:
            return
        existing = _find_entity_fuzzy(self._current_campaign_id, name, "location")
        props = {
            "visit_order": loc.get("visit_order"),
            "connections": loc.get("connections", []),
            "relative_position": loc.get("relative_position", ""),
            "status": "visited",
        }
        if existing:
            _update_entity(
                self._current_campaign_id, existing["id"],
                self._current_session_id or "",
                session_date=getattr(self, '_session_date', ''),
                description=loc.get("description", ""),
                properties=props,
                change_summary="Visited this session",
            )
        else:
            _create_entity(
                campaign_id=self._current_campaign_id,
                entity_type="location",
                name=name,
                session_id=self._current_session_id or "",
                session_date=getattr(self, '_session_date', ''),
                definition=loc.get("description", "")[:200],
                description=loc.get("description", ""),
                properties=props,
            )

    # ── NPCs ──────────────────────────────────────────────────────────

    def _generate_npcs_streaming(self, txt_path: str, character_names: List[str],
                                  transcript: Optional[str] = None) -> str:
        _log.info("generate_npcs (streaming)  txt=%s", txt_path)
        if transcript is None:
            transcript = Path(txt_path).read_text(encoding="utf-8")
        names_str = ", ".join(character_names) if character_names else "Unknown"
        glossary_ctx = getattr(self, '_glossary_context', '') or self._build_glossary_context()
        entity_ctx = getattr(self, '_entity_context', '')
        if entity_ctx:
            glossary_ctx = glossary_ctx + entity_ctx

        session_date = getattr(self, '_session_date', '')
        prompt = """You are a D&D campaign chronicler specializing in NPC documentation. Extract all NPCs encountered or mentioned in this session transcript.

## Session Context
This session took place on {date}. Extract information ONLY from THIS session's transcript.

## Rules
- Include every NPC: allies, enemies, shopkeepers, quest givers, bystanders
- Do NOT include player characters: {names}
- Cross-reference with the campaign glossary entries below. Use existing NPC names and details exactly as they appear in the glossary.
- Update information based on what is newly learned this session.
- "race" = species/race if mentioned or inferable (e.g. "Human", "Elf", "Dwarf"), or "Unknown"
- "role" = their function in the story (e.g. "tavern keeper", "bandit leader", "quest giver")
- "description" = physical appearance and notable traits mentioned
- "attitude" = disposition toward the party (friendly, neutral, hostile, unknown)
- "actions" = what they did during this session
- "current_status" = where they are / what state they're in at session end (alive, dead, fled, unknown)
- "glossary_match" = true if this NPC matches a glossary entry, false otherwise

## Characters (do NOT include these)
{names}

## Output Format
Return ONLY a valid JSON array (no markdown, no explanation):
[
  {{
    "name": "NPC Name",
    "race": "Race",
    "role": "Their role or title",
    "description": "Physical description and notable traits.",
    "attitude": "friendly",
    "actions": "What they did this session.",
    "current_status": "Alive, last seen at the tavern.",
    "glossary_match": true,
    "confidence": 90,
    "reasoning": "Why you believe this NPC extraction is accurate"
  }}
]

## Confidence Score Rules
- "confidence" = 0-100 integer. How certain are you that this NPC exists and the details are correct?
- "reasoning" = brief explanation of your confidence (what transcript evidence supports this)
- 95-100 = NPC clearly named and described in dialogue/narration
- 70-94 = mentioned by name but some details inferred
- below 70 = barely mentioned or heavily inferred from context{glossary}

## Session Transcript
{transcript}""".format(
            date=session_date,
            names=names_str,
            glossary=glossary_ctx,
            transcript=transcript,
        )
        return self._llm_stream(prompt, "npcs", max_tokens=4096)

    def _save_npcs(self, text: str, out_dir: Path) -> None:
        npcs = self._repair_json_array(text)
        if npcs is None or len(npcs) == 0:
            _log.error("NPCs JSON parse failed for text: %s…", text[:200])
            (out_dir / "npcs.raw").write_text(text, encoding="utf-8")
            self._notify_stage("npcs", "error", {"error": "Could not parse NPCs JSON. Raw output saved."})
            return
        # Filter to dicts only (defensive against malformed items)
        npcs = [n for n in npcs if isinstance(n, dict)]
        if not npcs:
            _log.error("NPCs JSON contained no valid dict items")
            (out_dir / "npcs.raw").write_text(text, encoding="utf-8")
            self._notify_stage("npcs", "error", {"error": "Could not parse NPCs JSON. Raw output saved."})
            return
        import copy as _copy
        npcs_with_conf = _copy.deepcopy(npcs)
        self._strip_confidence(npcs)
        out_path = out_dir / "npcs.json"
        out_path.write_text(json.dumps(npcs, indent=2, ensure_ascii=False), encoding="utf-8")
        if self._current_session_id:
            update_session(self._current_session_id, npcs_path=str(out_path))

        # Split by confidence
        threshold = self._ENTITY_REVIEW_THRESHOLD
        auto_apply = [n for n in npcs_with_conf if n.get("confidence", 100) >= threshold]
        review_queue = [n for n in npcs_with_conf if n.get("confidence", 100) < threshold]

        auto_applied_summary = [
            {"name": n.get("name", ""), "action": "create", "confidence": n.get("confidence", 100)}
            for n in auto_apply
        ]

        if review_queue:
            _log.info("NPCs: %d auto-applied, %d need review", len(auto_apply), len(review_queue))
            decisions = self._request_entity_review("npcs", review_queue, auto_applied_summary)
            # NPCs don't go into entity registry directly, but decisions are logged
            _log.info("NPC review decisions received: %d", len(decisions))

        # Sync NPCs to character registry with rich session data
        if self._current_campaign_id:
            session_date = getattr(self, '_session_date', '')
            self._sync_npcs_from_session_data(
                npcs, self._current_session_id or "", session_date, self._current_campaign_id,
            )

        _log.info("NPCs saved → %s (%d NPCs)", out_path, len(npcs))
        self._notify_stage("npcs", "done", {"npcs": npcs})

    # ── Loot ──────────────────────────────────────────────────────────

    # TODO: Future enhancement — diff D&D Beyond backpack between sessions
    # beyond.py already fetches backpack[] with {name, quantity, equipped, magic}
    # and currency {cp, sp, ep, gp, pp}. Store snapshots per session to detect changes.
    def _generate_loot_streaming(self, txt_path: str, character_names: List[str],
                                  transcript: Optional[str] = None) -> str:
        _log.info("generate_loot (streaming)  txt=%s", txt_path)
        if transcript is None:
            transcript = Path(txt_path).read_text(encoding="utf-8")
        names_str = ", ".join(character_names) if character_names else "Unknown"
        glossary_ctx = getattr(self, '_glossary_context', '') or self._build_glossary_context()
        entity_ctx = getattr(self, '_entity_context', '')
        if entity_ctx:
            glossary_ctx = glossary_ctx + entity_ctx
        session_date = getattr(self, '_session_date', '')

        prompt = """You are a D&D loot tracker. Extract all items acquired and gold/currency transactions from this session transcript.

## Session Context
This session took place on {date}. Extract information ONLY from THIS session's transcript.

## Rules
- ONLY include items NEWLY ACQUIRED during THIS session — items that changed hands
- Do NOT include items characters already had from previous sessions or starting equipment
- Do NOT include items merely mentioned, discussed, or identified but not actually taken/purchased/received
- Do NOT include items BOUGHT or PURCHASED from merchants/shops (spending money to acquire goods)
- Do NOT include items SPENT, USED, or CONSUMED during the session (potions drunk, scrolls used, ammunition spent)
- Only items that represent a NET GAIN to the party's inventory: looted, found, gifted, crafted, or stolen
- "items" = physical items looted, bought, crafted, gifted, or found
  - "item" = item name
  - "type" = weapon, armor, potion, scroll, wondrous, mundane, etc.
  - "magical" = true/false (only true if explicitly stated as magical)
  - "looted_by" = character who took/received the item (or "Party" if shared)
  - "looted_from" = source (enemy name, chest, shop, NPC gift, etc.)
  - "when" = approximate moment in the session (e.g. "after defeating the ogre")
  - "where" = location where the item was acquired
  - "how" = method of acquisition (looted, bought, found, gifted, crafted, stolen)
- "gold" = currency transactions
  - "amount" = numeric amount
  - "currency" = gp, sp, cp, ep, pp
  - "gained_by" = who received it (character name or "Party")
  - "source" = where it came from (enemy, quest reward, sale, NPC, etc.)
  - "context" = brief description of the transaction
- Only include items/gold explicitly mentioned in the transcript

## Characters
{names}

## Output Format
Return ONLY a JSON object (no markdown, no explanation):
{{
  "items": [
    {{"item": "Longsword +1", "type": "weapon", "magical": true, "looted_by": "CharName", "looted_from": "Goblin Chief", "when": "after the cave battle", "where": "Goblin Cave", "how": "looted", "confidence": 90, "reasoning": "Explicitly looted after combat"}}
  ],
  "gold": [
    {{"amount": 50, "currency": "gp", "gained_by": "Party", "source": "Goblin Chief's chest", "context": "Found in a locked chest after clearing the cave", "confidence": 90, "reasoning": "DM described the chest contents"}}
  ]
}}

## Confidence Score Rules
- "confidence" = 0-100 integer. How certain are you that this item/gold was actually acquired this session?
- "reasoning" = brief explanation of your confidence (what transcript evidence supports this)
- 95-100 = explicitly stated loot with clear recipient and source
- 70-94 = mentioned but details partially inferred (who took it, exact amount, etc.)
- below 70 = barely mentioned or heavily inferred{glossary}

## Session Transcript
{transcript}""".format(
            date=session_date,
            names=names_str,
            glossary=glossary_ctx,
            transcript=transcript,
        )
        return self._llm_stream(prompt, "loot", max_tokens=4096)

    def _save_loot(self, text: str, out_dir: Path) -> None:
        loot = self._extract_json_object(text)
        if loot is None:
            _log.error("loot: no valid JSON object found")
            self._notify_stage("loot", "error", {"error": "Could not parse loot"})
            return
        import copy as _copy
        loot_with_conf = _copy.deepcopy(loot)
        self._strip_confidence_loot(loot)
        out_path = out_dir / "loot.json"
        out_path.write_text(json.dumps(loot, indent=2, ensure_ascii=False), encoding="utf-8")
        if self._current_session_id:
            update_session(self._current_session_id, loot_path=str(out_path))

        # Split loot items by confidence
        threshold = self._ENTITY_REVIEW_THRESHOLD
        all_loot_items = loot_with_conf.get("items", []) + loot_with_conf.get("gold", [])
        auto_apply_items = [it for it in loot_with_conf.get("items", []) if it.get("confidence", 100) >= threshold]
        review_items = [it for it in all_loot_items if it.get("confidence", 100) < threshold]

        # Auto-apply high-confidence items to entity registry
        if self._current_campaign_id:
            try:
                for item in auto_apply_items:
                    self._apply_loot_entity(item)
            except Exception as e:
                _log.error("Entity registry update for loot failed: %s", e)

        auto_applied_summary = [
            {"name": it.get("item", it.get("source", "")), "action": "create", "confidence": it.get("confidence", 100)}
            for it in all_loot_items if it.get("confidence", 100) >= threshold
        ]

        if review_items:
            _log.info("Loot: %d auto-applied, %d need review", len(auto_applied_summary), len(review_items))
            # Normalize loot items to have a "name" field for the review system
            for it in review_items:
                if "item" in it and "name" not in it:
                    it["name"] = it["item"]
                elif "source" in it and "name" not in it:
                    it["name"] = "Gold: {}".format(it.get("source", ""))
            decisions = self._request_entity_review("loot", review_items, auto_applied_summary)
            self._apply_entity_decisions("loot", decisions, all_loot_items)

        items_count = len(loot.get("items", []))
        gold_count = len(loot.get("gold", []))
        _log.info("Loot saved → %s (%d items, %d gold transactions)", out_path, items_count, gold_count)
        self._notify_stage("loot", "done", {"loot": loot})

    def _apply_loot_entity(self, item):
        # type: (dict) -> None
        """Apply a single loot item to the entity registry."""
        if not self._current_campaign_id:
            return
        name = item.get("item", "")
        if not name:
            return
        existing = _find_entity_fuzzy(self._current_campaign_id, name, "item")
        props = {
            "item_type": item.get("type", ""),
            "magical": item.get("magical", False),
            "owner_name": item.get("looted_by", ""),
            "status": "owned",
        }
        if existing:
            _update_entity(
                self._current_campaign_id, existing["id"],
                self._current_session_id or "",
                session_date=getattr(self, '_session_date', ''),
                properties=props,
                change_summary="Acquired by {}".format(item.get("looted_by", "unknown")),
            )
        else:
            _create_entity(
                campaign_id=self._current_campaign_id,
                entity_type="item",
                name=name,
                session_id=self._current_session_id or "",
                session_date=getattr(self, '_session_date', ''),
                definition="{} {} ({})".format(
                    "Magical" if item.get("magical") else "",
                    item.get("type", "item"),
                    item.get("how", "found"),
                ).strip(),
                properties=props,
            )

    # ── Missions ──────────────────────────────────────────────────────

    def _generate_missions_streaming(self, txt_path: str, character_names: List[str],
                                      transcript: Optional[str] = None) -> str:
        _log.info("generate_missions (streaming)  txt=%s", txt_path)
        if transcript is None:
            transcript = Path(txt_path).read_text(encoding="utf-8")
        names_str = ", ".join(character_names) if character_names else "Unknown"
        glossary_ctx = getattr(self, '_glossary_context', '') or self._build_glossary_context()
        entity_ctx = getattr(self, '_entity_context', '')
        if entity_ctx:
            glossary_ctx = glossary_ctx + entity_ctx

        session_date = getattr(self, '_session_date', '')
        prompt = """You are a D&D quest tracker. Extract all quests, missions, and objectives from this session transcript.

## Session Context
This session took place on {date}. Extract information ONLY from THIS session's transcript.

## Rules
- Include quests that were started, continued, or completed during this session
- "name" = a concise, descriptive quest name
- "status" = one of: "started", "continued", "completed"
  - "started" = quest was first introduced this session
  - "continued" = quest was already known and progress was made
  - "completed" = quest objective was fulfilled this session
- "description" = what the quest is about
- "givers" = NPCs or entities who gave/assigned this quest
- "objectives" = list of specific objectives or goals
- "rewards_mentioned" = any rewards discussed or promised (gold, items, favors, etc.)
- "notes" = any additional context (complications, time limits, moral dilemmas)

## Characters
{names}

## Output Format
Return ONLY a valid JSON array (no markdown, no explanation):
[
  {{
    "name": "Quest Name",
    "status": "started",
    "description": "What the quest is about.",
    "givers": ["NPC Name"],
    "objectives": ["Objective 1", "Objective 2"],
    "rewards_mentioned": "100 gp and a magic item",
    "notes": "Must be completed before the full moon.",
    "confidence": 90,
    "reasoning": "Why you believe this quest extraction is accurate"
  }}
]

## Confidence Score Rules
- "confidence" = 0-100 integer. How certain are you that this quest exists and the details are correct?
- "reasoning" = brief explanation of your confidence (what transcript evidence supports this)
- 95-100 = quest explicitly given or completed with clear objectives
- 70-94 = quest implied or partially discussed, some details inferred
- below 70 = vague reference, heavily inferred from context{glossary}

## Session Transcript
{transcript}""".format(
            date=session_date,
            names=names_str,
            glossary=glossary_ctx,
            transcript=transcript,
        )
        return self._llm_stream(prompt, "missions", max_tokens=4096)

    def _save_missions(self, text: str, out_dir: Path) -> None:
        missions = self._repair_json_array(text)
        if missions is None:
            _log.error("Missions JSON parse failed for text: %s…", text[:200])
            (out_dir / "missions.raw").write_text(text, encoding="utf-8")
            self._notify_stage("missions", "error", {"error": "Could not parse missions JSON. Raw output saved."})
            return
        import copy as _copy
        missions_with_conf = _copy.deepcopy(missions)
        self._strip_confidence(missions)
        out_path = out_dir / "missions.json"
        out_path.write_text(json.dumps(missions, indent=2, ensure_ascii=False), encoding="utf-8")
        if self._current_session_id:
            update_session(self._current_session_id, missions_path=str(out_path))

        # Split by confidence
        threshold = self._ENTITY_REVIEW_THRESHOLD
        auto_apply = [m for m in missions_with_conf if m.get("confidence", 100) >= threshold]
        review_queue = [m for m in missions_with_conf if m.get("confidence", 100) < threshold]

        # Auto-apply high-confidence missions to entity registry
        if self._current_campaign_id:
            try:
                for mission in auto_apply:
                    self._apply_mission_entity(mission)
            except Exception as e:
                _log.error("Entity registry update for missions failed: %s", e)

        auto_applied_summary = [
            {"name": m.get("name", ""), "action": "update" if (_find_entity_fuzzy(self._current_campaign_id, m.get("name", ""), "mission") if self._current_campaign_id else None) else "create", "confidence": m.get("confidence", 100)}
            for m in auto_apply
        ]

        if review_queue:
            _log.info("Missions: %d auto-applied, %d need review", len(auto_apply), len(review_queue))
            decisions = self._request_entity_review("missions", review_queue, auto_applied_summary)
            self._apply_entity_decisions("missions", decisions, missions_with_conf)

        _log.info("Missions saved → %s (%d missions)", out_path, len(missions))
        self._notify_stage("missions", "done", {"missions": missions})

    def _apply_mission_entity(self, mission):
        # type: (dict) -> None
        """Apply a single mission to the entity registry."""
        if not self._current_campaign_id:
            return
        name = mission.get("name", "")
        if not name:
            return
        existing = _find_entity_fuzzy(self._current_campaign_id, name, "mission")
        props = {
            "status": mission.get("status", "active"),
            "givers": mission.get("givers", []),
            "objectives": [
                {"text": obj, "completed": False}
                for obj in mission.get("objectives", [])
            ],
            "rewards_mentioned": mission.get("rewards_mentioned", ""),
        }
        if existing:
            _update_entity(
                self._current_campaign_id, existing["id"],
                self._current_session_id or "",
                session_date=getattr(self, '_session_date', ''),
                description=mission.get("description", ""),
                properties=props,
                change_summary="Status: {}".format(mission.get("status", "continued")),
            )
        else:
            _create_entity(
                campaign_id=self._current_campaign_id,
                entity_type="mission",
                name=name,
                session_id=self._current_session_id or "",
                session_date=getattr(self, '_session_date', ''),
                definition=mission.get("description", "")[:200],
                description=mission.get("description", ""),
                properties=props,
            )

    def _generate_fact_extraction_streaming(self, txt_path: str, character_names: List[str],
                                             transcript: Optional[str] = None) -> str:
        """LLM stage: extract structured facts from the labeled transcript."""
        _log.info("generate_fact_extraction (streaming)  txt=%s", txt_path)
        if transcript is None:
            transcript = Path(txt_path).read_text(encoding="utf-8")
        names_str = ", ".join(character_names) if character_names else "Unknown"
        glossary_ctx = getattr(self, '_glossary_context', '') or self._build_glossary_context()
        entity_ctx = getattr(self, '_entity_context', '')
        if entity_ctx:
            glossary_ctx = glossary_ctx + entity_ctx
        session_date = getattr(self, '_session_date', '')

        prompt = f"""You are a D&D session analyst. Extract ALL important facts from this session transcript into a structured JSON array.

A "fact" is any discrete event, action, dialogue, decision, discovery, or combat moment that matters to the story. Each fact captures WHO did WHAT, WHY, and WHEN.

Your ENTIRE response must be a single valid JSON array. No text before or after. No trailing commas.

[
  {{
    "type": "action | dialogue | event | decision | discovery | combat | noise",
    "who": "Character Name",
    "what": "Brief description of what happened",
    "why": "Motivation or context (empty string if unclear)",
    "when": "Relative timing or context in session (e.g., 'at the start', 'during combat at the bridge')",
    "speaker": "The speaker label from the transcript who said/narrated this (e.g., 'DM', 'Khuzz')",
    "segment_indices": [42, 43],
    "original_text": "The exact transcript lines this fact comes from (include speaker label and timestamp if present)",
    "confidence": 92,
    "reasoning": "Why you are confident (or not) about this fact and its speaker attribution"
  }}
]

## Fact Types
- "action": A character performs a physical or magical action
- "dialogue": An important conversation or statement
- "event": Something happens in the world (weather, NPC arrival, etc.)
- "decision": A character or party makes a meaningful choice
- "discovery": Finding something, learning something, a reveal
- "combat": A combat action, attack, spell cast in combat
- "noise": Non-D&D content (side conversation, break chatter, off-topic). ONLY use this if you are 100% certain this is NOT game content. Include the original text so the DM can verify.

## Segment Indices
The transcript has numbered lines. For each fact, list the line numbers (0-based) of the transcript lines this fact comes from. Count from the top of the transcript — each line that starts with a speaker label like "[DM]" or "[Character]" is a new segment.

## Confidence Scoring
- 95-100: Speaker attribution is clearly correct, fact is unambiguous from the text
- 80-94: Fact is likely correct but some ambiguity in speaker or details
- 60-79: Significant uncertainty — speaker diarization may have merged speakers, or fact is partially inferred
- below 60: Very uncertain — heavily inferred or speaker attribution likely wrong

**Be critical about speaker attribution.** Audio diarization often bundles multiple speakers into one segment. If a segment contains dialogue that seems to switch speakers mid-sentence, or if the attributed speaker says something inconsistent with their character, lower the confidence and explain why in the reasoning.

## Rules
- Extract 15-40 facts depending on session length (aim for all important moments)
- Chronological order
- **ALWAYS use canonical spellings** from the Characters and Glossary sections below. Audio transcription often misspells proper nouns (e.g., "Marchal" instead of "Warchaal"). Always cross-reference names against the known characters and glossary terms.
- Include the original transcript text snippet for each fact
- If the DM is narrating what a character does, the "who" is the character but the "speaker" is "DM"
- Lower confidence when speaker attribution seems inconsistent with the content

## Session Context
This session took place on {session_date}. Extract facts ONLY from THIS session's transcript.

## Characters in This Session
{names_str}{glossary_ctx}

## Transcript
{transcript}"""
        return self._llm_stream(prompt, "fact_extraction", max_tokens=8192)

    def _generate_timeline_streaming(self, txt_path: str, character_names: List[str],
                                      transcript: Optional[str] = None) -> str:
        _log.info("generate_timeline (streaming)  txt=%s", txt_path)
        # Prefer SRT for timestamps; fall back to cached TXT transcript
        srt_path = Path(txt_path).with_suffix('.srt')
        if srt_path.exists():
            source = srt_path.read_text(encoding="utf-8")
            source_label = "SRT subtitle file (timestamps are in the SRT header lines — use them)"
        elif transcript is not None:
            source = transcript
            source_label = "plain text transcript (timestamps may not be available)"
        else:
            source = Path(txt_path).read_text(encoding="utf-8")
            source_label = "plain text transcript (timestamps may not be available)"
        names_str = ", ".join(character_names) if character_names else "Unknown"
        glossary_ctx = getattr(self, '_glossary_context', '') or self._build_glossary_context()
        entity_ctx = getattr(self, '_entity_context', '')
        if entity_ctx:
            glossary_ctx = glossary_ctx + entity_ctx
        session_date = getattr(self, '_session_date', '')
        prompt = f"""You are a D&D session archivist. Extract the most pivotal, story-defining moments from this session into a structured timeline.

Analyze the {source_label} and identify 8–15 key moments in chronological order. Focus only on truly significant events: major plot reveals, combat outcomes, critical decisions, pivotal character moments, dramatic confrontations, and important discoveries.

Your ENTIRE response must be a single valid JSON array. No text before or after. No trailing commas. Ensure every string value is properly escaped.

[
  {{
    "time": "timestamp string like \\"01:23\\" or \\"1:02:45\\", or null if unavailable",
    "title": "Short event title (5–8 words max)",
    "summary": "1-2 sentence description of what happened.",
    "details": "Richer context: who was involved, what was said or decided, what led to this moment, the consequences.",
    "importance": "high",
    "type": "combat"
  }}
]

Importance levels:
- "high": plot reveals, combat outcomes, major decisions, pivotal character moments
- "medium": notable NPC interactions, discoveries, lore reveals, faction events
- "low": minor events still worth noting for continuity

Event types (pick the single best match):
- "combat": battles, fights, combat encounters
- "discovery": finding items, locations, secrets, lore
- "dialogue": important conversations, negotiations, persuasion
- "travel": journeys, arrivals, departures, exploration
- "magic": spells, rituals, magical events, enchantments
- "rest": camps, rests, downtime, healing
- "death": character deaths, NPC deaths, resurrections
- "treasure": loot, rewards, acquisitions
- "puzzle": riddles, traps, puzzles, challenges
- "npc": meeting new NPCs, faction interactions
- "boss": boss encounters, major villain confrontations
- "stealth": infiltration, sneaking, espionage
- "ritual": ceremonies, pacts, oaths, transformations
- "betrayal": deception, treachery, plot twists
- "victory": triumphs, quest completions, celebrations

Rules:
- Chronological order
- If using SRT: extract the start time from the SRT timestamp block nearest each event (format: "01:23" or "1:02:45")
- Be specific: names, places, items, dice outcomes if mentioned
- "details" must add meaningful context beyond "summary" — what led to this, consequences
- Quality over quantity: only include moments genuinely important to the session's narrative arc. Omit routine actions, minor chatter, and logistical moments
- Temporal spacing: key moments should be spread across the full session. If two events happen within 2 minutes of each other, only include the more significant one unless both are truly pivotal
- Return 8–15 events covering the full session arc

## Session Context
This session took place on {session_date}. Extract information ONLY from THIS session's transcript.

## Characters in This Session
{names_str}{glossary_ctx}

## Transcript
{source}"""
        return self._llm_stream(prompt, "timeline", max_tokens=4096)

    def _generate_dm_notes_internal(self, txt_path: str, character_names: List[str]) -> dict:
        _log.info("generate_dm_notes  txt=%s", txt_path)
        try:
            transcript = Path(txt_path).read_text(encoding="utf-8")
            names_str = ", ".join(character_names) if character_names else "Unknown"
            prompt = f"""You are an expert Dungeon Master's assistant. Analyze this D&D session transcript and produce structured DM notes.

Be thorough, specific, and practical. The DM will use these notes to prepare future sessions.

Format your response in Markdown with exactly these sections:

## Key Events & Timeline
A concise chronological bullet list of what happened, including location changes and major decisions.

## NPCs Encountered
For each NPC: name, role/description, attitude toward the party, any promises made or threats issued, and current status/location.

## Items & Loot
List EVERY item found, looted, purchased, received, gifted, consumed, or mentioned in the session. For each: who received/used it, what it does (if known), and whether it's identified. Include ALL gold/currency transactions (gained and spent). Be thorough — missing loot is the most common error in DM notes.

## Character Development
Notable moments per character: decisions made, personal arcs advanced, relationships changed, any leveling or ability use worth noting.

## World-Building & Lore
Locations visited or described, factions mentioned, history or lore revealed, hooks planted.

## Open Plot Threads
Unresolved questions, cliffhangers, mysteries, and promises that need follow-up.

## DM Action Items for Next Session
A concrete to-do list: NPCs to prepare, locations to flesh out, rules to look up, consequences to plan, player rewards pending.

## Characters in This Session
{names_str}

## Session Transcript
{transcript}"""

            notes = self._llm_call(prompt)
            out_path = Path(txt_path).parent / "dm_notes.md"
            out_path.write_text(notes, encoding="utf-8")
            if self._current_session_id:
                update_session(self._current_session_id, dm_notes_path=str(out_path))
            _log.info("DM notes saved → %s", out_path)
            return {"notes": notes}
        except Exception as e:
            _log.error("generate_dm_notes failed: %s", e, exc_info=True)
            return {"error": str(e)}

    def _generate_scenes_internal(self, txt_path: str, character_names: List[str]) -> dict:
        _log.info("generate_scenes  txt=%s", txt_path)
        try:
            transcript = Path(txt_path).read_text(encoding="utf-8")
            names_str = ", ".join(character_names) if character_names else "Unknown"
            prompt = f"""You are a cinematic AI director extracting visually compelling scenes from a D&D session transcript to generate AI video prompts.

Identify 6–12 of the most dramatic or visually interesting moments in chronological order. For each, craft a detailed video generation prompt optimized for tools like Sora, Runway, or Kling.

Return ONLY a valid JSON array (no markdown, no explanation) with this exact structure:
[
  {{
    "title": "Short evocative scene title",
    "description": "1–2 sentence description of what happens in this scene.",
    "videoPrompt": "Cinematic video prompt in present tense: describe the environment, time of day, lighting, atmosphere, figures present described by role/appearance not name, their action or movement, camera angle and motion, visual style. 3–5 sentences."
  }}
]

Rules:
- Focus on cinematic moments: combat, exploration, reveals, confrontations, emotional beats
- Use character names where appropriate (e.g. "Aragorn raises his sword") alongside visual descriptions
- Be specific about lighting, environment, mood
- Do not include dialogue in videoPrompt

## Characters in This Session
{names_str}

## Session Transcript
{transcript}"""

            raw = self._llm_call(prompt).strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()
            scenes = json.loads(raw)

            out_path = Path(txt_path).parent / "scenes.json"
            out_path.write_text(json.dumps(scenes, indent=2, ensure_ascii=False), encoding="utf-8")
            if self._current_session_id:
                update_session(self._current_session_id, scenes_path=str(out_path))
            _log.info("Scenes saved → %s (%d scenes)", out_path, len(scenes))
            return {"scenes": scenes}
        except json.JSONDecodeError as e:
            _log.error("generate_scenes: bad JSON from LLM: %s", e)
            return {"error": f"Could not parse scenes JSON: {e}"}
        except Exception as e:
            _log.error("generate_scenes failed: %s", e, exc_info=True)
            return {"error": str(e)}

    # ── Campaign / Season management ─────────────────────────────────────────

    def get_campaigns(self) -> list:
        _log.debug("get_campaigns called")
        result = _get_campaigns()
        _log.debug("get_campaigns → %d campaigns", len(result))
        return result

    def create_campaign(self, name: str, seasons: list) -> dict:
        _log.info("create_campaign  name=%s  seasons=%d", name, len(seasons))
        try:
            campaign = _create_campaign(name, seasons)
            return {"ok": True, "campaign": campaign}
        except Exception as e:
            _log.error("create_campaign failed: %s", e)
            return {"ok": False, "error": str(e)}

    def add_season(self, campaign_id: str, number: int, characters: list) -> dict:
        _log.info("add_season  campaign=%s  number=%d  chars=%s", campaign_id, number, characters)
        try:
            season = _add_season(campaign_id, number, characters)
            if season:
                return {"ok": True, "season": season}
            return {"ok": False, "error": "Campaign not found"}
        except Exception as e:
            _log.error("add_season failed: %s", e)
            return {"ok": False, "error": str(e)}

    def update_season(self, campaign_id: str, season_id: str, characters: list) -> dict:
        _log.info("update_season  campaign=%s  season=%s", campaign_id, season_id)
        try:
            ok = _update_season(campaign_id, season_id, characters)
            return {"ok": ok}
        except Exception as e:
            _log.error("update_season failed: %s", e)
            return {"ok": False, "error": str(e)}

    def update_campaign(self, campaign_id: str, name: str, beyond_url: str) -> dict:
        _log.info("update_campaign  id=%s  name=%r", campaign_id, name)
        try:
            ok = _update_campaign(campaign_id, name, beyond_url)
            return {"ok": ok}
        except Exception as e:
            _log.error("update_campaign failed: %s", e)
            return {"ok": False, "error": str(e)}

    def delete_campaign(self, campaign_id: str) -> dict:
        _log.info("delete_campaign  id=%s", campaign_id)
        try:
            ok = _delete_campaign(campaign_id)
            return {"ok": ok}
        except Exception as e:
            _log.error("delete_campaign failed: %s", e)
            return {"ok": False, "error": str(e)}

    # ── Glossary ──────────────────────────────────────────────────────────────

    def get_campaign_locations(self, campaign_id: str) -> dict:
        """Return all locations across all sessions for a campaign, deduplicated and ordered chronologically."""
        _log.info("get_campaign_locations  campaign=%s", campaign_id)
        try:
            sessions = get_sessions()
            campaign_sessions = [
                s for s in sessions
                if s.get("campaign_id") == campaign_id and s.get("locations_path")
            ]
            # Sort chronologically by date
            campaign_sessions.sort(key=lambda s: s.get("date", ""))

            # Deduplicate locations across sessions
            seen = {}  # type: Dict[str, dict]  # lowercase name -> merged location
            seen_order = []  # type: List[str]  # track insertion order

            for session_idx, sess in enumerate(campaign_sessions):
                lpath = sess.get("locations_path", "")
                if not lpath or not Path(lpath).exists():
                    continue
                try:
                    raw = Path(lpath).read_text(encoding="utf-8")
                    locs = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(locs, list):
                    continue

                session_date = sess.get("date", "")
                for loc in locs:
                    if not isinstance(loc, dict):
                        continue
                    name = (loc.get("name") or "").strip()
                    if not name:
                        continue
                    key = name.lower()

                    if key in seen:
                        # Merge: keep richest description, merge connections, update status
                        existing = seen[key]
                        new_desc = loc.get("description", "")
                        if new_desc and len(new_desc) > len(existing.get("description", "")):
                            existing["description"] = new_desc
                        # Merge connections (union, preserve order)
                        new_conns = loc.get("connections", [])
                        if new_conns:
                            existing_conns = existing.get("connections", [])
                            existing_lower = {c.lower() for c in existing_conns}
                            for c in new_conns:
                                if c.lower() not in existing_lower:
                                    existing_conns.append(c)
                                    existing_lower.add(c.lower())
                            existing["connections"] = existing_conns
                        # Keep latest relative_position
                        new_relpos = loc.get("relative_position", "")
                        if new_relpos:
                            existing["relative_position"] = new_relpos
                        # Mark visited if visited in any session
                        if loc.get("visited"):
                            existing["visited"] = True
                        existing["last_session_date"] = session_date
                        existing["session_count"] = existing.get("session_count", 1) + 1
                        # Keep latest non-empty region_type/location_type
                        if loc.get("region_type"):
                            existing["region_type"] = loc["region_type"]
                        if loc.get("location_type"):
                            existing["location_type"] = loc["location_type"]
                    else:
                        seen[key] = {
                            "name": name,
                            "description": loc.get("description", ""),
                            "connections": loc.get("connections", []),
                            "relative_position": loc.get("relative_position", ""),
                            "visit_order": loc.get("visit_order"),
                            "visited": bool(loc.get("visited")),
                            "first_session_date": session_date,
                            "last_session_date": session_date,
                            "session_count": 1,
                            "region_type": loc.get("region_type", ""),
                            "location_type": loc.get("location_type", ""),
                        }
                        seen_order.append(key)

            # Return in insertion order (chronological by first appearance, then visit_order)
            locations = [seen[k] for k in seen_order]
            return {"ok": True, "locations": locations, "session_count": len(campaign_sessions)}
        except Exception as e:
            _log.error("get_campaign_locations failed: %s", e)
            return {"ok": False, "locations": [], "error": str(e)}

    # ── Campaign Map ──────────────────────────────────────────────────────────

    def get_campaign_map(self, campaign_id: str) -> dict:
        """Return saved map layout, or null if not generated yet."""
        from maps import load_map
        data = load_map(campaign_id)
        return {"ok": True, "map": data}

    def generate_campaign_map(self, campaign_id: str) -> dict:
        """Generate an interactive map layout from campaign locations via LLM."""
        _log.info("generate_campaign_map  campaign=%s", campaign_id)
        try:
            # Get all deduplicated locations
            loc_result = self.get_campaign_locations(campaign_id)
            if not loc_result.get("ok"):
                return {"ok": False, "error": "Failed to load locations"}
            locations = loc_result.get("locations", [])
            if not locations:
                return {"ok": False, "error": "No locations found. Process sessions first."}

            # Build location descriptions for LLM
            loc_parts = []
            for loc in locations:
                part = '- **{}**'.format(loc["name"])
                if loc.get("description"):
                    part += ': {}'.format(loc["description"][:300])
                if loc.get("connections"):
                    part += '\n  Connections: {}'.format("; ".join(loc["connections"]))
                if loc.get("relative_position"):
                    part += '\n  Position: {}'.format(loc["relative_position"])
                if loc.get("visited"):
                    part += ' [VISITED]'
                if loc.get("region_type"):
                    part += '\n  Region: {}'.format(loc["region_type"])
                if loc.get("location_type"):
                    part += '\n  Type: {}'.format(loc["location_type"])
                loc_parts.append(part)

            locations_block = "\n".join(loc_parts)

            prompt = """You are a fantasy cartographer creating an interactive map layout from D&D campaign locations.

## Locations
{locations}

## Coordinate System
- Use a 1000x1000 grid (both x and y range 0-1000)
- North = lower Y values, South = higher Y values
- East = higher X values, West = lower X values
- Distance heuristics: "2 hours walk" ≈ 50 units, "half day" ≈ 150 units, "several days" ≈ 300+ units
- Keep connected locations near each other, respecting directional relationships from connection text

## Node Classification
For each location, assign:
- **region_type**: terrain around this location. One of: sea, coast, plains, forest, jungle, mountains, desert, swamp, underground, urban, ruins, arctic
- **location_type**: what kind of place it is. One of: city, town, village, inn, temple, ship, dock, farm, camp, cave, ruins, fortress, tower, clearing, bridge, crossroads, dungeon, shrine, market, manor, other

## Plane Detection
- Default plane is "Material Plane"
- Detect other planes from descriptions: Feywild, Shadowfell, Nine Hells, Abyss, Astral Sea, Ethereal Plane, Elemental planes, etc.
- Locations on other planes should have a different "plane" value
- Each plane has its own coordinate space (coordinates are independent per plane)

## Edge Classification
Create edges ONLY between locations that have explicit connection evidence. Classify travel_type:
- **walk**: road, path, trail, trek, hike (default)
- **ride**: horseback, carriage, cart
- **sail**: ship, boat, ferry, raft, sailing
- **fly**: griffon, carpet, broom, airship, dragon flight
- **teleport**: teleport, misty step, dimension door, magical transport
- **portal**: portal, gate, planar rift, interplanar travel
- **underground**: tunnel, underdark passage, mine, sewer
- **swim**: swimming, diving, underwater travel
- **climb**: cliff ascent, mountain climbing, rappelling
- **other**: any unclassified connection

## Rules
- ONLY include locations that have at least ONE connection to another location in the list
- Do NOT include isolated locations with no connections
- Extract edge labels from the connection text (e.g., "2 hours north" → label: "2 hours north")
- Ensure no two nodes overlap (minimum 60 units apart)
- Center the map: use the full 0-1000 range, don't cluster everything in one corner
- The FIRST location listed is the party's starting point — place it prominently (e.g., center-left of the map)

## Output
Return ONLY a JSON object with this structure:
{{
  "nodes": [
    {{"name": "Location Name", "x": 500, "y": 300, "plane": "Material Plane", "region_type": "coast", "location_type": "city"}}
  ],
  "edges": [
    {{"from": "Location A", "to": "Location B", "label": "2 hours north", "travel_type": "walk"}}
  ],
  "planes": ["Material Plane"]
}}

Return ONLY the JSON. No markdown fences, no explanation.""".format(locations=locations_block)

            from llm import call_llm
            provider, api_key, model = _get_llm_config()
            if not api_key:
                return {"ok": False, "error": "No LLM API key configured"}

            raw = call_llm(prompt, provider, api_key, model=model, max_tokens=8192)
            map_data = self._extract_json_object(raw)
            if not map_data:
                _log.error("generate_campaign_map: failed to parse LLM output")
                return {"ok": False, "error": "Failed to parse map layout from LLM"}

            # Validate structure
            if "nodes" not in map_data or "edges" not in map_data:
                return {"ok": False, "error": "Invalid map structure from LLM"}

            # Ensure planes list exists
            if "planes" not in map_data:
                planes = list(set(n.get("plane", "Material Plane") for n in map_data["nodes"]))
                map_data["planes"] = planes if planes else ["Material Plane"]

            # Add metadata
            map_data["generated_at"] = datetime.now().isoformat()

            # Save
            from maps import save_map
            save_map(campaign_id, map_data)

            _log.info("generate_campaign_map: %d nodes, %d edges, %d planes",
                       len(map_data["nodes"]), len(map_data["edges"]), len(map_data["planes"]))
            return {"ok": True, "map": map_data}
        except Exception as e:
            _log.error("generate_campaign_map failed: %s", e)
            return {"ok": False, "error": str(e)}

    def update_map_positions(self, campaign_id: str, positions: dict) -> dict:
        """Persist manual node position changes."""
        from maps import update_node_positions
        ok = update_node_positions(campaign_id, positions)
        return {"ok": ok}

    def get_location_events(self, campaign_id: str, location_name: str) -> dict:
        """Get per-session events for a specific location."""
        _log.info("get_location_events  campaign=%s  location=%s", campaign_id, location_name)
        try:
            sessions = get_sessions()
            campaign_sessions = [
                s for s in sessions
                if s.get("campaign_id") == campaign_id
            ]
            campaign_sessions.sort(key=lambda s: s.get("date", ""))

            loc_lower = location_name.lower().strip()
            result_sessions = []

            for sess in campaign_sessions:
                session_entry = {
                    "session_id": sess.get("id", ""),
                    "session_date": sess.get("date", ""),
                    "session_name": sess.get("display_name", sess.get("title", "")),
                    "description": "",
                    "npcs": [],
                    "events": [],
                }

                found = False

                # Check locations.json
                lpath = sess.get("locations_path", "")
                if lpath and Path(lpath).exists():
                    try:
                        locs = json.loads(Path(lpath).read_text(encoding="utf-8"))
                        for loc in locs:
                            if isinstance(loc, dict) and loc.get("name", "").lower().strip() == loc_lower:
                                session_entry["description"] = loc.get("description", "")
                                found = True
                                break
                    except Exception:
                        pass

                # Check npcs.json for NPCs at/near this location
                npath = sess.get("npcs_path", "")
                if npath and Path(npath).exists():
                    try:
                        npcs = json.loads(Path(npath).read_text(encoding="utf-8"))
                        for npc in npcs:
                            if isinstance(npc, dict):
                                # Check if NPC description mentions this location
                                desc = (npc.get("description", "") + " " + npc.get("actions", "")).lower()
                                if loc_lower in desc or location_name.lower() in desc:
                                    session_entry["npcs"].append(npc.get("name", "Unknown"))
                    except Exception:
                        pass

                # Check timeline.json for events mentioning location
                tpath = sess.get("timeline_path", "")
                if tpath and Path(tpath).exists():
                    try:
                        timeline = json.loads(Path(tpath).read_text(encoding="utf-8"))
                        for event in timeline:
                            if isinstance(event, dict):
                                event_text = event.get("description", "") or event.get("event", "")
                                if location_name.lower() in event_text.lower():
                                    session_entry["events"].append(event_text)
                    except Exception:
                        pass

                if found or session_entry["npcs"] or session_entry["events"]:
                    result_sessions.append(session_entry)

            return {"ok": True, "location_name": location_name, "sessions": result_sessions}
        except Exception as e:
            _log.error("get_location_events failed: %s", e)
            return {"ok": False, "error": str(e)}

    # ── Glossary ──────────────────────────────────────────────────────────────

    def get_campaign_glossary(self, campaign_id: str) -> dict:
        _log.debug("get_campaign_glossary  id=%s", campaign_id)
        # Filter out NPC and Location entries — they have dedicated views
        glossary = _get_glossary(campaign_id)
        return {
            term: info for term, info in glossary.items()
            if isinstance(info, dict) and info.get("category", "").upper() not in ("NPC", "LOCATION")
        }

    def update_campaign_glossary(self, campaign_id: str, glossary: dict) -> dict:
        _log.info("update_campaign_glossary  id=%s  terms=%d", campaign_id, len(glossary))
        try:
            ok = _update_glossary(campaign_id, glossary)
            return {"ok": ok}
        except Exception as e:
            _log.error("update_campaign_glossary failed: %s", e)
            return {"ok": False, "error": str(e)}

    def rebuild_campaign_glossary(self, campaign_id: str) -> dict:
        """Rebuild campaign glossary from all session glossary files.

        Routes NPC entries to character registry (with rich session data),
        routes Location entries to entity registry, and keeps only
        Faction/Item/Spell/Other in the glossary.
        """
        _log.info("rebuild_campaign_glossary  campaign=%s", campaign_id)
        try:
            sessions = get_sessions()
            campaign_sessions = [s for s in sessions if s.get("campaign_id") == campaign_id]
            # Sort chronologically
            campaign_sessions.sort(key=lambda s: s.get("date", ""))

            # Clear campaign glossary
            _update_glossary(campaign_id, {})

            total_terms = 0
            total_npcs = 0

            for s in campaign_sessions:
                session_id = s.get("id", "")
                session_date = s.get("date", "")

                # 1) Rebuild glossary from glossary files (excluding NPC/Location)
                gpath = s.get("glossary_path", "")
                if gpath and Path(gpath).exists():
                    try:
                        raw = Path(gpath).read_text(encoding="utf-8")
                        session_glossary = json.loads(raw)
                    except Exception as e:
                        _log.warning("rebuild: skipping glossary %s: %s", gpath, e)
                        session_glossary = None

                    if isinstance(session_glossary, dict):
                        _ENTRY_FIELDS = {"category", "definition", "description", "confidence", "reasoning"}
                        if not (session_glossary.keys() <= _ENTRY_FIELDS):
                            # Strip confidence/reasoning + filter out NPC/Location
                            clean = {}  # type: Dict[str, dict]
                            for term, info in session_glossary.items():
                                if term.startswith("_"):
                                    continue
                                if isinstance(info, dict):
                                    cat = info.get("category", "").upper()
                                    if cat in ("NPC", "LOCATION"):
                                        continue  # Routed to dedicated registries
                                    clean[term] = {k: v for k, v in info.items() if k not in ("confidence", "reasoning")}
                                else:
                                    clean[term] = {"category": "Other", "definition": str(info), "description": ""}
                            if clean:
                                added, updated = _smart_merge_glossary(campaign_id, clean)
                                total_terms += added

                # 2) Sync NPCs from session NPC data (rich source)
                npath = s.get("npcs_path", "")
                if npath and Path(npath).exists():
                    try:
                        raw = Path(npath).read_text(encoding="utf-8")
                        npcs_data = json.loads(raw)
                        if isinstance(npcs_data, list):
                            created = self._sync_npcs_from_session_data(
                                npcs_data, session_id, session_date, campaign_id,
                            )
                            total_npcs += created
                    except Exception as e:
                        _log.warning("rebuild: skipping npcs %s: %s", npath, e)

                # 3) Fallback: sync NPCs from glossary NPC entries (for sessions without npcs.json)
                if not npath or not Path(npath).exists():
                    if gpath and Path(gpath).exists():
                        try:
                            raw = Path(gpath).read_text(encoding="utf-8")
                            sg = json.loads(raw)
                            if isinstance(sg, dict):
                                npc_glossary = {t: i for t, i in sg.items()
                                                if isinstance(i, dict) and i.get("category", "").upper() == "NPC"}
                                if npc_glossary:
                                    npc_before = len([c for c in _get_characters() if c.get("is_npc")])
                                    self._sync_npcs_from_glossary(npc_glossary, campaign_id)
                                    npc_after = len([c for c in _get_characters() if c.get("is_npc")])
                                    total_npcs += npc_after - npc_before
                        except Exception:
                            pass

            final_glossary = _get_glossary(campaign_id)
            # Strip any remaining NPC/Location entries from the campaign glossary
            filtered = {t: i for t, i in final_glossary.items()
                        if isinstance(i, dict) and i.get("category", "").upper() not in ("NPC", "LOCATION")}
            if len(filtered) != len(final_glossary):
                _update_glossary(campaign_id, filtered)
                _log.info("rebuild: stripped %d NPC/Location entries from campaign glossary",
                          len(final_glossary) - len(filtered))

            _log.info("rebuild_campaign_glossary: done. %d glossary terms, %d NPCs created",
                       len(filtered), total_npcs)
            return {"ok": True, "terms": len(filtered), "npcs_created": total_npcs}
        except Exception as e:
            _log.error("rebuild_campaign_glossary failed: %s", e)
            return {"ok": False, "error": str(e)}

    # ── Session Library ───────────────────────────────────────────────────────

    def get_sessions(self) -> list:
        _log.debug("get_sessions called")
        sessions = get_sessions()
        # Resolve character_ids from campaign/season for each session
        campaigns_cache = {}  # type: Dict[str, list]
        for s in sessions:
            if not s.get("character_ids"):
                cid = s.get("campaign_id", "")
                sid = s.get("season_id", "")
                if cid and sid:
                    if cid not in campaigns_cache:
                        campaigns_cache[cid] = _get_campaigns()
                    for camp in campaigns_cache[cid]:
                        if camp["id"] == cid:
                            for season in camp.get("seasons", []):
                                if season["id"] == sid:
                                    s["character_ids"] = season.get("characters", [])
                                    break
                            break
            # Build name→ID lookup for hero tag linking
            char_map = {}
            if s.get("character_ids"):
                try:
                    chars = _get_characters_by_ids(s["character_ids"])
                    for ch in chars:
                        if ch.get("name"):
                            char_map[ch["name"]] = ch["id"]
                except Exception:
                    pass
            s["character_map"] = char_map
            s["files"] = {
                "audio": bool(s.get("audio_path") and Path(s["audio_path"]).exists()),
                "transcript": bool(s.get("txt_path") and Path(s["txt_path"]).exists()),
                "srt": bool(s.get("srt_path") and Path(s["srt_path"]).exists()),
                "summary": bool(s.get("summary_path") and Path(s["summary_path"]).exists()),
                "dm_notes": bool(s.get("dm_notes_path") and Path(s["dm_notes_path"]).exists()),
                "scenes": bool(s.get("scenes_path") and Path(s["scenes_path"]).exists()),
                "timeline": bool(s.get("timeline_path") and Path(s["timeline_path"]).exists()),
                "illustration": bool(s.get("illustration_path") and Path(s["illustration_path"]).exists()),
                "glossary": bool(s.get("glossary_path") and Path(s["glossary_path"]).exists()),
                "character_updates": bool(s.get("character_updates_path") and Path(s["character_updates_path"]).exists()),
                "leaderboard": bool(s.get("leaderboard_path") and Path(s["leaderboard_path"]).exists()),
                "locations": bool(s.get("locations_path") and Path(s["locations_path"]).exists()),
                "npcs": bool(s.get("npcs_path") and Path(s["npcs_path"]).exists()),
                "loot": bool(s.get("loot_path") and Path(s["loot_path"]).exists()),
                "missions": bool(s.get("missions_path") and Path(s["missions_path"]).exists()),
            }
        _log.debug("get_sessions → %d sessions", len(sessions))
        return sessions

    def open_path(self, path: str) -> dict:
        _log.info("open_path → %s", path)
        try:
            if path.startswith("http://") or path.startswith("https://"):
                subprocess.Popen(["open", path])
                return {"ok": True}
            p = Path(path)
            target = str(p.parent) if p.is_file() else str(p)
            subprocess.Popen(["open", target])
            return {"ok": True}
        except Exception as e:
            _log.error("open_path failed: %s", e)
            return {"ok": False, "error": str(e)}

    def rename_session(self, session_id: str, display_name: str) -> dict:
        _log.info("rename_session  id=%s  name=%r", session_id, display_name)
        try:
            update_session(session_id, display_name=display_name)
            return {"ok": True}
        except Exception as e:
            _log.error("rename_session failed: %s", e)
            return {"ok": False, "error": str(e)}

    def update_session_date(self, session_id: str, new_date: str) -> dict:
        """new_date is a YYYY-MM-DD string."""
        _log.info("update_session_date  id=%s  date=%s", session_id, new_date)
        try:
            from datetime import datetime
            iso = datetime.strptime(new_date, "%Y-%m-%d").isoformat()
            update_session(session_id, date=iso)
            return {"ok": True}
        except Exception as e:
            _log.error("update_session_date failed: %s", e)
            return {"ok": False, "error": str(e)}

    def generate_session_title(self, session_id: str) -> dict:
        """Use LLM to generate a short, evocative title for a session based on its transcript."""
        _log.info("generate_session_title  id=%s", session_id)
        try:
            sessions = get_sessions()
            session = None
            for s in sessions:
                if s["id"] == session_id:
                    session = s
                    break
            if not session:
                return {"ok": False, "error": "Session not found"}

            txt_path = session.get("txt_path")
            if not txt_path or not Path(txt_path).exists():
                return {"ok": False, "error": "No transcript available"}

            transcript = Path(txt_path).read_text(encoding="utf-8")
            # Truncate to 5k from start + 5k from end
            if len(transcript) > 10000:
                transcript = transcript[:5000] + "\n\n[...]\n\n" + transcript[-5000:]

            from llm import call_llm
            provider, api_key, model = _get_llm_config()
            if not api_key:
                return {"ok": False, "error": "No LLM API key configured"}

            prompt = (
                "You are a master D&D storyteller naming a chapter of an epic campaign.\n"
                "Based on this session transcript, create an evocative, dramatic title (3-7 words) "
                "that captures the SPIRIT and DRAMA — like a chapter in a fantasy novel.\n\n"
                "Good examples: 'The Serpent's Gambit', 'Shadows Over Thundertop', "
                "'A Crown of Thorns', 'The Price of Mercy', 'Into the Maw'\n"
                "Bad examples: 'Session 5', 'Fight in Cave', 'Meeting NPCs', 'Travel to Town'\n\n"
                "Return ONLY the title. No quotes, no explanation, no numbering.\n\n"
                "## Session Transcript\n{}".format(transcript)
            )
            title = call_llm(prompt, provider, api_key, model=model, max_tokens=64)
            title = title.strip().strip('"').strip("'").strip()
            update_session(session_id, display_name=title)
            return {"ok": True, "title": title}
        except Exception as e:
            _log.error("generate_session_title failed: %s", e)
            return {"ok": False, "error": str(e)}

    def get_season_digest(self, campaign_id, season_id):
        # type: (str, str) -> dict
        """Return existing season digest or {ok: false} if none exists."""
        _log.info("get_season_digest  campaign=%s season=%s", campaign_id, season_id)
        try:
            digest_dir = Path.home() / ".config" / "dnd-whisperx" / "digests"
            digest_path = digest_dir / "{}_{}.json".format(campaign_id, season_id)
            if not digest_path.exists():
                return {"ok": False}
            import json as _json
            digest = _json.loads(digest_path.read_text(encoding="utf-8"))
            return {"ok": True, "digest": digest}
        except Exception as e:
            _log.error("get_season_digest failed: %s", e)
            return {"ok": False, "error": str(e)}

    def generate_season_digest(self, campaign_id, season_id):
        # type: (str, str) -> dict
        """Generate a season digest by summarizing all sessions for a campaign+season."""
        _log.info("generate_season_digest  campaign=%s season=%s", campaign_id, season_id)
        try:
            from campaigns import get_campaigns
            from sessions import get_sessions
            import json as _json

            # Find the campaign and season
            campaigns = get_campaigns()
            campaign = None
            season = None
            for c in campaigns:
                if c["id"] == campaign_id:
                    campaign = c
                    for s in c.get("seasons", []):
                        if s["id"] == season_id:
                            season = s
                            break
                    break

            if not campaign:
                return {"ok": False, "error": "Campaign not found"}
            if not season:
                return {"ok": False, "error": "Season not found"}

            # Find all sessions for this campaign + season
            all_sessions = get_sessions()
            season_sessions = [
                s for s in all_sessions
                if s.get("campaign_id") == campaign_id
                and s.get("season_id") == season_id
            ]
            season_sessions.sort(key=lambda s: s.get("date", ""))

            if not season_sessions:
                return {"ok": False, "error": "No sessions found for this season"}

            # Build context from session summaries or transcripts
            session_texts = []
            for sess in season_sessions:
                date = sess.get("date", "unknown date")
                display = sess.get("display_name", "")
                header = "### Session: {} ({})".format(display or date, date)

                summary_path = sess.get("summary_path")
                txt_path = sess.get("txt_path")

                text = ""
                if summary_path and Path(summary_path).exists():
                    text = Path(summary_path).read_text(encoding="utf-8")
                elif txt_path and Path(txt_path).exists():
                    raw = Path(txt_path).read_text(encoding="utf-8")
                    text = raw[:3000] if len(raw) > 3000 else raw

                if text:
                    session_texts.append("{}\n{}".format(header, text))

            if not session_texts:
                return {"ok": False, "error": "No session content available to generate digest"}

            combined = "\n\n---\n\n".join(session_texts)
            # Truncate if too long
            if len(combined) > 40000:
                combined = combined[:40000] + "\n\n[...truncated...]"

            from llm import call_llm
            provider, api_key, model = _get_llm_config()
            if not api_key:
                return {"ok": False, "error": "No LLM API key configured"}

            prompt = (
                "You are a master chronicler writing the definitive account of a D&D campaign season.\n"
                "Campaign: {campaign}\n"
                "Season: {season_num}\n\n"
                "Below are individual session summaries in chronological order.\n\n"
                "{sessions}\n\n"
                "Generate a JSON object with this exact structure:\n"
                '{{\n'
                '  "title": "Dramatic 3-7 word season title (like a fantasy novel chapter)",\n'
                '  "narrative": "3-5 paragraph cohesive narrative weaving all sessions into an epic arc (use markdown formatting)",\n'
                '  "character_arcs": [\n'
                '    {{"name": "Character Name", "arc": "2-3 sentence arc description"}}\n'
                '  ],\n'
                '  "unresolved": ["Thread 1 still open", "Mystery still unsolved"]\n'
                '}}\n\n'
                "Return ONLY valid JSON. No markdown fences, no explanation."
            ).format(
                campaign=campaign.get("name", "Unknown"),
                season_num=season.get("number", "?"),
                sessions=combined,
            )

            raw = call_llm(prompt, provider, api_key, model=model, max_tokens=4000)

            # Parse the JSON response
            raw = raw.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            digest = _json.loads(raw)

            # ── Generate season timeline ──────────────────────────
            try:
                timeline_prompt = (
                    "You are a D&D campaign chronicler. Given session summaries from Season {season_num} "
                    "of campaign \"{campaign}\", extract 12-25 KEY events that form the season's narrative arc.\n\n"
                    "{sessions}\n\n"
                    "Each event must reference the session it occurred in via the 'time' field "
                    "(use the session display name or date shown in the ### headers above).\n"
                    "There should be multiple events per session — pick the most important moments.\n"
                    "Generate a JSON array:\n"
                    "[\n"
                    "  {{\n"
                    '    "time": "Session display name or date",\n'
                    '    "title": "Short event title (5-8 words)",\n'
                    '    "summary": "What happened (1-2 sentences)",\n'
                    '    "details": "Deeper context, consequences, who was involved",\n'
                    '    "importance": "high|medium|low",\n'
                    '    "type": "combat|discovery|dialogue|travel|magic|death|treasure|npc|boss|betrayal|victory"\n'
                    "  }}\n"
                    "]\n\n"
                    "Return ONLY valid JSON. No markdown fences."
                ).format(
                    campaign=campaign.get("name", "Unknown"),
                    season_num=season.get("number", "?"),
                    sessions=combined,
                )

                timeline_raw = call_llm(timeline_prompt, provider, api_key, model=model, max_tokens=4000)
                timeline_raw = timeline_raw.strip()
                if timeline_raw.startswith("```"):
                    timeline_raw = timeline_raw.split("\n", 1)[1] if "\n" in timeline_raw else timeline_raw[3:]
                    if timeline_raw.endswith("```"):
                        timeline_raw = timeline_raw[:-3]
                    timeline_raw = timeline_raw.strip()

                timeline = _json.loads(timeline_raw)
                if isinstance(timeline, list):
                    digest["timeline"] = timeline
                    _log.info("Season timeline generated: %d events", len(timeline))
                else:
                    _log.warning("Timeline LLM returned non-array, skipping")
            except Exception as te:
                _log.warning("Season timeline generation failed (non-fatal): %s", te)
                # Digest still saves without timeline

            # Save
            digest_dir = Path.home() / ".config" / "dnd-whisperx" / "digests"
            digest_dir.mkdir(parents=True, exist_ok=True)
            digest_path = digest_dir / "{}_{}.json".format(campaign_id, season_id)
            digest_path.write_text(_json.dumps(digest, indent=2, ensure_ascii=False), encoding="utf-8")

            _log.info("Season digest generated and saved → %s", digest_path)
            return {"ok": True, "digest": digest}

        except Exception as e:
            _log.error("generate_season_digest failed: %s", e)
            return {"ok": False, "error": str(e)}

    def download_file(self, path: str) -> dict:
        """Copy a file to ~/Downloads/, adding a timestamp suffix if name already exists."""
        _log.info("download_file  path=%s", path)
        try:
            import shutil as _shutil
            src = Path(path)
            if not src.exists():
                return {"ok": False, "error": "File not found: {}".format(path)}

            downloads = Path.home() / "Downloads"
            downloads.mkdir(parents=True, exist_ok=True)
            dest = downloads / src.name
            if dest.exists():
                stem = src.stem
                suffix = src.suffix
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                dest = downloads / "{}_{}{}".format(stem, ts, suffix)
            _shutil.copy2(str(src), str(dest))
            _log.info("File downloaded → %s", dest)
            return {"ok": True, "dest": str(dest)}
        except Exception as e:
            _log.error("download_file failed: %s", e)
            return {"ok": False, "error": str(e)}

    def download_session_zip(self, session_id: str) -> dict:
        """Zip all files in a session's output directory to ~/Downloads/."""
        _log.info("download_session_zip  id=%s", session_id)
        try:
            import zipfile
            sessions = get_sessions()
            session = None
            for s in sessions:
                if s["id"] == session_id:
                    session = s
                    break
            if not session:
                return {"ok": False, "error": "Session not found"}

            output_dir = session.get("output_dir")
            if not output_dir or not Path(output_dir).exists():
                return {"ok": False, "error": "Session output directory not found"}

            out_path = Path(output_dir)
            display_name = session.get("display_name", "") or session.get("campaign_name", "Session")
            safe_name = "".join(c if c.isalnum() or c in " -_" else "_" for c in display_name).strip()
            safe_name = safe_name or "Session"

            downloads = Path.home() / "Downloads"
            downloads.mkdir(parents=True, exist_ok=True)
            zip_name = "Chronicles_{}".format(safe_name)
            zip_dest = downloads / "{}.zip".format(zip_name)
            if zip_dest.exists():
                from datetime import datetime
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                zip_dest = downloads / "{}_{}.zip".format(zip_name, ts)

            with zipfile.ZipFile(str(zip_dest), "w", zipfile.ZIP_DEFLATED) as zf:
                for f in out_path.iterdir():
                    if f.is_file():
                        zf.write(str(f), f.name)

            _log.info("Session zip downloaded → %s", zip_dest)
            return {"ok": True, "dest": str(zip_dest)}
        except Exception as e:
            _log.error("download_session_zip failed: %s", e)
            return {"ok": False, "error": str(e)}

    def delete_session_folder(self, session_id: str) -> dict:
        """Delete a session's output folder from disk and remove it from the registry.

        Safety: if another session shares the same output_dir, only the
        registry entry is removed — the folder is kept on disk.
        """
        _log.info("delete_session_folder  id=%s", session_id)
        try:
            output_dir = _delete_session(session_id)
            if output_dir:
                # Check whether any remaining session still uses this directory
                others_use_dir = any(
                    s.get("output_dir") == output_dir
                    for s in get_sessions()
                )
                p = Path(output_dir)
                if others_use_dir:
                    _log.info(
                        "Skipping folder delete — another session shares %s", p
                    )
                elif p.exists():
                    shutil.rmtree(p)
                    _log.info("Deleted session folder: %s", p)
            return {"ok": True}
        except Exception as e:
            _log.error("delete_session_folder failed: %s", e)
            return {"ok": False, "error": str(e)}

    def read_file(self, path: str) -> dict:
        """Read and return the text content of a file."""
        try:
            content = Path(path).read_text(encoding="utf-8")
            return {"ok": True, "content": content}
        except Exception as e:
            return {"ok": False, "content": "", "error": str(e)}

    # ── Characters ────────────────────────────────────────────────────────────

    def get_characters(self) -> list:
        _log.debug("get_characters called")
        return _get_characters()

    def get_character(self, char_id: str) -> dict:
        _log.debug("get_character  id=%s", char_id)
        c = _get_character(char_id)
        return {"ok": True, "character": c} if c else {"ok": False, "error": "Not found"}

    def get_characters_by_ids(self, char_ids: list) -> list:
        return _get_characters_by_ids(char_ids)

    def get_character_campaigns(self, char_id: str) -> list:
        """Return campaigns/seasons that reference a character."""
        from campaigns import get_campaigns_for_character
        return get_campaigns_for_character(char_id)

    def create_character(
        self,
        name: str,
        race: str = "",
        class_name: str = "",
        subclass: str = "",
        level: int = 1,
        specialty: str = "",
        beyond_url: str = "",
        portrait_path: str = "",
    ) -> dict:
        _log.info("create_character  name=%s", name)
        try:
            char = _create_character(
                name=name,
                race=race,
                class_name=class_name,
                subclass=subclass,
                level=level,
                specialty=specialty,
                beyond_url=beyond_url,
                portrait_path=portrait_path,
            )
            # Auto-sync from D&D Beyond if URL provided
            if beyond_url:
                self._sync_beyond(char["id"], beyond_url)
            return {"ok": True, "character": char}
        except Exception as e:
            _log.error("create_character failed: %s", e)
            return {"ok": False, "error": str(e)}

    def update_character(self, char_id: str, fields: dict) -> dict:
        _log.info("update_character  id=%s  fields=%s", char_id, list(fields.keys()))
        try:
            # If portrait_path is being set, also add to portrait gallery
            if "portrait_path" in fields and fields["portrait_path"]:
                from characters import add_portrait
                add_portrait(char_id, fields["portrait_path"], set_primary=True)
            c = _update_character(char_id, **fields)
            if c:
                return {"ok": True, "character": c}
            return {"ok": False, "error": "Not found"}
        except Exception as e:
            _log.error("update_character failed: %s", e)
            return {"ok": False, "error": str(e)}

    def delete_character(self, char_id: str) -> dict:
        _log.info("delete_character  id=%s", char_id)
        try:
            ok = _delete_character(char_id)
            return {"ok": ok}
        except Exception as e:
            _log.error("delete_character failed: %s", e)
            return {"ok": False, "error": str(e)}

    def sync_beyond_character(self, char_id: str) -> dict:
        """Fetch latest data from D&D Beyond for a character."""
        _log.info("sync_beyond_character  id=%s", char_id)
        try:
            char = _get_character(char_id)
            if not char:
                return {"ok": False, "error": "Character not found"}
            beyond_url = char.get("beyond_url", "")
            if not beyond_url:
                return {"ok": False, "error": "No D&D Beyond URL set"}
            updated = self._sync_beyond(char_id, beyond_url)
            if updated:
                return {"ok": True, "character": updated}
            return {"ok": False, "error": "Failed to fetch from D&D Beyond"}
        except ValueError as e:
            _log.warning("sync_beyond_character: %s", e)
            return {"ok": False, "error": str(e)}
        except Exception as e:
            _log.error("sync_beyond_character failed: %s", e)
            return {"ok": False, "error": str(e)}

    def _sync_beyond(self, char_id: str, beyond_url: str) -> Optional[dict]:
        """Internal: fetch D&D Beyond data and update character."""
        from beyond import download_avatar, fetch_beyond_character
        from characters import _char_dir
        from datetime import datetime

        data = fetch_beyond_character(beyond_url)
        if not data:
            return None

        # Download avatar if available
        avatar_path = ""
        avatar_url = data.pop("avatar_url", "")
        if avatar_url:
            avatar_dest = str(_char_dir(char_id) / "avatar.jpg")
            if download_avatar(avatar_url, avatar_dest):
                avatar_path = avatar_dest

        synced_at = datetime.now().isoformat()
        return _set_beyond_data(char_id, data, avatar_path=avatar_path, synced_at=synced_at)

    def pick_character_realistic_portrait(self) -> Optional[str]:
        """Pick a realistic portrait image for video generation reference."""
        _log.debug("pick_character_realistic_portrait called")
        picked = self._osascript_pick(
            "Select a realistic character portrait for video generation",
            ["png", "jpg", "jpeg", "gif", "webp", "bmp", "tiff"],
        )
        _log.info("pick_character_realistic_portrait → %s", picked or "(cancelled)")
        return picked

    @staticmethod
    def _race_physical_description(race):
        # type: (str) -> str
        """Return physical appearance hints for D&D races to guide image generation."""
        r = race.lower().strip()
        race_map = {
            "half-orc": "with greenish-grey skin, prominent lower canine tusks, a heavy brow, and a muscular, broad build",
            "half orc": "with greenish-grey skin, prominent lower canine tusks, a heavy brow, and a muscular, broad build",
            "orc": "with green skin, large protruding tusks, a heavy brow ridge, and a massive muscular build",
            "dwarf": "short and stocky with a thick beard, broad shoulders, and a sturdy, compact build (about 4'5\" tall)",
            "hill dwarf": "short and stocky with a thick beard, broad shoulders, ruddy cheeks, and a sturdy, compact build (about 4'5\" tall)",
            "mountain dwarf": "short and stocky with a thick braided beard, broad muscular shoulders, and a powerful compact build (about 4'8\" tall)",
            "elf": "with elegant pointed ears, angular cheekbones, slender build, and an ageless ethereal beauty",
            "high elf": "with elegant pointed ears, angular cheekbones, tall slender build, and regal bearing with an ageless ethereal beauty",
            "wood elf": "with pointed ears, coppery or olive skin, lean athletic build, and alert watchful eyes",
            "dark elf": "with dark purple-black skin, white or silver hair, pointed ears, and striking pale eyes",
            "drow": "with dark purple-black skin, white or silver hair, pointed ears, and striking pale eyes",
            "halfling": "very short and small (about 3' tall), with a round friendly face, curly hair, and slightly pointed ears",
            "lightfoot halfling": "very short and small (about 3' tall), with a round friendly face, curly hair, and slightly pointed ears",
            "stout halfling": "very short and small (about 3'2\" tall), with a round sturdy face, curly hair, and slightly pointed ears",
            "gnome": "very small (about 3'4\" tall) with a large head relative to body, prominent nose, bright curious eyes, and pointed ears",
            "rock gnome": "very small (about 3'4\" tall) with a large head, prominent nose, bright curious eyes, and pointed ears",
            "tiefling": "with small curved horns on the forehead, reddish or purple-tinted skin, solid-colored eyes (no whites), and a thin tail",
            "dragonborn": "with a draconic reptilian face, scales covering the skin, a broad snout, and a tall powerful muscular build",
            "half-elf": "with slightly pointed ears, human-like build but with elven angular features and an ageless quality",
            "half elf": "with slightly pointed ears, human-like build but with elven angular features and an ageless quality",
            "goliath": "extremely tall (7-8 feet) with grey stone-like skin, bald head with dark markings/tattoos, and a massive muscular build",
            "tabaxi": "with feline features — cat-like face with whiskers, fur-covered skin, slit-pupil eyes, and a lean agile build",
            "kenku": "with a raven-like bird head, black feathers covering the body, a beak, and dark beady eyes",
            "firbolg": "very tall (7-8 feet) with a large nose, cow-like ears, and a gentle giant appearance with slightly bluish skin",
            "aasimar": "with a subtle golden or silver glow to the skin, luminous eyes, and an otherworldly angelic beauty",
            "genasi": "with elemental features — skin that hints at their element (fire: reddish with ember glow, water: blue-green, earth: grey-brown, air: pale blue)",
            "changeling": "with pale almost white skin, colorless eyes, and soft undefined features",
            "warforged": "a living construct with a body made of wood, metal, and stone plates, with glowing eyes set in a mechanical face",
            "tortle": "with a turtle-like appearance — a hard shell on the back, a reptilian face with a beak-like mouth, and green-brown scaly skin",
            "kobold": "very small (about 2'5\" tall) with a reptilian dog-like face, scales, a long tail, and small horns",
            "bugbear": "tall and hairy with a goblinoid face, long arms, and a powerful hulking build covered in coarse fur",
        }
        for key, desc in race_map.items():
            if key in r:
                return desc
        return ""

    def _build_character_prompt_details(self, char):
        # type: (dict) -> tuple
        """Build subject, features, and extra context strings from character data.

        Returns (subject_str, features_str, extra_context_str).
        """
        beyond = char.get("beyond_data", {})
        appearance = beyond.get("appearance", {})

        # Subject line
        subject = []
        subject.append(char.get("name", "a character"))
        race = char.get("race", "")
        if race:
            subject.append(race)
        if char.get("class_name"):
            subject.append(char["class_name"])
        if appearance.get("gender"):
            subject.append(appearance["gender"])
        if appearance.get("age"):
            subject.append("{} years old".format(appearance["age"]))

        # Racial physical description — placed FIRST and prominently
        race_desc = self._race_physical_description(race) if race else ""

        # Physical features from D&D Beyond
        features = []
        if race_desc:
            features.append(race_desc)
        if appearance.get("skin"):
            features.append("{} skin".format(appearance["skin"]))
        if appearance.get("hair"):
            features.append("{} hair".format(appearance["hair"]))
        if appearance.get("eyes"):
            features.append("{} eyes".format(appearance["eyes"]))

        # Extra context from backstory / personality
        extra = []
        if beyond.get("background"):
            extra.append("Background: {}".format(beyond["background"]))
        if beyond.get("personality_traits"):
            pt = beyond["personality_traits"]
            if len(pt) > 200:
                pt = pt[:200] + "..."
            extra.append("Personality: {}".format(pt))
        if beyond.get("alignment"):
            extra.append("Alignment: {}".format(beyond["alignment"]))

        subject_str = " ".join(subject)
        # Put race description FIRST in features for maximum visibility to image model
        features_str = (", " + ", ".join(features)) if features else ""
        # For non-human races, add emphasis to ensure image model captures key features
        if race_desc and race.lower().strip() not in ("human", ""):
            features_str = ". IMPORTANT — this is a {} character {}{}".format(
                race, race_desc, (", " + ", ".join(features[1:])) if len(features) > 1 else ""
            )
        extra_str = (" Character context: " + ". ".join(extra) + ".") if extra else ""

        return subject_str, features_str, extra_str

    def generate_character_portrait(self, char_id: str) -> dict:
        """Generate a realistic portrait using Imagen from character description."""
        _log.info("generate_character_portrait  id=%s", char_id)
        try:
            char = _get_character(char_id)
            if not char:
                return {"ok": False, "error": "Character not found"}

            gemini_key = get_gemini_token()
            if not gemini_key:
                return {"ok": False, "error": "Gemini API key not set"}

            subject_str, features_str, extra_str = self._build_character_prompt_details(char)

            prompt = (
                "Close-up headshot portrait photograph taken with a Canon EOS R5, 85mm f/1.4 lens. "
                "Subject: {subject}{features_str}. "
                "{extra_str}"
                "Shot on real camera with natural studio lighting, soft bokeh background. "
                "Photorealistic, real human skin texture with pores and subtle imperfections, "
                "real eyes with catchlights, natural hair strands. "
                "Professional actor headshot quality, shallow depth of field, neutral dark background. "
                "NOT a painting, NOT a drawing, NOT digital art, NOT fantasy illustration, NOT anime, NOT CGI. "
                "Real photograph of a real person, indistinguishable from a DSLR photo."
            ).format(
                subject=subject_str,
                features_str=features_str,
                extra_str=extra_str,
            )

            _log.info("Portrait prompt for %s: %s", char.get("name", char_id), prompt)

            import time
            from characters import _char_dir, add_portrait
            from image_gen import generate_portrait
            ts = int(time.time())
            out_path = str(_char_dir(char_id) / "portrait_{}.png".format(ts))

            ok = generate_portrait(prompt, gemini_key, out_path)
            if ok:
                updated = add_portrait(char_id, out_path, set_primary=True)
                if updated:
                    return {"ok": True, "portrait_path": out_path, "character": updated}
                return {"ok": True, "portrait_path": out_path}
            return {"ok": False, "error": "Image generation failed"}
        except Exception as e:
            _log.error("generate_character_portrait failed: %s", e)
            return {"ok": False, "error": str(e)}

    def set_primary_portrait(self, char_id, portrait_path):
        # type: (str, str) -> dict
        """Set a portrait as the primary for a character."""
        from characters import set_primary_portrait as _set_primary
        result = _set_primary(char_id, portrait_path)
        if result:
            return {"ok": True, "character": result}
        return {"ok": False, "error": "Portrait not found"}

    def delete_portrait(self, char_id, portrait_path):
        # type: (str, str) -> dict
        """Delete a portrait from a character's gallery."""
        from characters import delete_portrait as _delete
        result = _delete(char_id, portrait_path)
        if result:
            return {"ok": True, "character": result}
        return {"ok": False, "error": "Character or portrait not found"}

    # ── Full-body generation ──────────────────────────────────────────────

    def generate_character_fullbody(self, char_id):
        # type: (str) -> dict
        """Generate a photorealistic full-body image for a character."""
        _log.info("generate_character_fullbody  id=%s", char_id)
        try:
            char = _get_character(char_id)
            if not char:
                return {"ok": False, "error": "Character not found"}

            gemini_key = get_gemini_token()
            if not gemini_key:
                return {"ok": False, "error": "Gemini API key not set"}

            beyond = char.get("beyond_data", {})
            appearance = beyond.get("appearance", {})

            # Equipment from D&D Beyond
            equipment = []
            for item in beyond.get("equipment", [])[:8]:
                name = item if isinstance(item, str) else item.get("name", "")
                if name:
                    equipment.append(name)

            # Height from appearance
            height_str = ""
            if appearance.get("height"):
                height_str = ", {} tall".format(appearance["height"])

            # Use NPC description if it's an NPC
            npc_desc = char.get("npc_description", "")
            if char.get("is_npc") and npc_desc:
                prompt = (
                    "Full-body standing photograph taken with a Canon EOS R5, 50mm f/1.8 lens. "
                    "Subject: {desc}. "
                    "Full body visible from head to toe, natural studio lighting, neutral background. "
                    "Photorealistic, real human, professional full-body actor shot. "
                    "NOT a painting, NOT a drawing, NOT digital art, NOT fantasy illustration, NOT anime, NOT CGI. "
                    "Real photograph of a real person, indistinguishable from a DSLR photo."
                ).format(desc=npc_desc)
            else:
                subject_str, features_str, extra_str = self._build_character_prompt_details(char)
                equipment_str = (", wearing/carrying " + ", ".join(equipment)) if equipment else ""
                prompt = (
                    "Full-body standing photograph taken with a Canon EOS R5, 50mm f/1.8 lens. "
                    "Subject: {subject}{features_str}{height}{equipment_str}. "
                    "{extra_str}"
                    "Full body visible from head to toe, natural studio lighting, neutral background. "
                    "Photorealistic, real human, professional full-body actor shot. "
                    "NOT a painting, NOT a drawing, NOT digital art, NOT fantasy illustration, NOT anime, NOT CGI. "
                    "Real photograph of a real person, indistinguishable from a DSLR photo."
                ).format(
                    subject=subject_str,
                    features_str=features_str,
                    height=height_str,
                    equipment_str=equipment_str,
                    extra_str=extra_str,
                )

            _log.info("Fullbody prompt for %s: %s", char.get("name", char_id), prompt)

            import time
            from characters import _char_dir, add_fullbody
            from image_gen import generate_fullbody
            ts = int(time.time())
            out_path = str(_char_dir(char_id) / "fullbody_{}.png".format(ts))

            ok = generate_fullbody(prompt, gemini_key, out_path)
            if ok:
                updated = add_fullbody(char_id, out_path, set_primary=True)
                if updated:
                    return {"ok": True, "fullbody_path": out_path, "character": updated}
                return {"ok": True, "fullbody_path": out_path}
            return {"ok": False, "error": "Image generation failed"}
        except Exception as e:
            _log.error("generate_character_fullbody failed: %s", e)
            return {"ok": False, "error": str(e)}

    def set_primary_fullbody(self, char_id, fullbody_path):
        # type: (str, str) -> dict
        """Set a full-body image as the primary for a character."""
        from characters import set_primary_fullbody as _set_primary
        result = _set_primary(char_id, fullbody_path)
        if result:
            return {"ok": True, "character": result}
        return {"ok": False, "error": "Fullbody not found"}

    def delete_fullbody(self, char_id, fullbody_path):
        # type: (str, str) -> dict
        """Delete a full-body image from a character's gallery."""
        from characters import delete_fullbody as _delete
        result = _delete(char_id, fullbody_path)
        if result:
            return {"ok": True, "character": result}
        return {"ok": False, "error": "Character or fullbody not found"}

    # ── NPC management ────────────────────────────────────────────────────

    def get_npcs(self, campaign_id=""):
        # type: (str) -> list
        """Return NPC characters, optionally filtered by campaign."""
        from characters import get_npcs as _get_npcs
        return _get_npcs(campaign_id if campaign_id else None)

    def generate_npc_portrait(self, char_id):
        # type: (str) -> dict
        """Generate a photorealistic portrait for an NPC using its description."""
        _log.info("generate_npc_portrait  id=%s", char_id)
        try:
            char = _get_character(char_id)
            if not char:
                return {"ok": False, "error": "Character not found"}

            gemini_key = get_gemini_token()
            if not gemini_key:
                return {"ok": False, "error": "Gemini API key not set"}

            npc_desc = char.get("npc_description", "")
            if not npc_desc:
                return {"ok": False, "error": "NPC has no description yet — process more sessions first"}

            prompt = (
                "Close-up headshot portrait photograph taken with a Canon EOS R5, 85mm f/1.4 lens. "
                "Subject: {desc}. "
                "Shot on real camera with natural studio lighting, soft bokeh background. "
                "Photorealistic, real human skin texture with pores and subtle imperfections, "
                "real eyes with catchlights, natural hair strands. "
                "Professional actor headshot quality, shallow depth of field, neutral dark background. "
                "NOT a painting, NOT a drawing, NOT digital art, NOT fantasy illustration, NOT anime, NOT CGI. "
                "Real photograph of a real person, indistinguishable from a DSLR photo."
            ).format(desc=npc_desc)

            import time
            from characters import _char_dir, add_portrait
            from image_gen import generate_portrait
            ts = int(time.time())
            out_path = str(_char_dir(char_id) / "portrait_{}.png".format(ts))

            ok = generate_portrait(prompt, gemini_key, out_path)
            if ok:
                updated = add_portrait(char_id, out_path, set_primary=True)
                if updated:
                    return {"ok": True, "portrait_path": out_path, "character": updated}
                return {"ok": True, "portrait_path": out_path}
            return {"ok": False, "error": "Image generation failed"}
        except Exception as e:
            _log.error("generate_npc_portrait failed: %s", e)
            return {"ok": False, "error": str(e)}

    def generate_npc_fullbody(self, char_id):
        # type: (str) -> dict
        """Generate a full-body image for an NPC using its description."""
        _log.info("generate_npc_fullbody  id=%s", char_id)
        try:
            char = _get_character(char_id)
            if not char:
                return {"ok": False, "error": "Character not found"}

            gemini_key = get_gemini_token()
            if not gemini_key:
                return {"ok": False, "error": "Gemini API key not set"}

            npc_desc = char.get("npc_description", "")
            if not npc_desc:
                return {"ok": False, "error": "NPC has no description yet — process more sessions first"}

            prompt = (
                "Full-body standing photograph taken with a Canon EOS R5, 50mm f/1.8 lens. "
                "Subject: {desc}. "
                "Full body visible from head to toe, natural studio lighting, neutral background. "
                "Photorealistic, real human, professional full-body actor shot. "
                "NOT a painting, NOT a drawing, NOT digital art, NOT fantasy illustration, NOT anime, NOT CGI. "
                "Real photograph of a real person, indistinguishable from a DSLR photo."
            ).format(desc=npc_desc)

            import time
            from characters import _char_dir, add_fullbody
            from image_gen import generate_fullbody
            ts = int(time.time())
            out_path = str(_char_dir(char_id) / "fullbody_{}.png".format(ts))

            ok = generate_fullbody(prompt, gemini_key, out_path)
            if ok:
                updated = add_fullbody(char_id, out_path, set_primary=True)
                if updated:
                    return {"ok": True, "fullbody_path": out_path, "character": updated}
                return {"ok": True, "fullbody_path": out_path}
            return {"ok": False, "error": "Image generation failed"}
        except Exception as e:
            _log.error("generate_npc_fullbody failed: %s", e)
            return {"ok": False, "error": str(e)}

    def update_npc_description(self, char_id, description):
        # type: (str, str) -> dict
        """Update an NPC's description."""
        from characters import update_npc_description as _update
        result = _update(char_id, description)
        if result:
            return {"ok": True, "character": result}
        return {"ok": False, "error": "NPC not found"}

    def update_character_history_manual(
        self, char_id: str, session_id: str, manual_text: str
    ) -> dict:
        """Update manual text on a character's history entry for a session."""
        try:
            ok = _update_history_manual_text(char_id, session_id, manual_text)
            return {"ok": ok}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def update_character_history_auto(
        self, char_id, session_id, auto_text
    ):
        # type: (str, str, str) -> dict
        """Update auto-generated text on a character's history entry."""
        try:
            from characters import update_history_auto_text as _update_auto
            ok = _update_auto(char_id, session_id, auto_text)
            return {"ok": ok}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def update_character_history_summary(self, char_id, summary):
        # type: (str, str) -> dict
        """Manually update a character's history summary."""
        try:
            ok = _set_history_summary(char_id, summary)
            return {"ok": ok}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def generate_character_history_summary(self, char_id: str) -> dict:
        """Generate a condensed summary of a character's full history."""
        _log.info("generate_character_history_summary  id=%s", char_id)
        try:
            char = _get_character(char_id)
            if not char:
                return {"ok": False, "error": "Character not found"}

            history = char.get("history", [])
            if not history:
                return {"ok": False, "error": "No history entries to summarize"}

            # Build history text
            history_text = ""
            for entry in history:
                history_text += "### {} — {} Season {}\n".format(
                    entry.get("session_date", "Unknown"),
                    entry.get("campaign_name", ""),
                    entry.get("season_number", ""),
                )
                if entry.get("auto_text"):
                    history_text += entry["auto_text"] + "\n"
                if entry.get("manual_text"):
                    history_text += "Player notes: " + entry["manual_text"] + "\n"
                history_text += "\n"

            # Get LLM provider info
            provider = get_pref("llm_provider") or "anthropic"
            if provider == "anthropic":
                api_key = get_claude_token()
            else:
                api_key = get_openai_token()
            model = None

            prompt = (
                "You are a fantasy storyteller summarizing a D&D character's journey.\n\n"
                "## Character\n"
                "Name: {name}\n"
                "Race: {race}\n"
                "Class: {cls}\n\n"
                "## Session-by-Session History\n"
                "{history}\n\n"
                "Write a cohesive narrative summary (3-5 paragraphs) of this character's arc "
                "so far. Highlight key moments, character growth, relationships formed, "
                "challenges overcome, and current situation. Write in third person past tense. "
                "Be vivid and engaging but concise."
            ).format(
                name=char.get("name", "Unknown"),
                race=char.get("race", ""),
                cls=char.get("class_name", ""),
                history=history_text,
            )

            from llm import call_llm
            summary = call_llm(prompt, api_key, provider=provider, model=model, max_tokens=1024)
            _set_history_summary(char_id, summary)
            return {"ok": True, "summary": summary}
        except Exception as e:
            _log.error("generate_character_history_summary failed: %s", e)
            return {"ok": False, "error": str(e)}

    # ── Entity Registry API ──────────────────────────────────────────────

    def get_entities(self, campaign_id, entity_type=None):
        # type: (str, Optional[str]) -> dict
        """Return all entities for a campaign, optionally filtered by type."""
        try:
            # Ensure migration on first access
            glossary = _get_glossary(campaign_id)
            sessions = get_sessions()
            _ensure_entities_migrated(campaign_id, glossary, sessions)

            entities = _get_entities(campaign_id, entity_type)
            return {"ok": True, "entities": entities}
        except Exception as e:
            _log.error("get_entities failed: %s", e)
            return {"ok": False, "error": str(e)}

    def get_entity_detail(self, campaign_id, entity_id):
        # type: (str, str) -> dict
        """Return a single entity with its relationships and timeline."""
        try:
            entity = _get_entity(campaign_id, entity_id)
            if not entity:
                return {"ok": False, "error": "Entity not found"}
            relationships = _get_relationships(campaign_id, entity_id)
            timeline = _get_entity_timeline(campaign_id, entity_id)
            return {
                "ok": True,
                "entity": entity,
                "relationships": relationships,
                "timeline": timeline,
            }
        except Exception as e:
            _log.error("get_entity_detail failed: %s", e)
            return {"ok": False, "error": str(e)}

    def get_entity_relationships(self, campaign_id, entity_id):
        # type: (str, str) -> dict
        """Return all relationships for an entity."""
        try:
            relationships = _get_relationships(campaign_id, entity_id)
            return {"ok": True, "relationships": relationships}
        except Exception as e:
            _log.error("get_entity_relationships failed: %s", e)
            return {"ok": False, "error": str(e)}

    def get_entity_timeline(self, campaign_id, entity_id):
        # type: (str, str) -> dict
        """Return the full timeline for an entity (changes + relationship events)."""
        try:
            timeline = _get_entity_timeline(campaign_id, entity_id)
            return {"ok": True, "timeline": timeline}
        except Exception as e:
            _log.error("get_entity_timeline failed: %s", e)
            return {"ok": False, "error": str(e)}

    def migrate_campaign_entities(self, campaign_id):
        # type: (str,) -> dict
        """Trigger entity migration for a campaign (glossary + session artifacts)."""
        try:
            glossary = _get_glossary(campaign_id)
            sessions = get_sessions()
            migrated = _ensure_entities_migrated(campaign_id, glossary, sessions)
            return {"ok": True, "migrated": migrated}
        except Exception as e:
            _log.error("migrate_campaign_entities failed: %s", e)
            return {"ok": False, "error": str(e)}

