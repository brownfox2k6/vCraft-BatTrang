"""Dynamic database field bilingual selection with automatic fallback to Vietnamese."""

from collections.abc import Mapping
from typing import Any

from app.i18n import DEFAULT_LANG, normalize_lang


def _non_empty_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    return value if value.strip() else None


def pick_localized(
    vi_value: str | None,
    en_value: str | None,
    lang: str = DEFAULT_LANG,
) -> str:
    """Return the selected language text, automatically falling back to Vietnamese when empty."""
    resolved = normalize_lang(lang)
    vi_text = _non_empty_text(vi_value)
    en_text = _non_empty_text(en_value)

    if resolved == "en":
        return en_text or vi_text or ""
    return vi_text or en_text or ""


def localized_field(obj: Any, field: str, lang: str = DEFAULT_LANG) -> str:
    """Read `<field>_vi` and `<field>_en` from an ORM model, object, or mapping with VI fallback."""
    vi_key = f"{field}_vi"
    en_key = f"{field}_en"

    if isinstance(obj, Mapping):
        vi_val = obj.get(vi_key)
        en_val = obj.get(en_key)
    else:
        vi_val = getattr(obj, vi_key, None)
        en_val = getattr(obj, en_key, None)

    return pick_localized(
        vi_val if isinstance(vi_val, str) else None,
        en_val if isinstance(en_val, str) else None,
        lang,
    )
