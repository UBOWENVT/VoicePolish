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
# unless the server explicitly allows it. Our frontend runs from a file://
# URL or localhost, and our backend runs on localhost:8000 — different origin.
# So we tell FastAPI: "Allow any origin to call us during development."
# In production we would lock this down to specific domains.
# -----------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],           # dev-only; tighten in production
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
