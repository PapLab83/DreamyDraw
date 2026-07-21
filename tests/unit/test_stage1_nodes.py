from pathlib import Path

from src.core.graph.state import to_graph_state
from src.core.nodes.stage1 import (
    candidate_layer_resolution,
    clarification_interrupt,
    empty_input_interrupt,
    final_parameter_validation,
    input_analysis,
    metadata_lookup,
    preview,
    prompt_context_preparation,
    request_classification,
)
from src.core.prompts.registry import PromptRegistry
from src.models.schemas import (
    SessionRequest,
    SessionState,
)

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts" / "cultural_contexts" / "russian_folk"

def test_input_analysis_maps_russian_request_and_clears_resume():
    session = SessionState(
        request=SessionRequest(
            raw_text="Сделай сказку про лису для 5 лет",
            current_config={
                "count": 2,
                "target_age": "5",
                "truth_mode": "FAIRY_TALE",
                "utility_mode": "TEACHING",
            },
        )
    )
    state = to_graph_state(session)
    state["user_input"] = {"freeform_text": "Научи лису безопасности на дороге"}
    session.pending_interrupt = _waiting_interrupt()
    session.interpretation_state.clarification_attempts = 1

    result = input_analysis(state)

    normalized = result["session"].normalized_request
    assert result["user_input"] is None
    assert result["session"].pending_interrupt is None
    assert result["session"].current_node == "input_analysis"
    assert normalized.content_format == "story"
    assert normalized.truth_mode == "FAIRY_TALE"
    assert normalized.utility_mode == "TEACHING"
    assert normalized.utility_topic == "ROAD_SAFETY"
    assert normalized.target_age == "5"
    assert normalized.output_count == 2
    assert normalized.cultural_context == "RUSSIAN_FOLK"
    assert normalized.audience_language == "ru"
    assert normalized.result_language == "ru"
    assert normalized.main_subject == "fox"
    assert normalized.subjects[0].id == "fox"
    assert normalized.subjects[0].label == "лиса"
    assert normalized.subjects[0].type == "animal"
    assert normalized.subjects[0].role == "main"
    assert normalized.subjects[0].is_character is True
    assert result["session"].interpretation_state.confidence["input_analysis"] >= 70


def test_metadata_lookup_writes_only_lookup_hints():
    registry = PromptRegistry.load(PROMPTS_ROOT)
    session = _analyzed_session()
    before_normalized_context = session.normalized_request.prompt_context.model_dump()
    before_top_context = session.prompt_context.model_dump()

    result = metadata_lookup(to_graph_state(session), registry)

    hints = result["session"].interpretation_state.lookup_hints
    assert result["session"].current_node == "metadata_lookup"
    assert hints["content_format"]["layer_id"] == "CONTENT_FORMAT_STORY"
    assert hints["truth_mode"]["layer_id"] == "FAIRY_TALE_BASE"
    assert hints["utility_mode"]["layer_id"] == "UTILITY_TEACHING_BASE"
    assert hints["utility_topic"]["layer_id"] == "UTILITY_TOPIC_ROAD_SAFETY"
    assert hints["age"]["layer_id"] == "AGE_5"
    assert hints["subjects"][0]["layer_id"] == "FAIRY_TALE_ANIMAL_FOX"
    assert session.normalized_request.prompt_context.model_dump() == before_normalized_context
    assert session.prompt_context.model_dump() == before_top_context


def test_input_analysis_does_not_extract_controlled_parameters_from_raw_text():
    session = SessionState(
        request=SessionRequest(
            raw_text="Сделай 2 сказки про лису для 3 лет, поучительные",
            current_config={},
        )
    )

    normalized = input_analysis(to_graph_state(session))["session"].normalized_request

    assert normalized.output_count == 3
    assert normalized.target_age == "5"
    assert normalized.truth_mode == "TRUTH"
    assert normalized.utility_mode == "NARRATIVE"
    assert normalized.cultural_context == "RUSSIAN_FOLK"
    assert normalized.main_subject == "fox"


def test_request_classification_marks_complete_request():
    session = _analyzed_session()

    result = request_classification(to_graph_state(session))

    interpretation = result["session"].interpretation_state
    assert result["session"].current_node == "request_classification"
    assert interpretation.classification == "complete"
    assert interpretation.requires_clarification is False
    assert interpretation.clarification_reason is None


