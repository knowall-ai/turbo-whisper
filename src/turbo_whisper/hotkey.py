"""Global hotkey handling with platform-specific backends."""

import os
import platform
import select
import threading
from typing import Callable


def is_wayland() -> bool:
    """Use native Wayland backends rather than assuming XWayland can see all keys."""
    return os.environ.get("XDG_SESSION_TYPE") == "wayland" or bool(
        os.environ.get("WAYLAND_DISPLAY")
    )


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
    """Native Wayland shortcuts with permission-mediated press and release events."""

    INTERFACE = "org.freedesktop.portal.GlobalShortcuts"
    PATH = "/org/freedesktop/portal/desktop"

    def __init__(self, hotkey_combo, on_activate, on_deactivate=None):
        import dbus
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib

        modifiers = {
            "alt",
            "alt_l",
            "alt_r",
            "ctrl",
            "ctrl_l",
            "ctrl_r",
            "shift",
            "shift_l",
            "shift_r",
            "cmd",
            "super",
        }
        if not any(key not in modifiers for key in hotkey_combo):
            raise ValueError("The desktop shortcut portal needs a non-modifier key")
        self.on_activate = on_activate
        self.on_deactivate = on_deactivate
        self.on_status = lambda text: None
        self.hotkey_str = _format_hotkey_for_portal(hotkey_combo)
        self._dbus = dbus
        self._GLib = GLib
        self._session = None
        self._running = False
        self._thread = None
        self._loop = None
        self._matches = []
        DBusGMainLoop(set_as_default=True)
        self._bus = dbus.SessionBus(private=True)
        self._portal = self._bus.get_object("org.freedesktop.portal.Desktop", self.PATH)
        # Native (unsandboxed) applications must identify the connection before
        # their first portal call; otherwise GNOME rejects CreateSession.
        try:
            self._portal.Register(
                "turbo-whisper", {}, dbus_interface="org.freedesktop.host.portal.Registry"
            )
        except dbus.DBusException:
            # Older portals lack Registry; desktop-launched apps may already be identified.
            pass
        # Fail synchronously if this desktop does not implement GlobalShortcuts.
        self._portal.Get(
            self.INTERFACE, "version", dbus_interface="org.freedesktop.DBus.Properties"
        )

    def _on_activated(self, session_handle, shortcut_id, timestamp, options):
        if (
            self._running
            and session_handle == self._session
            and shortcut_id == "turbo-whisper-toggle"
        ):
            self.on_activate()

    def _on_deactivated(self, session_handle, shortcut_id, timestamp, options):
        if (
            self._running
            and session_handle == self._session
            and shortcut_id == "turbo-whisper-toggle"
            and self.on_deactivate
        ):
            self.on_deactivate()

    def _request(self, method, args, callback, extra=None):
        import uuid

        token = "turbo_" + uuid.uuid4().hex
        sender = self._bus.get_unique_name().lstrip(":").replace(".", "_")
        request_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
        # Subscribe before the call: a fast portal can respond before it returns.
        match = self._bus.add_signal_receiver(
            callback,
            signal_name="Response",
            dbus_interface="org.freedesktop.portal.Request",
            bus_name="org.freedesktop.portal.Desktop",
            path=request_path,
        )
        self._matches.append(match)
        options = {"handle_token": self._dbus.String(token), **(extra or {})}
        getattr(self._portal, method)(*args, options, dbus_interface=self.INTERFACE)

    def _on_session_created(self, response, results):
        if not self._running:
            return
        if response != 0 or not results.get("session_handle"):
            self.on_status(
                "Shortcut permission was not granted. Use Start dictation or try another shortcut."
            )
            return
        self._session = results["session_handle"]
        for name, callback in [
            ("Activated", self._on_activated),
            ("Deactivated", self._on_deactivated),
        ]:
            self._matches.append(
                self._bus.add_signal_receiver(
                    callback,
                    signal_name=name,
                    dbus_interface=self.INTERFACE,
                    bus_name="org.freedesktop.portal.Desktop",
                    path=self.PATH,
                )
            )
        shortcuts = [
            (
                "turbo-whisper-toggle",
                {
                    "description": self._dbus.String("Record with Turbo Whisper"),
                    "preferred_trigger": self._dbus.String(self.hotkey_str),
                },
            )
        ]
        try:
            self._request("BindShortcuts", [self._session, shortcuts, ""], self._on_bound)
        except Exception:
            self.on_status("Could not bind the shortcut. You can still use Start dictation.")

    def _on_bound(self, response, results):
        if not self._running:
            return
        shortcuts = results.get("shortcuts", [])
        if response == 0 and any(str(item[0]) == "turbo-whisper-toggle" for item in shortcuts):
            self.on_status("Desktop shortcut ready. You can change it in your desktop settings.")
        else:
            self.on_status(
                "Shortcut permission was not granted. You can still use Start dictation."
            )

    def start(self):
        if self._running:
            return
        self._running = True
        self._loop = self._GLib.MainLoop()
        self._thread = threading.Thread(target=self._loop.run, daemon=True)
        self._thread.start()
        self.on_status("Confirm the desktop's shortcut permission dialog to enable the hotkey.")
        try:
            import uuid

            self._request(
                "CreateSession",
                [],
                self._on_session_created,
                {"session_handle_token": self._dbus.String("turbo_" + uuid.uuid4().hex)},
            )
        except Exception:
            self.stop()
            raise

    def stop(self):
        self._running = False
        for match in self._matches:
            match.remove()
        self._matches = []
        if self._session:
            try:
                self._bus.get_object("org.freedesktop.portal.Desktop", self._session).Close(
                    dbus_interface="org.freedesktop.portal.Session"
                )
            except Exception:
                pass
            self._session = None
        if self._loop:
            self._loop.quit()
        if self._thread:
            self._thread.join(timeout=1)
        self._loop = self._thread = None
        self._bus.close()


