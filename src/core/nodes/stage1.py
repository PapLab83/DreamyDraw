from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from src.core.graph.state import GraphState
from src.core.prompts.composer import PromptComposer
from src.core.prompts.lookup import execute_prompt_lookup, lookup_prompt_metadata
from src.core.prompts.registry import PromptRegistry
from src.models.schemas import (
    CompletionStatus,
    ExecutionPromptContext,
    NormalizedPromptContext,
    NormalizedRequest,
    PendingInterrupt,
    PromptLayerRef,
    PromptUnresolvedDetail,
    SessionState,
    StatusResult,
    Subject,
)

_SUPPORTED_LAYER_IDS = {
    "content_format": "CONTENT_FORMAT_STORY",
    "truth_mode": "FAIRY_TALE_BASE",
    "utility_mode": "UTILITY_TEACHING_BASE",
    "utility_topic": "UTILITY_TOPIC_ROAD_SAFETY",
    "age": "AGE_5",
    "audience_language": "LANGUAGE_RU_AUDIENCE",
    "result_language": "LANGUAGE_RU_RESULT",
    "substyle:russian_folk_tale": "RUSSIAN_FOLK_TALE",
    "subject:fox": "FAIRY_TALE_ANIMAL_FOX",
}

_FAIRY_TALE_RE = re.compile(r"\bсказ(?:ка|ку|ки|кой|ке|ок|очная|очный|очное)\b", re.I)
_TEACHING_TERMS = ("научи", "объясни", "безопасность", "дорога", "переход", "светофор")
_ROAD_TERMS = ("безопасность", "дорог", "переход", "светофор")
_FOX_RE = re.compile(r"\b(лиса|лис|лису|лисой|лисе|лисичка|лисичку|лисица|лисицу)\b", re.I)
_AGE_RE = re.compile(r"(?:для\s*)?([3-9])\s*(?:лет|года|год)?", re.I)
_UNSUPPORTED_RE = re.compile(
    r"\b(дисней|disney|микки|mickey|человек[- ]?паук|spider[- ]?man|гарри поттер|harry potter)\b",
    re.I,
)
_IMPOSSIBLE_VISUAL_RE = re.compile(
    r"\b(точн(?:ая|ое|ый)\s+картин|фотореалистич|анимаци|мультфильм|сгенерируй\s+картин)\b",
    re.I,
)


def input_analysis(state: GraphState) -> GraphState:
    session = state["session"]
    resume_payload = state.get("user_input")
    text, valid_resume_consumed = _input_text(session, resume_payload)

    if valid_resume_consumed:
        session.pending_interrupt = None
        session.completion_status = CompletionStatus.RUNNING
    state["user_input"] = None

    normalized = _extract_normalized_request(session, text)
    session.normalized_request = normalized
    session.interpretation_state.confidence.update(_analysis_confidence(normalized, text))
    session.current_node = "input_analysis"
    return {"session": session, "user_input": None}


def metadata_lookup(state: GraphState, registry: PromptRegistry) -> GraphState:
    session = state["session"]
    request = session.normalized_request

    hints: dict[str, Any] = {}
    _hint(hints, "content_format", registry, ["story"], type="format", role="content_format")
    if request.truth_mode == "FAIRY_TALE":
        _hint(hints, "truth_mode", registry, ["FAIRY_TALE", "сказка"], type="truth_mode")
    if request.utility_mode == "TEACHING":
        _hint(hints, "utility_mode", registry, ["TEACHING", "обучение"], type="utility", role="utility_mode")
    if request.utility_topic == "ROAD_SAFETY":
        _hint(hints, "utility_topic", registry, ["ROAD_SAFETY", "дорога"], type="utility", role="utility_topic")
    if request.target_age:
        _hint(hints, "age", registry, [request.target_age], type="age")
    _hint(hints, "audience_language", registry, [request.audience_language], type="language", role="audience_language")
    _hint(hints, "result_language", registry, [request.result_language], type="language", role="result_language")
    if request.substyle:
        _hint(hints, "substyle", registry, [request.substyle], type="substyle")

    subject_hints = []
    for subject in request.subjects:
        candidates = lookup_prompt_metadata(
            registry,
            user_terms=[subject.id, subject.label],
            type="entity",
            applicability={"truth_modes": request.truth_mode or ""},
            limit=3,
        )
        if candidates:
            subject_hints.append({"subject_id": subject.id, **candidates[0].to_dict()})
    hints["subjects"] = subject_hints
    hints["fallback_candidates"] = []
    hints["unresolved_detail_candidates"] = [
        {"label": detail, "type": "hard_detail"} for detail in request.hard_details
    ]

    session.interpretation_state.lookup_hints = hints
    session.interpretation_state.confidence["metadata_lookup"] = 80 if hints else 30
    session.current_node = "metadata_lookup"
    return state


