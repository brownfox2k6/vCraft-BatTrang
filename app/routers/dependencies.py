"""FastAPI request-scoped dependencies."""

from collections.abc import Iterator

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, sessionmaker

from app.i18n import DEFAULT_LANG, Lang, normalize_lang


def get_db(request: Request) -> Iterator[Session]:
    """Yield a scoped ORM session per HTTP request."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_templates(request: Request) -> Jinja2Templates:
    """Return the application's configured Jinja2Templates instance."""
    templates: Jinja2Templates = request.app.state.templates
    return templates


def get_request_lang(request: Request) -> Lang:
    """Return the normalized active language for the current HTTP request."""
    raw_lang = getattr(request.state, "lang", DEFAULT_LANG)
    return normalize_lang(raw_lang if isinstance(raw_lang, str) else None)
