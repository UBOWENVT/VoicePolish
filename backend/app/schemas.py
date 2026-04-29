"""
VoicePolish Backend — Pydantic Schemas

Pydantic schemas define the SHAPE of data crossing the HTTP boundary:
  - What JSON a client is allowed to POST (request bodies)
  - What JSON the server returns (response bodies)

These are separate from SQLAlchemy models (models.py) because:
  - Clients should NOT set server-controlled fields (id, created_at)
  - Responses may need to hide internal fields
  - Input validation happens here automatically (type checks, required fields)
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


# =============================================================================
# Transcription schemas
# =============================================================================

class TranscriptionBase(BaseModel):
    """Fields shared between create and read schemas."""
    raw_text: str
    polished_text: Optional[str] = None
    polish_mode: Optional[str] = None
    language: Optional[str] = None


class TranscriptionCreate(TranscriptionBase):
    """
    Schema for POST /api/transcriptions request body.
    Inherits all fields from Base. Notice `id` and `created_at` are NOT here —
    the client is not allowed to set them.
    """
    pass


class TranscriptionRead(TranscriptionBase):
    """
    Schema for API responses.
    Adds server-generated fields: id, created_at.
    """
    id: int
    created_at: datetime

    # Tell Pydantic: "When converting a SQLAlchemy Transcription object into
    # this schema, read attributes off the object instead of expecting a dict."
    # Without this, FastAPI cannot serialize SQLAlchemy objects automatically.
    model_config = ConfigDict(from_attributes=True)


# =============================================================================
# Vocabulary schemas
# =============================================================================

class VocabularyBase(BaseModel):
    """Fields shared between create and read schemas."""
    term: str
    replacement: str
    source: Optional[str] = "manual"


class VocabularyCreate(VocabularyBase):
    """
    Schema for POST /api/vocabulary request body.
    Inherits all fields from Base. Notice `id` and `created_at` are NOT here —
    the client is not allowed to set them.
    """
    pass


class VocabularyRead(VocabularyBase):
    """
    Schema for API responses.
    Adds server-generated fields: id, created_at.
    """
    id: int
    created_at: datetime

    # Tell Pydantic: "When converting a SQLAlchemy Vocabulary object into
    # this schema, read attributes off the object instead of expecting a dict."
    # Without this, FastAPI cannot serialize SQLAlchemy objects automatically.
    model_config = ConfigDict(from_attributes=True)    
