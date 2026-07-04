from __future__ import annotations

import re
from dataclasses import dataclass

from src.core.interpretation.text_normalize import normalize_lookup_phrase

_HARD_MARKERS = ("строго", "обязательно")
_BOUNDARY = r"(?:\s+(?:для|про|и\b|на\b)|[.!?]|$)"

_STYLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "в_стиле",
        re.compile(rf"в\s+стиле\s+(.+?){_BOUNDARY}", re.IGNORECASE | re.UNICODE),
    ),
    (
        "как_у",
        re.compile(rf"как\s+у\s+(.+?){_BOUNDARY}", re.IGNORECASE | re.UNICODE),
    ),
    (
        "по",
        re.compile(rf"по[-\s]+(\S+(?:\s+\S{{0,3}})?){_BOUNDARY}", re.IGNORECASE | re.UNICODE),
    ),
    (
        "как",
        re.compile(
            rf"как\s+(?!у\b)(?!в\s+жизни\b)(?!в\s+реальности\b)(.+?){_BOUNDARY}",
            re.IGNORECASE | re.UNICODE,
        ),
    ),
    (
        "похоже_на",
        re.compile(rf"похож(?:е|ая|ий)\s+на\s+(.+?){_BOUNDARY}", re.IGNORECASE | re.UNICODE),
    ),
)


@dataclass(frozen=True)
class StylePhrase:
    raw: str
    normalized: str
    is_hard_requirement: bool
    source_pattern: str
    start: int


def extract_style_phrases(text: str) -> list[StylePhrase]:
    if not text.strip():
        return []

    lowered = text.casefold()
    found: list[StylePhrase] = []
    seen_normalized: set[str] = set()

    for pattern_name, pattern in _STYLE_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group(1).strip(" \t\n\r,;:")
            if not raw or len(raw) < 2:
                continue
            normalized = normalize_lookup_phrase(raw)
            if not normalized or normalized in seen_normalized:
                continue
            seen_normalized.add(normalized)
            found.append(
                StylePhrase(
                    raw=raw,
                    normalized=normalized,
                    is_hard_requirement=_is_hard_requirement(lowered, match.start()),
                    source_pattern=pattern_name,
                    start=match.start(),
                )
            )

    return sorted(found, key=lambda item: item.start)


def _is_hard_requirement(lowered_text: str, match_start: int) -> bool:
    window_start = max(0, match_start - 40)
    prefix = lowered_text[window_start:match_start]
    return any(marker in prefix for marker in _HARD_MARKERS)
