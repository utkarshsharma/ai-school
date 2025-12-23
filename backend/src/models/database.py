"""Database configuration and session management."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from src.config import get_settings

Base = declarative_base()

_engine = None
_SessionLocal = None


def get_engine():
    """Get or create the database engine."""
    global _engine
    if _engine is None:
        settings = get_settings()
        # Ensure storage directory exists
        settings.storage_base_path.mkdir(parents=True, exist_ok=True)

        # SQLite-specific settings
        connect_args = {}
        engine_kwargs = {}

        if "sqlite" in settings.database_url:
            connect_args["check_same_thread"] = False
        else:
            # PostgreSQL connection pooling
            engine_kwargs["pool_size"] = 10
            engine_kwargs["max_overflow"] = 20
            engine_kwargs["pool_pre_ping"] = True

        _engine = create_engine(
            settings.database_url,
            connect_args=connect_args,
            **engine_kwargs,
        )
    return _engine


def get_session_local():
    """Get or create the session factory."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionLocal


def init_db() -> None:
    """Initialize database tables."""
    Base.metadata.create_all(bind=get_engine())


def get_db() -> Generator[Session, None, None]:
    """Dependency for getting database sessions."""
    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
