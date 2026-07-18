from __future__ import annotations

import json

from src.core.llm_temperature_policy import resolve_llm_temperature
from src.core.stage2_llm_executor import LLMStage2TextExecutor
from src.providers.base import BaseLLMProvider


def test_resolve_llm_temperature_per_stage():
    assert resolve_llm_temperature("candidate_text_generator") == 0.9
    assert resolve_llm_temperature("topic_deduplicator") == 0.2
    assert resolve_llm_temperature("scorer") == 0.2
    assert resolve_llm_temperature("candidate_validator") == 0.2
    assert resolve_llm_temperature("candidate_refiner") == 0.5


def test_resolve_llm_temperature_unknown_stage_uses_default():
    assert resolve_llm_temperature("unknown_stage") == 0.7


class TemperatureTrackingProvider(BaseLLMProvider):
    def __init__(self) -> None:
        self.temperatures: list[float | None] = []

    def generate_text(self, prompt: str, *, temperature: float | None = None) -> str:
        self.temperatures.append(temperature)
        if len(self.temperatures) == 1:
            return json.dumps({"candidates": [{"theme": "T", "text": "Body"}]})
        if len(self.temperatures) == 2:
            return json.dumps({"decisions": []})
        if len(self.temperatures) == 3:
            return json.dumps(
                {
                    "scores": [
                        {
                            "candidate_id": "c01",
                            "hard_gates": {
                                "safety": "pass",
                                "truth_fit": "pass",
                                "age_fit": "pass",
                                "utility_goal": "pass",
                                "subject_continuity": "pass",
                                "hard_details": "pass",
                                "character_consistency": "pass",
                            },
                            "score_components": {"novelty": 0.5},
                            "total_score": 0.5,
                        }
                    ]
                }
            )
        if len(self.temperatures) == 4:
            return json.dumps({"status": "accepted", "summary": "ok", "issues": [], "required_fixes": []})
        return json.dumps({"theme": "T", "text": "Body", "questions": [], "changes_summary": "ok"})

    def generate_questions(self, text: str) -> list[str]:
        raise AssertionError("Stage 2 executor must not call generate_questions")


def test_executor_passes_stage_temperature_to_provider():
    provider = TemperatureTrackingProvider()
    executor = LLMStage2TextExecutor(provider)

    executor.generate_candidates({"stage": "candidate_text_generator"}, count=1)
    executor.deduplicate_topics({"candidate_texts": [{"candidate_id": "c01", "theme": "T", "text": "Body"}]})
    executor.score_candidates({"candidate_texts": [{"candidate_id": "c01", "theme": "T", "text": "Body"}]})
    executor.validate_candidate({"stage": "candidate_validator"})
    executor.refine_candidate({"candidate_text": {"theme": "T", "text": "Body"}})

    assert provider.temperatures == [0.9, 0.2, 0.2, 0.2, 0.5]
