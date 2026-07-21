from __future__ import annotations

from typing import Any

from src.core.generation_config import effective_current_config
from src.models.schemas import GenerationRequest, SessionRequest


def to_session_request(
    request: SessionRequest | GenerationRequest | str,
    current_config: dict[str, Any] | None = None,
) -> SessionRequest:
    """Convert public compatibility inputs into the Stage 1-2 request model."""
    override_config = dict(current_config or {})

    if isinstance(request, SessionRequest):
        merged_config = {**request.current_config, **override_config}
        return request.model_copy(update={"current_config": effective_current_config(merged_config)})

    if isinstance(request, str):
        return SessionRequest(raw_text=request, current_config=effective_current_config(override_config))

    if isinstance(request, GenerationRequest):
        legacy_config = {
            **override_config,
            "count": request.count,
            "truth_mode": request.truth_mode.name,
            "text_style": request.text_style.name,
            "image_style": request.image_style.name,
            "work_mode": request.work_mode.value,
        }
        return SessionRequest(raw_text=request.topic, current_config=effective_current_config(legacy_config))

    raise TypeError(f"Unsupported request type: {type(request).__name__}")
