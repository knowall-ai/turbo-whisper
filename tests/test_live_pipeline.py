import io
import struct
import threading
import time
import wave
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

    def tracked_start(session, *args):
        sessions.append(session)
        start(session, *args)

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
        session.join(timeout=2)
        assert not session.is_alive()
    view._work_queue.shutdown()
    view._work_queue.thread.join(timeout=2)
    view.writer.close()
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
    old_session.join(timeout=1)
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


def test_rapid_restart_captures_while_previous_session_is_finishing(controller, qapp):
    entered, release = threading.Event(), threading.Event()

    def delayed(audio):
        entered.set()
        assert release.wait(2)
        return "First thought."

    controller.client.transcribe_live_sync.side_effect = delayed
    controller._toggle_recording()
    phrase(controller)
    assert entered.wait(1)
    controller._toggle_recording()
    assert controller.is_transcribing
    try:
        controller._toggle_recording()
        assert controller.is_recording, "A rapid start must not be silently dropped"
        assert controller.recorder.start.call_count == 2
    finally:
        release.set()


def test_old_result_cannot_hide_or_reset_new_capture(controller, qapp):
    entered, release = threading.Event(), threading.Event()

    def delayed(audio):
        entered.set()
        assert release.wait(2)
        return "Previous session."

    controller.client.transcribe_live_sync.side_effect = delayed
    controller._start_recording()
    phrase(controller)
    assert entered.wait(1)
    controller._stop_recording()
    controller._start_recording()
    active = controller._active_session
    try:
        release.set()
        wait(qapp, lambda: len(controller.config.history) == 1)
        assert controller.config.history[0]["text"] == "Previous session."
        assert controller.is_recording
        assert controller.window.isVisible()
        assert controller._waveform_timer.isActive()
        assert controller._active_session is active
        controller._cancel_recording()
    finally:
        release.set()


@pytest.mark.parametrize("live", [True, False])
def test_rapid_sessions_keep_fifo_text_and_unique_audio_files(
    controller, qapp, tmp_path, monkeypatch, live
):
    controller.config.live_transcription = live
    controller.config.store_recordings = True
    monkeypatch.setattr(Config, "get_recordings_dir", lambda self: tmp_path)
    entered, release = threading.Event(), threading.Event()
    calls = []

    def delayed(audio):
        calls.append(audio)
        if len(calls) == 1:
            entered.set()
            assert release.wait(2)
        return f"Session {len(calls)}."

    client = controller.client
    client.transcribe_live_sync.side_effect = delayed
    client.transcribe_sync.side_effect = delayed
    audio = []
    try:
        for index in range(5):
            controller._start_recording()
            assert controller.is_recording
            if live:
                phrase(controller)
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                wav.writeframes(struct.pack("<h", index + 1) * 160)
            clip = buffer.getvalue()
            audio.append(clip)
            controller.recorder.stop.return_value = clip
            controller._stop_recording()
            if index == 0:
                assert entered.wait(1)
        assert len(controller._sessions) == 5
        release.set()
        wait(qapp, lambda: not controller.is_transcribing)
        assert [item["text"] for item in reversed(controller.config.history)] == [
            f"Session {index}." for index in range(1, 6)
        ]
        assert [call.args[0] for call in controller.typer.type_text.call_args_list] == [
            f"Session {index}." for index in range(1, 6)
        ]
        files = [item["audio_file"] for item in reversed(controller.config.history)]
        assert len(set(files)) == 5
        assert [(tmp_path / name).read_bytes() for name in files] == audio
        if not live:
            assert calls == audio
    finally:
        release.set()


def test_empty_taps_then_short_audio_flush_and_cancel_recover(controller, qapp):
    controller.recorder.stop.return_value = b""
    for _ in range(10):
        controller._toggle_recording()
        assert controller.is_recording
        controller._toggle_recording()
        assert not controller.is_recording
        assert not controller.is_transcribing
        assert not controller._sessions
    controller.recorder.stop.return_value = b"RIFF-short-audio"
    controller._start_recording()
    feed = controller.recorder.start.call_args.kwargs["frame_callback"]
    feed(struct.pack("<h", 5000) * 1600)  # 100 ms, no pause endpoint
    controller._stop_recording()
    controller._start_recording()
    controller._cancel_recording()
    wait(qapp, lambda: len(controller.config.history) == 1)
    assert controller.config.history[0]["text"] == "First thought."
    assert not controller.is_transcribing
    controller._start_recording()
    assert controller.is_recording
    controller._cancel_recording()


def test_slow_batch_typing_leaves_gui_available_for_next_toggle(controller, qapp):
    controller.config.live_transcription = False
    controller.client.transcribe_sync.return_value = "A complete thought."
    entered, release = threading.Event(), threading.Event()

    def type_slowly(text):
        entered.set()
        assert release.wait(2)
        return True

    controller.typer.type_text.side_effect = type_slowly
    try:
        controller._start_recording()
        controller._stop_recording()
        assert entered.wait(1), "Typing must run without needing the GUI event loop"
        controller._toggle_recording()
        assert controller.is_recording
        controller._cancel_recording()
        release.set()
        wait(qapp, lambda: not controller.is_transcribing)
    finally:
        release.set()


def test_reopening_window_during_capture_preserves_recording_status(controller, monkeypatch):
    waveform = Mock()
    monkeypatch.setattr(controller.window.waveform, "set_recording", waveform)
    controller._start_recording()
    controller.window.set_status("Listening · 1.0 s recorded")
    controller._show_window()
    assert controller.is_recording
    waveform.assert_called_with(True)
    assert "Listening" in controller.window.status_label.text()
    controller._cancel_recording()


