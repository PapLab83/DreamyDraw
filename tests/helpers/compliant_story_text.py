from __future__ import annotations

COMPLIANT_STORY_TEXT = (
    "Герой делает одно простое действие. "
    "Всё проходит спокойно и понятно. "
    "История заканчивается мягко."
)


def compliant_story_text(*, label: str = "") -> str:
    if not label:
        return COMPLIANT_STORY_TEXT
    return (
        f"{label}. "
        "Герой делает одно простое действие. "
        "История заканчивается мягко."
    )
