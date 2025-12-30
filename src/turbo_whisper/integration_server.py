"""HTTP integration server for Claude Code communication."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer


class IntegrationHandler(BaseHTTPRequestHandler):
    """Handler for integration API requests."""

    ready_timestamp: float = 0

    def do_POST(self):
        """Handle POST requests."""
        if self.path == "/ready":
            IntegrationHandler.ready_timestamp = time.time()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "ok"}')
        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/status":
            age = time.time() - IntegrationHandler.ready_timestamp
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {
                "ready": age < 5,  # Ready if signal within last 5 seconds
                "last_signal_age": round(age, 2),
            }
            self.wfile.write(json.dumps(response).encode())
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"status": "healthy"}')
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        """Suppress HTTP logging."""
        pass


class IntegrationServer:
    """Lightweight HTTP server for external tool integration."""

    def __init__(self, port: int = 7878):
        self.port = port
        self.server: HTTPServer | None = None
        self.thread: threading.Thread | None = None

    def start(self) -> bool:
        """Start the integration server. Returns True if successful."""
        try:
            self.server = HTTPServer(("127.0.0.1", self.port), IntegrationHandler)
            self.thread = threading.Thread(
                target=self.server.serve_forever, daemon=True
            )
            self.thread.start()
            return True
        except OSError as e:
            # Port already in use (maybe another instance running)
            print(f"Integration server failed to start on port {self.port}: {e}")
            return False

    def stop(self) -> None:
        """Stop the integration server."""
        if self.server:
            self.server.shutdown()
            self.server = None
            self.thread = None

    @staticmethod
    def is_ready(max_age: float = 5.0) -> bool:
        """Check if a ready signal was received within max_age seconds."""
        return (time.time() - IntegrationHandler.ready_timestamp) < max_age

    @staticmethod
    def reset_ready() -> None:
        """Reset the ready timestamp (e.g., after typing)."""
        IntegrationHandler.ready_timestamp = 0
