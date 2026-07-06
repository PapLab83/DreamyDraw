from __future__ import annotations

import re
from dataclasses import dataclass

from src.core.stage2_length_policy import get_length_policy
from src.models.schemas import ValidationIssue, ValidationResult

_ABBREVIATION_DOT = "<DOT>"
_ABBREVIATIONS = ("т.д.", "т.п.", "и т.д.", "и т.п.", "др.")
_SENTENCE_SPLIT = re.compile(r"[.!?…]+\s*")


@dataclass(frozen=True)
class LengthFinding:
    issue_type: str
    description: str
    required_fix: str


def count_story_sentences(text: str) -> int:
    """Count sentences in story text using MVP Russian heuristics."""
    normalized = text.strip()
    if not normalized:
        return 0

    protected = normalized.replace("…", ".")
    for abbr in _ABBREVIATIONS:
        protected = protected.replace(abbr, abbr.replace(".", _ABBREVIATION_DOT))

    parts = [part.strip() for part in _SENTENCE_SPLIT.split(protected) if part.strip()]
    return len(parts)


def check_length_text(text: str, target_age: str | None) -> list[LengthFinding]:
    policy = get_length_policy(target_age)
    count = count_story_sentences(text)

    if count < policy.sentences_min:
        return [
            LengthFinding(
                issue_type="text_underlength",
                description=(
                    f"Текст истории содержит {count} предложений; "
                    f"для возраста {target_age or '5'} нужно минимум {policy.sentences_min}."
                ),
                required_fix=(
                    f"Добавь содержание до {policy.sentences_min}-{policy.sentences_max} "
                    "коротких предложений, сохранив тему и субъект."
                ),
            )
        ]

    if count > policy.sentences_max:
        return [
            LengthFinding(
                issue_type="text_overlength",
                description=(
                    f"Текст истории содержит {count} предложений; "
                    f"для возраста {target_age or '5'} допустимо не больше {policy.sentences_max}."
                ),
                required_fix=(
                    f"Сократи текст до {policy.sentences_min}-{policy.sentences_max} "
                    "предложений, сохранив смысл, тему и субъект."
                ),
            )
        ]

    return []


def apply_length_post_check(
    validation: ValidationResult,
    *,
    target_age: str | None,
    text: str,
) -> ValidationResult:
    if validation.status != "accepted":
        return validation

    findings = check_length_text(text, target_age)
    if not findings:
        return validation

    issues = list(validation.issues)
    required_fixes = list(validation.required_fixes)
    for finding in findings:
        issues.append(
            ValidationIssue(
                type=finding.issue_type,
                severity="major",
                description=finding.description,
            )
        )
        if finding.required_fix not in required_fixes:
            required_fixes.append(finding.required_fix)

    summary = validation.summary or "Length post-check requires revision."
    return validation.model_copy(
        update={
            "status": "needs_revision",
            "summary": summary,
            "issues": issues,
            "required_fixes": required_fixes,
        }
    )
