import json
import os

from turbo_whisper.config import Config


def test_existing_config_migrates_without_losing_unknown_fields():
    path = Config.get_config_path()
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "api_url": "http://localhost:8000/transcribe",
                "history": ["old clip"],
                "future_option": {"enabled": True},
            }
        )
    )
    config = Config.load()
    assert config.history[0]["text"] == "old clip"
    assert config.api_url == "http://localhost:8000/transcribe"
    assert config.push_to_talk is False
    assert config.transcription_timeout == 30
    config.save()
    saved = json.loads(path.read_text())
    assert saved["future_option"] == {"enabled": True}
    assert "_unknown_fields" not in saved
    if os.name != "nt":
        assert path.stat().st_mode & 0o777 == 0o600


def test_new_installs_do_not_send_audio_to_an_unrelated_server():
    config = Config.load()
    assert config.api_url == "https://api.openai.com/v1/audio/transcriptions"
    assert not config.claude_integration
    assert config.transcription_backend == "api"
    assert not config.writer_polish


def test_local_settings_round_trip():
    config = Config(
        transcription_backend="local",
        local_model="/models/whisper",
        local_files_only=True,
    )
    config.save()
    loaded = Config.load()
    assert loaded.transcription_backend == "local"
    assert loaded.local_model == "/models/whisper"
    assert loaded.local_device == "cpu"
    assert loaded.local_compute_type == "int8"
    assert loaded.local_files_only


def test_history_deduplicates_and_retains_latest():
    config = Config(history_max=2)
    for text in ["first", "second", "first", "third"]:
        config.add_to_history(text)
    assert [item["text"] for item in Config.load().history] == ["third", "first"]


def test_explicit_project_config_path(tmp_path, monkeypatch):
    path = tmp_path / "profile" / "config.json"
    monkeypatch.setenv("TURBO_WHISPER_CONFIG", str(path))
    Config(transcription_backend="whisper_cpp", whisper_cpp_model="/models/ggml.bin").save()
    assert Config.get_config_path() == path
    loaded = Config.load()
    assert loaded.whisper_cpp_model == "/models/ggml.bin"
    assert not loaded.whisper_cpp_require_gpu
    assert not loaded.whisper_cpp_use_gpu


def test_legacy_explicit_gpu_profile_keeps_its_acceleration_choice():
    path = Config.get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"transcription_backend":"whisper_cpp","whisper_cpp_require_gpu":true}')
    loaded = Config.load()
    assert loaded.whisper_cpp_use_gpu and loaded.whisper_cpp_require_gpu


def test_legacy_optional_acceleration_is_not_silently_replaced_with_cpu():
    path = Config.get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"transcription_backend":"whisper_cpp","whisper_cpp_require_gpu":false}')
    loaded = Config.load()
    assert loaded.whisper_cpp_use_gpu
    assert not loaded.whisper_cpp_require_gpu


def test_review_entries_keep_distinct_sessions_and_original_words_after_reload():
    config = Config(
        writer_polish=True,
        polish_url="http://127.0.0.1:8080/v1/chat/completions",
        polish_model="local-test",
    )
    for identifier in ["first", "second"]:
        config.add_to_history(
            "Because the train was delayed.",
            review={
                "writer_id": identifier,
                "status": "incomplete",
                "source_text": "Because the train was delayed.",
                "message": "Provisional in Writer",
                "incomplete_tail": "Because the train was delayed.",
            },
        )
    loaded = Config.load()
    assert loaded.writer_polish and loaded.polish_model == "local-test"
    assert len(loaded.history) == 2
    assert [entry["dictation_review"]["writer_id"] for entry in loaded.history] == [
        "second",
        "first",
    ]
    assert all(
        entry["dictation_review"]["source_text"] == entry["text"] for entry in loaded.history
    )
