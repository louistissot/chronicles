"""
Centralised logging for DnD WhisperX.

Log file: ~/.config/dnd-whisperx/app.log
Rotates at 5 MB, keeps 3 backups → max ~20 MB on disk.

Usage (any module):
    from log import log
    log.info("...")
    log.warning("...")
    log.error("...", exc_info=True)
"""
import logging
import logging.handlers
import pathlib
import sys

_LOG_DIR = pathlib.Path.home() / ".config" / "dnd-whisperx"
_LOG_FILE = _LOG_DIR / "app.log"

_FMT = "%(asctime)s  %(levelname)-8s  %(name)-20s  %(message)s"
_DATE_FMT = "%Y-%m-%d %H:%M:%S"


def _setup() -> logging.Logger:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("dnd")
    if root.handlers:           # already initialised (e.g. reimport)
        return root

    root.setLevel(logging.DEBUG)

    # ── Rotating file handler ─────────────────────────────────────────────────
    fh = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=5 * 1024 * 1024,   # 5 MB per file
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))
    root.addHandler(fh)

    # ── Console handler (visible when running from terminal / debug mode) ─────
    if not getattr(sys, "frozen", False):
        sh = logging.StreamHandler(sys.stderr)
        sh.setLevel(logging.DEBUG)
        sh.setFormatter(logging.Formatter(_FMT, datefmt=_DATE_FMT))
        root.addHandler(sh)

    return root


log: logging.Logger = _setup()


def get_logger(name: str) -> logging.Logger:
    """Return a child logger, e.g. get_logger('backend') → 'dnd.backend'."""
    return logging.getLogger(f"dnd.{name}")
