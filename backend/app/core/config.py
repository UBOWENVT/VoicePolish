"""
Centralized configuration for the VoicePolish backend.

This module:
  1. Loads variables from a `.env` file (in development) into os.environ.
  2. Reads them out into well-named Python constants.
  3. Provides a single source of truth — every other file imports from here
     instead of touching os.environ directly.

The `.env` file is git-ignored (see .gitignore) so secrets never leave your
machine. In production (e.g. on Railway/Render), real environment variables
are set in the platform's dashboard and `load_dotenv()` simply finds nothing
to load — that's expected and harmless.
"""

import os
from dotenv import load_dotenv


# -----------------------------------------------------------------------------
# Step 1: Load the .env file.
# load_dotenv() searches for a file named ".env" starting from the current
# working directory and walking up. If it finds one, every KEY=value line
# becomes an entry in os.environ.
#
# If the .env file doesn't exist (e.g. in production), load_dotenv() returns
# False silently — no error. That's the design: in prod, the real env vars
# are already set by the platform.
# -----------------------------------------------------------------------------
load_dotenv()


# -----------------------------------------------------------------------------
# Step 2: Read variables into typed Python constants.
#
# os.environ.get("KEY") returns the value or None if missing.
# We DON'T raise an error when a key is missing here, because some keys are
# optional (e.g. you might not have an OpenAI key if you only use Anthropic).
# Code that actually needs a key should check for it at use time.
# -----------------------------------------------------------------------------

# LLM provider API keys
ANTHROPIC_API_KEY: str | None = os.environ.get("ANTHROPIC_API_KEY")
OPENAI_API_KEY: str | None = os.environ.get("OPENAI_API_KEY")
GOOGLE_API_KEY: str | None = os.environ.get("GOOGLE_API_KEY")

# Default model choices (override per-request later if needed)
DEFAULT_ANTHROPIC_MODEL: str = os.environ.get(
    "DEFAULT_ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"
)


# -----------------------------------------------------------------------------
# Step 3: Sanity helpers.
#
# A small function the rest of the app can call to confirm a key is present
# before attempting an LLM call. Better than crashing in the middle of a
# request with a confusing SDK error.
# -----------------------------------------------------------------------------

def require_anthropic_key() -> str:
    """Return ANTHROPIC_API_KEY, or raise a clear error if it's not set."""
    if not ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY is not set. Add it to backend/.env and restart "
            "the server."
        )
    return ANTHROPIC_API_KEY


def require_openai_key() -> str:
    """Return OPENAI_API_KEY, or raise a clear error if it's not set."""
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to backend/.env and restart "
            "the server."
        )
    return OPENAI_API_KEY
