from __future__ import annotations

import pytest

from src.core.stage2_truth_post_check import apply_truth_post_check, check_truth_text
from src.models.schemas import ValidationIssue, ValidationResult


@pytest.mark.parametrize(
    ("text", "category"),
    [
        ("Жила-была лиса в зимнем лесу.", "fairy_opening"),
        ("В некотором царстве жила лиса.", "fairy_opening"),
        ("Однажды в сказочном лесу ёжик искал листья.", "fairy_opening"),
        ("Лиса сказала: «Пойдём со мной».", "direct_animal_speech"),
        ("Ёжик ответил мальчику и пошёл дальше.", "direct_animal_speech"),
        ("«Пойдём со мной», — сказала лиса.", "direct_animal_speech"),
    ],
)
def test_check_truth_text_flags_category_one_and_two(text: str, category: str) -> None:
    findings = check_truth_text(text)

    assert findings
    assert findings[0].category == category


@pytest.mark.parametrize(
    "text",
    [
        "Правдивая короткая история: ёжик зимой тихо ищет укрытие в лесу.",
        "Лисёнок прислушался и побежал к норе.",
        "Мальчик представил, что ёжик сказал ему спасибо, но на самом деле ёжик тихо пошёл к кустам.",
    ],
)
def test_check_truth_text_allows_clean_or_imagination_frame(text: str) -> None:
    assert check_truth_text(text) == []


def test_apply_truth_post_check_downgrades_accepted_truth_violation() -> None:
    validation = ValidationResult(
        candidate_id="c01",
        version_id="c01_v1",
        status="accepted",
        summary="ok",
        issues=[],
        required_fixes=[],
    )

    result = apply_truth_post_check(
        validation,
        truth_mode_value="TRUTH",
        text="Жила-была лиса в лесу.",
    )

    assert result.status == "needs_revision"
    assert result.issues[0].type == "truth_fit"
    assert result.issues[0].severity == "major"
    assert result.required_fixes


def test_apply_truth_post_check_skips_non_truth_mode() -> None:
    validation = ValidationResult(
        candidate_id="c01",
        version_id="c01_v1",
        status="accepted",
        summary="ok",
        issues=[],
        required_fixes=[],
    )

    result = apply_truth_post_check(
        validation,
        truth_mode_value="FAIRY_TALE",
        text="Жила-была лиса в лесу.",
    )

    assert result.status == "accepted"
    assert result.issues == []


def test_apply_truth_post_check_preserves_existing_issues_on_downgrade() -> None:
    validation = ValidationResult(
        candidate_id="c01",
        version_id="c01_v1",
        status="accepted",
        summary="ok",
        issues=[ValidationIssue(type="age_fit", severity="minor", description="long")],
        required_fixes=["shorten"],
    )

    result = apply_truth_post_check(
        validation,
        truth_mode_value="TRUTH",
        text="Лиса сказала: «Привет».",
    )

    assert result.status == "needs_revision"
    assert len(result.issues) == 2
    assert result.issues[0].type == "age_fit"
    assert result.issues[1].type == "truth_fit"
