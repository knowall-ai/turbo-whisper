"""Auto-type functionality using xdotool."""

import shutil
import subprocess


class Typer:
    """Types text into the currently focused window."""

    def __init__(self):
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
