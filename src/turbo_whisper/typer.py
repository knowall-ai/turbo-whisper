"""Auto-type functionality - cross-platform."""

import platform
import shutil
import subprocess

SYSTEM = platform.system()


class Typer:
    """Types text into the currently focused window."""

    def __init__(self):
        self.system = SYSTEM

        if self.system == "Windows":
            try:
                import pyperclip

                self._pyperclip = pyperclip
            except ImportError:
                self._pyperclip = None
                print("Warning: pyperclip not installed. Install with: pip install pyperclip")
        else:
            self._pyperclip = None
            self.xdotool_available = shutil.which("xdotool") is not None
            self.wtype_available = shutil.which("wtype") is not None

            if not self.xdotool_available and not self.wtype_available:
                print("Warning: Neither xdotool nor wtype found. Auto-typing disabled.")
                print("Install with: sudo apt install xdotool")

    def type_text(self, text: str) -> bool:
        """
        Type text into the currently focused window.

        Args:
            text: Text to type

        Returns:
            True if successful, False otherwise
        """
        if not text:
            return False

        if self.system == "Windows":
            return self._type_windows(text)
        elif self.system == "Darwin":
            return self._type_macos(text)
        else:
            return self._type_linux(text)

    def _type_windows(self, text: str) -> bool:
        """Type text on Windows using pyautogui or keyboard simulation."""
        try:
            # Copy to clipboard and paste (most reliable on Windows)
            if self._pyperclip:
                self._pyperclip.copy(text)
                # Simulate Ctrl+V
                import ctypes

                user32 = ctypes.windll.user32
                # Press Ctrl
                user32.keybd_event(0x11, 0, 0, 0)
                # Press V
                user32.keybd_event(0x56, 0, 0, 0)
                # Release V
                user32.keybd_event(0x56, 0, 2, 0)
                # Release Ctrl
                user32.keybd_event(0x11, 0, 2, 0)
                return True
        except Exception as e:
            print(f"Windows typing error: {e}")
        return False

    def _type_macos(self, text: str) -> bool:
        """Type text on macOS using osascript."""
        try:
            # Escape text for AppleScript
            escaped = text.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(
                ["osascript", "-e", f'tell application "System Events" to keystroke "{escaped}"'],
                check=True,
                capture_output=True,
            )
            return True
        except subprocess.CalledProcessError as e:
            print(f"macOS typing error: {e}")
        return False

    def _type_linux(self, text: str) -> bool:
        """Type text on Linux using xdotool or wtype."""
        # Try wtype first (Wayland)
        if self.wtype_available:
            try:
                subprocess.run(
                    ["wtype", text],
                    check=True,
                    capture_output=True,
                )
                return True
            except subprocess.CalledProcessError:
                pass  # Fall through to xdotool

        # Try xdotool (X11)
        if self.xdotool_available:
            try:
                subprocess.run(
                    ["xdotool", "type", "--clearmodifiers", "--", text],
                    check=True,
                    capture_output=True,
                )
                return True
            except subprocess.CalledProcessError as e:
                print(f"xdotool error: {e}")
                return False

        return False

    def copy_to_clipboard(self, text: str) -> bool:
        """
        Copy text to clipboard.

        Args:
            text: Text to copy

        Returns:
            True if successful, False otherwise
        """
        if self.system == "Windows":
            if self._pyperclip:
                try:
                    self._pyperclip.copy(text)
                    return True
                except Exception:
                    pass
            return False

        if self.system == "Darwin":
            try:
                proc = subprocess.Popen(
                    ["pbcopy"],
                    stdin=subprocess.PIPE,
                )
                proc.communicate(input=text.encode())
                return proc.returncode == 0
            except Exception:
                pass
            return False

        # Linux
        # Try xclip first
        if shutil.which("xclip"):
            try:
                proc = subprocess.Popen(
                    ["xclip", "-selection", "clipboard"],
                    stdin=subprocess.PIPE,
                )
                proc.communicate(input=text.encode())
                return proc.returncode == 0
            except Exception:
                pass

        # Try xsel
        if shutil.which("xsel"):
            try:
                proc = subprocess.Popen(
                    ["xsel", "--clipboard", "--input"],
                    stdin=subprocess.PIPE,
                )
                proc.communicate(input=text.encode())
                return proc.returncode == 0
            except Exception:
                pass

        # Try wl-copy (Wayland)
        if shutil.which("wl-copy"):
            try:
                proc = subprocess.Popen(
                    ["wl-copy"],
                    stdin=subprocess.PIPE,
                )
                proc.communicate(input=text.encode())
                return proc.returncode == 0
            except Exception:
                pass

        return False
