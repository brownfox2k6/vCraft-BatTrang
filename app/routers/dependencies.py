"""FastAPI request-scoped dependencies."""

from collections.abc import Callable, Iterator
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.security import Argon2PasswordHasher
from app.i18n import DEFAULT_LANG, Lang, normalize_lang
from app.i18n.catalog import translate
from app.repositories.audit_repository import AuditRepository
from app.repositories.auth_repository import AuthRepository
from app.repositories.media_repository import MediaRepository
from app.repositories.workshop_application_repository import WorkshopApplicationRepository
from app.services.audit_service import AuditService
from app.services.auth_service import AuthError, AuthService, RateLimitExceededAuthError
from app.services.media_service import MediaService
from app.services.workshop_application_service import WorkshopApplicationService


def build_audit_service(
    db: Session,
    *,
    clock: Callable[[], datetime],
) -> AuditService:
    """Construct an AuditService bound to the supplied DB session and clock."""
    return AuditService(repository=AuditRepository(db), clock=clock)


def build_auth_service(
    db: Session,
    *,
    password_hasher: Argon2PasswordHasher,
    settings: Settings,
    clock: Callable[[], datetime],
) -> AuthService:
    """Construct an AuthService bound to the supplied DB session, audit service, and clock."""
    return AuthService(
        repository=AuthRepository(db),
        password_hasher=password_hasher,
        settings=settings,
        clock=clock,
        audit_service=build_audit_service(db, clock=clock),
    )


def translate_auth_error(exc: AuthError, lang: str) -> tuple[str, dict[str, str]]:
    """Translate an AuthError message and its per-field validation errors."""
    message = translate(exc.message_key, lang, **exc.message_params)
    field_errors = {field: translate(key, lang) for field, key in exc.field_errors.items()}
    return message, field_errors


def rate_limit_headers(exc: AuthError) -> dict[str, str] | None:
    """Return Retry-After headers when an AuthError represents rate limiting."""
    if isinstance(exc, RateLimitExceededAuthError):
        return {"Retry-After": str(exc.retry_after_seconds)}
    return None


def get_settings(request: Request) -> Settings:
    """Return the application's typed runtime Settings."""
    settings: Settings = request.app.state.settings
    return settings


def get_db(request: Request) -> Iterator[Session]:
    """Yield a scoped ORM session per HTTP request."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


def get_audit_service(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> AuditService:
    """Build AuditService wired with the request DB session and application clock."""
    clock: Callable[[], datetime] = request.app.state.clock
    return build_audit_service(db, clock=clock)


def get_media_service(
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> MediaService:
    """Build MediaService wired with the request DB session and runtime settings."""
    return MediaService(repository=MediaRepository(db), settings=settings)


def get_workshop_application_service(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> WorkshopApplicationService:
    """Build WorkshopApplicationService wired with request DB session, hasher, and audit log."""
    password_hasher: Argon2PasswordHasher = request.app.state.password_hasher
    clock: Callable[[], datetime] = request.app.state.clock
    return WorkshopApplicationService(
        application_repository=WorkshopApplicationRepository(db),
        auth_repository=AuthRepository(db),
        media_repository=MediaRepository(db),
        password_hasher=password_hasher,
        audit_service=build_audit_service(db, clock=clock),
    )


def get_auth_service(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> AuthService:
    """Build AuthService wired with request DB session, hasher, audit service, and clock."""
    password_hasher: Argon2PasswordHasher = request.app.state.password_hasher
    clock: Callable[[], datetime] = request.app.state.clock
    return build_auth_service(
        db,
        password_hasher=password_hasher,
        settings=settings,
        clock=clock,
    )


def get_templates(request: Request) -> Jinja2Templates:
    """Return the application's configured Jinja2Templates instance."""
    templates: Jinja2Templates = request.app.state.templates
    return templates


def get_request_lang(request: Request) -> Lang:
    """Return the normalized active language for the current HTTP request."""
    raw_lang = getattr(request.state, "lang", DEFAULT_LANG)
    return normalize_lang(raw_lang if isinstance(raw_lang, str) else None)
