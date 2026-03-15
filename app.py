"""
DnD WhisperX — Main window (PyQt6).
4 tabs: Session Setup | Progress | Speaker Review | Settings
"""
import queue
import threading
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont, QTextCursor
from PyQt6.QtWidgets import (
    QComboBox, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSpinBox,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

import config
import postprocess
from runner import TranscriptionJob

MODELS = ["tiny", "base", "small", "medium", "large-v2", "large-v3"]
AUDIO_EXTS = (
    "Audio files (*.m4a *.mp3 *.wav *.ogg *.flac *.aac *.opus *.wma *.webm);;"
    "All files (*.*)"
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DnD WhisperX")
        self.resize(900, 700)
        self.setMinimumSize(800, 580)

        self._audio_path: Optional[str] = None
        self._output_dir: Optional[str] = config.get_pref("last_output_dir")
        self._job: Optional[TranscriptionJob] = None
        self._log_queue: queue.Queue = queue.Queue()
        self._json_path: Optional[Path] = None
        self._whisperx_data: Optional[dict] = None
        self._speaker_combos: Dict[str, QComboBox] = {}
        self._char_entries: List[QLineEdit] = []

        self._build_ui()

        self._timer = QTimer()
        self._timer.timeout.connect(self._poll_log_queue)
        self._timer.start(50)

        if not config.get_hf_token():
            QTimer.singleShot(600, self._prompt_missing_hf_token)

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)

        self._tabs = QTabWidget()
        root.addWidget(self._tabs)

        self._build_session_tab()
        self._build_progress_tab()
        self._build_review_tab()
        self._build_settings_tab()

    # ── Tab 1: Session ────────────────────────────────────────────────────────

    def _build_session_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(14)

        # Audio file
        layout.addLayout(self._file_row(
            "Audio file:",
            "_audio_label", "No file selected",
            "Browse…", self._browse_audio,
        ))

        # Output folder
        layout.addLayout(self._file_row(
            "Output folder:",
            "_output_label", self._output_dir or "Not set",
            "Choose…", self._browse_output,
        ))

        # Model
        model_row = QHBoxLayout()
        model_row.addWidget(QLabel("Whisper model:"))
        self._model_combo = QComboBox()
        self._model_combo.addItems(MODELS)
        saved = config.get_pref("model") or "large-v2"
        idx = self._model_combo.findText(saved)
        if idx >= 0:
            self._model_combo.setCurrentIndex(idx)
        self._model_combo.setFixedWidth(180)
        model_row.addWidget(self._model_combo)
        model_row.addStretch()
        layout.addLayout(model_row)

        layout.addWidget(self._separator())

        # Number of speakers
        spk_row = QHBoxLayout()
        spk_row.addWidget(QLabel("Number of speakers:"))
        self._speaker_spin = QSpinBox()
        self._speaker_spin.setRange(1, 10)
        self._speaker_spin.setValue(2)
        self._speaker_spin.setFixedWidth(70)
        self._speaker_spin.valueChanged.connect(self._refresh_char_entries)
        spk_row.addWidget(self._speaker_spin)
        spk_row.addStretch()
        layout.addLayout(spk_row)

        # Character names
        char_row = QHBoxLayout()
        char_lbl = QLabel("Character names:")
        char_lbl.setAlignment(Qt.AlignmentFlag.AlignTop)
        char_row.addWidget(char_lbl)

        self._char_scroll = QScrollArea()
        self._char_scroll.setWidgetResizable(True)
        self._char_scroll.setFixedHeight(150)
        self._char_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #3B3B50; border-radius: 4px; background: #1C1C24; }"
        )
        self._char_container = QWidget()
        self._char_layout = QVBoxLayout(self._char_container)
        self._char_layout.setContentsMargins(8, 8, 8, 8)
        self._char_layout.setSpacing(6)
        self._char_scroll.setWidget(self._char_container)
        char_row.addWidget(self._char_scroll, 1)
        layout.addLayout(char_row)

        self._refresh_char_entries()
        layout.addStretch()

        # Run button
        self._run_btn = QPushButton("▶  Run WhisperX")
        self._run_btn.setMinimumHeight(50)
        f = self._run_btn.font()
        f.setPointSize(14)
        f.setBold(True)
        self._run_btn.setFont(f)
        self._run_btn.setStyleSheet("""
            QPushButton {
                background: #3B8ED0; color: white;
                border: none; border-radius: 6px;
            }
            QPushButton:hover   { background: #4A9FE1; }
            QPushButton:pressed { background: #2A7DC0; }
            QPushButton:disabled { background: #2B2B3A; color: #555; border: none; }
        """)
        self._run_btn.clicked.connect(self._run)
        layout.addWidget(self._run_btn)

        self._tabs.addTab(w, "  Session  ")

    def _file_row(self, label_text, attr, default_text, btn_text, slot):
        row = QHBoxLayout()
        row.addWidget(QLabel(label_text))
        lbl = QLabel(default_text)
        lbl.setStyleSheet(
            "background: #252530; border: 1px solid #3B3B50; "
            "border-radius: 4px; padding: 5px 10px;"
        )
        lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        setattr(self, attr, lbl)
        row.addWidget(lbl, 1)
        btn = QPushButton(btn_text)
        btn.setFixedWidth(90)
        btn.clicked.connect(slot)
        row.addWidget(btn)
        return row

    def _refresh_char_entries(self):
        n = self._speaker_spin.value()
        existing = [e.text() for e in self._char_entries]

        while self._char_layout.count():
            item = self._char_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._char_entries = []

        placeholders = ["DM", "Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Grace", "Heidi", "Ivan"]
        for i in range(n):
            entry = QLineEdit()
            entry.setPlaceholderText(
                f"Character {i+1} (e.g. {placeholders[i % len(placeholders)]})"
            )
            if i < len(existing):
                entry.setText(existing[i])
            self._char_layout.addWidget(entry)
            self._char_entries.append(entry)
        self._char_layout.addStretch()

    def _browse_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select audio file",
            config.get_pref("last_audio_dir") or str(Path.home()),
            AUDIO_EXTS,
        )
        if path:
            self._audio_path = path
            config.set_pref("last_audio_dir", str(Path(path).parent))
            self._audio_label.setText(Path(path).name)

    def _browse_output(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select output folder",
            self._output_dir or str(Path.home()),
        )
        if path:
            self._output_dir = path
            config.set_pref("last_output_dir", path)
            self._output_label.setText(path)

    # ── Tab 2: Progress ───────────────────────────────────────────────────────

    def _build_progress_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)

        status_bar = QHBoxLayout()
        status_bar.addWidget(QLabel("Status:"))
        self._status_label = QLabel("Idle")
        self._status_label.setStyleSheet("color: #666;")
        status_bar.addWidget(self._status_label, 1)
        self._stop_btn = QPushButton("■  Stop")
        self._stop_btn.setFixedWidth(90)
        self._stop_btn.setStyleSheet(
            "QPushButton { background: #3B3B50; border: none; border-radius: 4px; }"
            "QPushButton:hover { background: #4B4B60; }"
        )
        self._stop_btn.clicked.connect(self._stop)
        status_bar.addWidget(self._stop_btn)
        layout.addLayout(status_bar)

        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Menlo", 12))
        self._log.setStyleSheet("""
            QTextEdit {
                background: #0E0E16; color: #C8D0DC;
                border: 1px solid #3B3B50; border-radius: 4px;
                padding: 8px;
            }
        """)
        layout.addWidget(self._log, 1)
        self._tabs.addTab(w, "  Progress  ")

    def _log_append(self, text: str):
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertText(text)
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()

    def _poll_log_queue(self):
        try:
            while True:
                self._log_append(self._log_queue.get_nowait())
        except queue.Empty:
            pass

    def _set_status(self, text: str, color: str = "#666"):
        self._status_label.setText(text)
        self._status_label.setStyleSheet(f"color: {color};")

    # ── Tab 3: Speaker Review ─────────────────────────────────────────────────

    def _build_review_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 12, 16, 16)
        layout.setSpacing(8)

        self._review_scroll = QScrollArea()
        self._review_scroll.setWidgetResizable(True)
        self._review_scroll.setStyleSheet(
            "QScrollArea { border: 1px solid #3B3B50; border-radius: 4px; background: #1C1C24; }"
        )
        self._review_container = QWidget()
        self._review_layout = QVBoxLayout(self._review_container)
        self._review_layout.setContentsMargins(12, 12, 12, 12)
        self._review_layout.setSpacing(8)
        self._review_scroll.setWidget(self._review_container)

        placeholder = QLabel("Run a transcription first to see speakers here.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder.setStyleSheet("color: #555; font-size: 15px;")
        self._review_layout.addWidget(placeholder)
        self._review_layout.addStretch()

        layout.addWidget(self._review_scroll, 1)

        btn_bar = QHBoxLayout()
        self._llm_btn = QPushButton("✨  Auto-suggest (Claude)")
        self._llm_btn.setStyleSheet(
            "QPushButton { background: #3B3B50; border: none; border-radius: 4px; padding: 8px 16px; }"
            "QPushButton:hover { background: #4B4B60; }"
            "QPushButton:disabled { color: #555; }"
        )
        self._llm_btn.clicked.connect(self._llm_suggest)
        btn_bar.addWidget(self._llm_btn)
        btn_bar.addStretch()

        self._apply_btn = QPushButton("💾  Apply & Save transcript")
        self._apply_btn.setStyleSheet("""
            QPushButton { background: #3B8ED0; color: white; border: none; border-radius: 4px; padding: 8px 16px; }
            QPushButton:hover { background: #4A9FE1; }
        """)
        self._apply_btn.clicked.connect(self._apply_mapping)
        btn_bar.addWidget(self._apply_btn)
        layout.addLayout(btn_bar)

        self._tabs.addTab(w, "  Speaker Review  ")

    def _populate_review(self):
        if not self._whisperx_data:
            return

        while self._review_layout.count():
            item = self._review_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._speaker_combos = {}

        samples = postprocess.get_speaker_samples(self._whisperx_data, n_samples=3)
        speakers = postprocess.get_speakers(self._whisperx_data)
        char_names = [
            e.text().strip() or f"Character {i+1}"
            for i, e in enumerate(self._char_entries)
        ]
        options = char_names + ["Unknown"]

        if not speakers:
            lbl = QLabel("No speakers found in transcript output.")
            lbl.setStyleSheet("color: #e74c3c;")
            self._review_layout.addWidget(lbl)
            self._review_layout.addStretch()
            return

        # Header row
        hdr = QWidget()
        hdr_layout = QHBoxLayout(hdr)
        hdr_layout.setContentsMargins(12, 4, 12, 4)
        for text, width in [("Speaker ID", 130), ("Sample lines", 0), ("Assign to", 190)]:
            lbl = QLabel(text)
            lbl.setStyleSheet("font-weight: bold; color: #8090A0; font-size: 12px;")
            if width:
                lbl.setFixedWidth(width)
            else:
                lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            hdr_layout.addWidget(lbl)
        self._review_layout.addWidget(hdr)

        for i, sp in enumerate(speakers):
            frame = QFrame()
            frame.setStyleSheet("QFrame { background: #252530; border-radius: 6px; }")
            row = QHBoxLayout(frame)
            row.setContentsMargins(12, 10, 12, 10)
            row.setSpacing(12)

            id_lbl = QLabel(sp)
            id_lbl.setFixedWidth(130)
            id_lbl.setFont(QFont("Menlo", 12))
            id_lbl.setStyleSheet("color: #7EB8E0;")
            row.addWidget(id_lbl)

            sp_samples = samples.get(sp, ["(no samples)"])
            sample_lbl = QLabel("\n".join(f'"{s}"' for s in sp_samples))
            sample_lbl.setWordWrap(True)
            sample_lbl.setStyleSheet("color: #7A8A9A; font-size: 13px;")
            sample_lbl.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            row.addWidget(sample_lbl, 1)

            combo = QComboBox()
            combo.addItems(options)
            if i < len(char_names):
                combo.setCurrentText(char_names[i])
            combo.setFixedWidth(190)
            row.addWidget(combo)

            self._speaker_combos[sp] = combo
            self._review_layout.addWidget(frame)

        self._review_layout.addStretch()

    # ── Tab 4: Settings ───────────────────────────────────────────────────────

    def _build_settings_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("API Keys")
        f = title.font()
        f.setPointSize(15)
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)

        # HuggingFace token
        hf_row = QHBoxLayout()
        lbl = QLabel("HuggingFace token:")
        lbl.setFixedWidth(190)
        hf_row.addWidget(lbl)
        self._hf_entry = QLineEdit()
        self._hf_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self._hf_entry.setPlaceholderText("hf_…")
        if config.get_hf_token():
            self._hf_entry.setText(config.get_hf_token())
        hf_row.addWidget(self._hf_entry, 1)
        self._hf_status = QLabel("")
        self._hf_status.setFixedWidth(80)
        hf_row.addWidget(self._hf_status)
        save_hf = QPushButton("Save")
        save_hf.setFixedWidth(70)
        save_hf.clicked.connect(self._save_hf_token)
        hf_row.addWidget(save_hf)
        layout.addLayout(hf_row)
        self._refresh_hf_status()

        info_hf = QLabel(
            "Required for speaker diarization. "
            "Get a free token at huggingface.co/settings/tokens"
        )
        info_hf.setStyleSheet("color: #555; font-size: 12px;")
        info_hf.setWordWrap(True)
        layout.addWidget(info_hf)

        layout.addWidget(self._separator())

        # Claude API key
        claude_row = QHBoxLayout()
        lbl2 = QLabel("Claude API key:")
        lbl2.setFixedWidth(190)
        claude_row.addWidget(lbl2)
        self._claude_entry = QLineEdit()
        self._claude_entry.setEchoMode(QLineEdit.EchoMode.Password)
        self._claude_entry.setPlaceholderText("sk-ant-…")
        if config.get_claude_token():
            self._claude_entry.setText(config.get_claude_token())
        claude_row.addWidget(self._claude_entry, 1)
        self._claude_status = QLabel("")
        self._claude_status.setFixedWidth(80)
        claude_row.addWidget(self._claude_status)
        save_claude = QPushButton("Save")
        save_claude.setFixedWidth(70)
        save_claude.clicked.connect(self._save_claude_token)
        claude_row.addWidget(save_claude)
        layout.addLayout(claude_row)
        self._refresh_claude_status()

        info_claude = QLabel('Optional — enables "Auto-suggest" in the Speaker Review tab.')
        info_claude.setStyleSheet("color: #555; font-size: 12px;")
        layout.addWidget(info_claude)

        layout.addStretch()
        self._tabs.addTab(w, "  Settings  ")

    def _save_hf_token(self):
        config.set_hf_token(self._hf_entry.text().strip())
        self._refresh_hf_status()

    def _save_claude_token(self):
        config.set_claude_token(self._claude_entry.text().strip())
        self._refresh_claude_status()

    def _refresh_hf_status(self):
        if config.get_hf_token():
            self._hf_status.setText("✓ Saved")
            self._hf_status.setStyleSheet("color: #4CD389;")
        else:
            self._hf_status.setText("Not set")
            self._hf_status.setStyleSheet("color: #555;")

    def _refresh_claude_status(self):
        if config.get_claude_token():
            self._claude_status.setText("✓ Saved")
            self._claude_status.setStyleSheet("color: #4CD389;")
        else:
            self._claude_status.setText("Not set")
            self._claude_status.setStyleSheet("color: #555;")

    # ── Run / Stop ────────────────────────────────────────────────────────────

    def _run(self):
        if not self._audio_path:
            QMessageBox.warning(self, "Missing audio", "Please select an audio file first.")
            return
        if not self._output_dir:
            QMessageBox.warning(self, "Missing output", "Please choose an output folder first.")
            return
        hf_token = config.get_hf_token()
        if not hf_token:
            QMessageBox.warning(
                self, "HuggingFace token missing",
                "Please save your HuggingFace token in the Settings tab.\n"
                "It is required for speaker diarization.",
            )
            self._tabs.setCurrentIndex(3)
            return

        config.set_pref("model", self._model_combo.currentText())

        self._log.clear()
        self._tabs.setCurrentIndex(1)
        self._set_status("Starting…", "#f0a500")
        self._run_btn.setEnabled(False)

        def on_line(line: str):
            self._log_queue.put(line)

        def on_done(success: bool, json_path):
            self._json_path = json_path
            if success and json_path:
                try:
                    self._whisperx_data = postprocess.load_json(json_path)
                except Exception as e:
                    self._whisperx_data = None
                    self._log_queue.put(f"[Warning] Could not parse JSON: {e}\n")
                QTimer.singleShot(0, self._on_success)
            else:
                QTimer.singleShot(0, self._on_failure)

        self._job = TranscriptionJob(
            audio_path=self._audio_path,
            output_dir=self._output_dir,
            hf_token=hf_token,
            model=self._model_combo.currentText(),
            num_speakers=self._speaker_spin.value(),
            on_line=on_line,
            on_done=on_done,
        )
        self._job.start()

    def _stop(self):
        if self._job:
            self._job.cancel()
        self._set_status("Stopped", "#666")
        self._run_btn.setEnabled(True)

    def _on_success(self):
        self._set_status("Complete", "#4CD389")
        self._run_btn.setEnabled(True)
        if self._whisperx_data:
            self._populate_review()
            self._tabs.setCurrentIndex(2)

    def _on_failure(self):
        self._set_status("Error — see log", "#e74c3c")
        self._run_btn.setEnabled(True)

    # ── Speaker Review actions ────────────────────────────────────────────────

    def _llm_suggest(self):
        claude_key = config.get_claude_token()
        if not claude_key:
            QMessageBox.warning(
                self, "Claude API key missing",
                "Please save your Claude API key in the Settings tab to use auto-suggest.",
            )
            self._tabs.setCurrentIndex(3)
            return
        if not self._whisperx_data:
            QMessageBox.warning(self, "No data", "Run a transcription first.")
            return

        char_names = [
            e.text().strip() or f"Character {i+1}"
            for i, e in enumerate(self._char_entries)
        ]
        samples = postprocess.get_speaker_samples(self._whisperx_data)

        self._llm_btn.setEnabled(False)
        self._llm_btn.setText("Thinking…")

        def _run():
            try:
                from llm_mapper import suggest_mapping
                mapping = suggest_mapping(samples, char_names, claude_key)
                QTimer.singleShot(0, lambda: self._apply_llm_suggestion(mapping))
            except Exception as e:
                err = str(e)
                QTimer.singleShot(
                    0, lambda: QMessageBox.critical(self, "Claude error", f"Auto-suggest failed:\n{err}")
                )
            finally:
                def _restore():
                    self._llm_btn.setEnabled(True)
                    self._llm_btn.setText("✨  Auto-suggest (Claude)")
                QTimer.singleShot(0, _restore)

        threading.Thread(target=_run, daemon=True).start()

    def _apply_llm_suggestion(self, mapping: dict):
        for sp, name in mapping.items():
            if sp in self._speaker_combos:
                combo = self._speaker_combos[sp]
                idx = combo.findText(name)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
                else:
                    combo.addItem(name)
                    combo.setCurrentText(name)

    def _apply_mapping(self):
        if not self._json_path or not self._whisperx_data:
            QMessageBox.warning(self, "No data", "Run a transcription first.")
            return
        if not self._speaker_combos:
            QMessageBox.warning(self, "No mapping", "No speaker mapping to apply.")
            return

        mapping = {sp: combo.currentText() for sp, combo in self._speaker_combos.items()}
        try:
            txt_path, srt_path = postprocess.save_all(
                self._json_path, mapping, self._output_dir
            )
            QMessageBox.information(
                self, "Saved",
                f"Transcript saved:\n  {txt_path.name}\n  {srt_path.name}"
                f"\n\nFolder: {txt_path.parent}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Save error", str(e))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _separator(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #3B3B50;")
        return line

    def _prompt_missing_hf_token(self):
        reply = QMessageBox.question(
            self,
            "HuggingFace token not set",
            "No HuggingFace token found.\n\n"
            "Speaker diarization requires a free token.\n"
            "Go to Settings now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._tabs.setCurrentIndex(3)
