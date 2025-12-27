# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

Turbo Whisper is a SuperWhisper-like voice dictation application for Linux. It provides a floating waveform UI that appears when the user presses a global hotkey, records audio, sends it to a Whisper API endpoint, and types the transcribed text into the focused window.

## Architecture

```
src/turbo_whisper/
├── main.py       # Application entry point, Qt app, system tray
├── waveform.py   # Waveform visualization widget (PyQt6)
├── recorder.py   # Audio recording with PyAudio
├── api.py        # Whisper API client (OpenAI-compatible)
├── hotkey.py     # Global hotkey handling with pynput
├── typer.py      # Auto-type using xdotool/wtype
└── config.py     # Configuration management
```

## Development Commands

```bash
# Activate virtual environment
source .venv/bin/activate

# Run the application
turbo-whisper

# Or run directly
python -m turbo_whisper.main

# Install in development mode
pip install -e .

# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black src/

# Lint
ruff check src/
```

## Key Features to Maintain

1. **Waveform visualization** - Real-time audio level display with bars
2. **Global hotkey** - Alt+Space by default, works from any application
3. **OpenAI API compatibility** - Works with OpenAI or self-hosted faster-whisper-server
4. **Auto-type** - Transcribed text typed into focused window
5. **System tray** - Runs in background with tray icon

## Configuration

Config file: `~/.config/turbo-whisper/config.json`

Key settings:
- `api_url`: Whisper API endpoint
- `api_key`: API key (optional for self-hosted)
- `hotkey`: Key combination as list, e.g., `["alt", "space"]`
- `waveform_color`: Hex color for waveform bars
- `auto_paste`: Whether to auto-type transcription

## Dependencies

- **PyQt6**: UI framework
- **PyAudio**: Audio recording
- **pynput**: Global hotkey handling
- **httpx**: HTTP client for API calls
- **xdotool**: Auto-typing (system dependency)

## Testing

When testing changes:
1. Ensure the waveform displays correctly during recording
2. Verify hotkey works from other applications
3. Test with both OpenAI API and self-hosted endpoints
4. Check auto-typing works in various applications
