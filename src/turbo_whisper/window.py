"""Focused window detection - cross-platform."""

import os
import platform
import shutil
import subprocess
from typing import Optional

SYSTEM = platform.system()


class WindowDetector:
    """Detects the currently focused window/application."""

    def __init__(self):
        self.system = SYSTEM

        # Check for required tools on Linux
        if self.system == "Linux":
            self.xdotool_available = shutil.which("xdotool") is not None
            self.kdotool_available = shutil.which("kdotool") is not None
            self.is_wayland = os.environ.get("XDG_SESSION_TYPE") == "wayland"
            self.desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()

    def get_focused_window_name(self) -> Optional[str]:
        """
        Get the name of the currently focused window.

        Returns:
            Window/application name, or None if detection fails.
        """
        try:
            if self.system == "Windows":
                return self._get_window_windows()
            elif self.system == "Darwin":
                return self._get_window_macos()
            else:
                return self._get_window_linux()
        except Exception:
            # Catch-all: never let window detection break recording
            return None

    def _get_window_linux(self) -> Optional[str]:
        """Get focused window on Linux (X11 or Wayland)."""
        # Try kdotool first (KDE Wayland)
        if self.kdotool_available:
            try:
                result = subprocess.run(
                    ["kdotool", "getactivewindow", "getwindowname"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return self._clean_window_name(result.stdout.strip())
            except (subprocess.SubprocessError, OSError, subprocess.TimeoutExpired):
                pass

        # Try KDE DBus for Wayland
        if self.is_wayland and "kde" in self.desktop:
            name = self._get_window_kde_dbus()
            if name:
                return name

        # Try xdotool (X11)
        if self.xdotool_available:
            try:
                result = subprocess.run(
                    ["xdotool", "getactivewindow", "getwindowname"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return self._clean_window_name(result.stdout.strip())
            except (subprocess.SubprocessError, OSError, subprocess.TimeoutExpired):
                pass

        return None

    def _get_window_kde_dbus(self) -> Optional[str]:
        """Get focused window on KDE Wayland via DBus."""
        try:
            # Try using qdbus6 or qdbus to get active window caption
            for qdbus in ["qdbus6", "qdbus"]:
                if shutil.which(qdbus):
                    result = subprocess.run(
                        [
                            qdbus,
                            "org.kde.KWin",
                            "/KWin",
                            "org.kde.KWin.activeWindow",
                        ],
                        capture_output=True,
                        text=True,
                        timeout=1.0,
                    )
                    if result.returncode == 0 and result.stdout.strip():
                        # Returns window ID, need to get caption
                        window_id = result.stdout.strip()
                        # Try to get window caption
                        result2 = subprocess.run(
                            [
                                qdbus,
                                "org.kde.KWin",
                                f"/Windows/{window_id}",
                                "caption",
                            ],
                            capture_output=True,
                            text=True,
                            timeout=1.0,
                        )
                        if result2.returncode == 0 and result2.stdout.strip():
                            return self._clean_window_name(result2.stdout.strip())
        except (subprocess.SubprocessError, OSError, subprocess.TimeoutExpired):
            pass
        return None

    def _get_window_macos(self) -> Optional[str]:
        """Get focused window on macOS using AppleScript."""
        script = """
            tell application "System Events"
                set frontApp to name of first application process whose frontmost is true
            end tell
            return frontApp
        """
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            if result.returncode == 0:
                return self._clean_window_name(result.stdout.strip())
        except (subprocess.SubprocessError, OSError, subprocess.TimeoutExpired):
            pass
        return None

    def _get_window_windows(self) -> Optional[str]:
        """Get focused window on Windows using Win32 API."""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()

            if not hwnd:
                return None

            # Get window title length
            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return None

            # Get window title
            buffer = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buffer, length + 1)

            return self._clean_window_name(buffer.value)
        except Exception:
            pass
        return None

    def _clean_window_name(self, name: str) -> str:
        """Clean and truncate window name for display."""
        if not name:
            return ""

        name = name.strip()

        # Truncate long names
        max_length = 20
        if len(name) > max_length:
            name = name[: max_length - 3] + "..."

        return name
