from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.core.stage2_expressiveness_policy import append_expressiveness_task
from src.core.stage2_gate_policy import (
    append_truth_task,
    apply_character_consistency_gate_policy,
    requires_character_consistency,
    scorer_task,
)
from src.core.stage2_length_policy import append_length_task
from src.core.utils.json_parser import LLMJsonParseError, parse_llm_json
from src.providers.base import BaseLLMProvider

REQUIRED_HARD_GATES = (
    "safety",
    "truth_fit",
    "age_fit",
    "utility_goal",
    "subject_continuity",
    "hard_details",
    "character_consistency",
)
VALID_GATE_VALUES = {"pass", "fail", "unknown"}
VALID_ISSUE_TYPES = set(REQUIRED_HARD_GATES) | {
    "text_overlength",
    "text_underlength",
    "sentence_too_complex",
    "flat_narrative",
    "style_fit_weak",
}
VALID_ISSUE_SEVERITIES = {"minor", "major", "critical"}
VALID_VALIDATION_STATUSES = {"accepted", "needs_revision", "rejected"}


class LLMStage2TextExecutor:
    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        *,
        model_name: str | None = None,
        max_retries: int = 1,
        debug_artifact_dir: str | Path | None = None,
        debug_to_stderr: bool = False,
    ) -> None:
        self.llm_provider = llm_provider
        self.model_name = model_name
        self.max_retries = max(0, int(max_retries))
        self.llm_call_count = 0
        self.parse_failure_count = 0
        self.debug_artifact_dir = Path(debug_artifact_dir) if debug_artifact_dir is not None else None
        self.debug_to_stderr = debug_to_stderr
        self._debug_sequence = 0
        self._last_call: dict[str, Any] = {}

    def set_debug_artifacts(self, artifact_dir: str | Path | None, *, to_stderr: bool = False) -> None:
        self.debug_artifact_dir = Path(artifact_dir) if artifact_dir is not None else None
        self.debug_to_stderr = to_stderr

    def generate_candidates(self, runtime_context: dict[str, Any], count: int) -> list[dict[str, Any]]:
        prompt = self._build_prompt(
            runtime_context,
            contract={
                "candidates": [
                    {
                        "theme": "string",
                        "text": "string",
                        "questions": ["string"],
                        "utility_points": ["string"],
                        "used_subjects": ["string"],
                        "expected_visual_idea": "string|null",
                    }
                ]
            },
            task=append_truth_task(
                append_expressiveness_task(
                    append_length_task(
                        f"Generate up to {count} distinct text candidates. "
                        "Return fewer if you cannot satisfy the contract safely.",
                        runtime_context,
                        stage="generate_candidates",
                    ),
                    runtime_context,
                    stage="generate_candidates",
                ),
                runtime_context.get("normalized_request_summary"),
                stage="generate_candidates",
            ),
        )
        parsed = self._call_json(prompt, "stage2.generate_candidates", default=None)
        if not isinstance(parsed, dict):
            self._write_debug_artifact(
                "candidate_text_generator",
                prompt=prompt,
                parsed_response=parsed,
                normalized_result=[],
                diagnostics={"raw_items": 0, "valid_items": 0, "rejected_items": [], "reason": "response_not_object"},
            )
            return []
        candidates = parsed.get("candidates")
        if not isinstance(candidates, list):
            self._write_debug_artifact(
                "candidate_text_generator",
                prompt=prompt,
                parsed_response=parsed,
                normalized_result=[],
                diagnostics={"raw_items": 0, "valid_items": 0, "rejected_items": [], "reason": "missing_candidates_key"},
            )
            return []
        result: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for item in candidates:
            if len(result) >= count:
                break
            if not isinstance(item, dict):
                rejected.append({"reason": "item_not_object"})
                continue
            theme = _clean_str(item.get("theme"))
            text = _clean_str(item.get("text"))
            if not theme or not text:
                rejected.append({"reason": "missing_theme_or_text", "theme": theme})
                continue
            result.append(
                {
                    "theme": theme,
                    "text": text,
                    "questions": _string_list(item.get("questions")),
                    "utility_points": _string_list(item.get("utility_points")),
                    "used_subjects": _string_list(item.get("used_subjects")),
                    "expected_visual_idea": _optional_str(item.get("expected_visual_idea")),
                }
            )
        self._write_debug_artifact(
            "candidate_text_generator",
            prompt=prompt,
            parsed_response=parsed,
            normalized_result=result,
            diagnostics={"raw_items": len(candidates), "valid_items": len(result), "rejected_items": rejected},
        )
        return result

    def deduplicate_topics(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        allowed_ids = _candidate_ids(runtime_context)
        prompt = self._build_prompt(
            runtime_context,
            contract={
                "decisions": [
                    {
                        "candidate_id": "c01",
                        "is_duplicate": False,
                        "duplicate_of": None,
                        "reason": "string",
                    }
                ]
            },
            task="Detect semantic duplicate topics only for candidate ids present in stage inputs.",
        )
        parsed = self._call_json(prompt, "stage2.deduplicate_topics", default=None)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("decisions"), list):
            self._write_debug_artifact(
                "topic_deduplicator",
                prompt=prompt,
                parsed_response=parsed,
                normalized_result=[],
                diagnostics={"raw_items": 0, "valid_items": 0, "rejected_items": [], "reason": "missing_decisions_key"},
            )
            return []
        result: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for item in parsed["decisions"]:
            if not isinstance(item, dict):
                rejected.append({"reason": "item_not_object"})
                continue
            candidate_id = _clean_str(item.get("candidate_id"))
            duplicate_of = _optional_str(item.get("duplicate_of"))
            if candidate_id not in allowed_ids:
                rejected.append({"candidate_id": candidate_id, "reason": "unknown_candidate_id"})
                continue
            if duplicate_of is not None and duplicate_of not in allowed_ids:
                rejected.append({"candidate_id": candidate_id, "duplicate_of": duplicate_of, "reason": "unknown_duplicate_of"})
                duplicate_of = None
            result.append(
                {
                    "candidate_id": candidate_id,
                    "is_duplicate": bool(item.get("is_duplicate")),
                    "duplicate_of": duplicate_of,
                    "reason": _clean_str(item.get("reason")),
                }
            )
        self._write_debug_artifact(
            "topic_deduplicator",
            prompt=prompt,
            parsed_response=parsed,
            normalized_result=result,
            diagnostics={"raw_items": len(parsed["decisions"]), "valid_items": len(result), "rejected_items": rejected},
        )
        return result

    def score_candidates(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        allowed_ids = _candidate_ids(runtime_context)
        prompt = self._build_prompt(
            runtime_context,
            contract={
                "scores": [
                    {
                        "candidate_id": "c01",
                        "hard_gates": {gate: "pass" for gate in REQUIRED_HARD_GATES},
                        "score_components": {
                            "child_interest": 0.0,
                            "age_fit": 0.0,
                            "utility_fit": 0.0,
                            "style_fit": 0.0,
                            "novelty": 0.0,
                            "visual_potential": 0.0,
                        },
                        "total_score": 0.0,
                    }
                ]
            },
            task=append_expressiveness_task(
                append_length_task(
                    scorer_task(
                        "Score each candidate. Use only pass, fail, or unknown for every hard gate.",
                        runtime_context.get("normalized_request_summary"),
                        allowed_ids=allowed_ids,
                    ),
                    runtime_context,
                    stage="score_candidates",
                ),
                runtime_context,
                stage="score_candidates",
            ),
        )
        parsed = self._call_json(prompt, "stage2.score_candidates", default=None)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("scores"), list):
            self._write_debug_artifact(
                "scorer",
                prompt=prompt,
                parsed_response=parsed,
                normalized_result=[],
                diagnostics={"raw_items": 0, "valid_items": 0, "rejected_items": [], "reason": "missing_scores_key"},
            )
            return []
        result: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        for item in parsed["scores"]:
            if not isinstance(item, dict):
                rejected.append({"reason": "item_not_object"})
                continue
            candidate_id = _clean_str(item.get("candidate_id"))
            if candidate_id not in allowed_ids:
                rejected.append({"candidate_id": candidate_id, "reason": "unknown_candidate_id"})
                continue
            hard_gates = apply_character_consistency_gate_policy(
                _normalize_hard_gates(item.get("hard_gates")),
                runtime_context.get("normalized_request_summary"),
            )
            score_components = {
                str(key): _clamp01(value)
                for key, value in (item.get("score_components") or {}).items()
                if _is_number_like(value)
            }
            result.append(
                {
                    "candidate_id": candidate_id,
                    "hard_gates": hard_gates,
                    "score_components": score_components,
                    "total_score": _clamp01(item.get("total_score")),
                }
            )
        self._write_debug_artifact(
            "scorer",
            prompt=prompt,
            parsed_response=parsed,
            normalized_result=result,
            diagnostics={"raw_items": len(parsed["scores"]), "valid_items": len(result), "rejected_items": rejected},
        )
        return result

    def validate_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(
            runtime_context,
            contract={
                "status": "accepted|needs_revision|rejected",
                "summary": "string",
                "issues": [
                    {
                        "type": "safety|truth_fit|age_fit|utility_goal|subject_continuity|hard_details|character_consistency|text_overlength|text_underlength|sentence_too_complex|flat_narrative|style_fit_weak",
                        "severity": "minor|major|critical",
                        "description": "string",
                    }
                ],
                "required_fixes": ["string"],
            },
            task=append_truth_task(
                append_expressiveness_task(
                    append_length_task(
                        _validation_task(runtime_context),
                        runtime_context,
                        stage="validate_candidate",
                    ),
                    runtime_context,
                    stage="validate_candidate",
                ),
                runtime_context.get("normalized_request_summary"),
                stage="validate_candidate",
            ),
        )
        parsed = self._call_json(prompt, "stage2.validate_candidate", default=None)
        if not isinstance(parsed, dict):
            result = _technical_validation_failure()
            self._write_debug_artifact(
                "candidate_validator",
                prompt=prompt,
                parsed_response=parsed,
                normalized_result=result,
                diagnostics={"status": "rejected", "reason": "response_not_object"},
            )
            return result
        status = _clean_str(parsed.get("status"))
        if status not in VALID_VALIDATION_STATUSES:
            status = "needs_revision"
        issues = _normalize_issues(parsed.get("issues"))
        if status == "accepted" and issues:
            status = "needs_revision"
        result = {
            "status": status,
            "summary": _clean_str(parsed.get("summary")),
            "issues": issues,
            "required_fixes": _string_list(parsed.get("required_fixes")),
        }
        self._write_debug_artifact(
            "candidate_validator",
            prompt=prompt,
            parsed_response=parsed,
            normalized_result=result,
            diagnostics={"status": status, "issue_count": len(issues)},
        )
        return result

    def refine_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        original = runtime_context.get("candidate_text") if isinstance(runtime_context.get("candidate_text"), dict) else {}
        prompt = self._build_prompt(
            runtime_context,
            contract={
                "theme": "string",
                "text": "string",
                "questions": ["string"],
                "changes_summary": "string",
            },
            task=append_truth_task(
                append_expressiveness_task(
                    append_length_task(
                        (
                            "Revise only the current candidate text according to validator issues. "
                            "Preserve protected subject, truth mode, hard details, and character continuity."
                        ),
                        runtime_context,
                        stage="refine_candidate",
                    ),
                    runtime_context,
                    stage="refine_candidate",
                ),
                runtime_context.get("normalized_request_summary"),
                stage="refine_candidate",
            ),
        )
        parsed = self._call_json(prompt, "stage2.refine_candidate", default=None)
        if not isinstance(parsed, dict):
            result = {
                "theme": _clean_str(original.get("theme")),
                "text": _clean_str(original.get("text")),
                "questions": _string_list(original.get("questions")),
                "changes_summary": "Parse failure: preserved original candidate text.",
            }
            self._write_debug_artifact(
                "candidate_refiner",
                prompt=prompt,
                parsed_response=parsed,
                normalized_result=result,
                diagnostics={"reason": "response_not_object"},
            )
            return result
        theme = _clean_str(parsed.get("theme")) or _clean_str(original.get("theme"))
        text = _clean_str(parsed.get("text")) or _clean_str(original.get("text"))
        result = {
            "theme": theme,
            "text": text,
            "questions": _string_list(parsed.get("questions")) or _string_list(original.get("questions")),
            "changes_summary": _clean_str(parsed.get("changes_summary")),
        }
        self._write_debug_artifact(
            "candidate_refiner",
            prompt=prompt,
            parsed_response=parsed,
            normalized_result=result,
            diagnostics={"status": "completed"},
        )
        return result

    def trace_metadata(self) -> dict[str, Any]:
        return {
            "executor_type": "llm",
            "provider_name": self.llm_provider.__class__.__name__,
            "model_name": self.model_name,
            "llm_call_count": self.llm_call_count,
            "parse_failure_count": self.parse_failure_count,
        }

    def _call_json(self, prompt: str, context: str, *, default: Any) -> Any:
        attempts = self.max_retries + 1
        for index in range(attempts):
            self.llm_call_count += 1
            raw_response = self.llm_provider.generate_text(prompt)
            self._last_call = {"raw_response": raw_response, "parse_error": None, "context": context}
            try:
                return parse_llm_json(raw_response, context=context)
            except LLMJsonParseError:
                self._last_call = {"raw_response": raw_response, "parse_error": "LLMJsonParseError", "context": context}
                if index >= attempts - 1:
                    self.parse_failure_count += 1
                    return default
        return default

    def _write_debug_artifact(
        self,
        stage: str,
        *,
        prompt: str,
        parsed_response: Any,
        normalized_result: Any,
        diagnostics: dict[str, Any],
    ) -> None:
        if self.debug_artifact_dir is None and not self.debug_to_stderr:
            return
        status = "parse_failed" if self._last_call.get("parse_error") else "completed"
        artifact = {
            "created_at": datetime.now(UTC).isoformat(),
            "stage": stage,
            "status": status,
            "provider_name": self.llm_provider.__class__.__name__,
            "model_name": self.model_name,
            "llm_call_count": self.llm_call_count,
            "parse_failure_count": self.parse_failure_count,
            "diagnostics": diagnostics,
            "prompt": prompt,
            "raw_response": self._last_call.get("raw_response"),
            "parsed_response": parsed_response,
            "normalized_result": normalized_result,
        }
        artifact_path: Path | None = None
        if self.debug_artifact_dir is not None:
            self.debug_artifact_dir.mkdir(parents=True, exist_ok=True)
            self._debug_sequence += 1
            artifact_path = self.debug_artifact_dir / f"{self._debug_sequence:03d}_{stage}.json"
            artifact_path.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
        if self.debug_to_stderr:
            raw_items = diagnostics.get("raw_items")
            valid_items = diagnostics.get("valid_items")
            rejected = diagnostics.get("rejected_items")
            rejected_count = len(rejected) if isinstance(rejected, list) else 0
            parts = [f"[llm-debug] stage={stage}", f"status={status}"]
            if raw_items is not None:
                parts.append(f"raw_items={raw_items}")
            if valid_items is not None:
                parts.append(f"valid_items={valid_items}")
            if rejected_count:
                parts.append(f"rejected={rejected_count}")
            if artifact_path is not None:
                parts.append(f"artifact={artifact_path}")
            print(" ".join(parts), file=sys.stderr)

    def _build_prompt(self, runtime_context: dict[str, Any], *, contract: dict[str, Any], task: str) -> str:
        payload = {
            "stage": runtime_context.get("stage"),
            "model_name": self.model_name,
            "task": task,
            "normalized_request_summary": runtime_context.get("normalized_request_summary", {}),
            "length_policy": runtime_context.get("length_policy", {}),
            "stage_inputs": _stage_inputs(runtime_context),
            "prompt_context": {
                "ordered_layer_ids": [ref.get("id") for ref in runtime_context.get("ordered_layer_refs", []) if isinstance(ref, dict)],
                "fallback_layer_ids": [
                    ref.get("fallback_layer_id")
                    for ref in runtime_context.get("fallback_layer_refs", [])
                    if isinstance(ref, dict)
                ],
                "unresolved_details": runtime_context.get("unresolved_details", []),
                "stage_context_hash": runtime_context.get("stage_context_hash"),
            },
            "layer_grounding": _layer_grounding(runtime_context),
            "stage_context": {
                "body_policy": runtime_context.get("body_policy"),
                "stage_instructions": runtime_context.get("stage_instructions", []),
                "context_blocks": runtime_context.get("context_blocks", []),
                "hard_details": runtime_context.get("hard_details", []),
                "soft_preferences": runtime_context.get("soft_preferences", []),
            },
            "required_output_shape": contract,
        }
        return (
            "You are DreamyDraw Stage 2 text pipeline executor.\n"
            "Return JSON only. Do not include markdown, commentary, external secrets, or unrelated data.\n"
            "Return the required object itself. Do not wrap it in keys such as json_contract, schema, result, or model_name.\n"
            f"The top-level key(s) of your response must be exactly: {sorted(contract.keys())}.\n"
            "Do not perform or plan later media work; this stage only writes and evaluates text.\n"
            f"{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
        )


