"""Unit tests for WindowDetector (cross-platform focused window detection)."""

import subprocess
from unittest.mock import MagicMock, patch

from turbo_whisper.window import WindowDetector


def test_clean_window_name():
    """Test window name cleaning and truncation."""
    detector = WindowDetector()
    assert detector._clean_window_name("") == ""
    assert detector._clean_window_name("   ") == ""
    assert detector._clean_window_name("Firefox") == "Firefox"
    assert detector._clean_window_name("  Visual Studio Code  ") == "Visual Studio Code"

    # Exactly 20 chars
    name_20 = "12345678901234567890"
    assert detector._clean_window_name(name_20) == name_20

    # Over 20 chars should be truncated to 17 chars + "..."
    name_long = "Google Chrome - Github Issue Review"
    cleaned = detector._clean_window_name(name_long)
    assert len(cleaned) == 20
    assert cleaned.endswith("...")
    assert cleaned == name_long[:17] + "..."


def test_kde_wayland_with_kdotool():
    """Test KDE Wayland focused window detection using kdotool."""
    detector = WindowDetector()
    detector.system = "Linux"
    detector.is_wayland = True
    detector.desktop = "kde plasma"
    detector.kdotool_available = True

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Kate Editor\n"

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        name = detector.get_focused_window_name()
        mock_run.assert_called_once_with(
            ["kdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=1.0,
        )
        assert name == "Kate Editor"


def test_kde_wayland_missing_kdotool_graceful_fallback():
    """Test KDE Wayland gracefully returns None without error when kdotool is missing."""
    detector = WindowDetector()
    detector.system = "Linux"
    detector.is_wayland = True
    detector.desktop = "kde plasma"
    detector.kdotool_available = False

    with patch("subprocess.run") as mock_run:
        name = detector.get_focused_window_name()
        mock_run.assert_not_called()
        assert name is None


def test_x11_with_xdotool():
    """Test Linux X11 focused window detection with xdotool."""
    detector = WindowDetector()
    detector.system = "Linux"
    detector.is_wayland = False
    detector.xdotool_available = True

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Alacritty\n"

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        name = detector.get_focused_window_name()
        mock_run.assert_called_once_with(
            ["xdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=1.0,
        )
        assert name == "Alacritty"


def test_x11_fallback_to_kdotool():
    """Test Linux X11 falls back to kdotool if xdotool is not available."""
    detector = WindowDetector()
    detector.system = "Linux"
    detector.is_wayland = False
    detector.xdotool_available = False
    detector.kdotool_available = True

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Konsole\n"

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        name = detector.get_focused_window_name()
        mock_run.assert_called_once_with(
            ["kdotool", "getactivewindow", "getwindowname"],
            capture_output=True,
            text=True,
            timeout=1.0,
        )
        assert name == "Konsole"


def test_macos_osascript():
    """Test macOS window detection via osascript."""
    detector = WindowDetector()
    detector.system = "Darwin"

    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stdout = "Safari\n"

    with patch("subprocess.run", return_value=mock_result) as mock_run:
        name = detector.get_focused_window_name()
        assert mock_run.called
        assert name == "Safari"


def test_command_timeout_handled_gracefully():
    """Test that subprocess timeout or errors return None safely without raising."""
    detector = WindowDetector()
    detector.system = "Linux"
    detector.is_wayland = True
    detector.desktop = "kde plasma"
    detector.kdotool_available = True

    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="kdotool", timeout=1.0)):
        assert detector.get_focused_window_name() is None
