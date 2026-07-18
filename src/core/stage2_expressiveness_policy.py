from __future__ import annotations

from typing import Any

DEFAULT_CANDIDATE_POOL_FLOOR = 20

_FOLK_SUBSTYLE_IDS = frozenset({"RUSSIAN_FOLK_TALE", "russian_folk_tale"})
_FAIRY_TALE_TRICKSTER_ENTITY_LAYERS = frozenset(
    {
        "FAIRY_TALE_ANIMAL_FOX",
        "FAIRY_TALE_ANIMAL_HARE",
        "FAIRY_TALE_ANIMAL_SQUIRREL",
        "FAIRY_TALE_ANIMAL_HEDGEHOG",
    }
)


def resolve_candidate_count(explicit: int | None, output_count: int | None) -> int:
    if explicit is not None:
        return explicit
    requested = max(1, int(output_count or 1))
    return max(DEFAULT_CANDIDATE_POOL_FLOOR, requested * 3)


def _summary(runtime_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(runtime_context, dict):
        return {}
    summary = runtime_context.get("normalized_request_summary")
    return summary if isinstance(summary, dict) else {}


def _layer_ids(runtime_context: dict[str, Any] | None) -> set[str]:
    if not isinstance(runtime_context, dict):
        return set()
    ids: set[str] = set()
    for ref in runtime_context.get("ordered_layer_refs", []):
        if isinstance(ref, dict) and ref.get("id"):
            ids.add(str(ref["id"]))
    prompt_context = runtime_context.get("prompt_context")
    if isinstance(prompt_context, dict):
        for layer_id in prompt_context.get("ordered_layer_ids", []):
            if layer_id:
                ids.add(str(layer_id))
    return ids


def is_fairy_tale_context(runtime_context: dict[str, Any] | None) -> bool:
    summary = _summary(runtime_context)
    return str(summary.get("truth_mode") or "").strip().upper() == "FAIRY_TALE"


def has_folk_substyle(runtime_context: dict[str, Any] | None) -> bool:
    summary = _summary(runtime_context)
    substyle = str(summary.get("substyle") or "").strip()
    if substyle in _FOLK_SUBSTYLE_IDS:
        return True
    return "RUSSIAN_FOLK_TALE" in _layer_ids(runtime_context)


def has_vivid_entity_layer(runtime_context: dict[str, Any] | None) -> bool:
    return bool(_FAIRY_TALE_TRICKSTER_ENTITY_LAYERS & _layer_ids(runtime_context))


def requires_vivid_fairy_tale(runtime_context: dict[str, Any] | None) -> bool:
    return is_fairy_tale_context(runtime_context) and (
        has_folk_substyle(runtime_context) or has_vivid_entity_layer(runtime_context)
    )


def append_expressiveness_task(base: str, runtime_context: dict[str, Any] | None, *, stage: str) -> str:
    if not requires_vivid_fairy_tale(runtime_context):
        return base

    folk = has_folk_substyle(runtime_context)
    suffix_by_stage = {
        "generate_candidates": (
            " FAIRY_TALE vividness: write lively fairy-tale drafts, not flat moral-lesson templates. "
            "Avoid generic plots like '<hero> helped a friend find X' or '<hero> taught everyone to share' "
            "when utility_mode is NARRATIVE. "
            "The main subject must show personality from entity/style layers (play, trickery, wonder, comic turns), "
            "not act as a neutral helper or lecturer. "
            "Age-simple wording is required, but keep direct speech, concrete images, and small playful conflict "
            "within length_policy."
            + (
                " RUSSIAN_FOLK_TALE: add folk cadence (жили-были, шёл-шёл, бежал-бежал), "
                "ласковые обращения, and at least one folk-colored line when length allows."
                if folk
                else ""
            )
        ),
        "score_candidates": (
            " For FAIRY_TALE with folk/entity vividness layers: lower child_interest and style_fit "
            "for flat helpful-lesson templates with no dialogue, no playful conflict, and no folk cadence "
            "when RUSSIAN_FOLK_TALE is active."
        ),
        "validate_candidate": (
            " For FAIRY_TALE with RUSSIAN_FOLK_TALE and/or vivid entity layers: use issue type "
            "flat_narrative or style_fit_weak (severity major) when the story is a generic "
            "helpful-lesson template with no direct speech, no playful conflict, and no folk cadence "
            "despite resolved style/entity layers."
        ),
        "refine_candidate": (
            " When fixing length or sentence complexity: preserve direct speech, folk repetitions, "
            "and playful turns. Compress connective narration first; do not replace vivid dialogue "
            "with flat summary sentences."
        ),
    }
    suffix = suffix_by_stage.get(stage)
    if not suffix:
        return base
    return base + suffix
