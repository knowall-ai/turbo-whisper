"""Global hotkey handling with platform-specific backends."""

import os
import threading
import time
from typing import Callable


def is_wayland() -> bool:
    """Check if running on Wayland.

    Note: We default to pynput (X11) because it works on Wayland via XWayland.
    The xdg-desktop-portal GlobalShortcuts is experimental and doesn't work
    reliably on all desktop environments (e.g., KDE Plasma).

    Set TURBO_WHISPER_USE_PORTAL=1 to try the portal backend.
    """
    if os.environ.get("TURBO_WHISPER_USE_PORTAL") == "1":
        return os.environ.get("XDG_SESSION_TYPE") == "wayland"
    return False  # Default to pynput (works via XWayland)


def _format_hotkey_for_portal(hotkey_combo: list[str]) -> str:
    """Convert hotkey combo to portal format (e.g., 'CTRL+SHIFT+space')."""
    parts = []
    for key in hotkey_combo:
        key_lower = key.lower()
        if key_lower in ("ctrl", "ctrl_l", "ctrl_r"):
            parts.append("CTRL")
        elif key_lower in ("alt", "alt_l", "alt_r"):
            parts.append("ALT")
        elif key_lower in ("shift", "shift_l", "shift_r"):
            parts.append("SHIFT")
        elif key_lower in ("super", "cmd"):
            parts.append("SUPER")
        else:
            parts.append(key_lower)
    return "+".join(parts)