def request_classification(state: GraphState) -> GraphState:
    session = state["session"]
    interpretation = session.interpretation_state
    request = session.normalized_request

    validation_status = interpretation.validation_result.status
    execution_status = interpretation.execution_lookup_result.status
    stop_reason = "stop"
    if validation_status in {"stop"} or execution_status in {"fail_stop"}:
        classification = "stop"
        stop_reason = "validation_or_execution_stop"
    elif request.hard_details and any("unsupported:" in item for item in request.hard_details):
        classification = "unsupported_hard_requirement"
    elif not _meaningful_request(request):
        if interpretation.clarification_attempts >= interpretation.max_clarification_attempts:
            classification = "stop"
            stop_reason = "empty_or_meaningless"
        else:
            classification = "empty_or_meaningless"
    elif validation_status == "fail_reclassify" or execution_status == "fail_clarify":
        classification = "needs_clarification"
    elif _is_complete_request(request):
        classification = "complete"
    else:
        classification = "needs_clarification"

    interpretation.classification = classification
    interpretation.requires_clarification = classification in {
        "needs_clarification",
        "empty_or_meaningless",
        "contradictory",
        "unsupported_hard_requirement",
    }
    interpretation.clarification_reason = None if classification == "complete" else classification
    interpretation.clarification_options = _classification_options(classification)
    if classification == "stop":
        _stop_session(
            session,
            reason=stop_reason,
            issues=["Запрос не удалось довести до исполнимой интерпретации в лимит уточнений."],
        )
    session.current_node = "request_classification"
    return state


def clarification_interrupt(state: GraphState) -> GraphState:
    return _create_or_reuse_interrupt(
        state,
        node="clarification_interrupt",
        reason=state["session"].interpretation_state.clarification_reason or "needs_clarification",
        message="Нужно уточнить запрос, чтобы собрать исполнимую задачу.",
        options=_payload_options(state["session"]),
    )


def empty_input_interrupt(state: GraphState) -> GraphState:
    return _create_or_reuse_interrupt(
        state,
        node="empty_input_interrupt",
        reason="empty_or_meaningless",
        message=(
            "Пока не вижу темы для детского текста. Можно выбрать пример или "
            "написать своими словами, о чём сделать короткую историю."
        ),
        options=[
            {
                "id": "opt_1",
                "label": "Сказка про лису для 5 лет",
                "normalized_patch": {"truth_mode": "FAIRY_TALE", "target_age": "5", "main_subject": "fox"},
            },
            {
                "id": "opt_2",
                "label": "История про лису и безопасность на дороге",
                "normalized_patch": {"utility_mode": "TEACHING", "utility_topic": "ROAD_SAFETY", "main_subject": "fox"},
            },
        ],
    )


def unsupported_interrupt_or_stop(state: GraphState) -> GraphState:
    session = state["session"]
    attempts = session.interpretation_state.clarification_attempts
    if attempts < session.interpretation_state.max_clarification_attempts:
        return _create_or_reuse_interrupt(
            state,
            node="unsupported_interrupt_or_stop",
            reason="unsupported_hard_requirement",
            message="Часть запроса пока нельзя выполнить буквально. Можно выбрать безопасную замену.",
            options=[
                {
                    "id": "opt_1",
                    "label": "Сказка с оригинальным героем-лисой",
                    "normalized_patch": {"truth_mode": "FAIRY_TALE", "main_subject": "fox"},
                }
            ],
        )

    _stop_session(
        session,
        reason="unsupported_hard_requirement",
        issues=["Запрос содержит жёсткое требование, которое нельзя безопасно выполнить в MVP."],
    )
    session.current_node = "unsupported_interrupt_or_stop"
    return state


