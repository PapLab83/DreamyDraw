from __future__ import annotations

import re
import unicodedata

_YO_TO_E = str.maketrans({"ё": "е", "Ё": "Е"})
_PUNCTUATION_RE = re.compile(r"[^\w\s]+", re.UNICODE)


def normalize_lookup_phrase(value: str) -> str:
    """Normalize user/style phrases for registry matching."""
    normalized = unicodedata.normalize("NFKC", value).translate(_YO_TO_E).casefold().strip()
    normalized = _PUNCTUATION_RE.sub(" ", normalized)
    return re.sub(r"\s+", " ", normalized).strip()
