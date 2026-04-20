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
