"""Lucide icons for Turbo Whisper UI."""

from PyQt6.QtCore import QByteArray, QSize
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtGui import QPainter


def _svg_to_icon(svg_content: str, size: int = 24, color: str = "#888888") -> QIcon:
    """Convert SVG string to QIcon with specified color."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QImage

    # Replace stroke color in SVG
    svg_with_color = svg_content.replace('stroke="currentColor"', f'stroke="{color}"')

    # Create pixmap from SVG with proper transparency
    svg_bytes = QByteArray(svg_with_color.encode())
    renderer = QSvgRenderer(svg_bytes)

    # Use QImage for proper alpha channel support
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)

    painter = QPainter(image)
    renderer.render(painter)
    painter.end()

    pixmap = QPixmap.fromImage(image)
    return QIcon(pixmap)


# Lucide icon SVGs (24x24 viewBox, stroke-based)
ICON_POWER = '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 2v10"/>
  <path d="M18.4 6.6a9 9 0 1 1-12.77.04"/>
</svg>'''

ICON_COPY = '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect width="14" height="14" x="8" y="8" rx="2" ry="2"/>
  <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2"/>
</svg>'''

ICON_EYE = '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 10.75 10.75 0 0 1-19.876 0"/>
  <circle cx="12" cy="12" r="3"/>
</svg>'''

ICON_EYE_OFF = '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/>
  <path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/>
  <path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/>
  <path d="m2 2 20 20"/>
</svg>'''

ICON_CHEVRON_DOWN = '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m6 9 6 6 6-6"/>
</svg>'''

ICON_CHEVRON_UP = '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m18 15-6-6-6 6"/>
</svg>'''

ICON_CHECK = '''<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M20 6 9 17l-5-5"/>
</svg>'''


def get_close_icon(size: int = 20, color: str = "#888888") -> QIcon:
    """Get the power/close icon."""
    return _svg_to_icon(ICON_POWER, size, color)


def get_copy_icon(size: int = 20, color: str = "#888888") -> QIcon:
    """Get the copy icon."""
    return _svg_to_icon(ICON_COPY, size, color)


def get_eye_icon(size: int = 20, color: str = "#888888") -> QIcon:
    """Get the eye (visible) icon."""
    return _svg_to_icon(ICON_EYE, size, color)


def get_eye_off_icon(size: int = 20, color: str = "#888888") -> QIcon:
    """Get the eye-off (hidden) icon."""
    return _svg_to_icon(ICON_EYE_OFF, size, color)


def get_chevron_down_icon(size: int = 20, color: str = "#888888") -> QIcon:
    """Get the chevron-down icon."""
    return _svg_to_icon(ICON_CHEVRON_DOWN, size, color)


def get_chevron_up_icon(size: int = 20, color: str = "#888888") -> QIcon:
    """Get the chevron-up icon."""
    return _svg_to_icon(ICON_CHEVRON_UP, size, color)


def get_check_icon(size: int = 20, color: str = "#888888") -> QIcon:
    """Get the check/tick icon."""
    return _svg_to_icon(ICON_CHECK, size, color)
