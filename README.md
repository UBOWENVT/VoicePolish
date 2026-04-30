# VoicePolish

> Speech-to-text with AI refinement and adaptive vocabulary learning.

Capture your voice, convert it to polished text via OpenAI Whisper + Claude.
Over time, VoicePolish learns the domain-specific terms you use most and
suggests adding them to your personal dictionary using a three-stage pipeline
(NLTK → TF-IDF → LLM).

**🔗 Live demo:** https://voice-polish-nine.vercel.app/
**🔗 Backend API docs:** https://voicepolish-production-4b7c.up.railway.app/docs

---

## Architecture

```
┌─────────────────────┐         ┌──────────────────────┐
│  Frontend (HTML/JS) │  HTTPS  │  Backend (FastAPI)   │
│  MediaRecorder API  │ ──────→ │  Docker container    │
└─────────────────────┘         └──────────────────────┘
                                          │
                          ┌───────────────┼───────────────┐
                          ↓               ↓               ↓
                    ┌──────────┐  ┌──────────────┐ ┌────────────┐
                    │ OpenAI   │  │ Anthropic    │ │  SQLite    │
                    │ Whisper  │  │ Claude       │ │  database  │
                    └──────────┘  └──────────────┘ └────────────┘
```

The frontend handles audio capture and UI. The backend owns all API keys,
database access, LLM calls, and vocabulary analytics — nothing sensitive
lives in the browser.

## Key Features

- **Whisper-based transcription** — multipart audio upload to OpenAI Whisper API
- **5 polish modes** powered by Claude — clean, formal, casual, bullets, summary
- **Adaptive vocabulary mining** — three-stage pipeline:
  1. NLTK tokenization + stopword filtering populates `word_stats` on every save
  2. scikit-learn TF-IDF surfaces statistically distinctive terms
  3. Claude semantically filters TF-IDF candidates with structured JSON output,
     suggesting canonical replacements with reasoning
- **Custom dictionary** — applied pre-polish so the LLM sees your intended terms
- **Graceful degradation** — LLM failure → TF-IDF fallback → count fallback
- **Production-ready** — Dockerized backend, deployed on Railway

## Local Development

### Prerequisites
- Python 3.12+
- Modern browser (Chrome/Edge/Firefox)
- OpenAI API key, Anthropic API key

### Backend setup

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -c "import nltk; nltk.download('punkt_tab'); nltk.download('stopwords')"

# Create .env from template
copy .env.example .env
# Edit .env — add OPENAI_API_KEY and ANTHROPIC_API_KEY

uvicorn app.main:app --reload
```

API at **http://localhost:8000** · Docs at **http://localhost:8000/docs**

### Frontend

Open `frontend/VoicePolish.html` via a local HTTP server (file:// won't work
for mic permissions in some browsers):

```powershell
cd frontend
python -m http.server 5500
```

Then visit http://localhost:5500/VoicePolish.html

### Docker (production-equivalent)

```powershell
cd backend
docker build -t voicepolish-backend .
docker run -p 8000:8000 --env-file .env voicepolish-backend
```

## Deployment

Backend deployed on **Railway** via auto-build from Dockerfile. Required env vars:
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

Set `Root Directory = backend` in the Railway service settings so it finds the
Dockerfile.

## Roadmap

- [x] **M1** — FastAPI skeleton with `/health`
- [x] **M2** — Database schema (transcriptions, vocabulary) + SQLAlchemy ORM
- [x] **M3** — Frontend wired to backend; transcripts saved to DB
- [x] **M4** — Polish logic moved to backend (API keys off the client)
- [x] **M5** — Vocabulary analysis v1: NLTK + frequency counting
- [x] **M6** — Vocabulary analysis v2: TF-IDF via scikit-learn
- [x] **M7** — Vocabulary analysis v3: LLM-assisted curation with grounding
- [x] **M8** — Whisper integration (multipart audio upload, full pipeline)
- [x] **M9.1** — Backend dockerized
- [x] **M9.2** — Backend deployed to Railway (with persistent volume for SQLite)
- [x] **M9.3** — Frontend deployed to Vercel (env-aware API_BASE)
- [x] **M9.4** — Production CORS hardening (env-driven origin whitelist)

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend framework | FastAPI + Uvicorn |
| ORM / DB | SQLAlchemy + SQLite |
| Transcription | OpenAI Whisper API (multipart upload) |
| Polish / curation | Anthropic Claude (Haiku 4.5) |
| NLP | NLTK (tokenization, stopwords) |
| ML | scikit-learn (TF-IDF) |
| Frontend | Vanilla HTML/CSS/JS, MediaRecorder API |
| Deployment | Docker, Railway |

## Engineering Highlights

- **Two-stage candidate generation** for vocabulary suggestions
  (cheap algorithm → expensive AI), a standard production ML pattern
- **Grounding constraint** on LLM outputs — only accepts terms that exist in
  the TF-IDF candidate pool, preventing hallucinated suggestions
- **Layered architecture** — routes → schemas → services → models, allowing
  service-layer reuse and easy swapping of underlying tech
- **Defensive JSON parsing** for LLM responses (handles markdown fence
  wrapping despite explicit prompt instructions)
- **Graceful degradation chain** across LLM → TF-IDF → count fallback levels
- **Side-effect hook pattern** for word frequency tracking — analytics
  failures never block the primary save flow
- **Immutable Docker images** for reproducible production deployments

## License

MIT
