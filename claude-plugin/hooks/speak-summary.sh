#!/bin/bash
# Speak a brief summary of Claude's response when it finishes
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

# Find the transcript file from CLAUDE_PROJECT_DIR
if [ -n "$CLAUDE_PROJECT_DIR" ]; then
    # Convert project dir to transcript folder name (e.g., /home/user/proj -> -home-user-proj)
    PROJ_FOLDER=$(echo "$CLAUDE_PROJECT_DIR" | sed 's|/|-|g' | sed 's|\.|-|g')
    TRANSCRIPT_DIR="$HOME/.claude/projects/$PROJ_FOLDER"

    # Get the most recently modified transcript file
    if [ -d "$TRANSCRIPT_DIR" ]; then
        TRANSCRIPT_PATH=$(ls -t "$TRANSCRIPT_DIR"/*.jsonl 2>/dev/null | head -1)
    fi
fi

# Extract the last assistant message from the transcript
if [ -n "$TRANSCRIPT_PATH" ] && [ -f "$TRANSCRIPT_PATH" ]; then
    # Get text from the last assistant message that contains text
    RAW_TEXT=$(jq -s -r '
        [.[] | select(.type == "assistant") |
         select(.message.content | if type == "array" then any(.[]; .type == "text") else true end)
        ] | last |
        .message.content |
        if type == "array" then
            [.[] | select(.type == "text") | .text] | join(" ")
        else
            .
        end // empty
    ' "$TRANSCRIPT_PATH" 2>/dev/null)

    if [ -n "$RAW_TEXT" ]; then
        # Extract content from <summary>...</summary> tags if present
        MESSAGE=$(echo "$RAW_TEXT" | grep -oP '(?<=<summary>).*(?=</summary>)' | head -1)

        # Clean up for speech: remove any remaining markdown
        if [ -n "$MESSAGE" ]; then
            MESSAGE=$(echo "$MESSAGE" | \
                sed 's/\*\*//g' | \
                sed 's/\*//g' | \
                sed 's/`[^`]*`//g' | \
                sed 's/%/ percent/g' | \
                tr '\n' ' ' | \
                sed 's/  */ /g')
        fi
    fi
fi

# If no text content, just exit silently
if [ -z "$MESSAGE" ] || [ "$MESSAGE" = " " ]; then
    exit 0
fi

# Escape quotes for JSON
MESSAGE=$(echo "$MESSAGE" | sed 's/"/\\"/g')

# Use temp directory for audio files
TTS_OUTPUT="/tmp/turbo-whisper-tts-output.wav"
TTS_FAST="/tmp/turbo-whisper-tts-fast.wav"

# Call TTS API (OpenAI-compatible format)
curl -s -X POST "$TTS_URL" \
    -H "Authorization: Bearer $TTS_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"$TTS_MODEL\", \"voice\": \"$TTS_VOICE\", \"input\": \"$MESSAGE\"}" \
    -o "$TTS_OUTPUT" 2>/dev/null

# Speed up audio by 20% and play
if [ -f "$TTS_OUTPUT" ]; then
    ffmpeg -y -i "$TTS_OUTPUT" -filter:a "atempo=1.2" "$TTS_FAST" 2>/dev/null
    aplay "$TTS_FAST" 2>/dev/null || paplay "$TTS_FAST" 2>/dev/null
fi

exit 0
