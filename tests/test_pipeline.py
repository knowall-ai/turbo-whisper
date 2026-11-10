"""End-to-end controller flow with synthetic audio and an isolated HTTP transport."""

import time
from unittest.mock import Mock

import httpx

from turbo_whisper.config import Config
from turbo_whisper.main import TurboWhisper


def test_record_transcribe_history_and_clipboard(qapp, monkeypatch):
    from turbo_whisper import main

    config = Config(
        api_url="https://example.invalid/transcribe",
        auto_paste=False,
        store_recordings=False,
        claude_integration=False,
    )
    monkeypatch.setattr(Config, "load", classmethod(lambda cls: config))
    monkeypatch.setattr(TurboWhisper, "_setup_activation_server", lambda self: None)
    recorder = Mock()
    recorder.stop.return_value = b"RIFF-synthetic-wave"
    monkeypatch.setattr(main, "AudioRecorder", lambda config: recorder)
    typer = Mock()
    monkeypatch.setattr(main, "Typer", lambda **kw: typer)
    monkeypatch.setattr(
        main.RecordingWindow,
        "_populate_mic_dropdown",
        lambda self: self.mic_combo.addItem("Synthetic microphone", None),
    )
    sync = httpx.Client

    def response(request):
        assert b"RIFF-synthetic-wave" in request.content
        return httpx.Response(200, json={"text": "A complete thought, from voice to text."})

    transport = httpx.MockTransport(response)
    monkeypatch.setattr(httpx, "Client", lambda **kw: sync(transport=transport, **kw))
    controller = TurboWhisper()
    try:
        controller._start_recording()
        assert controller.is_recording
        controller._stop_recording()
        deadline = time.monotonic() + 2
        while controller.is_transcribing and time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.01)
        assert not controller.is_transcribing
        assert config.history[0]["text"] == "A complete thought, from voice to text."
        typer.copy_to_clipboard.assert_called_once_with(config.history[0]["text"])
        typer.type_text.assert_not_called()
        assert controller.window.history_list.count() == 1
    finally:
        controller._work_queue.shutdown()
        controller._work_queue.thread.join(timeout=2)
        controller.window.close()
        controller.window.settings_panel.close()
        controller.tray.hide()
        controller._waveform_timer.stop()
