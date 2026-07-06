from __future__ import annotations

import pytest

from src.core.stage2_length_policy import (
    AGE_STORY_LENGTH_POLICIES,
    get_length_policy,
    length_policy_payload,
)
from src.core.stage2_length_post_check import (
    apply_length_post_check,
    check_length_text,
    count_story_sentences,
)
from src.models.schemas import ValidationIssue, ValidationResult


def test_get_length_policy_age_3() -> None:
    policy = get_length_policy("3")
    assert policy.sentences_min == 3
    assert policy.sentences_max == 4
    assert policy.complexity_profile == "strict"


def test_get_length_policy_age_5() -> None:
    policy = get_length_policy("5")
    assert policy.sentences_min == 3
    assert policy.sentences_max == 5
    assert policy.complexity_profile == "moderate"


def test_get_length_policy_unknown_falls_back_to_age_5() -> None:
    policy = get_length_policy(None)
    assert policy == AGE_STORY_LENGTH_POLICIES["5"]


def test_length_policy_payload_resolves_target_age() -> None:
    assert length_policy_payload("3") == {
        "target_age": "3",
        "sentences_min": 3,
        "sentences_max": 4,
        "complexity_profile": "strict",
    }


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Миша увидел лужу. Он обошёл её. Мама улыбнулась.", 3),
        ("Одно предложение.", 1),
        ("", 0),
    ],
)
def test_count_story_sentences(text: str, expected: int) -> None:
    assert count_story_sentences(text) == expected


def test_check_length_text_flags_overlength_for_age_3() -> None:
    text = ". ".join(f"Предложение {index}." for index in range(1, 9))
    findings = check_length_text(text, "3")

    assert len(findings) == 1
    assert findings[0].issue_type == "text_overlength"


def test_check_length_text_flags_underlength() -> None:
    findings = check_length_text("Одно предложение.", "5")

    assert len(findings) == 1
    assert findings[0].issue_type == "text_underlength"


def test_check_length_text_allows_five_sentences_for_age_5() -> None:
    text = " ".join(f"Шаг {index}." for index in range(1, 6))
    assert check_length_text(text, "5") == []


def test_check_length_text_rejects_five_sentences_for_age_3() -> None:
    text = " ".join(f"Шаг {index}." for index in range(1, 6))
    findings = check_length_text(text, "3")

    assert findings
    assert findings[0].issue_type == "text_overlength"


def test_apply_length_post_check_downgrades_accepted_overlength() -> None:
    validation = ValidationResult(
        candidate_id="c01",
        version_id="c01_v1",
        status="accepted",
        summary="ok",
        issues=[],
        required_fixes=[],
    )
    text = ". ".join(f"Предложение {index}." for index in range(1, 9))

    result = apply_length_post_check(validation, target_age="3", text=text)

    assert result.status == "needs_revision"
    assert result.issues[0].type == "text_overlength"
    assert result.required_fixes


def test_apply_length_post_check_skips_non_accepted() -> None:
    validation = ValidationResult(
        candidate_id="c01",
        version_id="c01_v1",
        status="needs_revision",
        summary="already bad",
        issues=[],
        required_fixes=[],
    )
    text = ". ".join(f"Предложение {index}." for index in range(1, 9))

    result = apply_length_post_check(validation, target_age="3", text=text)

    assert result.status == "needs_revision"
    assert result.issues == []


def test_apply_length_post_check_preserves_existing_issues() -> None:
    validation = ValidationResult(
        candidate_id="c01",
        version_id="c01_v1",
        status="accepted",
        summary="ok",
        issues=[ValidationIssue(type="age_fit", severity="minor", description="complex")],
        required_fixes=["simplify"],
    )
    text = ". ".join(f"Предложение {index}." for index in range(1, 9))

    result = apply_length_post_check(validation, target_age="3", text=text)

    assert result.status == "needs_revision"
    assert len(result.issues) == 2
    assert result.issues[0].type == "age_fit"
    assert result.issues[1].type == "text_overlength"
