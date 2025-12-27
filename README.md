# Turbo Whisper

SuperWhisper-like voice dictation for Linux with waveform UI.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Platform](https://img.shields.io/badge/platform-Linux-lightgrey.svg)

## Features

- **Global hotkey** (Alt+Space) to start/stop recording from anywhere
- **Waveform visualization** - see your audio levels in real-time
- **OpenAI API compatible** - works with OpenAI Whisper API or self-hosted faster-whisper-server
- **Auto-type** - transcribed text is typed directly into the focused window
- **Clipboard support** - text is also copied to clipboard
- **System tray** - runs quietly in the background

## Requirements

- Python 3.10+
- Linux (X11 or Wayland)
- A Whisper API endpoint (OpenAI or self-hosted)

### System Dependencies

```bash
# Ubuntu/Debian
sudo apt install python3-pyaudio portaudio19-dev xdotool xclip

# Fedora
sudo dnf install python3-pyaudio portaudio-devel xdotool xclip

# Arch
sudo pacman -S python-pyaudio portaudio xdotool xclip
```

## Installation

```bash
# Clone the repository
git clone https://github.com/knowall-ai/turbo-whisper.git
cd turbo-whisper

# Install with pip
pip install -e .

# Or with uv
uv pip install -e .
```

## Configuration

Configuration is stored in `~/.config/turbo-whisper/config.json`:

```json
{
  "api_url": "http://localhost:8000/v1/audio/transcriptions",
  "api_key": "",
  "hotkey": ["alt", "space"],
  "language": "en",
  "auto_paste": true,
  "copy_to_clipboard": true,
  "waveform_color": "#00ff88",
  "background_color": "#1a1a2e"
}
```

### API Endpoints

**OpenAI API:**
```json
{
  "api_url": "https://api.openai.com/v1/audio/transcriptions",
  "api_key": "sk-your-api-key"
}
```

**Self-hosted faster-whisper-server:**
```json
{
  "api_url": "http://your-server:8000/v1/audio/transcriptions",
  "api_key": ""
}
```

## Usage

```bash
# Start the application
turbo-whisper
```

1. Press **Alt+Space** to start recording
2. Speak your text
3. Press **Alt+Space** again to stop and transcribe
4. Text is automatically typed into the focused window

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Alt+Space | Start/stop recording |
| Esc | Cancel recording (when window is focused) |

## Self-Hosting Whisper

You can run your own Whisper server using [faster-whisper-server](https://github.com/fedirz/faster-whisper-server):

```bash
# With GPU
docker run --gpus=all -p 8000:8000 fedirz/faster-whisper-server:latest-cuda

# CPU only
docker run -p 8000:8000 fedirz/faster-whisper-server:latest-cpu
```

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

Inspired by [SuperWhisper](https://superwhisper.com/) for macOS.
