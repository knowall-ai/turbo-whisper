import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest

from turbo_whisper.api import WhisperAPIError, WhisperClient
from turbo_whisper.config import Config


@pytest.fixture
def engine(monkeypatch):
    model = Mock()
    model.transcribe.side_effect = lambda *args, **kwargs: (
        iter([SimpleNamespace(text=" Hello,"), SimpleNamespace(text=" world. ")]),
        None,
    )
    factory = Mock(return_value=model)
    monkeypatch.setitem(sys.modules, "faster_whisper", SimpleNamespace(WhisperModel=factory))
    return factory, model


@pytest.mark.parametrize("asynchronous", [False, True])
def test_local_transcription_never_uses_http(monkeypatch, engine, asynchronous):
    http = Mock(side_effect=AssertionError("Local audio must not be uploaded"))
    monkeypatch.setattr(httpx, "Client", http)
    monkeypatch.setattr(httpx, "AsyncClient", http)
    client = WhisperClient(Config(transcription_backend="local", local_files_only=True))
    text = (
        asyncio.run(client.transcribe(b"wav-data"))
        if asynchronous
        else client.transcribe_sync(b"wav-data")
    )
    assert text == "Hello, world."
    factory, model = engine
    factory.assert_called_once_with(
        "base", device="cpu", compute_type="int8", local_files_only=True
    )
    args, kwargs = model.transcribe.call_args
    assert args[0].read() == b"wav-data"
    assert kwargs == {"language": "en", "beam_size": 5, "vad_filter": True}
    http.assert_not_called()


def test_model_is_cached_and_reloads_when_settings_change(engine):
    factory, model = engine
    config = Config(transcription_backend="local")
    client = WhisperClient(config)
    for _ in range(2):
        assert client.transcribe_sync(b"wav") == "Hello, world."
    factory.assert_called_once()
    config.local_model = "small"
    client.transcribe_sync(b"wav")
    assert factory.call_count == 2
    config.local_files_only = True
    client.transcribe_sync(b"wav")
    assert factory.call_count == 3
    config.language = ""
    client.transcribe_sync(b"wav")
    assert model.transcribe.call_args.kwargs["language"] is None
    assert factory.call_count == 3


def test_live_prepare_reuses_model_and_keeps_local_quality_settings(engine):
    factory, model = engine
    client = WhisperClient(Config(transcription_backend="local", local_files_only=True))
    client.prepare_live()
    client.prepare_live()
    assert client.transcribe_live_sync(b"wav") == "Hello, world."
    factory.assert_called_once()
    assert model.transcribe.call_args.kwargs["beam_size"] == 5
    assert model.transcribe.call_args.kwargs["vad_filter"] is True


def test_existing_model_folder_is_passed_to_engine(engine, tmp_path):
    factory, _ = engine
    client = WhisperClient(Config(transcription_backend="local", local_model=str(tmp_path)))
    client.transcribe_sync(b"wav")
    assert factory.call_args.args == (str(tmp_path),)


def test_missing_optional_dependency_is_actionable(monkeypatch):
    monkeypatch.setitem(sys.modules, "faster_whisper", None)
    with pytest.raises(WhisperAPIError, match="requirements-local.txt"):
        WhisperClient(Config(transcription_backend="local")).transcribe_sync(b"wav")


def test_model_load_failure_does_not_fall_back_and_can_retry(engine):
    factory, model = engine
    factory.side_effect = [RuntimeError("private details"), model]
    client = WhisperClient(Config(transcription_backend="local"))
    with pytest.raises(WhisperAPIError, match="Could not load the local model") as error:
        client.transcribe_sync(b"wav")
    assert "private details" not in str(error.value)
    assert client.transcribe_sync(b"wav") == "Hello, world."


def test_lazy_inference_failure_is_handled(engine):
    _, model = engine

    def segments():
        raise RuntimeError("private inference error")
        yield

    model.transcribe.return_value = segments(), None
    model.transcribe.side_effect = None
    with pytest.raises(WhisperAPIError, match="Local transcription failed"):
        WhisperClient(Config(transcription_backend="local")).transcribe_sync(b"wav")


def test_silence_returns_empty_text(engine):
    _, model = engine
    model.transcribe.side_effect = lambda *args, **kwargs: (iter([]), None)
    assert WhisperClient(Config(transcription_backend="local")).transcribe_sync(b"wav") == ""


@pytest.mark.parametrize("backend", ["api", "local"])
def test_empty_audio_never_loads_model(engine, backend):
    factory, _ = engine
    with pytest.raises(WhisperAPIError, match="No audio"):
        WhisperClient(Config(transcription_backend=backend)).transcribe_sync(b"")
    factory.assert_not_called()


def test_invalid_backend_cannot_silently_upload_audio():
    with pytest.raises(WhisperAPIError, match="backend"):
        WhisperClient(Config(transcription_backend="typo")).transcribe_sync(b"wav")
