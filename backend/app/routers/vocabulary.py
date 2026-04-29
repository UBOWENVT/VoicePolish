"""
Routes for the /api/vocabulary resource.

Endpoints:
    POST   /api/vocabulary        Create a new vocabulary
    GET    /api/vocabulary        List all vocabulary (newest first)
    GET    /api/vocabulary/{id}   Get one vocabulary by id
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Vocabulary
from app.schemas import VocabularyCreate, VocabularyRead


# -----------------------------------------------------------------------------
# APIRouter — a mini FastAPI app that we'll mount onto the main app.
# prefix="/api/vocabulary" means every route below implicitly starts with
# that path, so we only write the remainder.
# tags=["vocabulary"] groups these routes together in the /docs UI.
# -----------------------------------------------------------------------------
router = APIRouter(
    prefix="/api/vocabulary",
    tags=["vocabulary"],
)


# -----------------------------------------------------------------------------
# POST /api/vocabulary
# -----------------------------------------------------------------------------
# `response_model=VocabularyRead` tells FastAPI to filter the returned
# object through that schema before serializing. Extra fields get dropped,
# missing fields cause errors. This is your contract with the frontend.
#
# `status_code=201` — HTTP 201 Created is the proper code for successful
# resource creation. Default would be 200 OK, which is less precise.
# -----------------------------------------------------------------------------
@router.post("", response_model=VocabularyRead, status_code=status.HTTP_201_CREATED)
def create_vocabulary(
    payload: VocabularyCreate,
    db: Session = Depends(get_db),
):
    """Create a new vocabulary record from a POST body."""
    # Build a SQLAlchemy object from the validated Pydantic data.
    # `payload.model_dump()` turns the Pydantic model into a plain dict,
    # then `**` unpacks it as keyword arguments to the SQLAlchemy class.
    new_record = Vocabulary(**payload.model_dump())

    db.add(new_record)        # Stage the INSERT
    db.commit()               # Actually run it — now the row exists in DB
    db.refresh(new_record)    # Pull back server-generated fields (id, created_at)

    return new_record


# -----------------------------------------------------------------------------
# GET /api/vocabulary
# -----------------------------------------------------------------------------
# Returns a list. `response_model=List[VocabularyRead]` — FastAPI applies
# the schema to every item in the list.
#
# Query parameters `skip` and `limit` are conventional names for pagination.
# In the URL they look like: /api/vocabulary?skip=0&limit=20
# -----------------------------------------------------------------------------
@router.get("", response_model=List[VocabularyRead])
def list_vocabulary(
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    """List vocabulary, newest first."""
    records = (
        db.query(Vocabulary)
        .order_by(Vocabulary.created_at.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return records


# -----------------------------------------------------------------------------
# GET /api/vocabulary/{vocabulary_id}
# -----------------------------------------------------------------------------
# `{vocabulary_id}` in the path is a PATH PARAMETER. FastAPI passes
# whatever is in that slot to the matching function argument, converting
# it to the declared type (int). If someone requests /api/vocabulary/foo,
# FastAPI auto-returns 422 because "foo" isn't an int.
# -----------------------------------------------------------------------------
@router.get("/{vocabulary_id}", response_model=VocabularyRead)
def get_vocabulary(
    vocabulary_id: int,
    db: Session = Depends(get_db),
):
    """Fetch a single vocabulary by its id."""
    record = db.query(Vocabulary).filter(Vocabulary.id == vocabulary_id).first()
    if record is None:
        # Standard way to send a clean 404 response. The `detail` becomes
        # the error message in the JSON response body.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vocabulary {vocabulary_id} not found",
        )
    return record
