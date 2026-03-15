"""
Subprocess runner for ffmpeg conversion and WhisperX transcription.
Streams stdout/stderr to a queue so the GUI can display it in real-time.
"""
import os
import platform
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Callable, Optional

# On macOS the CPU backend (ctranslate2) does not support float16 — use int8.
# int8 is also faster on CPU with negligible quality loss.
_COMPUTE_TYPE = "int8" if platform.system() == "Darwin" else "float16"

from log import get_logger

_log = get_logger("runner")

# Locate whisperx binary (installed in same pip env as whisperx package)
_WHISPERX_BIN = shutil.which("whisperx") or str(
    Path.home() / "Library/Python/3.9/bin/whisperx"
)
_FFMPEG_BIN = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"

# Extra directories to prepend to PATH when spawning subprocesses,
# so the whisperx binary and ffmpeg are found even from a bundled .app.
_EXTRA_PATH_DIRS = [
    str(Path.home() / "Library" / "Python" / "3.9" / "bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
]


class TranscriptionJob:
    """Manages one ffmpeg+whisperx run."""

    def __init__(
        self,
        audio_path: str,
        output_dir: str,
        hf_token: str,
        model: str,
        num_speakers: int,
        on_line: Callable[[str], None],
        on_done: Callable[[bool, Optional[Path]], None],
        language: str = "auto",
    ):
        self.audio_path = Path(audio_path)
        self.output_dir = Path(output_dir)
        self.hf_token = hf_token
        self.model = model
        self.num_speakers = num_speakers
        self.language = language
        self.on_line = on_line   # called with each output line
        self.on_done = on_done   # called with (success: bool, json_path: Path | None)

        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._cancelled = False
        self._tmp_dir: Optional[str] = None

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._cancelled = True
        if self._proc and self._proc.poll() is None:
            self._proc.kill()

    # keep cancel as an alias
    cancel = stop

    def is_running(self) -> bool:
        return not self._cancelled and self._thread is not None and self._thread.is_alive()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run(self) -> None:
        _log.info(
            "Job thread started  audio=%s  model=%s  speakers=%d  language=%s",
            self.audio_path, self.model, self.num_speakers, self.language,
        )
        try:
            wav_path = self._maybe_convert()
            if self._cancelled:
                _log.info("Job cancelled after conversion")
                return
            json_path = self._run_whisperx(wav_path)
            if self._cancelled:
                _log.info("Job cancelled after whisperx")
                return
            self.on_done(True, json_path)
        except Exception as exc:
            _log.error("Job failed: %s", exc, exc_info=True)
            try:
                self.on_line(f"\n[ERROR] {exc}\n")
            except Exception:
                pass
            self.on_done(False, None)
        finally:
            if self._tmp_dir:
                shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def _maybe_convert(self) -> Path:
        """Return path to a WAV file, converting if necessary."""
        if self.audio_path.suffix.lower() == ".wav":
            self.on_line("[Info] Input is already WAV — skipping conversion.\n")
            return self.audio_path

        self._tmp_dir = tempfile.mkdtemp(prefix="dnd_whisperx_")
        wav_path = Path(self._tmp_dir) / (self.audio_path.stem + ".wav")

        cmd = [
            _FFMPEG_BIN, "-y",
            "-i", str(self.audio_path),
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(wav_path),
        ]
        _log.info("ffmpeg cmd: %s", " ".join(cmd))
        self.on_line(f"[ffmpeg] Converting {self.audio_path.name} → WAV …\n")
        self._stream(cmd)
        if not wav_path.exists():
            raise RuntimeError("ffmpeg conversion failed — WAV file not created.")
        _log.info("ffmpeg conversion done → %s", wav_path)
        self.on_line("[ffmpeg] Conversion complete.\n\n")
        return wav_path

    def _run_whisperx(self, wav_path: Path) -> Optional[Path]:
        """Run whisperx and return path to the output JSON."""
        self.output_dir.mkdir(parents=True, exist_ok=True)

        whisperx_bin = _WHISPERX_BIN
        _log.info("Using whisperx binary: %s", whisperx_bin)

        cmd = [
            whisperx_bin,
            str(wav_path),
            "--model", self.model,
            "--compute_type", _COMPUTE_TYPE,
            "--diarize",
            "--hf_token", self.hf_token,
            "--min_speakers", str(self.num_speakers),
            "--max_speakers", str(self.num_speakers),
            "--output_dir", str(self.output_dir),
            "--output_format", "json",
        ]

        # Add language if explicitly specified (not auto)
        if self.language and self.language != "auto":
            cmd.extend(["--language", self.language])

        _log.info(
            "whisperx cmd: %s",
            " ".join(str(c) for c in cmd if c != self.hf_token),
        )
        self.on_line(
            f"[WhisperX] Starting transcription\n"
            f"  model    : {self.model}\n"
            f"  speakers : {self.num_speakers}\n"
            f"  language : {self.language}\n"
            f"  output   : {self.output_dir}\n\n"
        )
        self._stream(cmd)

        # WhisperX writes <stem>.json to output_dir
        stem = wav_path.stem
        json_path = self.output_dir / f"{stem}.json"
        if json_path.exists():
            self.on_line(f"\n[Done] Output saved to {json_path}\n")
            return json_path

        # Fallback: search for any JSON produced
        candidates = list(self.output_dir.glob("*.json"))
        if candidates:
            self.on_line(f"\n[Done] Output saved to {candidates[0]}\n")
            return candidates[0]

        self.on_line("\n[Warning] Could not locate output JSON file.\n")
        return None

    def _stream(self, cmd: list) -> None:
        """Run cmd, streaming every line to on_line callback."""
        env = os.environ.copy()
        # Ensure user Python bin and Homebrew are on PATH (needed when running from .app)
        existing_path = env.get("PATH", "")
        extra = ":".join(d for d in _EXTRA_PATH_DIRS if d not in existing_path)
        if extra:
            env["PATH"] = f"{extra}:{existing_path}"

        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env,
            bufsize=1,
        )
        assert self._proc.stdout
        for line in self._proc.stdout:
            if self._cancelled:
                break
            self.on_line(line)
        self._proc.wait()
        rc = self._proc.returncode
        _log.debug("subprocess exited  returncode=%s  cmd=%s", rc, cmd[0])
        if rc not in (0, None) and not self._cancelled:
            raise RuntimeError(f"Process exited with code {rc}")
