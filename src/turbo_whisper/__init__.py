"""Turbo Whisper - SuperWhisper-like voice dictation for Linux."""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("turbo-whisper")
except PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development
