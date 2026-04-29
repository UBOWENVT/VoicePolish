"""
Transcribe Service — converts audio bytes to text using OpenAI Whisper.

This is a SERVICE module: pure business logic, no HTTP concerns.
The router layer (routers/transcribe.py) handles HTTP file uploads;
this file only knows how to take audio bytes + a filename and return text.

Why OpenAI Whisper (vs browser Web Speech API):
  - Cross-browser consistency (Web Speech only works on Chromium)
  - Better accuracy for technical terms, accents, fast speech
  - Doesn't require Google services (works in restricted networks)
  - Returns confidence-scored text, not just guesses
"""

import io
import logging

from openai import OpenAI

from app.core.config import require_openai_key


logger = logging.getLogger(__name__)


# Module-level OpenAI client. Created lazily on first use so importing this
# module doesn't fail when OPENAI_API_KEY is missing.
_client: OpenAI | None = None


def _get_client() -> OpenAI:
    """Lazy singleton for the OpenAI client."""
    global _client
    if _client is None:
        api_key = require_openai_key()
        _client = OpenAI(api_key=api_key)
    return _client


def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "recording.webm",
    language: str | None = None,
) -> str:
    """
    Send audio bytes to OpenAI Whisper and return the transcribed text.

    Args:
        audio_bytes:  raw audio file content (any format Whisper supports:
                      mp3, mp4, mpeg, mpga, m4a, wav, webm)
        filename:     used by the API to detect the audio format from the
                      extension. The bytes are what matters; filename is hint.
        language:     optional ISO-639-1 code ("en", "zh", etc.) to skip
                      auto-detection. None = let Whisper auto-detect.

    Returns:
        The transcribed text as a plain string.

    Raises:
        ValueError:    if audio_bytes is empty
        RuntimeError:  if API key missing or Whisper call fails
    """
    if not audio_bytes:
        raise ValueError("audio_bytes must not be empty")

    client = _get_client()

    # Whisper API expects a file-like object, not raw bytes. We wrap the bytes
    # in BytesIO and give it a `name` attribute so the SDK can infer format.
    # The .name attribute matters: OpenAI's SDK reads it to determine the
    # audio format (it cannot inspect the bytes themselves).
    audio_file = io.BytesIO(audio_bytes)
    audio_file.name = filename

    try:
        # Build the request kwargs. We only pass `language` if it's set,
        # so the API can auto-detect when we don't know.
        kwargs = {
            "model": "whisper-1",
            "file": audio_file,
            "response_format": "text",   # plain text; alternative: "json", "verbose_json", "srt"
        }
        if language:
            kwargs["language"] = language

        # The SDK call. Despite being a network operation, this is sync —
        # OpenAI's Python SDK has both sync and async versions. We use sync
        # to match the rest of our codebase; FastAPI handles the threading.
        response = client.audio.transcriptions.create(**kwargs)

        # When response_format="text", the SDK returns a string directly.
        # For "json" or "verbose_json" it would return a structured object.
        text = response if isinstance(response, str) else getattr(response, "text", "")
        return text.strip()

    except Exception as e:
        # Wrap any SDK / network error into our standard RuntimeError so the
        # router layer can convert it to a clean HTTP response.
        logger.error("Whisper transcription failed: %s", e)
        raise RuntimeError(f"Whisper API call failed: {e}") from e
