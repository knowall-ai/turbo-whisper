# CLAUDE.md

This file provides guidance to Claude Code when working with this repository.

## Project Overview

Turbo Whisper is a SuperWhisper-like voice dictation application for Linux, macOS, and Windows. It provides a floating waveform UI with an animated orb that appears when the user presses a global hotkey, records audio, sends it to a Whisper API endpoint, and types the transcribed text into the focused window.

## Architecture

```
src/turbo_whisper/
├── main.py       # Application entry point, Qt app, system tray, settings panel
├── waveform.py   # Animated orb visualization widget (PyQt6)
├── icons.py      # Lucide SVG icons (power, copy, eye, chevron)
├── recorder.py   # Audio recording with PyAudio
├── api.py        # Whisper API client (OpenAI-compatible)
├── hotkey.py     # Global hotkey handling with pynput
├── typer.py      # Auto-type using xdotool/wtype
└── config.py     # Configuration management with history
```

## Icon Library

We use [Lucide Icons](https://lucide.dev/) for UI icons. Icons are stored as SVG strings in `icons.py` and rendered to QIcon via QSvgRenderer.

Current icons used:
- `power` - Close button
- `copy` - Copy to clipboard
- `eye` / `eye-off` - Show/hide API key
- `chevron-down` / `chevron-up` - Expand/collapse settings
- `play` / `stop` - Audio playback controls
- `check` - Success indicator

To add a new icon:
1. Find the icon at https://lucide.dev/icons/
2. Copy the SVG path data
3. Add it to `icons.py` as `ICON_NAME = '''<svg>...</svg>'''`
4. Create a getter function `get_name_icon(size, color)`

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

1. **Animated orb visualization** - Sound-responsive blob animation (OpenAI/ElevenLabs style)
2. **Global hotkey** - Ctrl+Shift+Space by default, works from any application
3. **OpenAI API compatibility** - Works with OpenAI or self-hosted faster-whisper-server
4. **Auto-type** - Transcribed text typed into focused window
5. **System tray** - Runs in background with tray icon
6. **Settings panel** - Expandable panel for API URL, API key, sensitivity
7. **Clip history** - Stores last 20 transcriptions for easy re-use
8. **Draggable window** - Can be moved anywhere on screen

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
1. **Kill all existing processes first** (see below for proper kill commands)
2. Ensure the waveform displays correctly during recording
3. Verify hotkey works from other applications
4. Test with both OpenAI API and self-hosted endpoints
5. Check auto-typing works in various applications

**Important**: Multiple instances can run simultaneously and cause conflicts. Always kill all processes before starting a new test instance.

### Killing All Processes (IMPORTANT)

The app spawns multiple processes that must ALL be killed:
- Python process: `turbo_whisper.main` or `turbo-whisper`
- uv wrapper: `uv run turbo-whisper`
- Parent shell wrappers (when run from Claude)

**Reliable kill command:**
```bash
# Kill ALL turbo-whisper processes (catches all variations)
pkill -9 -f "turbo.whisper"

# Verify they're gone
pgrep -af "turbo.whisper" || echo "All killed"
```

**Why this pattern works:**
- `turbo.whisper` matches both `turbo-whisper` and `turbo_whisper` (regex dot matches any char)
- Catches: `turbo-whisper`, `turbo_whisper.main`, `uv run turbo-whisper`
- Does NOT match other turbo projects (e.g., `turbo-translator`)

### Running the App (for Claude)

Claude CAN run the app using background execution. The display and D-Bus session are accessible.

```bash
# Kill existing instances first, then start in background
pkill -9 -f "turbo.whisper" 2>/dev/null; sleep 0.5

# Run in background (use run_in_background=true in Bash tool)
sg input -c "uv run turbo-whisper" 2>&1
```

The `sg input -c` wrapper is needed on Linux/Wayland to access `/dev/uinput` for keyboard simulation (evdev).

## Documentation

Keep the `/docs/` directory up to date:

- **docs/SOLUTION_DESIGN.adoc** - Technical design decisions, cross-platform compatibility tables
- **docs/TROUBLESHOOTING.adoc** - Problem/solution table for common issues

When fixing bugs or adding features:
1. Update TROUBLESHOOTING.adoc if the fix resolves a common user problem
2. Update SOLUTION_DESIGN.adoc if the change affects cross-platform behavior
3. Add new platform-specific workarounds to the compatibility tables
