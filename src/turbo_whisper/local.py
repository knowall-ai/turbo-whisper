"""Optional in-process Whisper inference; audio never falls back to an API."""

import io
import threading
from pathlib import Path

from .api import WhisperAPIError
from .config import Config


class LocalWhisperClient:
    def __init__(self, config: Config):
        self.config = config
        self._model = None
        self._model_settings = None
        self._lock = threading.Lock()

    def transcribe_sync(self, audio_data: bytes) -> str:
        if not audio_data:
            raise WhisperAPIError("No audio was recorded")
        # Keep one model resident and serialize inference and settings reloads.
        with self._lock:
            self._load_model()
            try:
                segments, _ = self._model.transcribe(
                    io.BytesIO(audio_data),
                    language=self.config.language.strip() or None,
                    beam_size=5,
                    vad_filter=True,
                )
                # faster-whisper performs inference while this generator is consumed.
                return " ".join(segment.text.strip() for segment in segments).strip()
            except Exception as exc:
                raise WhisperAPIError(
                    "Local transcription failed. Check the recording and model/device settings."
                ) from exc

    def prepare(self):
        with self._lock:
            self._load_model()

    def _load_model(self):
        settings = (
            self.config.local_model.strip(),
            self.config.local_device,
            self.config.local_compute_type,
            self.config.local_files_only,
        )
        model_name, device, compute_type, files_only = settings
        if not model_name:
            raise WhisperAPIError("Enter a local model name or folder")
        if device not in {"cpu", "cuda", "auto"}:
            raise WhisperAPIError("Local device must be cpu, cuda, or auto")
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise WhisperAPIError(
                "Local transcription needs faster-whisper. From the project folder, run: "
                "uv run --with-requirements requirements-local.txt turbo-whisper"
            ) from exc
        if self._model_settings != settings:
            # Release the old model before loading another, limiting peak RAM/VRAM.
            self._model = None
            self._model_settings = None
            try:
                self._model = WhisperModel(
                    (
                        str(Path(model_name).expanduser())
                        if model_name.startswith("~")
                        else model_name
                    ),
                    device=device,
                    compute_type=compute_type,
                    local_files_only=files_only,
                )
            except Exception as exc:
                raise WhisperAPIError(
                    "Could not load the local model. Check its name or folder, cached files, "
                    "and device/precision settings. First use needs a model download unless "
                    "you supply a model folder."
                ) from exc
            self._model_settings = settings
