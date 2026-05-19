"""Smoke tests for VoicePolish backend.

These are minimal CI tests — they verify the FastAPI app boots,
core routes respond, and the DB layer connects. They do NOT cover
endpoints that depend on external APIs (Whisper, Anthropic).
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200():
    """The /health endpoint should respond 200 with a status='ok' field."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json().get("status") == "ok"


def test_get_transcriptions_returns_list():
    """GET /api/transcriptions should return a list (empty in CI's fresh DB)."""
    response = client.get("/api/transcriptions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
