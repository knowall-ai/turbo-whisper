"""Turbo Whisper - SuperWhisper-like voice dictation for Linux."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("turbo-whisper")
except PackageNotFoundError:
    __version__ = "1.1.0"  # Fallback for development
