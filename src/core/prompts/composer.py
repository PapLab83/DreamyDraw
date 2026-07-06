from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from src.core.prompts.models import StagePromptContextBuild
from src.core.prompts.registry import PromptRegistry
from src.core.stage2_length_policy import length_policy_payload
from src.models.schemas import (
    ExecutionPromptContext,
    NormalizedRequest,
    StagePromptContextEntry,
)

BodyPolicy = str


_BODY_POLICIES = {"lazy_not_persisted", "metadata_only", "include_bodies_runtime"}

_STAGE_LAYER_ROLE_BY_STAGE = {
    "candidate_text_generator": "candidate_text_generator",
    "topic_deduplicator": "topic_deduplicator",
    "scorer": "scorer",
    "ranker": "ranker",
    "approved_text_selector": "approved_text_selector",
}

_VALIDATOR_LAYER_ROLE_BY_STAGE = {
    "candidate_validator": "candidate_validator",
}

_REFINER_LAYER_ROLE_BY_STAGE = {
    "candidate_refiner": "candidate_refiner",
}

_PROFILE_LAYER_GROUPS = {
    "candidate_text_generator": (
        "format",
        "truth_mode",
        "utility_mode",
        "utility_topic",
        "age",
        "audience_language",
        "result_language",
        "style",
        "entity",
    ),
    "topic_deduplicator": (
        "utility_mode",
        "utility_topic",
        "entity",
    ),
    "scorer": (
        "format",
        "truth_mode",
        "utility_mode",
        "utility_topic",
        "age",
        "audience_language",
        "result_language",
        "style",
        "entity",
    ),
    "ranker": (),
    "candidate_validator": (
        "format",
        "truth_mode",
        "utility_mode",
        "utility_topic",
        "age",
        "audience_language",
        "result_language",
        "style",
        "entity",
    ),
    "candidate_refiner": (
        "format",
        "truth_mode",
        "utility_mode",
        "utility_topic",
        "age",
        "audience_language",
        "result_language",
        "style",
        "entity",
    ),
    "approved_text_selector": (),
}

_ORDERED_GROUPS = (
    "format",
    "truth_mode",
    "utility_mode",
    "utility_topic",
    "age",
    "audience_language",
    "result_language",
    "style",
    "entity",
)

_HARD_GATES = [
    "safety",
    "truth_fit",
    "age_fit",
    "utility_goal",
    "subject_continuity",
    "hard_details",
    "character_consistency",
]

_REFINER_IMMUTABLE_FIELDS = [
    "candidate_id",
    "source_version_id",
    "theme",
    "content_format",
    "truth_mode",
    "utility_mode",
    "utility_topic",
    "target_age",
    "audience_language",
    "result_language",
    "main_subject",
    "required_subjects",
    "subject_continuity_policy",
    "character_profile",
    "hard_details",
]


