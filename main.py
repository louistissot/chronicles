#!/usr/bin/env python3
"""Chronicles — Entry point. Launches the pywebview window with React frontend."""
import json
import sys
from pathlib import Path

import webview  # type: ignore

import deps  # background dependency version check / auto-upgrade
import log  # initialises rotating file logger first — must be before other imports
from backend import API
from log import get_logger

_log = get_logger("main")

AUDIO_EXTS    = {"m4a", "mp3", "wav", "ogg", "flac", "aac", "wma"}
TRANSCRIPT_EXTS = {"json", "txt", "srt"}


def _setup_native_drag_drop(window: webview.Window) -> None:
    """Register the app window as a native macOS file drop destination."""
    try:
        import AppKit  # type: ignore
        import objc  # type: ignore

        NSDragOperationCopy = 1

        from Foundation import NSURL  # type: ignore

        class _FileDropView(AppKit.NSView):  # type: ignore
            """Transparent full-window overlay that accepts file drops."""

            def init(self):
                self = objc.super(_FileDropView, self).init()
                if self is not None:
                    # Register for modern UTI-based drag types
                    self.registerForDraggedTypes_([
                        "public.file-url",
                    ])
                return self

            def _get_file_paths(self, sender):
                """Extract file paths from the pasteboard using modern API."""
                pboard = sender.draggingPasteboard()
                # Use readObjectsForClasses:options: with NSURL
                urls = pboard.readObjectsForClasses_options_(
                    [NSURL], {"NSPasteboardURLReadingFileURLsOnlyKey": True}
                )
                if not urls:
                    return []
                return [u.path() for u in urls if u.path()]

            def _classify(self, sender):
                """Return file type ('audio'/'transcript') or None."""
                paths = self._get_file_paths(sender)
                if not paths:
                    return None
                ext = Path(paths[0]).suffix.lstrip(".").lower()
                if ext in AUDIO_EXTS:
                    return "audio"
                if ext in TRANSCRIPT_EXTS:
                    return "transcript"
                return None

            def draggingEntered_(self, sender):
                dtype = self._classify(sender)
                if dtype:
                    window.evaluate_js(
                        'window._pyDragOver && window._pyDragOver("{}")'.format(dtype)
                    )
                    return NSDragOperationCopy
                return 0

            def draggingUpdated_(self, sender):
                dtype = self._classify(sender)
                return NSDragOperationCopy if dtype else 0

            def draggingExited_(self, sender):
                window.evaluate_js(
                    "window._pyDragLeave && window._pyDragLeave()"
                )

            def hitTest_withEvent_(self, point, event):
                return None  # Pass all mouse/keyboard events through to the webview

            def prepareForDragOperation_(self, sender):
                return True

            def performDragOperation_(self, sender):
                paths = self._get_file_paths(sender)
                if not paths:
                    _log.warning("drag-drop: no file paths extracted from pasteboard")
                    return False
                path = paths[0]
                ext  = Path(path).suffix.lstrip(".").lower()
                if ext in AUDIO_EXTS:
                    dtype = "audio"
                elif ext in TRANSCRIPT_EXTS:
                    dtype = "transcript"
                else:
                    _log.warning("drag-drop: unsupported extension: %s", ext)
                    return False
                payload = json.dumps({"type": dtype, "path": path})
                window.evaluate_js("window._pyDragDrop && window._pyDragDrop({})".format(payload))
                _log.info("drag-drop file accepted: %s (%s)", path, dtype)
                return True

            def concludeDragOperation_(self, sender):
                window.evaluate_js(
                    "window._pyDragLeave && window._pyDragLeave()"
                )

        # Find the app's key NSWindow and attach the overlay view
        ns_app = AppKit.NSApplication.sharedApplication()
        ns_win = ns_app.keyWindow() or ns_app.mainWindow()
        if ns_win is None:
            # Window not yet key — iterate all windows
            for w in ns_app.windows():
                if w.title() == "Chronicles":
                    ns_win = w
                    break

        if ns_win is None:
            _log.warning("native DnD: could not find NSWindow")
            return

        content = ns_win.contentView()
        overlay = _FileDropView.alloc().initWithFrame_(content.frame())
        overlay.setAutoresizingMask_(18)   # flexible width + height
        overlay.setWantsLayer_(True)
        overlay.layer().setBackgroundColor_(
            AppKit.NSColor.clearColor().CGColor()
        )
        content.addSubview_positioned_relativeTo_(
            overlay, AppKit.NSWindowAbove, None
        )
        _log.info("native DnD registered on NSWindow")

    except Exception as e:
        _log.warning("native DnD setup skipped: %s", e)


# When bundled with PyInstaller the dist/ lives next to the executable;
# when running from source it's at frontend/dist/index.html.
def _find_index() -> str:
    # PyInstaller sets sys._MEIPASS when running from .app bundle
    if hasattr(sys, "_MEIPASS"):
        dist = Path(sys._MEIPASS) / "frontend_dist" / "index.html"
    else:
        dist = Path(__file__).parent / "frontend" / "dist" / "index.html"

    if not dist.exists():
        raise FileNotFoundError(
            f"Frontend build not found at {dist}\n"
            "Run:  cd frontend && npm install && npm run build"
        )
    return dist.as_uri()


def main():
    _log.info("=" * 60)
    _log.info("Chronicles starting  python=%s", sys.version.split()[0])
    _log.info("Log file: %s", log._LOG_FILE)

    # Kick off background dependency check (non-blocking, skipped in bundled .app)
    deps.run_in_background()

    window_ref: list = [None]
    api = API(window_ref)

    url = _find_index()
    _log.info("Frontend URL: %s", url)
    window = webview.create_window(
        title="Chronicles",
        url=url,
        js_api=api,
        width=900,
        height=700,
        min_size=(720, 560),
        background_color="#080B14",
        frameless=False,
        easy_drag=False,
        text_select=False,
    )
    window_ref[0] = window
    window.events.loaded += lambda: _setup_native_drag_drop(window)

    _log.info("Window created, entering webview event loop")
    webview.start(debug=False)
    _log.info("Chronicles exiting")


if __name__ == "__main__":
    main()
