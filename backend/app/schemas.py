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


# =============================================================================
# Polish schemas
# =============================================================================
# Polish is an ACTION, not a stored resource. So instead of Base/Create/Read,
# we have Request/Response — just an input shape and an output shape.

from typing import Literal

PolishMode = Literal["clean", "formal", "casual", "bullets", "summary"]


class PolishRequest(BaseModel):
    """Input for POST /api/polish."""
    raw_text: str
    mode: PolishMode = "clean"
    # Optional: override the default model. Most callers will omit this.
    model: Optional[str] = None
    # Optional: if provided, the polish result will be written back to this
    # transcription's polished_text + polish_mode fields. If omitted, polish
    # only computes and returns the result without touching the database.
    transcription_id: Optional[int] = None


# =============================================================================
# Vocabulary suggestion schemas (M5 + M6)
# =============================================================================
# Suggestions are derived from word_stats / TF-IDF, not stored as their own
# resource. The schema is a SUPERSET of fields used by either ranking method:
#   - count + last_seen: populated when method="count"
#   - score + document_count: populated when method="tfidf"
# Fields irrelevant to the chosen method come back as null. This keeps the
# frontend's parsing logic simple (one shape) at the cost of a few null fields.

class VocabularySuggestion(BaseModel):
    """One candidate word the user might want to add to their vocabulary."""
    word: str
    count: int
    # Only populated when method="count"
    last_seen: Optional[datetime] = None
    # Only populated when method="tfidf"
    score: Optional[float] = None
    document_count: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class PolishResponse(BaseModel):
    """Output of POST /api/polish."""
    polished_text: str
    mode: PolishMode
    model: str
    # When transcription_id was given and the update succeeded, this echoes
    # back the id so the client can confirm. None when no update happened.
    transcription_id: Optional[int] = None