def candidate_layer_resolution(state: GraphState, registry: PromptRegistry) -> GraphState:
    session = state["session"]
    request = session.normalized_request
    refs: list[PromptLayerRef] = []
    unresolved: list[PromptUnresolvedDetail] = []

    _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["content_format"], "content_format=story")
    if request.truth_mode == "FAIRY_TALE":
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["truth_mode"], "truth_mode=FAIRY_TALE")
    if request.utility_mode == "TEACHING":
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["utility_mode"], "utility_mode=TEACHING")
    if request.utility_topic == "ROAD_SAFETY":
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["utility_topic"], "utility_topic=ROAD_SAFETY")
    if request.target_age == "5":
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["age"], "target_age=5")
    elif request.target_age:
        unresolved.append(
            PromptUnresolvedDetail(
                label=f"age {request.target_age}",
                type="age",
                instruction="Учитывать возраст как свободную деталь, без отдельного layer id.",
            )
        )
    if request.audience_language == "ru":
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["audience_language"], "audience_language=ru")
    if request.result_language == "ru":
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["result_language"], "result_language=ru")
    if request.substyle == "russian_folk_tale":
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["substyle:russian_folk_tale"], "substyle=russian_folk_tale")

    for subject in request.subjects:
        if subject.id == "fox" and request.truth_mode == "FAIRY_TALE":
            _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["subject:fox"], "subject=fox")
            subject.resolved_layer_id = _SUPPORTED_LAYER_IDS["subject:fox"]
        elif subject.label:
            unresolved.append(
                PromptUnresolvedDetail(
                    label=subject.label,
                    type="subject",
                    instruction="Использовать как свободную деталь, не подставляя fake layer id.",
                )
            )
            subject.unresolved_detail = subject.label

    request.prompt_context = NormalizedPromptContext(
        resolved_layers=refs,
        fallback_layers=[],
        unresolved_details=unresolved,
    )
    session.interpretation_state.layer_resolution_result = StatusResult(
        status="resolved",
        issues=[],
        details={
            "resolved_layer_ids": [ref.id for ref in refs],
            "unresolved_detail_labels": [detail.label for detail in unresolved],
        },
    )
    session.current_node = "candidate_layer_resolution"
    return state


def final_parameter_validation(state: GraphState, registry: PromptRegistry) -> GraphState:
    session = state["session"]
    request = session.normalized_request
    refs = request.prompt_context.resolved_layers
    issues: list[str] = []

    if request.content_format != "story":
        issues.append("content_format is missing or unsupported")
    if not request.truth_mode:
        issues.append("truth_mode is missing")
    if not request.target_age:
        issues.append("target_age is missing")
    if request.output_count < 1:
        issues.append("output_count must be positive")
    if not request.main_subject or not request.subjects:
        issues.append("main subject is missing")
    if not _has_ref(refs, type_="format", role="content_format"):
        issues.append("content_format layer is missing")
    if request.truth_mode == "FAIRY_TALE" and not _has_id(refs, "FAIRY_TALE_BASE"):
        issues.append("truth_mode layer is missing")
    if request.utility_topic and not _has_ref(refs, type_="utility", role="utility_topic"):
        issues.append("utility_topic layer is missing")
    if not _has_ref(refs, type_="language", role="audience_language"):
        issues.append("audience language layer is missing")
    if not _has_ref(refs, type_="language", role="result_language"):
        issues.append("result language layer is missing")
    if request.substyle and not _has_ref(refs, type_="substyle"):
        issues.append("substyle layer is missing")
    if not any(ref.type == "entity" for ref in refs) and not request.prompt_context.unresolved_details:
        issues.append("subject layer or unresolved detail is missing")

    for ref in refs:
        if ref.id not in registry.layers_by_id:
            issues.append(f"fake layer id is present: {ref.id}")
            continue
        layer = registry.get(ref.id)
        if ref.type != layer.type or ref.role != layer.role:
            issues.append(f"layer metadata mismatch: {ref.id}")
        if not ref.source:
            issues.append(f"layer source is missing: {ref.id}")
    for fallback in request.prompt_context.fallback_layers:
        if not fallback.source:
            issues.append(f"fallback source is missing: {fallback.fallback_layer_id}")

    status = "pass" if not issues else "fail_reclassify"
    session.interpretation_state.validation_result = StatusResult(
        status=status,
        issues=issues,
        details={"resolved_layer_ids": [ref.id for ref in refs]},
    )
    session.current_node = "final_parameter_validation"
    return state


def preview(state: GraphState) -> GraphState:
    session = state["session"]
    request = session.normalized_request
    pieces = [
        f"Подготовлю {request.output_count} коротк. детск. текст(а)",
        f"в формате: {request.content_format}",
    ]
    if request.truth_mode == "FAIRY_TALE":
        pieces.append("сказка")
    if request.main_subject == "fox":
        pieces.append("главная героиня лиса")
    if request.target_age:
        pieces.append(f"для {request.target_age} лет")
    if request.utility_topic == "ROAD_SAFETY":
        pieces.append("с мягким обучением безопасности на дороге")
    session.preview_state.preview_text = ", ".join(pieces) + "."
    session.preview_state.shown_to_user = True
    session.preview_state.accepted_by_user = True
    session.preview_state.shown_at = _now()
    session.preview_state.accepted_at = session.preview_state.shown_at
    session.current_node = "preview"
    return state


