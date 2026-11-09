import io
import struct
import threading
import wave
from unittest.mock import Mock

import pytest

from turbo_whisper import recorder
from turbo_whisper.config import Config


def test_linux_microphone_selection_and_wave_encoding(monkeypatch):
    raw = struct.pack("<hhhh", -32768, 0, 32767, 0)
    process = Mock(stdout=io.BytesIO(raw))
    spawn = Mock(return_value=process)
    monkeypatch.setattr(recorder.sys, "platform", "linux")
    monkeypatch.setattr(recorder.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(recorder.subprocess, "Popen", spawn)
    native_audio = Mock(side_effect=AssertionError("Pulse recording must not initialize ALSA"))
    monkeypatch.setattr(recorder.pyaudio, "PyAudio", native_audio)
    audio = recorder.AudioRecorder(Config(input_device_index="alsa_input.synthetic"))
    levels = []
    audio.start(lambda level, buffer: levels.append(level))
    audio._record_thread.join(timeout=1)
    wav = audio.stop()
    assert "--device=alsa_input.synthetic" in spawn.call_args.args[0]
    assert "--latency-msec=20" in spawn.call_args.args[0]
    assert "--process-time-msec=20" in spawn.call_args.args[0]
    process.terminate.assert_called_once()
    with wave.open(io.BytesIO(wav)) as source:
        assert source.getframerate() == 16000
        assert source.getsampwidth() == 2
        assert source.readframes(4) == raw
    assert levels[0] > 0.49  # int16 minimum must not overflow in abs().


def test_empty_recording_is_not_a_header_only_wav(monkeypatch):
    audio = recorder.AudioRecorder(Config())
    assert audio.stop() == b""


def test_stop_drains_audio_already_buffered_in_the_capture_pipe(monkeypatch):
    """Stopping must not discard unread blocks queued before the stop request."""
    reading = threading.Event()
    terminated = threading.Event()
    raw = struct.pack("<h", 1234) * (1024 * 6 + 123)

    class Pipe(io.BytesIO):
        def read(self, size):
            reading.set()
            assert terminated.wait(1)
            return super().read(size)

    process = Mock(stdout=Pipe(raw))
    process.terminate.side_effect = terminated.set
    monkeypatch.setattr(recorder.sys, "platform", "linux")
    monkeypatch.setattr(recorder.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(recorder.subprocess, "Popen", Mock(return_value=process))
    audio = recorder.AudioRecorder(Config())
    audio.start()
    assert reading.wait(1)
    result = audio.stop()
    with wave.open(io.BytesIO(result)) as source:
        assert source.readframes(source.getnframes()) == raw


def test_capture_process_exiting_early_is_reported_instead_of_successful_short_audio(monkeypatch):
    process = Mock(stdout=io.BytesIO(b"\0\0" * 1024))
    process.poll.return_value = 1
    monkeypatch.setattr(recorder.sys, "platform", "linux")
    monkeypatch.setattr(recorder.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(recorder.subprocess, "Popen", Mock(return_value=process))
    audio = recorder.AudioRecorder(Config())
    audio.start()
    audio._record_thread.join(timeout=1)
    with pytest.raises(RuntimeError, match="stopped before recording finished"):
        audio.stop()


def test_repeated_recordings_do_not_reuse_audio_or_meter_history(monkeypatch):
    first, second = struct.pack("<h", 2000) * 1024, struct.pack("<h", 5000) * 300
    processes = [Mock(stdout=io.BytesIO(first)), Mock(stdout=io.BytesIO(second))]
    monkeypatch.setattr(recorder.sys, "platform", "linux")
    monkeypatch.setattr(recorder.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(recorder.subprocess, "Popen", Mock(side_effect=processes))
    audio = recorder.AudioRecorder(Config())
    for raw in [first, second]:
        audio.start()
        audio._record_thread.join(timeout=1)
        with wave.open(io.BytesIO(audio.stop())) as source:
            assert source.readframes(source.getnframes()) == raw
        assert audio.captured_frames == len(raw) // 2
        assert len(audio.waveform_buffer) == 1


def test_pyaudio_overflow_cannot_be_silently_transcribed_as_a_short_success(monkeypatch):
    calls = 0

    def read(size, exception_on_overflow):
        nonlocal calls
        calls += 1
        if calls == 1:
            return b"\0\0" * size
        if exception_on_overflow:
            raise OSError("Input overflowed")
        return b""  # A suppressed overflow would otherwise look like short audio.

    stream = Mock(read=read)
    native = Mock()
    native.open.return_value = stream
    monkeypatch.setattr(recorder.sys, "platform", "darwin")
    monkeypatch.setattr(recorder.pyaudio, "PyAudio", lambda: native)
    audio = recorder.AudioRecorder(Config())
    audio.start()
    audio._record_thread.join(timeout=1)
    with pytest.raises(RuntimeError, match="recording may be incomplete"):
        audio.stop()
    stream.close.assert_called_once()
