"""Render real Qt widgets using synthetic content, without microphone or API access."""

import argparse
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from turbo_whisper.config import Config
from turbo_whisper.main import RecordingWindow


def render(output):
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    config = Config(claude_integration=False)
    config.history = [
        {
            "text": "The best ideas arrive when you can just say them.",
            "timestamp": "2026-10-29T12:30:00",
        }
    ]
    with patch.object(
        RecordingWindow,
        "_populate_mic_dropdown",
        lambda self: self.mic_combo.addItem("System default", None),
    ):
        window = RecordingWindow(config)
    window._toggle_settings()
    for index, name in enumerate(["dictation", "connection", "audio", "history"]):
        window.navigation.setCurrentRow(index)
        app.processEvents()
        app.processEvents()
        assert window.settings_panel.grab().save(str(output / f"{name}.png"))
    window.navigation.setCurrentRow(1)
    window.backend_combo.setCurrentIndex(window.backend_combo.findData("local"))
    app.processEvents()
    assert window.settings_panel.grab().save(str(output / "local-model.png"))
    window.backend_combo.setCurrentIndex(window.backend_combo.findData("whisper_cpp"))
    window.cpp_model_input.setText("~/models/ggml-large-v3-turbo.bin")
    app.processEvents()
    assert window.settings_panel.grab().save(str(output / "whisper-cpp.png"))
    window.settings_panel.resize(740, 560)
    window.navigation.setCurrentRow(0)
    app.processEvents()
    assert window.settings_panel.grab().save(str(output / "small-window.png"))
    window.settings_panel.hide()
    window.show()
    window.waveform.set_recording(True)
    window.set_status("Listening")
    window.set_recording_hint(True)
    for _ in range(12):
        window.waveform.update_waveform(0.6, [0.2, 0.4, 0.8, 0.4, 0.2] * 30)
        window.waveform._animate()
    app.processEvents()
    assert window.grab().save(str(output / "recording.png"))
    window.close()
    window.settings_panel.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("ui-previews"))
    render(parser.parse_args().output)
