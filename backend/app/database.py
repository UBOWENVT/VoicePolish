"""
VoicePolish Backend — Database Setup

This module wires up SQLAlchemy. It does NOT define tables — that's in models.py.
Here we only set up the infrastructure: connection, session factory, and base class.

Three things are exported:
    engine         — the connection pool to the database
    SessionLocal   — a factory that creates a new session per request
    Base           — the class every model will inherit from
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base


# -----------------------------------------------------------------------------
# 1. Database URL
# -----------------------------------------------------------------------------
# SQLAlchemy connects to any database through a URL string. The format is:
#     dialect+driver://user:password@host:port/dbname
#
# For SQLite (a file-based database), we skip the user/host stuff and just
# point at a file:
#     sqlite:///./voicepolish.db    <- three slashes = relative path
#     sqlite:////absolute/path.db   <- four slashes = absolute path
#
# The ".db" file will be created automatically on first run. The "./" means
# "relative to the current working directory when uvicorn starts", which for
# us is the backend/ folder. So the database file lands at backend/voicepolish.db.
# -----------------------------------------------------------------------------
DATABASE_URL = "sqlite:///./voicepolish.db"


# -----------------------------------------------------------------------------
# 2. Engine — the connection pool
# -----------------------------------------------------------------------------
# The engine is SQLAlchemy's low-level interface to the database. Think of it
# as a pool of open connections that get reused across requests, so we don't
# pay the cost of opening a connection every time.
#
# The `connect_args={"check_same_thread": False}` is SQLite-specific:
# By default SQLite insists that a connection be used only by the thread that
# created it. FastAPI serves requests from multiple threads, so we need to
# override this. (PostgreSQL users will NOT need this argument.)
# -----------------------------------------------------------------------------
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # SQLite-specific
)


# -----------------------------------------------------------------------------
# 3. SessionLocal — the session factory
# -----------------------------------------------------------------------------
# A Session is a short-lived object representing "one conversation with the DB":
# you open it, do some queries/inserts, commit, close. One session per HTTP
# request is the standard pattern.
#
# sessionmaker() returns a *factory* — a callable that produces new Session
# objects. It's a factory (not a session itself) because we want a fresh
# session for every request. The naming convention is uppercase `SessionLocal`
# to signal "this is a class/factory, call it to get an instance."
#
# autocommit=False + autoflush=False: the sensible defaults. You control
# exactly when changes get written (via session.commit()).
# -----------------------------------------------------------------------------
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# -----------------------------------------------------------------------------
# 4. Base — the declarative base class
# -----------------------------------------------------------------------------
# Every model class we write (Transcription, Vocabulary, ...) will inherit
# from Base. This is how SQLAlchemy's "declarative" style works:
#     class Transcription(Base):
#         __tablename__ = "transcriptions"
#         id = Column(Integer, primary_key=True)
#         ...
#
# Behind the scenes, Base tracks all subclasses and knows how to translate
# them into SQL CREATE TABLE statements (and how to map rows <-> objects).
# -----------------------------------------------------------------------------
Base = declarative_base()


# -----------------------------------------------------------------------------
# 5. get_db() — FastAPI dependency for injecting a session per request
# -----------------------------------------------------------------------------
# Use with: `db: Session = Depends(get_db)` in a route function.
# Each request gets a fresh Session. When the request finishes (success OR
# error), the `finally` block runs and closes the session — no leaks.
#
# Why `yield` instead of `return`? FastAPI's Depends system needs to run code
# AFTER the route function is done (the cleanup). A generator (yield) lets
# FastAPI pause at the yield, run the route, then come back to execute the
# finally block.
# -----------------------------------------------------------------------------
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
