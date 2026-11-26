"""JSON translation catalog loader and dot-notation lookup helper."""

import json
import re
from functools import lru_cache
from pathlib import Path

from app.i18n import DEFAULT_LANG, Lang, normalize_lang

LOCALES_DIR = Path(__file__).resolve().parent / "locales"

_PLAIN_TEXT_KEYS: frozenset[str] = frozenset(
    {
        "site.title_default",
        "site.meta_description",
        "theme.toggle_title",
    }
)

_NON_BREAKING_PHRASES: dict[Lang, tuple[str, ...]] = {
    "vi": (
        "Làng gốm Bát Tràng",
        "Thành phố Hà Nội",
        "Xã Bát Tràng",
        "Bát Tràng",
        "Hà Nội",
        "Ban Quản lý",
        "Triển lãm số",
        "lô gốm QR",
    ),
    "en": (
        "Bát Tràng Commune",
        "Bát Tràng",
        "Pottery Village",
        "Digital Exhibition",
        "Management Board",
    ),
}

_PLACEHOLDER_RE = re.compile(r"(\{[^{}]+\})")
_SEPARATORS: frozenset[str] = frozenset({"·", "-", "–", "—", "/"})


def _bind_phrases(segment: str, phrases: tuple[str, ...]) -> str:
    for phrase in phrases:
        if phrase in segment:
            segment = segment.replace(phrase, phrase.replace(" ", "\u00a0"))
    return segment


def _prevent_widow(line: str) -> str:
    tokens = line.split(" ")
    if len(tokens) < 5:
        return line
    last = tokens[-1]
    prev = tokens[-2]
    if "\u00a0" in last or prev in _SEPARATORS:
        return line
    if (last.startswith("{") and last.endswith("}")) or (
        prev.startswith("{") and prev.endswith("}")
    ):
        return line
    return " ".join([*tokens[:-2], f"{prev}\u00a0{last}"])


def _apply_typography(text: str, lang: Lang) -> str:
    """Bind proper-noun phrases and prevent orphan trailing words without mutating placeholders."""
    phrases = _NON_BREAKING_PHRASES.get(lang, ())
    processed_lines: list[str] = []
    for line in text.split("\n"):
        parts = _PLACEHOLDER_RE.split(line)
        bound = "".join(
            part if _PLACEHOLDER_RE.fullmatch(part) else _bind_phrases(part, phrases)
            for part in parts
        )
        processed_lines.append(_prevent_widow(bound))
    return "\n".join(processed_lines)


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
    flattened = _flatten_catalog({str(k): v for k, v in raw.items()})
    return {
        key: (
            value
            if key in _PLAIN_TEXT_KEYS or key.endswith("_aria")
            else _apply_typography(value, lang)
        )
        for key, value in flattened.items()
    }


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
