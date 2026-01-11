<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo.svg">
    <source media="(prefers-color-scheme: light)" srcset="assets/logo.svg">
    <img alt="Turbo Whisper" src="assets/logo.svg" width="100%">
  </picture>
</p>

Turbo Whisper is a **free, open source** voice dictation and transcription app for Linux, macOS, and Windows. A SuperWhisper alternative with a beautiful GUI for real-time speech to text (STT). Supports **99 languages** via OpenAI Whisper. Perfect for accessibility, RSI, and hands-free typing.

**Voice dictation** | **Speech to text (STT)** | **Voice typing** | **Transcription** | **Open source** | **Multilingual** | **Hands-free**

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)
![Platform](https://img.shields.io/badge/platform-Linux%20%7C%20macOS%20%7C%20Windows-lightgrey.svg)
![AUR](https://img.shields.io/aur/version/turbo-whisper)
![PPA](https://img.shields.io/badge/PPA-bengweeks%2Fturbo--whisper-orange)

<img width="1554" height="678" alt="image" src="https://github.com/user-attachments/assets/1f2e0447-2152-48d6-99c3-8d49d3053ac8" />

## Features

- **Global hotkey** (Ctrl+Shift+Space) to start/stop recording from anywhere
- **Waveform visualization** - see your audio levels in real-time with an animated orb
- **OpenAI API compatible** - works with OpenAI Whisper API or self-hosted faster-whisper-server
- **Multilingual** - supports 99 languages via Whisper
- **Auto-type** - transcribed text is typed directly into the focused window
- **Clipboard support** - text is also copied to clipboard
- **System tray** - runs quietly in the background with autostart support
- **Cross-platform** - Linux, macOS, and Windows support
- **Accessibility** - great for RSI, carpal tunnel, or anyone preferring hands-free input

## Perfect for AI CLI Tools

Turbo Whisper is ideal for voice input with terminal-based AI tools:

- **[Claude Code](https://github.com/anthropics/claude-code)** - Anthropic's CLI for Claude
- **[Aider](https://github.com/paul-gauthier/aider)** - AI pair programming in your terminal
- **[GitHub Copilot CLI](https://githubnext.com/projects/copilot-cli)** - Voice commands for git and shell
- **[Open Interpreter](https://github.com/OpenInterpreter/open-interpreter)** - Natural language to code execution
- **Any terminal app** - Works anywhere you can type text

Simply press the hotkey, speak your prompt, and the transcription is typed directly into your terminal.

## Installation

### Ubuntu/Debian (PPA) - Recommended

```bash
sudo add-apt-repository ppa:bengweeks/turbo-whisper
sudo apt update
sudo apt install turbo-whisper
```

### Arch Linux (AUR) - Recommended

```bash
# Using yay
yay -S turbo-whisper

# Using paru
paru -S turbo-whisper
```

### From Source

<details>
<summary>Ubuntu/Debian</summary>

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

</details>

<details>
<summary>Fedora</summary>

```bash
sudo dnf install python3-pyaudio portaudio-devel xdotool xclip
git clone https://github.com/knowall-ai/turbo-whisper.git
cd turbo-whisper
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

</details>

<details>
<summary>Arch Linux (manual)</summary>

```bash
sudo pacman -S python-pyaudio portaudio xdotool xclip
git clone https://github.com/knowall-ai/turbo-whisper.git
cd turbo-whisper
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

</details>

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

### Autostart on Login

To start Turbo Whisper automatically when you log in:

**Linux (all distros):**
```bash
# Create autostart directory if it doesn't exist
mkdir -p ~/.config/autostart

# Copy the desktop file (if installed via AUR/PPA)
cp /usr/share/applications/turbo-whisper.desktop ~/.config/autostart/

# Or create manually
cat > ~/.config/autostart/turbo-whisper.desktop << 'EOF'
[Desktop Entry]
Name=Turbo Whisper
Exec=turbo-whisper
Type=Application
X-GNOME-Autostart-enabled=true
EOF
```

**macOS:**
- Open System Preferences → Users & Groups → Login Items
- Click + and add Turbo Whisper

**Windows:**
- Press Win+R, type `shell:startup`, press Enter
- Create a shortcut to `turbo-whisper` in that folder

## Self-Hosting Whisper

You can run your own Whisper server for faster, private, and cost-free transcription using [faster-whisper-server](https://github.com/fedirz/faster-whisper-server).

### Hardware Requirements

| Model | VRAM (GPU) | RAM (CPU) | Speed | Accuracy |
|-------|------------|-----------|-------|----------|
| tiny | ~1 GB | ~2 GB | Fastest | Basic |
| base | ~1 GB | ~2 GB | Very fast | Good |
| small | ~2 GB | ~4 GB | Fast | Better |
| medium | ~5 GB | ~8 GB | Moderate | Great |
| large-v3 | ~10 GB | ~16 GB | Slower | Best |

**Recommendations:**
- **GPU with 6+ GB VRAM**: Use `large-v3` for best accuracy
- **GPU with 4 GB VRAM**: Use `small` or `medium`
- **CPU only**: Use `tiny` or `base` (expect slower transcription)

### Quick Start with Docker

```bash
# With NVIDIA GPU (recommended)
docker run --gpus=all -p 8000:8000 \
  -e WHISPER__MODEL=Systran/faster-whisper-large-v3 \
  fedirz/faster-whisper-server:latest-cuda

# With smaller model (less VRAM)
docker run --gpus=all -p 8000:8000 \
  -e WHISPER__MODEL=Systran/faster-whisper-small \
  fedirz/faster-whisper-server:latest-cuda

# CPU only (slower, no GPU required)
docker run -p 8000:8000 \
  -e WHISPER__MODEL=Systran/faster-whisper-base \
  fedirz/faster-whisper-server:latest-cpu
```

### Available Models

Models are downloaded automatically on first use:

| Model ID | Size |
|----------|------|
| `Systran/faster-whisper-tiny` | ~75 MB |
| `Systran/faster-whisper-base` | ~150 MB |
| `Systran/faster-whisper-small` | ~500 MB |
| `Systran/faster-whisper-medium` | ~1.5 GB |
| `Systran/faster-whisper-large-v3` | ~3 GB |

### Persistent Model Cache

To avoid re-downloading models on container restart:

```bash
docker run --gpus=all -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  -e WHISPER__MODEL=Systran/faster-whisper-large-v3 \
  fedirz/faster-whisper-server:latest-cuda
```

### Configure Turbo Whisper

Update your config to use the self-hosted server:

```json
{
  "api_url": "http://localhost:8000/v1/audio/transcriptions",
  "api_key": ""
}
```

### Verify Server is Running

```bash
curl http://localhost:8000/health
```

## Documentation

For detailed documentation, see the [`docs/`](docs/) directory:

- **[Installation Guide](docs/INSTALLATION.adoc)** - Complete installation instructions for all platforms
- **[Solution Design](docs/SOLUTION_DESIGN.adoc)** - Technical architecture and cross-platform compatibility
- **[Troubleshooting](docs/TROUBLESHOOTING.adoc)** - Common issues and solutions

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

For more troubleshooting tips, see [docs/TROUBLESHOOTING.adoc](docs/TROUBLESHOOTING.adoc).

## License

MIT License - see [LICENSE](LICENSE) for details.

## Keywords

Voice dictation Linux, speech to text, STT, voice typing, transcription, transcribe audio, OpenAI Whisper GUI, dictation software, speech recognition, voice input, hands-free typing, accessibility, SuperWhisper alternative, faster-whisper, voice to text CLI, terminal dictation, free open source, multilingual, 99 languages, RSI, carpal tunnel, real-time transcription, local whisper, offline speech recognition, nerd-dictation alternative, voice coding, voice input terminal, how to dictate on Linux, best voice dictation Linux, Ubuntu voice typing, Arch Linux dictation.

## Credits

Inspired by [SuperWhisper](https://superwhisper.com/) for macOS.
