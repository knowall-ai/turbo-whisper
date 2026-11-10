import asyncio

import httpx
import pytest

from turbo_whisper.api import WhisperAPIError, WhisperClient
from turbo_whisper.config import Config


@pytest.mark.parametrize("asynchronous", [False, True])
def test_multipart_transcription_request(monkeypatch, asynchronous):
    seen = []

    def handle(request):
        seen.append(request)
        return httpx.Response(200, json={"text": " Hello, world. "})

    transport = httpx.MockTransport(handle)
    sync, async_ = httpx.Client, httpx.AsyncClient
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: sync(transport=transport, **kwargs))
    monkeypatch.setattr(
        httpx, "AsyncClient", lambda **kwargs: async_(transport=transport, **kwargs)
    )
    client = WhisperClient(
        Config(
            api_url="https://example.invalid/transcribe",
            api_key="synthetic-test-key",
            api_model="local-model",
            transcription_timeout=600,
        )
    )
    result = (
        asyncio.run(client.transcribe(b"RIFF-test-audio"))
        if asynchronous
        else client.transcribe_sync(b"RIFF-test-audio")
    )
    assert result == "Hello, world."
    assert seen[0].headers["authorization"] == "Bearer synthetic-test-key"
    assert b"RIFF-test-audio" in seen[0].content
    assert b"local-model" in seen[0].content
    assert seen[0].extensions["timeout"] == {"connect": 10, "read": 600, "write": 600, "pool": 10}


@pytest.mark.parametrize(
    "status,message",
    [
        (401, "API key"),
        (403, "permissions"),
        (404, "URL"),
        (429, "rate limited"),
        (500, "server error"),
        (400, "HTTP 400"),
    ],
)
def test_errors_are_readable_and_do_not_echo_server_body(status, message):
    with pytest.raises(WhisperAPIError, match=message):
        WhisperClient._response(httpx.Response(status, text="private server response"))


@pytest.mark.parametrize("body", [b"broken json", b"[]", b'{"other": "value"}', b'{"text": 123}'])
def test_malformed_transcription_is_a_handled_error(body):
    with pytest.raises(WhisperAPIError):
        WhisperClient._response(httpx.Response(200, content=body))


@pytest.mark.parametrize("value", [0, -1, float("inf"), float("nan"), True, "600"])
def test_invalid_timeout(value):
    with pytest.raises(WhisperAPIError, match="positive number"):
        WhisperClient(Config(transcription_timeout=value))._timeout()


def test_no_audio_never_submits_a_request():
    with pytest.raises(WhisperAPIError, match="No audio"):
        WhisperClient(Config())._request(b"")
