from __future__ import annotations

from dataclasses import dataclass

from src.core.interpretation.style_llm_tail import (
    HeuristicStyleLlmTailProvider,
    StyleLlmTailProvider,
    pick_style_layer_with_llm_tail,
    verify_style_layer_pick,
)
from src.core.interpretation.style_phrases import StylePhrase, extract_style_phrases
from src.core.prompts.lookup import match_style_substyle_layers
from src.core.prompts.models import MetadataLookupCandidate
from src.core.prompts.registry import PromptRegistry

_AUTO_RESOLVE_SCORE = 0.90
_LLM_BAND_LOW_SCORE = 0.75
_AMBIGUITY_SCORE_DELTA = 0.05
_DEFAULT_LLM_TAIL_PROVIDER: StyleLlmTailProvider = HeuristicStyleLlmTailProvider()


@dataclass(frozen=True)
class StyleMatchOutcome:
    phrase: StylePhrase
    layer_id: str | None
    match_score: float
    match_level: str
    applicability_status: str
    resolved: bool
    is_hard_unsupported: bool
    is_applicability_conflict: bool
    used_llm_tail: bool = False


def resolve_style_from_text(
    registry: PromptRegistry,
    text: str,
    *,
    applicability: dict[str, str] | None = None,
    llm_tail_provider: StyleLlmTailProvider | None = _DEFAULT_LLM_TAIL_PROVIDER,
) -> StyleMatchOutcome | None:
    phrases = extract_style_phrases(text)
    if not phrases:
        return None

    best_resolved: StyleMatchOutcome | None = None
    for phrase in phrases:
        outcome = _resolve_phrase(
            registry,
            phrase,
            applicability=applicability,
            llm_tail_provider=llm_tail_provider,
        )
        if outcome.resolved and (
            best_resolved is None or outcome.match_score > best_resolved.match_score
        ):
            best_resolved = outcome
            continue
        if best_resolved is None and outcome.is_applicability_conflict:
            return outcome
        if best_resolved is None and outcome.is_hard_unsupported:
            return outcome

    return best_resolved


def _resolve_phrase(
    registry: PromptRegistry,
    phrase: StylePhrase,
    *,
    applicability: dict[str, str] | None,
    llm_tail_provider: StyleLlmTailProvider | None,
) -> StyleMatchOutcome:
    candidates = match_style_substyle_layers(
        registry,
        normalized_phrase=phrase.normalized,
        applicability=applicability,
    )
    if not candidates:
        return StyleMatchOutcome(
            phrase=phrase,
            layer_id=None,
            match_score=0.0,
            match_level="miss",
            applicability_status="unknown",
            resolved=False,
            is_hard_unsupported=phrase.is_hard_requirement,
            is_applicability_conflict=False,
        )

    applicable = [candidate for candidate in candidates if candidate.applicability_status == "applicable"]
    if not applicable:
        top = candidates[0]
        return StyleMatchOutcome(
            phrase=phrase,
            layer_id=top.layer_id,
            match_score=top.match_score,
            match_level=top.match_level,
            applicability_status=top.applicability_status,
            resolved=False,
            is_hard_unsupported=phrase.is_hard_requirement,
            is_applicability_conflict=True,
        )

    top = applicable[0]
    llm_outcome = _try_llm_tail_resolve(
        registry,
        phrase,
        applicable,
        top=top,
        applicability=applicability,
        llm_tail_provider=llm_tail_provider,
    )
    if llm_outcome is not None:
        return llm_outcome

    resolved = top.match_score >= _AUTO_RESOLVE_SCORE
    return StyleMatchOutcome(
        phrase=phrase,
        layer_id=top.layer_id if resolved else None,
        match_score=top.match_score,
        match_level=top.match_level,
        applicability_status=top.applicability_status,
        resolved=resolved,
        is_hard_unsupported=phrase.is_hard_requirement and not resolved and top.match_score < _LLM_BAND_LOW_SCORE,
        is_applicability_conflict=False,
    )


def _try_llm_tail_resolve(
    registry: PromptRegistry,
    phrase: StylePhrase,
    applicable: list[MetadataLookupCandidate],
    *,
    top: MetadataLookupCandidate,
    applicability: dict[str, str] | None,
    llm_tail_provider: StyleLlmTailProvider | None,
) -> StyleMatchOutcome | None:
    ambiguous = _is_ambiguous(applicable)
    in_llm_band = _LLM_BAND_LOW_SCORE <= top.match_score < _AUTO_RESOLVE_SCORE
    if not ambiguous and not in_llm_band:
        return None

    picked_layer_id = pick_style_layer_with_llm_tail(
        llm_tail_provider,
        phrase=phrase.raw,
        draft_params=dict(applicability or {}),
        candidates=applicable,
    )
    if not picked_layer_id or not verify_style_layer_pick(
        registry,
        picked_layer_id,
        normalized_phrase=phrase.normalized,
        applicability=applicability,
    ):
        return None

    picked = next(candidate for candidate in applicable if candidate.layer_id == picked_layer_id)
    return StyleMatchOutcome(
        phrase=phrase,
        layer_id=picked.layer_id,
        match_score=picked.match_score,
        match_level=picked.match_level,
        applicability_status=picked.applicability_status,
        resolved=True,
        is_hard_unsupported=False,
        is_applicability_conflict=False,
        used_llm_tail=True,
    )


def _is_ambiguous(applicable: list[MetadataLookupCandidate]) -> bool:
    if len(applicable) < 2:
        return False
    top, second = applicable[0], applicable[1]
    if second.match_score < _LLM_BAND_LOW_SCORE:
        return False
    return (top.match_score - second.match_score) < _AMBIGUITY_SCORE_DELTA