class HotkeyManager:
    """Manages global hotkey registration using pynput (X11/Windows/macOS)."""

    def __init__(
        self,
        hotkey_combo: list[str],
        on_activate: Callable[[], None],
        on_deactivate: Callable[[], None] | None = None,
    ):
        """
        Initialize hotkey manager.

        Args:
            hotkey_combo: List of key names, e.g., ["alt", "space"]
            on_activate: Function to call when hotkey combo is pressed
            on_deactivate: Function to call when hotkey combo is released
        """
        # Import here to make dependency optional (only needed on non-Wayland)
        from pynput import keyboard

        self._keyboard = keyboard

        self.on_activate = on_activate
        self.on_deactivate = on_deactivate
        self.hotkey_combo = self._parse_hotkey(hotkey_combo)
        self.hotkey_chars = self._get_char_keys(hotkey_combo)
        self.current_keys = set()
        self.current_chars = set()
        self._combo_active = False
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

    def _matches(self):
        kb = self._keyboard
        aliases = set(self.current_keys)
        for generic, left, right in [
            (kb.Key.alt, kb.Key.alt_l, kb.Key.alt_r),
            (kb.Key.ctrl, kb.Key.ctrl_l, kb.Key.ctrl_r),
            (kb.Key.shift, kb.Key.shift_l, kb.Key.shift_r),
            (kb.Key.cmd, kb.Key.cmd_l, kb.Key.cmd_r),
        ]:
            if left in aliases or right in aliases:
                aliases.add(generic)
        special = {key for key in self.hotkey_combo if not isinstance(key, kb.KeyCode)}
        return special.issubset(aliases) and self.hotkey_chars.issubset(self.current_chars)

    @staticmethod
    def _character(key):
        char = getattr(key, "char", None)
        if char and len(char) == 1 and 1 <= ord(char) <= 26:
            return chr(ord(char) + 96)
        return char.lower() if char else None

    def _on_press(self, key):
        char = self._character(key)
        if char:
            self.current_chars.add(char)
        else:
            self.current_keys.add(key)
        if self._matches() and not self._combo_active:
            self._combo_active = True
            self.on_activate()

    def _on_release(self, key):
        char = self._character(key)
        if char:
            self.current_chars.discard(char)
        else:
            self.current_keys.discard(key)
        if self._combo_active and not self._matches():
            self._combo_active = False
            if self.on_deactivate:
                self.on_deactivate()

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


