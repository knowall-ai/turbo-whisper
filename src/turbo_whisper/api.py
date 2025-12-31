"""Whisper API client - compatible with OpenAI API and faster-whisper-server."""

import httpx

from .config import Config


class WhisperAPIError(Exception):
    """Error communicating with Whisper API."""

    pass


class WhisperClient:
    """Client for OpenAI-compatible Whisper API."""

    def __init__(self, config: Config):
        self.config = config

    async def transcribe(self, audio_data: bytes) -> str:
        """
        Send audio to Whisper API and return transcription.

        Args:
            audio_data: WAV audio data as bytes

        Returns:
            Transcribed text
        """
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        files = {
            "file": ("audio.wav", audio_data, "audio/wav"),
        }

        data = {
            "model": "whisper-1",  # Ignored by faster-whisper-server but required by OpenAI
            "language": self.config.language,
            "response_format": "json",
            "prompt": "Use proper punctuation: commas, periods, question marks.",
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.config.api_url,
                    headers=headers,
                    files=files,
                    data=data,
                )

                if response.status_code != 200:
                    raise WhisperAPIError(f"API returned {response.status_code}: {response.text}")

                result = response.json()
                return result.get("text", "").strip()

        except httpx.TimeoutException:
            raise WhisperAPIError("Request timed out")
        except httpx.RequestError as e:
            raise WhisperAPIError(f"Request failed: {e}")
        except Exception as e:
            raise WhisperAPIError(f"Unexpected error: {e}")

    def transcribe_sync(self, audio_data: bytes) -> str:
        """Synchronous version of transcribe."""
        headers = {}
        if self.config.api_key:
            headers["Authorization"] = f"Bearer {self.config.api_key}"

        files = {
            "file": ("audio.wav", audio_data, "audio/wav"),
        }

        data = {
            "model": "whisper-1",
            "language": self.config.language,
            "response_format": "json",
            "prompt": "Use proper punctuation: commas, periods, question marks.",
        }

        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(
                    self.config.api_url,
                    headers=headers,
                    files=files,
                    data=data,
                )

                if response.status_code == 401:
                    raise WhisperAPIError("Unauthorized - check your API key in settings")
                elif response.status_code == 403:
                    raise WhisperAPIError("Access denied - check your API key permissions")
                elif response.status_code == 404:
                    raise WhisperAPIError("API endpoint not found - check your API URL")
                elif response.status_code >= 500:
                    raise WhisperAPIError("Server error - try again later")
                elif response.status_code != 200:
                    raise WhisperAPIError(f"API error ({response.status_code})")

                result = response.json()
                return result.get("text", "").strip()

        except httpx.TimeoutException:
            raise WhisperAPIError("Request timed out - server may be busy")
        except httpx.ConnectError:
            raise WhisperAPIError("Could not connect - check internet/API URL")
        except httpx.RequestError as e:
            raise WhisperAPIError(f"Connection error: {e}")
