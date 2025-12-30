#!/bin/bash
# Signal Turbo Whisper that Claude is ready for input

# Try to send ready signal to Turbo Whisper
if curl -s -X POST http://localhost:7878/ready >/dev/null 2>&1; then
    exit 0
fi

# Turbo Whisper not running - exit silently (user may not have it installed)
exit 0
