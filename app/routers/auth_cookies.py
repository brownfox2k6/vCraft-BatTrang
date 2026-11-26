"""Shared HTTP cookie and client-metadata helpers for API and SSR auth routers."""

from fastapi import Request, Response

from app.core.config import Settings


def is_secure_request(request: Request, settings: Settings) -> bool:
    """Return True when cookies should carry the Secure attribute."""
    return settings.session_cookie_secure or request.url.scheme.lower() == "https"


def set_session_cookie(
    response: Response,
    raw_token: str,
    settings: Settings,
    *,
    secure: bool,
) -> None:
    """Attach the HttpOnly SameSite=Lax server-side session cookie to a response."""
    response.set_cookie(
        key=settings.session_cookie_name,
        value=raw_token,
        max_age=settings.session_ttl_seconds,
        path="/",
        httponly=True,
        samesite="lax",
        secure=secure,
    )


def clear_session_cookie(
    response: Response,
    settings: Settings,
    *,
    secure: bool,
) -> None:
    """Clear the session cookie in the browser."""
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/",
        httponly=True,
        samesite="lax",
        secure=secure,
    )


def set_csrf_cookie(
    response: Response,
    token: str,
    settings: Settings,
    *,
    secure: bool,
) -> None:
    """Attach the non-HttpOnly SameSite=Lax CSRF cookie synchronized with the active token."""
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=token,
        max_age=settings.session_ttl_seconds,
        path="/",
        httponly=False,
        samesite="lax",
        secure=secure,
    )


def clear_csrf_cookie(
    response: Response,
    settings: Settings,
    *,
    secure: bool,
) -> None:
    """Clear the CSRF cookie in the browser."""
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        httponly=False,
        samesite="lax",
        secure=secure,
    )


def get_client_ip(request: Request) -> str:
    """Resolve the direct caller IP address for rate limiting, session, and audit metadata."""
    if request.client is not None and request.client.host:
        return request.client.host[:45]
    return "unknown"
