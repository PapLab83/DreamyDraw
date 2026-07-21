from __future__ import annotations

import pytest

from tests.helpers.stage1_2_golden import GoldenStage2Executor, approved_text, layer_ids, run_golden_pipeline

pytestmark = pytest.mark.integration


def test_empty_meta_input_clarifies_without_starting_stage2(tmp_path):
    executor = GoldenStage2Executor()
    result, executor = run_golden_pipeline(tmp_path, "привет, что ты умеешь?", executor=executor)

    assert result.is_waiting_user or result.session.completion_status == "stopped_unresolved_request"
    assert not result.session.approved_texts
    assert executor.calls["generate_candidates"] == 0


def test_unsupported_style_as_soft_preference_is_preserved_without_failure(tmp_path):
    result, executor = run_golden_pipeline(
        tmp_path,
        "Сделай сказку про лису для 5 лет в акварельном импрессионистичном настроении.",
        count=1,
    )
    session = result.session

    assert result.is_done
    assert any("импрессионистич" in preference for preference in session.normalized_request.soft_preferences)
    assert "IMPRESSIONISM" not in " ".join(layer_ids(session))
    assert session.approved_texts
    assert executor.calls["generate_candidates"] == 1


def test_unsupported_style_as_hard_requirement_clarifies_without_fabricated_layer(tmp_path):
    executor = GoldenStage2Executor()
    result, executor = run_golden_pipeline(
        tmp_path,
        "Сделай сказку про лису для 5 лет строго в стиле Дисней.",
        count=1,
        executor=executor,
    )

    assert result.is_waiting_user or result.session.completion_status == "stopped_unresolved_request"
    assert not result.session.approved_texts
    assert "DISNEY" not in " ".join(layer_ids(result.session))
    assert executor.calls["generate_candidates"] == 0


def test_unsupported_non_brand_style_as_hard_requirement_clarifies(tmp_path):
    executor = GoldenStage2Executor()
    result, executor = run_golden_pipeline(
        tmp_path,
        "Сделай сказку про лису для 5 лет строго в импрессионистичном стиле.",
        count=1,
        executor=executor,
    )

    assert result.is_waiting_user or result.session.completion_status == "stopped_unresolved_request"
    assert not result.session.approved_texts
    assert "IMPRESSIONISM" not in " ".join(layer_ids(result.session))
    assert executor.calls["generate_candidates"] == 0


def test_truth_with_fantastic_hard_detail_does_not_approve_contradiction(tmp_path):
    executor = GoldenStage2Executor()
    result, executor = run_golden_pipeline(
        tmp_path,
        "Сделай правдивую историю про лису для 5 лет, обязательно чтобы она летала на волшебном ковре.",
        count=1,
        executor=executor,
    )

    assert result.is_waiting_user or result.session.completion_status == "stopped_unresolved_request"
    assert not result.session.approved_texts
    assert executor.calls["generate_candidates"] == 0


def test_candidate_with_required_subject_disappearing_is_refined_before_approval(tmp_path):
    result, _ = run_golden_pipeline(
        tmp_path,
        "Сделай 3 истории про лису, зайца и белку зимой, чтобы герои не исчезали.",
        count=1,
    )
    session = result.session

    assert result.is_done
    assert any(issue.type == "subject_continuity" for item in session.validation_results for issue in item.issues)
    assert "__DROP_SUBJECT__" not in approved_text(session)
    assert all("белка" in item.text.casefold() for item in session.approved_texts)


def test_refiner_that_changes_protected_character_profile_is_not_accepted(tmp_path):
    result, executor = run_golden_pipeline(
        tmp_path,
        "Сделай историю про маленького бельчонка Тима, он смелый и любит жёлуди.",
        count=1,
        executor=GoldenStage2Executor(mutate_tim_refiner=True),
    )
    session = result.session

    assert result.is_done
    assert executor.calls["refine_candidate"] >= 1
    assert "__TIM_MUTATED__" not in approved_text(session)
    assert all("Том" not in item.text for item in session.approved_texts)
    assert any(issue.type == "character_consistency" for item in session.validation_results for issue in item.issues)


def test_stranger_candy_unsafe_advice_is_not_approved(tmp_path):
    result, _ = run_golden_pipeline(
        tmp_path,
        "Сделай поучительную историю про незнакомца и конфету для ребёнка 5 лет.",
        count=1,
        utility_mode="TEACHING",
    )
    session = result.session

    assert result.is_done
    text = approved_text(session).casefold()
    assert "пошёл за ним" not in text
    assert "взял конфету у незнакомца" not in text
    assert any(issue.type == "safety" for item in session.validation_results for issue in item.issues)


def test_truth_animal_talking_like_person_is_not_approved(tmp_path):
    result, _ = run_golden_pipeline(
        tmp_path,
        "Сделай 1 правдивую короткую историю про ёжика зимой в лесу для ребёнка 3 лет.",
        count=1,
    )
    session = result.session

    assert result.is_done
    assert "__BAD_TALKING__" not in approved_text(session)
    assert "сказал человеческим голосом" not in approved_text(session).casefold()
    assert any(issue.type == "truth_fit" for item in session.validation_results for issue in item.issues)
