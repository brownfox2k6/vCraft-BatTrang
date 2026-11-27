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
        "workspace.role_default",
        "auth.login.page_title",
        "auth.register.page_title",
    }
)

_NON_BREAKING_PHRASES: dict[Lang, tuple[str, ...]] = {
    "vi": (
        "vCraft Bát Tràng",
        "Làng gốm Bát Tràng",
        "Thành phố Hà Nội",
        "Xã Bát Tràng",
        "Bát Tràng",
        "Hà Nội",
        "Ban Quản lý",
        "Triển lãm số",
        "lô gốm QR",
        "lô gốm",
        "xưởng gốm",
        "đơn báo giá",
        "báo giá",
        "tài khoản",
        "hộ gia đình",
        "khách hàng",
        "nghệ nhân",
        "tác phẩm",
        "hành trình",
        "theo dõi",
        "tiến độ",
        "trọn vẹn",
        "truyền thống",
        "nguồn gốc",
        "xác minh",
        "tạo dáng",
        "ký tự",
        "chữ cái",
        "chữ số",
    ),
    "en": (
        "vCraft Bát Tràng",
        "Bát Tràng Commune",
        "Bát Tràng",
        "Pottery Village",
        "Digital Exhibition",
        "Management Board",
        "quote requests",
        "ceramic workshops",
        "family workshops",
        "kiln batch",
        "batch progress",
    ),
}

_GLUE_WORDS: dict[Lang, frozenset[str]] = {
    "vi": frozenset({"và", "hoặc", "tại", "với", "của", "các", "từ", "cho", "để"}),
    "en": frozenset({"a", "an", "the", "to", "of", "in", "for", "or", "and", "with"}),
}

_PLACEHOLDER_RE = re.compile(r"(\{[^{}]+\})")
_HYPHEN_IN_WORD_RE = re.compile(r"(?<=\w)-(?=\w)")
_QUANTITY_UNIT_RE = re.compile(r"(?<!\w)(\d{1,3}) ([a-zà-ỹ]\w*)", re.IGNORECASE)
_SEPARATORS: frozenset[str] = frozenset({"·", "-", "–", "—", "/"})
_MAX_BOUND_CHUNK_LEN = 22


def _compile_phrase_pattern(phrases: tuple[str, ...]) -> re.Pattern[str]:
    ordered = sorted(phrases, key=len, reverse=True)
    alternatives = "|".join(re.escape(phrase) for phrase in ordered)
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


_NON_BREAKING_PATTERNS: dict[Lang, re.Pattern[str]] = {
    lang: _compile_phrase_pattern(phrases) for lang, phrases in _NON_BREAKING_PHRASES.items()
}


def _bind_non_breaking_hyphens(segment: str) -> str:
    return _HYPHEN_IN_WORD_RE.sub("\u2011", segment)


def _bind_phrases(segment: str, pattern: re.Pattern[str] | None) -> str:
    if pattern is None:
        return segment
    return pattern.sub(lambda match: match.group(0).replace(" ", "\u00a0"), segment)


def _bind_quantity_units(segment: str) -> str:
    return _QUANTITY_UNIT_RE.sub("\\1\u00a0\\2", segment)


def _bind_glue_words(line: str, lang: Lang) -> str:
    glue_words = _GLUE_WORDS.get(lang)
    if not glue_words:
        return line
    tokens = line.split(" ")
    if len(tokens) < 2:
        return line
    for idx in range(len(tokens) - 2, -1, -1):
        word = tokens[idx]
        nxt = tokens[idx + 1]
        if word.lower() not in glue_words:
            continue
        if nxt in _SEPARATORS or "{" in nxt or "}" in nxt:
            continue
        if "\u00a0" in nxt and nxt.split("\u00a0", 1)[0].lower() in glue_words:
            continue
        if len(word) + 1 + len(nxt) > _MAX_BOUND_CHUNK_LEN:
            continue
        tokens[idx : idx + 2] = [f"{word}\u00a0{nxt}"]
    return " ".join(tokens)


def _prevent_widow(line: str) -> str:
    tokens = line.split(" ")
    if len(tokens) < 4:
        return line
    last = tokens[-1]
    prev = tokens[-2]
    if "\u00a0" in last or prev in _SEPARATORS:
        return line
    if any(brace in token for token in (prev, last) for brace in ("{", "}")):
        return line
    if len(prev) + 1 + len(last) > _MAX_BOUND_CHUNK_LEN:
        return line
    return " ".join([*tokens[:-2], f"{prev}\u00a0{last}"])


def _apply_typography(text: str, lang: Lang) -> str:
    """Bind proper-noun phrases and prevent orphan trailing words without mutating placeholders."""
    pattern = _NON_BREAKING_PATTERNS.get(lang)
    processed_lines: list[str] = []
    for line in text.split("\n"):
        parts = _PLACEHOLDER_RE.split(line)
        bound = "".join(
            (
                part
                if _PLACEHOLDER_RE.fullmatch(part)
                else _bind_quantity_units(_bind_phrases(_bind_non_breaking_hyphens(part), pattern))
            )
            for part in parts
        )
        glued = _bind_glue_words(bound, lang)
        processed_lines.append(_prevent_widow(glued))
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
            if key in _PLAIN_TEXT_KEYS
            or key.endswith(("_aria", ".page_title"))
            or key.startswith(("auth.errors.", "media.errors."))
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
