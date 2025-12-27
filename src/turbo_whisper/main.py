"""Main application entry point for Turbo Whisper."""

import sys
import threading

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .api import WhisperAPIError, WhisperClient
from .config import Config
from .hotkey import HotkeyManager
from .recorder import AudioRecorder
from .typer import Typer
from .waveform import WaveformWidget


class SignalBridge(QObject):
    """Bridge for thread-safe Qt signals."""

    toggle_recording = pyqtSignal()
    update_waveform = pyqtSignal(float, list)
    transcription_complete = pyqtSignal(str)
    transcription_error = pyqtSignal(str)
    show_status = pyqtSignal(str)


class RecordingWindow(QWidget):
    """Floating window showing waveform during recording."""

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the recording window UI."""
        # Frameless, always on top, floating window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        # Main container with rounded corners
        container = QWidget(self)
        container.setObjectName("container")
        container.setStyleSheet(f"""
            #container {{
                background-color: {self.config.background_color};
                border-radius: 12px;
                border: 1px solid #333;
            }}
        """)

        # Layout
        layout = QVBoxLayout(container)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(8)

        # Waveform
        self.waveform = WaveformWidget(
            color=self.config.waveform_color,
            bg_color=self.config.background_color,
        )
        layout.addWidget(self.waveform)

        # Status row
        status_layout = QHBoxLayout()
        status_layout.setContentsMargins(0, 0, 0, 0)

        self.status_label = QLabel("Press Alt+Space to stop")
        self.status_label.setStyleSheet("""
            color: #888;
            font-size: 11px;
        """)
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        # Hint labels
        hints = QLabel("Stop: Alt+Space  |  Cancel: Esc")
        hints.setStyleSheet("""
            color: #666;
            font-size: 10px;
        """)
        status_layout.addWidget(hints)

        layout.addLayout(status_layout)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

        # Size
        self.setFixedSize(self.config.window_width, self.config.window_height)

    def set_status(self, text: str) -> None:
        """Update status label."""
        self.status_label.setText(text)

    def center_on_screen(self) -> None:
        """Center window on the screen."""
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = int(screen.height() * 0.3)  # Upper third of screen
        self.move(x, y)


class TurboWhisper:
    """Main application class."""

    def __init__(self):
        self.config = Config.load()
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)

        # Components
        self.recorder = AudioRecorder(self.config)
        self.client = WhisperClient(self.config)
        self.typer = Typer()
        self.signals = SignalBridge()

        # UI
        self.window = RecordingWindow(self.config)
        self._setup_tray()

        # State
        self.is_recording = False

        # Connect signals
        self.signals.toggle_recording.connect(self._toggle_recording)
        self.signals.update_waveform.connect(self._on_waveform_update)
        self.signals.transcription_complete.connect(self._on_transcription_complete)
        self.signals.transcription_error.connect(self._on_transcription_error)
        self.signals.show_status.connect(self.window.set_status)

        # Hotkey
        self.hotkey_manager = HotkeyManager(
            self.config.hotkey,
            lambda: self.signals.toggle_recording.emit(),
        )

    def _setup_tray(self) -> None:
        """Set up system tray icon."""
        self.tray = QSystemTrayIcon(self.app)

        # Create simple icon (will use default if no icon available)
        self.tray.setIcon(QIcon.fromTheme("audio-input-microphone"))
        self.tray.setToolTip("Turbo Whisper - Press Alt+Space to dictate")

        # Context menu
        menu = QMenu()

        self.toggle_action = QAction("Start Recording", menu)
        self.toggle_action.triggered.connect(self._toggle_recording)
        menu.addAction(self.toggle_action)

        menu.addSeparator()

        settings_action = QAction("Settings...", menu)
        settings_action.setEnabled(False)  # TODO: Implement settings UI
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.show()

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

        self.is_recording = True
        self.toggle_action.setText("Stop Recording")

        # Show window
        self.window.waveform.set_recording(True)
        self.window.set_status("Listening...")
        self.window.center_on_screen()
        self.window.show()

        # Start recording
        self.recorder.start(level_callback=self._on_audio_level)

    def _stop_recording(self) -> None:
        """Stop recording and transcribe."""
        if not self.is_recording:
            return

        self.is_recording = False
        self.toggle_action.setText("Start Recording")

        # Update UI
        self.window.waveform.set_recording(False)
        self.window.set_status("Processing...")

        # Stop recording and get audio
        audio_data = self.recorder.stop()

        # Transcribe in background thread
        def transcribe():
            try:
                text = self.client.transcribe_sync(audio_data)
                self.signals.transcription_complete.emit(text)
            except WhisperAPIError as e:
                self.signals.transcription_error.emit(str(e))

        threading.Thread(target=transcribe, daemon=True).start()

    def _on_audio_level(self, level: float, waveform_buffer: list[float]) -> None:
        """Handle audio level update from recorder."""
        self.signals.update_waveform.emit(level, waveform_buffer)

    def _on_waveform_update(self, level: float, waveform_buffer: list[float]) -> None:
        """Update waveform display."""
        self.window.waveform.update_waveform(level, waveform_buffer)

    def _on_transcription_complete(self, text: str) -> None:
        """Handle completed transcription."""
        self.window.hide()

        if text:
            # Copy to clipboard
            if self.config.copy_to_clipboard:
                self.typer.copy_to_clipboard(text)

            # Type into focused window
            if self.config.auto_paste:
                self.typer.type_text(text)

            self.tray.showMessage(
                "Turbo Whisper",
                f"Transcribed: {text[:50]}..." if len(text) > 50 else f"Transcribed: {text}",
                QSystemTrayIcon.MessageIcon.Information,
                2000,
            )
        else:
            self.tray.showMessage(
                "Turbo Whisper",
                "No speech detected",
                QSystemTrayIcon.MessageIcon.Warning,
                2000,
            )

    def _on_transcription_error(self, error: str) -> None:
        """Handle transcription error."""
        self.window.hide()
        self.tray.showMessage(
            "Turbo Whisper - Error",
            error,
            QSystemTrayIcon.MessageIcon.Critical,
            3000,
        )

    def _quit(self) -> None:
        """Clean up and quit application."""
        self.hotkey_manager.stop()
        self.recorder.cleanup()
        self.app.quit()

    def run(self) -> int:
        """Run the application."""
        self.hotkey_manager.start()

        self.tray.showMessage(
            "Turbo Whisper",
            "Press Alt+Space to start dictating",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

        return self.app.exec()


def main():
    """Application entry point."""
    app = TurboWhisper()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
