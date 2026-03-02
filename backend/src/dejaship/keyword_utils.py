"""Keyword normalization utilities."""
import re

_INVALID_CHARS = re.compile(r"[^a-z0-9-]")

# Pattern for a fully normalized (valid) keyword.
KEYWORD_PATTERN = re.compile(r"^[a-z0-9][a-z0-9\-]*[a-z0-9]$")


def normalize_keyword(kw: str) -> str:
    """Normalize a keyword: lowercase, spaces→hyphens, strip invalid chars, trim hyphens.

    Applies these transforms in order:
    1. Lowercase
    2. Replace spaces with hyphens
    3. Strip any char that is not alphanumeric or hyphen
    4. Strip leading/trailing hyphens
    """
    kw = kw.lower()
    kw = kw.replace(" ", "-")
    kw = _INVALID_CHARS.sub("", kw)
    kw = kw.strip("-")
    return kw
