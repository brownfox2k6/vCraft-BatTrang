"""Shared Vietnamese-aware URL slug normalization and collision-free slug generator."""

import re
import unicodedata
from collections.abc import Callable

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_MULTI_HYPHEN_RE = re.compile(r"-{2,}")


def slugify_vi(text: str, *, max_length: int = 120) -> str:
    """Normalize Vietnamese text into a clean ASCII kebab-case slug (`[a-z0-9-]`)."""
    replaced = text.replace("đ", "d").replace("Đ", "d")
    normalized = unicodedata.normalize("NFKD", replaced)
    ascii_only = "".join(ch for ch in normalized if not unicodedata.combining(ch)).lower()
    collapsed = _NON_ALNUM_RE.sub("-", ascii_only)
    cleaned = _MULTI_HYPHEN_RE.sub("-", collapsed).strip("-")
    if max_length > 0 and len(cleaned) > max_length:
        cleaned = cleaned[:max_length].rstrip("-")
    return cleaned


def generate_unique_slug(
    base_text: str,
    exists: Callable[[str], bool],
    *,
    fallback: str = "xuong-gom",
    max_length: int = 140,
) -> str:
    """Generate a unique slug by appending `-2`, `-3`, ... when the base slug already exists."""
    base = slugify_vi(base_text, max_length=max_length) or fallback
    if not exists(base):
        return base

    suffix = 2
    while True:
        suffix_str = f"-{suffix}"
        trimmed_base = base[: max_length - len(suffix_str)].rstrip("-") or fallback
        candidate = f"{trimmed_base}{suffix_str}"
        if not exists(candidate):
            return candidate
        suffix += 1
