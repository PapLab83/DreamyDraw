from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.core.stage2_llm_executor import LLMStage2TextExecutor, REQUIRED_HARD_GATES, _layer_grounding
from src.providers.base import BaseLLMProvider


class ScriptedLLMProvider(BaseLLMProvider):
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.prompts: list[str] = []

    def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.responses:
            raise AssertionError("Unexpected provider call")
        return self.responses.pop(0)

    def generate_questions(self, text: str) -> list[str]:
        raise AssertionError("Stage 2 executor must not call generate_questions")


def test_build_prompt_includes_layer_grounding() -> None:
    provider = ScriptedLLMProvider([json.dumps({"candidates": [{"theme": "Тема", "text": "Текст"}]})])
    executor = LLMStage2TextExecutor(provider)

    executor.generate_candidates(_runtime_context_with_grounding(), count=1)

    prompt = provider.prompts[0]
    assert '"layer_grounding"' in prompt
    assert "TRUTH_BASE" in prompt
    assert "Не изображать животных говорящими" in prompt
    assert '"metadata_constraints"' in prompt
    assert '"include_bodies_runtime"' in prompt


def test_layer_grounding_omits_empty_blocks() -> None:
    assert _layer_grounding({}) == {}
    assert _layer_grounding({"metadata_constraints": {}, "bodies": {}}) == {}


def test_generate_candidates_parses_fenced_json_and_limits_count() -> None:
    provider = ScriptedLLMProvider(
        [
            """```json
            {
              "candidates": [
                {"theme": "Лиса и мост", "text": "Лиса спокойно перешла мост.", "questions": ["Что сделала лиса?"], "utility_points": ["спокойствие"], "used_subjects": ["fox"], "expected_visual_idea": "мост"},
                {"theme": "", "text": "invalid"},
                {"theme": "Лиса и фонарь", "text": "Лиса дождалась света.", "questions": "bad"},
                {"theme": "Лиса лишняя", "text": "Не должна попасть в результат."}
              ]
            }
            ```"""
        ]
    )
    executor = LLMStage2TextExecutor(provider, model_name="unit-model")

    result = executor.generate_candidates(_runtime_context(), count=2)

    assert result == [
        {
            "theme": "Лиса и мост",
            "text": "Лиса спокойно перешла мост.",
            "questions": ["Что сделала лиса?"],
            "utility_points": ["спокойствие"],
            "used_subjects": ["fox"],
            "expected_visual_idea": "мост",
        },
        {
            "theme": "Лиса и фонарь",
            "text": "Лиса дождалась света.",
            "questions": [],
            "utility_points": [],
            "used_subjects": [],
            "expected_visual_idea": None,
        },
    ]
    assert executor.llm_call_count == 1
    assert executor.parse_failure_count == 0
    _assert_no_stage3_words(provider.prompts[0])
    assert '"json_contract":' not in provider.prompts[0]
    assert "top-level key" in provider.prompts[0]


def test_generate_candidates_invalid_json_returns_empty_list() -> None:
    provider = ScriptedLLMProvider(["not-json"])
    executor = LLMStage2TextExecutor(provider, max_retries=0)

    assert executor.generate_candidates(_runtime_context(), count=2) == []
    assert executor.parse_failure_count == 1


def test_deduplicate_topics_ignores_unknown_candidate_ids() -> None:
    provider = ScriptedLLMProvider(
        [
            json.dumps(
                {
                    "decisions": [
                        {"candidate_id": "c01", "is_duplicate": False, "duplicate_of": None, "reason": "unique"},
                        {"candidate_id": "missing", "is_duplicate": True, "duplicate_of": "c01", "reason": "bad id"},
                    ]
                }
            )
        ]
    )
    executor = LLMStage2TextExecutor(provider, max_retries=0)

    result = executor.deduplicate_topics(_runtime_context())

    assert result == [{"candidate_id": "c01", "is_duplicate": False, "duplicate_of": None, "reason": "unique"}]
    assert executor.llm_call_count == 1


