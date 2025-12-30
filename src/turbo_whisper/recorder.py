"""Audio recording functionality."""

import io
import subprocess
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
            elif line.startswith("Description:"):
                desc = line.split(":", 1)[1].strip()
                current["description"] = desc
                current["is_input"] = (
                    "alsa_input" in current.get("name", "")
                    and "Monitor" not in desc
                )

        if current and current.get("is_input"):
            sources.append(current)

        return sources
    except Exception:
        return []


def set_pipewire_default_source(source_id: str) -> bool:
    """Set the default PipeWire audio source."""
    try:
        result = subprocess.run(
            ["wpctl", "set-default", source_id],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


class AudioRecorder:
    """Records audio from microphone with level monitoring."""

    def __init__(self, config: Config):
        self.config = config
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.frames: list[bytes] = []
        self.is_recording = False
        self.level_callback = None
        self._actual_sample_rate = config.sample_rate
        self.waveform_buffer = deque(maxlen=100)
        self._record_thread = None

    def get_input_devices(self) -> list[dict]:
        """Get list of available input devices."""
        import sys

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
        devices = []
        for i in range(self.audio.get_device_count()):
            try:
                info = self.audio.get_device_info_by_index(i)
                if info["maxInputChannels"] > 0:
                    devices.append({
                        "index": i,
                        "name": info["name"],
                        "channels": info["maxInputChannels"],
                        "sample_rate": int(info["defaultSampleRate"]),
                    })
            except Exception:
                pass
        return devices

    def start(self, level_callback=None) -> None:
        """Start recording audio."""
        if self.is_recording:
            return

        self.level_callback = level_callback
        self.frames = []
        self.is_recording = True

        # Use simple defaults - let PyAudio/PipeWire handle device routing
        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=self.config.channels,
            rate=self.config.sample_rate,
            input=True,
            frames_per_buffer=self.config.chunk_size,
        )

        self._record_thread = threading.Thread(target=self._record_loop, daemon=True)
        self._record_thread.start()

    def _record_loop(self) -> None:
        """Recording loop."""
        frame_count = 0
        while self.is_recording and self.stream:
            try:
                data = self.stream.read(self.config.chunk_size, exception_on_overflow=False)
                self.frames.append(data)
                frame_count += 1

                audio_data = np.frombuffer(data, dtype=np.int16)
                level = np.abs(audio_data).mean() / 32768.0

                self.waveform_buffer.append(level)

                if self.level_callback:
                    self.level_callback(level, list(self.waveform_buffer))

            except Exception as e:
                print(f"Recording error: {e}")
                break

    def stop(self) -> bytes:
        """Stop recording and return WAV data."""
        self.is_recording = False

        if self._record_thread:
            self._record_thread.join(timeout=1.0)

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(self.config.channels)
            wf.setsampwidth(self.audio.get_sample_size(pyaudio.paInt16))
            wf.setframerate(self._actual_sample_rate)
            wf.writeframes(b"".join(self.frames))

        return wav_buffer.getvalue()

    def cleanup(self) -> None:
        """Clean up audio resources."""
        self.is_recording = False
        if self.stream:
            self.stream.close()
        self.audio.terminate()
