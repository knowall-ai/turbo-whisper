import asyncio
import io
import json
import os
import subprocess
import wave
from pathlib import Path
from unittest.mock import Mock

import httpx
import pytest

from turbo_whisper.api import WhisperAPIError, WhisperClient
from turbo_whisper.config import Config


def wav(rate=16000, channels=1, empty=False):
    output = io.BytesIO()
    with wave.open(output, "wb") as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(b"" if empty else b"\x00\x00" * rate * channels)
    return output.getvalue()


@pytest.fixture
def cpp(monkeypatch, tmp_path):
    from turbo_whisper import whisper_cpp

    model = tmp_path / "model with spaces.bin"
    model.write_bytes(b"synthetic model")
    config = Config(transcription_backend="whisper_cpp", whisper_cpp_model=str(model))
    monkeypatch.setattr(whisper_cpp.shutil, "which", lambda value: "/synthetic/whisper-cli")

    def run(command, **kwargs):
        audio = Path(command[command.index("-f") + 1])
        assert audio.read_bytes() == wav()
        assert kwargs["timeout"] == 120
        Path(command[command.index("-of") + 1] + ".json").write_text(
            json.dumps({"transcription": [{"text": " Hello,"}, {"text": " world. "}]})
        )
        return subprocess.CompletedProcess(
            command, 0, "", "whisper_backend_init_gpu: using Vulkan0 backend\n"
        )

    runner = Mock(side_effect=run)
    monkeypatch.setattr(whisper_cpp.subprocess, "run", runner)
    http = Mock(side_effect=AssertionError("whisper.cpp audio must not be uploaded"))
    monkeypatch.setattr(httpx, "Client", http)
    monkeypatch.setattr(httpx, "AsyncClient", http)
    return config, runner


@pytest.mark.parametrize("asynchronous", [False, True])
def test_cpp_transcription_and_temporary_file_cleanup(cpp, asynchronous):
    config, runner = cpp
    client = WhisperClient(config)
    text = asyncio.run(client.transcribe(wav())) if asynchronous else client.transcribe_sync(wav())
    assert text == "Hello, world."
    command = runner.call_args.args[0]
    assert command[command.index("-m") + 1] == config.whisper_cpp_model
    assert command[command.index("-dev") + 1] == "0"
    assert "-ng" not in command
    assert "shell" not in runner.call_args.kwargs
    assert not Path(command[command.index("-f") + 1]).parent.exists()


def test_cpp_requires_actual_gpu_initialization(cpp):
    config, runner = cpp
    runner.side_effect = None
    runner.return_value = subprocess.CompletedProcess([], 0, "", "VULKAN = 1; no GPU found")
    with pytest.raises(WhisperAPIError, match="CPU fallback was rejected"):
        WhisperClient(config).transcribe_sync(wav())


def test_cpp_cpu_fallback_can_be_explicitly_allowed(cpp):
    config, runner = cpp
    config.whisper_cpp_require_gpu = False
    original = runner.side_effect

    def cpu(command, **kwargs):
        result = original(command, **kwargs)
        result.stderr = "whisper_backend_init_gpu: no GPU found"
        return result

    runner.side_effect = cpu
    assert WhisperClient(config).transcribe_sync(wav()) == "Hello, world."


def test_cpp_timeout_is_handled_and_audio_is_removed(cpp):
    config, runner = cpp
    runner.side_effect = subprocess.TimeoutExpired("whisper-cli", 120)
    with pytest.raises(WhisperAPIError, match="timed out"):
        WhisperClient(config).transcribe_sync(wav())
    command = runner.call_args.args[0]
    assert not Path(command[command.index("-f") + 1]).parent.exists()


@pytest.mark.parametrize("body", ["invalid", "[]", "{}", '{"transcription": [1]}'])
def test_cpp_malformed_output_is_handled(cpp, body):
    config, runner = cpp
    original = runner.side_effect

    def malformed(command, **kwargs):
        result = original(command, **kwargs)
        Path(command[command.index("-of") + 1] + ".json").write_text(body)
        return result

    runner.side_effect = malformed
    with pytest.raises(WhisperAPIError, match="unreadable"):
        WhisperClient(config).transcribe_sync(wav())


