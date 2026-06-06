from __future__ import annotations

import copy
import hashlib
import json
import logging
from typing import Any

from src.models.schemas import SessionState, StagePromptContextEntry

logger = logging.getLogger(__name__)

FORBIDDEN_KEYS = {"bodies", "full_prompt", "prompt_body", "candidate_texts"}
FORBIDDEN_STRINGS = ("# Назначение",)
MAX_RAW_INPUT_SUMMARY = 240
MAX_STRING_VALUE = 500
MAX_LIST_ITEMS = 40


def build_root_trace_metadata(session: SessionState) -> dict[str, Any]:
    return _safe_payload(
        {
            "session_id": session.session_id,
            "raw_input_summary": _raw_input(session)[:MAX_RAW_INPUT_SUMMARY],
            "normalized_summary": _normalized_summary(session),
            "completion_status": _value(session.completion_status),
            "current_node": session.current_node,
            "shortage_status": session.shortage.status,
            "approved_count": len(session.approved_texts),
            "candidate_count": len(session.candidate_texts),
            "validation_attempts": session.pipeline_counters.validation_attempts,
            "refinement_attempts": session.pipeline_counters.refinement_attempts,
            "prompt_context_hash": session.prompt_context.snapshot_hash,
        }
    )


def build_node_trace_metadata(session: SessionState, node_name: str) -> dict[str, Any]:
    return _safe_payload(
        {
            "node_name": node_name,
            "current_node": session.current_node,
            "completion_status": _value(session.completion_status),
            "stage1": _stage1_metadata(session),
            "stage2": _stage2_metadata(session),
            "prompt": _prompt_metadata(session, node_name),
        }
    )


def record_node_trace(
    session: SessionState,
    *,
    node_name: str,
    status: str,
    metadata: dict[str, Any] | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
) -> None:
    try:
        event = {
            "node_name": node_name,
            "status": status,
            "trace_id": trace_id,
            "span_id": span_id,
            "metadata": redact_trace_payload(metadata or build_node_trace_metadata(session, node_name)),
        }
        event = _safe_payload(event)
        session.trace_refs.setdefault("node_events", []).append(event)
    except Exception as exc:
        logger.debug("record_node_trace failed for %s: %s", node_name, exc)


def enrich_approved_text_trace_refs(session: SessionState) -> None:
    try:
        trace_id = session.trace_refs.get("root", {}).get("trace_id")
        span_ids = _span_ids_by_node(session)
        selector_hash = _latest_stage_hash(session, "approved_text_selector")
        generator_hash = _latest_stage_hash(session, "candidate_text_generator")
        for approved in session.approved_texts:
            candidate_id = approved.candidate_id
            version_id = approved.version_id
            validator_hash = _latest_stage_hash(
                session,
                "candidate_validator",
                candidate_id=candidate_id,
                version_id=version_id,
            )
            refiner_hash = _latest_stage_hash(
                session,
                "candidate_refiner",
                candidate_id=candidate_id,
                version_id=version_id,
            )
            existing = dict(approved.trace_refs)
            approved.trace_refs = _safe_payload(
                {
                    **existing,
                    "prompt_context_hash": session.prompt_context.snapshot_hash,
                    "candidate_id": candidate_id,
                    "version_id": version_id,
                    "generator_stage_context_hash": generator_hash,
                    "validator_stage_context_hash": validator_hash or existing.get("stage_context_hash"),
                    "refiner_stage_context_hash": refiner_hash,
                    "selector_stage_context_hash": selector_hash,
                    "trace_id": trace_id,
                    "span_ids": span_ids,
                }
            )
    except Exception as exc:
        logger.debug("enrich_approved_text_trace_refs failed: %s", exc)


def redact_trace_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return _redact(copy.deepcopy(payload))


def _stage1_metadata(session: SessionState) -> dict[str, Any]:
    interpretation = session.interpretation_state
    prompt_context = session.normalized_request.prompt_context
    return {
        "classification": interpretation.classification,
        "confidence": dict(interpretation.confidence),
        "clarification_reason": interpretation.clarification_reason,
        "clarification_attempts": interpretation.clarification_attempts,
        "selected_option": _selected_resume_marker(session),
        "resolved_layer_ids": [ref.id for ref in prompt_context.resolved_layers],
        "fallback_layer_ids": [item.fallback_layer_id for item in prompt_context.fallback_layers],
        "unresolved_detail_labels": [item.label for item in prompt_context.unresolved_details],
        "validation_status": interpretation.validation_result.status,
        "execution_lookup_status": interpretation.execution_lookup_result.status,
        "preview": _hash_or_summary(session.preview_state.preview_text),
    }


