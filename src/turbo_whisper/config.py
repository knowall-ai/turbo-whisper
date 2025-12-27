"""Configuration management for Turbo Whisper."""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Config:
    """Application configuration."""

    # API settings
    api_url: str = "http://localhost:8000/v1/audio/transcriptions"
    api_key: str = ""

    # Hotkey settings (using pynput key names)
    hotkey: list[str] = field(default_factory=lambda: ["alt", "space"])

    # Audio settings
    sample_rate: int = 16000
    channels: int = 1
    chunk_size: int = 1024

    # UI settings
    waveform_color: str = "#00ff88"
    background_color: str = "#1a1a2e"
    window_width: int = 400
    window_height: int = 100

    # Behavior
    auto_paste: bool = True
    copy_to_clipboard: bool = True
    language: str = "en"

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