def _validation_task(runtime_context: dict[str, Any]) -> str:
    task = "Validate the current candidate against Stage 2 hard gates."
    summary = runtime_context.get("normalized_request_summary")
    if not requires_character_consistency(summary if isinstance(summary, dict) else None):
        task += (
            " No character_profile and no required persistent character: "
            "do not fail character_consistency unless a conflicting named character appears."
        )
    return task


def _layer_grounding(runtime_context: dict[str, Any]) -> dict[str, Any]:
    grounding: dict[str, Any] = {}
    metadata = runtime_context.get("metadata_constraints")
    if isinstance(metadata, dict) and metadata:
        grounding["metadata_constraints"] = metadata
    bodies = runtime_context.get("bodies")
    if isinstance(bodies, dict) and bodies:
        grounding["bodies"] = bodies
    return grounding


def _stage_inputs(runtime_context: dict[str, Any]) -> dict[str, Any]:
    allowed = (
        "candidate_count",
        "output_count",
        "candidate_themes",
        "candidate_texts",
        "candidate_text",
        "validator_issues",
        "required_fixes",
        "stage_inputs_summary",
    )
    return {key: runtime_context[key] for key in allowed if key in runtime_context}


def _candidate_ids(runtime_context: dict[str, Any]) -> set[str]:
    candidates = runtime_context.get("candidate_texts")
    if not isinstance(candidates, list):
        return set()
    return {
        candidate_id
        for item in candidates
        if isinstance(item, dict) and (candidate_id := _clean_str(item.get("candidate_id")))
    }


