"""
Routes for the /api/transcribe action.

POST /api/transcribe  -> takes an uploaded audio file, returns transcribed text.

This is an "action" endpoint, not a CRUD resource. The transcription itself
is returned and (if the client wants) can be saved via POST /api/transcriptions.
We deliberately keep "transcribe" and "store" as separate operations so the
client controls what gets persisted (e.g. a draft might not be saved).
"""

import logging
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.services.transcribe_service import transcribe_audio


logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/transcribe",
    tags=["transcribe"],
)


class TranscribeResponse(BaseModel):
    """Response for POST /api/transcribe."""
    text: str
    language: Optional[str] = None


# Maximum upload size in bytes. Whisper API itself accepts up to 25 MB; we
# guard a bit lower to leave headroom and reject obvious mistakes.
_MAX_AUDIO_BYTES = 20 * 1024 * 1024  # 20 MB


@router.post("", response_model=TranscribeResponse)
async def transcribe(
    # File() declares this is a multipart file upload.
    # UploadFile is FastAPI's wrapper around an uploaded file — it's a stream,
    # so we don't load the entire thing into memory until we call .read().
    file: UploadFile = File(..., description="Audio file (webm, mp3, wav, m4a, etc.)"),
    # Form() declares additional fields in the same multipart payload.
    # Optional language hint — pass "en", "zh", etc., or omit to auto-detect.
    language: Optional[str] = Form(default=None),
):
    """Transcribe an uploaded audio file using OpenAI Whisper."""
    # Read the uploaded bytes. For typical 1-3 minute recordings this is a
    # few MB at most — fine to load fully into memory. For huge files, we'd
    # stream in chunks, but Whisper has a 25 MB hard limit anyway.
    audio_bytes = await file.read()

    if not audio_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio file too large ({len(audio_bytes)} bytes). Max is {_MAX_AUDIO_BYTES} bytes.",
        )

    # Filename hint is what Whisper uses to detect format. UploadFile gives
    # us the original filename from the client; fall back to a sensible
    # default if missing.
    filename = file.filename or "recording.webm"

    try:
        text = transcribe_audio(
            audio_bytes=audio_bytes,
            filename=filename,
            language=language,
        )
    except ValueError as e:
        # Bad input from caller (empty audio, malformed)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        # Misconfigured server or upstream API failure
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    return TranscribeResponse(text=text, language=language)
