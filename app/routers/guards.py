"""Reusable RBAC (Buyer, Artisan, Admin) and resource-ownership guards for API and SSR routes."""

import uuid
from collections.abc import Callable
from typing import Annotated
from urllib.parse import quote

from fastapi import Depends, Request

from app.models.auth import UserRole
from app.services.auth_service import AuthenticatedUser


class ApiGuardError(Exception):
    """Raised by API auth/RBAC/ownership guards to emit a standardized JSON ApiResponse error."""

    def __init__(self, *, status_code: int, code: str, message_key: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message_key = message_key


class WebRedirectError(Exception):
    """Raised by SSR auth guards to redirect unauthenticated visitors to /dang-nhap?next=..."""

    def __init__(self, redirect_url: str) -> None:
        super().__init__(redirect_url)
        self.redirect_url = redirect_url


class WebForbiddenError(Exception):
    """Raised by SSR RBAC/ownership guards to render a localized 403 Forbidden page."""

    def __init__(self, message_key: str = "auth.errors.forbidden") -> None:
        super().__init__(message_key)
        self.message_key = message_key


def _current_user_from_request(request: Request) -> AuthenticatedUser | None:
    user = getattr(request.state, "current_user", None)
    return user if isinstance(user, AuthenticatedUser) else None


def require_authenticated_api(request: Request) -> AuthenticatedUser:
    """Require an active session on /api/* endpoints or raise 401 UNAUTHENTICATED."""
    user = _current_user_from_request(request)
    if user is None:
        raise ApiGuardError(
            status_code=401,
            code="UNAUTHENTICATED",
            message_key="auth.errors.unauthenticated",
        )
    return user


def require_roles_api(
    *allowed_roles: UserRole,
) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Return a FastAPI dependency restricting an /api/* endpoint to the given roles."""
    allowed = frozenset(allowed_roles)

    def _dependency(
        user: Annotated[AuthenticatedUser, Depends(require_authenticated_api)],
    ) -> AuthenticatedUser:
        if user.role not in allowed:
            raise ApiGuardError(
                status_code=403,
                code="FORBIDDEN",
                message_key="auth.errors.forbidden",
            )
        return user

    return _dependency


def require_authenticated_web(request: Request) -> AuthenticatedUser:
    """Require an active session on SSR pages or redirect to /dang-nhap?next=<current_url>."""
    user = _current_user_from_request(request)
    if user is None:
        target = request.url.path or "/"
        if request.url.query:
            target = f"{target}?{request.url.query}"
        raise WebRedirectError(f"/dang-nhap?next={quote(target, safe='/')}")
    return user


def require_roles_web(
    *allowed_roles: UserRole,
) -> Callable[[AuthenticatedUser], AuthenticatedUser]:
    """Return a FastAPI dependency restricting an SSR route to the given roles."""
    allowed = frozenset(allowed_roles)

    def _dependency(
        user: Annotated[AuthenticatedUser, Depends(require_authenticated_web)],
    ) -> AuthenticatedUser:
        if user.role not in allowed:
            raise WebForbiddenError("auth.errors.forbidden")
        return user

    return _dependency


def require_owner_or_admin(
    owner_user_id: uuid.UUID,
    current_user: AuthenticatedUser,
    *,
    api: bool = True,
) -> None:
    """Ensure the caller owns the resource or holds the Admin role, else raise 403."""
    if current_user.id == owner_user_id or current_user.role == UserRole.ADMIN:
        return
    if api:
        raise ApiGuardError(
            status_code=403,
            code="FORBIDDEN",
            message_key="auth.errors.forbidden",
        )
    raise WebForbiddenError("auth.errors.forbidden")
