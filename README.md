# VoicePolish

> Speech-to-text with AI refinement and adaptive vocabulary learning.

Capture your voice, convert it to text, and let an LLM clean it up in the style
you want (formal, casual, bullets, summary). Over time, VoicePolish learns the
domain-specific terms you use most and suggests adding them to your personal
dictionary — so transcription accuracy keeps improving with use.

---

## Architecture

```
frontend/  ← HTML + JS (browser)
backend/   ← FastAPI (Python) — routes, LLM calls, vocabulary analysis
           ← SQLite (dev) / PostgreSQL (prod) — transcripts, dictionary, stats
```

The frontend handles audio capture and UI. The backend owns all API keys,
database access, and vocabulary analytics — nothing sensitive lives in the browser.

## Local Development

### Prerequisites
- Python 3.11+
- A modern browser (Chrome/Edge for Web Speech API support in early milestones)

### Backend setup

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The API will be running at **http://localhost:8000**.
Interactive docs: **http://localhost:8000/docs**

### Frontend

For now the frontend is a single HTML file — open `frontend/VoicePolish.html` in your browser.

## Roadmap

- [x] **M1** — FastAPI skeleton with `/health`
- [ ] **M2** — Database schema (transcriptions, vocabulary) + SQLAlchemy ORM
- [ ] **M3** — Wire frontend to backend: save transcripts to DB
- [ ] **M4** — Move polish logic to backend (API keys off the client)
- [ ] **M5** — Vocabulary analysis v1: frequency counting
- [ ] **M6** — Vocabulary analysis v2: TF-IDF against user's corpus
- [ ] **M7** — Vocabulary analysis v3: LLM-assisted term extraction
- [ ] **M8** — Swap Web Speech API for OpenAI Whisper
- [ ] **M9** — Deploy (Docker + Railway/Render)

## Tech Stack

**Backend:** Python 3.11, FastAPI, Uvicorn, SQLAlchemy, SQLite → PostgreSQL
**Frontend:** Vanilla HTML/CSS/JS (may migrate to React in later milestones)
**AI:** OpenAI Whisper (transcription), OpenAI / Anthropic / Gemini (polish), custom TF-IDF + LLM pipeline (vocabulary analysis)
**Deployment:** Docker, Railway or Render

## License

MIT (to be added)
