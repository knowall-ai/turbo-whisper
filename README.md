# Turbo Whisper

SuperWhisper-like voice dictation for Linux, macOS, and Windows with waveform UI.

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)

## Features

- **Global hotkey** (Ctrl+Shift+Space) to start/stop recording from anywhere
- **Waveform visualization** - see your audio levels in real-time
- **OpenAI API compatible** - works with OpenAI Whisper API or self-hosted faster-whisper-server
- **Auto-type** - transcribed text is typed directly into the focused window
- **Clipboard support** - text is also copied to clipboard
- **System tray** - runs quietly in the background
- **Cross-platform** - Linux, macOS, and Windows support

## Installation

### Linux (Ubuntu/Debian)

```bash
# Install system dependencies
sudo apt install python3-pyaudio portaudio19-dev xdotool xclip

# Clone and install
git clone https://github.com/knowall-ai/turbo-whisper.git
cd turbo-whisper
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Linux (Fedora)

```bash
sudo dnf install python3-pyaudio portaudio-devel xdotool xclip
git clone https://github.com/knowall-ai/turbo-whisper.git
cd turbo-whisper
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Linux (Arch)

```bash
sudo pacman -S python-pyaudio portaudio xdotool xclip
git clone https://github.com/knowall-ai/turbo-whisper.git
cd turbo-whisper
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### macOS

```bash
# Install Homebrew dependencies
brew install portaudio

# Clone and install
git clone https://github.com/knowall-ai/turbo-whisper.git
cd turbo-whisper
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Windows

```powershell
# Clone the repository
git clone https://github.com/knowall-ai/turbo-whisper.git
cd turbo-whisper

# Create virtual environment
python -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -e .
pip install pyperclip  # Required for Windows clipboard/typing
```

## Configuration

Create `~/.config/turbo-whisper/config.json` (Linux/macOS) or `%APPDATA%\turbo-whisper\config.json` (Windows):

```json
{
  "api_url": "https://api.openai.com/v1/audio/transcriptions",
  "api_key": "sk-your-api-key",
  "hotkey": ["ctrl", "shift", "space"],
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
# Activate virtual environment
source .venv/bin/activate  # Linux/macOS
# or
.venv\Scripts\activate     # Windows

# Start the application
turbo-whisper
```

1. Press **Ctrl+Shift+Space** to start recording
2. Speak your text
3. Press **Ctrl+Shift+Space** again to stop and transcribe
4. Text is automatically typed into the focused window (wherever your cursor is)

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| Ctrl+Shift+Space | Start/stop recording (configurable) |
| Esc | Cancel recording (when window is focused) |

### Custom Hotkey

Edit your config to change the hotkey:
```json
{
  "hotkey": ["ctrl", "alt", "w"]
}
```

Available modifiers: `ctrl`, `shift`, `alt`, `super`

## Self-Hosting Whisper

You can run your own Whisper server using [faster-whisper-server](https://github.com/fedirz/faster-whisper-server):

```bash
# With GPU
docker run --gpus=all -p 8000:8000 fedirz/faster-whisper-server:latest-cuda

# CPU only
docker run -p 8000:8000 fedirz/faster-whisper-server:latest-cpu
```

## Troubleshooting

### Linux: Hotkey conflicts
If Ctrl+Shift+Space conflicts with another application, edit the config:
```json
{
  "hotkey": ["ctrl", "alt", "w"]
}
```

### Windows: PyAudio installation fails
Install the pre-built wheel:
```powershell
pip install pipwin
pipwin install pyaudio
```

### macOS: Accessibility permissions
Grant accessibility permissions to your terminal app in System Preferences → Security & Privacy → Privacy → Accessibility.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

Inspired by [SuperWhisper](https://superwhisper.com/) for macOS.
