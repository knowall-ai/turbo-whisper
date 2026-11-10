"""A compact, sound-responsive waveform for the recording HUD."""

import math

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QPainter
from PyQt6.QtWidgets import QWidget


class WaveformWidget(QWidget):
    """Smoothed bars with bounded work per frame and no idle animation."""

    def __init__(self, parent=None, color="#c7aff5", bg_color="#252528"):
        super().__init__(parent)
        self.recording_color = QColor(color)
        self.idle_color = QColor("#80788d")
        self.bg_color = QColor(bg_color)
        self.is_recording = False
        self.current_level = 0.0
        self.target_level = 0.0
        self.waveform_data = []
        self.phase = 0.0
        self._sensitivity_value = 100
        self._gain = 1.0
        self._bars = [0.0] * 18
        self.animation_timer = QTimer(self)
        self.animation_timer.setInterval(30)
        self.animation_timer.timeout.connect(self._animate)
        self.setMinimumHeight(30)
        self.setAccessibleName("Recording audio level")

    @property
    def sensitivity(self):
        return self._sensitivity_value

    @sensitivity.setter
    def sensitivity(self, value):
        self._sensitivity_value = max(0, min(200, value))
        self._gain = self._sensitivity_value / 100

    def set_recording(self, recording):
        self.is_recording = recording
        self.current_level = self.target_level = 0.0
        self.waveform_data = []
        self._bars = [0.0] * 18
        if recording and self.isVisible():
            self.animation_timer.start()
        else:
            self.animation_timer.stop()
        self.update()

    def update_waveform(self, level, waveform_buffer):
        self.target_level = min(1.0, max(0.0, level) * self._gain)
        # Keep a bounded display buffer; the recorder owns the full audio.
        self.waveform_data = list(waveform_buffer[-180:])

    def _animate(self):
        self.current_level += (self.target_level - self.current_level) * 0.35
        self.target_level *= 0.88
        self.phase += 0.24
        for i in range(len(self._bars)):
            envelope = 0.35 + 0.65 * math.sin(math.pi * (i + 1) / 19)
            sample = (
                abs(self.waveform_data[i * len(self.waveform_data) // 18])
                if self.waveform_data
                else 0
            )
            target = min(1.0, max(sample * self._gain, self.current_level) * envelope)
            self._bars[i] += (target - self._bars[i]) * 0.4
        self.update()

    def showEvent(self, event):
        if self.is_recording:
            self.animation_timer.start()
        super().showEvent(event)

    def hideEvent(self, event):
        self.animation_timer.stop()
        super().hideEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self.recording_color if self.is_recording else self.idle_color)
        from PyQt6.QtCore import QRectF

        spacing = self.width() / len(self._bars)
        for i, level in enumerate(self._bars):
            height = max(3.0, level * (self.height() - 6))
            width = max(2.0, spacing * 0.52)
            painter.drawRoundedRect(
                QRectF(i * spacing, (self.height() - height) / 2, width, height),
                width / 2,
                width / 2,
            )
