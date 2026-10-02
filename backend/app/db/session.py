"""
Database engine, session factory, and FastAPI dependency.

Pool sizing notes:
- pool_size=20    — 20 persistent connections kept warm
- max_overflow=30 — up to 30 extra connections during bursts
- pool_recycle=1800 — recycle connections every 30 min (Postgres default
                     idle timeout is 60 min; recycling earlier avoids
                     "connection closed unexpectedly" errors)
- pool_timeout=10 — wait up to 10s for a free connection; else raise
"""
from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings


# echo=True logs every SQL statement. Useful for learning; turn off in prod.
engine = create_engine(
    settings.database_url,
    echo=settings.debug,
    pool_pre_ping=True,      # verify connections are alive before using them
    pool_size=20,            # persistent connections
    max_overflow=30,         # additional connections for bursts
    pool_recycle=1800,       # recycle every 30 min
    pool_timeout=10,         # wait max 10s for a free connection
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency. Yields a session; closes it when the request ends.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()