def test_empty_input_produces_durable_clarification_interrupt():
    session = SessionState(request=SessionRequest(raw_text=" "))
    state = request_classification(input_analysis(to_graph_state(session)))

    result = empty_input_interrupt(state)

    session = result["session"]
    assert session.current_node == "empty_input_interrupt"
    assert session.completion_status == "waiting_user"
    assert session.is_completed is False
    assert session.interpretation_state.clarification_attempts == 1
    assert session.pending_interrupt is not None
    assert session.pending_interrupt.type == "request_clarification"
    assert session.pending_interrupt.payload["reason"] == "empty_or_meaningless"
    assert session.pending_interrupt.payload["attempt"] == 1
    assert session.pending_interrupt.payload["freeform_allowed"] is True
    assert session.pending_interrupt.payload["options"]


def test_existing_waiting_interrupt_is_idempotently_reshown():
    session = SessionState(request=SessionRequest(raw_text=""))
    session.interpretation_state.classification = "needs_clarification"
    session.interpretation_state.requires_clarification = True
    session.interpretation_state.clarification_reason = "ambiguous_subject"
    session.interpretation_state.clarification_attempts = 2

    first = clarification_interrupt(to_graph_state(session))["session"]
    second = clarification_interrupt(to_graph_state(first))["session"]

    assert first.pending_interrupt is not None
    assert second.pending_interrupt is not None
    assert first.interpretation_state.clarification_attempts == 3
    assert second.interpretation_state.clarification_attempts == 3
    assert second.pending_interrupt.created_at == first.pending_interrupt.created_at
    assert second.pending_interrupt.payload["attempt"] == 3


def test_resume_consumption_clears_interrupt_without_incrementing_attempts():
    session = SessionState(request=SessionRequest(raw_text=""))
    session.pending_interrupt = _waiting_interrupt(attempt=2)
    session.interpretation_state.clarification_attempts = 2
    session.completion_status = "waiting_user"
    state = to_graph_state(session)
    state["user_input"] = {"selected_option_id": "opt_1"}

    result = input_analysis(state)

    assert result["session"].pending_interrupt is None
    assert result["session"].interpretation_state.clarification_attempts == 2
    assert result["session"].completion_status == "running"
    assert result["session"].current_node == "input_analysis"
    assert result["user_input"] is None


def test_invalid_resume_payload_does_not_clear_waiting_interrupt():
    session = SessionState(request=SessionRequest(raw_text=""))
    session.pending_interrupt = _waiting_interrupt(attempt=2)
    session.interpretation_state.clarification_attempts = 2
    state = to_graph_state(session)
    state["user_input"] = {"selected_option_id": "missing_option"}

    result = input_analysis(state)

    assert result["session"].pending_interrupt is not None
    assert result["session"].pending_interrupt.attempt == 2
    assert result["session"].interpretation_state.clarification_attempts == 2
    assert result["user_input"] is None


def test_request_classification_stop_sets_terminal_state():
    session = SessionState(request=SessionRequest(raw_text=""))
    session.interpretation_state.clarification_attempts = 5
    session.interpretation_state.max_clarification_attempts = 5
    state = input_analysis(to_graph_state(session))

    result = request_classification(state)

    session = result["session"]
    assert session.interpretation_state.classification == "stop"
    assert session.is_completed is True
    assert session.completion_status == "stopped_unresolved_request"
    assert session.pending_interrupt is None
    assert session.interpretation_state.stop_reason == "empty_or_meaningless"
    assert session.interpretation_state.stop_issues
    assert session.interpretation_state.stopped_at


