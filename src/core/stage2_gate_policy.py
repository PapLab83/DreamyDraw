from __future__ import annotations

from typing import Any


def requires_character_consistency(summary: dict[str, Any] | None) -> bool:
    if not isinstance(summary, dict):
        return False
    if summary.get("character_profile"):
        return True
    subjects = summary.get("subjects")
    if not isinstance(subjects, list):
        return False
    return any(isinstance(subject, dict) and subject.get("is_character") for subject in subjects)


def apply_character_consistency_gate_policy(
    gates: dict[str, str],
    summary: dict[str, Any] | None,
) -> dict[str, str]:
    if requires_character_consistency(summary):
        return gates
    return {**gates, "character_consistency": "pass"}


def truth_mode(summary: dict[str, Any] | None) -> str | None:
    if not isinstance(summary, dict):
        return None
    mode = str(summary.get("truth_mode") or "").strip().upper()
    return mode or None


def append_truth_task(base: str, summary: dict[str, Any] | None, *, stage: str) -> str:
    if truth_mode(summary) != "TRUTH":
        return base
    suffix_by_stage = {
        "generate_candidates": (
            " TRUTH mode: write realistic observational stories. "
            "No fairy-tale openings, no animals speaking as real-world fact, no factual magic."
        ),
        "score_candidates": (
            " TRUTH mode: fail truth_fit for fairy-tale framing, speaking animals as fact, "
            "factual magic, or anthropomorphic social logic treated as real events."
        ),
        "validate_candidate": (
            " Cross-check the candidate against truth_mode and entity layer bodies in layer_grounding. "
            "Fail truth_fit for mode violations."
        ),
        "refine_candidate": (
            " Remove TRUTH violations while preserving theme, subject, and hard details. "
            "Do not rewrite into fairy tale."
        ),
    }
    return base + suffix_by_stage.get(stage, "")


def scorer_task(base: str, summary: dict[str, Any] | None, *, allowed_ids: set[str]) -> str:
    task = (
        f"{base} Return scores only for these exact candidate_id values: {sorted(allowed_ids)}."
    )
    if not requires_character_consistency(summary):
        task += (
            " No character_profile and no required persistent character: "
            "set character_consistency=pass unless the candidate invents a conflicting named character."
        )
    return append_truth_task(task, summary, stage="score_candidates")
