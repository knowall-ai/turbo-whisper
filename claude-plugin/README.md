# Turbo Whisper Integration for Claude Code

This plugin enables seamless voice dictation with [Turbo Whisper](https://github.com/knowall-ai/turbo-whisper).

## What it does

Signals Turbo Whisper when Claude Code is ready for input, so your voice transcriptions
are typed at the right moment - not while Claude is still generating output.

## Installation

1. Install Turbo Whisper: `pip install turbo-whisper`
2. Install this plugin: `/plugin install turbo-whisper-integration`

## How it works

The plugin adds hooks that fire when:
- Claude finishes responding (ready for next prompt)
- Claude asks you a question (waiting for your answer)
- A subagent completes its task

Each hook sends a signal to Turbo Whisper's local API (port 7878), which then knows it's safe to type the transcribed text.

## Fallback behavior

- If Claude doesn't signal within 5 seconds: Text is copied to clipboard with "Copied (Claude busy)" message
- If Claude not detected: Turbo Whisper types immediately (normal behavior)
- If plugin not installed: Turbo Whisper types immediately (no waiting)

## Configuration

Turbo Whisper's Claude integration can be configured in `~/.config/turbo-whisper/config.json`:

```json
{
  "claude_integration": true,
  "claude_integration_port": 7878,
  "claude_wait_timeout": 5.0
}
```
