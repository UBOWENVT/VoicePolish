# ─────────────────────────────────────────────────────────────────────────────
# VoicePolish Backend Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
# Builds a self-contained image of the FastAPI app + all its Python deps +
# the NLTK data packages we need at runtime.
#
# Build:   docker build -t voicepolish-backend .
# Run:     docker run -p 8000:8000 --env-file .env voicepolish-backend
# ─────────────────────────────────────────────────────────────────────────────

# Start from the official Python 3.12 slim image. "slim" is a stripped-down
# Debian variant — much smaller than the full image, but still has enough
# system libraries for most pure-Python workloads.
FROM python:3.12-slim

# Don't write .pyc files (we won't be re-importing within the container's
# lifetime, so caching them is wasted disk).
ENV PYTHONDONTWRITEBYTECODE=1
# Force stdout/stderr to be unbuffered so logs appear in real time.
# Without this, container logs can lag by several seconds.
ENV PYTHONUNBUFFERED=1

# Working directory inside the container. All subsequent COPY / RUN paths
# are relative to here unless absolute.
WORKDIR /app

# ─── Install Python dependencies ─────────────────────────────────────────────
# Copy requirements.txt FIRST (before app code) so Docker can cache the
# pip-install layer. If only your app code changes, Docker reuses the cached
# pip layer and skips reinstalling everything — huge speedup on iteration.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ─── Download NLTK data packages ─────────────────────────────────────────────
# Without this the M5 vocab analyzer fails on first request with "Resource
# punkt_tab not found." Doing it at build time means it's baked into the
# image — no first-request delay, no runtime network dependency.
RUN python -c "import nltk; nltk.download('punkt_tab', quiet=True); nltk.download('stopwords', quiet=True)"

# ─── Copy application code ───────────────────────────────────────────────────
# Done last because it changes most often. Docker only re-runs layers below
# this on code changes; the deps + NLTK layers stay cached.
COPY app/ ./app/

# Expose port 8000 (informational; doesn't actually publish — `docker run -p`
# does that). Tells anyone reading the Dockerfile what port the app uses.
EXPOSE 8000

# ─── Runtime command ─────────────────────────────────────────────────────────
# --host 0.0.0.0 is CRITICAL: by default uvicorn binds to 127.0.0.1 (localhost
# inside the container) which means external traffic can't reach it. 0.0.0.0
# means "listen on all interfaces", which lets `docker run -p` forward traffic
# from your host machine to the container.
#
# No --reload here: that's a development convenience that watches files for
# changes. In production we want a stable single process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
