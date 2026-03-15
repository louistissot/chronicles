"""Persistent configuration: tokens and preferences stored in a local JSON file.

Tokens are stored in plain JSON alongside preferences — this app runs locally
only, so no need for the macOS Keychain.
"""
import json
import pathlib
import threading

CONFIG_DIR  = pathlib.Path.home() / ".config" / "dnd-whisperx"
CONFIG_FILE = CONFIG_DIR / "prefs.json"

# Guard against concurrent read-modify-write on prefs.json
_prefs_lock = threading.Lock()

_SESSIONS_DIR = pathlib.Path.home() / "Documents" / "Chronicles"

_DEFAULTS = {
    "model": "large-v2",
    "output_dir": str(_SESSIONS_DIR),
    "num_speakers": "2",
    "character_names": "",
    "llm_provider": "anthropic",
    "openai_model": "gpt-4.5",
}


def _load_prefs() -> dict:
    """Load prefs from disk. Caller MUST hold _prefs_lock when used in a
    read-modify-write cycle (see set_token / set_pref)."""
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except Exception:
            pass
    return dict(_DEFAULTS)


def _save_prefs(prefs: dict) -> None:
    """Write prefs atomically (write tmp then rename) to avoid partial writes."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(prefs, indent=2))
    tmp.replace(CONFIG_FILE)


# ── Token helpers ─────────────────────────────────────────────────────────────

def get_token(name: str) -> str:
    return _load_prefs().get(f"token_{name}", "")


def set_token(name: str, value: str) -> None:
    with _prefs_lock:
        prefs = _load_prefs()
        prefs[f"token_{name}"] = value
        _save_prefs(prefs)


def get_hf_token() -> str:
    return get_token("hf_token")


def set_hf_token(value: str) -> None:
    set_token("hf_token", value)


def get_claude_token() -> str:
    return get_token("claude_token")


def set_claude_token(value: str) -> None:
    set_token("claude_token", value)


def get_openai_token() -> str:
    return get_token("openai_token")


def set_openai_token(value: str) -> None:
    set_token("openai_token", value)


def get_gemini_token() -> str:
    return get_token("gemini_token")


def set_gemini_token(value: str) -> None:
    set_token("gemini_token", value)


# ── Preference helpers ────────────────────────────────────────────────────────

def get_pref(key: str):
    return _load_prefs().get(key, _DEFAULTS.get(key))


def set_pref(key: str, value) -> None:
    with _prefs_lock:
        prefs = _load_prefs()
        prefs[key] = value
        _save_prefs(prefs)
