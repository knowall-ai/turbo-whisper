"""Configuration management for Turbo Whisper."""

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TypedDict


class HistoryEntry(TypedDict):
    """A history entry with text and timestamp."""

    text: str
    timestamp: str  # ISO format


@dataclass
class Config:
    """Application configuration."""

    # API settings
    api_url: str = "https://whisper.weeksfamily.me/v1/audio/transcriptions"
    api_key: str = ""

    # Hotkey settings (using pynput key names)
    hotkey: list[str] = field(default_factory=lambda: ["alt", "space"])

    # Audio settings
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024
    input_device_index: int | None = None  # None = system default
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

    # History (recent transcriptions)
    history: list[HistoryEntry] = field(default_factory=list)
    history_max: int = 20

    def add_to_history(self, text: str) -> None:
        """Add a transcription to history."""
        if text and text.strip():
            # Remove if already exists (move to top)
            for i, entry in enumerate(self.history):
                entry_text = entry["text"] if isinstance(entry, dict) else entry
                if entry_text == text:
                    self.history.pop(i)
                    break
            # Add to front with timestamp
            entry: HistoryEntry = {
                "text": text,
                "timestamp": datetime.now().isoformat(),
            }
            self.history.insert(0, entry)
            # Trim to max size
            self.history = self.history[:self.history_max]
            self.save()

    @classmethod
    def get_config_path(cls) -> Path:
        """Get the configuration file path."""
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
                return cls(**data)
            except (json.JSONDecodeError, TypeError) as e:
                print(f"Warning: Could not load config: {e}")

        return cls()

    def save(self) -> None:
        """Save configuration to file."""
        config_path = self.get_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)

        with open(config_path, "w") as f:
            json.dump(self.__dict__, f, indent=2)
