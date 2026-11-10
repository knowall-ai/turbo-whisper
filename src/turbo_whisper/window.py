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
        self._warned_kdotool = False

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
        # Under Wayland, X11 tools cannot inspect other windows due to security restrictions
        if self.is_wayland:
            # KDE Plasma on Wayland: kdotool interacts with KWin via DBus scripting
            if "kde" in self.desktop:
                if self.kdotool_available:
                    try:
                        result = subprocess.run(
                            ["kdotool", "getactivewindow", "getwindowname"],
                            capture_output=True,
                            text=True,
                            timeout=1.0,
                        )
                        if result.returncode == 0 and result.stdout.strip():
                            return self._clean_window_name(result.stdout)
                    except (subprocess.SubprocessError, OSError, subprocess.TimeoutExpired):
                        pass
                elif not self._warned_kdotool:
                    self._warned_kdotool = True
                    print(
                        "[turbo-whisper] Focused window detection on KDE Wayland requires "
                        "'kdotool'. Install with: yay -S kdotool or cargo install kdotool"
                    )

            # Other Wayland compositors (GNOME, etc.) restrict reading other windows' titles
            return None

        # X11 session: try xdotool first, then kdotool if available
        if self.xdotool_available:
            try:
                result = subprocess.run(
                    ["xdotool", "getactivewindow", "getwindowname"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return self._clean_window_name(result.stdout)
            except (subprocess.SubprocessError, OSError, subprocess.TimeoutExpired):
                pass

        if self.kdotool_available:
            try:
                result = subprocess.run(
                    ["kdotool", "getactivewindow", "getwindowname"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                )
                if result.returncode == 0 and result.stdout.strip():
                    return self._clean_window_name(result.stdout)
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
            if result.returncode == 0 and result.stdout.strip():
                return self._clean_window_name(result.stdout)
        except (subprocess.SubprocessError, OSError, subprocess.TimeoutExpired):
            pass
        return None

    def _get_window_windows(self) -> Optional[str]:
        """Get focused window on Windows using Win32 API."""
        try:
            import ctypes
            from ctypes import wintypes

            user32 = ctypes.windll.user32

            # Define Win32 prototypes with pointer-sized HWND to prevent 64-bit truncation
            user32.GetForegroundWindow.argtypes = []
            user32.GetForegroundWindow.restype = wintypes.HWND

            user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            user32.GetWindowTextLengthW.restype = ctypes.c_int

            user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            user32.GetWindowTextW.restype = ctypes.c_int

            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None

            length = user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return None

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