def test_candidate_layer_resolution_writes_canonical_prompt_context_refs():
    registry = PromptRegistry.load(PROMPTS_ROOT)
    session = metadata_lookup(to_graph_state(_analyzed_session()), registry)["session"]

    result = candidate_layer_resolution(to_graph_state(session), registry)

    normalized = result["session"].normalized_request
    refs = normalized.prompt_context.resolved_layers
    assert result["session"].current_node == "candidate_layer_resolution"
    assert [ref.id for ref in refs] == [
        "CONTENT_FORMAT_STORY",
        "FAIRY_TALE_BASE",
        "UTILITY_TEACHING_BASE",
        "UTILITY_TOPIC_ROAD_SAFETY",
        "AGE_5",
        "LANGUAGE_RU_AUDIENCE",
        "LANGUAGE_RU_RESULT",
        "FAIRY_TALE_ANIMAL_FOX",
        "ENTITY_ROAD",
        "ENTITY_TRAFFIC_LIGHT",
    ]
    assert all(ref.source for ref in refs)
    assert {(ref.id, ref.type, ref.role) for ref in refs} >= {
        ("CONTENT_FORMAT_STORY", "format", "content_format"),
        ("FAIRY_TALE_BASE", "truth_mode", None),
        ("UTILITY_TOPIC_ROAD_SAFETY", "utility", "utility_topic"),
        ("FAIRY_TALE_ANIMAL_FOX", "entity", None),
    }
    assert normalized.subjects[0].resolved_layer_id == "FAIRY_TALE_ANIMAL_FOX"
    assert result["session"].prompt_context.resolved_layers == []
    layer_result = result["session"].interpretation_state.layer_resolution_result
    assert layer_result.status == "resolved"
    assert layer_result.details["resolved_layer_ids"] == [ref.id for ref in refs]


def test_candidate_layer_resolution_preserves_unknown_modes_as_unresolved_details():
    registry = PromptRegistry.load(PROMPTS_ROOT)
    session = _analyzed_session()
    request = session.normalized_request
    request.truth_mode = "UNKNOWN_TRUTH"
    request.utility_mode = "UNKNOWN_UTILITY"
    request.utility_topic = "UNKNOWN_TOPIC"

    result = candidate_layer_resolution(to_graph_state(session), registry)

    normalized = result["session"].normalized_request
    labels = {detail.label for detail in normalized.prompt_context.unresolved_details}
    assert result["session"].interpretation_state.layer_resolution_result.status == "resolved"
    assert {"truth_mode UNKNOWN_TRUTH", "utility_mode UNKNOWN_UTILITY", "utility_topic UNKNOWN_TOPIC"} <= labels
    assert "CONTENT_FORMAT_STORY" in {ref.id for ref in normalized.prompt_context.resolved_layers}

    validation = final_parameter_validation(result, registry)["session"].interpretation_state.validation_result
    assert validation.status == "fail_reclassify"
    assert "truth_mode layer is missing" in validation.issues
    assert "utility_topic layer is missing" in validation.issues


def test_final_parameter_validation_reclassifies_single_unknown_utility_mode():
    registry = PromptRegistry.load(PROMPTS_ROOT)
    session = _analyzed_session()
    request = session.normalized_request
    request.truth_mode = "FAIRY_TALE"
    request.utility_mode = "UNKNOWN_UTILITY"
    request.utility_topic = None

    state = candidate_layer_resolution(to_graph_state(session), registry)

    labels = {detail.label for detail in state["session"].normalized_request.prompt_context.unresolved_details}
    validation = final_parameter_validation(state, registry)["session"].interpretation_state.validation_result
    assert "utility_mode UNKNOWN_UTILITY" in labels
    assert validation.status == "fail_reclassify"
    assert "unsupported normalized utility_mode: utility_mode UNKNOWN_UTILITY" in validation.issues


def test_final_parameter_validation_passes_for_fully_resolved_request():
    registry = PromptRegistry.load(PROMPTS_ROOT)
    state = candidate_layer_resolution(
        metadata_lookup(to_graph_state(_analyzed_session()), registry),
        registry,
    )

    result = final_parameter_validation(state, registry)

    validation = result["session"].interpretation_state.validation_result
    assert result["session"].current_node == "final_parameter_validation"
    assert validation.status == "pass"
    assert validation.issues == []


