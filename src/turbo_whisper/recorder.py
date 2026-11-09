"""Audio recording functionality."""

import io
import shutil
import subprocess
import sys
import threading
import wave
from collections import deque

import numpy as np
import pyaudio

from .config import Config


def get_pipewire_sources() -> list[dict]:
    """Get PipeWire audio input sources with friendly names."""
    try:
        result = subprocess.run(
            ["pactl", "list", "sources"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return []

        sources = []
        current = {}

        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Source #"):
                if current and current.get("is_input"):
                    sources.append(current)
                current = {"id": line.split("#")[1]}
            elif line.startswith("Name:"):
                current["name"] = line.split(":", 1)[1].strip()
                current["id"] = current["name"]
            elif line.startswith("Description:"):
                desc = line.split(":", 1)[1].strip()
                current["description"] = desc
                current["is_input"] = (
                    "alsa_input" in current.get("name", "") and "Monitor" not in desc
                )

        if current and current.get("is_input"):
            sources.append(current)

        return sources
    except Exception:
        return []


class AudioRecorder:
    """Records audio from microphone with level monitoring."""

    def __init__(self, config: Config):
        self.config = config
        self.audio = None
        self._process = None
        self.stream = None
        self.frames: list[bytes] = []
        self.is_recording = False
        self.level_callback = None
        self._actual_sample_rate = config.sample_rate
        self.waveform_buffer = deque(maxlen=100)
        self._record_thread = None
        self.frame_callback = None
        self.capture_error = None
        self.captured_frames = 0

    def get_input_devices(self) -> list[dict]:
        """Get list of available input devices."""
        # Try PipeWire first (Linux)
        if sys.platform.startswith("linux"):
            pw_sources = get_pipewire_sources()
            if pw_sources:
                return [
                    {
                        "index": src["id"],
                        "name": src["description"],
                        "pipewire_name": src["name"],
                        "channels": 2,
                        "sample_rate": 48000,
                    }
                    for src in pw_sources
                ]

        # Fallback to PyAudio
        if self.audio is None:
            self.audio = pyaudio.PyAudio()
        devices = []
        for i in range(self.audio.get_device_count()):
            try:
                info = self.audio.get_device_info_by_index(i)
                if info["maxInputChannels"] > 0:
                    devices.append(
                        {
                            "index": i,
                            "name": info["name"],
                            "channels": info["maxInputChannels"],
                            "sample_rate": int(info["defaultSampleRate"]),
                        }
                    )
            except Exception:
                pass
        return devices

    def start(self, level_callback=None, frame_callback=None) -> None:
        """Start recording audio."""
        if self.is_recording:
            return
        if self._record_thread and self._record_thread.is_alive():
            raise RuntimeError("The previous microphone session has not stopped")

        self.level_callback = level_callback
        self.frame_callback = frame_callback
        self.capture_error = None
        self.captured_frames = 0
        self.frames = []
        self.waveform_buffer.clear()
        self.is_recording = True

        self._actual_sample_rate = self.config.sample_rate
        if sys.platform.startswith("linux") and shutil.which("parec"):
            command = [
                "parec",
                "--raw",
                "--format=s16le",
                f"--rate={self.config.sample_rate}",
                f"--channels={self.config.channels}",
                "--latency-msec=20",
                "--process-time-msec=20",
            ]
            if self.config.input_device_index is not None:
                command.append(f"--device={self.config.input_device_index}")
            try:
                self._process = subprocess.Popen(
                    command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
                )
            except OSError:
                self.is_recording = False
                raise
        else:
            if self.audio is None:
                self.audio = pyaudio.PyAudio()
            selected = self.config.input_device_index
            try:
                self.stream = self.audio.open(
                    format=pyaudio.paInt16,
                    channels=self.config.channels,
                    rate=self.config.sample_rate,
                    input=True,
                    frames_per_buffer=self.config.chunk_size,
                    input_device_index=selected if isinstance(selected, int) else None,
                )
            except Exception:
                self.is_recording = False
                raise

        self._record_thread = threading.Thread(target=self._record_loop, daemon=True)
        self._record_thread.start()

    def _record_loop(self) -> None:
        """Recording loop."""
        # Drain the child's pipe to EOF after termination. Checking is_recording
        # here used to discard all but one of the blocks buffered at stop time.
        process, stream = self._process, self.stream
        while process or (self.is_recording and stream):
            try:
                if process:
                    data = process.stdout.read(self.config.chunk_size * self.config.channels * 2)
                else:
                    data = stream.read(self.config.chunk_size, exception_on_overflow=True)
                if not data:
                    if self.is_recording and process and isinstance(process.poll(), int):
                        self.capture_error = "The microphone stopped before recording finished"
                    break
                self.frames.append(data)
                self.captured_frames += len(data) // (self.config.channels * 2)
                if self.frame_callback:
                    self.frame_callback(data)
                audio_data = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                level = np.abs(audio_data).mean() / 32768.0

                self.waveform_buffer.append(level)

                if self.level_callback:
                    self.level_callback(level, list(self.waveform_buffer))

            except Exception:
                self.capture_error = "Microphone capture failed; the recording may be incomplete"
                break

    def stop(self) -> bytes:
        """Stop recording and return WAV data."""
        self.is_recording = False

        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=1)
        if self._record_thread:
            self._record_thread.join(timeout=2.0)
            if self._record_thread.is_alive():
                raise RuntimeError("The microphone did not stop; the recording may be incomplete")
        if self._process:
            self._process.stdout.close()
            self._process = None

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        if self.capture_error:
            raise RuntimeError(self.capture_error)
        if not self.frames:
            return b""
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(self.config.channels)
            wf.setsampwidth(2)
            wf.setframerate(self._actual_sample_rate)
            wf.writeframes(b"".join(self.frames))

        return wav_buffer.getvalue()

    def cleanup(self) -> None:
        """Release only this recorder's stream and child process."""
        if self.is_recording or self._process or self.stream:
            self.stop()
        if self.audio is not None:
            self.audio.terminate()
            self.audio = None
