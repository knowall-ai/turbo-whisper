import struct
import time
from unittest.mock import Mock

import pytest

from turbo_whisper.config import Config
from turbo_whisper.main import TurboWhisper


def wait(qapp, predicate):
    deadline = time.monotonic() + 2
    while not predicate() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.001)
    assert predicate()


@pytest.fixture
def controller(qapp, monkeypatch):
    from turbo_whisper import live, main

    config = Config(
        transcription_backend="local",
        live_transcription=True,
        store_recordings=False,
        claude_integration=False,
    )
    monkeypatch.setattr(Config, "load", classmethod(lambda cls: config))
    monkeypatch.setattr(TurboWhisper, "_setup_activation_server", lambda self: None)
    monkeypatch.setattr(TurboWhisper, "_detect_focused_window", lambda *args: None)
    sessions = []
    start = live.PhraseTranscriber.start

    def tracked_start(session):
        sessions.append(session)
        start(session)

    monkeypatch.setattr(live.PhraseTranscriber, "start", tracked_start)
    recorder = Mock(captured_frames=0, capture_error=None)
    recorder.stop.return_value = b"RIFF-synthetic-complete-audio"
    monkeypatch.setattr(main, "AudioRecorder", lambda config: recorder)
    typer = Mock()
    typer.type_text.return_value = True
    monkeypatch.setattr(main, "Typer", lambda **kw: typer)
    monkeypatch.setattr(
        main.RecordingWindow,
        "_populate_mic_dropdown",
        lambda self: self.mic_combo.addItem("Synthetic input", None),
    )
    view = TurboWhisper()
    view.client = Mock()
    view.client.transcribe_live_sync.side_effect = ["First thought.", "Final thought."]
    yield view
    for session in sessions:
        session.cancel()
        session.thread.join(timeout=2)
        assert not session.thread.is_alive()
    view._live_token += 1
    view._live_session = None
    qapp.processEvents()
    view.window.close()
    view.window.settings_panel.close()
    view.tray.hide()
    view._waveform_timer.stop()
    # Closing only hides Qt objects. Destroy them on the GUI thread instead of
    # leaving controller/signal cycles for GC on a later inference worker.
    from PyQt6.QtCore import QCoreApplication, QEvent

    for obj in [
        view.window.settings_panel,
        view.window,
        view.tray,
        view._waveform_timer,
        view.signals,
    ]:
        obj.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def phrase(controller):
    feed = controller.recorder.start.call_args.kwargs["frame_callback"]
    feed(struct.pack("<h", 5000) * 4800)
    feed(b"\0\0" * 10400)


def test_live_typing_precedes_stop_and_finalization_never_retypes_it(controller, qapp):
    controller._start_recording()
    phrase(controller)
    wait(qapp, lambda: controller.typer.type_text.call_count == 1)
    assert controller.is_recording
    assert not controller.config.history
    feed = controller.recorder.start.call_args.kwargs["frame_callback"]
    feed(struct.pack("<h", 4000) * 2000)
    controller._stop_recording()
    wait(qapp, lambda: not controller.is_transcribing)
    assert [call.args[0] for call in controller.typer.type_text.call_args_list] == [
        "First thought.",
        " Final thought.",
    ]
    assert controller.config.history[0]["text"] == "First thought. Final thought."
    controller.typer.copy_to_clipboard.assert_called_once_with("First thought. Final thought.")


def test_failed_insertion_copies_remaining_text_without_retrying_inserted_phrases(controller, qapp):
    controller.typer.type_text.return_value = False
    controller._start_recording()
    phrase(controller)
    wait(qapp, lambda: controller.typer.type_text.called)
    feed = controller.recorder.start.call_args.kwargs["frame_callback"]
    feed(struct.pack("<h", 3000) * 2000)
    controller._stop_recording()
    wait(qapp, lambda: not controller.is_transcribing)
    controller.typer.type_text.assert_called_once_with("First thought.")
    assert controller.typer.copy_to_clipboard.call_args.args == ("First thought. Final thought.",)
    assert controller.config.history[0]["text"] == "First thought. Final thought."


def test_cancel_restart_ignores_late_result_and_session_lists_remain_separate(controller, qapp):
    controller._start_recording()
    old_token = controller._live_token
    old_session = controller._live_session
    controller._cancel_recording()
    old_session.thread.join(timeout=1)
    controller._start_recording()
    controller._on_live_complete("Stale result.", old_token)
    controller._on_live_error("Stale error.", old_token)
    assert controller.is_recording
    assert controller.config.history == []
    assert controller._live_text == []
    phrase(controller)
    wait(qapp, lambda: controller.typer.type_text.called)
    controller._stop_recording()
    wait(qapp, lambda: not controller.is_transcribing)
    assert controller.config.history[0]["text"] == "First thought."


def test_capture_failure_never_turns_a_short_recording_into_success(controller, qapp):
    controller._start_recording()
    controller.recorder.stop.side_effect = RuntimeError("Capture was interrupted")
    controller._stop_recording()
    assert not controller.is_transcribing
    assert not controller.config.history
    controller.typer.type_text.assert_not_called()
    assert "Capture was interrupted" in controller.window.save_feedback.text()


def test_api_live_mode_is_rejected_before_recording_or_http(controller):
    controller.config.transcription_backend = "api"
    controller._start_recording()
    controller.recorder.start.assert_not_called()
    controller.client.prepare_live.assert_not_called()
    assert "local backend" in controller.window.save_feedback.text()
