from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from src.config.settings import settings
from src.core.generation_config import effective_current_config, resolve_controlled_generation_config
from src.core.graph.state import GraphState
from src.core.interpretation.style_match import resolve_style_from_text
from src.core.prompts.composer import PromptComposer
from src.core.prompts.lookup import execute_prompt_lookup, lookup_prompt_metadata
from src.core.prompts.registry import PromptRegistry
from src.models.schemas import (
    CompletionStatus,
    ExecutionPromptContext,
    CharacterProfile,
    NormalizedPromptContext,
    NormalizedRequest,
    PendingInterrupt,
    PromptFallbackLayer,
    PromptLayerRef,
    PromptUnresolvedDetail,
    SessionState,
    StatusResult,
    Subject,
    SubjectContinuityPolicy,
)

_SUPPORTED_LAYER_IDS = {
    "content_format": "CONTENT_FORMAT_STORY",
    "truth_mode:TRUTH": "TRUTH_BASE",
    "truth_mode:FAIRY_TALE": "FAIRY_TALE_BASE",
    "utility_mode:NARRATIVE": "UTILITY_NARRATIVE_BASE",
    "utility_mode:TEACHING": "UTILITY_TEACHING_BASE",
    "utility_topic:ROAD_SAFETY": "UTILITY_TOPIC_ROAD_SAFETY",
    "utility_topic:HAND_WASHING_AFTER_WALK": "UTILITY_TOPIC_HAND_WASHING_AFTER_WALK",
    "utility_topic:STRANGERS_AND_CANDY": "UTILITY_TOPIC_STRANGERS_AND_CANDY",
    "age:3": "AGE_3",
    "age:5": "AGE_5",
    "audience_language": "LANGUAGE_RU_AUDIENCE",
    "result_language": "LANGUAGE_RU_RESULT",
    "substyle:naturalistic_animal_story": "NATURALISTIC_ANIMAL_STORY",
    "substyle:russian_folk_tale": "RUSSIAN_FOLK_TALE",
    "substyle:CHUKOVSKY_STYLE": "CHUKOVSKY_STYLE",
    "entity:child": "ENTITY_CHILD",
    "entity:hands": "ENTITY_HANDS",
    "entity:soap": "ENTITY_SOAP",
    "entity:road": "ENTITY_ROAD",
    "entity:traffic_light": "ENTITY_TRAFFIC_LIGHT",
    "entity:stranger": "ENTITY_STRANGER",
    "entity:candy": "ENTITY_CANDY",
    "entity:caring_adult": "ENTITY_CARING_ADULT",
    "subject:TRUTH:fox": "TRUTH_ANIMAL_FOX",
    "subject:FAIRY_TALE:fox": "FAIRY_TALE_ANIMAL_FOX",
    "subject:TRUTH:hedgehog": "TRUTH_ANIMAL_HEDGEHOG",
    "subject:FAIRY_TALE:hedgehog": "FAIRY_TALE_ANIMAL_HEDGEHOG",
    "subject:TRUTH:hare": "TRUTH_ANIMAL_HARE",
    "subject:FAIRY_TALE:hare": "FAIRY_TALE_ANIMAL_HARE",
    "subject:TRUTH:squirrel": "TRUTH_ANIMAL_SQUIRREL",
    "subject:FAIRY_TALE:squirrel": "FAIRY_TALE_ANIMAL_SQUIRREL",
    "subject:TRUTH:parrot": "TRUTH_ANIMAL_PARROT",
}