def prompt_context_preparation(
    state: GraphState,
    registry: PromptRegistry,
    composer: PromptComposer | None = None,
) -> GraphState:
    session = state["session"]
    normalized_context = session.normalized_request.prompt_context
    frozen_context = ExecutionPromptContext(**normalized_context.model_dump())
    frozen_context.frozen_at = _now()
    frozen_context.source_hash = registry.registry_hash
    frozen_context.snapshot_hash = _stable_hash(
        {
            "registry_hash": registry.registry_hash,
            "prompt_context": normalized_context.model_dump(),
            "normalized_request": _request_hash_payload(session.normalized_request),
        }
    )
    frozen_context.body_policy = "metadata_only"
    frozen_context.version = "stage1-v1"
    session.prompt_context = frozen_context

    envelope = execute_prompt_lookup(
        registry,
        resolved_layers=[ref.model_dump() for ref in frozen_context.resolved_layers],
        fallback_layers=[ref.model_dump() for ref in frozen_context.fallback_layers],
        unresolved_details=[detail.model_dump() for detail in frozen_context.unresolved_details],
    )
    session.interpretation_state.execution_lookup_result = StatusResult(
        status=envelope.status,
        issues=list(envelope.issues),
        details=envelope.to_dict(),
    )
    session.stage_prompt_context.entries = []
    if envelope.status != "pass":
        session.current_node = "prompt_context_preparation"
        return state

    stage_context = (composer or PromptComposer(registry)).build_stage_context(
        normalized_request=session.normalized_request,
        prompt_context=session.prompt_context,
        stage="candidate_text_generator",
    )
    session.stage_prompt_context.entries.append(stage_context.durable_entry)
    session.current_node = "prompt_context_preparation"
    return state


def _input_text(session: SessionState, resume_payload: Any) -> tuple[str, bool]:
    raw_text = getattr(session.request, "raw_text", None)
    if raw_text is None:
        raw_text = getattr(session.request, "topic", "")
    parts = [str(raw_text or "")]
    valid_resume_consumed = False
    if isinstance(resume_payload, dict):
        freeform = resume_payload.get("freeform_text")
        if isinstance(freeform, str) and freeform.strip():
            parts.append(freeform)
            valid_resume_consumed = True
        selected = resume_payload.get("selected_option_id")
        if selected and session.pending_interrupt:
            for option in session.pending_interrupt.payload.get("options", []):
                if option.get("id") == selected and option.get("label"):
                    parts.append(str(option["label"]))
                    valid_resume_consumed = True
                    break
    elif isinstance(resume_payload, str) and resume_payload.strip():
        parts.append(resume_payload)
        valid_resume_consumed = True
    return (
        " ".join(part.strip() for part in parts if part and str(part).strip()).strip(),
        valid_resume_consumed,
    )


def _stop_session(session: SessionState, *, reason: str, issues: list[str]) -> None:
    session.is_completed = True
    session.completion_status = CompletionStatus.STOPPED_UNRESOLVED_REQUEST
    session.pending_interrupt = None
    session.interpretation_state.stop_reason = reason
    session.interpretation_state.stop_issues = issues
    session.interpretation_state.stopped_at = _now()


def _extract_normalized_request(session: SessionState, text: str) -> NormalizedRequest:
    current_config = dict(getattr(session.request, "current_config", {}) or {})
    output_count = int(
        getattr(session.request, "count", None)
        or current_config.get("count")
        or session.normalized_request.output_count
    )
    normalized = NormalizedRequest(
        content_format="story",
        output_count=output_count,
        audience_language="ru",
        result_language="ru",
        current_config=current_config,
    )
    lowered = text.casefold()
    if _FAIRY_TALE_RE.search(text):
        normalized.truth_mode = "FAIRY_TALE"
    if any(term in lowered for term in _TEACHING_TERMS):
        normalized.utility_mode = "TEACHING"
    if any(term in lowered for term in _ROAD_TERMS):
        normalized.utility_topic = "ROAD_SAFETY"
        normalized.utility_mode = normalized.utility_mode or "TEACHING"
    age = _AGE_RE.search(text)
    if age:
        normalized.target_age = age.group(1)
    if _FOX_RE.search(text):
        normalized.main_subject = "fox"
        normalized.subjects.append(
            Subject(
                id="fox",
                label="лиса",
                type="animal",
                role="main",
                is_character=True,
                base_species="fox",
            )
        )
    if "русск" in lowered and "народ" in lowered:
        normalized.substyle = "russian_folk_tale"
    if _UNSUPPORTED_RE.search(text) or _IMPOSSIBLE_VISUAL_RE.search(text):
        normalized.hard_details.append("unsupported: hard requirement outside MVP scope")
    return normalized