def test_cpp_process_failure_does_not_echo_private_output(cpp):
    config, runner = cpp
    runner.side_effect = None
    runner.return_value = subprocess.CompletedProcess(
        [], 1, "private transcript", "whisper_backend_init_gpu: using Vulkan0 backend\nprivate log"
    )
    with pytest.raises(WhisperAPIError, match="whisper.cpp failed") as error:
        WhisperClient(config).transcribe_sync(wav())
    assert "private" not in str(error.value)


@pytest.mark.parametrize(
    "value", [b"", b"RIFF-truncated", wav(48000), wav(channels=2), wav(empty=True)]
)
def test_cpp_invalid_audio_never_starts_process(cpp, value):
    config, runner = cpp
    with pytest.raises(WhisperAPIError):
        WhisperClient(config).transcribe_sync(value)
    runner.assert_not_called()


def test_cpp_missing_binary_is_actionable(cpp, monkeypatch):
    config, runner = cpp
    monkeypatch.setattr("turbo_whisper.whisper_cpp.shutil.which", lambda value: None)
    with pytest.raises(WhisperAPIError, match="not found"):
        WhisperClient(config).transcribe_sync(wav())
    runner.assert_not_called()


def test_cpp_missing_model_never_starts_process(cpp):
    config, runner = cpp
    config.whisper_cpp_model = ""
    with pytest.raises(WhisperAPIError, match="existing whisper.cpp"):
        WhisperClient(config).transcribe_sync(wav())
    runner.assert_not_called()


def test_cpp_auto_language_and_device_setting(cpp):
    config, runner = cpp
    config.language = ""
    config.whisper_cpp_device = 2
    assert WhisperClient(config).transcribe_sync(wav()) == "Hello, world."
    command = runner.call_args.args[0]
    assert command[command.index("-dev") + 1] == "2"
    assert command[command.index("-l") + 1] == "auto"


@pytest.mark.skipif(os.name == "nt", reason="Synthetic executable uses a POSIX shebang")
def test_native_cli_process_contract_and_cleanup(tmp_path):
    """Exercise subprocess/file I/O with a synthetic engine, without GPU or weights."""
    executable = tmp_path / "fake-whisper-cli"
    executable.write_text(
        "#!/usr/bin/env python3\n"
        "import json, pathlib, sys\n"
        "args = sys.argv[1:]\n"
        'assert pathlib.Path(args[args.index("-f") + 1]).read_bytes().startswith(b"RIFF")\n'
        'pathlib.Path(args[args.index("-of") + 1] + ".json").write_text(\n'
        '    json.dumps({"transcription": [{"text": "A native process result."}]}))\n'
        'print("whisper_backend_init_gpu: using Vulkan0 backend", file=sys.stderr)\n'
    )
    executable.chmod(0o700)
    model = tmp_path / "model file.bin"
    model.write_bytes(b"synthetic weights")
    config = Config(
        transcription_backend="whisper_cpp",
        whisper_cpp_binary=str(executable),
        whisper_cpp_model=str(model),
    )
    assert WhisperClient(config).transcribe_sync(wav()) == "A native process result."


@pytest.mark.skipif(os.name == "nt", reason="Intel workstation launcher is a Bash script")
def test_intel_profile_setup_preserves_saved_settings(tmp_path):
    profile = tmp_path / "profile" / "config.json"
    model = tmp_path / "ggml-test.bin"
    model.write_bytes(b"synthetic model")
    environment = {
        **os.environ,
        "TURBO_WHISPER_CONFIG": str(profile),
        "TURBO_WHISPER_CPP_MODEL": str(model),
    }
    launcher = Path(__file__).resolve().parents[1] / "tools" / "run-intel"
    subprocess.run(["bash", str(launcher), "--configure-only"], env=environment, check=True)
    saved = profile.read_bytes()
    config = json.loads(saved)
    assert config["transcription_backend"] == "whisper_cpp"
    assert config["whisper_cpp_require_gpu"]
    assert config["whisper_cpp_model"] == str(model)
    environment["TURBO_WHISPER_CPP_MODEL"] = str(tmp_path / "absent-model.bin")
    subprocess.run(["bash", str(launcher), "--configure-only"], env=environment, check=True)
    assert profile.read_bytes() == saved
