"""FastAPI application factory wiring configuration, database lifecycle, and routers."""

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles

from app.core.config import Settings
from app.core.database import create_db_engine, create_session_factory
from app.core.templating import STATIC_DIR, create_templates
from app.i18n import LANG_COOKIE_NAME, normalize_lang
from app.routers.api.health import router as health_router
from app.routers.web.home import router as home_router
from app.routers.web.lang import router as lang_router


def create_app(settings: Settings | None = None) -> FastAPI:
    """Create and configure a FastAPI instance with explicit settings injection."""
    resolved_settings = settings or Settings()
    engine = create_db_engine(resolved_settings.database_url)
    session_factory = create_session_factory(engine)
    templates = create_templates()

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
    app.state.session_factory = session_factory
    app.state.templates = templates

    @app.middleware("http")
    async def attach_request_language(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        request.state.lang = normalize_lang(request.cookies.get(LANG_COOKIE_NAME))
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
    app.include_router(lang_router)
    app.include_router(home_router)
    return app
