"""
Vocabulary Analyzer — extracts and tracks word frequencies from transcriptions.

This is a SERVICE module: pure business logic, no HTTP concerns.
Called as a side-effect after each new transcription is saved.

The current implementation is naive — count after stopword removal. M6 will
add TF-IDF to surface "uniquely yours" terms. M7 will add LLM-based filtering.

Key functions:
    extract_words(text)            — pure: text -> list of meaningful words
    update_word_stats(db, text)    — side effect: updates word_stats table
    get_top_suggestions(db, n=20)  — read: top N words not yet in vocabulary
"""

from datetime import datetime
from collections import Counter

import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from sqlalchemy.orm import Session

from app.models import WordStat, Vocabulary


# -----------------------------------------------------------------------------
# Stopword set — built once at module load.
# We use NLTK's English stopwords plus a few extras specific to spoken English
# that NLTK doesn't include (filler words people say a lot).
# -----------------------------------------------------------------------------
_STOPWORDS: set[str] = set(stopwords.words("english")) | {
    # Common spoken filler words not in NLTK's default list
    "um", "uh", "uhh", "umm", "hmm", "like", "okay", "ok", "yeah",
    "actually", "basically", "literally", "really", "right", "well",
    "kind", "sort", "thing", "stuff", "lot", "lots",
    # Contractions NLTK splits but doesn't filter
    "n't", "'s", "'re", "'ve", "'ll", "'d", "'m",
    # Single letters that survive tokenization
    "i", "a",
}


# Minimum word length to consider. Filters out things like "u", "k" that
# slip through. 2 = include "ai", "ml", "ui" etc. which we want.
_MIN_WORD_LENGTH = 2


def _is_word_like(token: str) -> bool:
    """
    Return True if the token looks like a real word.

    Allowed: pure letters ("rag") OR letters with internal hyphens
    ("rag-based", "state-of-the-art"). Internal means not at the start or end.

    Rejected: numbers, punctuation, contraction fragments ("'s", "n't"),
    leading/trailing hyphens.
    """
    if not token:
        return False
    if token.isalpha():
        return True
    # Allow internal hyphens: must start and end with a letter, and every
    # character is either a letter or a hyphen.
    if (
        token[0].isalpha()
        and token[-1].isalpha()
        and all(c.isalpha() or c == "-" for c in token)
    ):
        return True
    return False


def extract_words(text: str) -> list[str]:
    """
    Tokenize a chunk of text and return only "meaningful" words.

    Pipeline:
      1. Lowercase
      2. NLTK tokenization (handles punctuation, contractions)
      3. Keep only alphabetic tokens (drops numbers, punctuation)
      4. Drop stopwords
      5. Drop tokens shorter than _MIN_WORD_LENGTH

    Returns a flat list (preserving order, with duplicates) so the caller can
    do further analysis like Counter() if needed.
    """
    if not text or not text.strip():
        return []

    # Lowercase first so "RAG" and "rag" merge into one count.
    tokens = word_tokenize(text.lower())

    return [
        tok for tok in tokens
        if _is_word_like(tok)
        and tok not in _STOPWORDS
        and len(tok) >= _MIN_WORD_LENGTH
    ]


def update_word_stats(db: Session, text: str) -> dict[str, int]:
    """
    Process a transcription and update the word_stats table.

    For every meaningful word in `text`:
      - If it's already in word_stats, increment its count and update last_seen.
      - If not, insert a new row with count = (occurrences in this text).

    Returns a dict {word: total_count_after_update} for the words seen in
    this text, useful for debugging / response payloads.
    """
    words = extract_words(text)
    if not words:
        return {}

    # Count occurrences within THIS text first, then update DB once per
    # unique word. Avoids hitting the DB N times for "rag rag rag rag rag".
    occurrences: Counter[str] = Counter(words)

    now = datetime.utcnow()
    updated: dict[str, int] = {}

    for word, delta in occurrences.items():
        # UPSERT: query first, then either UPDATE or INSERT.
        existing = db.query(WordStat).filter(WordStat.word == word).first()
        if existing:
            existing.count += delta
            existing.last_seen = now
            updated[word] = existing.count
        else:
            new_row = WordStat(word=word, count=delta, last_seen=now)
            db.add(new_row)
            updated[word] = delta

    db.commit()
    return updated


def get_top_suggestions(db: Session, limit: int = 20) -> list[WordStat]:
    """
    Return the top N most-frequent words that are NOT already in the user's
    vocabulary table. These become the "Suggestions" surface in the UI.

    Implementation: subquery to get all existing vocabulary terms (lowercased),
    then filter word_stats by exclusion.
    """
    # Subquery: every term currently in Vocabulary, lowercased to match
    # word_stats which stores lowercase.
    existing_terms_subq = db.query(Vocabulary.term).subquery()

    # Note: This case-sensitivity assumption holds only for English. For mixed
    # scripts we'd need func.lower() on both sides — fine for M5.
    return (
        db.query(WordStat)
        .filter(~WordStat.word.in_(existing_terms_subq))
        .order_by(WordStat.count.desc(), WordStat.last_seen.desc())
        .limit(limit)
        .all()
    )
