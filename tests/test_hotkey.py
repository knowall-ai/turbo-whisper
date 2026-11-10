import sys
from dataclasses import dataclass
from enum import Enum
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from turbo_whisper import hotkey


@pytest.fixture
def keyboard(monkeypatch):
    names = [
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
        "cmd_l",
        "cmd_r",
        "space",
        "tab",
        "enter",
        "esc",
        "backspace",
    ] + [f"f{i}" for i in range(1, 13)]
    key = Enum("Key", {name: name for name in names})

    @dataclass(frozen=True)
    class KeyCode:
        char: str

        @classmethod
        def from_char(cls, char):
            return cls(char)

    kb = SimpleNamespace(Key=key, KeyCode=KeyCode)
    monkeypatch.setitem(sys.modules, "pynput", SimpleNamespace(keyboard=kb))
    return kb


def test_letter_shortcut_handles_unrelated_release_and_key_repeat(keyboard):
    pressed, released = Mock(), Mock()
    manager = hotkey.HotkeyManager(["super", "h"], pressed, released)
    manager._on_press(keyboard.Key.cmd_r)
    manager._on_press(keyboard.KeyCode("h"))
    manager._on_press(keyboard.KeyCode("h"))
    pressed.assert_called_once_with()
    manager._on_release(keyboard.KeyCode("x"))
    released.assert_not_called()
    manager._on_release(keyboard.KeyCode("h"))
    released.assert_called_once_with()
    manager._on_press(keyboard.KeyCode("h"))
    assert pressed.call_count == 2


def test_ctrl_character_and_both_modifier_sides(keyboard):
    pressed, released = Mock(), Mock()
    manager = hotkey.HotkeyManager(["ctrl", "w"], pressed, released)
    manager._on_press(keyboard.Key.ctrl_l)
    manager._on_press(keyboard.Key.ctrl_r)
    manager._on_press(keyboard.KeyCode("\x17"))
    pressed.assert_called_once()
    manager._on_release(keyboard.Key.ctrl_l)
    released.assert_not_called()
    manager._on_release(keyboard.Key.ctrl_r)
    released.assert_called_once()


def test_fast_repeated_shortcut_cycles_are_not_debounced_away(keyboard):
    pressed, released = Mock(), Mock()
    manager = hotkey.HotkeyManager(["ctrl", "w"], pressed, released)
    manager._on_press(keyboard.Key.ctrl_l)
    for _ in range(20):
        manager._on_press(keyboard.KeyCode("w"))
        manager._on_release(keyboard.KeyCode("w"))
    assert pressed.call_count == released.call_count == 20


def test_evdev_supports_letters_right_modifiers_and_release(monkeypatch):
    ecodes = SimpleNamespace(KEY_LEFTCTRL=1, KEY_RIGHTCTRL=2, KEY_W=3)
    monkeypatch.setitem(sys.modules, "evdev", SimpleNamespace(ecodes=ecodes))
    monkeypatch.setattr(hotkey.EvdevHotkeyManager, "_open_devices", lambda self: [])
    pressed, released = Mock(), Mock()
    manager = hotkey.EvdevHotkeyManager(["ctrl", "w"], pressed, released)
    manager._update_pressed(10, 2, 1)
    manager._update_pressed(10, 3, 1)
    manager._update_pressed(10, 3, 2)
    pressed.assert_called_once()
    manager._update_pressed(11, 2, 1)
    manager._update_pressed(10, 2, 0)
    released.assert_not_called()
    manager._update_pressed(11, 2, 0)
    released.assert_called_once()


def test_evdev_never_silently_accepts_a_partial_shortcut(monkeypatch):
    monkeypatch.setitem(
        sys.modules, "evdev", SimpleNamespace(ecodes=SimpleNamespace(KEY_LEFTALT=1, KEY_RIGHTALT=2))
    )
    with pytest.raises(ValueError, match="Unsupported"):
        hotkey.EvdevHotkeyManager(["alt", "unrecognized"], Mock())


