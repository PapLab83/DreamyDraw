from __future__ import annotations

from src.core.stage2_expressiveness_policy import (
    append_expressiveness_task,
    has_folk_substyle,
    is_fairy_tale_context,
    requires_vivid_fairy_tale,
    resolve_candidate_count,
)


def test_resolve_candidate_count_explicit_override():
    assert resolve_candidate_count(2, 5) == 2


def test_resolve_candidate_count_scales_with_output_count():
    assert resolve_candidate_count(None, 5) == 20
    assert resolve_candidate_count(None, 8) == 24


def test_requires_vivid_fairy_tale_for_folk_fox_stack():
    runtime = {
        "normalized_request_summary": {
            "truth_mode": "FAIRY_TALE",
            "substyle": "RUSSIAN_FOLK_TALE",
        },
        "ordered_layer_refs": [
            {"id": "RUSSIAN_FOLK_TALE"},
            {"id": "FAIRY_TALE_ANIMAL_FOX"},
        ],
    }
    assert is_fairy_tale_context(runtime)
    assert has_folk_substyle(runtime)
    assert requires_vivid_fairy_tale(runtime)


def test_append_expressiveness_task_adds_folk_guidance():
    runtime = {
        "normalized_request_summary": {
            "truth_mode": "FAIRY_TALE",
            "substyle": "RUSSIAN_FOLK_TALE",
        },
        "ordered_layer_refs": [{"id": "RUSSIAN_FOLK_TALE"}, {"id": "FAIRY_TALE_ANIMAL_FOX"}],
    }
    task = append_expressiveness_task("Base task.", runtime, stage="generate_candidates")
    assert "flat moral-lesson" in task
    assert "RUSSIAN_FOLK_TALE" in task
    assert "шёл-шёл" in task


def test_append_expressiveness_task_skips_truth_mode():
    runtime = {
        "normalized_request_summary": {"truth_mode": "TRUTH"},
        "ordered_layer_refs": [{"id": "TRUTH_ANIMAL_FOX"}],
    }
    assert append_expressiveness_task("Base.", runtime, stage="generate_candidates") == "Base."
