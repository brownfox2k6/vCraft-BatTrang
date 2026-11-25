"""Public homepage presentation router."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.routers.dependencies import get_templates

router = APIRouter(tags=["web"])


@router.get("/", response_class=HTMLResponse)
def read_home(
    request: Request,
    templates: Annotated[Jinja2Templates, Depends(get_templates)],
) -> HTMLResponse:
    """Render the minimal vCraft Bat Trang homepage shell."""
    return templates.TemplateResponse(
        request=request,
        name="home.html",
        context={
            "page_title": "vCraft Bát Tràng — Tinh hoa làng nghề, muôn phương lan tỏa",
        },
    )
