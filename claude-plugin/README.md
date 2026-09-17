# Turbo Whisper Integration for Claude Code

This plugin provides full voice integration with [Turbo Whisper](https://github.com/knowall-ai/turbo-whisper):

- **Speech-to-Text**: Signals when Claude is ready for your voice input
- **Text-to-Speech**: Speaks summaries and notifications aloud

## Features

### Voice Dictation (Speech-to-Text)
Signals Turbo Whisper when Claude Code is ready for input, so your voice transcriptions are typed at the right moment - not while Claude is still generating output.

### Voice Summaries (Text-to-Speech)
When Claude finishes responding, it speaks a brief summary of what it did. Requires Claude to include `<summary>` blocks in responses (add instruction to your CLAUDE.md).

### Voice Notifications
Context-aware spoken notifications when Claude needs your input:
- **"Permission required"** - When Claude needs permission to run a command
- **"I have a question"** - When Claude asks you something
- **"Ready for input"** - When Claude is idle and waiting
- **"Compacting context"** - When Claude auto-compacts due to full context window
- **"Compacting"** - When you run `/compact` manually

## Installation

1. Install Turbo Whisper: `pip install turbo-whisper`
2. Install this plugin: `/plugin install turbo-whisper-integration`

## Setup for Voice Summaries

Add this to your `~/.claude/CLAUDE.md` to enable spoken summaries:

```
- IMPORTANT: Always end EVERY response with a `<summary>` block containing a brief spoken summary (1-2 sentences). This is spoken aloud via TTS. Write conversationally. Example: `<summary>I've updated the config file and added the new feature.</summary>` Never skip this.
```

## Requirements

### For Voice Dictation
- Turbo Whisper running locally

### For TTS (Voice Summaries/Notifications)
- turbo-tts server running (see [turbo-tts setup](https://github.com/knowall-ai/turbo-whisper#turbo-tts))
- `jq` - for parsing JSON transcripts
- `ffmpeg` - for audio speed adjustment (optional)
- `aplay` or `paplay` - for audio playback on Linux

## TTS Configuration

The TTS hooks use the OpenAI-compatible TTS API format. You must configure the endpoint and API key.

**Setup:**
```bash
# In the plugin directory
cp .env.example .env.local
# Edit .env.local with your settings
```

**Required settings in `.env.local`:**
```
# OpenAI
TURBO_TTS_URL=https://api.openai.com/v1/audio/speech
TURBO_TTS_API_KEY=sk-your-openai-key

# Or your own OpenAI-compatible server
TURBO_TTS_URL=http://your-server:8103/v1/audio/speech
TURBO_TTS_API_KEY=your-api-key
```

**Optional settings:**
```
TURBO_TTS_MODEL=tts-1      # Default: tts-1
TURBO_TTS_VOICE=alloy      # Default: alloy
```

TTS hooks will silently skip if not configured.

## How it works

### Voice Dictation Hooks
The plugin adds hooks that fire when:
- Claude finishes responding (ready for next prompt)
- Claude asks you a question (waiting for your answer)
- A subagent completes its task

Each hook sends a signal to Turbo Whisper's local API (port 7878), which then knows it's safe to type the transcribed text.

### TTS Hooks
- **Stop hook**: Extracts `<summary>` block from Claude's response and speaks it
- **Notification hooks**: Speak contextual messages based on notification type

## Fallback behavior

### Voice Dictation
- If Claude doesn't signal within 5 seconds: Text is copied to clipboard with "Copied (Claude busy)" message
- If Claude not detected: Turbo Whisper types immediately (normal behavior)
- If plugin not installed: Turbo Whisper types immediately (no waiting)

### TTS
- If no `<summary>` block in response: No audio plays (silent)
- If TTS server unreachable: Script exits silently
- If ffmpeg not installed: Audio plays at normal speed

## Configuration

Turbo Whisper's Claude integration can be configured in `~/.config/turbo-whisper/config.json`:

```json
{
  "claude_integration": true,
  "claude_integration_port": 7878,
  "claude_wait_timeout": 5.0
}
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No audio plays | Check TTS server is running and `.env.local` has correct `TURBO_TTS_URL` |
| Hear nothing after Claude responds | Ensure Claude's response contains a `<summary>` block |
| "jq: parse error" | Transcript is JSONL format - the script uses `jq -s` to handle this |
| Audio too slow/fast | Adjust `atempo` value in hook script (1.2 = 20% faster) |
| ffmpeg not found | Install ffmpeg or audio will play at normal speed |
| Hooks not working after install | Restart Claude Code to pick up new hooks |
