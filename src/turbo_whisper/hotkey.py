"""Global hotkey handling using pynput."""

import threading
from typing import Callable

from pynput import keyboard


class HotkeyManager:
    """Manages global hotkey registration and handling."""

    def __init__(self, hotkey_combo: list[str], callback: Callable[[], None]):
        """
        Initialize hotkey manager.

        Args:
            hotkey_combo: List of key names, e.g., ["alt", "space"]
            callback: Function to call when hotkey is pressed
        """
        self.callback = callback
        self.hotkey_combo = self._parse_hotkey(hotkey_combo)
        self.current_keys = set()
        self.listener = None
        self._running = False

    def _parse_hotkey(self, combo: list[str]) -> set:
        """Parse hotkey string names to pynput keys."""
        key_map = {
            "alt": keyboard.Key.alt,
            "alt_l": keyboard.Key.alt_l,
            "alt_r": keyboard.Key.alt_r,
            "ctrl": keyboard.Key.ctrl,
            "ctrl_l": keyboard.Key.ctrl_l,
            "ctrl_r": keyboard.Key.ctrl_r,
            "shift": keyboard.Key.shift,
            "shift_l": keyboard.Key.shift_l,
            "shift_r": keyboard.Key.shift_r,
            "cmd": keyboard.Key.cmd,
            "super": keyboard.Key.cmd,
            "space": keyboard.Key.space,
            "tab": keyboard.Key.tab,
            "enter": keyboard.Key.enter,
            "esc": keyboard.Key.esc,
            "backspace": keyboard.Key.backspace,
            "f1": keyboard.Key.f1,
            "f2": keyboard.Key.f2,
            "f3": keyboard.Key.f3,
            "f4": keyboard.Key.f4,
            "f5": keyboard.Key.f5,
            "f6": keyboard.Key.f6,
            "f7": keyboard.Key.f7,
            "f8": keyboard.Key.f8,
            "f9": keyboard.Key.f9,
            "f10": keyboard.Key.f10,
            "f11": keyboard.Key.f11,
            "f12": keyboard.Key.f12,
        }

        parsed = set()
        for key_name in combo:
            key_lower = key_name.lower()
            if key_lower in key_map:
                parsed.add(key_map[key_lower])
            elif len(key_lower) == 1:
                # Single character key
                parsed.add(keyboard.KeyCode.from_char(key_lower))
            else:
                print(f"Warning: Unknown key '{key_name}'")

        return parsed

    def _on_press(self, key) -> None:
        """Handle key press event."""
        # Normalize the key
        if hasattr(key, "char"):
            self.current_keys.add(key)
        else:
            self.current_keys.add(key)

        # Check for alt variants
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            self.current_keys.add(keyboard.Key.alt)
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.current_keys.add(keyboard.Key.ctrl)
        if key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
            self.current_keys.add(keyboard.Key.shift)

        # Check if hotkey combo is pressed
        if self.hotkey_combo.issubset(self.current_keys):
            self.callback()

    def _on_release(self, key) -> None:
        """Handle key release event."""
        self.current_keys.discard(key)

        # Also remove generic versions
        if key in (keyboard.Key.alt_l, keyboard.Key.alt_r):
            self.current_keys.discard(keyboard.Key.alt)
        if key in (keyboard.Key.ctrl_l, keyboard.Key.ctrl_r):
            self.current_keys.discard(keyboard.Key.ctrl)
        if key in (keyboard.Key.shift_l, keyboard.Key.shift_r):
            self.current_keys.discard(keyboard.Key.shift)

    def start(self) -> None:
        """Start listening for hotkeys."""
        if self._running:
            return

        self._running = True
        self.listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self.listener.start()

    def stop(self) -> None:
        """Stop listening for hotkeys."""
        self._running = False
        if self.listener:
            self.listener.stop()
            self.listener = None
