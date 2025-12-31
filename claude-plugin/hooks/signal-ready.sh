#!/bin/bash
# Signal Turbo Whisper that Claude is ready for input

echo "[Hook] signal-ready.sh called at $(date)" >> /tmp/turbo-whisper-hook.log

# Try to send ready signal to Turbo Whisper (1s timeout, full path)
/usr/bin/curl -s -m 1 -X POST http://localhost:7878/ready >> /tmp/turbo-whisper-hook.log 2>&1 || echo "[Hook] curl failed" >> /tmp/turbo-whisper-hook.log
exit 0
