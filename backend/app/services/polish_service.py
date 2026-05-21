"""
Polish Service — calls Claude to refine transcribed text.

This is a SERVICE module: pure business logic, no HTTP/FastAPI concerns.
The router layer (routers/polish.py) handles HTTP; this file only knows how
to take text + a mode and return polished text.

Why this lives outside the router:
  - Reusable: future features (auto-analysis, batch jobs) can import polish_text()
    without going through HTTP
  - Testable: we can unit-test polishing logic without spinning up a server
  - Swappable: switching from Anthropic to OpenAI later means changing only
    this file, not every route that polishes text
"""

from anthropic import Anthropic

import logging
import time

from app.core.config import require_anthropic_key, DEFAULT_ANTHROPIC_MODEL


logger = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Prompts per polish mode.
# Keep these as plain strings here so they're easy to tweak without touching
# code logic. If they grow, we'd move them to a separate prompts.py file.
# -----------------------------------------------------------------------------
POLISH_PROMPTS = {
    "clean": (
        "You are a transcription editor. Clean up the following spoken text: "
        "remove filler words (um, uh, like, you know), fix obvious speech "
        "stumbles, add punctuation, and capitalize properly. Preserve the "
        "speaker's voice and meaning exactly. Return ONLY the cleaned text, "
        "no preamble or explanation."
    ),
    "formal": (
        "Rewrite the following spoken text in a formal, professional tone "
        "suitable for written business communication. Keep the original meaning "
        "and key points. Return ONLY the rewritten text."
    ),
    "casual": (
        "Rewrite the following spoken text in a friendly, conversational tone "
        "as if writing a casual message to a colleague. Keep it natural and "
        "warm. Return ONLY the rewritten text."
    ),
    "bullets": (
        "Convert the following spoken text into a clean bullet-point list "
        "capturing the key points. Use concise phrasing. Return ONLY the "
        "bullets, one per line, each starting with a hyphen."
    ),
    "summary": (
        "Summarize the following spoken text in 2-3 sentences, preserving the "
        "main idea. Return ONLY the summary."
    ),
}


# Module-level Anthropic client. Created lazily on first use so importing this
# module doesn't fail when ANTHROPIC_API_KEY is missing (e.g. in tests that
# stub the service).
_client: Anthropic | None = None


def _get_client() -> Anthropic:
    """Lazy singleton for the Anthropic client."""
    global _client
    if _client is None:
        api_key = require_anthropic_key()  # raises clear error if missing
        _client = Anthropic(api_key=api_key)
    return _client


def polish_text(
    raw_text: str,
    mode: str = "clean",
    model: str | None = None,
) -> str:
    """
    Send raw_text to Claude and return the polished version.

    Args:
        raw_text:  the speech-to-text output to refine
        mode:      one of POLISH_PROMPTS keys (clean, formal, casual, bullets, summary)
        model:     override the default model for this call

    Returns:
        polished text string

    Raises:
        ValueError:    if mode is not recognized
        RuntimeError:  if API key missing or Anthropic call fails
    """
    if mode not in POLISH_PROMPTS:
        raise ValueError(
            f"Unknown polish mode: {mode!r}. "
            f"Valid modes: {list(POLISH_PROMPTS.keys())}"
        )
    if not raw_text or not raw_text.strip():
        raise ValueError("raw_text must not be empty")

    system_prompt = POLISH_PROMPTS[mode]
    client = _get_client()
    chosen_model = model or DEFAULT_ANTHROPIC_MODEL

    # Time the call so we can chart LLM latency in Grafana.
    start = time.monotonic()

    try:
        # Anthropic Messages API call.
        # `system` carries the instructions; `messages` carries the user content.
        # max_tokens caps the reply length so a runaway model can't burn budget.
        response = client.messages.create(
            model=chosen_model,
            max_tokens=1024,
            system=system_prompt,
            messages=[
                {"role": "user", "content": raw_text}
            ],
        )
    except Exception as e:
        # Structured failure log — enables Loki/Grafana to compute error rate.
        logger.error(
            "ai_api.call",
            extra={
                "event": "ai_api.call",
                "provider_type": "llm",
                "provider": "anthropic",
                "model": chosen_model,
                "mode": mode,
                "status": "error",
                "duration_ms": int((time.monotonic() - start) * 1000),
                "error_type": type(e).__name__,
                "error_message": str(e)[:500],  # truncate to keep log size bounded
            },
        )
        raise RuntimeError(f"Anthropic API call failed: {e}") from e

    duration_ms = int((time.monotonic() - start) * 1000)

    # response.content is a list of content blocks. For a plain text reply
    # there's one TextBlock. We concatenate any text blocks defensively.
    text_parts = [block.text for block in response.content if hasattr(block, "text")]
    polished = "".join(text_parts).strip()

    # Structured success log — enables Loki/Grafana to count calls + chart latency.
    # Token counts come from Anthropic's response usage block; helps cost dashboards.
    usage = getattr(response, "usage", None)
    logger.info(
        "ai_api.call",
        extra={
            "event": "ai_api.call",
            "provider_type": "llm",
            "provider": "anthropic",
            "model": chosen_model,
            "mode": mode,
            "status": "success",
            "duration_ms": duration_ms,
            "input_tokens": getattr(usage, "input_tokens", None) if usage else None,
            "output_tokens": getattr(usage, "output_tokens", None) if usage else None,
            "output_chars": len(polished),
        },
    )

    return polished