def test_final_parameter_validation_reclassifies_missing_utility_topic_layer():
    registry = PromptRegistry.load(PROMPTS_ROOT)
    state = candidate_layer_resolution(
        metadata_lookup(to_graph_state(_analyzed_session()), registry),
        registry,
    )
    request = state["session"].normalized_request
    request.prompt_context.resolved_layers = [
        ref
        for ref in request.prompt_context.resolved_layers
        if ref.id != "UTILITY_TOPIC_ROAD_SAFETY"
    ]

    result = final_parameter_validation(state, registry)

    validation = result["session"].interpretation_state.validation_result
    assert validation.status == "fail_reclassify"
    assert "utility_topic layer is missing" in validation.issues


def test_preview_writes_concise_russian_text_without_image_promise():
    session = _fully_resolved_session()

    result = preview(to_graph_state(session))

    preview_state = result["session"].preview_state
    assert result["session"].current_node == "preview"
    assert preview_state.shown_to_user is True
    assert preview_state.accepted_by_user is True
    assert preview_state.preview_text is not None
    assert "сказк" in preview_state.preview_text.casefold()
    assert "лиса" in preview_state.preview_text.casefold()
    assert "5" in preview_state.preview_text
    assert "картин" not in preview_state.preview_text.casefold()
    assert "изображ" not in preview_state.preview_text.casefold()


def test_prompt_context_preparation_copies_verifies_and_creates_stage_entry():
    registry = PromptRegistry.load(PROMPTS_ROOT)
    session = _fully_resolved_session()

    result = prompt_context_preparation(to_graph_state(session), registry)

    session = result["session"]
    assert session.current_node == "prompt_context_preparation"
    assert session.prompt_context.resolved_layers == (
        session.normalized_request.prompt_context.resolved_layers
    )
    assert session.prompt_context.frozen_at
    assert session.prompt_context.source_hash == registry.registry_hash
    assert session.prompt_context.snapshot_hash
    assert session.prompt_context.body_policy == "metadata_only"
    assert session.prompt_context.cultural_context == "RUSSIAN_FOLK"
    assert session.prompt_context.prompt_root == registry.root.as_posix()
    assert session.interpretation_state.execution_lookup_result.status == "pass"
    assert len(session.stage_prompt_context.entries) == 1
    entry = session.stage_prompt_context.entries[0]
    assert entry.stage == "candidate_text_generator"
    assert entry.layer_ids[-1] == "STAGE_CANDIDATE_TEXT_GENERATOR"
    assert entry.body_policy == "lazy_not_persisted"


def test_prompt_context_preparation_fails_when_resolved_layer_source_is_missing():
    registry = PromptRegistry.load(PROMPTS_ROOT)
    session = _fully_resolved_session()
    session.normalized_request.prompt_context.resolved_layers[0].source = None

    result = prompt_context_preparation(to_graph_state(session), registry)

    session = result["session"]
    assert session.interpretation_state.execution_lookup_result.status == "fail_reresolve"
    assert session.interpretation_state.execution_lookup_result.details["failure_type"] == (
        "missing_source"
    )
    assert session.stage_prompt_context.entries == []


def _analyzed_session() -> SessionState:
    session = SessionState(
        request=SessionRequest(
            raw_text="Сделай сказку про лису для 5 лет и научи безопасности на дороге",
            current_config={
                "count": 2,
                "target_age": "5",
                "truth_mode": "FAIRY_TALE",
                "utility_mode": "TEACHING",
            },
        )
    )
    return input_analysis(to_graph_state(session))["session"]


def _fully_resolved_session() -> SessionState:
    registry = PromptRegistry.load(PROMPTS_ROOT)
    state = candidate_layer_resolution(
        metadata_lookup(to_graph_state(_analyzed_session()), registry),
        registry,
    )
    return final_parameter_validation(state, registry)["session"]


def _waiting_interrupt(attempt: int = 1):
    from src.models.schemas import PendingInterrupt

    return PendingInterrupt(
        type="request_clarification",
        node="clarification_interrupt",
        status="waiting",
        payload={
            "type": "request_clarification",
            "reason": "ambiguous_subject",
            "message": "Нужно уточнить запрос, чтобы собрать исполнимую задачу.",
            "options": [{"id": "opt_1", "label": "Сказка про лису для 5 лет"}],
            "freeform_allowed": True,
            "attempt": attempt,
            "max_attempts": 5,
        },
        attempt=attempt,
        resume_schema={
            "selected_option_id": "string|null",
            "freeform_text": "string|null",
        },
    )
