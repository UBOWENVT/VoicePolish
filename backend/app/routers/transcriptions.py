"""
Routes for the /api/transcriptions resource.

Endpoints:
    POST   /api/transcriptions        Create a new transcription
    GET    /api/transcriptions        List all transcriptions (newest first)
    GET    /api/transcriptions/{id}   Get one transcription by id
"""

import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Transcription
from app.schemas import TranscriptionCreate, TranscriptionRead
from app.services.vocab_analyzer import update_word_stats

# Module-level logger. Anything we log here goes to uvicorn's stdout, alongside
# the request logs. The name (__name__) becomes "app.routers.transcriptions"
# in the log line, making it easy to grep.
logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# APIRouter — a mini FastAPI app that we'll mount onto the main app.
# prefix="/api/transcriptions" means every route below implicitly starts with
# that path, so we only write the remainder.
# tags=["transcriptions"] groups these routes together in the /docs UI.
# -----------------------------------------------------------------------------
router = APIRouter(
    prefix="/api/transcriptions",
    tags=["transcriptions"],
)


# -----------------------------------------------------------------------------
# POST /api/transcriptions
# -----------------------------------------------------------------------------
# `response_model=TranscriptionRead` tells FastAPI to filter the returned
# object through that schema before serializing. Extra fields get dropped,
# missing fields cause errors. This is your contract with the frontend.
#
# `status_code=201` — HTTP 201 Created is the proper code for successful
# resource creation. Default would be 200 OK, which is less precise.
# -----------------------------------------------------------------------------
@router.post("", response_model=TranscriptionRead, status_code=status.HTTP_201_CREATED)
def create_transcription(
    payload: TranscriptionCreate,
    db: Session = Depends(get_db),
):
    """Create a new transcription record from a POST body."""
    # Build a SQLAlchemy object from the validated Pydantic data.
    # `payload.model_dump()` turns the Pydantic model into a plain dict,
    # then `**` unpacks it as keyword arguments to the SQLAlchemy class.
    new_record = Transcription(**payload.model_dump())

    db.add(new_record)        # Stage the INSERT
    db.commit()               # Actually run it — now the row exists in DB
    db.refresh(new_record)    # Pull back server-generated fields (id, created_at)

    # ── Side-effect hook: update word frequency stats ──
    # This is a SECONDARY concern. If it fails, the transcription is still
    # saved (more important to the user). We log the error so it's debuggable
    # but never re-raise — the user shouldn't see a failed save toast just
    # because word counting hiccuped.
    try:
        update_word_stats(db, new_record.raw_text)
    except Exception as e:
        logger.warning(
            "update_word_stats failed for transcription id=%s: %s",
            new_record.id, e,
        )

    return new_record


# -----------------------------------------------------------------------------
# GET /api/transcriptions
# -----------------------------------------------------------------------------
# Returns a list. `response_model=List[TranscriptionRead]` — FastAPI applies
# the schema to every item in the list.
#
# Query parameters `skip` and `limit` are conventional names for pagination.
# In the URL they look like: /api/transcriptions?skip=0&limit=20
# -----------------------------------------------------------------------------
@router.get("", response_model=List[TranscriptionRead])
def list_transcriptions(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """List transcriptions, newest first."""
    records = (
        db.query(Transcription)
        .order_by(Transcription.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return records


# -----------------------------------------------------------------------------
# GET /api/transcriptions/{transcription_id}
# -----------------------------------------------------------------------------
# `{transcription_id}` in the path is a PATH PARAMETER. FastAPI passes
# whatever is in that slot to the matching function argument, converting
# it to the declared type (int). If someone requests /api/transcriptions/foo,
# FastAPI auto-returns 422 because "foo" isn't an int.
# -----------------------------------------------------------------------------
@router.get("/{transcription_id}", response_model=TranscriptionRead)
def get_transcription(
    transcription_id: int,
    db: Session = Depends(get_db),
):
    """Fetch a single transcription by its id."""
    record = db.query(Transcription).filter(Transcription.id == transcription_id).first()
    if record is None:
        # Standard way to send a clean 404 response. The `detail` becomes
        # the error message in the JSON response body.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transcription {transcription_id} not found",
        )
    return record
