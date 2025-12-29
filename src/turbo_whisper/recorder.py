"""Audio recording functionality."""

import io
import threading
import wave
from collections import deque

import numpy as np
import pyaudio

from .config import Config


class AudioRecorder:
    """Records audio from microphone with level monitoring."""

    def __init__(self, config: Config):
        self.config = config
        self.audio = pyaudio.PyAudio()
        self.stream = None
        self.frames: list[bytes] = []
        self.is_recording = False
        self.level_callback = None
        self._actual_sample_rate = config.sample_rate  # May differ from config

        # Circular buffer for waveform visualization
        self.waveform_buffer = deque(maxlen=100)

        self._record_thread = None

    def get_input_devices(self) -> list[dict]:
        """Get list of available input devices."""
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

    def get_default_device_index(self) -> int | None:
        """Get the default input device index."""
        try:
            info = self.audio.get_default_input_device_info()
            return info["index"]
        except Exception:
            return None

    def start(self, level_callback=None) -> None:
        """Start recording audio."""
        if self.is_recording:
            return

        self.level_callback = level_callback
        self.frames = []
        self.is_recording = True

        # Determine device and sample rate
        device_index = self.config.input_device_index
        sample_rate = self.config.sample_rate

        # Get device info to determine native sample rate
        try:
            if device_index is not None:
                info = self.audio.get_device_info_by_index(device_index)
            else:
                # Use system default INPUT device
                info = self.audio.get_default_input_device_info()
                device_index = info["index"]

            # Verify device actually works - "default" often reports wrong channel count
            # Look for input-only devices (no output channels)
            if "default" in info["name"].lower() or info["maxInputChannels"] == 0:
                print(f"Warning: Device '{info['name']}' may not work, searching for hardware input...")
                device_index = None
                for i in range(self.audio.get_device_count()):
                    dev_info = self.audio.get_device_info_by_index(i)
                    # Input-only devices have input channels but NO output channels
                    if dev_info["maxInputChannels"] > 0 and dev_info["maxOutputChannels"] == 0:
                        info = dev_info
                        device_index = i
                        print(f"Found input device {i}: {info['name']}")
                        break

            if device_index is not None:
                device_rate = int(info["defaultSampleRate"])
                if device_rate != sample_rate:
                    print(f"Using device's native sample rate: {device_rate}Hz")
                    sample_rate = device_rate
                print(f"Using input device {device_index}: {info['name']} ({info['maxInputChannels']} channels)")
        except Exception as e:
            print(f"Could not get device info: {e}, using config sample rate")

        self._actual_sample_rate = sample_rate

        self.stream = self.audio.open(
            format=pyaudio.paInt16,
            channels=self.config.channels,
            rate=sample_rate,
            input=True,
            input_device_index=device_index,
            frames_per_buffer=self.config.chunk_size,
        )

        self._record_thread = threading.Thread(target=self._record_loop, daemon=True)
        self._record_thread.start()

    def _record_loop(self) -> None:
        """Recording loop running in separate thread."""
        import sys
        frame_count = 0
        print("Recording thread started", flush=True)
        while self.is_recording and self.stream:
            try:
                data = self.stream.read(self.config.chunk_size, exception_on_overflow=False)
                self.frames.append(data)
                frame_count += 1

                # Calculate audio level for visualization
                audio_data = np.frombuffer(data, dtype=np.int16)
                level = np.abs(audio_data).mean() / 32768.0  # Normalize to 0-1

                self.waveform_buffer.append(level)

                # Debug every 50 frames (~3 seconds)
                if frame_count % 50 == 0:
                    print(f"Recording: frame={frame_count}, level={level:.4f}", flush=True)

                if self.level_callback:
                    self.level_callback(level, list(self.waveform_buffer))

            except Exception as e:
                print(f"Recording error: {e}", flush=True)
                break
        print("Recording thread stopped", flush=True)

    def stop(self) -> bytes:
        """Stop recording and return WAV data."""
        self.is_recording = False

        if self._record_thread:
            self._record_thread.join(timeout=1.0)

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

        # Convert frames to WAV format (use actual sample rate from recording)
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
