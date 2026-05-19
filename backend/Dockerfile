# ─────────────────────────────────────────────────────────────────────────────
# VoicePolish Backend — Multi-Stage Dockerfile
# ─────────────────────────────────────────────────────────────────────────────
# Two-stage build to keep the runtime image lean:
#
#   Stage 1 (builder): Installs all pip packages and downloads NLTK data.
#                      Carries pip itself, setuptools, build leftovers,
#                      and the full pip toolchain. NEVER deployed.
#
#   Stage 2 (runtime): Starts from a clean python:3.12-slim and copies ONLY
#                      the final site-packages and nltk_data over. This is
#                      the image that gets tagged, pushed, and run.
#
# Build:   docker build -t voicepolish-backend .
# Run:     docker run -p 8000:8000 --env-file .env voicepolish-backend
# ─────────────────────────────────────────────────────────────────────────────


# ═════════════════════════════════════════════════════════════════════════════
# Stage 1: builder — install dependencies, download NLTK data
# ═════════════════════════════════════════════════════════════════════════════
FROM python:3.12-slim AS builder

# Don't write .pyc files during package install — saves space in the layer
# that the runtime stage will pick from. (Runtime stage sets this too, so
# any .pyc that DO get generated at runtime are skipped there as well.)
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install Python dependencies. requirements.txt is copied alone (not the whole
# app/) so this layer is cacheable across code-only changes.
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Download NLTK data packages into the builder's HOME (defaults to /root/nltk_data).
# We'll copy this directory verbatim into the runtime stage so first-request
# downloads don't hit the network at runtime.
RUN python -c "import nltk; \
    nltk.download('punkt_tab', quiet=True); \
    nltk.download('stopwords', quiet=True)"


# ═════════════════════════════════════════════════════════════════════════════
# Stage 2: runtime — clean image, only the final artifacts
# ═════════════════════════════════════════════════════════════════════════════
# Starts FROM scratch on python:3.12-slim again. Inherits NOTHING from builder
# except what we explicitly COPY --from=builder below. pip, setuptools, build
# caches, /tmp leftovers — all stay in builder and are discarded after build.
#
# Naming this stage `runtime` (via AS runtime) is optional — the last FROM is
# always the final image regardless — but it makes build logs read
# `[runtime N/N]` instead of `[stage-1 N/N]`, and lets you
# `docker build --target runtime` or `--target builder` to stop at a specific
# stage during debugging.
FROM python:3.12-slim AS runtime

# Re-declare ENV — these do NOT carry over from builder. Each FROM resets
# the environment.
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Cherry-pick from builder:
#   1. The installed Python packages (site-packages) — used by `import` statements
#   2. The CLI entry-point scripts pip generated (e.g. /usr/local/bin/uvicorn)
#      — used when CMD invokes those tools by name. site-packages alone is
#      NOT enough: `pip install uvicorn` installs both the importable package
#      AND a /usr/local/bin/uvicorn launcher script. Without the launcher,
#      `CMD ["uvicorn", ...]` fails with "executable file not found in $PATH".
#   3. The NLTK data directory
#
# Everything else in builder (pip cache, build artifacts, etc.) is left
# behind and never enters this image.
COPY --from=builder /usr/local/lib/python3.12/site-packages \
                    /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /root/nltk_data /root/nltk_data

# Now copy application code. Done last because it changes most often —
# Docker only re-runs THIS layer on code-only edits; the heavy site-packages
# COPY above stays cached.
COPY app/ ./app/

# Informational — declares the port the app uses. Does not publish (that's
# `docker run -p` or compose's `ports:` block).
EXPOSE 8000

# --host 0.0.0.0 is CRITICAL inside a container: by default uvicorn binds to
# 127.0.0.1, which from outside the container is unreachable. 0.0.0.0 means
# "listen on all interfaces", so `docker run -p 8000:8000` (or compose's
# internal network) can forward traffic in.
#
# No --reload: that's a dev-time file watcher. In production we want a stable
# single process.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
