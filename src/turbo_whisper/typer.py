"""Auto-type functionality - cross-platform using PyAutoGUI and evdev."""

import platform
import shutil
import subprocess

SYSTEM = platform.system()


class Typer:
    """Types text into the currently focused window."""

    def __init__(self):
        self.system = SYSTEM
        self._uinput = None
        self._evdev_available = False

        if self.system == "Linux":
            self._setup_linux()

    def _setup_linux(self) -> None:
        """Set up Linux typing backend (evdev for uinput access)."""
        try:
            import evdev
            from evdev import UInput, ecodes

            # Key mapping: character -> (keycode, needs_shift)
            self._key_map = self._build_key_map(ecodes)
            self._ecodes = ecodes

            # Try to create UInput device
            cap = {ecodes.EV_KEY: list(range(1, 128))}
            self._uinput = UInput(cap, name="turbo-whisper-keyboard")
            self._evdev_available = True
            print("evdev UInput keyboard initialized")
        except PermissionError:
            print("evdev: Permission denied for /dev/uinput")
            print("Fix with: sudo usermod -aG input $USER (then log out/in)")
            self._evdev_available = False
        except Exception as e:
            print(f"evdev unavailable: {e}")
            self._evdev_available = False

    def _build_key_map(self, ecodes) -> dict:
        """Build character to keycode mapping."""
        # US QWERTY layout
        key_map = {
            # Letters (lowercase - no shift)
            'a': (ecodes.KEY_A, False), 'b': (ecodes.KEY_B, False),
            'c': (ecodes.KEY_C, False), 'd': (ecodes.KEY_D, False),
            'e': (ecodes.KEY_E, False), 'f': (ecodes.KEY_F, False),
            'g': (ecodes.KEY_G, False), 'h': (ecodes.KEY_H, False),
            'i': (ecodes.KEY_I, False), 'j': (ecodes.KEY_J, False),
            'k': (ecodes.KEY_K, False), 'l': (ecodes.KEY_L, False),
            'm': (ecodes.KEY_M, False), 'n': (ecodes.KEY_N, False),
            'o': (ecodes.KEY_O, False), 'p': (ecodes.KEY_P, False),
            'q': (ecodes.KEY_Q, False), 'r': (ecodes.KEY_R, False),
            's': (ecodes.KEY_S, False), 't': (ecodes.KEY_T, False),
            'u': (ecodes.KEY_U, False), 'v': (ecodes.KEY_V, False),
            'w': (ecodes.KEY_W, False), 'x': (ecodes.KEY_X, False),
            'y': (ecodes.KEY_Y, False), 'z': (ecodes.KEY_Z, False),
            # Letters (uppercase - with shift)
            'A': (ecodes.KEY_A, True), 'B': (ecodes.KEY_B, True),
            'C': (ecodes.KEY_C, True), 'D': (ecodes.KEY_D, True),
            'E': (ecodes.KEY_E, True), 'F': (ecodes.KEY_F, True),
            'G': (ecodes.KEY_G, True), 'H': (ecodes.KEY_H, True),
            'I': (ecodes.KEY_I, True), 'J': (ecodes.KEY_J, True),
            'K': (ecodes.KEY_K, True), 'L': (ecodes.KEY_L, True),
            'M': (ecodes.KEY_M, True), 'N': (ecodes.KEY_N, True),
            'O': (ecodes.KEY_O, True), 'P': (ecodes.KEY_P, True),
            'Q': (ecodes.KEY_Q, True), 'R': (ecodes.KEY_R, True),
            'S': (ecodes.KEY_S, True), 'T': (ecodes.KEY_T, True),
            'U': (ecodes.KEY_U, True), 'V': (ecodes.KEY_V, True),
            'W': (ecodes.KEY_W, True), 'X': (ecodes.KEY_X, True),
            'Y': (ecodes.KEY_Y, True), 'Z': (ecodes.KEY_Z, True),
            # Numbers
            '1': (ecodes.KEY_1, False), '2': (ecodes.KEY_2, False),
            '3': (ecodes.KEY_3, False), '4': (ecodes.KEY_4, False),
            '5': (ecodes.KEY_5, False), '6': (ecodes.KEY_6, False),
            '7': (ecodes.KEY_7, False), '8': (ecodes.KEY_8, False),
            '9': (ecodes.KEY_9, False), '0': (ecodes.KEY_0, False),
            # Shifted numbers (symbols)
            '!': (ecodes.KEY_1, True), '@': (ecodes.KEY_2, True),
            '#': (ecodes.KEY_3, True), '$': (ecodes.KEY_4, True),
            '%': (ecodes.KEY_5, True), '^': (ecodes.KEY_6, True),
            '&': (ecodes.KEY_7, True), '*': (ecodes.KEY_8, True),
            '(': (ecodes.KEY_9, True), ')': (ecodes.KEY_0, True),
            # Punctuation
            ' ': (ecodes.KEY_SPACE, False),
            '\n': (ecodes.KEY_ENTER, False),
            '\t': (ecodes.KEY_TAB, False),
            '-': (ecodes.KEY_MINUS, False), '_': (ecodes.KEY_MINUS, True),
            '=': (ecodes.KEY_EQUAL, False), '+': (ecodes.KEY_EQUAL, True),
            '[': (ecodes.KEY_LEFTBRACE, False), '{': (ecodes.KEY_LEFTBRACE, True),
            ']': (ecodes.KEY_RIGHTBRACE, False), '}': (ecodes.KEY_RIGHTBRACE, True),
            '\\': (ecodes.KEY_BACKSLASH, False), '|': (ecodes.KEY_BACKSLASH, True),
            ';': (ecodes.KEY_SEMICOLON, False), ':': (ecodes.KEY_SEMICOLON, True),
            "'": (ecodes.KEY_APOSTROPHE, False), '"': (ecodes.KEY_APOSTROPHE, True),
            ',': (ecodes.KEY_COMMA, False), '<': (ecodes.KEY_COMMA, True),
            '.': (ecodes.KEY_DOT, False), '>': (ecodes.KEY_DOT, True),
            '/': (ecodes.KEY_SLASH, False), '?': (ecodes.KEY_SLASH, True),
            '`': (ecodes.KEY_GRAVE, False), '~': (ecodes.KEY_GRAVE, True),
        }
        return key_map

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

        if self.system == "Windows" or self.system == "Darwin":
            return self._type_pyautogui(text)
        else:
            return self._type_linux(text)

    def _type_pyautogui(self, text: str) -> bool:
        """Type text using PyAutoGUI (Windows/macOS)."""
        try:
            import pyautogui
            import time

            # Small delay to let focus settle
            time.sleep(0.1)
            pyautogui.write(text, interval=0.01)
            return True
        except Exception as e:
            print(f"PyAutoGUI typing error: {e}")
            return self.copy_to_clipboard(text)

    def _type_linux(self, text: str) -> bool:
        """Type text on Linux using evdev UInput."""
        import time

        # Small delay to let focus settle after our window hides
        time.sleep(0.05)

        if self._evdev_available and self._uinput:
            try:
                return self._type_evdev(text)
            except Exception as e:
                print(f"evdev typing failed: {e}")

        # Fallback to PyAutoGUI (works on X11)
        try:
            import pyautogui
            pyautogui.write(text, interval=0.01)
            return True
        except Exception as e:
            print(f"PyAutoGUI fallback failed: {e}")

        # Last resort: clipboard
        if self.copy_to_clipboard(text):
            print("Text copied to clipboard - press Ctrl+V to paste")
            return True

        return False

    def _type_evdev(self, text: str) -> bool:
        """Type text using evdev UInput (works on Wayland)."""
        import time

        ecodes = self._ecodes

        for char in text:
            if char in self._key_map:
                keycode, needs_shift = self._key_map[char]

                if needs_shift:
                    self._uinput.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1)
                    self._uinput.syn()

                # Key press
                self._uinput.write(ecodes.EV_KEY, keycode, 1)
                self._uinput.syn()
                # Key release
                self._uinput.write(ecodes.EV_KEY, keycode, 0)
                self._uinput.syn()

                if needs_shift:
                    self._uinput.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
                    self._uinput.syn()

                # Small delay between characters to prevent dropped keystrokes
                time.sleep(0.005)

        return True

    def copy_to_clipboard(self, text: str) -> bool:
        """
        Copy text to clipboard.

        Args:
            text: Text to copy

        Returns:
            True if successful, False otherwise
        """
        if self.system == "Windows":
            try:
                import pyperclip
                pyperclip.copy(text)
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

        # Linux - try multiple clipboard tools
        clipboard_commands = [
            ["wl-copy"],  # Wayland
            ["xclip", "-selection", "clipboard"],  # X11
            ["xsel", "--clipboard", "--input"],  # X11 alternative
        ]

        for cmd in clipboard_commands:
            if shutil.which(cmd[0]):
                try:
                    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
                    proc.communicate(input=text.encode())
                    if proc.returncode == 0:
                        return True
                except Exception:
                    pass

        return False

    def __del__(self):
        """Clean up UInput device."""
        if self._uinput:
            try:
                self._uinput.close()
            except Exception:
                pass
