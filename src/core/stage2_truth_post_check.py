from __future__ import annotations

import re
from dataclasses import dataclass

from src.core.stage2_gate_policy import truth_mode
from src.models.schemas import ValidationIssue, ValidationResult

_IMAGINATION_MARKERS = (
    "представил",
    "представила",
    "вообразил",
    "вообразила",
    "подумал, что",
    "подумала, что",
    "мечтал, что",
    "мечтала, что",
    "казалось, что",
    "на самом деле",
)
_IMAGINATION_WINDOW_CHARS = 90

_FAIRY_OPENING_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bжил[аи]?-была\b", re.IGNORECASE), "жила-была"),
    (re.compile(r"\bжил-был\b", re.IGNORECASE), "жил-был"),
    (re.compile(r"\bжили-были\b", re.IGNORECASE), "жили-были"),
    (re.compile(r"\bв некотором царстве\b", re.IGNORECASE), "в некотором царстве"),
    (re.compile(r"\bв тридевят\w+ (?:царств\w+|королевств\w+)\b", re.IGNORECASE), "в тридевятом царстве"),
    (re.compile(r"\bоднажды в сказочн\w+\b", re.IGNORECASE), "однажды в сказочном"),
    (re.compile(r"\bкогда-то давным-давно\b", re.IGNORECASE), "когда-то давным-давно"),
)

_ANIMAL_TOKEN = (
    r"лис\w*|"
    r"ёжик\w*|ежик\w*|еж\w*|"
    r"зай\w*|"
    r"белк\w*|бельчон\w*|"
    r"попуг\w*|какад\w*"
)
_SPEECH_VERB = r"сказал\w*|ответил\w*|спросил\w*|произнес\w*|крикнул\w*|шепнул\w*|промолвил\w*|говорил\w*"

_ANIMAL_SPEECH_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            rf"\b(?P<animal>{_ANIMAL_TOKEN})\s+(?P<verb>{_SPEECH_VERB})\b",
            re.IGNORECASE,
        ),
        "прямая речь животного",
    ),
    (
        re.compile(
            rf"(?:[:«\"]\s*[^\"»]{{0,120}}?\s*)?—\s*(?P<verb>{_SPEECH_VERB})\s+(?P<animal>{_ANIMAL_TOKEN})\b",
            re.IGNORECASE,
        ),
        "прямая речь животного (реплика)",
    ),
)


@dataclass(frozen=True, slots=True)
class TruthPostCheckFinding:
    category: str
    marker: str
    description: str
    required_fix: str


def check_truth_text(text: str) -> list[TruthPostCheckFinding]:
    cleaned = str(text or "").strip()
    if not cleaned:
        return []

    findings: list[TruthPostCheckFinding] = []
    for pattern, marker in _FAIRY_OPENING_RULES:
        match = pattern.search(cleaned)
        if match is None or _in_imagination_frame(cleaned, match.start()):
            continue
        findings.append(
            TruthPostCheckFinding(
                category="fairy_opening",
                marker=marker,
                description="В TRUTH недопустимо сказочное вступление.",
                required_fix="Убрать сказочное вступление и начать с наблюдаемого действия.",
            )
        )
        break

    for pattern, marker in _ANIMAL_SPEECH_RULES:
        for match in pattern.finditer(cleaned):
            if _in_imagination_frame(cleaned, match.start()):
                continue
            findings.append(
                TruthPostCheckFinding(
                    category="direct_animal_speech",
                    marker=marker,
                    description="В TRUTH животное не должно говорить как человек.",
                    required_fix="Убрать прямую речь животного как факт; оставить наблюдаемое поведение.",
                )
            )
            return findings

    return findings


def apply_truth_post_check(
    validation: ValidationResult,
    *,
    truth_mode_value: str | None,
    text: str,
) -> ValidationResult:
    if validation.status != "accepted":
        return validation
    if truth_mode({"truth_mode": truth_mode_value}) != "TRUTH":
        return validation

    findings = check_truth_text(text)
    if not findings:
        return validation

    issues = list(validation.issues)
    required_fixes = list(validation.required_fixes)
    for finding in findings:
        issues.append(
            ValidationIssue(
                type="truth_fit",
                severity="major",
                description=f"{finding.description} (marker: {finding.marker})",
            )
        )
        if finding.required_fix not in required_fixes:
            required_fixes.append(finding.required_fix)

    summary = validation.summary or "TRUTH post-check requires revision."
    return validation.model_copy(
        update={
            "status": "needs_revision",
            "summary": summary,
            "issues": issues,
            "required_fixes": required_fixes,
        }
    )


def _in_imagination_frame(text: str, match_start: int) -> bool:
    window = text[max(0, match_start - _IMAGINATION_WINDOW_CHARS) : match_start].casefold()
    return any(marker in window for marker in _IMAGINATION_MARKERS)
