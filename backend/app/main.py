"""
VoicePolish Backend — FastAPI Entry Point

This file defines the FastAPI application and its routes.
Run locally with:
    uvicorn app.main:app --reload

Then visit:
    http://localhost:8000/health   -> returns {"status": "ok"}
    http://localhost:8000/docs     -> interactive API documentation
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import os

from app.database import engine, Base
from app import models  # noqa: F401  -- import needed so Base knows about the models
from app.routers import transcriptions, vocabulary, polish, transcribe


# -----------------------------------------------------------------------------
# Create database tables on startup.
# This scans every class that inherits from Base and runs CREATE TABLE
# for any table that doesn't exist yet. Existing tables are left alone.
# On first run this will create the voicepolish.db file in the backend/ folder.
# -----------------------------------------------------------------------------
Base.metadata.create_all(bind=engine)

# -----------------------------------------------------------------------------
# Create the FastAPI application instance.
# `title` and `version` show up in the auto-generated /docs page.
# -----------------------------------------------------------------------------
app = FastAPI(
    title="VoicePolish API",
    version="0.1.0",
    description="Backend for VoicePolish — speech capture, polish, and vocabulary analysis.",
)

# -----------------------------------------------------------------------------
# CORS middleware.
# Browsers block JavaScript from calling APIs on a different origin (domain/port)
# unless the server explicitly allows it. Production tightens this to specific
# domains via the ALLOWED_ORIGINS env var (comma-separated). For local dev
# (env var unset) we fall back to allowing localhost dev servers.
# -----------------------------------------------------------------------------
_default_dev_origins = [
    "http://localhost:5500",
    "http://127.0.0.1:5500",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
_env_origins = os.getenv("ALLOWED_ORIGINS", "").strip()
allowed_origins = (
    [o.strip() for o in _env_origins.split(",") if o.strip()]
    if _env_origins
    else _default_dev_origins
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# Routes
# -----------------------------------------------------------------------------
@app.get("/health")
def health_check():
    """
    Health check endpoint.
    Used to verify the server is running. Any monitoring tool or load balancer
    will ping an endpoint like this to decide if the service is alive.
    """
    return {"status": "ok", "service": "voicepolish-backend"}


@app.get("/")
def root():
    """Friendly landing message so people don't see a 404 on the root URL."""
    return {
        "message": "VoicePolish API is running.",
        "docs": "/docs",
        "health": "/health",
    }


# -----------------------------------------------------------------------------
# Mount routers
# -----------------------------------------------------------------------------
# Each router is a self-contained group of routes in its own file.
# include_router() registers them all under the main app. The prefix was set
# on the router itself, so nothing to add here.
# -----------------------------------------------------------------------------
app.include_router(transcriptions.router)
app.include_router(vocabulary.router)
app.include_router(polish.router)
app.include_router(transcribe.router)