_ROAD_TERMS = ("безопасность", "дорог", "переход", "светофор")
_HAND_WASHING_TERMS = ("мыть", "мытьё", "мытье", "рук", "мыло", "прогулк")
_FOX_RE = re.compile(r"\b(лиса|лис|лису|лисой|лисе|лисичка|лисичку|лисица|лисицу)\b", re.I)
_HEDGEHOG_RE = re.compile(r"\b(ёжик|ежик|ежа|ежом|ёжика|ежика)\b", re.I)
_HARE_RE = re.compile(r"\b(заяц|зайца|зайцу|зайцем|зайчик|зайца)\b", re.I)
_SQUIRREL_RE = re.compile(r"\b(белка|белку|белки|бельчонок|бельчонка|белчонок|белчонка)\b", re.I)
_PARROT_RE = re.compile(r"\b(попугай|попугая|какаду)\b", re.I)
_SUN_RE = re.compile(r"\b(солнце|солнца|солнцу)\b", re.I)
_WIND_RE = re.compile(r"\b(ветер|ветра|ветру|ветром)\b", re.I)
_UNSUPPORTED_RE = re.compile(
    r"\b(дисней|disney|микки|mickey|человек[- ]?паук|spider[- ]?man|гарри поттер|harry potter)\b",
    re.I,
)
_SOFT_STYLE_RE = re.compile(r"в\s+([^.!?]*(?:импрессионистичн|акварельн)[^.!?]*)", re.I)
_CHARACTER_MARKER_RE = re.compile(
    r"\b(герой|персонаж|назови|зовут|имя)\b",
    re.I,
)
_YOUNG_SPECIES_TRAIT_RE = re.compile(
    r"маленьк(?:ий|ая|ое|ого|ую)\s+(?:\b\w+\b\s+){0,2}(?:бельчонок|белчонок|зайчонок|лисичк|ежонок|еженок)",
    re.I,
)
_FANTASTIC_TRUTH_RE = re.compile(
    r"(волшебн|магическ|колдов|летала?\s+на\s+волшебн|говор(?:ит|ила?)\s+человеческ)",
    re.I,
)
_IMPOSSIBLE_VISUAL_RE = re.compile(
    r"\b(точн(?:ая|ое|ый)\s+картин|фотореалистич|анимаци|мультфильм|сгенерируй\s+картин)\b",
    re.I,
)


_SUBSTYLE_SLUG_TO_LAYER_ID = {
    "russian_folk_tale": "RUSSIAN_FOLK_TALE",
    "naturalistic_animal_story": "NATURALISTIC_ANIMAL_STORY",
}


def input_analysis(state: GraphState, registry: PromptRegistry | None = None) -> GraphState:
    session = state["session"]
    resume_payload = state.get("user_input")
    text, valid_resume_consumed = _input_text(session, resume_payload)

    if valid_resume_consumed:
        session.pending_interrupt = None
        session.completion_status = CompletionStatus.RUNNING
    state["user_input"] = None

    normalized = _extract_normalized_request(session, text, registry=registry)
    session.normalized_request = normalized
    session.interpretation_state.confidence.update(_analysis_confidence(normalized, text))
    session.current_node = "input_analysis"
    return {"session": session, "user_input": None}


