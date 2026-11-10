"""Real X11 events, isolated in Xvfb. Never synthesize keys on the user's desktop."""

import os
import time

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("TURBO_WHISPER_TEST_X11") != "1",
    reason="requires an explicitly isolated Xvfb display",
)


def wait_for(predicate):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    assert predicate(), "X11 event did not arrive"


def test_hotkey_is_swallowed_and_release_is_delivered():
    from Xlib import XK, X
    from Xlib.display import Display
    from Xlib.ext.xtest import fake_input

    from turbo_whisper.hotkey import X11GrabHotkeyManager

    display = Display()
    root = display.screen().root
    target = root.create_window(
        0, 0, 100, 100, 0, display.screen().root_depth, event_mask=X.KeyPressMask | X.KeyReleaseMask
    )
    target.map()
    target.set_input_focus(X.RevertToParent, X.CurrentTime)
    display.sync()
    transitions = []
    manager = X11GrabHotkeyManager(
        ["ctrl", "h"], lambda: transitions.append("down"), lambda: transitions.append("up")
    )
    manager.start()
    ctrl = display.keysym_to_keycode(XK.string_to_keysym("Control_L"))
    letter = display.keysym_to_keycode(XK.string_to_keysym("h"))
    try:
        for kind, code in [
            (X.KeyPress, ctrl),
            (X.KeyPress, letter),
            (X.KeyRelease, letter),
            (X.KeyRelease, ctrl),
        ]:
            fake_input(display, kind, code)
        display.sync()
        wait_for(lambda: transitions == ["down", "up"])
        received = []
        while display.pending_events():
            event = display.next_event()
            if event.type == X.KeyPress:
                received.append(event.detail)
        assert letter not in received
        manager.stop()
        fake_input(display, X.KeyPress, letter)
        fake_input(display, X.KeyRelease, letter)
        display.sync()
        wait_for(lambda: bool(display.pending_events()))
        assert any(display.next_event().detail == letter for _ in range(display.pending_events()))
    finally:
        manager.stop()
        target.destroy()
        display.close()


def test_conflicting_grab_is_detected_before_worker_start():
    from turbo_whisper.hotkey import X11GrabHotkeyManager

    first = X11GrabHotkeyManager(["ctrl", "j"], lambda: None)
    try:
        with pytest.raises(RuntimeError, match="already in use"):
            X11GrabHotkeyManager(["ctrl", "j"], lambda: None)
    finally:
        first.stop()
