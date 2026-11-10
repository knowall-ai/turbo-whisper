"""Launcher races use private sockets and mocked locks, never the desktop app."""

import os
import subprocess
import sys
import uuid
from unittest.mock import Mock

import pytest

from turbo_whisper import main


def test_missing_activation_socket_is_not_reported_as_success(qapp, monkeypatch):
    monkeypatch.setattr(main, "_activation_name", lambda: "tw-test-" + uuid.uuid4().hex)
    assert not main._activate_running_instance()


@pytest.mark.skipif(sys.platform == "win32", reason="Unix lock adapter")
def test_relaunch_retries_when_previous_process_is_exiting(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    lock = Mock(side_effect=[BlockingIOError(), BlockingIOError(), None])
    activate = Mock(return_value=False)
    monkeypatch.setattr(main.fcntl, "flock", lock)
    monkeypatch.setattr(main, "_activate_running_instance", activate)
    monkeypatch.setattr(main.time, "sleep", lambda seconds: None)
    try:
        main.ensure_single_instance()
        assert lock.call_count == 3
        assert activate.call_count == 2
    finally:
        if main._lock_fd is not None:
            main.os.close(main._lock_fd)
            main._lock_fd = None


@pytest.mark.parametrize("starting", [True, False], ids=["startup", "shutdown"])
def test_real_launcher_survives_short_process_lifecycle_races(tmp_path, starting):
    # Private namespace for both Unix sockets and Windows lock files.
    tmp_path.chmod(0o700)
    name = "tw-launch-test-" + uuid.uuid4().hex
    setup = (
        "import tempfile; from turbo_whisper import main; "
        f"tempfile.gettempdir=lambda:{str(tmp_path)!r}; "
        f"main._activation_name=lambda:{name!r}; "
    )
    if starting:
        owner = (
            setup
            + """
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
main.ensure_single_instance()
app=QApplication([])
view=object.__new__(main.TurboWhisper)
view.app=app
view._show_settings=lambda: print('activated', flush=True)
QTimer.singleShot(150, view._setup_activation_server)
QTimer.singleShot(4000, app.quit)
print('locked', flush=True)
app.exec()
"""
        )
    else:
        owner = (
            setup
            + """
import time
main.ensure_single_instance()
print('locked', flush=True)
time.sleep(.15)
"""
        )
    env = {**os.environ, "XDG_RUNTIME_DIR": str(tmp_path), "QT_QPA_PLATFORM": "offscreen"}
    # pytest's pythonpath is not necessarily exported to child interpreters.
    env["PYTHONPATH"] = os.pathsep.join(sys.path)
    process = subprocess.Popen(
        [sys.executable, "-c", owner], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        assert process.stdout.readline() == b"locked\n"
        client = subprocess.run(
            [sys.executable, "-c", setup + "main.ensure_single_instance(); print('acquired')"],
            env=env,
            capture_output=True,
            timeout=7,
        )
        assert client.returncode == 0, client.stderr.decode()
        if starting:
            assert b"Opened the running" in client.stdout
            assert process.stdout.readline() == b"activated\n"
        else:
            assert client.stdout == b"acquired\n"
    finally:
        process.terminate()
        process.communicate(timeout=3)
