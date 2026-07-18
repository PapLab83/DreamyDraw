from __future__ import annotations

from src.config.settings import settings

STAGE2_LLM_STAGES = (
    "candidate_text_generator",
    "topic_deduplicator",
    "scorer",
    "candidate_validator",
    "candidate_refiner",
)


def resolve_llm_temperature(stage: str) -> float:
    """Return LLM temperature for a Stage 2 executor stage."""
    key = str(stage).strip()
    attr_by_stage = {
        "candidate_text_generator": "LLM_TEMPERATURE_GENERATE_CANDIDATES",
        "topic_deduplicator": "LLM_TEMPERATURE_DEDUPLICATE_TOPICS",
        "scorer": "LLM_TEMPERATURE_SCORE_CANDIDATES",
        "candidate_validator": "LLM_TEMPERATURE_VALIDATE_CANDIDATE",
        "candidate_refiner": "LLM_TEMPERATURE_REFINE_CANDIDATE",
    }
    attr = attr_by_stage.get(key)
    if attr is None:
        return float(settings.LLM_TEMPERATURE_DEFAULT)
    return float(getattr(settings, attr))
