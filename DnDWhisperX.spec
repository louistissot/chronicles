# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for DnD WhisperX (pywebview + React build).

Build:
  /Users/louistissot/Library/Python/3.9/bin/pyinstaller DnDWhisperX.spec --clean --noconfirm
"""
import os
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Include the built React frontend as a data directory
FRONTEND_DIST = str(Path("frontend/dist").resolve())

numpy_datas, numpy_binaries, numpy_hiddenimports = collect_all("numpy")
sd_datas, sd_binaries, sd_hiddenimports = collect_all("sounddevice")

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[] + numpy_binaries + sd_binaries,
    datas=[
        (FRONTEND_DIST, "frontend_dist"),
        ("maps.py", "."),
    ] + numpy_datas + sd_datas,
    hiddenimports=[
        # App modules
        "config",
        "runner",
        "postprocess",
        "llm_mapper",
        "llm",
        "sessions",
        "campaigns",
        "characters",
        "entities",
        "maps",
        "image_gen",
        "deps",
        "backend",
        # pywebview
        "webview",
        "webview.platforms.cocoa",
        "webview.platforms.gtk",
        "webview.platforms.winforms",
        "webview.js",
        # keyring macOS backends
        "keyring",
        "keyring.backends",
        "keyring.backends.macOS",
        "keyring.backends.fail",
        "keyring.backends.null",
        # anthropic / httpx
        "anthropic",
        "httpx",
        "httpcore",
        "anyio",
        "certifi",
        # openai
        "openai",
        # objc / Foundation (needed by pywebview on macOS)
        "objc",
        "Foundation",
        "AppKit",
        "WebKit",
        # audio recording
        "sounddevice",
        "sounddevice._sounddevice",
        "numpy",
        "numpy.core",
        "numpy.core._multiarray_umath",
        "cffi",
        "_cffi_backend",
    ] + numpy_hiddenimports + sd_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "torch",
        "torchaudio",
        "whisperx",
        "pyannote",
        "faster_whisper",
        "transformers",
        "tkinter",
        "_tkinter",
        "customtkinter",
        "darkdetect",
        "PyQt6",
        "PIL",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Chronicles",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Chronicles",
)

app = BUNDLE(
    coll,
    name="Chronicles.app",
    icon="DnDWhisperX.icns",
    bundle_identifier="com.louistissot.chronicles",
    info_plist={
        "CFBundleDisplayName": "Chronicles",
        "CFBundleShortVersionString": "2.0.0",
        "CFBundleVersion": "2.0.0",
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "Microphone access for recording DnD sessions.",
        "LSMinimumSystemVersion": "11.0",
    },
)
