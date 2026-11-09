import io
import struct
import threading
import wave
from unittest.mock import Mock

import pytest

from turbo_whisper.live import PhraseTranscriber


def pcm(value, seconds, rate=16000):
    return struct.pack("<h", value) * round(seconds * rate)


def unpack(audio):
    with wave.open(io.BytesIO(audio)) as source:
        return source.readframes(source.getnframes())


def session(infer=None):
    inputs, phrases, completed, errors = [], [], [], []
    delivered = threading.Event()

    def transcribe(audio):
        inputs.append(unpack(audio))
        return infer(audio) if infer else f"Phrase {len(inputs)}."

    client = Mock(transcribe_live_sync=transcribe)
    worker = PhraseTranscriber(
        client,
        16000,
        1,
        lambda text: (phrases.append(text), delivered.set()),
        completed.append,
        errors.append,
    )
    worker.start()
    return worker, inputs, phrases, completed, errors, delivered


def join(worker):
    worker.thread.join(timeout=2)
    assert not worker.thread.is_alive()


def test_phrase_arrives_during_recording_and_stop_flushes_every_sample_once():
    worker, inputs, phrases, completed, errors, delivered = session()
    first = pcm(5000, 0.4) + pcm(0, 0.65)
    worker.feed(first[:12800])
    worker.feed(first[12800:])
    assert delivered.wait(1)
    assert phrases == ["Phrase 1."]
    assert not completed
    tail = pcm(2000, 0.3) + pcm(0, 0.1)
    worker.feed(tail)
    worker.finish()
    join(worker)
    assert b"".join(inputs) == first + tail
    assert completed == ["Phrase 1. Phrase 2."]
    assert not errors


@pytest.mark.parametrize("level", [0, 1, 50, 5000])
def test_short_or_quiet_utterances_are_never_filtered_out(level):
    worker, inputs, _, completed, errors, _ = session()
    audio = pcm(level, 0.08)
    worker.feed(audio)
    worker.finish()
    join(worker)
    assert inputs == [audio]
    assert completed == ["Phrase 1."]
    assert not errors


def test_continuous_speech_is_retained_until_a_pause_or_stop():
    worker, inputs, _, _, errors, _ = session()
    audio = pcm(4000, 65)
    for offset in range(0, len(audio), 2048):
        worker.feed(audio[offset : offset + 2048])
    worker.finish()
    join(worker)
    assert b"".join(inputs) == audio
    assert not errors


def test_slow_inference_coalesces_pending_phrases_without_dropping_audio():
    entered, release = threading.Event(), threading.Event()

    def slow(audio):
        entered.set()
        assert release.wait(1)
        return "Complete phrase."

    worker, inputs, _, completed, errors, _ = session(slow)
    phrase = pcm(5000, 0.3) + pcm(0, 0.65)
    worker.feed(pcm(5000, 0.3))
    worker.feed(pcm(0, 0.65))
    assert entered.wait(1)
    for _ in range(20):
        worker.feed(pcm(5000, 0.3))
        worker.feed(pcm(0, 0.65))
    worker.finish()
    release.set()
    join(worker)
    assert len(inputs) == 2  # One in flight and one coalesced tail, not 21 jobs.
    assert b"".join(inputs) == phrase * 21
    assert len(completed) == 1
    assert not errors


def test_cancel_suppresses_an_inflight_result_and_completion():
    entered, release = threading.Event(), threading.Event()

    def slow(audio):
        entered.set()
        assert release.wait(1)
        return "Stale text."

    worker, _, phrases, completed, errors, _ = session(slow)
    worker.feed(pcm(5000, 0.3))
    worker.feed(pcm(0, 0.65))
    assert entered.wait(1)
    worker.cancel()
    release.set()
    join(worker)
    assert phrases == completed == errors == []


def test_inference_failure_cannot_be_presented_as_success_or_leak_native_details():
    def fail(audio):
        raise RuntimeError("private diagnostic or transcript")

    worker, _, phrases, completed, errors, _ = session(fail)
    worker.feed(pcm(5000, 0.3))
    worker.finish()
    join(worker)
    assert phrases == completed == []
    assert errors == ["Local live transcription failed"]
