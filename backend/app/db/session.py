"""
Database engine, session factory, and FastAPI dependency.

- `engine`: connection pool. One per process.
- `SessionLocal`: factory that produces new sessions.
- `get_db`: FastAPI dependency that yields a session per request.
"""
from collections.abc import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.config import settings


# echo=True logs every SQL statement. Useful for learning; turn off in prod.
engine = create_engine(
    settings.database_url,
    echo=settings.debug,      # logs SQL when debug=True
    pool_pre_ping=True,       # verify connections are alive before using them
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,          # we flush explicitly
    autocommit=False,         # SQLAlchemy 2.0 style
    expire_on_commit=False,   # objects stay usable after commit
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """
    FastAPI dependency. Yields a session; closes it when the request ends.

    Usage in a route:
        def my_route(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()