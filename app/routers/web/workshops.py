"""Public workshop registration SSR page router (/dang-ky-xuong)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.core.config import Settings
from app.i18n import Lang
from app.i18n.catalog import translate
from app.models.auth import UserRole
from app.routers.dependencies import get_request_lang, get_settings, get_templates
from app.services.auth_service import AuthenticatedUser

router = APIRouter(tags=["web-workshops"])


@router.get("/dang-ky-xuong", response_class=HTMLResponse)
def workshop_application_page(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    settings: Annotated[Settings, Depends(get_settings)],
    lang: Annotated[Lang, Depends(get_request_lang)],
) -> Response:
    """Render the public household workshop registration form (redirecting active Artisans)."""
    current_user = getattr(request.state, "current_user", None)
    if isinstance(current_user, AuthenticatedUser) and current_user.role == UserRole.ARTISAN:
        return RedirectResponse(url="/nghe-nhan", status_code=303)

    return templates.TemplateResponse(
        request=request,
        name="workshops/apply.html",
        context={
            "page_title": translate("workshop_apply.page_title", lang),
            "active_nav": "workshops",
            "max_files": settings.media_max_files_per_request,
            "max_bytes": settings.media_max_bytes,
            "max_mb": max(1, settings.media_max_bytes // (1024 * 1024)),
        },
    )