class PromptComposer:
    def __init__(self, registry: PromptRegistry) -> None:
        self.registry = registry

    def build_stage_context(
        self,
        *,
        normalized_request: NormalizedRequest,
        prompt_context: ExecutionPromptContext,
        stage: str,
        candidate_id: str | None = None,
        version_id: str | None = None,
        attempt: int | None = None,
        stage_inputs: dict[str, Any] | None = None,
        body_policy: BodyPolicy = "lazy_not_persisted",
    ) -> StagePromptContextBuild:
        if body_policy not in _BODY_POLICIES:
            raise ValueError(f"Unsupported body policy: {body_policy}")
        if stage not in _PROFILE_LAYER_GROUPS:
            raise ValueError(f"Unsupported stage: {stage}")

        dynamic_stage = stage in {"candidate_validator", "candidate_refiner"}
        if dynamic_stage and (candidate_id is None or version_id is None or attempt is None):
            raise ValueError(
                f"{stage} requires candidate_id, version_id and attempt."
            )
        if not dynamic_stage and (
            candidate_id is not None or version_id is not None or attempt is not None
        ):
            raise ValueError(f"{stage} does not accept candidate identity.")

        selected_refs = self._ordered_layer_refs(prompt_context, stage)
        fallback_refs = self._fallback_refs(prompt_context, stage)
        unresolved_details = [
            _model_to_plain(detail) for detail in prompt_context.unresolved_details
        ]
        source_hash = self._source_prompt_context_hash(prompt_context)
        stage_input_summary = self._stage_inputs_summary(
            stage=stage,
            normalized_request=normalized_request,
            stage_inputs=stage_inputs or {},
            candidate_id=candidate_id,
            version_id=version_id,
            attempt=attempt,
        )

        metadata_constraints = {
            ref["id"]: {
                "short_description": self.registry.get(ref["id"]).short_description,
                "constraints": list(self.registry.get(ref["id"]).constraints),
                "source_hash": self.registry.get(ref["id"]).source_hash,
                "metadata_hash": self.registry.get(ref["id"]).metadata_hash,
                "body_hash": self.registry.get(ref["id"]).body_hash,
            }
            for ref in selected_refs
        }
        runtime_context: dict[str, Any] = {
            "stage": stage,
            "candidate_id": candidate_id,
            "version_id": version_id,
            "attempt": attempt,
            "body_policy": body_policy,
            "source_prompt_context_hash": source_hash,
            "ordered_layer_refs": selected_refs,
            "fallback_layer_refs": fallback_refs,
            "metadata_constraints": metadata_constraints,
            "normalized_request_summary": self._normalized_request_summary(
                normalized_request
            ),
            "length_policy": length_policy_payload(normalized_request.target_age),
            "hard_details": list(normalized_request.hard_details),
            "soft_preferences": list(normalized_request.soft_preferences),
            "unresolved_details": unresolved_details,
            "context_blocks": self._context_blocks(stage, unresolved_details),
            "stage_instructions": self._stage_instructions(stage),
            "output_contract_summary": self._output_contract_summary(stage),
            "stage_inputs_summary": stage_input_summary,
            "trace_refs": {
                "registry_hash": self.registry.registry_hash,
                "layer_source_hashes": {
                    ref["id"]: self.registry.get(ref["id"]).source_hash
                    for ref in selected_refs
                },
            },
        }

        if body_policy == "include_bodies_runtime":
            runtime_context["bodies"] = {
                layer_id: self.registry.get_body(layer_id)
                for layer_id in _dedupe(
                    [ref["id"] for ref in selected_refs]
                    + [ref["fallback_layer_id"] for ref in fallback_refs]
                )
            }

        hash_payload = {
            "stage": stage,
            "candidate_id": candidate_id,
            "version_id": version_id,
            "attempt": attempt,
            "source_prompt_context_hash": source_hash,
            "layer_refs": self._hashable_layer_refs(selected_refs),
            "fallback_refs": self._hashable_fallback_refs(fallback_refs),
            "unresolved_details": unresolved_details,
            "hard_details": list(normalized_request.hard_details),
            "soft_preferences": list(normalized_request.soft_preferences),
            "normalized_request_summary": runtime_context["normalized_request_summary"],
            "stage_inputs_summary": stage_input_summary,
            "body_policy": body_policy,
        }
        stage_context_hash = _stable_hash(hash_payload)
        runtime_context["stage_context_hash"] = stage_context_hash

        durable_entry = StagePromptContextEntry(
            stage=stage,
            candidate_id=candidate_id,
            version_id=version_id,
            attempt=attempt,
            source_prompt_context_hash=source_hash,
            stage_context_hash=stage_context_hash,
            layer_ids=[ref["id"] for ref in selected_refs],
            fallback_layer_ids=[ref["fallback_layer_id"] for ref in fallback_refs],
            unresolved_detail_labels=[
                str(detail.get("label")) for detail in unresolved_details
            ],
            body_policy=body_policy,
            context_summary=self._context_summary(
                stage=stage,
                selected_refs=selected_refs,
                fallback_refs=fallback_refs,
                unresolved_details=unresolved_details,
                stage_input_summary=stage_input_summary,
            ),
            created_at=datetime.now(UTC).isoformat(),
            version=1,
        )
        return StagePromptContextBuild(
            durable_entry=durable_entry,
            runtime_context=runtime_context,
        )

    def _ordered_layer_refs(
        self,
        prompt_context: ExecutionPromptContext,
        stage: str,
    ) -> list[dict[str, Any]]:
        required_groups = set(_PROFILE_LAYER_GROUPS[stage])
        selected: list[dict[str, Any]] = []
        refs = [_model_to_plain(ref) for ref in prompt_context.resolved_layers]

        for group in _ORDERED_GROUPS:
            if group not in required_groups:
                continue
            for ref in refs:
                if self._layer_group(ref) == group:
                    selected.append(self._enriched_ref(ref))

        selected.extend(self._stage_specific_refs(stage))
        return _dedupe_refs(selected)

    def _stage_specific_refs(self, stage: str) -> list[dict[str, Any]]:
        role = (
            _STAGE_LAYER_ROLE_BY_STAGE.get(stage)
            or _VALIDATOR_LAYER_ROLE_BY_STAGE.get(stage)
            or _REFINER_LAYER_ROLE_BY_STAGE.get(stage)
        )
        if not role:
            return []
        layer_ids = self.registry.by_role.get(role, [])
        return [self._enriched_ref({"id": layer_id}) for layer_id in layer_ids]

    def _fallback_refs(
        self,
        prompt_context: ExecutionPromptContext,
        stage: str,
    ) -> list[dict[str, Any]]:
        required_groups = set(_PROFILE_LAYER_GROUPS[stage])
        fallback_refs: list[dict[str, Any]] = []
        for fallback in prompt_context.fallback_layers:
            ref = _model_to_plain(fallback)
            fallback_id = ref.get("fallback_layer_id")
            if fallback_id is None:
                continue
            layer = self.registry.get(str(fallback_id))
            if self._layer_group(
                {"type": layer.type, "role": layer.role}
            ) in required_groups:
                fallback_refs.append(self._enriched_fallback_ref(ref))
        return _dedupe_fallback_refs(fallback_refs)

    def _layer_group(self, ref: dict[str, Any]) -> str:
        role = ref.get("role")
        type_ = ref.get("type")
        if role == "content_format":
            return "format"
        if role == "utility_mode":
            return "utility_mode"
        if role == "utility_topic":
            return "utility_topic"
        if role == "audience_language":
            return "audience_language"
        if role == "result_language":
            return "result_language"
        if type_ == "format":
            return "format"
        if type_ == "truth_mode":
            return "truth_mode"
        if type_ == "age":
            return "age"
        if type_ in {"style", "substyle"}:
            return "style"
        if type_ == "entity":
            return "entity"
        return str(type_ or "")

    def _enriched_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        layer = self.registry.get(str(ref["id"]))
        return {
            "id": layer.id,
            "type": layer.type,
            "role": layer.role,
            "source": layer.source,
            "reason": ref.get("reason"),
            "source_hash": layer.source_hash,
            "metadata_hash": layer.metadata_hash,
            "body_hash": layer.body_hash,
            "short_description": layer.short_description,
        }

    def _enriched_fallback_ref(self, ref: dict[str, Any]) -> dict[str, Any]:
        layer = self.registry.get(str(ref["fallback_layer_id"]))
        return {
            "requested": ref.get("requested"),
            "fallback_layer_id": layer.id,
            "source": layer.source,
            "reason": ref.get("reason"),
            "source_hash": layer.source_hash,
            "metadata_hash": layer.metadata_hash,
            "body_hash": layer.body_hash,
            "short_description": layer.short_description,
        }

    def _source_prompt_context_hash(
        self,
        prompt_context: ExecutionPromptContext,
    ) -> str:
        if prompt_context.snapshot_hash:
            return prompt_context.snapshot_hash
        if prompt_context.source_hash:
            return prompt_context.source_hash
        return _stable_hash(
            {
                "resolved_layers": [
                    self._enriched_ref(_model_to_plain(ref))
                    for ref in prompt_context.resolved_layers
                ],
                "fallback_layers": [
                    self._enriched_fallback_ref(_model_to_plain(ref))
                    for ref in prompt_context.fallback_layers
                ],
                "unresolved_details": [
                    _model_to_plain(detail)
                    for detail in prompt_context.unresolved_details
                ],
                "version": prompt_context.version,
            }
        )

    def _normalized_request_summary(
        self,
        normalized_request: NormalizedRequest,
    ) -> dict[str, Any]:
        return {
            "content_format": normalized_request.content_format,
            "truth_mode": normalized_request.truth_mode,
            "utility_mode": normalized_request.utility_mode,
            "utility_topic": normalized_request.utility_topic,
            "target_age": normalized_request.target_age,
            "output_count": normalized_request.output_count,
            "audience_language": normalized_request.audience_language,
            "result_language": normalized_request.result_language,
            "main_subject": normalized_request.main_subject,
            "subjects": [
                {
                    "id": subject.id,
                    "label": subject.label,
                    "type": subject.type,
                    "role": subject.role,
                    "is_character": subject.is_character,
                    "resolved_layer_id": subject.resolved_layer_id,
                    "unresolved_detail": subject.unresolved_detail,
                }
                for subject in normalized_request.subjects
            ],
            "text_style_base": normalized_request.text_style_base,
            "substyle": normalized_request.substyle,
            "character_profile": _model_to_plain(
                normalized_request.character_profile
            ),
            "subject_continuity_policy": _model_to_plain(
                normalized_request.subject_continuity_policy
            ),
        }

    def _stage_inputs_summary(
        self,
        *,
        stage: str,
        normalized_request: NormalizedRequest,
        stage_inputs: dict[str, Any],
        candidate_id: str | None,
        version_id: str | None,
        attempt: int | None,
    ) -> dict[str, Any]:
        if stage == "topic_deduplicator":
            themes = stage_inputs.get("candidate_themes")
            candidate_texts = stage_inputs.get("candidate_texts", [])
            return {
                "candidate_themes_count": len(themes or []),
                "candidate_texts_count": len(candidate_texts),
                "candidate_themes_hash": _stable_hash(themes or []),
                "candidate_texts_hash": _stable_hash(candidate_texts),
                "utility_mode": normalized_request.utility_mode,
                "utility_topic": normalized_request.utility_topic,
                "subject_count": len(normalized_request.subjects),
                "subject_continuity_policy": _model_to_plain(
                    normalized_request.subject_continuity_policy
                ),
            }
        if stage == "scorer":
            candidate_texts = stage_inputs.get("candidate_texts", [])
            return {
                "candidate_texts_count": len(candidate_texts),
                "candidate_texts_hash": _stable_hash(candidate_texts),
                "score_components": [
                    "child_interest",
                    "age_fit",
                    "utility_fit",
                    "style_fit",
                    "novelty",
                    "visual_potential",
                ],
                "hard_gates": _HARD_GATES,
            }
        if stage == "ranker":
            return {
                "scores_count": len(stage_inputs.get("scores", [])),
                "scores_hash": _stable_hash(stage_inputs.get("scores", [])),
                "ranking_policy": "hard_gates_first_total_score_desc",
            }
        if stage == "candidate_validator":
            return {
                "candidate_id": candidate_id,
                "version_id": version_id,
                "attempt": attempt,
                "candidate_text_hash": _stable_hash(
                    stage_inputs.get("candidate_text", {})
                ),
                "validation_criteria": stage_inputs.get(
                    "validation_criteria",
                    "canonical_stage_2_validation",
                ),
            }
        if stage == "candidate_refiner":
            candidate_text = stage_inputs.get("candidate_text", {})
            return {
                "candidate_id": candidate_id,
                "version_id": version_id,
                "attempt": attempt,
                "candidate_text_hash": _stable_hash(
                    candidate_text
                ),
                "validator_issues_count": len(
                    stage_inputs.get("validator_issues", [])
                ),
                "required_fixes_count": len(stage_inputs.get("required_fixes", [])),
                "validator_issues_hash": _stable_hash(
                    stage_inputs.get("validator_issues", [])
                ),
                "required_fixes_hash": _stable_hash(
                    stage_inputs.get("required_fixes", [])
                ),
                "immutable_fields": stage_inputs.get(
                    "immutable_fields",
                    _REFINER_IMMUTABLE_FIELDS,
                ),
                "immutable_snapshot": self._refiner_immutable_snapshot(
                    normalized_request=normalized_request,
                    candidate_text=candidate_text,
                    candidate_id=candidate_id,
                    version_id=version_id,
                ),
            }
        if stage == "approved_text_selector":
            return {
                "ranked_candidates_count": len(
                    stage_inputs.get("ranked_candidates", [])
                ),
                "ranked_candidates_hash": _stable_hash(
                    stage_inputs.get("ranked_candidates", [])
                ),
                "validated_versions_count": len(
                    stage_inputs.get("validated_versions", [])
                ),
                "validated_versions_hash": _stable_hash(
                    stage_inputs.get("validated_versions", [])
                ),
                "validation_summaries_count": len(
                    stage_inputs.get("validation_summaries", [])
                ),
                "validation_summaries_hash": _stable_hash(
                    stage_inputs.get("validation_summaries", [])
                ),
                "output_count": normalized_request.output_count,
                "shortage_policy": stage_inputs.get(
                    "shortage_policy",
                    "normal_approved_only_then_shortage",
                ),
            }
        return {"output_count": normalized_request.output_count}

    def _refiner_immutable_snapshot(
        self,
        *,
        normalized_request: NormalizedRequest,
        candidate_text: dict[str, Any],
        candidate_id: str | None,
        version_id: str | None,
    ) -> dict[str, Any]:
        return {
            "candidate_id": candidate_text.get("candidate_id", candidate_id),
            "version_id": candidate_text.get("version_id", version_id),
            "source_version_id": candidate_text.get("source_version_id"),
            "theme": candidate_text.get("theme"),
            "content_format": normalized_request.content_format,
            "truth_mode": normalized_request.truth_mode,
            "utility_mode": normalized_request.utility_mode,
            "utility_topic": normalized_request.utility_topic,
            "target_age": normalized_request.target_age,
            "audience_language": normalized_request.audience_language,
            "result_language": normalized_request.result_language,
            "main_subject": normalized_request.main_subject,
            "required_subjects": [
                subject.id
                for subject in normalized_request.subjects
                if subject.role == "main" or subject.id in (
                    normalized_request.subject_continuity_policy.required_subjects
                )
            ],
            "subject_continuity_policy": _model_to_plain(
                normalized_request.subject_continuity_policy
            ),
            "character_profile": _model_to_plain(
                normalized_request.character_profile
            ),
            "hard_details": list(normalized_request.hard_details),
        }

    def _stage_instructions(self, stage: str) -> dict[str, Any]:
        if stage == "candidate_text_generator":
            return {
                "profile": "full_creative_context",
                "output_contract": "candidate_texts",
            }
        if stage == "topic_deduplicator":
            return {
                "profile": "compact_semantic_context",
                "similarity_criteria": [
                    "theme_semantics",
                    "subject_overlap",
                    "utility_goal_overlap",
                    "narrative_arc_overlap",
                ],
            }
        if stage == "scorer":
            return {
                "profile": "criteria_oriented_context",
                "hard_gates": _HARD_GATES,
            }
        if stage == "ranker":
            return {
                "profile": "deterministic_ranking_context",
                "ranking_policy": "hard_gates_first_total_score_desc",
            }
        if stage == "candidate_validator":
            return {
                "profile": "constraints_oriented_context",
                "output_contract": "validation_result",
            }
        if stage == "candidate_refiner":
            return {
                "profile": "repair_oriented_context",
                "output_contract": "revised_candidate",
            }
        return {
            "profile": "selection_oriented_context",
            "output_contract": "approved_texts_and_shortage",
        }

    def _output_contract_summary(self, stage: str) -> dict[str, Any]:
        contracts = {
            "candidate_text_generator": [
                "candidate_id",
                "theme",
                "text",
                "questions",
                "used_subjects",
                "utility_points",
                "expected_visual_idea",
            ],
            "topic_deduplicator": [
                "candidate_id",
                "is_duplicate",
                "duplicate_of",
                "reason",
            ],
            "scorer": ["candidate_id", "hard_gates", "score_components", "total_score"],
            "ranker": ["candidate_id", "rank", "total_score", "hard_gates_passed"],
            "candidate_validator": [
                "candidate_id",
                "version_id",
                "status",
                "issues",
                "required_fixes",
                "summary",
            ],
            "candidate_refiner": [
                "candidate_id",
                "version_id",
                "source_version_id",
                "theme",
                "text",
                "questions",
                "changes_summary",
            ],
            "approved_text_selector": [
                "approved_texts",
                "shortage",
                "safe_fallback_candidates",
            ],
        }
        return {"stage": stage, "fields": contracts[stage]}

    def _context_blocks(
        self,
        stage: str,
        unresolved_details: list[dict[str, Any]],
    ) -> list[str]:
        blocks = ["layers", "metadata_constraints", "normalized_request"]
        if stage == "candidate_text_generator":
            blocks.extend(["character_profile", "subject_continuity_policy"])
        blocks.extend(["hard_details", "soft_preferences"])
        if unresolved_details:
            blocks.append("unresolved_details")
        blocks.extend(["stage_instructions", "output_contract", "stage_inputs"])
        return blocks

    def _context_summary(
        self,
        *,
        stage: str,
        selected_refs: list[dict[str, Any]],
        fallback_refs: list[dict[str, Any]],
        unresolved_details: list[dict[str, Any]],
        stage_input_summary: dict[str, Any],
    ) -> str:
        details = [
            f"{stage} context",
            f"layers={len(selected_refs)}",
            f"fallbacks={len(fallback_refs)}",
            f"unresolved={len(unresolved_details)}",
        ]
        if "candidate_id" in stage_input_summary:
            details.append(f"candidate={stage_input_summary['candidate_id']}")
        return "; ".join(details)

    def _hashable_layer_refs(self, refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [
            {
                "id": ref["id"],
                "type": ref["type"],
                "role": ref["role"],
                "source_hash": ref["source_hash"],
                "metadata_hash": ref["metadata_hash"],
                "body_hash": ref["body_hash"],
            }
            for ref in refs
        ]

    def _hashable_fallback_refs(
        self,
        refs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        return [
            {
                "requested": ref["requested"],
                "fallback_layer_id": ref["fallback_layer_id"],
                "source_hash": ref["source_hash"],
                "metadata_hash": ref["metadata_hash"],
                "body_hash": ref["body_hash"],
            }
            for ref in refs
        ]


def _dedupe_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for ref in refs:
        layer_id = ref["id"]
        if layer_id in seen:
            continue
        seen.add(layer_id)
        result.append(ref)
    return result


def _dedupe_fallback_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str | None, str]] = set()
    result: list[dict[str, Any]] = []
    for ref in refs:
        key = (ref.get("requested"), ref["fallback_layer_id"])
        if key in seen:
            continue
        seen.add(key)
        result.append(ref)
    return result


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _model_to_plain(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_model_to_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _model_to_plain(nested) for key, nested in value.items()}
    return value


def _stable_hash(value: Any) -> str:
    payload = json.dumps(
        _model_to_plain(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
