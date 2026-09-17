#!/bin/bash
# Speak context-aware notifications when Claude needs input
# Part of turbo-whisper integration plugin

# Load environment from plugin's .env.local if it exists
PLUGIN_DIR="$(dirname "$(dirname "$0")")"
if [ -f "$PLUGIN_DIR/.env.local" ]; then
    export $(grep -v '^#' "$PLUGIN_DIR/.env.local" | xargs)
fi

# TTS configuration (OpenAI-compatible API)
# Required: set these in .env.local
TTS_URL="$TURBO_TTS_URL"
TTS_API_KEY="$TURBO_TTS_API_KEY"
TTS_MODEL="${TURBO_TTS_MODEL:-tts-1}"
TTS_VOICE="${TURBO_TTS_VOICE:-alloy}"

# Exit if not configured
if [ -z "$TTS_URL" ] || [ -z "$TTS_API_KEY" ]; then
    exit 0
fi

# Get notification type from environment or argument
NOTIFICATION_TYPE="${CLAUDE_NOTIFICATION_TYPE:-$1}"

# Select message based on notification type
case "$NOTIFICATION_TYPE" in
    permission_prompt)
        MESSAGE="Permission required"
        ;;
    elicitation_dialog)
        MESSAGE="I have a question"
        ;;
    idle_prompt)
        MESSAGE="Ready for input"
        ;;
    pre_compact_auto)
        MESSAGE="Compacting context"
        ;;
    pre_compact_manual)
        MESSAGE="Compacting"
        ;;
    *)
        # Unknown type, exit silently
        exit 0
        ;;
esac

# Use temp directory for audio files
TTS_OUTPUT="/tmp/turbo-whisper-tts-notification.wav"
TTS_FAST="/tmp/turbo-whisper-tts-notification-fast.wav"

# Call TTS API (OpenAI-compatible format)
curl -s -X POST "$TTS_URL" \
    -H "Authorization: Bearer $TTS_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"$TTS_MODEL\", \"voice\": \"$TTS_VOICE\", \"input\": \"$MESSAGE\"}" \
    -o "$TTS_OUTPUT" 2>/dev/null

# Speed up and play
if [ -f "$TTS_OUTPUT" ]; then
    ffmpeg -y -i "$TTS_OUTPUT" -filter:a "atempo=1.2" "$TTS_FAST" 2>/dev/null
    aplay "$TTS_FAST" 2>/dev/null || paplay "$TTS_FAST" 2>/dev/null
fi

exit 0
