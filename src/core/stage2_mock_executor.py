from __future__ import annotations

from typing import Any

REQUIRED_GATES = {
    "safety",
    "truth_fit",
    "age_fit",
    "utility_goal",
    "subject_continuity",
    "hard_details",
    "character_consistency",
}


class MockStage2TextExecutor:
    def generate_candidates(self, runtime_context: dict[str, Any], count: int) -> list[dict[str, Any]]:
        base = [
            ("Лиса ждёт зелёный", "Лиса остановилась у перехода и дождалась зелёного света."),
            ("Лиса смотрит по сторонам", "Перед дорогой лиса посмотрела налево и направо."),
            ("Лиса ждёт зелёный", "Лиса снова вспоминает про зелёный свет."),
        ]
        return [
            {
                "theme": theme,
                "text": text,
                "questions": ["Когда можно переходить дорогу?"],
                "utility_points": ["остановиться", "посмотреть по сторонам"],
                "used_subjects": ["fox"],
            }
            for theme, text in base[:count]
        ]

    def deduplicate_topics(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    def score_candidates(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "candidate_id": candidate["candidate_id"],
                "hard_gates": {gate: "pass" for gate in REQUIRED_GATES},
                "score_components": {"novelty": 0.8, "visual_potential": 0.8},
                "total_score": 0.9 - index * 0.05,
            }
            for index, candidate in enumerate(runtime_context["candidate_texts"])
        ]

    def validate_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        return {"status": "accepted", "summary": "ok", "issues": [], "required_fixes": []}

    def refine_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        candidate = runtime_context["candidate_text"]
        return {
            "theme": candidate["theme"],
            "text": candidate["text"],
            "questions": candidate.get("questions", []),
            "changes_summary": "Без изменений.",
        }
