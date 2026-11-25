"""FastAPI request-scoped dependencies."""

from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session, sessionmaker


def get_db(request: Request) -> Iterator[Session]:
    """Yield a scoped ORM session per HTTP request."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session