def test_score_candidates_clamps_scores_and_requires_hard_gates() -> None:
    gates = {gate: "pass" for gate in REQUIRED_HARD_GATES}
    gates["safety"] = "weird"
    provider = ScriptedLLMProvider(
        [
            json.dumps(
                {
                    "scores": [
                        {
                            "candidate_id": "c01",
                            "hard_gates": gates,
                            "score_components": {"novelty": 1.7, "age_fit": -0.2},
                            "total_score": 2.3,
                        },
                        {
                            "candidate_id": "unknown",
                            "hard_gates": {gate: "pass" for gate in REQUIRED_HARD_GATES},
                            "score_components": {},
                            "total_score": 0.5,
                        },
                    ]
                }
            )
        ]
    )
    executor = LLMStage2TextExecutor(provider, max_retries=0)

    result = executor.score_candidates(_runtime_context())

    assert result == [
        {
            "candidate_id": "c01",
            "hard_gates": {**{gate: "pass" for gate in REQUIRED_HARD_GATES}, "safety": "unknown"},
            "score_components": {"novelty": 1.0, "age_fit": 0.0},
            "total_score": 1.0,
        }
    ]


def test_debug_artifacts_capture_raw_scorer_response_and_rejection_reason(tmp_path: Path) -> None:
    provider = ScriptedLLMProvider(
        [
            json.dumps(
                {
                    "scores": [
                        {
                            "candidate_id": "not-c01",
                            "hard_gates": {gate: "pass" for gate in REQUIRED_HARD_GATES},
                            "score_components": {"novelty": 0.8},
                            "total_score": 0.8,
                        }
                    ]
                }
            )
        ]
    )
    executor = LLMStage2TextExecutor(provider, max_retries=0, debug_artifact_dir=tmp_path)

    result = executor.score_candidates(_runtime_context())

    assert result == []
    artifacts = list(tmp_path.glob("*.json"))
    assert len(artifacts) == 1
    artifact = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert artifact["stage"] == "scorer"
    assert artifact["status"] == "completed"
    assert artifact["raw_response"]
    assert artifact["diagnostics"]["raw_items"] == 1
    assert artifact["diagnostics"]["valid_items"] == 0
    assert artifact["diagnostics"]["rejected_items"][0]["reason"] == "unknown_candidate_id"


def test_validate_candidate_parse_failure_is_not_accepted() -> None:
    provider = ScriptedLLMProvider(["nope"])
    executor = LLMStage2TextExecutor(provider, max_retries=0)

    result = executor.validate_candidate(_runtime_context())

    assert result["status"] == "rejected"
    assert result["issues"][0]["type"] == "safety"
    assert result["issues"][0]["severity"] == "critical"
    assert executor.parse_failure_count == 1


def test_validate_candidate_never_accepts_critical_issues() -> None:
    provider = ScriptedLLMProvider(
        [
            json.dumps(
                {
                    "status": "accepted",
                    "summary": "has issue",
                    "issues": [{"type": "age_fit", "severity": "critical", "description": "too complex"}],
                    "required_fixes": ["simplify"],
                }
            )
        ]
    )
    executor = LLMStage2TextExecutor(provider)

    result = executor.validate_candidate(_runtime_context())

    assert result["status"] == "needs_revision"


@pytest.mark.parametrize("issue_type", ["safety", "truth_fit"])
def test_validate_candidate_never_accepts_major_issues(issue_type: str) -> None:
    provider = ScriptedLLMProvider(
        [
            json.dumps(
                {
                    "status": "accepted",
                    "summary": "has major issue",
                    "issues": [{"type": issue_type, "severity": "major", "description": "must not approve"}],
                    "required_fixes": ["fix issue"],
                }
            )
        ]
    )
    executor = LLMStage2TextExecutor(provider)

    result = executor.validate_candidate(_runtime_context())

    assert result["status"] == "needs_revision"