def _normalize_hard_gates(value: Any) -> dict[str, str]:
    source = value if isinstance(value, dict) else {}
    normalized: dict[str, str] = {}
    for gate in REQUIRED_HARD_GATES:
        gate_value = _clean_str(source.get(gate))
        normalized[gate] = gate_value if gate_value in VALID_GATE_VALUES else "unknown"
    return normalized


def _normalize_issues(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        issue_type = _clean_str(item.get("type"))
        severity = _clean_str(item.get("severity"))
        if issue_type not in VALID_ISSUE_TYPES:
            issue_type = "safety"
        if severity not in VALID_ISSUE_SEVERITIES:
            severity = "major"
        result.append(
            {
                "type": issue_type,
                "severity": severity,
                "description": _clean_str(item.get("description")),
            }
        )
    return result


def _technical_validation_failure() -> dict[str, Any]:
    return {
        "status": "rejected",
        "summary": "Technical validation failure: provider response was not valid JSON.",
        "issues": [
            {
                "type": "safety",
                "severity": "critical",
                "description": "Provider response could not be parsed into the required validation contract.",
            }
        ],
        "required_fixes": ["Retry validation with a valid JSON-only provider response."],
    }


def _clean_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _optional_str(value: Any) -> str | None:
    cleaned = _clean_str(value)
    return cleaned or None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [cleaned for item in value if (cleaned := _clean_str(item))]


def _is_number_like(value: Any) -> bool:
    try:
        float(value)
    except (TypeError, ValueError):
        return False
    return True


def _clamp01(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))
