"""An owned, loopback-only whisper.cpp worker for local live dictation."""

import atexit
import re
import secrets
import socket
import subprocess
import tempfile
import threading
import time

import httpx

from .api import WhisperAPIError


class ResidentWhisperCpp:
    def __init__(self, binary, model, device, require_gpu, timeout):
        self.timeout = timeout
        self._process = None
        self._directory = tempfile.TemporaryDirectory(prefix="turbo-whisper-worker-")
        self._gpu = threading.Event()
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        # A private route also prevents accidentally sending audio to an unrelated
        # service if another process claims the port between bind and exec.
        route = "/" + secrets.token_hex(24)
        self._http = httpx.Client(
            base_url=f"http://127.0.0.1:{port}{route}", trust_env=False, timeout=timeout
        )
        try:
            self._process = subprocess.Popen(
                [
                    binary,
                    "-m",
                    str(model),
                    "-dev",
                    str(device),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--request-path",
                    route,
                    "--public",
                    self._directory.name,
                    "--tmp-dir",
                    self._directory.name,
                    "-bs",
                    "5",
                    "-bo",
                    "5",
                    "-nt",
                    "-sns",
                ],
                cwd=self._directory.name,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            # Own the child before waiting for model readiness. Quitting during
            # startup must release it even if the constructor hasn't returned.
            atexit.register(self.close)
            threading.Thread(target=self._drain, args=(self._process.stderr,), daemon=True).start()
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                if self._process.poll() is not None:
                    raise WhisperAPIError("The local whisper.cpp worker could not start")
                try:
                    response = self._http.get("health", timeout=0.2)
                    if response.status_code == 200 and response.json() == {"status": "ok"}:
                        if require_gpu and not self._gpu.wait(min(0.2, timeout)):
                            raise WhisperAPIError(
                                "whisper.cpp did not confirm GPU initialization; "
                                "CPU fallback was rejected"
                            )
                        return
                except (httpx.RequestError, ValueError):
                    pass
                time.sleep(0.05)
            raise WhisperAPIError("The local whisper.cpp worker timed out while loading")
        except Exception:
            self.close()
            raise

    def _drain(self, pipe):
        # Discard native diagnostics, which can include recognized words. Retain
        # only GPU initialization as a boolean, never transcripts or a log file.
        tail = b""
        try:
            while chunk := pipe.read1(4096):
                tail = (tail + chunk)[-8192:]
                if re.search(rb"whisper_backend_init_gpu:\s+using\s+\S+\s+backend", tail):
                    self._gpu.set()
        finally:
            pipe.close()

    def transcribe(self, audio_data, language):
        if self._process is None or self._process.poll() is not None:
            raise WhisperAPIError("The local whisper.cpp worker stopped; start a new dictation")
        try:
            response = self._http.post(
                "inference",
                files={"file": ("audio.wav", audio_data, "audio/wav")},
                data={
                    "language": language.strip() or "auto",
                    "response_format": "json",
                    "beam_size": "5",
                    "best_of": "5",
                    "token_timestamps": "false",
                },
            )
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, dict) or not isinstance(result.get("text"), str):
                raise ValueError("Missing text")
            # Match the CLI adapter's space-joined 30-second segments.
            return " ".join(result["text"].split())
        except (httpx.HTTPError, ValueError) as exc:
            # A timeout can leave native inference running. Discard this worker
            # rather than queue another request behind an unknown running job.
            self.close()
            raise WhisperAPIError(
                "The local whisper.cpp worker could not finish transcription"
            ) from exc

    def close(self):
        atexit.unregister(self.close)
        process, self._process = self._process, None
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
        self._http.close()
        self._directory.cleanup()

    @property
    def alive(self):
        return self._process is not None and self._process.poll() is None
