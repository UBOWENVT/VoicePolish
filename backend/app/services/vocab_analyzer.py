"""
Vocabulary Analyzer — extracts and tracks word frequencies from transcriptions.

This is a SERVICE module: pure business logic, no HTTP concerns.
Called as a side-effect after each new transcription is saved.

The current implementation is naive — count after stopword removal. M6 will
add TF-IDF to surface "uniquely yours" terms. M7 will add LLM-based filtering.

Key functions:
    extract_words(text)              — pure: text -> list of meaningful words
    update_word_stats(db, text)      — side effect: updates word_stats table
    get_top_suggestions(db, n=20)    — read: top N by raw count (M5)
    get_tfidf_suggestions(db, n=20)  — read: top N by TF-IDF score (M6)
    get_llm_suggestions(db, n=15)    — read: TF-IDF candidates filtered by Claude (M7)
"""

from datetime import datetime
from collections import Counter
from dataclasses import dataclass

import nltk
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from sqlalchemy.orm import Session

from app.models import WordStat, Vocabulary, Transcription


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


# =============================================================================
# M6: TF-IDF based suggestions
# =============================================================================

@dataclass
class TfidfSuggestion:
    """
    A word + its TF-IDF score + raw count, returned by get_tfidf_suggestions.

    This is a plain dataclass (not an ORM model) because TF-IDF scores aren't
    stored anywhere — they're computed on the fly from current data.
    """
    word: str
    score: float       # TF-IDF score; higher = more "distinctive"
    count: int         # raw occurrence count, for context in the UI
    document_count: int  # how many transcriptions this word appears in


def get_tfidf_suggestions(db: Session, limit: int = 20) -> list[TfidfSuggestion]:
    """
    Return top N words ranked by TF-IDF, excluding those already in vocabulary.

    Algorithm:
        1. Pull all transcriptions' raw_text from the DB
        2. Run sklearn's TfidfVectorizer over the corpus
        3. Sum each word's TF-IDF score across all documents
        4. Sort by total score, drop vocabulary words, take top N

    Why this is different from get_top_suggestions:
        Raw counts surface words like "work" / "time" — high frequency but
        also common everywhere. TF-IDF down-weights such words because they
        appear in many documents (low IDF), letting genuinely distinctive
        terms (RAG, embedding, etc.) rise to the top.
    """
    # Lazy import: sklearn is heavy (~50 MB), only load it when this function
    # is actually called. Most requests don't hit TF-IDF, so the count-based
    # path stays light.
    from sklearn.feature_extraction.text import TfidfVectorizer
    import numpy as np

    # ── Step 1: pull the corpus ──
    # We use raw_text (not polished_text) — the user's actual spoken words,
    # not the LLM's reformulation. This matches the M5 hook design.
    transcriptions = db.query(Transcription.raw_text).all()
    corpus = [t.raw_text for t in transcriptions if t.raw_text]

    # Edge case: TF-IDF needs at least 2 documents to compute IDF meaningfully.
    # With 0 or 1 documents, fall back to the count-based ranking so the user
    # still gets something useful in the UI.
    if len(corpus) < 2:
        fallback = get_top_suggestions(db, limit=limit)
        return [
            TfidfSuggestion(word=w.word, score=float(w.count), count=w.count, document_count=1)
            for w in fallback
        ]

    # ── Step 2: run TfidfVectorizer ──
    # We feed it our stopword set so it strips fillers and common words.
    # token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z\-]*[a-zA-Z]\b|\b[a-zA-Z]\b"
    #   matches words of letters and internal hyphens, mirroring _is_word_like.
    # lowercase=True merges "RAG" and "rag" — same as our M5 pipeline.
    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words=list(_STOPWORDS),
        token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z\-]*[a-zA-Z]\b",
        min_df=1,        # include words that appear in at least 1 document
    )
    # tfidf_matrix is a sparse matrix of shape (n_documents, n_unique_words).
    # Each cell is the TF-IDF score of that word in that document.
    tfidf_matrix = vectorizer.fit_transform(corpus)

    # ── Step 3: aggregate scores across documents ──
    # Sum each column → total score per word across all documents.
    # We then squeeze the (1, n_words) result down to a 1-D array.
    summed_scores = np.asarray(tfidf_matrix.sum(axis=0)).flatten()
    feature_names = vectorizer.get_feature_names_out()

    # Also count document frequency (how many docs each word appeared in)
    # for display purposes. tfidf_matrix > 0 gives a binary matrix; sum per
    # column = how many docs contained that word.
    doc_freq = np.asarray((tfidf_matrix > 0).sum(axis=0)).flatten()

    # ── Step 4: filter vocabulary, sort, take top N ──
    existing_terms = {row.term for row in db.query(Vocabulary.term).all()}

    # Build (word, score, doc_count) triples. Multiple guards here:
    #   - drop empty / whitespace-only tokens (sklearn occasionally yields these)
    #   - drop words already in vocabulary
    #   - drop zero-score candidates (no signal at all)
    candidates = [
        (feature_names[i], float(summed_scores[i]), int(doc_freq[i]))
        for i in range(len(feature_names))
        if feature_names[i]
        and feature_names[i].strip()
        and feature_names[i] not in existing_terms
        and float(summed_scores[i]) > 0
    ]
    # Sort by score descending
    candidates.sort(key=lambda x: x[1], reverse=True)
    candidates = candidates[:limit]

    # Look up raw count from word_stats for display.
    # If a sklearn-tokenized word isn't in word_stats (e.g. transcriptions that
    # predate the M5.3 hook), fall back to the document_count as a sensible
    # placeholder so the UI doesn't show "×0".
    word_to_count = {
        row.word: row.count
        for row in db.query(WordStat).filter(WordStat.word.in_([c[0] for c in candidates])).all()
    }

    return [
        TfidfSuggestion(
            word=word,
            score=score,
            count=word_to_count.get(word) or doc_count,
            document_count=doc_count,
        )
        for word, score, doc_count in candidates
    ]


