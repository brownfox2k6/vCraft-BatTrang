"""FastAPI request-scoped dependencies."""

from collections.abc import Iterator

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, sessionmaker


def get_db(request: Request) -> Iterator[Session]:
    """Yield a scoped ORM session per HTTP request."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_templates(request: Request) -> Jinja2Templates:
    """Return the application's configured Jinja2Templates instance."""
    templates: Jinja2Templates = request.app.state.templates
    return templates
