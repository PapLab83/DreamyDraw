from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ComplexityProfile = Literal["strict", "moderate"]


@dataclass(frozen=True)
class AgeStoryLengthPolicy:
    sentences_min: int
    sentences_max: int
    complexity_profile: ComplexityProfile


DEFAULT_POLICY_AGE = "5"

AGE_STORY_LENGTH_POLICIES: dict[str, AgeStoryLengthPolicy] = {
    "3": AgeStoryLengthPolicy(sentences_min=3, sentences_max=4, complexity_profile="strict"),
    "5": AgeStoryLengthPolicy(sentences_min=3, sentences_max=5, complexity_profile="moderate"),
}


def get_length_policy(target_age: str | None) -> AgeStoryLengthPolicy:
    age = str(target_age or "").strip()
    if age in AGE_STORY_LENGTH_POLICIES:
        return AGE_STORY_LENGTH_POLICIES[age]
    return AGE_STORY_LENGTH_POLICIES[DEFAULT_POLICY_AGE]


def length_policy_payload(target_age: str | None) -> dict[str, str | int]:
    policy = get_length_policy(target_age)
    resolved_age = str(target_age or "").strip() or DEFAULT_POLICY_AGE
    if resolved_age not in AGE_STORY_LENGTH_POLICIES:
        resolved_age = DEFAULT_POLICY_AGE
    return {
        "target_age": resolved_age,
        "sentences_min": policy.sentences_min,
        "sentences_max": policy.sentences_max,
        "complexity_profile": policy.complexity_profile,
    }


def append_length_task(base: str, runtime_context: dict[str, Any] | None, *, stage: str) -> str:
    if not isinstance(runtime_context, dict):
        return base
    policy = runtime_context.get("length_policy")
    if not isinstance(policy, dict):
        return base

    sentences_min = policy.get("sentences_min")
    sentences_max = policy.get("sentences_max")
    complexity = policy.get("complexity_profile", "moderate")
    if not isinstance(sentences_min, int) or not isinstance(sentences_max, int):
        return base

    suffix_by_stage = {
        "generate_candidates": (
            f" Story text must contain {sentences_min}-{sentences_max} sentences. "
            f"Use age-appropriate {complexity} sentence complexity from the active age layer body. "
            "Simple wording must not mean bland list-like prose; vivid dialogue and concrete action "
            "within the sentence limit are encouraged. Questions are outside this limit."
        ),
        "score_candidates": (
            f" Fail age_fit when story text has fewer than {sentences_min} or more than "
            f"{sentences_max} sentences, or when sentences are too complex for target age."
        ),
        "validate_candidate": (
            f" Check story text sentence count is {sentences_min}-{sentences_max} using length_policy. "
            "Check sentence simplicity against the active age layer body in layer_grounding. "
            "Use issue types text_underlength, text_overlength, or sentence_too_complex when needed."
        ),
        "refine_candidate": (
            f" On text_overlength or text_underlength: adjust story text to "
            f"{sentences_min}-{sentences_max} sentences. "
            "On sentence_too_complex: shorten and simplify phrases. "
            "Preserve theme, subjects, hard details, direct speech, and folk/playful color when present."
        ),
    }
    suffix = suffix_by_stage.get(stage)
    if not suffix:
        return base
    return base + suffix
