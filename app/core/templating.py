"""Jinja2 templating, i18n context/filters, and static asset paths shared by web routers."""

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import Request
from fastapi.templating import Jinja2Templates
from jinja2 import pass_context

from app.i18n import DEFAULT_LANG, normalize_lang
from app.i18n.catalog import translate
from app.i18n.fallback import localized_field
from app.i18n.formatting import format_currency, format_date, format_datetime
from app.routers.dependencies import get_request_lang

APP_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"


def _resolve_context_lang(context: Mapping[str, Any], override: str | None = None) -> str:
    if override is not None:
        return normalize_lang(override)
    raw = context.get("lang")
    return normalize_lang(raw if isinstance(raw, str) else None)


@pass_context
def _jinja_t(context: Mapping[str, Any], key: str, **params: object) -> str:
    return translate(key, _resolve_context_lang(context), **params)


@pass_context
def _jinja_localize(
    context: Mapping[str, Any],
    obj: Any,
    field: str,
    lang: str | None = None,
) -> str:
    return localized_field(obj, field, _resolve_context_lang(context, lang))


@pass_context
def _jinja_format_currency(
    context: Mapping[str, Any],
    amount: int | float | Decimal,
    lang: str | None = None,
) -> str:
    return format_currency(amount, _resolve_context_lang(context, lang))


@pass_context
def _jinja_format_date(
    context: Mapping[str, Any],
    value: date | datetime,
    lang: str | None = None,
) -> str:
    return format_date(value, _resolve_context_lang(context, lang))


@pass_context
def _jinja_format_datetime(
    context: Mapping[str, Any],
    value: datetime,
    lang: str | None = None,
) -> str:
    return format_datetime(value, _resolve_context_lang(context, lang))


def _i18n_context_processor(request: Request) -> dict[str, Any]:
    current_url = request.url.path or "/"
    if request.url.query:
        current_url = f"{current_url}?{request.url.query}"
    return {
        "lang": get_request_lang(request),
        "current_url": current_url,
        "current_user": getattr(request.state, "current_user", None),
    }


def create_templates() -> Jinja2Templates:
    """Create a Jinja2Templates engine with bilingual helpers and formatters registered."""
    templates = Jinja2Templates(
        directory=str(TEMPLATES_DIR),
        context_processors=[_i18n_context_processor],
    )
    templates.env.globals["lang"] = DEFAULT_LANG
    templates.env.globals["current_url"] = "/"
    templates.env.globals["current_user"] = None
    templates.env.globals["t"] = _jinja_t
    templates.env.globals["localize"] = _jinja_localize
    templates.env.filters["format_currency"] = _jinja_format_currency
    templates.env.filters["format_date"] = _jinja_format_date
    templates.env.filters["format_datetime"] = _jinja_format_datetime
    templates.env.filters["localized_field"] = _jinja_localize
    return templates