def _stage2_metadata(session: SessionState) -> dict[str, Any]:
    duplicate_count = sum(1 for item in session.deduplication_results if item.is_duplicate)
    return {
        "candidate_count": {
            "requested": session.normalized_request.output_count,
            "generated": len(session.candidate_texts),
        },
        "duplicate_count": duplicate_count,
        "hard_gate_failure_counts": _hard_gate_failure_counts(session),
        "score_summary": _score_summary(session),
        "ranked_candidate_ids": [item.candidate_id for item in sorted(session.ranked_candidates, key=lambda item: item.rank)],
        "active_candidate": {
            "candidate_id": session.validation_loop_state.active_candidate_id,
            "version_id": session.validation_loop_state.active_version_id,
        },
        "validation_attempts": session.pipeline_counters.validation_attempts,
        "refinement_attempts": session.pipeline_counters.refinement_attempts,
        "approved_count": len(session.approved_texts),
        "shortage": {
            "status": session.shortage.status,
            "reason": session.shortage.reason,
            "requested": session.shortage.requested,
            "approved": session.shortage.approved,
        },
    }


def _prompt_metadata(session: SessionState, node_name: str) -> dict[str, Any]:
    entry = _latest_stage_entry(session, node_name)
    if entry is None and node_name == "prompt_context_preparation":
        entry = _latest_stage_entry(session, "candidate_text_generator")
    layer_ids = entry.layer_ids if entry else [ref.id for ref in session.prompt_context.resolved_layers]
    return {
        "layer_ids": list(layer_ids),
        "source_paths": _source_paths(session, list(layer_ids)),
        "source_prompt_context_hash": entry.source_prompt_context_hash if entry else session.prompt_context.source_hash,
        "stage_context_hash": entry.stage_context_hash if entry else None,
        "body_policy": entry.body_policy if entry else session.prompt_context.body_policy,
    }


def _latest_stage_entry(
    session: SessionState,
    stage: str,
    *,
    candidate_id: str | None = None,
    version_id: str | None = None,
) -> StagePromptContextEntry | None:
    for entry in reversed(session.stage_prompt_context.entries):
        if entry.stage != stage:
            continue
        if candidate_id is not None and entry.candidate_id != candidate_id:
            continue
        if version_id is not None and entry.version_id != version_id:
            continue
        return entry
    return None


def _latest_stage_hash(
    session: SessionState,
    stage: str,
    *,
    candidate_id: str | None = None,
    version_id: str | None = None,
) -> str | None:
    entry = _latest_stage_entry(session, stage, candidate_id=candidate_id, version_id=version_id)
    return entry.stage_context_hash if entry else None


def _normalized_summary(session: SessionState) -> dict[str, Any]:
    request = session.normalized_request
    return {
        "truth_mode": request.truth_mode,
        "utility_mode": request.utility_mode,
        "target_age": request.target_age,
        "main_subject": request.main_subject,
        "output_count": request.output_count,
    }


def _source_paths(session: SessionState, layer_ids: list[str]) -> list[str]:
    by_id = {ref.id: ref.source for ref in session.prompt_context.resolved_layers}
    by_id.update({ref.id: ref.source for ref in session.normalized_request.prompt_context.resolved_layers})
    return [source for layer_id in layer_ids if (source := by_id.get(layer_id))]


def _hard_gate_failure_counts(session: SessionState) -> dict[str, int]:
    counts: dict[str, int] = {}
    for score in session.scores:
        for gate, status in score.hard_gates.items():
            if status != "pass":
                counts[gate] = counts.get(gate, 0) + 1
    return counts


def _score_summary(session: SessionState) -> dict[str, Any]:
    scores = [score.total_score for score in session.scores if score.total_score is not None]
    if not scores:
        return {"count": 0, "min": None, "max": None}
    return {"count": len(scores), "min": min(scores), "max": max(scores)}


def _raw_input(session: SessionState) -> str:
    raw = getattr(session.request, "raw_text", None)
    if raw is None:
        raw = getattr(session.request, "topic", "")
    return str(raw or "")


def _selected_resume_marker(session: SessionState) -> str | None:
    pending = session.pending_interrupt
    if pending and pending.payload.get("selected_option_id"):
        return str(pending.payload["selected_option_id"])
    return None


def _hash_or_summary(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    return {"summary": value[:120], "hash": _stable_hash(value)}


def _span_ids_by_node(session: SessionState) -> dict[str, Any]:
    return {
        event["node_name"]: event.get("span_id")
        for event in session.trace_refs.get("node_events", [])
        if event.get("span_id") is not None
    }


def _safe_payload(payload: Any) -> Any:
    redacted = _redact(payload)
    return json.loads(json.dumps(redacted, ensure_ascii=False, sort_keys=True, default=str))


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in FORBIDDEN_KEYS:
                continue
            cleaned[key_text] = _redact(item)
        return cleaned
    if isinstance(value, list):
        return [_redact(item) for item in value[:MAX_LIST_ITEMS]]
    if isinstance(value, str):
        if any(forbidden in value for forbidden in FORBIDDEN_STRINGS):
            return "[redacted]"
        if len(value) > MAX_STRING_VALUE:
            return value[:MAX_STRING_VALUE]
        return value
    return value


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _stable_hash(payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
