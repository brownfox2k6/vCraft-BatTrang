"""Bilingual (VI | EN) internationalization helpers, catalogs, and formatters."""

from typing import Literal

Lang = Literal["vi", "en"]

DEFAULT_LANG: Lang = "vi"
SUPPORTED_LANGS: tuple[Lang, Lang] = ("vi", "en")
LANG_COOKIE_NAME = "vcraft_lang"
LANG_COOKIE_MAX_AGE = 60 * 60 * 24 * 365


def normalize_lang(value: str | None) -> Lang:
    """Return a supported language code, defaulting to Vietnamese."""
    if value is None:
        return DEFAULT_LANG
    cleaned = value.strip().lower()
    if cleaned == "en":
        return "en"
    return DEFAULT_LANG
