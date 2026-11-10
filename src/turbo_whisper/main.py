"""Main application entry point for Turbo Whisper."""

import errno
import os
import subprocess
import sys
import tempfile
import threading
import time
import uuid

# Platform-specific imports for single-instance locking
if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QWidget,
)

from .api import WhisperAPIError, WhisperClient
from .config import Config
from .hotkey import create_hotkey_manager
from .icons import (
    get_check_icon,
    get_copy_icon,
    get_eye_icon,
    get_eye_off_icon,
    get_play_icon,
    get_stop_icon,
    get_tray_icon,
)
from .recorder import AudioRecorder
from .sessions import DictationSession, SerialWorker
from .typer import Typer
from .window import WindowDetector


class SignalBridge(QObject):
    """Bridge for thread-safe Qt signals."""

    toggle_recording = pyqtSignal()
    recording_requested = pyqtSignal(bool)
    hotkey_status = pyqtSignal(str)
    focused_window_detected = pyqtSignal(str, int)
    update_waveform = pyqtSignal(float, list)
    transcription_complete = pyqtSignal(str, int)
    transcription_error = pyqtSignal(str, int)
    live_complete = pyqtSignal(str, int)
    live_error = pyqtSignal(str, int)
    show_status = pyqtSignal(str)
    session_status = pyqtSignal(str, int)
    review_applied = pyqtSignal(str, str, str)
    writer_notice = pyqtSignal(str)