class X11GrabHotkeyManager:
    """Consume an X11 shortcut without leaking its key into the focused app."""

    def __init__(self, hotkey_combo, callback, on_deactivate=None):
        from Xlib import X, error
        from Xlib.display import Display

        self.callback = callback
        self.on_deactivate = on_deactivate
        self.hotkey_combo = [k.lower() for k in hotkey_combo]
        self._running = False
        self._active = False
        self._thread = None
        self._disp = Display()  # Probe before factory selection, not in a doomed worker.
        root = self._disp.screen().root
        try:
            mod, self._keycode = self._resolve(self._disp)
            if not self._keycode:
                raise ValueError("X11 shortcut needs exactly one non-modifier key")
            self._masks = []
            for locks in range(8):
                variant = (
                    mod
                    | (X.LockMask if locks & 1 else 0)
                    | (X.Mod2Mask if locks & 2 else 0)
                    | (X.Mod5Mask if locks & 4 else 0)
                )
                catcher = error.CatchError(error.BadAccess)
                root.grab_key(
                    self._keycode, variant, False, X.GrabModeAsync, X.GrabModeAsync, onerror=catcher
                )
                self._disp.sync()
                if not catcher.get_error():
                    self._masks.append(variant)
            if not self._masks:
                raise RuntimeError("The shortcut is already in use")
        except Exception:
            self._disp.close()
            self._disp = None
            raise

    def _resolve(self, disp):
        from Xlib import XK, X

        modifiers = {
            "super": X.Mod4Mask,
            "cmd": X.Mod4Mask,
            "ctrl": X.ControlMask,
            "alt": X.Mod1Mask,
            "shift": X.ShiftMask,
        }
        mod = 0
        keys = []
        for key in self.hotkey_combo:
            generic = key.removesuffix("_l").removesuffix("_r")
            if generic in modifiers:
                mod |= modifiers[generic]
            else:
                keys.append(key)
        if len(keys) != 1:
            return None, None
        special = {
            "space": "space",
            "enter": "Return",
            "tab": "Tab",
            "esc": "Escape",
            "backspace": "BackSpace",
        }
        name = special.get(keys[0], keys[0].upper() if keys[0].startswith("f") else keys[0])
        return mod, disp.keysym_to_keycode(XK.string_to_keysym(name))

    def _run(self):
        from Xlib import X

        pending = None
        try:
            while self._running:
                if pending is None and not self._disp.pending_events():
                    if not select.select([self._disp.fileno()], [], [], 0.15)[0]:
                        continue
                event = pending if pending is not None else self._disp.next_event()
                pending = None
                if event.type not in (X.KeyPress, X.KeyRelease):
                    continue
                if event.detail != self._keycode:
                    continue
                if event.type == X.KeyPress and not self._active:
                    self._active = True
                    self.callback()
                elif event.type == X.KeyRelease:
                    # X11 auto-repeat can emit release/press pairs at the same timestamp.
                    if self._disp.pending_events():
                        following = self._disp.next_event()
                        if (
                            following.type == X.KeyPress
                            and following.detail == event.detail
                            and following.time == event.time
                        ):
                            continue
                        pending = following
                    if self._active:
                        self._active = False
                        if self.on_deactivate:
                            self.on_deactivate()
        finally:
            self._close()

    def _close(self):
        if self._disp is not None:
            try:
                root = self._disp.screen().root
                for mask in self._masks:
                    root.ungrab_key(self._keycode, mask)
                self._disp.sync()
            finally:
                self._disp.close()
                self._disp = None

    def start(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None
        else:
            self._close()


class EvdevHotkeyManager:
    """Non-exclusive Linux keyboard reader, used only with existing device access."""

    def __init__(self, hotkey_combo, callback, on_deactivate=None):
        from evdev import ecodes

        self._ecodes = ecodes
        self.callback = callback
        self.on_deactivate = on_deactivate
        self._groups = []
        names = {"super": "META", "cmd": "META", "ctrl": "CTRL", "alt": "ALT", "shift": "SHIFT"}
        special = {
            "space": "SPACE",
            "enter": "ENTER",
            "tab": "TAB",
            "esc": "ESC",
            "backspace": "BACKSPACE",
        }
        for raw in hotkey_combo:
            key = raw.lower()
            generic = key.removesuffix("_l").removesuffix("_r")
            if generic in names:
                sides = (
                    ["LEFT", "RIGHT"]
                    if key == generic
                    else ["RIGHT" if key.endswith("_r") else "LEFT"]
                )
                self._groups.append(
                    {getattr(ecodes, "KEY_" + side + names[generic]) for side in sides}
                )
            else:
                name = special.get(key, key.upper())
                if not (
                    (len(key) == 1 and key.isascii() and key.isalnum())
                    or key in special
                    or key in {f"f{i}" for i in range(1, 13)}
                ):
                    raise ValueError(f"Unsupported evdev key: {raw}")
                self._groups.append({getattr(ecodes, "KEY_" + name)})
        if not self._groups:
            raise ValueError("A shortcut cannot be empty")
        self._running = False
        self._thread = None
        self._pressed = {}
        self._combo_active = False
        self._devices = self._open_devices()

    def _open_devices(self):
        from evdev import InputDevice, list_devices

        devices = []
        for path in list_devices():
            try:
                device = InputDevice(path)
                keys = device.capabilities().get(self._ecodes.EV_KEY, [])
                if self._ecodes.KEY_A in keys and not device.name.startswith("turbo-whisper"):
                    devices.append(device)
                else:
                    device.close()
            except OSError:
                continue
        if not devices:
            raise RuntimeError("No readable keyboard devices; use the desktop shortcut portal")
        return devices

    def _update_pressed(self, fd, code, value):
        held = self._pressed.setdefault(fd, set())
        if value in (1, 2):
            held.add(code)
        elif value == 0:
            held.discard(code)
        keys = set().union(*self._pressed.values())
        active = all(group & keys for group in self._groups)
        if active and not self._combo_active:
            self._combo_active = True
            self.callback()
        elif not active and self._combo_active:
            self._combo_active = False
            if self.on_deactivate:
                self.on_deactivate()

    def _run(self):
        devices = {d.fd: d for d in self._devices}
        try:
            while self._running and devices:
                ready, _, _ = select.select(list(devices), [], [], 0.15)
                for fd in ready:
                    try:
                        for event in devices[fd].read():
                            if event.type == self._ecodes.EV_KEY:
                                self._update_pressed(fd, event.code, event.value)
                    except BlockingIOError:
                        continue
                    except OSError:
                        devices.pop(fd).close()
                        self._pressed.pop(fd, None)
                        self._update_pressed(fd, 0, 0)
        finally:
            for device in self._devices:
                device.close()
            self._devices = []

    def start(self):
        if not self._running:
            self._running = True
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None
        else:
            for device in self._devices:
                device.close()
            self._devices = []


def create_hotkey_manager(
    hotkey_combo: list[str],
    on_activate: Callable[[], None],
    on_deactivate: Callable[[], None] | None = None,
) -> HotkeyManager | PortalHotkeyManager | EvdevHotkeyManager | X11GrabHotkeyManager | None:
    """Select an available backend; leave manual recording usable if none is available."""
    if is_wayland():
        # An explicit portal preference is useful on GNOME without input-device permissions.
        backends = [PortalHotkeyManager, EvdevHotkeyManager]
        if os.environ.get("TURBO_WHISPER_USE_EVDEV") == "1":
            backends.reverse()
    elif platform.system() == "Linux" and os.environ.get("DISPLAY"):
        backends = [X11GrabHotkeyManager, HotkeyManager]
    else:
        backends = [HotkeyManager]
    for backend in backends:
        try:
            manager = backend(hotkey_combo, on_activate, on_deactivate)
            print(f"Using {backend.__name__} for global hotkeys")
            return manager
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            print(f"{backend.__name__} unavailable: {exc}")
        except Exception as exc:
            print(f"Could not register global hotkey: {exc}")
    return None
