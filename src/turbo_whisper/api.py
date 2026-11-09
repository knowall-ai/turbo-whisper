"""OpenAI-compatible transcription client with bounded, configurable timeouts."""

import asyncio
import math

import httpx

from .config import Config


class WhisperAPIError(Exception):
    """A user-readable transcription failure."""


class WhisperClient:
    def __init__(self, config: Config):
        self.config = config
        self._local_client = None
        self._cpp_client = None

    def _cpp(self):
        if self._cpp_client is None:
            from .whisper_cpp import WhisperCppClient

            self._cpp_client = WhisperCppClient(self.config)
        return self._cpp_client

    def _local(self):
        if self._local_client is None:
            from .local import LocalWhisperClient

            self._local_client = LocalWhisperClient(self.config)
        return self._local_client

    def _validate_backend(self):
        if self.config.transcription_backend not in {"api", "local", "whisper_cpp"}:
            raise WhisperAPIError("Choose API, Local model, or whisper.cpp as the backend")

    def prepare_live(self):
        if self.config.transcription_backend == "whisper_cpp":
            self._cpp().prepare_live()
        elif self.config.transcription_backend == "local":
            self._local().prepare()
        else:
            raise WhisperAPIError("Live phrases require a local transcription backend")

    def transcribe_live_sync(self, audio_data: bytes) -> str:
        if self.config.transcription_backend == "whisper_cpp":
            return self._cpp().transcribe_live_sync(audio_data)
        if self.config.transcription_backend == "local":
            return self._local().transcribe_sync(audio_data)
        raise WhisperAPIError("Live phrases require a local transcription backend")

    def close(self):
        if self._cpp_client is not None:
            self._cpp_client.close()

    def _timeout(self) -> httpx.Timeout:
        limit = self.config.transcription_timeout
        if (
            isinstance(limit, bool)
            or not isinstance(limit, (int, float))
            or not math.isfinite(limit)
            or limit <= 0
        ):
            raise WhisperAPIError("Transcription timeout must be a positive number of seconds")
        return httpx.Timeout(limit, connect=min(10.0, limit), pool=min(10.0, limit))

    def _request(self, audio_data: bytes) -> dict:
        if not audio_data:
            raise WhisperAPIError("No audio was recorded")
        return {
            "headers": (
                {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}
            ),
            "files": {"file": ("audio.wav", audio_data, "audio/wav")},
            "data": {
                "model": self.config.api_model,
                "language": self.config.language,
                "response_format": "json",
                "prompt": "Use proper punctuation: commas, periods, question marks.",
            },
        }

    @staticmethod
    def _response(response: httpx.Response) -> str:
        errors = {
            401: "Unauthorized — check your API key",
            403: "Access denied — check your API key permissions",
            404: "Endpoint not found — check your API URL",
            429: "Transcription service is rate limited — try again later",
        }
        if response.status_code in errors:
            raise WhisperAPIError(errors[response.status_code])
        if response.status_code >= 500:
            raise WhisperAPIError("Transcription server error — try again later")
        if response.status_code != 200:
            raise WhisperAPIError(f"Transcription service returned HTTP {response.status_code}")
        try:
            result = response.json()
        except ValueError as exc:
            raise WhisperAPIError("The transcription service returned invalid JSON") from exc
        if not isinstance(result, dict) or not isinstance(result.get("text"), str):
            raise WhisperAPIError("The transcription response is missing a text result")
        return result["text"].strip()

    async def transcribe(self, audio_data: bytes) -> str:
        self._validate_backend()
        if not audio_data:
            raise WhisperAPIError("No audio was recorded")
        if self.config.transcription_backend == "local":
            return await asyncio.to_thread(self._local().transcribe_sync, audio_data)
        if self.config.transcription_backend == "whisper_cpp":
            return await asyncio.to_thread(self._cpp().transcribe_sync, audio_data)
        try:
            async with httpx.AsyncClient(timeout=self._timeout()) as client:
                return self._response(
                    await client.post(self.config.api_url, **self._request(audio_data))
                )
        except httpx.TimeoutException as exc:
            raise WhisperAPIError(
                "Request timed out — increase the timeout for long recordings"
            ) from exc
        except httpx.RequestError as exc:
            raise WhisperAPIError(
                "Could not reach the transcription service — check its URL and your connection"
            ) from exc

    def transcribe_sync(self, audio_data: bytes) -> str:
        self._validate_backend()
        if not audio_data:
            raise WhisperAPIError("No audio was recorded")
        if self.config.transcription_backend == "local":
            return self._local().transcribe_sync(audio_data)
        if self.config.transcription_backend == "whisper_cpp":
            return self._cpp().transcribe_sync(audio_data)
        try:
            with httpx.Client(timeout=self._timeout()) as client:
                return self._response(client.post(self.config.api_url, **self._request(audio_data)))
        except httpx.TimeoutException as exc:
            raise WhisperAPIError(
                "Request timed out — increase the timeout for long recordings"
            ) from exc
        except httpx.RequestError as exc:
            raise WhisperAPIError(
                "Could not reach the transcription service — check its URL and your connection"
            ) from exc
