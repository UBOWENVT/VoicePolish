"""
Routes for the /api/vocabulary resource.

Endpoints:
    POST   /api/vocabulary        Create a new vocabulary
    GET    /api/vocabulary        List all vocabulary (newest first)
    GET    /api/vocabulary/{id}   Get one vocabulary by id
"""

from typing import List
from enum import Enum
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.models import Vocabulary
from app.schemas import VocabularyCreate, VocabularyRead, VocabularySuggestion
from app.services.vocab_analyzer import get_top_suggestions, get_tfidf_suggestions, get_llm_suggestions


# -----------------------------------------------------------------------------
# Enum for the `method` query parameter on /suggestions.
# Inheriting from str makes Enum members usable as plain strings (in JSON,
# in URL params, in equality checks against str literals). FastAPI sees the
# Enum and:
#   1. Validates the URL param value (rejects unknown methods with a 422)
#   2. Renders a dropdown in /docs with the allowed values
# -----------------------------------------------------------------------------
class SuggestionMethod(str, Enum):
    count = "count"
    tfidf = "tfidf"
    llm = "llm"


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
    try:
        db.commit()           # Actually run it — now the row exists in DB
    except IntegrityError:
        # Most likely cause: term already exists (UNIQUE constraint violation).
        # Roll back so the session is usable for subsequent queries.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Term {payload.term!r} already exists in vocabulary",
        )
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
# GET /api/vocabulary/suggestions
# -----------------------------------------------------------------------------
# Returns the top N most-frequent words from word_stats that are NOT already
# in the user's vocabulary. The user can then choose to add them.
#
# IMPORTANT: this route must be declared BEFORE /{vocabulary_id} below.
# FastAPI matches routes in declaration order; if /{vocabulary_id} comes first,
# the literal path "suggestions" gets matched as a path parameter and FastAPI
# tries to parse it as an int, returning 422.
#
# `method` controls the ranking algorithm:
#   - "count" (default): raw frequency, simple but biased toward common words
#   - "tfidf": TF-IDF score, surfaces words distinctive to your corpus
#   - "llm": TF-IDF candidates filtered by Claude, with replacement suggestions
# -----------------------------------------------------------------------------
@router.get("/suggestions", response_model=List[VocabularySuggestion])
def list_suggestions(
    limit: int = 20,
    method: SuggestionMethod = SuggestionMethod.count,
    db: Session = Depends(get_db),
):
    """Return top frequent words not yet in vocabulary, ranked by chosen method."""
    if method == SuggestionMethod.llm:
        # LLM path: returns LlmSuggestion dataclasses with replacement + reason.
        # Note: this calls Claude, takes a few seconds, costs API tokens.
        results = get_llm_suggestions(db, limit=limit)
        return [
            VocabularySuggestion(
                word=r.term,
                count=r.count,
                score=r.score,
                document_count=r.document_count,
                replacement=r.replacement,
                reason=r.reason,
            )
            for r in results
        ]

    if method == SuggestionMethod.tfidf:
        # TF-IDF path: returns TfidfSuggestion dataclasses with score + doc_count.
        results = get_tfidf_suggestions(db, limit=limit)
        return [
            VocabularySuggestion(
                word=r.word,
                count=r.count,
                score=r.score,
                document_count=r.document_count,
                # last_seen not applicable in TF-IDF path; left as None
            )
            for r in results
        ]

    # Default: count path. Returns WordStat ORM objects directly; Pydantic's
    # from_attributes=True picks the matching fields.
    return get_top_suggestions(db, limit=limit)


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


# -----------------------------------------------------------------------------
# DELETE /api/vocabulary/{vocabulary_id}
# -----------------------------------------------------------------------------
# Removes a vocabulary entry. Returns 204 No Content on success — the standard
# REST convention for deletion (the caller already knows the id, no body needed).
# -----------------------------------------------------------------------------
@router.delete("/{vocabulary_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_vocabulary(
    vocabulary_id: int,
    db: Session = Depends(get_db),
):
    """Delete a vocabulary entry by id."""
    record = db.query(Vocabulary).filter(Vocabulary.id == vocabulary_id).first()
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Vocabulary {vocabulary_id} not found",
        )
    db.delete(record)
    db.commit()
    # No return value — 204 means "success, no body".