def test_old_error_does_not_interrupt_new_capture(controller, qapp):
    controller._start_recording()
    old = controller._active_session
    controller._stop_recording()
    controller._start_recording()
    current = controller._active_session
    controller._on_live_error("Synthetic old failure", old.token)
    assert controller.is_recording
    assert controller._active_session is current
    assert controller._waveform_timer.isActive()
    assert controller.window.isVisible()
    controller._cancel_recording()


def test_queue_limit_is_visible_and_does_not_capture_unserviceable_audio(controller):
    from turbo_whisper.sessions import DictationSession

    for token in range(controller._work_queue.capacity):
        controller._sessions[token] = DictationSession(token, True, True, stopped=True)
    controller._start_recording()
    assert not controller.is_recording
    controller.recorder.start.assert_not_called()
    assert "queue full" in controller.window.status_label.text().lower()
    controller._sessions.clear()


def setup_writer(controller, monkeypatch, result):
    from concurrent.futures import Future

    from turbo_whisper.polish import LocalPolisher

    controller.config.writer_polish = True
    controller.config.polish_model = "local-test"
    binding = Future()
    binding.set_result({})
    controller.writer = Mock()
    controller.writer.begin.return_value = binding
    polish = Mock(return_value=result)
    monkeypatch.setattr(LocalPolisher, "polish", polish)
    return polish


def test_writer_inserts_live_then_polishes_full_session_and_holds_tail(
    controller, qapp, monkeypatch
):
    from turbo_whisper.polish import PolishResult

    raw = "She go to work. Because the train was delayed."
    final = "She goes to work. Because the train was delayed."
    polish = setup_writer(
        controller,
        monkeypatch,
        PolishResult(
            final,
            "incomplete",
            "Unfinished sentence — provisional in Writer",
            "Because the train was delayed.",
        ),
    )
    controller.client.transcribe_live_sync.side_effect = [
        "She go to work.",
        "Because the train was delayed.",
    ]
    controller._start_recording()
    phrase(controller)
    wait(qapp, lambda: controller.writer.call.called)
    assert controller.is_recording
    assert not polish.called
    assert controller.writer.call.call_args.args == ("append",)
    feed = controller.recorder.start.call_args.kwargs["frame_callback"]
    feed(struct.pack("<h", 4000) * 1600)
    controller._stop_recording()
    wait(qapp, lambda: not controller.is_transcribing)
    polish.assert_called_once_with(raw, "en")
    operations = [call.args[0] for call in controller.writer.call.call_args_list]
    assert operations == ["append", "append", "replace"]
    assert controller.writer.call.call_args.kwargs["text"] == final
    assert "provisional" in controller.writer.call.call_args.kwargs["message"]
    entry = controller.config.history[0]
    assert entry["text"] == final
    assert entry["dictation_review"]["source_text"] == raw
    assert entry["dictation_review"]["incomplete_tail"] == "Because the train was delayed."
    assert controller.window.review_list.count() == 1
    controller.typer.type_text.assert_not_called()

    # Completing/reviewing edits only the same range, once. Original words remain
    # available for comparison, and the existing history entry is updated.
    reviewed = "She goes to work because the train was delayed."
    controller.window.review_text.setPlainText(reviewed)
    controller.window._request_review_apply()
    wait(qapp, lambda: entry["dictation_review"]["status"] == "reviewed")
    assert len(controller.config.history) == 1
    assert entry["text"] == reviewed
    assert entry["dictation_review"]["source_text"] == raw
    assert controller.writer.call.call_args.kwargs["text"] == reviewed
    assert controller.writer.call.call_args.kwargs["id"] == entry["dictation_review"]["writer_id"]


def test_writer_conflict_retains_original_and_suggestion_for_review(controller, qapp, monkeypatch):
    from turbo_whisper.polish import PolishResult
    from turbo_whisper.writer import WriterError

    setup_writer(controller, monkeypatch, PolishResult("First thought!", "polished", "Polished"))

    def call(operation, **arguments):
        if operation == "replace":
            raise WriterError("Dictated text was edited in Writer; automatic replacement stopped")
        return {}

    controller.writer.call.side_effect = call
    controller._start_recording()
    phrase(controller)
    controller._stop_recording()
    wait(qapp, lambda: not controller.is_transcribing)
    entry = controller.config.history[0]
    assert entry["text"] == "First thought."
    assert entry["dictation_review"]["status"] == "review"
    assert entry["dictation_review"]["proposed_text"] == "First thought!"
    assert "edited in Writer" in controller.window.review_feedback.text()
    controller.typer.type_text.assert_not_called()


def test_unavailable_correction_marks_writer_text_provisional_without_retyping(
    controller, qapp, monkeypatch
):
    from turbo_whisper.polish import PolishResult

    setup_writer(
        controller, monkeypatch, PolishResult("First thought.", "review", "Correction unavailable")
    )
    controller._start_recording()
    phrase(controller)
    controller._stop_recording()
    wait(qapp, lambda: not controller.is_transcribing)
    assert [call.args[0] for call in controller.writer.call.call_args_list] == ["append", "mark"]
    assert controller.config.history[0]["dictation_review"]["status"] == "review"
    controller.typer.type_text.assert_not_called()
