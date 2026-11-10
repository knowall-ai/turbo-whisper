from unittest.mock import Mock

from turbo_whisper.typer import Typer


def test_x11_fallback_preserves_text_and_delay(monkeypatch):
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("XDG_SESSION_TYPE", "x11")
    monkeypatch.setattr("turbo_whisper.typer.shutil.which", lambda name: "/usr/bin/" + name)
    run = Mock()
    monkeypatch.setattr("turbo_whisper.typer.subprocess.run", run)
    typer = object.__new__(Typer)
    typer._evdev_available = False
    typer._uinput = None
    typer._typing_delay = 0.012
    assert typer._type_linux("--héllo; $(not-a-command)")
    assert run.call_args.args[0] == [
        "xdotool",
        "type",
        "--clearmodifiers",
        "--delay",
        "12",
        "--",
        "--héllo; $(not-a-command)",
    ]


def test_wayland_never_reports_xdotool_as_native_typing(monkeypatch):
    monkeypatch.setenv("XDG_SESSION_TYPE", "wayland")
    typer = object.__new__(Typer)
    typer._evdev_available = False
    typer._uinput = None
    typer.copy_to_clipboard = Mock(return_value=True)
    run = Mock()
    monkeypatch.setattr("turbo_whisper.typer.subprocess.run", run)
    assert not typer._type_linux("hello")
    run.assert_not_called()
    typer.copy_to_clipboard.assert_called_once_with("hello")
