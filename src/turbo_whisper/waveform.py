"""Waveform visualization widget - OpenAI/ElevenLabs style."""

import math
from collections import deque

from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient, QBrush
from PyQt6.QtWidgets import QWidget


class WaveformWidget(QWidget):
    """Organic blob-style audio visualization that responds to sound."""

    def __init__(self, parent=None, color="#84cc16", bg_color="#1a1a2e"):
        super().__init__(parent)
        self.base_color = QColor(color)
        self.bg_color = QColor(bg_color)

        # Audio state
        self.current_level = 0.0
        self.target_level = 0.0
        self.waveform_data = []
        self.level_history = deque(maxlen=60)  # Smooth level tracking
        self.is_recording = False

        # Animation state
        self.phase = 0.0
        self.blob_points = 32  # Points around the blob (fewer = smoother curves)

        # Smooth animation timer
        self.animation_timer = QTimer(self)
        self.animation_timer.timeout.connect(self._animate)
        self.animation_timer.setInterval(16)  # ~60 FPS

        # Sensitivity threshold - slider value (1-500) maps to threshold
        # Lower sensitivity = higher threshold = less responsive
        # Higher sensitivity = lower threshold = more responsive
        self._sensitivity_value = 200
        self._update_threshold()

        self.setMinimumHeight(130)

    @property
    def sensitivity(self) -> int:
        """Get sensitivity value (1-500)."""
        return self._sensitivity_value

    @sensitivity.setter
    def sensitivity(self, value: int) -> None:
        """Set gain value (0-200, where 100 = normal)."""
        self._sensitivity_value = max(0, min(200, value))
        self._update_threshold()

    def _update_threshold(self) -> None:
        """Update gain based on sensitivity value."""
        # Gain controls how much we amplify the mic signal
        # 0 = mute, 100 = 1.0x (normal), 200 = 2.0x (double)
        # Use a fixed low threshold; gain is purely about amplification
        self.silence_threshold = 0.03  # Fixed low threshold
        self._gain = self._sensitivity_value / 100.0  # 0.0 to 2.0 gain

    def set_recording(self, recording: bool) -> None:
        """Set recording state."""
        self.is_recording = recording
        self.waveform_data = []
        self.current_level = 0.0
        self.target_level = 0.0
        self.level_history.clear()
        self.phase = 0.0

        if recording:
            self.animation_timer.start()
        else:
            self.animation_timer.start()  # Keep for processing animation
        self.update()

    def update_waveform(self, level: float, waveform_buffer: list[float]) -> None:
        """Update with new audio data."""
        self.waveform_data = waveform_buffer
        # Apply gain based on sensitivity setting
        # This allows quiet mics to produce visible response
        amplified = min(1.0, level * self._gain)
        self.target_level = amplified
        self.level_history.append(amplified)

    def _animate(self) -> None:
        """Smooth animation tick."""
        # Smoothly interpolate towards target level
        self.current_level += (self.target_level - self.current_level) * 0.3

        # Decay target level if no new data
        self.target_level *= 0.85

        # Advance phase for organic movement (slower when quiet)
        if self.current_level > self.silence_threshold:
            self.phase += 0.08 + self.current_level * 0.1
        else:
            self.phase += 0.02  # Very slow idle drift

        self.repaint()

    def paintEvent(self, event) -> None:
        """Paint the organic blob visualization."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Transparent background
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)

        width = self.width()
        height = self.height()
        center_x = width / 2
        center_y = height / 2

        # Base radius scales with widget size - keep within bounds
        base_radius = min(width, height) * 0.40  # Fit within widget bounds

        # Calculate if we're in silence
        is_silent = self.current_level < self.silence_threshold

        # Draw multiple layered blobs for depth
        for layer in range(3):
            layer_factor = 1.0 - layer * 0.2
            layer_alpha = 255 - layer * 60

            # Build blob path
            path = QPainterPath()
            points = []

            for i in range(self.blob_points):
                angle = (i / self.blob_points) * 2 * math.pi

                if is_silent and self.is_recording:
                    # Subtle breathing when silent but recording
                    breath = math.sin(self.phase * 0.5) * 0.03
                    noise = math.sin(angle * 3 + self.phase * 0.3) * 0.02
                    radius_mod = 1.0 + breath + noise
                elif not self.is_recording:
                    # Processing state - gentle pulse
                    pulse = math.sin(self.phase) * 0.1
                    noise = math.sin(angle * 4 + self.phase * 2) * 0.05
                    radius_mod = 1.0 + pulse + noise
                else:
                    # Active sound - responsive blob
                    # Multiple frequency components for organic feel
                    wave1 = math.sin(angle * 2 + self.phase) * self.current_level * 0.4
                    wave2 = math.sin(angle * 3 - self.phase * 1.3) * self.current_level * 0.3
                    wave3 = math.sin(angle * 5 + self.phase * 0.7) * self.current_level * 0.2

                    # Add some randomness based on level history
                    if len(self.level_history) > 0:
                        idx = int((i / self.blob_points) * len(self.level_history))
                        idx = min(idx, len(self.level_history) - 1)
                        hist_mod = list(self.level_history)[idx] * 0.2
                    else:
                        hist_mod = 0

                    radius_mod = 1.0 + wave1 + wave2 + wave3 + hist_mod

                radius = base_radius * radius_mod * layer_factor
                x = center_x + math.cos(angle) * radius
                y = center_y + math.sin(angle) * radius
                points.append(QPointF(x, y))

            # Close the path smoothly using bezier curves
            if points:
                path.moveTo(points[0])
                for i in range(len(points)):
                    p0 = points[i]
                    p1 = points[(i + 1) % len(points)]

                    # Control points for smooth curves
                    ctrl_len = 0.3
                    angle0 = math.atan2(p0.y() - center_y, p0.x() - center_x) + math.pi / 2
                    angle1 = math.atan2(p1.y() - center_y, p1.x() - center_x) + math.pi / 2

                    dist0 = math.sqrt((p0.x() - center_x)**2 + (p0.y() - center_y)**2) * ctrl_len
                    dist1 = math.sqrt((p1.x() - center_x)**2 + (p1.y() - center_y)**2) * ctrl_len

                    cp1 = QPointF(p0.x() + math.cos(angle0) * dist0,
                                  p0.y() + math.sin(angle0) * dist0)
                    cp2 = QPointF(p1.x() - math.cos(angle1) * dist1,
                                  p1.y() - math.sin(angle1) * dist1)

                    path.cubicTo(cp1, cp2, p1)

            # Color with glow effect
            if layer == 0:
                # Outer glow
                glow_color = QColor(self.base_color)
                glow_color.setAlpha(30 + int(self.current_level * 50))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(glow_color))
            elif layer == 1:
                # Mid layer
                mid_color = QColor(self.base_color)
                mid_color.setAlpha(layer_alpha)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(mid_color))
            else:
                # Inner bright core
                # Radial gradient for depth
                gradient = QRadialGradient(center_x, center_y, base_radius * layer_factor)

                core_color = QColor(self.base_color).lighter(150)
                core_color.setAlpha(200)
                gradient.setColorAt(0, core_color)

                edge_color = QColor(self.base_color)
                edge_color.setAlpha(layer_alpha)
                gradient.setColorAt(1, edge_color)

                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(gradient))

            painter.drawPath(path)

        # Draw subtle ring around blob when actively listening
        if self.is_recording and self.current_level > self.silence_threshold:
            ring_radius = base_radius * (1.5 + self.current_level * 0.5)
            ring_color = QColor(self.base_color)
            ring_color.setAlpha(int(30 + self.current_level * 40))

            pen = QPen(ring_color)
            pen.setWidth(2)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawEllipse(QPointF(center_x, center_y), ring_radius, ring_radius)

        painter.end()
