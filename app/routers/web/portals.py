"""Role-protected SSR workspace portal shells (/nghe-nhan and /quan-tri)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.i18n import Lang
from app.i18n.catalog import translate
from app.models.auth import UserRole
from app.routers.dependencies import get_request_lang, get_templates
from app.routers.guards import require_roles_web
from app.services.auth_service import AuthenticatedUser

router = APIRouter(tags=["web-portals"])


@router.get("/nghe-nhan", response_class=HTMLResponse)
def artisan_portal(
    request: Request,
    artisan: Annotated[AuthenticatedUser, Depends(require_roles_web(UserRole.ARTISAN))],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    lang: Annotated[Lang, Depends(get_request_lang)],
) -> HTMLResponse:
    """Render the Artisan workspace portal shell (strictly Artisan role)."""
    return templates.TemplateResponse(
        request=request,
        name="portals/artisan.html",
        context={
            "page_title": translate("portals.artisan.page_title", lang),
            "workspace_role_label": translate("portals.artisan.role_label", lang),
            "sidebar_items": [
                {
                    "label": translate("portals.artisan.nav_overview", lang),
                    "href": "/nghe-nhan",
                    "active": True,
                }
            ],
            "portal_user": artisan,
        },
    )


@router.get("/quan-tri", response_class=HTMLResponse)
def admin_portal(
    request: Request,
    admin: Annotated[AuthenticatedUser, Depends(require_roles_web(UserRole.ADMIN))],
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    lang: Annotated[Lang, Depends(get_request_lang)],
) -> HTMLResponse:
    """Render the Management Board workspace portal shell (strictly Admin role)."""
    return templates.TemplateResponse(
        request=request,
        name="portals/admin.html",
        context={
            "page_title": translate("portals.admin.page_title", lang),
            "workspace_role_label": translate("portals.admin.role_label", lang),
            "sidebar_items": [
                {
                    "label": translate("portals.admin.nav_overview", lang),
                    "href": "/quan-tri",
                    "active": True,
                }
            ],
            "portal_user": admin,
        },
    )
