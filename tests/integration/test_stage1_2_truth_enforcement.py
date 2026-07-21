from __future__ import annotations

import pytest

from tests.helpers.stage1_2_golden import (
    LenientStage2Executor,
    approved_text,
    run_golden_pipeline,
)

pytestmark = pytest.mark.integration


def test_lenient_executor_natural_truth_violation_blocked_by_post_check(tmp_path):
    executor = LenientStage2Executor()
    result, executor = run_golden_pipeline(
        tmp_path,
        "Сделай 1 правдивую короткую историю про ёжика зимой в лесу для ребёнка 3 лет.",
        count=1,
        executor=executor,
    )
    session = result.session

    assert result.is_done
    assert session.normalized_request.truth_mode == "TRUTH"
    assert len(session.approved_texts) == 1
    text = approved_text(session).casefold()
    assert "жила-была" not in text
    assert "сказала" not in text
    assert "ёжик" in text
    assert any(issue.type == "truth_fit" for item in session.validation_results for issue in item.issues)
    assert executor.calls["refine_candidate"] >= 1


def test_lenient_executor_truth_fox_fairy_opening_blocked_without_marker(tmp_path):
    executor = LenientStage2Executor()
    result, executor = run_golden_pipeline(
        tmp_path,
        "Сделай 1 правдивую историю про лису для 5 лет.",
        count=1,
        executor=executor,
    )
    session = result.session

    assert result.is_done
    fox = next(subject for subject in session.normalized_request.subjects if subject.id == "fox")
    assert fox.is_character is False
    assert len(session.approved_texts) == 1
    text = approved_text(session).casefold()
    assert "жила-была" not in text
    assert "сказала" not in text
    assert "лис" in text
    assert any(issue.type == "truth_fit" for item in session.validation_results for issue in item.issues)


def test_lenient_executor_includes_truth_layer_bodies_in_runtime_context(tmp_path):
    executor = LenientStage2Executor()
    run_golden_pipeline(
        tmp_path,
        "Сделай 1 правдивую историю про лису для 5 лет.",
        count=1,
        executor=executor,
    )

    runtime_context = executor.runtime_contexts["generate_candidates"][0]
    assert runtime_context["body_policy"] == "include_bodies_runtime"
    assert "TRUTH_BASE" in runtime_context["bodies"]
    assert "# Назначение слоя" in runtime_context["bodies"]["TRUTH_BASE"]
    assert "TRUTH_ANIMAL_FOX" in runtime_context["bodies"]


def test_lenient_executor_fairy_tale_fox_still_allows_fairy_framing(tmp_path):
    executor = LenientStage2Executor()
    result, _ = run_golden_pipeline(
        tmp_path,
        "Сделай 1 сказочную историю про лису для 5 лет.",
        count=1,
        truth_mode="FAIRY_TALE",
        executor=executor,
    )
    session = result.session

    assert result.is_done
    assert session.normalized_request.truth_mode == "FAIRY_TALE"
    assert len(session.approved_texts) == 1
    assert "разговаривает" in approved_text(session).casefold()
    assert not any(
        issue.type == "truth_fit" and "сказочное вступление" in issue.description.casefold()
        for item in session.validation_results
        for issue in item.issues
    )
