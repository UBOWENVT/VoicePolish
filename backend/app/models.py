"""
VoicePolish Backend — Database Models

Each class in this file corresponds to one table in the database.
All models inherit from Base (defined in database.py) so SQLAlchemy knows
to include them when it creates tables.

Tables defined here:
    Transcription  — one row per recording session
    Vocabulary     — user's custom word dictionary
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.sql import func

from app.database import Base


# -----------------------------------------------------------------------------
# Transcription: one row per recording session
# -----------------------------------------------------------------------------
# Stores the raw speech-to-text output AND (optionally) the polished version.
# polished_text/polish_mode are nullable because a user might record but not
# polish, or polish later in a separate step.
# -----------------------------------------------------------------------------
class Transcription(Base):
    __tablename__ = "transcriptions"

    # Primary key — auto-incrementing integer.
    id = Column(Integer, primary_key=True, index=True)

    # The raw speech-to-text output. Required (cannot be empty/null).
    raw_text = Column(Text, nullable=False)

    # Polished version, produced by LLM. May be null if not yet polished.
    polished_text = Column(Text, nullable=True)

    # Which polish mode was used: "clean" | "formal" | "casual" | "bullets" | "summary"
    # Stored as a short string. Null if never polished.
    polish_mode = Column(String(32), nullable=True)

    # Language code of the recording: "en-US", "zh-CN", etc. Null = auto-detect.
    language = Column(String(16), nullable=True)

    # Creation timestamp — automatically set on insert.
    # `default=datetime.utcnow` passes the FUNCTION itself (no parentheses),
    # so SQLAlchemy calls it fresh for each new row.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        """Developer-friendly string for debugging. Shows up when you print() the object."""
        preview = (self.raw_text or "")[:30]
        return f"<Transcription id={self.id} raw={preview!r}>"


# -----------------------------------------------------------------------------
# Vocabulary: user's custom word dictionary
# -----------------------------------------------------------------------------
# The user can define "spoken phrase -> replacement" pairs. These are applied
# before polish so the LLM sees the user's intended terms.
#
# `source` tracks how the entry was added:
#   "manual"          — user typed it in the Dictionary panel
#   "auto_suggested"  — extracted from high-frequency words (later milestones)
#                       and then accepted by the user
# -----------------------------------------------------------------------------
class Vocabulary(Base):
    __tablename__ = "vocabulary"

    id = Column(Integer, primary_key=True, index=True)

    # The spoken phrase to match. unique=True means no duplicates allowed.
    # index=True creates a database index for fast lookups — we'll query
    # this column often when applying the dictionary to a transcript.
    term = Column(String(128), nullable=False, unique=True, index=True)

    # What to replace the term with.
    replacement = Column(String(256), nullable=False)

    # How this entry was created. String with a fixed set of values.
    # Default "manual" — if we don't say otherwise, assume the user added it.
    source = Column(String(32), nullable=False, default="manual")

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    def __repr__(self):
        return f"<Vocabulary {self.term!r} -> {self.replacement!r}>"
