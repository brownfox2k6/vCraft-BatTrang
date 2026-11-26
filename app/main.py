"""FastAPI application factory wiring configuration, database lifecycle, and routers."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.core.database import create_db_engine, create_session_factory
from app.core.security import Argon2PasswordHasher
from app.core.templating import STATIC_DIR, create_templates
from app.i18n import LANG_COOKIE_NAME, normalize_lang
from app.routers.api.auth import router as auth_api_router
from app.routers.api.health import router as health_router
from app.routers.dependencies import build_auth_service
from app.routers.web.auth import router as auth_web_router
from app.routers.web.home import router as home_router
from app.routers.web.lang import router as lang_router
from app.services.auth_service import default_utc_clock


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
    templates = create_templates()
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

    @app.middleware("http")
    async def attach_request_context(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.lang = normalize_lang(request.cookies.get(LANG_COOKIE_NAME))
        request.state.current_user = None
        path = request.url.path
        raw_session_token = request.cookies.get(resolved_settings.session_cookie_name)
        if raw_session_token and path != "/api/health" and not path.startswith("/static/"):
            try:
                with session_factory() as db:
                    auth_service = build_auth_service(
                        db,
                        password_hasher=password_hasher,
                        settings=resolved_settings,
                        clock=resolved_clock,
                    )
                    request.state.current_user = auth_service.resolve_session(raw_session_token)
            except SQLAlchemyError:
                request.state.current_user = None

        response = await call_next(request)
        if response.headers.get("content-type", "").lower().startswith("text/html"):
            existing_vary = (response.headers.get("vary") or "").strip()
            if not existing_vary:
                response.headers["Vary"] = "Cookie"
            elif "cookie" not in {part.strip().lower() for part in existing_vary.split(",")}:
                response.headers["Vary"] = f"{existing_vary}, Cookie"
        return response

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
    app.include_router(health_router)
    app.include_router(auth_api_router)
    app.include_router(lang_router)
    app.include_router(auth_web_router)
    app.include_router(home_router)
    return app