class RecordingWindow(QWidget):
    """Floating window showing waveform during recording."""

    # Signal emitted when ESC is pressed to cancel
    cancel_requested = pyqtSignal()

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._drag_pos = None  # For dragging support
        self._setup_ui()

        # Timer to refresh Claude status while settings panel is open
        self._claude_status_timer = QTimer()
        self._claude_status_timer.timeout.connect(self._update_claude_status)
        self._claude_status_timer.setInterval(1000)  # Update every second

    record_requested = pyqtSignal()
    settings_saved = pyqtSignal()
    open_writer_requested = pyqtSignal()
    review_requested = pyqtSignal(str, str)

    def _refresh_reviews(self):
        previous = self.review_list.currentItem()
        identifier = previous.data(Qt.ItemDataRole.UserRole) if previous else None
        self.review_list.blockSignals(True)
        self.review_list.clear()
        for entry in self.config.history:
            review = entry.get("dictation_review") if isinstance(entry, dict) else None
            if review:
                item = QListWidgetItem(
                    f"{entry['timestamp'][:19].replace('T', ' ')} · {review['status']}"
                )
                item.setData(Qt.ItemDataRole.UserRole, review["writer_id"])
                self.review_list.addItem(item)
        self.review_list.blockSignals(False)
        index = next(
            (
                i
                for i in range(self.review_list.count())
                if self.review_list.item(i).data(Qt.ItemDataRole.UserRole) == identifier
            ),
            0,
        )
        self.review_list.setCurrentRow(index)
        if not self.review_list.count():
            self.review_apply_btn.setEnabled(False)

    def _selected_review(self):
        item = self.review_list.currentItem()
        identifier = item.data(Qt.ItemDataRole.UserRole) if item else None
        return next(
            (
                entry
                for entry in self.config.history
                if isinstance(entry, dict)
                and entry.get("dictation_review", {}).get("writer_id") == identifier
            ),
            None,
        )

    def _select_review(self, index):
        entry = self._selected_review()
        self.review_apply_btn.setEnabled(entry is not None)
        if entry:
            review = entry["dictation_review"]
            self.review_original.setPlainText(review["source_text"])
            self.review_text.setPlainText(review.get("proposed_text") or entry["text"])
            self.review_feedback.setText(review["message"])

    def _request_review_apply(self):
        entry = self._selected_review()
        if entry and self.review_text.toPlainText().strip():
            self.review_apply_btn.setEnabled(False)
            self.review_requested.emit(
                entry["dictation_review"]["writer_id"], self.review_text.toPlainText()
            )

    def _setup_ui(self) -> None:
        from .ui import build_windows

        build_windows(self)

    def update_icon(self, recording: bool) -> None:
        """Update window icon based on recording state."""
        self.setWindowIcon(get_tray_icon(128, recording=recording))

    def keyPressEvent(self, event) -> None:
        """Handle key presses - ESC cancels recording."""
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_requested.emit()
        else:
            super().keyPressEvent(event)

    def set_status(self, text: str, animate: bool = False) -> None:
        """Update status label."""
        self._base_status = text
        self._status_dots = 0
        self.status_label.setText(text)
        if animate:
            self._status_timer.start()
        else:
            self._status_timer.stop()

    def set_recording_hint(self, recording: bool) -> None:
        """Update hint text based on recording state."""
        action = "Stop" if recording else "Start"
        self.hints_label.setText(f"{action}: {self._hotkey_str}")

    def update_mic_level(self, level: float) -> None:
        """Update the mic level display in sensitivity slider (0.0 to 1.0 scale)."""
        # Only update if level changed significantly (reduces stylesheet updates)
        if abs(level - self._current_mic_level) > 0.01 or level == 0:
            self._current_mic_level = level
            self._update_sensitivity_style()

    def _animate_status(self) -> None:
        """Animate the status text with dots."""
        self._status_dots = (self._status_dots + 1) % 4
        dots = "." * self._status_dots
        self.status_label.setText(f"{self._base_status}{dots}")

    def _toggle_settings(self) -> None:
        if self.settings_panel.isVisible():
            self.settings_panel.hide()
            self._claude_status_timer.stop()
        else:
            self.hide()
            self.settings_panel.show()
            self.settings_panel.raise_()
            self.settings_panel.activateWindow()
            self._claude_status_timer.start()

    def _update_api_key_display(self) -> None:
        self.api_key_input.setEchoMode(
            QLineEdit.EchoMode.Normal if self._key_visible else QLineEdit.EchoMode.Password
        )

    def _on_api_key_changed(self, text: str) -> None:
        self._actual_api_key = text

    def _toggle_key_visibility(self) -> None:
        self._key_visible = not self._key_visible
        self._update_api_key_display()
        self.key_visible_btn.setIcon(
            get_eye_off_icon(16, "#bcb7c7") if self._key_visible else get_eye_icon(16, "#bcb7c7")
        )

    def _copy_to_clipboard(self, text: str, button: QPushButton = None) -> None:
        """Copy text to clipboard and show feedback on button."""
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

        # Show "Copied" feedback on button if provided
        if button:
            original_icon = button.icon()
            button.setIcon(get_check_icon(16, "#84cc16"))
            QTimer.singleShot(1500, lambda: button.setIcon(original_icon))

    def _on_sensitivity_changed(self, value: int) -> None:
        """Handle gain slider change - update in real-time with 20% snapping."""
        self.waveform.sensitivity = value
        self.gain_value_label.setText(f"{value}%")
        self._update_sensitivity_style()

    def _update_sensitivity_style(self) -> None:
        # Palette is owned by the theme; no per-frame stylesheet regeneration.
        pass

    def _populate_mic_dropdown(self) -> None:
        """Populate the microphone dropdown with available devices."""
        import sys

        from .recorder import get_pipewire_sources

        self.mic_combo.clear()
        self.mic_combo.addItem("System Default", None)

        # Get input devices - use PipeWire on Linux, PyAudio elsewhere
        if sys.platform.startswith("linux"):
            pw_sources = get_pipewire_sources()
            if pw_sources:
                for src in pw_sources:
                    idx = src["id"]  # PipeWire source ID
                    name = src["description"]
                    display = f"{name} (48000Hz)"
                    self.mic_combo.addItem(display, idx)
                saved = self.mic_combo.findData(self.config.input_device_index)
                if saved >= 0:
                    self.mic_combo.setCurrentIndex(saved)
                return

        # Fallback to PyAudio device enumeration
        import pyaudio

        try:
            audio = pyaudio.PyAudio()
            for i in range(audio.get_device_count()):
                try:
                    info = audio.get_device_info_by_index(i)
                    if info["maxInputChannels"] > 0 and info["maxOutputChannels"] == 0:
                        name = info["name"]
                        rate = int(info["defaultSampleRate"])
                        self.mic_combo.addItem(f"{name} ({rate}Hz)", i)
                except Exception:
                    pass
            audio.terminate()
        except Exception as e:
            print(f"Could not enumerate audio devices: {e}")

        # Select the saved device
        if self.config.input_device_index is not None:
            for i in range(self.mic_combo.count()):
                if self.mic_combo.itemData(i) == self.config.input_device_index:
                    self.mic_combo.setCurrentIndex(i)
                    break

    def _save_settings(self) -> None:
        from urllib.parse import urlparse

        endpoint = self.api_url_input.text().strip()
        parsed = urlparse(endpoint)
        keys = [key.strip().lower() for key in self.hotkey_input.text().split("+") if key.strip()]
        allowed = {
            "ctrl",
            "ctrl_l",
            "ctrl_r",
            "alt",
            "alt_l",
            "alt_r",
            "shift",
            "shift_l",
            "shift_r",
            "cmd",
            "super",
            "space",
            "enter",
            "tab",
            "esc",
            "backspace",
        }

        def valid_key(key):
            return (
                key in allowed
                or (len(key) == 1 and key.isascii() and key.isalnum())
                or key in {f"f{i}" for i in range(1, 13)}
            )

        backend = self.backend_combo.currentData()
        if backend == "api" and (parsed.scheme not in {"http", "https"} or not parsed.netloc):
            self.save_feedback.setText("Enter a valid HTTP or HTTPS endpoint.")
            return
        if not keys or not all(valid_key(key) for key in keys):
            self.save_feedback.setText("Enter a supported shortcut, such as ctrl+alt+w.")
            return
        if backend == "api" and not self.model_input.text().strip():
            self.save_feedback.setText("Enter a model name.")
            return
        if backend == "local" and not self.local_model_input.text().strip():
            self.save_feedback.setText("Enter a local model name or folder.")
            return
        device = self.local_device_combo.currentData()
        precision = self.local_compute_combo.currentData()
        if backend == "local" and device == "cpu" and precision in {"float16", "int8_float16"}:
            self.save_feedback.setText("Use int8, float32, or default precision on CPU.")
            return
        if backend == "whisper_cpp":
            from pathlib import Path

            if not self.cpp_binary_input.text().strip():
                self.save_feedback.setText("Enter the whisper-cli executable name or path.")
                return
            if (
                not self.cpp_model_input.text().strip()
                or not Path(self.cpp_model_input.text().strip()).expanduser().is_file()
            ):
                self.save_feedback.setText("Choose an existing whisper.cpp model file.")
                return
        if self.writer_checkbox.isChecked():
            from .polish import local_endpoint

            try:
                local_endpoint(self.polish_url_input.text().strip())
            except ValueError as error:
                self.save_feedback.setText(str(error))
                return
            if not self.polish_model_input.text().strip():
                self.save_feedback.setText("Choose an existing local correction model.")
                return
        self.config.writer_polish = self.writer_checkbox.isChecked()
        self.config.polish_url = self.polish_url_input.text().strip()
        self.config.polish_model = self.polish_model_input.text().strip()
        self.config.transcription_backend = backend
        self.config.whisper_cpp_binary = self.cpp_binary_input.text().strip()
        self.config.whisper_cpp_model = self.cpp_model_input.text().strip()
        self.config.whisper_cpp_device = self.cpp_device_input.value()
        self.config.whisper_cpp_timeout = self.cpp_timeout_input.value()
        self.config.whisper_cpp_use_gpu = self.cpp_use_gpu_checkbox.isChecked()
        self.config.whisper_cpp_require_gpu = self.cpp_require_gpu_checkbox.isChecked()
        self.config.local_model = self.local_model_input.text().strip()
        self.config.local_device = device
        self.config.local_compute_type = precision
        self.config.local_files_only = self.local_files_checkbox.isChecked()
        self.config.api_url = endpoint
        self.config.api_key = self.api_key_input.text()
        self.config.api_model = self.model_input.text().strip()
        self.config.language = self.language_input.text().strip()
        self.config.transcription_timeout = self.timeout_input.value()
        self.config.hotkey = keys
        self.config.push_to_talk = self.hold_checkbox.isChecked()
        self.config.auto_paste = self.paste_checkbox.isChecked()
        self.config.live_transcription = self.live_checkbox.isChecked()
        self.config.copy_to_clipboard = self.clipboard_checkbox.isChecked()
        self.config.store_recordings = self.recordings_checkbox.isChecked()
        self.config.input_device_index = self.mic_combo.currentData()
        self.config.input_device_name = self.mic_combo.currentText()
        self.config.save()
        self._hotkey_str = "+".join(k.title() for k in keys)
        self.set_recording_hint(False)
        self.settings_saved.emit()
        self.save_feedback.setText("Changes saved")
        QTimer.singleShot(2000, lambda: self.save_feedback.setText(""))

    def _update_claude_status(self) -> None:
        """Update the Claude integration status indicator."""
        if not self.config.claude_integration:
            self.claude_status.setText("Ready to dictate")
            self.claude_status.setStyleSheet("color: #666; font-size: 11px;")
            return

        # Check integration server status - simple Ready/Busy display
        try:
            import json
            import urllib.request

            req = urllib.request.Request(
                f"http://127.0.0.1:{self.config.claude_integration_port}/status",
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                data = json.loads(resp.read().decode())
                age = data.get("last_signal_age", 999)
                # Ready if signal within last 30 seconds (matches typing logic)
                if age < 30:
                    self.claude_status.setText("Ready")
                    self.claude_status.setStyleSheet("color: #84cc16; font-size: 11px;")
                else:
                    self.claude_status.setText("Busy")
                    self.claude_status.setStyleSheet("color: #f59e0b; font-size: 11px;")
        except Exception:
            self.claude_status.setText("Server error")
            self.claude_status.setStyleSheet("color: #f59e0b; font-size: 11px;")

    def _refresh_history(self) -> None:
        """Refresh the history list from config."""
        self.history_list.clear()
        self.history_empty.setVisible(not self.config.history)
        for entry in self.config.history:
            # Handle both old (string) and new (dict) formats
            if isinstance(entry, dict):
                text = entry.get("text", "")
                timestamp = entry.get("timestamp", "")
                audio_file = entry.get("audio_file", "")
            else:
                text = entry
                timestamp = ""
                audio_file = ""

            # Format timestamp for display (date and time)
            time_str = ""
            if timestamp:
                try:
                    from datetime import datetime

                    dt = datetime.fromisoformat(timestamp)
                    time_str = dt.strftime("%b %d %H:%M") + " "  # "Dec 30 14:35"
                except ValueError:
                    pass

            # Create custom widget for this entry
            widget = QWidget()
            layout = QHBoxLayout(widget)
            layout.setContentsMargins(4, 2, 4, 2)
            layout.setSpacing(4)

            # Text label (truncated)
            display = text[:40] + "..." if len(text) > 40 else text
            display = f"{time_str}{display}"
            label = QLabel(display)
            label.setTextFormat(Qt.TextFormat.PlainText)
            label.setStyleSheet("color: #ddd8e5; font-size: 13px;")
            label.setToolTip(text)  # Full text on hover
            layout.addWidget(label, stretch=1)

            # Copy button
            copy_btn = QPushButton()
            copy_btn.setIcon(get_copy_icon(14, "#888"))
            copy_btn.setFixedSize(34, 34)
            copy_btn.setToolTip("Copy to clipboard")
            copy_btn.setStyleSheet(
                """
                QPushButton {
                    background: transparent;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: rgba(185, 160, 237, 0.2);
                }
            """
            )
            copy_btn.clicked.connect(lambda checked, t=text: self._copy_history_item(t))
            layout.addWidget(copy_btn)

            # Play button (only if audio file exists)
            if audio_file:
                play_btn = QPushButton()
                play_btn.setIcon(get_play_icon(14, "#888"))
                play_btn.setFixedSize(34, 34)
                play_btn.setToolTip("Play recording")
                play_btn.setStyleSheet(
                    """
                    QPushButton {
                        background: transparent;
                        border: none;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background: rgba(185, 160, 237, 0.2);
                    }
                """
                )
                play_btn.clicked.connect(
                    lambda checked, f=audio_file, b=play_btn: self._play_audio(f, b)
                )
                layout.addWidget(play_btn)

            # Add item to list
            item = QListWidgetItem()
            item.setSizeHint(widget.sizeHint())
            self.history_list.addItem(item)
            self.history_list.setItemWidget(item, widget)

    def _copy_history_item(self, text: str) -> None:
        """Copy a history item to clipboard."""
        self._copy_to_clipboard(text)
        # Show brief status update
        self.set_status("Copied!")

    def _play_audio(self, filename: str, button: QPushButton) -> None:
        """Play or stop an audio recording."""
        from PyQt6.QtCore import QUrl
        from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer

        # If already playing this file, stop it
        if hasattr(self, "_playing_button") and self._playing_button == button:
            self._media_player.stop()
            button.setIcon(get_play_icon(14, "#888"))
            button.setToolTip("Play recording")
            self._playing_button = None
            return

        audio_path = self.config.get_recordings_dir() / filename
        if not audio_path.exists():
            self.set_status("Audio file not found")
            return

        # Create or reuse media player
        if not hasattr(self, "_media_player"):
            self._media_player = QMediaPlayer()
            self._audio_output = QAudioOutput()
            self._media_player.setAudioOutput(self._audio_output)
            # Connect to playback state changes
            self._media_player.playbackStateChanged.connect(self._on_playback_state_changed)

        # Stop any current playback and reset previous button
        if hasattr(self, "_playing_button") and self._playing_button:
            self._playing_button.setIcon(get_play_icon(14, "#888"))
            self._playing_button.setToolTip("Play recording")
        self._media_player.stop()

        # Update button to stop icon
        button.setIcon(get_stop_icon(14, "#888"))
        button.setToolTip("Stop playback")
        self._playing_button = button

        # Play the file
        self._media_player.setSource(QUrl.fromLocalFile(str(audio_path)))
        self._audio_output.setVolume(1.0)
        self._media_player.play()

    def _on_playback_state_changed(self, state) -> None:
        """Handle media player state changes."""
        from PyQt6.QtMultimedia import QMediaPlayer

        if state == QMediaPlayer.PlaybackState.StoppedState:
            # Reset button icon when playback stops
            if hasattr(self, "_playing_button") and self._playing_button:
                self._playing_button.setIcon(get_play_icon(14, "#888"))
                self._playing_button.setToolTip("Play recording")
                self._playing_button = None

    def _close_window(self) -> None:
        """Close the window (emits cancel if recording)."""
        self.cancel_requested.emit()
        self.hide()

    def center_on_screen(self) -> None:
        """Center window on the screen."""
        from PyQt6.QtGui import QCursor

        screen = (
            QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
        ).availableGeometry()
        x = screen.x() + (screen.width() - self.width()) // 2
        y = screen.y() + screen.height() - self.height() - 36
        self.move(x, y)

    def mousePressEvent(self, event) -> None:
        """Handle mouse press for dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            # Use startSystemMove for Wayland compatibility
            if hasattr(self.windowHandle(), "startSystemMove"):
                self.windowHandle().startSystemMove()
            else:
                # Fallback for X11
                self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event) -> None:
        """Handle mouse move for dragging (X11 fallback)."""
        if event.buttons() == Qt.MouseButton.LeftButton and self._drag_pos is not None:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:
        """Handle mouse release."""
        self._drag_pos = None


class TurboWhisper:
    """Main application class."""

    def __init__(self):
        self.config = Config.load()
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setDesktopFileName("turbo-whisper")
        self.app.setWindowIcon(get_tray_icon(128, recording=False))  # Orange when idle

        # Components
        self.recorder = AudioRecorder(self.config)
        self.client = WhisperClient(self.config)
        self.window_detector = WindowDetector()
        self.typer = Typer(typing_delay_ms=self.config.typing_delay_ms)
        self.signals = SignalBridge()

        # UI
        self.window = RecordingWindow(self.config)
        self._setup_tray()

        # State
        self.is_recording = False
        self.is_transcribing = False
        self._recording_token = 0
        self._pending_waveform_data = None  # Thread-safe buffer for waveform data
        self._live_session = None
        self._live_token = 0
        self._live_text = []
        self._live_remainder = []
        self._live_delivery_lock = threading.Lock()
        self._sessions = {}
        self._active_session = None
        self._work_queue = SerialWorker()
        from .writer import WriterBridge

        self.writer = WriterBridge(self.config.writer_python, self.config.writer_binary)

        # Connect signals
        self.signals.toggle_recording.connect(self._toggle_recording)
        self.signals.recording_requested.connect(self._set_recording_state)
        self.signals.focused_window_detected.connect(self._on_focused_window_detected)
        self.signals.transcription_complete.connect(self._on_live_complete)
        self.signals.transcription_error.connect(self._on_live_error)
        self.signals.live_complete.connect(self._on_live_complete)
        self.signals.live_error.connect(self._on_live_error)
        self.signals.show_status.connect(self.window.set_status)
        self.window.cancel_requested.connect(self._cancel_recording)
        self.window.record_requested.connect(self._toggle_recording)
        self.window.settings_saved.connect(self._reload_hotkey)
        self.signals.hotkey_status.connect(self.window.hotkey_status.setText)
        self.signals.session_status.connect(self._on_session_status)
        self.signals.review_applied.connect(self._on_review_applied)
        self.signals.writer_notice.connect(self.window.review_feedback.setText)
        self.window.open_writer_requested.connect(self._open_writer)
        self.window.review_requested.connect(self._apply_review)

        # Timer to poll waveform data from recorder thread (avoids cross-thread signal issues)
        self._waveform_timer = QTimer()
        self._waveform_timer.timeout.connect(self._poll_waveform_data)
        self._waveform_timer.setInterval(30)  # Poll at ~33 FPS

        self.hotkey_manager = None
        self._setup_activation_server()

        # Integration server for Claude Code
        self.integration_server = None
        if self.config.claude_integration:
            from .integration_server import IntegrationServer

            self.integration_server = IntegrationServer(self.config.claude_integration_port)
            if not self.integration_server.start():
                self.integration_server = None

    def _setup_activation_server(self):
        from PyQt6.QtNetwork import QLocalServer

        self._activation_server = QLocalServer(self.app)
        self._activation_server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        QLocalServer.removeServer(_activation_name())
        if not self._activation_server.listen(_activation_name()):
            print("Could not register window activation; the application is still usable.")
            return
        self._activation_server.newConnection.connect(self._activate_from_launcher)

    def _activate_from_launcher(self):
        socket = self._activation_server.nextPendingConnection()
        self._show_settings()
        if socket:
            socket.write(b"activated\n")
            socket.flush()
            socket.disconnectFromServer()
            socket.deleteLater()

    def _setup_tray(self) -> None:
        """Set up system tray icon."""
        self.tray = QSystemTrayIcon(self.app)

        # Create simple icon (will use default if no icon available)
        self.tray.setIcon(get_tray_icon(64, recording=False))  # Orange when idle
        hotkey_str = "+".join(k.capitalize() for k in self.config.hotkey)
        self.tray.setToolTip(f"Turbo Whisper - Press {hotkey_str} to dictate")

        # Context menu
        menu = QMenu()

        show_action = QAction("Show Window", menu)
        show_action.triggered.connect(self._show_window)
        menu.addAction(show_action)

        self.toggle_action = QAction("Start Recording", menu)
        self.toggle_action.triggered.connect(self._toggle_recording)
        menu.addAction(self.toggle_action)

        menu.addSeparator()

        settings_action = QAction("Settings...", menu)
        settings_action.triggered.connect(self._show_settings)
        menu.addAction(settings_action)
        review_action = QAction("Review dictation...", menu)
        review_action.triggered.connect(self._show_review)
        menu.addAction(review_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _reload_hotkey(self) -> None:
        if self.hotkey_manager:
            self.hotkey_manager.stop()
        self.hotkey_manager = create_hotkey_manager(
            self.config.hotkey,
            self._on_hotkey_activate,
            self._on_hotkey_deactivate if self.config.push_to_talk else None,
        )
        self.window.hotkey_status.setText(
            "Global shortcut unavailable. You can still use Start dictation."
        )
        if self.hotkey_manager:
            self.hotkey_manager.on_status = self.signals.hotkey_status.emit
            self.window.hotkey_status.setText("Shortcut ready.")
            try:
                self.hotkey_manager.start()
            except Exception as exc:
                self.hotkey_manager.stop()
                self.hotkey_manager = None
                print(f"Global shortcut unavailable: {exc}")

    def _set_recording_state(self, recording: bool) -> None:
        # Press/release events are queued in order onto the Qt thread, including short taps.
        if recording:
            self._start_recording()
        else:
            self._stop_recording()

    def _on_hotkey_activate(self) -> None:
        if self.config.push_to_talk:
            self.signals.recording_requested.emit(True)
        else:
            self.signals.toggle_recording.emit()

    def _on_hotkey_deactivate(self) -> None:
        if self.config.push_to_talk:
            self.signals.recording_requested.emit(False)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """Handle tray icon clicks."""
        # Trigger = left click, DoubleClick = double click
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._show_window()

    def _update_icons(self, recording: bool) -> None:
        """Update all icons based on recording state."""
        self.tray.setIcon(get_tray_icon(64, recording=recording))
        self.window.update_icon(recording=recording)

    def _save_wav(self, path, audio_data: bytes) -> None:
        """The recorder already returns a complete WAV, including its header."""
        path.write_bytes(audio_data)

    def _show_window(self) -> None:
        """Show the window without starting recording (doesn't steal focus)."""
        self.window.waveform.set_recording(self.is_recording)
        self.window.set_recording_hint(recording=self.is_recording)
        self._update_icons(recording=self.is_recording)
        if not self.is_recording:
            self.window.set_status(
                "Processing" if self.is_transcribing else "Ready", animate=self.is_transcribing
            )
        self.window.center_on_screen()
        self.window.show()
        self.window.raise_()
        # Note: Don't call activateWindow() - keeps focus in user's original app

    def _show_settings(self) -> None:
        """Show the window with settings panel expanded (takes focus for editing)."""
        self._show_window()
        # Expand settings if not already visible
        if not self.window.settings_panel.isVisible():
            self.window._toggle_settings()
        # Take focus so user can edit settings fields
        self.window.activateWindow()

    def _show_review(self):
        self._show_settings()
        self.window.navigation.setCurrentRow(4)

    def _toggle_recording(self) -> None:
        """Toggle recording state."""
        if self.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        """Start recording audio."""
        if self.is_recording:
            return
        if len(self._sessions) >= self._work_queue.capacity:
            self.window.set_status("Transcription queue full — wait for pending recordings")
            return
        if self.config.live_transcription and self.config.transcription_backend == "api":
            self._on_transcription_error("Select a local backend to use live phrases")
            return

        self.is_recording = True
        self.window.settings_panel.setEnabled(False)
        self._recording_token += 1
        current_token = self._recording_token
        self._live_token += 1
        self._live_text = []
        self._live_remainder = []
        session = DictationSession(
            self._live_token, self.config.auto_paste, self.config.copy_to_clipboard
        )
        self._sessions[session.token] = session
        self._active_session = session
        if self.config.writer_polish:
            session.writer_id = uuid.uuid4().hex
            session.writer_binding = self.writer.begin(session.writer_id)
            self.window.hints_label.setToolTip(
                "Dictating into LibreOffice Writer's active document"
            )
        self._live_text, self._live_remainder = session.texts, session.remainder

        # Find focused app on background thread to keep hotkey/UI responsive
        threading.Thread(
            target=self._detect_focused_window,
            args=(current_token,),
            daemon=True,
        ).start()

        self.toggle_action.setText("Stop Recording")
        self._update_icons(recording=True)

        # Show window (don't steal focus from current app)
        self.window.waveform.set_recording(True)
        self.window.set_recording_hint(recording=True)
        self.window.set_status("Starting microphone", animate=True)

        # Hide settings panel if open (it changes window focus behavior)
        if self.window.settings_panel.isVisible():
            self.window._toggle_settings()

        self.window.center_on_screen()
        self.window.show()
        self.window.raise_()

        # Start waveform polling timer
        self._pending_waveform_data = None
        self._waveform_timer.start()

        # Start recording
        try:
            if self.config.live_transcription:
                from .live import PhraseTranscriber

                token = self._live_token
                texts, remainder = self._live_text, self._live_remainder
                auto_paste = self.config.auto_paste
                self._live_session = PhraseTranscriber(
                    self.client,
                    self.config.sample_rate,
                    self.config.channels,
                    lambda text: self._deliver_live_phrase(
                        text, token, texts, remainder, auto_paste
                    ),
                    lambda text: self._finish_session(text, session),
                    lambda error: self.signals.live_error.emit(error, token),
                )
                session.worker = self._live_session
                self._live_session.start(self._work_queue)
                self.recorder.start(
                    level_callback=self._on_audio_level, frame_callback=self._live_session.feed
                )
            else:
                self.recorder.start(level_callback=self._on_audio_level)
        except Exception as exc:
            self._fail_session(f"Microphone unavailable: {exc}", session.token)

    def _detect_focused_window(self, token: int) -> None:
        """Background worker: detect and report focused window name."""
        try:
            name = self.window_detector.get_focused_window_name()
        except Exception as e:
            print(f"Window detection failed: {e}")
            return
        if name:
            self.signals.focused_window_detected.emit(name, token)

    def _on_focused_window_detected(self, name: str, token: int) -> None:
        """Show which app will receive dictation if still recording current session."""
        if self.is_recording and token == self._recording_token:
            if not self._active_session.writer_id:
                self.window.hints_label.setToolTip(f"Dictating into {name}")

    def _cancel_recording(self) -> None:
        """Cancel only active capture; older stopped sessions keep their results."""
        session = self._active_session
        if session is None:
            return
        session.cancel()
        self._retire_writer(session)
        self._sessions.pop(session.token, None)
        self._active_session = self._live_session = None
        self.is_recording = False
        self._recording_token += 1
        self._live_token += 1
        self.toggle_action.setText("Start Recording")
        self._update_icons(recording=False)
        self._waveform_timer.stop()
        try:
            self.recorder.stop()
        except RuntimeError as exc:
            self._on_transcription_error(str(exc))
        self.window.waveform.set_recording(False)
        self.window.set_recording_hint(recording=False)
        self._update_pending_state()

    def _retire_writer(self, session):
        if session.writer_id:

            def retire():
                try:
                    session.writer_binding.result(timeout=15)
                    self.writer.call(
                        "mark",
                        id=session.writer_id,
                        message="Recording ended — provisional words retained; edit in Writer",
                    )
                except Exception:
                    pass

            threading.Thread(target=retire, daemon=True).start()

    def _update_pending_state(self):
        pending = sum(session.stopped for session in self._sessions.values())
        self.is_transcribing = bool(pending)
        self.window.settings_panel.setEnabled(not self.is_recording and not pending)
        if self.is_recording:
            return
        if pending:
            self.window.set_status(f"Processing · {pending} pending", animate=True)
        else:
            self.window.hide()

    def _stop_recording(self) -> None:
        """Stop recording and transcribe."""
        session = self._active_session
        if session is None:
            return
        session.stopped = True
        self._active_session = None
        self._live_session = None
        self.is_recording = False
        self.is_transcribing = True
        self._recording_token += 1
        self.toggle_action.setText("Start Recording")
        self._update_icons(recording=False)

        # Stop waveform polling
        self._waveform_timer.stop()

        # Update UI
        self.window.waveform.set_recording(False)
        self.window.set_recording_hint(recording=False)
        self.window.set_status("Processing", animate=True)

        # Stop recording and get audio
        try:
            audio_data = self.recorder.stop()
        except Exception as exc:
            self._fail_session(f"Could not finish recording: {exc}", session.token)
            return
        if not audio_data:
            session.cancel()
            self._retire_writer(session)
            self._sessions.pop(session.token, None)
            self._update_pending_state()
            self.tray.showMessage(
                "Turbo Whisper",
                "No audio captured — ready for the next recording",
                QSystemTrayIcon.MessageIcon.Information,
                1500,
            )
            return

        # Save audio to file if configured
        audio_filename = None
        if self.config.store_recordings and audio_data:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            audio_filename = f"{timestamp}_{uuid.uuid4().hex}.wav"
            audio_path = self.config.get_recordings_dir() / audio_filename
            try:
                self._save_wav(audio_path, audio_data)
            except Exception as e:
                print(f"Warning: Could not save audio: {e}")
                audio_filename = None

        session.audio_filename = audio_filename

        if session.worker is not None:
            session.worker.finish()
            return

        # Transcribe in background thread
        def transcribe():
            try:
                text = self.client.transcribe_sync(audio_data)
                if text:
                    self._deliver_live_phrase(
                        text, session.token, session.texts, session.remainder, session.auto_paste
                    )
                self._finish_session(text, session)
            except WhisperAPIError as e:
                self.signals.transcription_error.emit(str(e), session.token)
            except Exception:
                self.signals.transcription_error.emit(
                    "The transcription could not finish. Try again.", session.token
                )

        session.future = self._work_queue.submit(transcribe)

    def _on_audio_level(self, level: float, waveform_buffer: list[float]) -> None:
        """Handle audio level update from recorder (called from recorder thread)."""
        # Store data for main thread to poll (thread-safe assignment)
        self._pending_waveform_data = (level, list(waveform_buffer))

    def _poll_waveform_data(self) -> None:
        """Poll waveform data from recorder thread (called from main thread timer)."""
        if self.is_recording and isinstance(self.recorder.capture_error, str):
            self._stop_recording()
            return
        if self._pending_waveform_data is not None:
            level, waveform_buffer = self._pending_waveform_data
            self.window.waveform.update_waveform(level, waveform_buffer)
            # Update mic level meter (scale 0-1 to 0-100, cap at 100)
            self.window.update_mic_level(level)
            frames = self.recorder.captured_frames
            if isinstance(frames, int) and frames:
                seconds = frames / self.config.sample_rate
                self.window.set_status(f"Listening · {seconds:.1f} s recorded")

    def _deliver_live_phrase(self, text, token, texts, remainder, auto_paste):
        # Run insertion on the serialized phrase worker, keeping the Qt thread
        # available for stop/cancel. Bind lists to this session, never the next one.
        with self._live_delivery_lock:
            session = self._sessions.get(token)
            if session is None or session.cancelled:
                return
            prefix = " " if texts else ""
            texts.append(text)
            if session.writer_id:
                try:
                    session.writer_binding.result(timeout=15)
                    if session.cancelled or self._sessions.get(token) is not session:
                        return
                    if remainder:
                        raise RuntimeError("Earlier insertion needs review")
                    self.writer.call("append", id=session.writer_id, text=prefix + text)
                except Exception:
                    remainder.append(text)
                return
            if auto_paste:
                try:
                    inserted = (
                        not remainder
                        and self._wait_for_claude_ready()
                        and self._sessions.get(token) is session
                        and not session.cancelled
                        and self.typer.type_text(prefix + text)
                    )
                except Exception:
                    inserted = False
                if not inserted:
                    remainder.append(text)

    def _finish_session(self, text, session):
        if session.cancelled or self._sessions.get(session.token) is not session:
            return
        if session.writer_id and text:
            from .polish import LocalPolisher, PolishResult

            self.signals.session_status.emit("Polishing full dictation", session.token)
            try:
                result = LocalPolisher(self.config.polish_url, self.config.polish_model).polish(
                    text, self.config.language
                )
            except Exception:
                result = PolishResult(
                    text, "review", "Correction unavailable — original text retained"
                )
            if session.cancelled or self._sessions.get(session.token) is not session:
                return
            source = text
            try:
                session.writer_binding.result(timeout=15)
                if session.remainder:
                    raise RuntimeError(
                        "Some text could not be inserted; full result retained in Review"
                    )
                if result.status == "review":
                    self.writer.call("mark", id=session.writer_id, message=result.message)
                else:
                    self.writer.call(
                        "replace",
                        id=session.writer_id,
                        text=result.text,
                        message=result.message if result.status == "incomplete" else "",
                    )
                    text = result.text
            except Exception as error:
                from .writer import WriterError

                result.status = "review"
                result.message = (
                    str(error)
                    if isinstance(error, (WriterError, RuntimeError))
                    else "Writer unavailable — result retained in Review"
                )
                try:
                    self.writer.call("mark", id=session.writer_id, message=result.message)
                except Exception:
                    pass
            session.review = {
                "writer_id": session.writer_id,
                "source_text": source,
                "status": result.status,
                "message": result.message,
                "incomplete_tail": result.incomplete_tail,
                "proposed_text": result.proposed_text or result.text,
            }
        elif session.writer_id:
            self._retire_writer(session)
        self.signals.transcription_complete.emit(text, session.token)

    def _on_session_status(self, message, token):
        if not self.is_recording and token in self._sessions:
            self.window.set_status(message, animate=True)

    def _open_writer(self):
        def open_document():
            try:
                self.writer.call("open")
                message = "Writer ready — place its caret and start dictation"
            except Exception:
                message = "Could not open Writer; check LibreOffice and Python UNO support"
            self.signals.writer_notice.emit(message)

        threading.Thread(target=open_document, daemon=True).start()

    def _apply_review(self, identifier, text):
        def apply():
            error = ""
            try:
                self.writer.call("replace", id=identifier, text=text, message="")
            except Exception as exception:
                from .writer import WriterError

                error = (
                    str(exception)
                    if isinstance(exception, WriterError)
                    else "Writer unavailable — reviewed text retained"
                )
            self.signals.review_applied.emit(identifier, text, error)

        threading.Thread(target=apply, daemon=True).start()

    def _on_review_applied(self, identifier, text, error):
        if not error:
            for entry in self.config.history:
                review = entry.get("dictation_review", {})
                if review.get("writer_id") == identifier:
                    entry["text"] = text
                    review.update(
                        status="reviewed",
                        message="Reviewed text applied to Writer",
                        incomplete_tail="",
                        proposed_text=text,
                    )
                    self.config.save()
                    self.window._refresh_history()
                    self.window._refresh_reviews()
                    break
        self.window.review_feedback.setText(error or "Reviewed text applied to Writer")
        self.window.review_apply_btn.setEnabled(True)

    def _on_live_complete(self, text: str, token: int) -> None:
        session = self._sessions.pop(token, None)
        if session is None or session.cancelled:
            return
        self._on_transcription_complete(text, session)

    def _fail_session(self, error, token):
        session = self._sessions.pop(token, None)
        if session is None:
            return
        session.cancel()
        self._retire_writer(session)
        if self._active_session is session:
            self._active_session = self._live_session = None
            self.is_recording = False
            self._waveform_timer.stop()
            self.window.waveform.set_recording(False)
            self.window.set_recording_hint(recording=False)
            self.toggle_action.setText("Start Recording")
            self._update_icons(recording=False)
            try:
                self.recorder.stop()
            except Exception:
                pass
        self._update_pending_state()
        self._on_transcription_error(error)

    def _on_live_error(self, error: str, token: int) -> None:
        session = self._sessions.get(token)
        if session is None:
            return
        if self._active_session is session:
            self._stop_recording()
        self._fail_session(error, token)

    def _is_claude_running(self) -> bool:
        """Check if Claude Code process is running."""
        try:
            result = subprocess.run(
                ["pgrep", "-x", "claude"],
                capture_output=True,
                timeout=1,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            return False

    def _wait_for_claude_ready(self) -> bool:
        """Wait for Claude to signal ready, with timeout.

        Returns True if ready signal received or Claude not running.
        Returns False if timed out waiting.
        """
        if not self.config.claude_integration or not self.integration_server:
            return True

        # Only wait if Claude is actually running
        if not self._is_claude_running():
            return True

        from .integration_server import IntegrationServer

        # Accept signal from last 30 seconds (covers recording + transcription time)
        if IntegrationServer.is_ready(max_age=30.0):
            IntegrationServer.reset_ready()
            return True

        # Otherwise wait for a new signal
        timeout = self.config.claude_wait_timeout
        start = time.time()
        while (time.time() - start) < timeout:
            if IntegrationServer.is_ready(max_age=1.0):
                IntegrationServer.reset_ready()
                return True
            time.sleep(0.1)
        return False

    def _on_transcription_complete(self, text: str, session: DictationSession) -> None:
        """Handle completed transcription."""
        self._update_pending_state()
        audio_filename = session.audio_filename

        if text:
            # Save to history (with audio file if available)
            self.config.add_to_history(text, audio_file=audio_filename, review=session.review)
            self.window._refresh_history()
            self.window._refresh_reviews()
            if session.review and not self.window.settings_panel.isVisible():
                self.window.review_list.setCurrentRow(0)

            # Copy to clipboard
            if session.copy_to_clipboard:
                self.typer.copy_to_clipboard(text)

            # Type into focused window (wait for Claude if running)
            if session.writer_id:
                self.tray.showMessage(
                    "Turbo Whisper",
                    session.review["message"],
                    QSystemTrayIcon.MessageIcon.Information,
                    3000,
                )
            elif session.worker is not None:
                if session.remainder:
                    self.typer.copy_to_clipboard(" ".join(session.remainder))
                self.tray.showMessage(
                    "Turbo Whisper",
                    (
                        "Remaining text copied — full transcript in History"
                        if session.remainder
                        else "Live dictation complete — saved in History"
                    ),
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )
            elif session.auto_paste:
                if session.remainder:
                    self.typer.copy_to_clipboard(text)
                self.tray.showMessage(
                    "Turbo Whisper",
                    ("Copied — press Ctrl+V to paste" if session.remainder else "Text inserted"),
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )
            else:
                self.tray.showMessage(
                    "Turbo Whisper",
                    f"Transcribed: {text[:50]}..." if len(text) > 50 else f"Transcribed: {text}",
                    QSystemTrayIcon.MessageIcon.Information,
                    2000,
                )
        else:
            # Transcription failed - delete saved audio if any
            if audio_filename:
                audio_path = self.config.get_recordings_dir() / audio_filename
                if audio_path.exists():
                    try:
                        audio_path.unlink()
                    except OSError:
                        pass
            self.tray.showMessage(
                "Turbo Whisper",
                "No speech detected",
                QSystemTrayIcon.MessageIcon.Warning,
                2000,
            )

    def _on_transcription_error(self, error: str) -> None:
        """Show errors without interrupting a newer active recording."""
        self.window.save_feedback.setText(error)
        if not self.is_recording and not self.is_transcribing:
            self.window.waveform.set_recording(False)
            self.window.set_status("Transcription failed")
            self.window.settings_panel.setEnabled(True)
            self.window.settings_panel.show()
        self.tray.showMessage(
            "Turbo Whisper - Error", error, QSystemTrayIcon.MessageIcon.Critical, 3000
        )

    def _quit(self) -> None:
        """Clean up and quit application."""
        if hasattr(self, "_activation_server"):
            self._activation_server.close()
        if self.hotkey_manager:
            self.hotkey_manager.stop()
        if self.integration_server:
            self.integration_server.stop()
        for session in self._sessions.values():
            session.cancel()
        self._sessions.clear()
        self._active_session = self._live_session = None
        self._work_queue.shutdown()
        self.writer.close()
        self.client.close()
        self.recorder.cleanup()
        self.window.settings_panel.close()
        self.app.quit()

    def run(self) -> int:
        """Run the application."""
        self._reload_hotkey()

        hotkey_str = "+".join(k.title() for k in self.config.hotkey)
        self.tray.showMessage(
            "Turbo Whisper",
            f"Press {hotkey_str} to start dictating",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

        return self.app.exec()


_lock_fd = None  # Global to keep lock file descriptor open
_activation_app = None


def _activation_name():
    import getpass
    import hashlib

    identity = str(os.getuid()) if hasattr(os, "getuid") else getpass.getuser()
    return "turbo-whisper-" + hashlib.sha256(identity.encode()).hexdigest()[:16]


def _activate_running_instance(timeout_ms=250):
    from PyQt6.QtNetwork import QLocalSocket

    global _activation_app
    # A relaunch can acquire the lock after the previous process exits. Keep a
    # QApplication, rather than a core-only dispatcher, available for that path.
    _activation_app = QApplication.instance() or QApplication(sys.argv[:1])
    socket = QLocalSocket()
    try:
        socket.connectToServer(_activation_name())
        if not socket.waitForConnected(timeout_ms):
            return False
        if not socket.bytesAvailable() and not socket.waitForReadyRead(timeout_ms):
            return False
        return bytes(socket.readAll()) == b"activated\n"
    finally:
        socket.close()


def ensure_single_instance():
    """Activate the owner, or wait briefly for its startup/shutdown lock race."""
    global _lock_fd

    if sys.platform == "win32":
        lock_path = os.path.join(tempfile.gettempdir(), "turbo-whisper.lock")
    else:
        lock_path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "turbo-whisper.lock")
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + 5
    while True:
        try:
            if sys.platform == "win32":
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            if error.errno not in (None, errno.EACCES, errno.EAGAIN):
                os.close(fd)
                raise
            if _activate_running_instance():
                os.close(fd)
                print("Opened the running Turbo Whisper window.")
                sys.exit(0)
            if time.monotonic() >= deadline:
                os.close(fd)
                print("Turbo Whisper is still starting or stopping. Please try again.")
                sys.exit(1)
            time.sleep(0.05)
            continue
        _lock_fd = fd
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        os.write(fd, str(os.getpid()).encode())
        return


def main():
    """Application entry point."""
    ensure_single_instance()
    app = TurboWhisper()
    if "--background" not in sys.argv:
        app._show_settings()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
