import io
import subprocess
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from turbo_whisper import resident
from turbo_whisper.api import WhisperAPIError


@pytest.fixture
def native(monkeypatch):
    process = Mock(stderr=io.BytesIO(b"whisper_backend_init_gpu: using Vulkan0 backend\n"))
    process.poll.return_value = None
    spawn = Mock(return_value=process)
    monkeypatch.setattr(resident.subprocess, "Popen", spawn)
    response = httpx.Response(
        200,
        json={"text": " Complete\n  native result. \n"},
        request=httpx.Request("POST", "http://localhost"),
    )
    http = Mock()
    http.get.return_value = httpx.Response(200, json={"status": "ok"})
    http.post.return_value = response
    factory = Mock(return_value=http)
    monkeypatch.setattr(resident.httpx, "Client", factory)
    return process, spawn, http, factory


def create():
    return resident.ResidentWhisperCpp("whisper-server", Path("synthetic.bin"), 0, True, 0.5)


def test_owned_worker_uses_private_loopback_route_and_identical_decoding(native):
    process, spawn, http, factory = native
    worker = create()
    directory = Path(spawn.call_args.kwargs["cwd"])
    try:
        assert directory.is_dir()
        command = spawn.call_args.args[0]
        assert command[command.index("--host") + 1] == "127.0.0.1"
        route = command[command.index("--request-path") + 1]
        assert len(route) == 49
        kwargs = factory.call_args.kwargs
        assert kwargs["base_url"].startswith("http://127.0.0.1:")
        assert kwargs["base_url"].endswith(route)
        assert kwargs["trust_env"] is False
        assert spawn.call_args.kwargs["stdout"] == subprocess.DEVNULL
        assert worker.transcribe(b"synthetic-wav", "en") == "Complete native result."
        assert worker.transcribe(b"second-wav", "") == "Complete native result."
        spawn.assert_called_once()
        assert http.post.call_args.kwargs["data"] == {
            "language": "auto",
            "response_format": "json",
            "beam_size": "5",
            "best_of": "5",
            "token_timestamps": "false",
        }
    finally:
        worker.close()
    process.terminate.assert_called_once()
    assert not directory.exists()
    worker.close()  # Idempotent application/atexit cleanup.


def test_ready_cpu_worker_cannot_silently_replace_required_gpu(native):
    process, spawn, http, _ = native
    process.stderr = io.BytesIO(b"VULKAN = 1; no GPU found\n")
    with pytest.raises(WhisperAPIError, match="CPU fallback was rejected"):
        create()
    http.post.assert_not_called()
    process.terminate.assert_called_once()
    assert not Path(spawn.call_args.kwargs["cwd"]).exists()


def test_live_cpu_worker_uses_no_gpu_and_preserves_full_transcript(native):
    process, spawn, http, _ = native
    process.stderr = io.BytesIO(b"CPU backend initialized\n")
    worker = resident.ResidentWhisperCpp(
        "whisper-server", Path("model.bin"), 0, False, 0.5, use_gpu=False
    )
    try:
        assert "-ng" in spawn.call_args.args[0]
        assert worker.transcribe(b"synthetic-wav", "en") == "Complete native result."
        http.post.assert_called_once()
    finally:
        worker.close()


@pytest.mark.parametrize("failure", ["timeout", "redirect", "malformed", "error"])
def test_failed_request_closes_worker_without_echoing_audio_or_native_details(native, failure):
    process, _, http, _ = native
    worker = create()
    if failure == "timeout":
        http.post.side_effect = httpx.ReadTimeout("private details")
    else:
        code = {"redirect": 307, "malformed": 200, "error": 500}[failure]
        http.post.return_value = httpx.Response(
            code,
            text="private transcript",
            headers={"Location": "https://example.invalid"},
            request=httpx.Request("POST", "http://localhost"),
        )
    with pytest.raises(WhisperAPIError) as error:
        worker.transcribe(b"private audio", "en")
    assert "private" not in str(error.value)
    assert not worker.alive
    http.post.assert_called_once()
    process.terminate.assert_called_once()


def test_startup_failure_cleans_up_without_using_an_unrelated_service(native):
    process, spawn, http, _ = native
    process.poll.return_value = 1
    with pytest.raises(WhisperAPIError, match="could not start"):
        create()
    http.get.assert_not_called()
    http.post.assert_not_called()
    assert not Path(spawn.call_args.kwargs["cwd"]).exists()


def test_worker_is_owned_for_exit_cleanup_before_model_is_ready(native, monkeypatch):
    _, _, http, _ = native
    register = Mock()
    monkeypatch.setattr(resident.atexit, "register", register)

    def ready(*args, **kwargs):
        register.assert_called_once()
        return httpx.Response(200, json={"status": "ok"})

    http.get.side_effect = ready
    worker = create()
    register.assert_called_once_with(worker.close)
    worker.close()
