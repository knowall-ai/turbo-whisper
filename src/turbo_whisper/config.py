"""Configuration management for Turbo Whisper."""

import json
import os
from dataclasses import dataclass, field, fields
from datetime import datetime
from pathlib import Path
from typing import TypedDict


def _default_hotkey() -> list[str]:
    """Return platform-appropriate default hotkey."""
    import sys

    if sys.platform == "win32":
        # Alt+Space conflicts with Windows window menu
        # Ctrl+Shift+Space conflicts with various apps
        # Win+Shift+V conflicts with clipboard history
        return ["f8"]
    else:
        return ["alt", "space"]


class HistoryEntry(TypedDict, total=False):
    """A history entry with text, timestamp, and optional audio file."""

    text: str
    timestamp: str  # ISO format
    audio_file: str  # Filename (not full path) of WAV recording


@dataclass
class Config:
    """Application configuration."""

    # API settings
    api_url: str = "https://api.openai.com/v1/audio/transcriptions"
    api_model: str = "whisper-1"
    api_key: str = ""

    # Local inference is optional; existing installs continue using their API.
    transcription_backend: str = "api"
    local_model: str = "base"
    local_device: str = "cpu"
    local_compute_type: str = "int8"
    local_files_only: bool = False
    live_transcription: bool = False  # Deliver complete local phrases during recording

    # whisper.cpp runs locally using an installed GPU-enabled whisper-cli.
    whisper_cpp_binary: str = "whisper-cli"
    whisper_cpp_model: str = ""
    whisper_cpp_device: int = 0
    whisper_cpp_timeout: float = 120.0
    whisper_cpp_require_gpu: bool = True

    # Hotkey settings (using pynput key names)
    # Default: F8 on Windows (Alt+Space conflicts with window menu)
    #          Alt+Space on Linux/macOS
    hotkey: list[str] = field(default_factory=_default_hotkey)

    # Dictation interaction mode
    # False: press once to start, press again to stop
    # True: hold keys to record, release to stop
    push_to_talk: bool = False

    # Audio settings
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
    input_device_index: int | str | None = None  # None = system default, str for PipeWire source ID
    input_device_name: str = ""  # For display purposes

    # UI settings
    waveform_color: str = "#84cc16"  # KnowAll.ai lime green
    background_color: str = "#1a1a2e"
    window_width: int = 520
    window_height: int = 260  # Taller window for bigger waveform

    # Behavior
    auto_paste: bool = True
    copy_to_clipboard: bool = True
    language: str = "en"
    typing_delay_ms: int = 5  # Milliseconds between keystrokes (increase if terminal freezes)

    # Transcription settings
    transcription_timeout: float = (
        30.0  # HTTP read/write timeout in seconds; raise for long recordings
    )

    # Claude Code integration
    claude_integration: bool = False  # Enable integration server for Claude Code
    claude_integration_port: int = 7878  # Port for integration HTTP server
    claude_wait_timeout: float = 30.0  # Max seconds to wait for Claude ready signal

    # History (recent transcriptions)
    history: list[HistoryEntry] = field(default_factory=list)
    history_max: int = 20
    store_recordings: bool = True  # Save audio files with transcriptions

    def get_recordings_dir(self) -> Path:
        """Get the directory for storing audio recordings."""
        import sys

        if sys.platform == "win32":
            config_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        else:
            config_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        recordings_dir = config_dir / "turbo-whisper" / "recordings"
        recordings_dir.mkdir(parents=True, exist_ok=True)
        return recordings_dir

    def add_to_history(self, text: str, audio_file: str | None = None) -> None:
        """Add a transcription to history.

        Args:
            text: The transcribed text
            audio_file: Optional filename of the WAV recording
        """
        if text and text.strip():
            # Remove if already exists (move to top) and delete old audio
            for i, entry in enumerate(self.history):
                entry_text = entry["text"] if isinstance(entry, dict) else entry
                if entry_text == text:
                    # Delete old audio file if it exists
                    old_audio = entry.get("audio_file") if isinstance(entry, dict) else None
                    if old_audio:
                        old_path = self.get_recordings_dir() / old_audio
                        if old_path.exists():
                            old_path.unlink()
                    self.history.pop(i)
                    break
            # Add to front with timestamp
            entry: HistoryEntry = {
                "text": text,
                "timestamp": datetime.now().isoformat(),
            }
            if audio_file:
                entry["audio_file"] = audio_file
            self.history.insert(0, entry)
            # Trim to max size and clean up old recordings
            self._cleanup_old_recordings()
            self.save()

    def _cleanup_old_recordings(self) -> None:
        """Remove old recordings beyond history_max limit."""
        # Get entries that will be removed
        removed_entries = self.history[self.history_max :]
        self.history = self.history[: self.history_max]

        # Delete audio files for removed entries
        recordings_dir = self.get_recordings_dir()
        for entry in removed_entries:
            if isinstance(entry, dict) and entry.get("audio_file"):
                audio_path = recordings_dir / entry["audio_file"]
                if audio_path.exists():
                    try:
                        audio_path.unlink()
                    except OSError:
                        pass  # Ignore errors deleting files

    @classmethod
    def get_config_path(cls) -> Path:
        """Get the configuration file path."""
        import sys

        if override := os.environ.get("TURBO_WHISPER_CONFIG"):
            return Path(override).expanduser().resolve()

        if sys.platform == "win32":
            # Windows: use APPDATA
            config_dir = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        else:
            # Linux/macOS: use XDG_CONFIG_HOME
            config_dir = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
        return config_dir / "turbo-whisper" / "config.json"

    @classmethod
    def load(cls) -> "Config":
        """Load configuration from file or create default."""
        config_path = cls.get_config_path()

        if config_path.exists():
            try:
                with open(config_path) as f:
                    data = json.load(f)
                # Migrate old string-based history to new format
                if "history" in data and data["history"]:
                    migrated = []
                    for entry in data["history"]:
                        if isinstance(entry, str):
                            # Old format: just a string
                            migrated.append({"text": entry, "timestamp": ""})
                        else:
                            # New format: dict with text and timestamp
                            migrated.append(entry)
                    data["history"] = migrated
                known = {item.name for item in fields(cls)}
                config = cls(**{key: value for key, value in data.items() if key in known})
                config._unknown_fields = {
                    key: value for key, value in data.items() if key not in known
                }
                return config
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Warning: Could not load config: {e}")

        return cls()

    def save(self) -> None:
        """Save configuration to file."""
        config_path = self.get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        import tempfile

        data = {
            **getattr(self, "_unknown_fields", {}),
            **{key: value for key, value in self.__dict__.items() if not key.startswith("_")},
        }
        temporary = None
        try:
            with tempfile.NamedTemporaryFile("w", dir=config_path.parent, delete=False) as output:
                temporary = Path(output.name)
                json.dump(data, output, indent=2)
                output.write("\n")
            os.replace(temporary, config_path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
