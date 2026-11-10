"""Offline whisper.cpp subprocess adapter with CPU and optional GPU inference."""

import io
import json
import math
import re
import shutil
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

from .api import WhisperAPIError
from .config import Config


class WhisperCppClient:
    def __init__(self, config: Config):
        self.config = config
        self._worker = None
        self._worker_settings = None
        self._lock = threading.RLock()

    @staticmethod
    def _audio(audio_data: bytes) -> bytes:
        """Validate the recorder's default format before invoking the CLI."""
        if not audio_data:
            raise WhisperAPIError("No audio was recorded")
        try:
            with wave.open(io.BytesIO(audio_data), "rb") as source:
                if (
                    source.getsampwidth() != 2
                    or source.getcomptype() != "NONE"
                    or source.getframerate() != 16000
                    or source.getnchannels() != 1
                ):
                    raise ValueError("Expected mono 16 kHz PCM16")
                frames = source.readframes(source.getnframes())
                if not frames or len(frames) != source.getnframes() * 2:
                    raise ValueError("Empty or truncated WAV")
            return audio_data
        except (ValueError, EOFError, wave.Error) as exc:
            raise WhisperAPIError(
                "whisper.cpp needs mono 16 kHz PCM16 WAV audio. "
                "Set sample_rate to 16000 and channels to 1."
            ) from exc

    def transcribe_sync(self, audio_data: bytes) -> str:
        audio_data = self._audio(audio_data)
        binary, model, timeout, device = self._parameters()
        return self._transcribe_cli(audio_data, binary, model, timeout, device)

    def _parameters(self):
        binary = shutil.which(str(Path(self.config.whisper_cpp_binary).expanduser()))
        if binary is None:
            raise WhisperAPIError(
                "whisper-cli was not found. Install whisper.cpp for your operating system."
            )
        model = Path(self.config.whisper_cpp_model).expanduser()
        if not self.config.whisper_cpp_model.strip() or not model.is_file():
            raise WhisperAPIError("Choose an existing whisper.cpp ggml model file (.bin)")
        timeout = self.config.whisper_cpp_timeout
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout <= 0
        ):
            raise WhisperAPIError("whisper.cpp timeout must be a positive number of seconds")
        device = self.config.whisper_cpp_device
        if isinstance(device, bool) or not isinstance(device, int) or device < 0:
            raise WhisperAPIError("whisper.cpp GPU device must be a non-negative integer")
        if self.config.whisper_cpp_require_gpu and not self.config.whisper_cpp_use_gpu:
            raise WhisperAPIError("Enable GPU acceleration or clear Require GPU acceleration")
        return binary, model, timeout, device

    def _transcribe_cli(self, audio_data, binary, model, timeout, device):
        with tempfile.TemporaryDirectory(prefix="turbo-whisper-") as directory:
            audio_path = Path(directory) / "audio.wav"
            output_path = Path(directory) / "result"
            audio_path.write_bytes(audio_data)
            command = [
                binary,
                "-m",
                str(model.resolve()),
                "-f",
                str(audio_path),
                "-l",
                self.config.language.strip() or "auto",
                "-dev",
                str(device),
                "-oj",
                "-of",
                str(output_path),
                "-nt",
                "-sns",
            ]
            if not self.config.whisper_cpp_use_gpu:
                command.append("-ng")
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise WhisperAPIError(
                    "whisper.cpp timed out. Increase its timeout or use a smaller model."
                ) from exc
            except OSError as exc:
                raise WhisperAPIError(
                    "Could not start whisper-cli. Check the executable and its libraries."
                ) from exc
            # The CLI may silently fall back to CPU even when GPU was requested.
            # Require actual backend initialization, not a compile-time VULKAN=1 flag.
            if self.config.whisper_cpp_require_gpu and not re.search(
                r"whisper_backend_init_gpu:\s+using\s+\S+\s+backend", result.stderr
            ):
                raise WhisperAPIError(
                    "whisper.cpp did not confirm GPU initialization. Check your runtime and "
                    "drivers, or clear Require GPU acceleration. CPU fallback was rejected."
                )
            if result.returncode:
                raise WhisperAPIError(
                    "whisper.cpp failed. Check model compatibility and available memory."
                )
            try:
                output = json.loads(output_path.with_suffix(".json").read_text(encoding="utf-8"))
                segments = output["transcription"]
                if not isinstance(segments, list) or any(
                    not isinstance(segment, dict) or not isinstance(segment.get("text"), str)
                    for segment in segments
                ):
                    raise ValueError("Invalid segments")
                return " ".join(segment["text"].strip() for segment in segments).strip()
            except (OSError, ValueError, KeyError, TypeError) as exc:
                raise WhisperAPIError(
                    "whisper.cpp returned an unreadable transcription result"
                ) from exc

    def prepare_live(self):
        from .resident import ResidentWhisperCpp

        with self._lock:
            binary, model, timeout, device = self._parameters()
            server = Path(binary).with_name("whisper-server")
            server = str(server) if server.is_file() else shutil.which("whisper-server")
            if not server:
                raise WhisperAPIError(
                    "Live whisper.cpp needs whisper-server from the same build "
                    "as whisper-cli. Disable live phrases to use the CLI alone."
                )
            stat = model.stat()
            settings = (
                server,
                str(model.resolve()),
                stat.st_size,
                stat.st_mtime_ns,
                device,
                self.config.whisper_cpp_use_gpu,
                self.config.whisper_cpp_require_gpu,
                timeout,
            )
            if self._worker is None or not self._worker.alive or self._worker_settings != settings:
                self.close()
                try:
                    self._worker = ResidentWhisperCpp(
                        server,
                        model.resolve(),
                        device,
                        self.config.whisper_cpp_require_gpu,
                        timeout,
                        use_gpu=self.config.whisper_cpp_use_gpu,
                    )
                except OSError as exc:
                    raise WhisperAPIError("Could not start the local whisper.cpp worker") from exc
                self._worker_settings = settings

    def transcribe_live_sync(self, audio_data):
        audio_data = self._audio(audio_data)
        with self._lock:
            self.prepare_live()
            return self._worker.transcribe(audio_data, self.config.language)

    def close(self):
        if self._worker is not None:
            self._worker.close()
            self._worker = None
        self._worker_settings = None