# =============================================================================
# M7: LLM-assisted suggestions (Claude as a semantic filter)
# =============================================================================
# Architecture: two-stage candidate generation.
#   Stage 1 (cheap):  TF-IDF picks ~30 statistically interesting words
#   Stage 2 (smart):  Claude reviews them with context, returns the ~15 it
#                     thinks are genuinely worth adding to a personal
#                     vocabulary, with a suggested replacement and a reason.
#
# This pattern — "cheap algo generates candidates, expensive AI ranks them" —
# is standard in production ML systems (search, recsys, ad ranking).

import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class LlmSuggestion:
    """One vocabulary suggestion produced by the LLM filter."""
    term: str          # the spoken phrase to match (lowercased)
    replacement: str   # the LLM's suggested canonical form
    reason: str        # short human-readable justification
    score: float       # TF-IDF score that earned it a spot in the candidate set
    count: int         # raw occurrence count
    document_count: int  # how many transcriptions this word appears in


# Maximum number of TF-IDF candidates to send to the LLM. Keeps token cost
# bounded; 30 is enough for the LLM to have signal without being overwhelmed.
_LLM_CANDIDATE_POOL = 30

# Maximum number of context snippets per word to include in the prompt.
# More context = better LLM judgment, but more tokens.
_SNIPPETS_PER_WORD = 2
_SNIPPET_CHARS = 100


_LLM_SYSTEM_PROMPT = """You are a personal vocabulary curator. The user records voice notes that get transcribed; afterwards, they review high-frequency words and add domain-specific terms to a custom dictionary used to clean up future transcripts.

You will receive a list of candidate words (already filtered by TF-IDF) along with example sentences where each word appeared. Your job: decide which candidates are genuinely worth adding to the user's personal dictionary, and for each, suggest a canonical "replacement" form.

Good candidates are:
  - Domain-specific terminology (technical terms, jargon, project names, acronyms)
  - Proper nouns (people, products, companies the user works with)
  - Words the user clearly mispronounces or that auto-transcription mangles

Bad candidates (REJECT these):
  - Common English words that just happen to be frequent ("today", "think", "actually")
  - Filler/transition words missed by stopword filters
  - Obvious typos or noise (single random letters, gibberish, transcription artifacts)
  - Inflected forms when the base form is more useful (e.g. prefer "embedding" over "embeddings")

For the replacement field:
  - For acronyms/initialisms, capitalize and optionally expand: "rag" → "RAG (Retrieval-Augmented Generation)"
  - For proper nouns, fix the casing: "openai" → "OpenAI"
  - For technical terms with standard spelling, just match the standard: "finetune" → "fine-tune"
  - For words that are already fine as-is, the replacement equals the term

Respond with ONLY a JSON array, no preamble or markdown. Each item:
{
  "term": "<lowercased original word>",
  "replacement": "<your suggested canonical form>",
  "reason": "<10 words or fewer explaining why this is worth adding>"
}

Return at most 15 items. Omit any candidate you'd reject. STRONGLY PREFER returning fewer items than padding with marginal candidates — an empty list [] is a valid and often correct answer when the user's transcripts don't contain genuine domain-specific terminology. Quality over quantity."""


