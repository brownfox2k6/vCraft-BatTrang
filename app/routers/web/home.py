"""Public homepage presentation router."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.i18n import Lang
from app.i18n.catalog import translate
from app.routers.dependencies import get_request_lang, get_templates

router = APIRouter(tags=["web"])


@router.get("/", response_class=HTMLResponse)
def read_home(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
    lang: Annotated[Lang, Depends(get_request_lang)],
) -> HTMLResponse:
    """Render the minimal vCraft Bat Trang homepage shell."""
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "page_title": translate("home.page_title", lang),
        },
    )
