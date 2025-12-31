# Plan: Claude Code Integration (Issue #1)

## Problem Statement

When using Turbo Whisper with Claude Code, transcribed text can be typed at the wrong time if Claude is still generating output. Users need a way for Turbo Whisper to know when Claude Code is ready for input.

## Solution Overview

Create a two-way integration between Turbo Whisper and Claude Code using:
1. **HTTP API** in Turbo Whisper that listens for "ready" signals
2. **Claude Code Plugin** with hooks that signal when Claude is ready for input

## Architecture

```
┌─────────────────────┐              ┌──────────────────────┐
│    Claude Code      │              │    Turbo Whisper     │
│                     │    HTTP      │                      │
│  Stop hook ─────────┼─── POST ────►│  /ready endpoint     │
│  PostToolUse hook ──┼─── POST ────►│  sets ready flag     │
│  SubagentStop hook ─┼─── POST ────►│                      │
│                     │              │  Before typing:      │
│                     │              │  - Check Claude proc │
│                     │              │  - Wait for ready    │
└─────────────────────┘              └──────────────────────┘
```

## Implementation

### Phase 1: Turbo Whisper HTTP Server

Add a lightweight HTTP server that runs alongside the Qt app.

**New file: `src/turbo_whisper/integration_server.py`**

```python
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import json

class IntegrationHandler(BaseHTTPRequestHandler):
    ready_timestamp = 0

    def do_POST(self):
        if self.path == '/ready':
            IntegrationHandler.ready_timestamp = time.time()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == '/status':
            age = time.time() - IntegrationHandler.ready_timestamp
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            response = {
                "ready": age < 5,  # Ready if signal within last 5 seconds
                "last_signal_age": age
            }
            self.wfile.write(json.dumps(response).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # Suppress logging

class IntegrationServer:
    def __init__(self, port=7878):
        self.port = port
        self.server = None
        self.thread = None

    def start(self):
        self.server = HTTPServer(('127.0.0.1', self.port), IntegrationHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()

    @staticmethod
    def is_ready(max_age=5) -> bool:
        return (time.time() - IntegrationHandler.ready_timestamp) < max_age
```

**Changes to `config.py`:**
```python
# Add new config options
claude_integration: bool = True  # Enable Claude Code integration
claude_integration_port: int = 7878  # Port for integration server
```

**Changes to `main.py`:**
```python
# In TurboWhisperApp.__init__:
if self.config.claude_integration:
    from .integration_server import IntegrationServer
    self.integration_server = IntegrationServer(self.config.claude_integration_port)
    self.integration_server.start()

# In _on_transcription_complete, before typing:
def _should_wait_for_claude(self) -> bool:
    """Check if Claude Code is running."""
    import subprocess
    result = subprocess.run(['pgrep', '-x', 'claude'], capture_output=True)
    return result.returncode == 0

def _wait_for_claude_ready(self, timeout=5.0) -> bool:
    """Wait for Claude to signal ready, with timeout."""
    if not self.config.claude_integration:
        return True

    from .integration_server import IntegrationServer
    start = time.time()
    while (time.time() - start) < timeout:
        if IntegrationServer.is_ready():
            return True
        time.sleep(0.1)
    return False

# Before auto-typing:
if self._should_wait_for_claude():
    if not self._wait_for_claude_ready(timeout=5.0):
        # Timeout - just copy to clipboard, don't type
        self._show_status("Copied (Claude busy)")
        return
```

### Phase 2: Claude Code Plugin

**Repository structure in `turbo-whisper/claude-plugin/`:**

```
claude-plugin/
├── .claude-plugin/
│   └── plugin.json
├── hooks/
│   └── signal-ready.sh
└── README.md
```

**`.claude-plugin/plugin.json`:**
```json
{
  "name": "turbo-whisper-integration",
  "version": "1.0.0",
  "description": "Enables voice dictation with Turbo Whisper - signals when Claude is ready for input",
  "author": {
    "name": "KnowAll AI",
    "url": "https://github.com/knowall-ai"
  },
  "repository": "https://github.com/knowall-ai/turbo-whisper",
  "homepage": "https://github.com/knowall-ai/turbo-whisper",
  "license": "MIT",
  "keywords": ["voice", "dictation", "turbo-whisper", "speech-to-text"],
  "hooks": {
    "Stop": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "${CLAUDE_PLUGIN_ROOT}/hooks/signal-ready.sh"
      }]
    }],
    "PostToolUse": [{
      "matcher": "AskUserQuestion",
      "hooks": [{
        "type": "command",
        "command": "${CLAUDE_PLUGIN_ROOT}/hooks/signal-ready.sh"
      }]
    }],
    "SubagentStop": [{
      "matcher": "",
      "hooks": [{
        "type": "command",
        "command": "${CLAUDE_PLUGIN_ROOT}/hooks/signal-ready.sh"
      }]
    }]
  }
}
```

