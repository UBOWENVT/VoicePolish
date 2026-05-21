"""
Logging configuration — JSON-structured logs for centralized observability.

Why JSON: makes every log line machine-parseable. Aggregators like Loki, Splunk,
or Datadog can index fields (level, event, status, duration_ms, etc.) without
fragile regex parsing.

Why a separate module: keeps main.py focused on routing. Anyone who needs to
adjust formatter fields or log level only touches this one file.

Usage in main.py:
    from app.core.logging_config import configure_logging
    configure_logging()

Then any module can:
    import logging
    logger = logging.getLogger(__name__)
    logger.info("llm.call", extra={"provider": "anthropic", "status": "success"})
"""

import logging
import os
import sys

from pythonjsonlogger.json import JsonFormatter


def configure_logging() -> None:
    """
    Attach a JSON formatter to the root logger and a StreamHandler to stdout.

    Idempotent: safe to call multiple times — clears any existing handlers
    first so reload-on-edit (uvicorn --reload) doesn't stack handlers and
    duplicate every log line.

    Log level honors the LOG_LEVEL env var (default INFO). Set LOG_LEVEL=DEBUG
    in dev when you need to see noisier output.
    """
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # Build the JSON formatter. The `fmt` string lists which logging.LogRecord
    # attributes go into every line as top-level JSON keys; anything passed via
    # `extra={...}` is merged in alongside.
    # %(asctime)s -> timestamp;  %(name)s -> logger name (usually module path)
    formatter = JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        rename_fields={
            "asctime": "timestamp",
            "levelname": "level",
            "name": "logger",
        },
        # ISO-8601 in UTC; Loki/Grafana parse this directly.
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # StreamHandler -> stdout. Docker captures stdout into container logs,
    # where Promtail picks them up. Don't use stderr unless you want
    # everything tagged as warnings by some viewers.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)

    # Clear any previously-attached handlers so reloads don't stack them.
    for old in list(root.handlers):
        root.removeHandler(old)
    root.addHandler(handler)

    # Tame uvicorn's three internal loggers so they also emit JSON instead of
    # their own pretty-printed format. Letting them propagate to root achieves
    # this; setting them to WARNING for "uvicorn.access" silences per-request
    # noise (we get HTTP info from our own router logs when needed).
    for name in ("uvicorn", "uvicorn.error"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    access = logging.getLogger("uvicorn.access")
    access.handlers = []
    access.propagate = True
    access.setLevel(logging.WARNING)
