from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.core.prompts.models import MetadataLookupCandidate
from src.core.prompts.registry import PromptRegistry


@dataclass(frozen=True)
class StyleLlmTailRequest:
    phrase: str
    draft_params: dict[str, str]
    candidates: tuple[MetadataLookupCandidate, ...]


class StyleLlmTailProvider(Protocol):
    def pick_style_layer_id(self, request: StyleLlmTailRequest) -> str | None: ...


class HeuristicStyleLlmTailProvider:
    """Deterministic tail: pick top candidate when fuzzy band winner is clear."""

    def pick_style_layer_id(self, request: StyleLlmTailRequest) -> str | None:
        if not request.candidates:
            return None
        top = request.candidates[0]
        if len(request.candidates) == 1:
            return top.layer_id
        second = request.candidates[1]
        if (top.match_score - second.match_score) >= 0.05:
            return top.layer_id
        return None


class NoOpStyleLlmTailProvider:
    def pick_style_layer_id(self, request: StyleLlmTailRequest) -> str | None:
        return None


class ScriptedStyleLlmTailProvider:
    """Deterministic provider for tests and scripted CI runs."""

    def __init__(self, *, responses: dict[str, str] | None = None) -> None:
        self._responses = responses or {}

    def pick_style_layer_id(self, request: StyleLlmTailRequest) -> str | None:
        for key, layer_id in self._responses.items():
            if key in request.phrase.casefold():
                return layer_id
        if request.candidates:
            return request.candidates[0].layer_id
        return None


def pick_style_layer_with_llm_tail(
    provider: StyleLlmTailProvider | None,
    *,
    phrase: str,
    draft_params: dict[str, str],
    candidates: list[MetadataLookupCandidate],
) -> str | None:
    if provider is None or not candidates:
        return None

    allowed_ids = {candidate.layer_id for candidate in candidates}
    picked = provider.pick_style_layer_id(
        StyleLlmTailRequest(
            phrase=phrase,
            draft_params=draft_params,
            candidates=tuple(candidates[:10]),
        )
    )
    if picked is None or picked == "NONE":
        return None
    if picked not in allowed_ids:
        return None
    return picked


def verify_style_layer_pick(
    registry: PromptRegistry,
    layer_id: str,
    *,
    normalized_phrase: str,
    applicability: dict[str, str] | None,
) -> bool:
    if layer_id not in registry.layers_by_id:
        return False
    layer = registry.get(layer_id)
    if layer.type not in {"style", "substyle"}:
        return False
    from src.core.prompts.lookup import match_style_substyle_layers

    candidates = match_style_substyle_layers(
        registry,
        normalized_phrase=normalized_phrase,
        applicability=applicability,
    )
    return any(
        candidate.layer_id == layer_id and candidate.applicability_status == "applicable"
        for candidate in candidates
    )