def _gather_snippets(db: Session, word: str, max_snippets: int = _SNIPPETS_PER_WORD) -> list[str]:
    """
    Find up to N short snippets from transcriptions where `word` appears.
    Used to give the LLM enough context to judge meaning.
    """
    # Case-insensitive substring match. SQLite's LIKE is case-insensitive for
    # ASCII by default, which suits our lowercased word_stats.
    rows = (
        db.query(Transcription.raw_text)
        .filter(Transcription.raw_text.ilike(f"%{word}%"))
        .limit(max_snippets)
        .all()
    )
    snippets = []
    for row in rows:
        text = row.raw_text or ""
        # Find the word and grab a window around it for context.
        idx = text.lower().find(word)
        if idx == -1:
            continue
        start = max(0, idx - _SNIPPET_CHARS // 2)
        end = min(len(text), idx + len(word) + _SNIPPET_CHARS // 2)
        snippet = text[start:end].strip()
        if start > 0:
            snippet = "…" + snippet
        if end < len(text):
            snippet = snippet + "…"
        snippets.append(snippet)
    return snippets


def get_llm_suggestions(db: Session, limit: int = 15) -> list[LlmSuggestion]:
    """
    Two-stage suggestion pipeline:
        1. Get TF-IDF top _LLM_CANDIDATE_POOL words
        2. Send them + example snippets to Claude
        3. Parse Claude's JSON response, join back with TF-IDF scores

    Returns at most `limit` LlmSuggestions. May return fewer if Claude rejects
    most candidates as not worth adding.

    Falls back to converting TF-IDF results to LlmSuggestions (with the word
    itself as replacement, no reason) if the LLM call fails — the user still
    gets useful output.
    """
    # Lazy import: avoids a hard dependency on polish_service when unused.
    from app.services.polish_service import _get_client
    from app.core.config import DEFAULT_ANTHROPIC_MODEL

    # ── Stage 1: get TF-IDF candidates ──
    tfidf_candidates = get_tfidf_suggestions(db, limit=_LLM_CANDIDATE_POOL)
    if not tfidf_candidates:
        return []

    # Index by word for later joining with the LLM's response.
    by_word = {c.word: c for c in tfidf_candidates}

    # ── Build the user prompt: list of candidates with snippets ──
    lines = ["Here are the candidates with example contexts:\n"]
    for cand in tfidf_candidates:
        snippets = _gather_snippets(db, cand.word)
        snippets_str = "\n".join(f'    - "{s}"' for s in snippets) if snippets else "    (no snippets available)"
        lines.append(f"- {cand.word!r} (appears in {cand.document_count} doc(s)):\n{snippets_str}")
    user_prompt = "\n".join(lines)

    # ── Stage 2: ask Claude ──
    try:
        client = _get_client()
        response = client.messages.create(
            model=DEFAULT_ANTHROPIC_MODEL,
            max_tokens=2048,
            system=_LLM_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
        # Concatenate any text blocks (defensive against tool-use blocks).
        raw = "".join(b.text for b in response.content if hasattr(b, "text")).strip()

        # Strip a possible markdown code fence ("```json ... ```") if Claude
        # decides to wrap the JSON despite our instruction.
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1]   # drop the opening fence line
            if raw.endswith("```"):
                raw = raw.rsplit("```", 1)[0]
            raw = raw.strip()

        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError(f"Expected a JSON array, got {type(parsed).__name__}")

    except Exception as e:
        logger.warning("LLM suggestion call failed: %s. Falling back to TF-IDF.", e)
        # Fallback: turn TF-IDF results into LlmSuggestions with sensible defaults.
        return [
            LlmSuggestion(
                term=c.word,
                replacement=c.word,
                reason="(LLM unavailable; raw TF-IDF candidate)",
                score=c.score,
                count=c.count,
                document_count=c.document_count,
            )
            for c in tfidf_candidates[:limit]
        ]

    # ── Stage 3: join LLM output with TF-IDF metadata, build results ──
    results: list[LlmSuggestion] = []
    for item in parsed:
        # Defensive parsing — LLMs sometimes drop fields or invent terms.
        if not isinstance(item, dict):
            continue
        term = (item.get("term") or "").strip().lower()
        replacement = (item.get("replacement") or "").strip()
        reason = (item.get("reason") or "").strip()
        if not term or not replacement:
            continue

        # Look up TF-IDF metadata. If the LLM hallucinated a term not in our
        # candidate pool, skip it — we don't trust suggestions ungrounded in
        # the actual data.
        meta = by_word.get(term)
        if meta is None:
            logger.debug("LLM returned term %r not in candidate pool, skipping", term)
            continue

        results.append(LlmSuggestion(
            term=term,
            replacement=replacement,
            reason=reason,
            score=meta.score,
            count=meta.count,
            document_count=meta.document_count,
        ))
        if len(results) >= limit:
            break

    return results
