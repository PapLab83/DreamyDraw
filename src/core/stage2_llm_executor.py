from __future__ import annotations

import json
from typing import Any

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
VALID_ISSUE_TYPES = set(REQUIRED_HARD_GATES)
VALID_ISSUE_SEVERITIES = {"minor", "major", "critical"}
VALID_VALIDATION_STATUSES = {"accepted", "needs_revision", "rejected"}


class LLMStage2TextExecutor:
    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        *,
        model_name: str | None = None,
        max_retries: int = 1,
    ) -> None:
        self.llm_provider = llm_provider
        self.model_name = model_name
        self.max_retries = max(0, int(max_retries))
        self.llm_call_count = 0
        self.parse_failure_count = 0

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
            task=(
                f"Generate up to {count} distinct text candidates. "
                "Return fewer if you cannot satisfy the contract safely."
            ),
        )
        parsed = self._call_json(prompt, "stage2.generate_candidates", default=None)
        if not isinstance(parsed, dict):
            return []
        candidates = parsed.get("candidates")
        if not isinstance(candidates, list):
            return []
        result: list[dict[str, Any]] = []
        for item in candidates:
            if len(result) >= count:
                break
            if not isinstance(item, dict):
                continue
            theme = _clean_str(item.get("theme"))
            text = _clean_str(item.get("text"))
            if not theme or not text:
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
            return []
        result: list[dict[str, Any]] = []
        for item in parsed["decisions"]:
            if not isinstance(item, dict):
                continue
            candidate_id = _clean_str(item.get("candidate_id"))
            duplicate_of = _optional_str(item.get("duplicate_of"))
            if candidate_id not in allowed_ids:
                continue
            if duplicate_of is not None and duplicate_of not in allowed_ids:
                duplicate_of = None
            result.append(
                {
                    "candidate_id": candidate_id,
                    "is_duplicate": bool(item.get("is_duplicate")),
                    "duplicate_of": duplicate_of,
                    "reason": _clean_str(item.get("reason")),
                }
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
            task="Score each candidate. Use only pass, fail, or unknown for every hard gate.",
        )
        parsed = self._call_json(prompt, "stage2.score_candidates", default=None)
        if not isinstance(parsed, dict) or not isinstance(parsed.get("scores"), list):
            return []
        result: list[dict[str, Any]] = []
        for item in parsed["scores"]:
            if not isinstance(item, dict):
                continue
            candidate_id = _clean_str(item.get("candidate_id"))
            if candidate_id not in allowed_ids:
                continue
            hard_gates = _normalize_hard_gates(item.get("hard_gates"))
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
        return result

    def validate_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        prompt = self._build_prompt(
            runtime_context,
            contract={
                "status": "accepted|needs_revision|rejected",
                "summary": "string",
                "issues": [
                    {
                        "type": "safety|truth_fit|age_fit|utility_goal|subject_continuity|hard_details|character_consistency",
                        "severity": "minor|major|critical",
                        "description": "string",
                    }
                ],
                "required_fixes": ["string"],
            },
            task="Validate the current candidate against Stage 2 hard gates.",
        )
        parsed = self._call_json(prompt, "stage2.validate_candidate", default=None)
        if not isinstance(parsed, dict):
            return _technical_validation_failure()
        status = _clean_str(parsed.get("status"))
        if status not in VALID_VALIDATION_STATUSES:
            status = "needs_revision"
        issues = _normalize_issues(parsed.get("issues"))
        if status == "accepted" and issues:
            status = "needs_revision"
        return {
            "status": status,
            "summary": _clean_str(parsed.get("summary")),
            "issues": issues,
            "required_fixes": _string_list(parsed.get("required_fixes")),
        }

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
            task=(
                "Revise only the current candidate text according to validator issues. "
                "Preserve protected subject, truth mode, hard details, and character continuity."
            ),
        )
        parsed = self._call_json(prompt, "stage2.refine_candidate", default=None)
        if not isinstance(parsed, dict):
            return {
                "theme": _clean_str(original.get("theme")),
                "text": _clean_str(original.get("text")),
                "questions": _string_list(original.get("questions")),
                "changes_summary": "Parse failure: preserved original candidate text.",
            }
        theme = _clean_str(parsed.get("theme")) or _clean_str(original.get("theme"))
        text = _clean_str(parsed.get("text")) or _clean_str(original.get("text"))
        return {
            "theme": theme,
            "text": text,
            "questions": _string_list(parsed.get("questions")) or _string_list(original.get("questions")),
            "changes_summary": _clean_str(parsed.get("changes_summary")),
        }

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
            try:
                return parse_llm_json(raw_response, context=context)
            except LLMJsonParseError:
                if index >= attempts - 1:
                    self.parse_failure_count += 1
                    return default
        return default

    def _build_prompt(self, runtime_context: dict[str, Any], *, contract: dict[str, Any], task: str) -> str:
        payload = {
            "stage": runtime_context.get("stage"),
            "model_name": self.model_name,
            "task": task,
            "normalized_request_summary": runtime_context.get("normalized_request_summary", {}),
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
            "stage_context": {
                "stage_instructions": runtime_context.get("stage_instructions", []),
                "context_blocks": runtime_context.get("context_blocks", []),
                "hard_details": runtime_context.get("hard_details", []),
                "soft_preferences": runtime_context.get("soft_preferences", []),
            },
            "json_contract": contract,
        }
        return (
            "You are DreamyDraw Stage 2 text pipeline executor.\n"
            "Return JSON only. Do not include markdown, commentary, external secrets, or unrelated data.\n"
            "Do not perform or plan later media work; this stage only writes and evaluates text.\n"
            f"{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
        )


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
