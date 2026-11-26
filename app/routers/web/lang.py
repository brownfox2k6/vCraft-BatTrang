"""Language preference switching endpoint (POST /lang) with safe local redirects."""

from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.i18n import LANG_COOKIE_MAX_AGE, LANG_COOKIE_NAME, normalize_lang

router = APIRouter(tags=["web"])


def _is_safe_local_path(candidate: str) -> bool:
    if not candidate.startswith("/") or candidate.startswith("//"):
        return False
    if "\\" in candidate or "\r" in candidate or "\n" in candidate:
        return False
    parsed = urlsplit(candidate)
    return parsed.scheme == "" and parsed.netloc == ""


def _resolve_redirect_target(request: Request, next_url: str | None) -> str:
    if next_url is not None and next_url.strip():
        cleaned = next_url.strip()
        if _is_safe_local_path(cleaned):
            return cleaned
        return "/"

    referer = request.headers.get("referer")
    if referer:
        parsed = urlsplit(referer)
        if parsed.netloc == request.url.netloc or parsed.netloc == "":
            rebuilt = parsed.path or "/"
            if parsed.query:
                rebuilt = f"{rebuilt}?{parsed.query}"
            if _is_safe_local_path(rebuilt):
                return rebuilt
    return "/"


@router.post("/lang")
def switch_language(
    request: Request,
    lang: Annotated[str, Form()],
    next: Annotated[str | None, Form()] = None,
) -> RedirectResponse:
    """Persist the chosen VI | EN language in a cookie and redirect back safely."""
    resolved_lang = normalize_lang(lang)
    target = _resolve_redirect_target(request, next)
    response = RedirectResponse(url=target, status_code=303)
    response.set_cookie(
        key=LANG_COOKIE_NAME,
        value=resolved_lang,
        max_age=LANG_COOKIE_MAX_AGE,
        path="/",
        samesite="lax",
        httponly=False,
    )
    return response
