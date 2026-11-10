"""Tests never touch the user's configuration, microphone, or keyboard devices."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def private_config(tmp_path, monkeypatch):
    monkeypatch.delenv("TURBO_WHISPER_CONFIG", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("APPDATA", str(tmp_path))


@pytest.fixture(scope="session")
def qapp():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    return app


@pytest.fixture
def window(qapp, monkeypatch):
    from turbo_whisper.config import Config
    from turbo_whisper.main import RecordingWindow

    monkeypatch.setattr(
        RecordingWindow,
        "_populate_mic_dropdown",
        lambda self: self.mic_combo.addItem("System default", None),
    )
    view = RecordingWindow(Config(claude_integration=False))
    yield view
    view.settings_panel.close()
    view.close()
    qapp.processEvents()
