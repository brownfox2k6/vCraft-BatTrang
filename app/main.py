"""FastAPI application factory wiring configuration, database lifecycle, CSRF, and routers."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime
from urllib.parse import parse_qs

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError
from starlette.types import Message

from app.core.config import Settings
from app.core.database import create_db_engine, create_session_factory
from app.core.responses import ApiError, ApiResponse
from app.core.security import Argon2PasswordHasher, generate_csrf_token, verify_csrf_token
from app.core.templating import STATIC_DIR, create_templates
from app.i18n import LANG_COOKIE_NAME, normalize_lang
from app.i18n.catalog import translate
from app.routers.api.admin import router as admin_api_router
from app.routers.api.auth import router as auth_api_router
from app.routers.api.health import router as health_router
from app.routers.auth_cookies import is_secure_request, set_csrf_cookie
from app.routers.dependencies import build_auth_service, get_request_lang
from app.routers.guards import ApiGuardError, WebForbiddenError, WebRedirectError
from app.routers.web.auth import router as auth_web_router
from app.routers.web.home import router as home_router
from app.routers.web.lang import router as lang_router
from app.routers.web.portals import router as portals_web_router
from app.services.auth_service import default_utc_clock

_MUTATING_METHODS: frozenset[str] = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _wants_json_response(request: Request) -> bool:
    if request.url.path.startswith("/api/"):
        return True
    accept = request.headers.get("accept", "").lower()
    return "application/json" in accept and "text/html" not in accept


async def _extract_provided_csrf_token(request: Request, settings: Settings) -> str | None:
    header_token = request.headers.get(settings.csrf_header_name)
    if header_token:
        return header_token.strip()

    content_type = request.headers.get("content-type", "").lower()
    if content_type.startswith("application/x-www-form-urlencoded"):
        raw_body = await request.body()
        parsed = parse_qs(raw_body.decode("utf-8", errors="ignore"), keep_blank_values=False)
        values = parsed.get(settings.csrf_form_field)
        if values and values[0].strip():
            return values[0].strip()
    elif content_type.startswith("multipart/form-data"):
        raw_body = await request.body()
        sent = False

        async def _replay_receive() -> Message:
            nonlocal sent
            if sent:
                return {"type": "http.request", "body": b"", "more_body": False}
            sent = True
            return {"type": "http.request", "body": raw_body, "more_body": False}

        form = await Request(request.scope, receive=_replay_receive).form()
        try:
            raw_field = form.get(settings.csrf_form_field)
            if isinstance(raw_field, str) and raw_field.strip():
                return raw_field.strip()
        finally:
            await form.close()
    return None


def _ensure_vary_cookie(response: Response) -> None:
    if response.headers.get("content-type", "").lower().startswith("text/html"):
        existing_vary = (response.headers.get("vary") or "").strip()
        if not existing_vary:
            response.headers["Vary"] = "Cookie"
        elif "cookie" not in {part.strip().lower() for part in existing_vary.split(",")}:
            response.headers["Vary"] = f"{existing_vary}, Cookie"


def create_app(
    settings: Settings | None = None,
    *,
    clock: Callable[[], datetime] | None = None,
) -> FastAPI:
    """Create and configure a FastAPI instance with explicit settings injection."""
    resolved_settings = settings or Settings()
    resolved_clock = clock or default_utc_clock
    engine = create_db_engine(resolved_settings.database_url)
    session_factory = create_session_factory(engine)
    templates = create_templates(csrf_form_field=resolved_settings.csrf_form_field)
    password_hasher = Argon2PasswordHasher()

    @asynccontextmanager
    async def lifespan(_application: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(
        title=resolved_settings.app_name,
        debug=resolved_settings.debug,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.clock = resolved_clock
    app.state.password_hasher = password_hasher
    app.state.session_factory = session_factory
    app.state.templates = templates

    def _api_error_response(
        *,
        status_code: int,
        code: str,
        message_key: str,
        lang: str,
    ) -> JSONResponse:
        body = ApiResponse[None](
            error=ApiError(code=code, message=translate(message_key, lang)),
        )
        return JSONResponse(status_code=status_code, content=body.model_dump(mode="json"))

    def _web_forbidden_response(request: Request, *, message_key: str, lang: str) -> Response:
        response = templates.TemplateResponse(
            request=request,
            name="errors/403.html",
            context={
                "page_title": translate("errors.403.page_title", lang),
                "error_message": translate(message_key, lang),
            },
            status_code=403,
        )
        _ensure_vary_cookie(response)
        return response

    @app.exception_handler(ApiGuardError)
    async def handle_api_guard_error(request: Request, exc: ApiGuardError) -> JSONResponse:
        return _api_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message_key=exc.message_key,
            lang=get_request_lang(request),
        )

    @app.exception_handler(WebRedirectError)
    async def handle_web_redirect_error(
        _request: Request,
        exc: WebRedirectError,
    ) -> RedirectResponse:
        return RedirectResponse(url=exc.redirect_url, status_code=303)

    @app.exception_handler(WebForbiddenError)
    async def handle_web_forbidden_error(
        request: Request,
        exc: WebForbiddenError,
    ) -> Response:
        return _web_forbidden_response(
            request,
            message_key=exc.message_key,
            lang=get_request_lang(request),
        )

    @app.middleware("http")
    async def attach_request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        lang = normalize_lang(request.cookies.get(LANG_COOKIE_NAME))
        request.state.lang = lang
        request.state.current_user = None
        request.state.csrf_token = ""

        path = request.url.path
        if path == "/api/health" or path.startswith("/static/"):
            return await call_next(request)

        session_csrf: str | None = None
        raw_session_token = request.cookies.get(resolved_settings.session_cookie_name)
        if raw_session_token:
            try:
                with session_factory() as db:
                    auth_service = build_auth_service(
                        db,
                        password_hasher=password_hasher,
                        settings=resolved_settings,
                        clock=resolved_clock,
                    )
                    session_ctx = auth_service.resolve_session_context(raw_session_token)
                    if session_ctx is not None:
                        request.state.current_user = session_ctx.user
                        session_csrf = session_ctx.csrf_token or None
            except SQLAlchemyError:
                request.state.current_user = None
                session_csrf = None

        cookie_csrf = request.cookies.get(resolved_settings.csrf_cookie_name)
        expected_csrf = session_csrf if session_csrf is not None else cookie_csrf
        should_set_csrf_cookie = False
        if expected_csrf:
            request.state.csrf_token = expected_csrf
        else:
            request.state.csrf_token = generate_csrf_token()
            should_set_csrf_cookie = True

        if request.method.upper() in _MUTATING_METHODS:
            provided_csrf = await _extract_provided_csrf_token(request, resolved_settings)
            if not verify_csrf_token(expected_csrf, provided_csrf):
                if _wants_json_response(request):
                    return _api_error_response(
                        status_code=403,
                        code="CSRF_INVALID",
                        message_key="auth.errors.csrf_invalid",
                        lang=lang,
                    )
                return _web_forbidden_response(
                    request,
                    message_key="auth.errors.csrf_invalid",
                    lang=lang,
                )

        response = await call_next(request)
        if should_set_csrf_cookie or (session_csrf is not None and cookie_csrf != session_csrf):
            existing_cookies = response.headers.getlist("set-cookie")
            csrf_prefix = f"{resolved_settings.csrf_cookie_name}="
            if not any(header.startswith(csrf_prefix) for header in existing_cookies):
                set_csrf_cookie(
                    response,
                    request.state.csrf_token,
                    resolved_settings,
                    secure=is_secure_request(request, resolved_settings),
                )
        _ensure_vary_cookie(response)
        return response

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(health_router)
    app.include_router(auth_api_router)
    app.include_router(admin_api_router)
    app.include_router(lang_router)
    app.include_router(auth_web_router)
    app.include_router(portals_web_router)
    app.include_router(home_router)
    return app
