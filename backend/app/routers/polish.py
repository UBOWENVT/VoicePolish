"""
Routes for the /api/polish action.

POST /api/polish  -> takes raw text + mode, returns polished text.
                     If transcription_id is provided, also updates that
                     record's polished_text + polish_mode fields.

This is an "action" endpoint, not a CRUD resource. There's no /polish/{id}
because polishing produces no stored resource of its own — the result is
returned to the caller and (optionally) written back to a Transcription row.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Transcription
from app.schemas import PolishRequest, PolishResponse
from app.services.polish_service import polish_text
from app.core.config import DEFAULT_ANTHROPIC_MODEL


router = APIRouter(
    prefix="/api/polish",
    tags=["polish"],
)


@router.post("", response_model=PolishResponse)
def polish(
    payload: PolishRequest,
    db: Session = Depends(get_db),
):
    """
    Refine raw spoken text using the chosen polish mode.

    If `transcription_id` is provided, the result is also persisted to the
    matching Transcription row (polished_text + polish_mode fields).
    """
    # ── Step 1: call the service to compute polished text ──
    try:
        polished = polish_text(
            raw_text=payload.raw_text,
            mode=payload.mode,
            model=payload.model,
        )
    except ValueError as e:
        # Bad input (empty text, unknown mode). 400 = client's fault.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        # Misconfigured server (missing key) or upstream API failure.
        # 502 Bad Gateway = "I tried to call upstream and it didn't work."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e))

    # ── Step 2: optionally persist to the transcription row ──
    persisted_id: int | None = None
    if payload.transcription_id is not None:
        record = (
            db.query(Transcription)
            .filter(Transcription.id == payload.transcription_id)
            .first()
        )
        if record is None:
            # The polish itself succeeded, but the target row doesn't exist.
            # This is a 404 because the resource the client referenced is missing.
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Transcription {payload.transcription_id} not found",
            )

        # SQLAlchemy "unit of work": just modify the object's attributes.
        # On commit, SQLAlchemy detects which fields changed and emits
        # the appropriate UPDATE statement automatically.
        record.polished_text = polished
        record.polish_mode = payload.mode
        db.commit()
        persisted_id = record.id

    # ── Step 3: build the response ──
    return PolishResponse(
        polished_text=polished,
        mode=payload.mode,
        model=payload.model or DEFAULT_ANTHROPIC_MODEL,
        transcription_id=persisted_id,
    )
