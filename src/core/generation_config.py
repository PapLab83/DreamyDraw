from __future__ import annotations

from enum import Enum
from typing import Any

from src.models.schemas import ControlledGenerationConfig, TruthMode

CONTROLLED_CONFIG_KEYS = {
    "output_count",
    "count",
    "target_age",
    "age",
    "truth_mode",
    "cultural_context",
    "utility_mode",
}


def resolve_controlled_generation_config(
    current_config: dict[str, Any] | None,
) -> ControlledGenerationConfig:
    raw = dict(current_config or {})
    payload: dict[str, Any] = {}

    if "output_count" in raw or "count" in raw:
        payload["output_count"] = raw.get("output_count", raw.get("count"))
    if "target_age" in raw or "age" in raw:
        payload["target_age"] = str(raw.get("target_age", raw.get("age")))
    if "truth_mode" in raw:
        value = raw["truth_mode"]
        payload["truth_mode"] = value.name if isinstance(value, TruthMode) else _enum_or_text(value)
    if "cultural_context" in raw:
        payload["cultural_context"] = _enum_or_text(raw["cultural_context"])
    if "utility_mode" in raw:
        payload["utility_mode"] = _enum_or_text(raw["utility_mode"])

    return ControlledGenerationConfig.model_validate(payload)


def effective_current_config(current_config: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(current_config or {})
    effective = {
        key: value
        for key, value in raw.items()
        if key not in CONTROLLED_CONFIG_KEYS
    }
    controlled = resolve_controlled_generation_config(raw)
    effective.update(controlled.model_dump(mode="json"))
    return effective


def _enum_or_text(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value).upper()
    return str(value).upper()