**`hooks/signal-ready.sh`:**
```bash
#!/bin/bash
# Signal Turbo Whisper that Claude is ready for input

if curl -s -X POST http://localhost:7878/ready 2>/dev/null; then
    exit 0
fi

# Turbo Whisper not running - show helpful message if not installed
if ! command -v turbo-whisper &>/dev/null; then
    echo "🎙️ Voice dictation available! Install Turbo Whisper: pip install turbo-whisper"
    echo "   https://github.com/knowall-ai/turbo-whisper"
fi
exit 0
```

**`README.md`:**
```markdown
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

Each hook sends a signal to Turbo Whisper's local API, which then knows it's safe to type.
```

### Phase 3: Marketplace Configuration

**Add to `turbo-whisper/.claude-plugin/marketplace.json`:**
```json
{
  "name": "turbo-whisper-marketplace",
  "owner": {
    "name": "KnowAll AI",
    "email": "support@knowall.ai",
    "url": "https://github.com/knowall-ai"
  },
  "metadata": {
    "description": "Turbo Whisper voice dictation plugins",
    "version": "1.0.0"
  },
  "plugins": [
    {
      "name": "turbo-whisper-integration",
      "description": "Enables voice dictation with Turbo Whisper",
      "source": {
        "type": "path",
        "path": "claude-plugin"
      }
    }
  ]
}
```

### Phase 4: Submit to Official Marketplace

After testing, submit PR to `anthropics/claude-plugins-official` to add:
```json
{
  "name": "turbo-whisper-integration",
  "description": "Voice dictation integration - signals when Claude is ready for input",
  "source": {
    "type": "github",
    "repo": "knowall-ai/turbo-whisper",
    "path": "claude-plugin"
  }
}
```

## User Experience

### First-time setup
```bash
# Install Turbo Whisper
pip install turbo-whisper

# Install Claude Code plugin (once in official marketplace)
/plugin install turbo-whisper-integration
```

### Daily use
1. Start Turbo Whisper (runs in system tray)
2. Use Claude Code normally
3. Press hotkey, speak, release
4. Turbo Whisper waits for Claude to be ready, then types

### Fallback behavior
- If Claude doesn't signal within 5 seconds → copies to clipboard, shows "Copied (Claude busy)"
- If Claude not detected → types immediately (normal behavior for other apps)
- If plugin not installed → types immediately (no waiting)

## Testing Plan

1. [ ] Unit test: Integration server starts and responds correctly
2. [ ] Unit test: Ready signal detection with timeout
3. [ ] Integration test: Hook triggers signal on Claude Stop
4. [ ] Integration test: Hook triggers signal on AskUserQuestion
5. [ ] Manual test: Voice dictation waits for Claude correctly
6. [ ] Manual test: Fallback to clipboard on timeout
7. [ ] Manual test: Normal behavior when Claude not running

## Files to Create/Modify

### New files:
- `src/turbo_whisper/integration_server.py` - HTTP server for Claude signals
- `claude-plugin/.claude-plugin/plugin.json` - Plugin manifest
- `claude-plugin/hooks/signal-ready.sh` - Hook script
- `claude-plugin/README.md` - Plugin documentation
- `.claude-plugin/marketplace.json` - Marketplace configuration

### Modified files:
- `src/turbo_whisper/config.py` - Add integration config options
- `src/turbo_whisper/main.py` - Start server, wait for ready before typing
- `README.md` - Document Claude Code integration

## Cross-platform Considerations

| Platform | HTTP Server | curl in hook | pgrep for Claude |
|----------|-------------|--------------|------------------|
| Linux | ✅ | ✅ | ✅ `pgrep -x claude` |
| macOS | ✅ | ✅ | ✅ `pgrep -x claude` |
| Windows | ✅ | ⚠️ Use PowerShell | ⚠️ Use tasklist |

Windows hook alternative:
```powershell
Invoke-WebRequest -Uri http://localhost:7878/ready -Method POST -ErrorAction SilentlyContinue
```

## Future Enhancements

1. **Bidirectional communication**: Claude could query Turbo Whisper status
2. **Recording indicator**: Show in Claude Code when user is recording
3. **Direct integration**: If Claude Code adds native voice support, integrate directly