def _analysis_confidence(request: NormalizedRequest, text: str) -> dict[str, int]:
    if not text.strip():
        return {"input_analysis": 20}
    score = 50
    if request.truth_mode:
        score += 10
    if request.target_age:
        score += 10
    if request.subjects:
        score += 10
    if request.utility_topic:
        score += 10
    return {"input_analysis": min(score, 95)}


def _hint(
    hints: dict[str, Any],
    key: str,
    registry: PromptRegistry,
    terms: list[str],
    *,
    type: str | None = None,
    role: str | None = None,
) -> None:
    candidates = lookup_prompt_metadata(
        registry,
        user_terms=terms,
        type=type,
        role=role,
        fallback=False,
        limit=3,
    )
    if candidates:
        hints[key] = candidates[0].to_dict()


def _meaningful_request(request: NormalizedRequest) -> bool:
    return bool(
        request.truth_mode
        or request.utility_mode
        or request.target_age
        or request.main_subject
        or request.subjects
        or request.hard_details
    )


def _is_complete_request(request: NormalizedRequest) -> bool:
    return bool(
        request.content_format
        and request.truth_mode
        and request.target_age
        and request.output_count
        and request.main_subject
        and request.subjects
    )


def _classification_options(classification: str) -> list[str]:
    if classification == "complete":
        return []
    if classification == "empty_or_meaningless":
        return ["Сказка про лису для 5 лет", "История про безопасность на дороге"]
    if classification == "unsupported_hard_requirement":
        return ["Заменить на оригинального героя без бренда"]
    return ["Уточнить тему, возраст и главного героя"]


def _payload_options(session: SessionState) -> list[dict[str, Any]]:
    reason = session.interpretation_state.clarification_reason
    if reason == "unsupported_hard_requirement":
        return [
            {
                "id": "opt_1",
                "label": "Сказка про оригинальную лису для 5 лет",
                "normalized_patch": {"truth_mode": "FAIRY_TALE", "target_age": "5", "main_subject": "fox"},
            }
        ]
    return [
        {
            "id": "opt_1",
            "label": "Сказка про лису для 5 лет",
            "normalized_patch": {"truth_mode": "FAIRY_TALE", "target_age": "5", "main_subject": "fox"},
        }
    ]


def _create_or_reuse_interrupt(
    state: GraphState,
    *,
    node: str,
    reason: str,
    message: str,
    options: list[dict[str, Any]],
) -> GraphState:
    session = state["session"]
    if session.pending_interrupt and session.pending_interrupt.status == "waiting":
        session.is_completed = False
        session.completion_status = CompletionStatus.WAITING_USER
        session.current_node = node
        return state

    session.interpretation_state.clarification_attempts += 1
    attempt = session.interpretation_state.clarification_attempts
    payload = {
        "type": "request_clarification",
        "reason": reason,
        "message": message,
        "options": options,
        "freeform_allowed": True,
        "attempt": attempt,
        "max_attempts": session.interpretation_state.max_clarification_attempts,
    }
    session.pending_interrupt = PendingInterrupt(
        type="request_clarification",
        node=node,
        status="waiting",
        payload=payload,
        created_at=_now(),
        attempt=attempt,
        resume_schema={
            "selected_option_id": "string|null",
            "freeform_text": "string|null",
        },
    )
    session.is_completed = False
    session.completion_status = CompletionStatus.WAITING_USER
    session.current_node = node
    return state


def _append_ref(refs: list[PromptLayerRef], registry: PromptRegistry, layer_id: str, reason: str) -> None:
    if any(ref.id == layer_id for ref in refs):
        return
    layer = registry.get(layer_id)
    refs.append(
        PromptLayerRef(
            type=layer.type,
            id=layer.id,
            source=layer.source,
            reason=reason,
            role=layer.role,
        )
    )


def _has_ref(
    refs: list[PromptLayerRef],
    *,
    type_: str,
    role: str | None = None,
) -> bool:
    return any(ref.type == type_ and (role is None or ref.role == role) for ref in refs)


def _has_id(refs: list[PromptLayerRef], layer_id: str) -> bool:
    return any(ref.id == layer_id for ref in refs)


def _request_hash_payload(request: NormalizedRequest) -> dict[str, Any]:
    dumped = request.model_dump()
    dumped.pop("prompt_context", None)
    return dumped


def _stable_hash(payload: Any) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat()
