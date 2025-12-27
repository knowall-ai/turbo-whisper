"""Waveform visualization widget."""

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QWidget


class WaveformWidget(QWidget):
    """Widget displaying audio waveform visualization."""

    def __init__(self, parent=None, color="#00ff88", bg_color="#1a1a2e"):
        super().__init__(parent)
        self.waveform_data = []
        self.color = QColor(color)
        self.bg_color = QColor(bg_color)
        self.bar_count = 40
        self.animation_offset = 0

        # Animation timer for idle state
        self.idle_timer = QTimer(self)
        self.idle_timer.timeout.connect(self._animate_idle)
        self.is_recording = False

        self.setMinimumHeight(60)

    def set_recording(self, recording: bool) -> None:
        """Set recording state."""
        self.is_recording = recording
        if not recording:
            self.idle_timer.start(50)
        else:
            self.idle_timer.stop()
        self.update()

    def update_waveform(self, level: float, waveform_buffer: list[float]) -> None:
        """Update waveform with new audio data."""
        self.waveform_data = waveform_buffer
        self.update()

    def _animate_idle(self) -> None:
        """Animate bars when idle/processing."""
        self.animation_offset = (self.animation_offset + 1) % 360
        self.update()

    def paintEvent(self, event) -> None:
        """Paint the waveform visualization."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), self.bg_color)

        width = self.width()
        height = self.height()
        center_y = height / 2

        bar_width = max(3, (width - (self.bar_count * 2)) // self.bar_count)
        spacing = 2
        total_width = self.bar_count * (bar_width + spacing)
        start_x = (width - total_width) // 2

        pen = QPen(self.color)
        pen.setWidth(bar_width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)

        if self.is_recording and self.waveform_data:
            # Draw actual waveform from audio data
            data_len = len(self.waveform_data)
            for i in range(self.bar_count):
                # Map bar index to waveform data
                data_idx = int(i * data_len / self.bar_count) if data_len > 0 else 0
                level = self.waveform_data[data_idx] if data_idx < data_len else 0

                # Scale level to bar height (with some minimum visibility)
                bar_height = max(4, level * (height - 10) * 2)

                x = start_x + i * (bar_width + spacing) + bar_width // 2
                y1 = center_y - bar_height / 2
                y2 = center_y + bar_height / 2

                painter.drawLine(int(x), int(y1), int(x), int(y2))
        else:
            # Animated idle/processing state
            import math

            for i in range(self.bar_count):
                # Create wave animation
                phase = (i / self.bar_count) * 4 * math.pi
                offset = math.sin(phase + math.radians(self.animation_offset * 3)) * 0.3
                level = 0.2 + abs(offset)

                bar_height = max(4, level * (height - 20))

                x = start_x + i * (bar_width + spacing) + bar_width // 2
                y1 = center_y - bar_height / 2
                y2 = center_y + bar_height / 2

                # Fade color for processing effect
                fade_color = QColor(self.color)
                fade_color.setAlpha(150 + int(abs(offset) * 100))
                pen.setColor(fade_color)
                painter.setPen(pen)

                painter.drawLine(int(x), int(y1), int(x), int(y2))

        painter.end()
