"""Main application entry point for Turbo Whisper."""

import fcntl
import os
import subprocess
import sys
import threading
import time

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSlider,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .api import WhisperAPIError, WhisperClient
from .config import Config
from .hotkey import create_hotkey_manager
from .icons import (
    get_check_icon,
    get_chevron_down_icon,
    get_chevron_up_icon,
    get_close_icon,
    get_copy_icon,
    get_eye_icon,
    get_eye_off_icon,
    get_play_icon,
    get_stop_icon,
    get_tray_icon,
)
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


class TickMarksWidget(QWidget):
    """Widget that draws tick mark notches for a slider."""

    def __init__(self, num_ticks: int = 11, parent=None):
        super().__init__(parent)
        self.num_ticks = num_ticks  # 0%, 20%, 40%... 200% = 11 ticks
        self.setFixedHeight(6)

    def paintEvent(self, event):
        from PyQt6.QtGui import QColor, QPainter, QPen

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor("#666"))
        pen.setWidth(1)
        painter.setPen(pen)

        width = self.width()
        # Account for slider handle padding (roughly 8px on each side)
        padding = 8
        usable_width = width - 2 * padding

        for i in range(self.num_ticks):
            x = padding + int(i * usable_width / (self.num_ticks - 1))
            # Draw shorter tick for non-100% marks, taller for 100% (middle)
            if i == 5:  # 100% mark (middle)
                painter.drawLine(x, 0, x, 5)
            else:
                painter.drawLine(x, 2, x, 5)

        painter.end()


