"""Database-independent SQLAlchemy 2.x engine, session factory, and ORM base."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative ORM base class inherited by all domain models."""


def create_db_engine(database_url: str) -> Engine:
    """Create a SQLAlchemy engine with connection liveness checks enabled."""
    return create_engine(database_url, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Bind a typed session factory to the given SQLAlchemy engine."""
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