def metadata_lookup(state: GraphState, registry: PromptRegistry) -> GraphState:
    session = state["session"]
    request = session.normalized_request

    hints: dict[str, Any] = {}
    _hint(hints, "content_format", registry, ["story"], type="format", role="content_format")
    if request.truth_mode:
        truth_terms = {
            "TRUTH": ["TRUTH", "правдиво"],
            "FAIRY_TALE": ["FAIRY_TALE", "сказка"],
        }
        _hint(hints, "truth_mode", registry, truth_terms.get(request.truth_mode, [request.truth_mode]), type="truth_mode")
    if request.utility_mode:
        utility_terms = {
            "NARRATIVE": ["NARRATIVE", "история"],
            "TEACHING": ["TEACHING", "обучение"],
        }
        _hint(hints, "utility_mode", registry, utility_terms.get(request.utility_mode, [request.utility_mode]), type="utility", role="utility_mode")
    if request.utility_topic:
        topic_terms = {
            "ROAD_SAFETY": ["ROAD_SAFETY", "дорога"],
            "HAND_WASHING_AFTER_WALK": ["HAND_WASHING_AFTER_WALK", "руки"],
            "STRANGERS_AND_CANDY": ["STRANGERS_AND_CANDY", "незнакомец конфета"],
        }
        _hint(hints, "utility_topic", registry, topic_terms.get(request.utility_topic, [request.utility_topic]), type="utility", role="utility_topic")
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
    style_message, style_options = _unsupported_style_interrupt_payload(session)
    if attempts < session.interpretation_state.max_clarification_attempts:
        return _create_or_reuse_interrupt(
            state,
            node="unsupported_interrupt_or_stop",
            reason="unsupported_hard_requirement",
            message=style_message
            or "Часть запроса пока нельзя выполнить буквально. Можно выбрать безопасную замену.",
            options=style_options
            or [
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
    if request.truth_mode:
        _append_supported_ref_or_unresolved(
            refs,
            unresolved,
            registry,
            f"truth_mode:{request.truth_mode}",
            f"truth_mode={request.truth_mode}",
            label=f"truth_mode {request.truth_mode}",
            type_="truth_mode",
        )
    if request.utility_mode:
        _append_supported_ref_or_unresolved(
            refs,
            unresolved,
            registry,
            f"utility_mode:{request.utility_mode}",
            f"utility_mode={request.utility_mode}",
            label=f"utility_mode {request.utility_mode}",
            type_="utility_mode",
        )
    if request.utility_topic:
        _append_supported_ref_or_unresolved(
            refs,
            unresolved,
            registry,
            f"utility_topic:{request.utility_topic}",
            f"utility_topic={request.utility_topic}",
            label=f"utility_topic {request.utility_topic}",
            type_="utility_topic",
        )
    if request.target_age in {"3", "5"}:
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS[f"age:{request.target_age}"], f"target_age={request.target_age}")
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
    if request.truth_mode == "TRUTH" and any(subject.type == "animal" for subject in request.subjects):
        _append_ref(
            refs,
            registry,
            _SUPPORTED_LAYER_IDS["substyle:naturalistic_animal_story"],
            "truth animal story style",
        )
    if request.substyle:
        substyle_layer_id = _resolve_substyle_layer_id(request.substyle, registry)
        if substyle_layer_id:
            _append_ref(refs, registry, substyle_layer_id, f"substyle={request.substyle}")

    for subject in request.subjects:
        layer_key = f"subject:{request.truth_mode}:{subject.base_species or subject.id}"
        if layer_key in _SUPPORTED_LAYER_IDS:
            layer_id = _SUPPORTED_LAYER_IDS[layer_key]
            if subject.id == "parrot" and subject.unresolved_detail == "какаду":
                continue
            _append_ref(refs, registry, layer_id, f"subject={subject.id}")
            subject.resolved_layer_id = layer_id
        elif subject.label:
            unresolved.append(
                PromptUnresolvedDetail(
                    label=subject.label,
                    type="subject",
                    instruction="Использовать как свободную деталь, не подставляя fake layer id.",
                )
            )
            subject.unresolved_detail = subject.label

    fallback_layers: list[PromptFallbackLayer] = []
    for subject in request.subjects:
        if subject.id == "parrot" and subject.unresolved_detail == "какаду":
            fallback_layers.append(
                PromptFallbackLayer(
                    requested="какаду",
                    fallback_layer_id=_SUPPORTED_LAYER_IDS["subject:TRUTH:parrot"],
                    source=registry.get(_SUPPORTED_LAYER_IDS["subject:TRUTH:parrot"]).source,
                    reason="cockatoo-specific seed layer is unavailable; use parrot fallback",
                )
            )
            unresolved.append(
                PromptUnresolvedDetail(
                    label="какаду",
                    type="subject_detail",
                    instruction="Сохранить какаду как свободную деталь, не обещая отдельный layer id.",
                )
            )

    _append_support_entity_refs(refs, registry, request)
    for detail in request.hard_details:
        if detail in {"winter", "forest"}:
            unresolved.append(
                PromptUnresolvedDetail(
                    label=detail,
                    type="setting",
                    instruction="Сохранить как контекстную деталь сценария.",
                )
            )

    request.prompt_context = NormalizedPromptContext(
        resolved_layers=refs,
        fallback_layers=fallback_layers,
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
    if request.truth_mode not in {"TRUTH", "FAIRY_TALE"}:
        issues.append("truth_mode is missing or unsupported")
    if request.utility_mode not in {"NARRATIVE", "TEACHING"}:
        issues.append("utility_mode is missing or unsupported")
    if request.target_age not in {"3", "5"}:
        issues.append("target_age is missing or unsupported")
    if request.cultural_context != "RUSSIAN_FOLK":
        issues.append("cultural_context is missing or unsupported")
    if not 1 <= request.output_count <= settings.MAX_COUNT:
        issues.append(f"output_count must be between 1 and {settings.MAX_COUNT}")
    if not request.main_subject or not request.subjects:
        issues.append("main subject is missing")
    if not _has_ref(refs, type_="format", role="content_format"):
        issues.append("content_format layer is missing")
    if request.truth_mode and not _has_ref(refs, type_="truth_mode"):
        issues.append("truth_mode layer is missing")
    if request.utility_mode and not _has_ref(refs, type_="utility", role="utility_mode"):
        issues.append("utility_mode layer is missing")
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
    for detail in request.prompt_context.unresolved_details:
        if detail.type in {"truth_mode", "utility_mode", "utility_topic"}:
            issues.append(f"unsupported normalized {detail.type}: {detail.label}")

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
    pieces.append(f"контекст: {request.cultural_context}")
    pieces.append(f"режим назначения: {request.utility_mode}")
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
    frozen_context.cultural_context = session.normalized_request.cultural_context
    frozen_context.prompt_root = registry.root.as_posix()
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


def _extract_normalized_request(
    session: SessionState,
    text: str,
    *,
    registry: PromptRegistry | None = None,
) -> NormalizedRequest:
    current_config = effective_current_config(
        dict(getattr(session.request, "current_config", {}) or {})
    )
    controlled = resolve_controlled_generation_config(current_config)
    if hasattr(session.request, "current_config"):
        session.request.current_config = current_config
    normalized = NormalizedRequest(
        content_format="story",
        output_count=controlled.output_count,
        target_age=controlled.target_age,
        truth_mode=controlled.truth_mode.value,
        cultural_context=controlled.cultural_context.value,
        utility_mode=controlled.utility_mode.value,
        audience_language="ru",
        result_language="ru",
        current_config=current_config,
    )
    lowered = text.casefold()
    if normalized.utility_mode == "TEACHING":
        if any(term in lowered for term in _ROAD_TERMS):
            normalized.utility_topic = "ROAD_SAFETY"
        if "рук" in lowered and any(term in lowered for term in _HAND_WASHING_TERMS):
            normalized.utility_topic = "HAND_WASHING_AFTER_WALK"
        if "незнаком" in lowered and "конфет" in lowered:
            normalized.utility_topic = "STRANGERS_AND_CANDY"
    if _FOX_RE.search(text):
        _add_subject(
            normalized,
            "fox",
            "лиса",
            "animal",
            is_character=_default_animal_is_character(normalized, text, lowered),
        )
    if _HEDGEHOG_RE.search(text):
        _add_subject(
            normalized,
            "hedgehog",
            "ёжик",
            "animal",
            is_character=_default_animal_is_character(normalized, text, lowered),
        )
    if _HARE_RE.search(text):
        _add_subject(
            normalized,
            "hare",
            "заяц",
            "animal",
            is_character=_default_animal_is_character(normalized, text, lowered),
        )
    if _SQUIRREL_RE.search(text):
        _add_subject(
            normalized,
            "squirrel",
            "белка",
            "animal",
            is_character=_default_animal_is_character(normalized, text, lowered),
        )
    if _PARROT_RE.search(text):
        subject = _add_subject(
            normalized,
            "parrot",
            "попугай",
            "animal",
            is_character=_default_animal_is_character(normalized, text, lowered),
        )
        if "какаду" in lowered:
            subject.unresolved_detail = "какаду"
    if _SUN_RE.search(text):
        _add_subject(normalized, "sun", "солнце", "nature", role="main")
        normalized.prompt_context.unresolved_details.append(
            PromptUnresolvedDetail(label="солнце", type="nature_subject", instruction="Сохранить как свободный nature subject.")
        )
    if _WIND_RE.search(text):
        _add_subject(normalized, "wind", "ветер", "nature", role="required")
        normalized.prompt_context.unresolved_details.append(
            PromptUnresolvedDetail(label="ветер", type="nature_subject", instruction="Сохранить как свободный nature subject.")
        )
    if normalized.utility_topic in {"HAND_WASHING_AFTER_WALK", "STRANGERS_AND_CANDY", "ROAD_SAFETY"} and not normalized.subjects:
        _add_subject(normalized, "child", "ребёнок", "person", is_character=True)
    _apply_style_resolution(normalized, text, registry)
    if "русск" in lowered and "народ" in lowered and not normalized.substyle:
        normalized.substyle = "RUSSIAN_FOLK_TALE"
    if "зимой" in lowered or "зима" in lowered:
        normalized.setting.season = "winter"
        normalized.hard_details.append("winter")
    if "лес" in lowered:
        normalized.setting.place = "forest"
        normalized.hard_details.append("forest")
    if "герои не исчезали" in lowered or "не исчезали" in lowered:
        required = [subject.id for subject in normalized.subjects]
        normalized.subject_continuity_policy = SubjectContinuityPolicy(
            mode="preserve_required_subjects",
            required_subjects=required,
            coverage="item_level",
            allowed_distribution="all_items",
            can_mix_subjects_in_one_item=True,
            can_introduce_new_subjects=True,
            can_replace_required_subjects=False,
        )
    if "тим" in lowered and any(subject.id == "squirrel" for subject in normalized.subjects):
        for subject in normalized.subjects:
            if subject.id == "squirrel":
                subject.is_character = True
        normalized.character_profile = CharacterProfile(
            name="Тим",
            base_subject_id="squirrel",
            stable_traits=["смелый"] if "смел" in lowered else [],
            stable_details=["любит жёлуди"] if "жёлуд" in lowered or "желуд" in lowered else [],
        )
        normalized.hard_details.extend(["character name: Тим", "character trait: смелый", "character detail: любит жёлуди"])
        normalized.subject_continuity_policy.required_subjects = ["squirrel"]
        normalized.subject_continuity_policy.can_replace_required_subjects = False
    soft_style = _SOFT_STYLE_RE.search(text)
    if soft_style and "строго" not in lowered and "обязательно" not in lowered:
        normalized.soft_preferences.append(soft_style.group(1).strip())
    if soft_style and ("строго" in lowered or "обязательно" in lowered):
        normalized.hard_details.append("unsupported: hard style requirement outside MVP scope")
    if _UNSUPPORTED_RE.search(text) or _IMPOSSIBLE_VISUAL_RE.search(text):
        normalized.hard_details.append("unsupported: hard requirement outside MVP scope")
    if normalized.truth_mode == "TRUTH" and ("обязательно" in lowered or "строго" in lowered) and _FANTASTIC_TRUTH_RE.search(text):
        normalized.hard_details.append("unsupported: fantastic hard detail contradicts TRUTH")
    return normalized


def _default_animal_is_character(
    normalized: NormalizedRequest,
    text: str,
    lowered: str,
) -> bool:
    if normalized.truth_mode != "TRUTH":
        return True
    return _has_explicit_character_markers(text, lowered)


def _has_explicit_character_markers(text: str, lowered: str) -> bool:
    if _CHARACTER_MARKER_RE.search(text):
        return True
    if _YOUNG_SPECIES_TRAIT_RE.search(text):
        return True
    if "тим" in lowered and _SQUIRREL_RE.search(text):
        return True
    return False


def _draft_style_applicability(normalized: NormalizedRequest) -> dict[str, str]:
    applicability: dict[str, str] = {
        "content_formats": normalized.content_format,
    }
    if normalized.truth_mode:
        applicability["truth_modes"] = normalized.truth_mode
    if normalized.utility_mode:
        applicability["utility_modes"] = normalized.utility_mode
    if normalized.target_age:
        applicability["ages"] = normalized.target_age
    return applicability


def _apply_style_resolution(
    normalized: NormalizedRequest,
    text: str,
    registry: PromptRegistry | None,
) -> None:
    if registry is None:
        return

    outcome = resolve_style_from_text(
        registry,
        text,
        applicability=_draft_style_applicability(normalized),
    )
    if outcome is None:
        return

    if outcome.resolved and outcome.layer_id:
        normalized.substyle = outcome.layer_id
        return

    if outcome.is_applicability_conflict:
        normalized.hard_details.append(
            "unsupported: style applicability conflict "
            f"({outcome.phrase.raw} / {normalized.truth_mode})"
        )
        return

    if outcome.is_hard_unsupported:
        normalized.hard_details.append(
            f"unsupported: hard style requirement outside MVP scope ({outcome.phrase.raw})"
        )
        return

    if not outcome.phrase.is_hard_requirement:
        normalized.soft_preferences.append(outcome.phrase.raw)


def _resolve_substyle_layer_id(substyle: str, registry: PromptRegistry) -> str | None:
    if substyle in registry.layers_by_id:
        layer = registry.get(substyle)
        if layer.type in {"style", "substyle"}:
            return substyle
    slug_layer_id = _SUBSTYLE_SLUG_TO_LAYER_ID.get(substyle)
    if slug_layer_id and slug_layer_id in registry.layers_by_id:
        return slug_layer_id
    legacy_key = f"substyle:{substyle}"
    return _SUPPORTED_LAYER_IDS.get(legacy_key)


def _unsupported_style_interrupt_payload(
    session: SessionState,
) -> tuple[str | None, list[dict[str, Any]] | None]:
    request = session.normalized_request
    style_detail = next(
        (
            detail
            for detail in request.hard_details
            if "unsupported: hard style requirement" in detail
            or "unsupported: style applicability conflict" in detail
        ),
        None,
    )
    if style_detail is None:
        return None, None

    style_label = _extract_style_label_from_hard_detail(style_detail)
    subject_label = request.main_subject or "героя"
    if subject_label == "fox":
        subject_label = "лису"
    elif subject_label == "hedgehog":
        subject_label = "ёжика"

    message = (
        f"Стиль «{style_label}» пока не поддерживается в MVP. "
        "Мы можем сделать сказку без этого стиля или в базовой сказочной манере."
    )
    options = [
        {
            "id": "opt_no_style",
            "label": "Сказка без особого стиля",
            "normalized_patch": {
                "truth_mode": request.truth_mode or "FAIRY_TALE",
                "target_age": request.target_age or "5",
                "main_subject": request.main_subject,
            },
        },
        {
            "id": "opt_fairy_base",
            "label": f"Обычная сказка про {subject_label}",
            "normalized_patch": {
                "truth_mode": "FAIRY_TALE",
                "target_age": request.target_age or "5",
                "main_subject": request.main_subject or "fox",
            },
        },
    ]
    return message, options


def _extract_style_label_from_hard_detail(detail: str) -> str:
    if "(" in detail and detail.endswith(")"):
        inner = detail[detail.rindex("(") + 1 : -1]
        if " / " in inner:
            return inner.split(" / ", maxsplit=1)[0].strip()
        return inner.strip()
    return "запрошенный стиль"


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
        request.main_subject
        or request.subjects
        or request.hard_details
    )


def _meaningful_text(lowered: str) -> bool:
    return any(
        marker in lowered
        for marker in (
            "истори",
            "сказ",
            "ёж",
            "еж",
            "лис",
            "зая",
            "бел",
            "попуг",
            "какаду",
            "солн",
            "ветер",
            "рук",
            "дорог",
            "незнаком",
            "конфет",
        )
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
        _, style_options = _unsupported_style_interrupt_payload(session)
        if style_options:
            return style_options
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


def _add_subject(
    normalized: NormalizedRequest,
    subject_id: str,
    label: str,
    type_: str,
    *,
    role: str = "main",
    is_character: bool = False,
) -> Subject:
    for existing in normalized.subjects:
        if existing.id == subject_id:
            return existing
    if normalized.main_subject is None and role in {"main", "required"}:
        normalized.main_subject = subject_id
        actual_role = "main"
    else:
        actual_role = "required" if role == "main" else role
    subject = Subject(
        id=subject_id,
        label=label,
        type=type_,
        role=actual_role,
        is_character=is_character,
        base_species=subject_id if type_ == "animal" else None,
    )
    normalized.subjects.append(subject)
    return subject


def _append_support_entity_refs(refs: list[PromptLayerRef], registry: PromptRegistry, request: NormalizedRequest) -> None:
    if request.utility_topic == "HAND_WASHING_AFTER_WALK":
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["entity:hands"], "utility_topic=HAND_WASHING_AFTER_WALK")
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["entity:soap"], "utility_topic=HAND_WASHING_AFTER_WALK")
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["entity:child"], "utility_topic=HAND_WASHING_AFTER_WALK")
    if request.utility_topic == "ROAD_SAFETY":
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["entity:road"], "utility_topic=ROAD_SAFETY")
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["entity:traffic_light"], "utility_topic=ROAD_SAFETY")
    if request.utility_topic == "STRANGERS_AND_CANDY":
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["entity:stranger"], "utility_topic=STRANGERS_AND_CANDY")
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["entity:candy"], "utility_topic=STRANGERS_AND_CANDY")
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["entity:caring_adult"], "utility_topic=STRANGERS_AND_CANDY")
        _append_ref(refs, registry, _SUPPORTED_LAYER_IDS["entity:child"], "utility_topic=STRANGERS_AND_CANDY")


def _append_supported_ref_or_unresolved(
    refs: list[PromptLayerRef],
    unresolved: list[PromptUnresolvedDetail],
    registry: PromptRegistry,
    key: str,
    reason: str,
    *,
    label: str,
    type_: str,
) -> None:
    layer_id = _SUPPORTED_LAYER_IDS.get(key)
    if layer_id is None:
        unresolved.append(
            PromptUnresolvedDetail(
                label=label,
                type=type_,
                instruction="Unsupported normalized value; reclassify or clarify instead of fabricating a layer.",
            )
        )
        return
    _append_ref(refs, registry, layer_id, reason)


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
