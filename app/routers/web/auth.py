"""SSR authentication pages and form handlers (/dang-nhap, /dang-ky, /dang-xuat)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.core.config import Settings
from app.core.redirects import resolve_safe_next
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
    get_templates,
    rate_limit_headers,
    translate_auth_error,
)
from app.services.auth_service import (
    ROLE_DEFAULT_REDIRECTS,
    AuthenticatedUser,
    AuthError,
    AuthService,
)

router = APIRouter(tags=["web-auth"])


def _get_current_user(request: Request) -> AuthenticatedUser | None:
    user = getattr(request.state, "current_user", None)
    return user if isinstance(user, AuthenticatedUser) else None


def _render_login(
    *,
    request: Request,
    templates: Jinja2Templates,
    lang: str,
    email: str = "",
    next_url: str | None = None,
    form_error: str | None = None,
    field_errors: dict[str, str] | None = None,
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="auth/login.html",
        context={
            "page_title": translate("auth.login.page_title", lang),
            "next_url": resolve_safe_next(next_url, default="") if next_url else "",
            "form_values": {"email": email.strip()},
            "form_error": form_error,
            "field_errors": field_errors or {},
        },
        status_code=status_code,
        headers=headers,
    )


def _render_register(
    *,
    request: Request,
    templates: Jinja2Templates,
    lang: str,
    full_name: str = "",
    email: str = "",
    next_url: str | None = None,
    form_error: str | None = None,
    field_errors: dict[str, str] | None = None,
    status_code: int = 200,
) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="auth/register.html",
        context={
            "page_title": translate("auth.register.page_title", lang),
            "next_url": resolve_safe_next(next_url, default="") if next_url else "",
            "form_values": {
                "full_name": " ".join(full_name.split()),
                "email": email.strip(),
            },
            "form_error": form_error,
            "field_errors": field_errors or {},
        },
        status_code=status_code,
    )


@router.get("/dang-nhap", response_class=HTMLResponse)
def login_page(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    next: str | None = None,
) -> Response:
    """Render the login page or redirect authenticated users to their role landing page."""
    current_user = _get_current_user(request)
    if current_user is not None:
        target = resolve_safe_next(next, default=ROLE_DEFAULT_REDIRECTS[current_user.role])
        return RedirectResponse(url=target, status_code=303)

    return _render_login(
        request=request,
        templates=templates,
        lang=get_request_lang(request),
        next_url=next,
    )


@router.post("/dang-nhap", response_class=HTMLResponse)
def login_submit(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    email: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    next: Annotated[str | None, Form()] = None,
) -> Response:
    """Handle standard HTML form sign-in and redirect with an HttpOnly session cookie."""
    lang = get_request_lang(request)
    try:
        issued = service.login(
            email=email,
            password=password,
            next_url=next,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except AuthError as exc:
        form_error, field_errors = translate_auth_error(exc, lang)
        return _render_login(
            request=request,
            templates=templates,
            lang=lang,
            email=email,
            next_url=next,
            form_error=form_error,
            field_errors=field_errors,
            status_code=exc.status_code,
            headers=rate_limit_headers(exc),
        )

    response = RedirectResponse(url=issued.result.redirect_to, status_code=303)
    secure = is_secure_request(request, settings)
    set_session_cookie(response, issued.raw_token, settings, secure=secure)
    set_csrf_cookie(response, issued.csrf_token, settings, secure=secure)
    return response


@router.get("/dang-ky", response_class=HTMLResponse)
def register_page(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    next: str | None = None,
) -> Response:
    """Render Buyer registration or redirect authenticated users away."""
    current_user = _get_current_user(request)
    if current_user is not None:
        target = resolve_safe_next(next, default=ROLE_DEFAULT_REDIRECTS[current_user.role])
        return RedirectResponse(url=target, status_code=303)

    return _render_register(
        request=request,
        templates=templates,
        lang=get_request_lang(request),
        next_url=next,
    )


@router.post("/dang-ky", response_class=HTMLResponse)
def register_submit(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    full_name: Annotated[str, Form()] = "",
    email: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "",
    confirm_password: Annotated[str, Form()] = "",
    next: Annotated[str | None, Form()] = None,
) -> Response:
    """Handle standard HTML Buyer registration form submit with confirmation check."""
    lang = get_request_lang(request)
    if password != confirm_password:
        return _render_register(
            request=request,
            templates=templates,
            lang=lang,
            full_name=full_name,
            email=email,
            next_url=next,
            form_error=translate("auth.errors.validation_failed", lang),
            field_errors={"confirm_password": translate("auth.errors.password_mismatch", lang)},
            status_code=422,
        )

    try:
        issued = service.register_buyer(
            full_name=full_name,
            email=email,
            password=password,
            next_url=next,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except AuthError as exc:
        form_error, field_errors = translate_auth_error(exc, lang)
        return _render_register(
            request=request,
            templates=templates,
            lang=lang,
            full_name=full_name,
            email=email,
            next_url=next,
            form_error=form_error,
            field_errors=field_errors,
            status_code=exc.status_code,
        )

    response = RedirectResponse(url=issued.result.redirect_to, status_code=303)
    secure = is_secure_request(request, settings)
    set_session_cookie(response, issued.raw_token, settings, secure=secure)
    set_csrf_cookie(response, issued.csrf_token, settings, secure=secure)
    return response


@router.post("/dang-xuat")
def logout_submit(
    request: Request,
    service: Annotated[AuthService, Depends(get_auth_service)],
    settings: Annotated[Settings, Depends(get_settings)],
    next: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Revoke server-side session, clear browser cookie, and redirect safely."""
    raw_token = request.cookies.get(settings.session_cookie_name)
    service.logout(
        raw_token,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    response = RedirectResponse(url=resolve_safe_next(next, default="/"), status_code=303)
    secure = is_secure_request(request, settings)
    clear_session_cookie(response, settings, secure=secure)
    clear_csrf_cookie(response, settings, secure=secure)
    return response