class PortalHotkeyManager:
    """Wayland hotkey manager using xdg-desktop-portal GlobalShortcuts."""

    def __init__(self, hotkey_combo: list[str], callback: Callable[[], None]):
        """Initialize portal hotkey manager."""
        # Import here to make dependencies optional
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib

        self.callback = callback
        self.hotkey_combo = hotkey_combo
        self.hotkey_str = _format_hotkey_for_portal(hotkey_combo)
        self._running = False
        self._loop = None
        self._thread = None
        self._session = None

        # D-Bus setup
        DBusGMainLoop(set_as_default=True)
        self._bus = dbus.SessionBus()
        self._portal = self._bus.get_object(
            "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop"
        )

        self._GLib = GLib
        self._dbus = dbus

    def _on_activated(self, session_handle, shortcut_id, timestamp, options):
        """Handle shortcut activation."""
        if shortcut_id == "turbo-whisper-toggle":
            self.callback()

    def _on_session_created(self, response, results):
        """Handle session creation response."""
        if response != 0:
            print(f"Portal: Failed to create session (response={response})")
            return

        self._session = results.get("session_handle")
        if not self._session:
            print("Portal: No session handle in response")
            return

        print(f"Portal: Session created: {self._session}")

        # Register Activated signal on the session path (not desktop path)
        self._bus.add_signal_receiver(
            self._on_activated,
            signal_name="Activated",
            dbus_interface="org.freedesktop.portal.GlobalShortcuts",
            bus_name="org.freedesktop.portal.Desktop",
            path=self._session,
        )
        print(f"Portal: Listening for Activated on {self._session}")

        # Bind the shortcut
        shortcuts = [
            (
                "turbo-whisper-toggle",
                {
                    "description": self._dbus.String("Toggle Turbo Whisper recording"),
                    "preferred-trigger": self._dbus.String(self.hotkey_str),
                },
            ),
        ]

        try:
            self._portal.BindShortcuts(
                self._session,
                shortcuts,
                "",  # parent_window
                {},  # options
                dbus_interface="org.freedesktop.portal.GlobalShortcuts",
            )
            print(f"Portal: Bound shortcut with preferred trigger: {self.hotkey_str}")
        except Exception as e:
            print(f"Portal: Failed to bind shortcuts: {e}")

    def _run_loop(self):
        """Run GLib main loop in background thread."""
        self._loop = self._GLib.MainLoop()
        self._loop.run()

    def start(self) -> None:
        """Start listening for hotkeys via portal."""
        if self._running:
            return

        self._running = True

        # Create session
        options = {
            "handle_token": self._dbus.String("turbo_whisper"),
            "session_handle_token": self._dbus.String("turbo_whisper_session"),
        }

        try:
            reply = self._portal.CreateSession(
                options, dbus_interface="org.freedesktop.portal.GlobalShortcuts"
            )

            # Listen for response
            self._bus.add_signal_receiver(
                self._on_session_created,
                signal_name="Response",
                dbus_interface="org.freedesktop.portal.Request",
                bus_name="org.freedesktop.portal.Desktop",
                path=reply,
            )

            print("Portal: Creating session...")

        except Exception as e:
            print(f"Portal: Failed to create session: {e}")
            self._running = False
            return

        # Start GLib main loop in background thread
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop listening for hotkeys."""
        self._running = False
        if self._loop:
            self._loop.quit()
            self._loop = None
        self._thread = None


class HotkeyManager:
    """Manages global hotkey registration using pynput (X11/Windows/macOS)."""

    def __init__(self, hotkey_combo: list[str], callback: Callable[[], None]):
        """
        Initialize hotkey manager.

        Args:
            hotkey_combo: List of key names, e.g., ["alt", "space"]
            callback: Function to call when hotkey is pressed
        """
        # Import here to make dependency optional (only needed on non-Wayland)
        from pynput import keyboard

        self._keyboard = keyboard

        self.callback = callback
        self.hotkey_combo = self._parse_hotkey(hotkey_combo)
        self.hotkey_chars = self._get_char_keys(hotkey_combo)
        self.current_keys = set()
        self.current_chars = set()
        self.listener = None
        self._running = False
        self._last_trigger = 0
        self._debounce_ms = 300  # Prevent double triggers

    def _get_char_keys(self, combo: list[str]) -> set:
        """Extract single character keys from combo."""
        return {k.lower() for k in combo if len(k) == 1}

    def _parse_hotkey(self, combo: list[str]) -> set:
        """Parse hotkey string names to pynput keys."""
        kb = self._keyboard
        key_map = {
            "alt": kb.Key.alt,
            "alt_l": kb.Key.alt_l,
            "alt_r": kb.Key.alt_r,
            "ctrl": kb.Key.ctrl,
            "ctrl_l": kb.Key.ctrl_l,
            "ctrl_r": kb.Key.ctrl_r,
            "shift": kb.Key.shift,
            "shift_l": kb.Key.shift_l,
            "shift_r": kb.Key.shift_r,
            "cmd": kb.Key.cmd,
            "super": kb.Key.cmd,
            "space": kb.Key.space,
            "tab": kb.Key.tab,
            "enter": kb.Key.enter,
            "esc": kb.Key.esc,
            "backspace": kb.Key.backspace,
            "f1": kb.Key.f1,
            "f2": kb.Key.f2,
            "f3": kb.Key.f3,
            "f4": kb.Key.f4,
            "f5": kb.Key.f5,
            "f6": kb.Key.f6,
            "f7": kb.Key.f7,
            "f8": kb.Key.f8,
            "f9": kb.Key.f9,
            "f10": kb.Key.f10,
            "f11": kb.Key.f11,
            "f12": kb.Key.f12,
        }

        parsed = set()
        for key_name in combo:
            key_lower = key_name.lower()
            if key_lower in key_map:
                parsed.add(key_map[key_lower])
            elif len(key_lower) == 1:
                # Single character key
                parsed.add(kb.KeyCode.from_char(key_lower))
            else:
                print(f"Warning: Unknown key '{key_name}'")

        return parsed

    def _on_press(self, key) -> None:
        """Handle key press event."""
        kb = self._keyboard
        # Track character keys separately
        if hasattr(key, "char") and key.char:
            self.current_chars.add(key.char.lower())
        else:
            self.current_keys.add(key)

        # Check for alt variants
        if key in (kb.Key.alt_l, kb.Key.alt_r):
            self.current_keys.add(kb.Key.alt)
        if key in (kb.Key.ctrl_l, kb.Key.ctrl_r):
            self.current_keys.add(kb.Key.ctrl)
        if key in (kb.Key.shift_l, kb.Key.shift_r):
            self.current_keys.add(kb.Key.shift)

        # Check if hotkey combo is pressed (special keys + char keys)
        special_keys_match = self.hotkey_combo.issubset(self.current_keys)
        char_keys_match = self.hotkey_chars.issubset(self.current_chars)

        if special_keys_match and char_keys_match:
            # Debounce to prevent double triggers
            now = time.time() * 1000
            if now - self._last_trigger > self._debounce_ms:
                self._last_trigger = now
                # Clear key state to ensure next press re-triggers
                # (release events may be lost when window is shown)
                self.current_keys.clear()
                self.current_chars.clear()
                self.callback()

    def _on_release(self, key) -> None:
        """Handle key release event."""
        kb = self._keyboard
        # Clear character keys
        if hasattr(key, "char") and key.char:
            self.current_chars.discard(key.char.lower())
        else:
            self.current_keys.discard(key)

        # Also remove generic versions
        if key in (kb.Key.alt_l, kb.Key.alt_r):
            self.current_keys.discard(kb.Key.alt)
        if key in (kb.Key.ctrl_l, kb.Key.ctrl_r):
            self.current_keys.discard(kb.Key.ctrl)
        if key in (kb.Key.shift_l, kb.Key.shift_r):
            self.current_keys.discard(kb.Key.shift)

    def start(self) -> None:
        """Start listening for hotkeys."""
        if self._running:
            return

        self._running = True
        self.listener = self._keyboard.Listener(
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


def create_hotkey_manager(
    hotkey_combo: list[str], callback: Callable[[], None]
) -> HotkeyManager | PortalHotkeyManager | None:
    """
    Create appropriate hotkey manager for the current platform.

    Returns:
        HotkeyManager for X11/Windows/macOS
        PortalHotkeyManager for Wayland
        None if no backend is available
    """
    if is_wayland():
        try:
            manager = PortalHotkeyManager(hotkey_combo, callback)
            print("Using xdg-desktop-portal for global hotkeys (Wayland)")
            return manager
        except ImportError as e:
            print(f"Portal hotkeys unavailable (missing dependencies): {e}")
            print("Install with: pip install dbus-python PyGObject")
            return None
        except Exception as e:
            print(f"Portal hotkeys unavailable: {e}")
            return None
    else:
        print("Using pynput for global hotkeys (X11/Windows/macOS)")
        return HotkeyManager(hotkey_combo, callback)
