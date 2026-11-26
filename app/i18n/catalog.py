"""JSON translation catalog loader and dot-notation lookup helper."""

import json
from functools import lru_cache
from pathlib import Path

from app.i18n import DEFAULT_LANG, Lang, normalize_lang

LOCALES_DIR = Path(__file__).resolve().parent / "locales"


def _flatten_catalog(data: dict[str, object], prefix: str = "") -> dict[str, str]:
    flattened: dict[str, str] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            nested = {str(k): v for k, v in value.items()}
            flattened.update(_flatten_catalog(nested, full_key))
        elif isinstance(value, str):
            flattened[full_key] = value
    return flattened


@lru_cache(maxsize=4)
def load_catalog(lang: Lang) -> dict[str, str]:
    """Load and cache the flattened key->text translation map for a language."""
    catalog_path = LOCALES_DIR / f"{lang}.json"
    raw = json.loads(catalog_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return _flatten_catalog({str(k): v for k, v in raw.items()})


def translate(key: str, lang: str = DEFAULT_LANG, **params: object) -> str:
    """Resolve a dot-notation translation key with fallback to VI and then the key itself."""
    resolved = normalize_lang(lang)
    catalog = load_catalog(resolved)
    template = catalog.get(key)
    if template is None and resolved != DEFAULT_LANG:
        template = load_catalog(DEFAULT_LANG).get(key)
    if template is None:
        return key
    return template.format(**params) if params else template