def test_portal_delivers_release_only_for_its_own_session():
    manager = object.__new__(hotkey.PortalHotkeyManager)
    manager._running = True
    manager._session = "/session/ours"
    manager.on_activate, manager.on_deactivate = Mock(), Mock()
    manager._on_activated("/session/other", "turbo-whisper-toggle", 0, {})
    manager.on_activate.assert_not_called()
    manager._on_activated("/session/ours", "turbo-whisper-toggle", 0, {})
    manager._on_deactivated("/session/ours", "turbo-whisper-toggle", 0, {})
    manager.on_activate.assert_called_once()
    manager.on_deactivate.assert_called_once()


def test_portal_subscribes_before_request_is_sent():
    manager = object.__new__(hotkey.PortalHotkeyManager)
    order = []
    manager._matches = []
    manager._dbus = SimpleNamespace(String=str)
    manager._bus = SimpleNamespace(
        get_unique_name=lambda: ":1.23",
        add_signal_receiver=lambda *a, **k: order.append(("subscribe", k["path"])),
    )
    manager._portal = SimpleNamespace(
        CreateSession=lambda *a, **k: order.append(("call", a[-1]["handle_token"]))
    )
    manager._request("CreateSession", [], Mock())
    assert order[0][0] == "subscribe" and order[1][0] == "call"
    assert order[0][1].endswith("/" + order[1][1])


def test_wayland_fallback_is_real_and_never_uses_xwayland(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    monkeypatch.delenv("TURBO_WHISPER_USE_EVDEV", raising=False)
    portal = Mock(side_effect=RuntimeError("not supported"))
    evdev = Mock(side_effect=PermissionError("no device access"))
    native = Mock()
    # Factory logs class names; mocks have to identify themselves like classes.
    portal.__name__, evdev.__name__ = "Portal", "Evdev"
    monkeypatch.setattr(hotkey, "PortalHotkeyManager", portal)
    monkeypatch.setattr(hotkey, "EvdevHotkeyManager", evdev)
    monkeypatch.setattr(hotkey, "HotkeyManager", native)
    assert hotkey.create_hotkey_manager(["alt", "space"], Mock()) is None
    portal.assert_called_once()
    evdev.assert_called_once()
    native.assert_not_called()


@pytest.mark.parametrize(
    "key,expected", [("space", "space"), ("enter", "Return"), ("esc", "Escape"), ("f8", "F8")]
)
def test_x11_special_key_names(monkeypatch, key, expected):
    manager = object.__new__(hotkey.X11GrabHotkeyManager)
    manager.hotkey_combo = ["ctrl", key]
    symbols = []
    monkeypatch.setitem(
        sys.modules,
        "Xlib",
        SimpleNamespace(
            X=SimpleNamespace(Mod4Mask=64, ControlMask=4, Mod1Mask=8, ShiftMask=1),
            XK=SimpleNamespace(string_to_keysym=lambda name: symbols.append(name) or 42),
        ),
    )
    assert manager._resolve(SimpleNamespace(keysym_to_keycode=lambda symbol: symbol)) == (4, 42)
    assert symbols == [expected]


def test_native_portal_connection_identifies_the_app_before_any_portal_call(monkeypatch):
    order = []
    portal = SimpleNamespace(
        Register=lambda *a, **kw: order.append(("register", a[0])),
        Get=lambda *a, **kw: order.append(("capability", a[0])) or 2,
    )
    bus = Mock()
    bus.get_object.return_value = portal
    dbus = SimpleNamespace(SessionBus=Mock(return_value=bus), DBusException=RuntimeError)
    monkeypatch.setitem(sys.modules, "dbus", dbus)
    monkeypatch.setitem(sys.modules, "dbus.mainloop", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "dbus.mainloop.glib", SimpleNamespace(DBusGMainLoop=Mock()))
    monkeypatch.setitem(sys.modules, "gi", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "gi.repository", SimpleNamespace(GLib=Mock()))
    hotkey.PortalHotkeyManager(["alt", "space"], Mock())
    dbus.SessionBus.assert_called_once_with(private=True)
    assert order == [
        ("register", "turbo-whisper"),
        ("capability", hotkey.PortalHotkeyManager.INTERFACE),
    ]
