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
            self.ydotool_available = shutil.which("ydotool") is not None

            if not self.xdotool_available and not self.wtype_available and not self.ydotool_available:
                print("Warning: No typing tool found. Auto-typing disabled.")
                print("Install with: sudo apt install ydotool (Wayland) or xdotool (X11)")

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
        """Type text on Linux using ydotool, wtype, xdotool, or clipboard fallback."""
        import time

        print(f"type_linux called with: {text[:50] if text else 'empty'}...", flush=True)

        # Try ydotool first (works on KDE Wayland via uinput)
        if self.ydotool_available:
            try:
                print("Trying ydotool...", flush=True)
                # Small delay to let window focus settle after our window hides
                time.sleep(0.15)
                subprocess.run(
                    ["ydotool", "type", "--", text],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                print("ydotool succeeded", flush=True)
                return True
            except subprocess.CalledProcessError as e:
                print(f"ydotool failed: {e.stderr if hasattr(e, 'stderr') else e}", flush=True)
                pass  # Fall through to wtype

        # Try wtype (native Wayland, simpler compositors)
        if self.wtype_available:
            try:
                print("Trying wtype...", flush=True)
                subprocess.run(
                    ["wtype", text],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                print("wtype succeeded", flush=True)
                return True
            except subprocess.CalledProcessError as e:
                print(f"wtype failed: {e.stderr if hasattr(e, 'stderr') else e}", flush=True)
                pass  # Fall through to xdotool

        # Try xdotool (X11 / XWayland apps)
        if self.xdotool_available:
            try:
                # Longer delay to let window focus return to previous app
                time.sleep(0.3)
                print("Trying xdotool...", flush=True)
                subprocess.run(
                    ["xdotool", "type", "--delay", "10", "--clearmodifiers", "--", text],
                    check=True,
                    capture_output=True,
                )
                print("xdotool succeeded", flush=True)
                return True
            except subprocess.CalledProcessError as e:
                print(f"xdotool failed: {e}", flush=True)
                pass  # Fall through to clipboard

        # Last resort: copy to clipboard
        if self.copy_to_clipboard(text):
            print("Text copied to clipboard - press Ctrl+V to paste")
            return True

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
