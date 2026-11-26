"""Authentication REST API router (/api/auth/*)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import Settings
from app.core.responses import ApiError, ApiResponse
from app.i18n.catalog import translate
from app.routers.auth_cookies import (
    clear_csrf_cookie,
    clear_session_cookie,
    get_client_ip,
    is_secure_request,
    set_csrf_cookie,
    set_session_cookie,
)
from app.routers.dependencies import (
    get_auth_service,
    get_request_lang,
    get_settings,
    rate_limit_headers,
    translate_auth_error,
)
from app.services.auth_service import (
    AuthError,
    AuthResult,
    AuthService,
    LogoutResult,
    MeResult,
    SessionIssueResult,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    """JSON body for Buyer self-registration."""

    full_name: str = ""
    email: str = ""
    password: str = ""
    next: str | None = None


class LoginRequest(BaseModel):
    """JSON body for email/password sign-in across all roles."""

    email: str = ""
    password: str = ""
    next: str | None = None


def _error_json_response(
    *,
    status_code: int,
    code: str,
    message: str,
    meta: dict[str, object] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ApiResponse[None](
        meta=meta or {},
        error=ApiError(code=code, message=message),
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers=headers,
    )


def _auth_error_response(exc: AuthError, lang: str) -> JSONResponse:
    message, field_errors = translate_auth_error(exc, lang)
    meta: dict[str, object] = {"field_errors": field_errors} if field_errors else {}
    return _error_json_response(
        status_code=exc.status_code,
        code=exc.code,
        message=message,
        meta=meta,
        headers=rate_limit_headers(exc),
    )


def _session_issued_response(
    issued: SessionIssueResult,
    *,
    status_code: int,
    request: Request,
    settings: Settings,
) -> JSONResponse:
    body = ApiResponse[AuthResult](data=issued.result)
    response = JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
    )
    secure = is_secure_request(request, settings)
    set_session_cookie(
        response,
        issued.raw_token,
        settings,
        secure=secure,
    )
    set_csrf_cookie(
        response,
        issued.csrf_token,
        settings,
        secure=secure,
    )
    return response


@router.post(
    "/register",
    status_code=status.HTTP_201_CREATED,
    response_model=ApiResponse[AuthResult],
)
def register_buyer(
    payload: RegisterRequest,
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    """Register an active Buyer account, create a session, and set the session cookie."""
    lang = get_request_lang(request)
    try:
        issued = service.register_buyer(
            full_name=payload.full_name,
            email=payload.email,
            password=payload.password,
            next_url=payload.next,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except AuthError as exc:
        return _auth_error_response(exc, lang)
    return _session_issued_response(
        issued,
        status_code=status.HTTP_201_CREATED,
        request=request,
        settings=settings,
    )


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[AuthResult],
)
def login_user(
    payload: LoginRequest,
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    """Authenticate an existing account and set the HttpOnly session cookie."""
    lang = get_request_lang(request)
    try:
        issued = service.login(
            email=payload.email,
            password=payload.password,
            next_url=payload.next,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except AuthError as exc:
        return _auth_error_response(exc, lang)
    return _session_issued_response(
        issued,
        status_code=status.HTTP_200_OK,
        request=request,
        settings=settings,
    )


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[LogoutResult],
)
def logout_user(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JSONResponse:
    """Revoke the active server-side session and clear the session cookie."""
    raw_token = request.cookies.get(settings.session_cookie_name)
    result = service.logout(
        raw_token,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    body = ApiResponse[LogoutResult](data=result)
    response = JSONResponse(
        status_code=status.HTTP_200_OK,
        content=body.model_dump(mode="json"),
    )
    secure = is_secure_request(request, settings)
    clear_session_cookie(response, settings, secure=secure)
    clear_csrf_cookie(response, settings, secure=secure)
    return response


@router.get(
    "/me",
    response_model=ApiResponse[MeResult],
)
def read_current_user(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ApiResponse[MeResult] | JSONResponse:
    """Return the authenticated user resolved from the session cookie."""
    raw_token = request.cookies.get(settings.session_cookie_name)
    user = service.resolve_session(raw_token)
    if user is None:
        lang = get_request_lang(request)
        return _error_json_response(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="UNAUTHENTICATED",
            message=translate("auth.errors.unauthenticated", lang),
        )
    return ApiResponse(data=MeResult(user=user))
