"""Safe local redirect helpers preventing open-redirect vulnerabilities."""

from urllib.parse import urlsplit


def is_safe_local_path(candidate: str) -> bool:
    """Return True only when candidate is a relative path on the current origin."""
    if not candidate.startswith("/") or candidate.startswith("//"):
        return False
    if "\\" in candidate or "\r" in candidate or "\n" in candidate:
        return False
    parsed = urlsplit(candidate)
    return parsed.scheme == "" and parsed.netloc == ""


def resolve_safe_next(next_url: str | None, default: str = "/") -> str:
    """Return a sanitized local redirect path or fall back to the supplied default."""
    if next_url is None:
        return default
    cleaned = next_url.strip()
    if cleaned and is_safe_local_path(cleaned):
        return cleaned
    return default
