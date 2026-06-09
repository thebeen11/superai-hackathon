"""SQLAlchemy engine/session, configured from `settings.database_url` (Req 15)."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from ..config import settings

_engine = None
_SessionLocal: sessionmaker | None = None


def _require_url() -> str:
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return settings.database_url


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(_require_url(), pool_pre_ping=True, future=True)
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, class_=Session)
    return _engine


def get_session() -> Session:
    """Open a new ORM session (caller manages the lifecycle)."""
    if _SessionLocal is None:
        get_engine()
    assert _SessionLocal is not None
    return _SessionLocal()