def test_refine_candidate_parse_failure_preserves_original_text() -> None:
    provider = ScriptedLLMProvider(["not-json"])
    executor = LLMStage2TextExecutor(provider, max_retries=0)

    result = executor.refine_candidate(_runtime_context())

    assert result["theme"] == "Лиса и мост"
    assert result["text"] == "Лиса спокойно перешла мост."
    assert result["questions"] == ["Что сделала лиса?"]
    assert "parse" in result["changes_summary"].casefold()


@pytest.mark.parametrize(
    "method_name",
    [
        "generate_candidates",
        "deduplicate_topics",
        "score_candidates",
        "validate_candidate",
        "refine_candidate",
    ],
)
def test_each_method_makes_one_provider_call(method_name: str) -> None:
    provider = ScriptedLLMProvider([_valid_response_for(method_name)])
    executor = LLMStage2TextExecutor(provider)
    args = (_runtime_context(), 2) if method_name == "generate_candidates" else (_runtime_context(),)

    getattr(executor, method_name)(*args)

    assert len(provider.prompts) == 1


def _valid_response_for(method_name: str) -> str:
    if method_name == "generate_candidates":
        return json.dumps({"candidates": [{"theme": "Тема", "text": "Текст"}]})
    if method_name == "deduplicate_topics":
        return json.dumps({"decisions": [{"candidate_id": "c01", "is_duplicate": False, "duplicate_of": None, "reason": "unique"}]})
    if method_name == "score_candidates":
        return json.dumps(
            {
                "scores": [
                    {
                        "candidate_id": "c01",
                        "hard_gates": {gate: "pass" for gate in REQUIRED_HARD_GATES},
                        "score_components": {"novelty": 0.5},
                        "total_score": 0.5,
                    }
                ]
            }
        )
    if method_name == "validate_candidate":
        return json.dumps({"status": "accepted", "summary": "ok", "issues": [], "required_fixes": []})
    if method_name == "refine_candidate":
        return json.dumps({"theme": "Тема", "text": "Текст", "questions": [], "changes_summary": "ok"})
    raise AssertionError(method_name)


def _runtime_context_with_grounding() -> dict:
    return {
        **_runtime_context(),
        "body_policy": "include_bodies_runtime",
        "metadata_constraints": {
            "TRUTH_BASE": {
                "short_description": "Базовые правила реального мира",
                "constraints": ["Не изображать животных говорящими"],
            }
        },
        "bodies": {
            "TRUTH_BASE": "# Назначение слоя\n\nНе изображать животных говорящими.",
        },
    }


def _runtime_context() -> dict:
    return {
        "stage": "candidate_text_generator",
        "normalized_request_summary": {
            "truth_mode": "fairy_tale",
            "utility_mode": "narrative",
            "target_age": "5",
            "main_subject": "fox",
            "output_count": 2,
        },
        "ordered_layer_refs": [{"id": "truth_modes/FAIRY_TALE/BASE"}],
        "fallback_layer_refs": [],
        "unresolved_details": [],
        "stage_instructions": ["Use age-safe text."],
        "context_blocks": [{"id": "age/5", "summary": "short sentences"}],
        "hard_details": ["без страшных сцен"],
        "soft_preferences": ["добрый тон"],
        "candidate_texts": [
            {"candidate_id": "c01", "theme": "Лиса и мост", "text": "Лиса спокойно перешла мост."},
            {"candidate_id": "c02", "theme": "Лиса и фонарь", "text": "Лиса дождалась света."},
        ],
        "candidate_text": {
            "candidate_id": "c01",
            "theme": "Лиса и мост",
            "text": "Лиса спокойно перешла мост.",
            "questions": ["Что сделала лиса?"],
        },
        "validator_issues": [{"type": "age_fit", "severity": "major", "description": "too long"}],
        "required_fixes": ["shorten"],
    }


def _assert_no_stage3_words(prompt: str) -> None:
    lowered = prompt.casefold()
    for forbidden in ("image generation", "animation", "stage 3", "generate_image"):
        assert forbidden not in lowered
