from __future__ import annotations

from src.core.stage2_gate_policy import (
    apply_character_consistency_gate_policy,
    append_truth_task,
    requires_character_consistency,
    scorer_task,
    truth_mode,
)


def test_requires_character_consistency_without_profile_or_character_subjects() -> None:
    summary = {
        "character_profile": None,
        "subjects": [{"id": "fox", "is_character": False}],
    }
    assert requires_character_consistency(summary) is False


def test_requires_character_consistency_when_subject_is_character() -> None:
    summary = {
        "character_profile": None,
        "subjects": [{"id": "fox", "is_character": True}],
    }
    assert requires_character_consistency(summary) is True


def test_apply_character_consistency_gate_policy_auto_passes_without_character() -> None:
    gates = {"character_consistency": "fail", "truth_fit": "pass"}
    result = apply_character_consistency_gate_policy(
        gates,
        {"character_profile": None, "subjects": [{"is_character": False}]},
    )
    assert result["character_consistency"] == "pass"
    assert result["truth_fit"] == "pass"


def test_apply_character_consistency_gate_policy_keeps_fail_when_character_required() -> None:
    gates = {"character_consistency": "fail", "truth_fit": "pass"}
    result = apply_character_consistency_gate_policy(
        gates,
        {"character_profile": {"name": "Tim"}, "subjects": []},
    )
    assert result["character_consistency"] == "fail"


def test_append_truth_task_only_for_truth_mode() -> None:
    base = "Score each candidate."
    assert append_truth_task(base, {"truth_mode": "FAIRY_TALE"}, stage="score_candidates") == base
    truth_task = append_truth_task(base, {"truth_mode": "TRUTH"}, stage="score_candidates")
    assert "TRUTH mode" in truth_task
    assert "truth_fit" in truth_task


def test_scorer_task_includes_character_auto_pass_hint() -> None:
    task = scorer_task(
        "Score each candidate.",
        {"truth_mode": "TRUTH", "character_profile": None, "subjects": [{"is_character": False}]},
        allowed_ids={"c01"},
    )
    assert "character_consistency=pass" in task
    assert "TRUTH mode" in task
    assert "c01" in task


def test_truth_mode_normalizes_case() -> None:
    assert truth_mode({"truth_mode": "truth"}) == "TRUTH"