class RecordingWindow(QWidget):
    """Floating window showing waveform during recording."""

    # Signal emitted when ESC is pressed to cancel
    cancel_requested = pyqtSignal()

    def __init__(self, config: Config):
        super().__init__()
        self.config = config
        self._drag_pos = None  # For dragging support
        self._setup_ui()

    def _setup_ui(self) -> None:
        """Set up the recording window UI."""
        # Set window icon for taskbar (orange = idle)
        self.setWindowIcon(get_tray_icon(128, recording=False))

        # Frameless, always on top, floating window that doesn't steal focus
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)  # Don't steal focus
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Never accept keyboard focus
        # Allow resize via mouse
        self._resize_edge = None

        # Main container with rounded corners and purple gradient
        container = QWidget(self)
        container.setObjectName("container")
        container.setStyleSheet(
            """
            #container {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:1,
                    stop:0 #2d1b4e,
                    stop:0.5 #1a1033,
                    stop:1 #0f0a1a
                );
                border-radius: 12px;
                border: 1px solid #4a3070;
            }
        """
        )

        # Use a stacked layout - waveform behind, controls on top
        from PyQt6.QtWidgets import QFrame

        # Container layout
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # Create a frame for the main content
        content_frame = QFrame()
        content_frame.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content_frame)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(4)
        container_layout.addWidget(content_frame)

        # Waveform - use the bright KnowAll lime green (#84cc16)
        self.waveform = WaveformWidget(
            color="#84cc16",  # Same bright green as buttons
            bg_color=self.config.background_color,
        )
        self.waveform.setMinimumHeight(160)  # Bigger orb
        layout.addWidget(self.waveform, stretch=2)  # Give it more priority

        # Status row - transparent background so orb shows through
        status_widget = QWidget()
        status_widget.setStyleSheet("background: transparent;")
        status_layout = QHBoxLayout(status_widget)
        status_layout.setContentsMargins(4, 0, 4, 0)

        self.status_label = QLabel("Listening...")
        self.status_label.setStyleSheet(
            """
            color: #888;
            font-size: 11px;
        """
        )
        status_layout.addWidget(self.status_label)

        status_layout.addStretch()

        # Hint label - show configured hotkey
        self._hotkey_str = "+".join(k.title() for k in self.config.hotkey)
        self.hints_label = QLabel(f"Start: {self._hotkey_str}")
        self.hints_label.setStyleSheet(
            """
            color: #666;
            font-size: 10px;
        """
        )
        status_layout.addWidget(self.hints_label)

        # Animated status timer
        self._status_dots = 0
        self._status_timer = QTimer()
        self._status_timer.timeout.connect(self._animate_status)
        self._status_timer.setInterval(400)

        layout.addWidget(status_widget)

        # More toggle button - chevron icon
        self.settings_btn = QPushButton()
        self.settings_btn.setIcon(get_chevron_down_icon(20, "#84cc16"))
        self.settings_btn.setFixedSize(40, 28)
        self.settings_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Prevent SPACE triggering
        self.settings_btn.setStyleSheet(
            """
            QPushButton {
                background: rgba(132, 204, 22, 0.1);
                border: 1px solid rgba(132, 204, 22, 0.3);
                border-radius: 6px;
            }
            QPushButton:hover {
                background: rgba(132, 204, 22, 0.2);
            }
        """
        )
        self.settings_btn.clicked.connect(self._toggle_settings)
        layout.addWidget(self.settings_btn, alignment=Qt.AlignmentFlag.AlignCenter)

        # Collapsible settings panel
        self.settings_panel = QWidget()
        self.settings_panel.setStyleSheet(
            """
            QWidget {
                background-color: rgba(0, 0, 0, 0.3);
                border-radius: 8px;
            }
            QLabel {
                color: #888;
                font-size: 10px;
            }
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid #4a3070;
                border-radius: 4px;
                color: #fff;
                padding: 6px;
                font-size: 11px;
            }
            QSlider::groove:horizontal {
                background: #333;
                height: 6px;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #84cc16;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
        """
        )
        settings_layout = QVBoxLayout(self.settings_panel)
        settings_layout.setContentsMargins(12, 8, 12, 8)
        settings_layout.setSpacing(8)

        # API URL
        url_label = QLabel("API URL")
        url_row = QHBoxLayout()
        self.api_url_input = QLineEdit(self.config.api_url)
        self.api_url_input.setPlaceholderText("https://api.openai.com/v1/audio/transcriptions")
        self.url_copy_btn = QPushButton()
        self.url_copy_btn.setIcon(get_copy_icon(16, "#888888"))
        self.url_copy_btn.setFixedSize(28, 28)
        self.url_copy_btn.setToolTip("Copy to clipboard")
        self.url_copy_btn.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: rgba(132, 204, 22, 0.2);
                border-color: rgba(132, 204, 22, 0.3);
            }
        """
        )
        self.url_copy_btn.clicked.connect(
            lambda: self._copy_to_clipboard(self.api_url_input.text(), self.url_copy_btn)
        )
        url_row.addWidget(self.api_url_input)
        url_row.addWidget(self.url_copy_btn)
        settings_layout.addWidget(url_label)
        settings_layout.addLayout(url_row)

        # API Key - store actual value separately and display asterisks
        key_label = QLabel("API Key")
        key_row = QHBoxLayout()
        self._actual_api_key = self.config.api_key
        self.api_key_input = QLineEdit()
        self._key_visible = False
        self._update_api_key_display()
        self.api_key_input.setPlaceholderText("sk-...")
        self.api_key_input.textChanged.connect(self._on_api_key_changed)
        # Style to ensure asterisks show clearly
        self.api_key_input.setStyleSheet(
            """
            QLineEdit {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid #4a3070;
                border-radius: 4px;
                color: #fff;
                padding: 6px;
                font-size: 12px;
                font-family: monospace;
            }
        """
        )
        # Eye icon button for show/hide
        self.key_visible_btn = QPushButton()
        self.key_visible_btn.setIcon(get_eye_icon(16, "#888888"))
        self.key_visible_btn.setFixedSize(28, 28)
        self.key_visible_btn.setToolTip("Show/hide API key")
        self.key_visible_btn.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: rgba(132, 204, 22, 0.2);
                border-color: rgba(132, 204, 22, 0.3);
            }
        """
        )
        self.key_visible_btn.clicked.connect(self._toggle_key_visibility)
        # Copy icon button
        self.key_copy_btn = QPushButton()
        self.key_copy_btn.setIcon(get_copy_icon(16, "#888888"))
        self.key_copy_btn.setFixedSize(28, 28)
        self.key_copy_btn.setToolTip("Copy to clipboard")
        self.key_copy_btn.setStyleSheet(
            """
            QPushButton {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid rgba(255, 255, 255, 0.1);
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: rgba(132, 204, 22, 0.2);
                border-color: rgba(132, 204, 22, 0.3);
            }
        """
        )
        self.key_copy_btn.clicked.connect(
            lambda: self._copy_to_clipboard(self._actual_api_key, self.key_copy_btn)
        )
        key_row.addWidget(self.api_key_input)
        key_row.addWidget(self.key_visible_btn)
        key_row.addWidget(self.key_copy_btn)
        settings_layout.addWidget(key_label)
        settings_layout.addLayout(key_row)

        # Microphone selection
        mic_label = QLabel("Microphone")
        self.mic_combo = QComboBox()
        self.mic_combo.setStyleSheet(
            """
            QComboBox {
                background-color: rgba(255, 255, 255, 0.1);
                border: 1px solid #4a3070;
                border-radius: 4px;
                color: #fff;
                padding: 6px;
                font-size: 11px;
            }
            QComboBox::drop-down {
                border: none;
            }
            QComboBox::down-arrow {
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid #888;
                margin-right: 8px;
            }
            QComboBox QAbstractItemView {
                background-color: #1a1033;
                border: 1px solid #4a3070;
                color: #fff;
                selection-background-color: rgba(132, 204, 22, 0.3);
            }
        """
        )
        self._populate_mic_dropdown()
        settings_layout.addWidget(mic_label)
        settings_layout.addWidget(self.mic_combo)

        # Gain slider with dynamic level display in groove
        # 0-200% range, with 100% (1.0x) in the middle
        gain_row = QHBoxLayout()
        self.gain_label = QLabel("Mic Gain:")
        self.gain_value_label = QLabel("100%")
        self.gain_value_label.setStyleSheet("color: #84cc16; font-weight: bold;")
        gain_row.addWidget(self.gain_label)
        gain_row.addStretch()
        gain_row.addWidget(self.gain_value_label)
        self.sensitivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.sensitivity_slider.setRange(0, 200)
        self.sensitivity_slider.setValue(100)  # 100% = no gain adjustment
        self.sensitivity_slider.setSingleStep(20)  # Arrow keys move by 20%
        self.sensitivity_slider.setPageStep(20)  # Page up/down move by 20%
        self.sensitivity_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.sensitivity_slider.setTickInterval(20)  # Tick every 20% (20 units = 20%)
        self.sensitivity_slider.valueChanged.connect(self._on_sensitivity_changed)
        self._current_mic_level = 0  # Track current level for styling
        self._update_sensitivity_style()
        settings_layout.addLayout(gain_row)
        settings_layout.addWidget(self.sensitivity_slider)

        # Tick marks below slider (visual notches at 20% intervals)
        tick_marks = TickMarksWidget(num_ticks=11)  # 0%, 20%, 40%... 200%
        settings_layout.addWidget(tick_marks)

        # History section
        history_label = QLabel("Recent Clips")
        settings_layout.addWidget(history_label)

        self.history_list = QListWidget()
        self.history_list.setMinimumHeight(200)
        self.history_list.setMaximumHeight(320)  # ~10 items at 32px each
        self.history_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.history_list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.history_list.setStyleSheet(
            """
            QListWidget {
                background-color: rgba(255, 255, 255, 0.05);
                border: 1px solid #4a3070;
                border-radius: 4px;
                color: #ccc;
                font-size: 11px;
            }
            QListWidget::item {
                padding: 2px;
                border-bottom: 1px solid rgba(255, 255, 255, 0.1);
            }
            QListWidget::item:hover {
                background-color: rgba(132, 204, 22, 0.1);
            }
        """
        )
        self._refresh_history()
        settings_layout.addWidget(self.history_list)

        # Save button - at the bottom, vibrant green
        self.save_btn = QPushButton("Save Settings")
        self.save_btn.setStyleSheet(
            """
            QPushButton {
                background-color: #84cc16;
                color: #000;
                border: none;
                border-radius: 4px;
                font-size: 11px;
                font-weight: bold;
                padding: 8px 16px;
            }
            QPushButton:hover {
                background-color: #9ae62a;
            }
        """
        )
        self.save_btn.clicked.connect(self._save_settings)
        settings_layout.addWidget(self.save_btn)

        self.settings_panel.hide()  # Hidden by default
        layout.addWidget(self.settings_panel)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(container)

        # Close button - overlaid in top-right corner (not in layout)
        self.close_btn = QPushButton(container)
        self.close_btn.setIcon(get_close_icon(14, "#666666"))
        self.close_btn.setFixedSize(20, 20)
        self.close_btn.setToolTip("Close")
        self.close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # Prevent SPACE triggering
        self.close_btn.setStyleSheet(
            """
            QPushButton {
                background: transparent;
                border: none;
            }
        """
        )
        self.close_btn.clicked.connect(self._close_window)
        # Hover behavior - change icon to green instead of background
        self.close_btn.enterEvent = lambda e: self.close_btn.setIcon(get_close_icon(14, "#84cc16"))
        self.close_btn.leaveEvent = lambda e: self.close_btn.setIcon(get_close_icon(14, "#666666"))
        self.close_btn.move(self.config.window_width - 28, 8)  # Top-right corner
        self.close_btn.raise_()  # Bring to front

        # Version label - overlaid in top-left corner (not in layout)
        self.version_label = QLabel("v1.0.0", container)
        self.version_label.setStyleSheet(
            """
            color: #666;
            font-size: 10px;
        """
        )
        self.version_label.move(12, 8)

        # Size
        self.setFixedSize(self.config.window_width, self.config.window_height)

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
        """Toggle settings panel visibility."""
        if self.settings_panel.isVisible():
            self.settings_panel.hide()
            self.settings_btn.setIcon(get_chevron_down_icon(20, "#84cc16"))
            # Shrink window
            self.setFixedSize(self.config.window_width, self.config.window_height)
        else:
            self.settings_panel.show()
            self.settings_btn.setIcon(get_chevron_up_icon(20, "#84cc16"))
            # Expand window - make it tall enough for all settings + taller history
            self.setFixedSize(self.config.window_width, self.config.window_height + 520)

    def _update_api_key_display(self) -> None:
        """Update the API key display based on visibility."""
        # Block signals to prevent textChanged from firing
        self.api_key_input.blockSignals(True)
        if self._key_visible:
            self.api_key_input.setText(self._actual_api_key)
            self.api_key_input.setReadOnly(False)
        else:
            # Show asterisks for each character (use bullet character for better display)
            mask = "●" * len(self._actual_api_key) if self._actual_api_key else ""
            self.api_key_input.setText(mask)
            self.api_key_input.setReadOnly(True)  # Can't edit while hidden
        self.api_key_input.blockSignals(False)

    def _on_api_key_changed(self, text: str) -> None:
        """Handle API key text changes."""
        if self._key_visible:
            # If visible, update the actual key
            self._actual_api_key = text

    def _toggle_key_visibility(self) -> None:
        """Toggle API key visibility."""
        self._key_visible = not self._key_visible
        self._update_api_key_display()
        if self._key_visible:
            self.key_visible_btn.setIcon(get_eye_off_icon(16, "#888888"))
        else:
            self.key_visible_btn.setIcon(get_eye_icon(16, "#888888"))

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
        # Snap to nearest 20% increment
        snapped = round(value / 20) * 20
        if snapped != value:
            self.sensitivity_slider.blockSignals(True)
            self.sensitivity_slider.setValue(snapped)
            self.sensitivity_slider.blockSignals(False)
            value = snapped

        self.waveform.sensitivity = value
        self.gain_value_label.setText(f"{value}%")
        self._update_sensitivity_style()

    def _update_sensitivity_style(self) -> None:
        """Update the gain slider groove to show current mic level after gain."""
        # Apply gain to the raw level for visualization
        gain = self.sensitivity_slider.value() / 100.0  # 0-2.0
        gained_level = min(1.0, self._current_mic_level * gain * 5)  # Scale for visibility
        level_pct = int(gained_level * 100)

        self.sensitivity_slider.setStyleSheet(
            f"""
            QSlider::groove:horizontal {{
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #84cc16,
                    stop:{level_pct / 100:.2f} #84cc16,
                    stop:{min(1.0, level_pct / 100 + 0.01):.2f} #333,
                    stop:1 #333
                );
                height: 8px;
                border-radius: 4px;
            }}
            QSlider::handle:horizontal {{
                background: #fff;
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
                border: 2px solid #84cc16;
            }}
            QSlider::sub-page:horizontal {{
                background: transparent;
            }}
            QSlider::add-page:horizontal {{
                background: transparent;
            }}
            QSlider {{
                height: 24px;
            }}
        """
        )

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
        """Save settings to config."""
        self.config.api_url = self.api_url_input.text()
        self.config.api_key = self._actual_api_key  # Use the actual stored key
        # Save selected microphone
        self.config.input_device_index = self.mic_combo.currentData()
        self.config.input_device_name = self.mic_combo.currentText()
        self.config.save()
        # Brief confirmation
        self.save_btn.setText("✓ Saved!")
        QTimer.singleShot(1500, lambda: self.save_btn.setText("Save Settings"))

    def _refresh_history(self) -> None:
        """Refresh the history list from config."""
        self.history_list.clear()
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
            label.setStyleSheet("color: #ccc; font-size: 11px;")
            label.setToolTip(text)  # Full text on hover
            layout.addWidget(label, stretch=1)

            # Copy button
            copy_btn = QPushButton()
            copy_btn.setIcon(get_copy_icon(14, "#888"))
            copy_btn.setFixedSize(24, 24)
            copy_btn.setToolTip("Copy to clipboard")
            copy_btn.setStyleSheet(
                """
                QPushButton {
                    background: transparent;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover {
                    background: rgba(132, 204, 22, 0.2);
                }
            """
            )
            copy_btn.clicked.connect(lambda checked, t=text: self._copy_history_item(t))
            layout.addWidget(copy_btn)

            # Play button (only if audio file exists)
            if audio_file:
                play_btn = QPushButton()
                play_btn.setIcon(get_play_icon(14, "#888"))
                play_btn.setFixedSize(24, 24)
                play_btn.setToolTip("Play recording")
                play_btn.setStyleSheet(
                    """
                    QPushButton {
                        background: transparent;
                        border: none;
                        border-radius: 4px;
                    }
                    QPushButton:hover {
                        background: rgba(132, 204, 22, 0.2);
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
        self._show_status("Copied!")

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
            self._show_status("Audio file not found")
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
        screen = QApplication.primaryScreen().geometry()
        x = (screen.width() - self.width()) // 2
        y = int(screen.height() * 0.3)  # Upper third of screen
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
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(False)
        self.app.setWindowIcon(get_tray_icon(128, recording=False))  # Orange when idle

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
        self._pending_waveform_data = None  # Thread-safe buffer for waveform data

        # Connect signals
        self.signals.toggle_recording.connect(self._toggle_recording)
        self.signals.transcription_complete.connect(self._on_transcription_complete)
        self.signals.transcription_error.connect(self._on_transcription_error)
        self.signals.show_status.connect(self.window.set_status)
        self.window.cancel_requested.connect(self._cancel_recording)

        # Timer to poll waveform data from recorder thread (avoids cross-thread signal issues)
        self._waveform_timer = QTimer()
        self._waveform_timer.timeout.connect(self._poll_waveform_data)
        self._waveform_timer.setInterval(30)  # Poll at ~33 FPS

        # Hotkey - use appropriate backend for platform
        self.hotkey_manager = create_hotkey_manager(
            self.config.hotkey,
            lambda: self.signals.toggle_recording.emit(),
        )
        if self.hotkey_manager is None:
            print("Warning: Global hotkeys not available on this platform")

        # Integration server for Claude Code
        self.integration_server = None
        if self.config.claude_integration:
            from .integration_server import IntegrationServer

            self.integration_server = IntegrationServer(self.config.claude_integration_port)
            if self.integration_server.start():
                print(f"Integration server started on port {self.config.claude_integration_port}")
            else:
                self.integration_server = None

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
        settings_action.setEnabled(False)  # TODO: Implement settings UI
        menu.addAction(settings_action)

        menu.addSeparator()

        quit_action = QAction("Quit", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.show()

    def _update_icons(self, recording: bool) -> None:
        """Update all icons based on recording state."""
        self.tray.setIcon(get_tray_icon(64, recording=recording))
        self.window.update_icon(recording=recording)

    def _save_wav(self, path, audio_data: bytes) -> None:
        """Save audio data as a WAV file."""
        import wave

        with wave.open(str(path), "wb") as wf:
            wf.setnchannels(self.config.channels)
            wf.setsampwidth(2)  # 16-bit audio = 2 bytes
            wf.setframerate(self.config.sample_rate)
            wf.writeframes(audio_data)

    def _show_window(self) -> None:
        """Show the window without starting recording."""
        self.window.waveform.set_recording(False)
        self.window.set_recording_hint(recording=False)
        self._update_icons(recording=False)
        self.window.set_status("Ready", animate=False)
        self.window.center_on_screen()
        self.window.show()
        self.window.raise_()

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
        self._update_icons(recording=True)

        # Show window (don't steal focus from current app)
        self.window.waveform.set_recording(True)
        self.window.set_recording_hint(recording=True)
        self.window.set_status("Listening", animate=True)
        self.window.center_on_screen()
        self.window.show()

        # Start waveform polling timer
        self._pending_waveform_data = None
        self._waveform_timer.start()

        # Start recording
        self.recorder.start(level_callback=self._on_audio_level)

    def _cancel_recording(self) -> None:
        """Cancel recording without transcribing."""
        if not self.is_recording:
            return

        self.is_recording = False
        self.toggle_action.setText("Start Recording")
        self._update_icons(recording=False)

        # Stop waveform polling
        self._waveform_timer.stop()

        # Stop recording and discard audio
        self.recorder.stop()

        # Hide window
        self.window.waveform.set_recording(False)
        self.window.hide()

        self.tray.showMessage(
            "Turbo Whisper",
            "Recording cancelled",
            QSystemTrayIcon.MessageIcon.Information,
            1500,
        )

    def _stop_recording(self) -> None:
        """Stop recording and transcribe."""
        if not self.is_recording:
            return

        self.is_recording = False
        self.toggle_action.setText("Start Recording")
        self._update_icons(recording=False)

        # Stop waveform polling
        self._waveform_timer.stop()

        # Update UI
        self.window.waveform.set_recording(False)
        self.window.set_recording_hint(recording=False)
        self.window.set_status("Processing", animate=True)

        # Stop recording and get audio
        audio_data = self.recorder.stop()

        # Save audio to file if configured
        audio_filename = None
        if self.config.store_recordings and audio_data:
            from datetime import datetime

            timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            audio_filename = f"{timestamp}.wav"
            audio_path = self.config.get_recordings_dir() / audio_filename
            try:
                self._save_wav(audio_path, audio_data)
            except Exception as e:
                print(f"Warning: Could not save audio: {e}")
                audio_filename = None

        # Store for use in transcription callback
        self._pending_audio_filename = audio_filename

        # Transcribe in background thread
        def transcribe():
            try:
                text = self.client.transcribe_sync(audio_data)
                self.signals.transcription_complete.emit(text)
            except WhisperAPIError as e:
                self.signals.transcription_error.emit(str(e))

        threading.Thread(target=transcribe, daemon=True).start()

    def _on_audio_level(self, level: float, waveform_buffer: list[float]) -> None:
        """Handle audio level update from recorder (called from recorder thread)."""
        # Store data for main thread to poll (thread-safe assignment)
        self._pending_waveform_data = (level, list(waveform_buffer))

    def _poll_waveform_data(self) -> None:
        """Poll waveform data from recorder thread (called from main thread timer)."""
        if self._pending_waveform_data is not None:
            level, waveform_buffer = self._pending_waveform_data
            # Debug: print level occasionally
            if hasattr(self, "_poll_count"):
                self._poll_count += 1
            else:
                self._poll_count = 0
            if self._poll_count % 30 == 0:  # Every ~1 second
                print(f"Audio level: {level:.4f}")
            self.window.waveform.update_waveform(level, waveform_buffer)
            # Update mic level meter (scale 0-1 to 0-100, cap at 100)
            self.window.update_mic_level(level)

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

        timeout = self.config.claude_wait_timeout
        start = time.time()
        while (time.time() - start) < timeout:
            if IntegrationServer.is_ready(max_age=timeout):
                # Reset so we wait again next time
                IntegrationServer.reset_ready()
                return True
            time.sleep(0.1)
        return False

    def _on_transcription_complete(self, text: str) -> None:
        """Handle completed transcription."""
        self.window.hide()

        # Get the audio filename that was saved during _stop_recording
        audio_filename = getattr(self, "_pending_audio_filename", None)
        self._pending_audio_filename = None

        if text:
            # Save to history (with audio file if available)
            self.config.add_to_history(text, audio_file=audio_filename)
            self.window._refresh_history()

            # Copy to clipboard
            if self.config.copy_to_clipboard:
                self.typer.copy_to_clipboard(text)

            # Type into focused window (wait for Claude if running)
            if self.config.auto_paste:
                if self._wait_for_claude_ready():
                    self.typer.type_text(text)
                    self.tray.showMessage(
                        "Turbo Whisper",
                        f"Transcribed: {text[:50]}..."
                        if len(text) > 50
                        else f"Transcribed: {text}",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000,
                    )
                else:
                    # Timeout waiting for Claude - just show copied message
                    self.tray.showMessage(
                        "Turbo Whisper",
                        "Copied (Claude busy)",
                        QSystemTrayIcon.MessageIcon.Information,
                        2000,
                    )
            else:
                self.tray.showMessage(
                    "Turbo Whisper",
                    f"Transcribed: {text[:50]}..."
                    if len(text) > 50
                    else f"Transcribed: {text}",
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
        if self.hotkey_manager:
            self.hotkey_manager.stop()
        if self.integration_server:
            self.integration_server.stop()
        self.recorder.cleanup()
        self.app.quit()

    def run(self) -> int:
        """Run the application."""
        if self.hotkey_manager:
            self.hotkey_manager.start()

        hotkey_str = "+".join(k.title() for k in self.config.hotkey)
        self.tray.showMessage(
            "Turbo Whisper",
            f"Press {hotkey_str} to start dictating",
            QSystemTrayIcon.MessageIcon.Information,
            3000,
        )

        return self.app.exec()


_lock_fd = None  # Global to keep lock file descriptor open


def ensure_single_instance():
    """Ensure only one instance of the app is running."""
    global _lock_fd
    lock_path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "turbo-whisper.lock")

    try:
        # Open with O_CREAT to create if doesn't exist, O_WRONLY for writing
        _lock_fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o644)
        # Try to acquire exclusive lock (non-blocking)
        fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # Write PID
        os.ftruncate(_lock_fd, 0)
        os.write(_lock_fd, str(os.getpid()).encode())
    except OSError:
        print("Turbo Whisper is already running.")
        sys.exit(0)


def main():
    """Application entry point."""
    ensure_single_instance()
    app = TurboWhisper()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
