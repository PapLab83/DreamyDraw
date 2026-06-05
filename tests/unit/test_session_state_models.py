import pytest
from pydantic import ValidationError

from src.models.schemas import (
    ApprovedText,
    CandidateText,
    CompletionStatus,
    PromptLayerRef,
    SessionRequest,
    SessionState,
    StagePromptContextEntry,
    StageStatusValue,
    PendingInterrupt,
    ValidatedCandidateVersion,
)
from src.storage.json_storage import JSONStorage


def test_session_state_defaults_are_explicit_and_recoverable():
    session = SessionState(
        request={
            "raw_text": "Сделай 5 коротких историй про ёжика зимой.",
            "current_config": {"image_style": "cartoon"},
            "user_context": {"available": False},
        }
    )

    assert session.completion_status == CompletionStatus.RUNNING
    assert session.normalized_request.user_context.available is False
    assert session.normalized_request.user_context.defaults == {}
    assert session.interpretation_state.max_clarification_attempts == 5
    assert session.interpretation_state.validation_result.status == "not_started"
    assert session.interpretation_state.execution_lookup_result.status == "not_started"
    assert session.stage_status.candidate_text_generator.status == StageStatusValue.NOT_STARTED
    assert session.stage_status.validation_loop.status == "not_started"
    assert session.candidate_texts == []
    assert session.approved_texts == []
    assert session.shortage.status == "not_started"
    assert session.pending_interrupt is None
    assert session.stage_prompt_context.entries == []
    assert session.validation_loop_state.current_rank_index is None
    assert session.validation_loop_state.active_version_origin is None
    assert session.validation_loop_state.active_text_source is None
    assert session.validation_loop_state.accepted_count == 0
    assert session.validation_loop_state.selector_eligible_unique_accepted_count == 0


def test_normalized_request_excludes_runtime_interpretation_metadata():
    session = SessionState(request=SessionRequest(raw_text="История про лису."))
    dumped = session.normalized_request.model_dump()

    forbidden_keys = {
        "confidence",
        "requires_clarification",
        "preview_text",
        "frozen_at",
        "source_hash",
        "snapshot_hash",
        "trace_refs",
        "body_policy",
    }

    assert forbidden_keys.isdisjoint(dumped)
    assert set(dumped["prompt_context"]) == {
        "resolved_layers",
        "fallback_layers",
        "unresolved_details",
    }


@pytest.mark.parametrize("confidence", [-1, 101])
def test_interpretation_confidence_rejects_values_outside_0_100(confidence):
    with pytest.raises(ValidationError):
        SessionState(
            request=SessionRequest(raw_text="История про лису."),
            interpretation_state={"confidence": {"truth_mode": confidence}},
        )


def test_json_storage_round_trips_new_stage_1_2_state(tmp_path):
    storage = JSONStorage(base_dir=str(tmp_path))
    session = SessionState(
        session_id="wave-1-round-trip",
        request=SessionRequest(
            raw_text="Сделай короткую сказку про белку.",
            current_config={"truth_mode": "FAIRY_TALE"},
            user_context={"available": False},
        ),
    )
    session.normalized_request.main_subject = "белка"
    session.normalized_request.output_count = 1
    session.normalized_request.prompt_context.resolved_layers.append(
        PromptLayerRef(
            type="truth_mode",
            id="FAIRY_TALE_BASE",
            source="truth_modes/FAIRY_TALE/BASE.md",
            reason="truth_mode=FAIRY_TALE",
        )
    )
    session.prompt_context.version = "2026-06-05"
    session.prompt_context.source_hash = "registry-hash"
    session.stage_prompt_context.entries.append(
        StagePromptContextEntry(
            stage="candidate_text_generator",
            source_prompt_context_hash="registry-hash",
            stage_context_hash="stage-context-hash",
            layer_ids=["FAIRY_TALE_BASE"],
            fallback_layer_ids=[],
            unresolved_detail_labels=[],
            body_policy="lazy_not_persisted",
            context_summary="Generator context without prompt bodies.",
            created_at="2026-06-05T12:00:00Z",
            version=1,
        )
    )
    session.validation_loop_state.current_rank_index = 0
    session.validation_loop_state.active_candidate_id = "c01"
    session.validation_loop_state.active_version_id = "c01_v1"
    session.validation_loop_state.active_version_origin = "draft"
    session.validation_loop_state.active_text_source = "candidate_texts"
    session.validation_loop_state.accepted_count = 1
    session.validation_loop_state.selector_eligible_unique_accepted_count = 1
    session.pending_interrupt = PendingInterrupt(
        type="request_clarification",
        node="clarification_interrupt",
        status="waiting",
        payload={
            "type": "request_clarification",
            "reason": "ambiguous_subject",
            "message": "Нужно уточнить тему.",
            "options": [{"id": "squirrel", "label": "Белка"}],
        },
        created_at="2026-06-05T12:01:00Z",
        attempt=1,
        resume_schema={
            "selected_option_id": "string|null",
            "freeform_text": "string|null",
        },
    )
    session.candidate_texts.append(
        CandidateText(
            candidate_id="c01",
            theme="Белка ищет орешек",
            text="Белка нашла орешек и поделилась с другом.",
            questions=["Что нашла белка?"],
            used_subjects=["squirrel"],
            status="draft",
        )
    )
    session.validated_candidate_versions.append(
        ValidatedCandidateVersion(
            candidate_id="c01",
            version_id="c01-v1",
            source="candidate",
            theme="Белка ищет орешек",
            text="Белка нашла орешек и поделилась с другом.",
            questions=["Что нашла белка?"],
            validation_status="accepted",
        )
    )
    session.approved_texts.append(
        ApprovedText(
            candidate_id="c01",
            version_id="c01-v1",
            theme="Белка ищет орешек",
            text="Белка нашла орешек и поделилась с другом.",
            questions=["Что нашла белка?"],
            score=0.91,
            validation_status="accepted",
            validation_summary="Safety, age and fairy-tale mode passed.",
        )
    )
    session.stage_status.candidate_text_generator.status = StageStatusValue.COMPLETED
    session.stage_status.candidate_text_generator.input_hash = "input-hash"
    session.stage_status.candidate_text_generator.output_hash = "output-hash"
    session.shortage.requested = 1
    session.shortage.approved = 1
    session.shortage.status = "enough"

    storage.save_session(session)

    loaded = storage.get_session("wave-1-round-trip")

    assert loaded is not None
    assert loaded.request.raw_text == "Сделай короткую сказку про белку."
    assert loaded.normalized_request.main_subject == "белка"
    assert loaded.normalized_request.prompt_context.resolved_layers[0].id == "FAIRY_TALE_BASE"
    assert loaded.prompt_context.source_hash == "registry-hash"
    assert loaded.stage_prompt_context.entries[0].stage == "candidate_text_generator"
    assert loaded.stage_prompt_context.entries[0].source_prompt_context_hash == "registry-hash"
    assert loaded.stage_prompt_context.entries[0].stage_context_hash == "stage-context-hash"
    assert loaded.stage_prompt_context.entries[0].layer_ids == ["FAIRY_TALE_BASE"]
    assert loaded.stage_prompt_context.entries[0].body_policy == "lazy_not_persisted"
    assert loaded.stage_prompt_context.entries[0].context_summary.startswith("Generator")
    assert "selected_layer_ids" not in loaded.stage_prompt_context.entries[0].model_dump()
    assert loaded.candidate_texts[0].candidate_id == "c01"
    assert loaded.validated_candidate_versions[0].validation_status == "accepted"
    assert loaded.approved_texts[0].text.startswith("Белка нашла")
    assert loaded.shortage.status == "enough"
    assert loaded.validation_loop_state.current_rank_index == 0
    assert loaded.validation_loop_state.active_version_origin == "draft"
    assert loaded.validation_loop_state.active_text_source == "candidate_texts"
    assert loaded.validation_loop_state.accepted_count == 1
    assert loaded.validation_loop_state.selector_eligible_unique_accepted_count == 1
    assert loaded.pending_interrupt is not None
    assert loaded.pending_interrupt.type == "request_clarification"
    assert loaded.pending_interrupt.node == "clarification_interrupt"
    assert loaded.pending_interrupt.status == "waiting"
    assert loaded.pending_interrupt.attempt == 1
    assert loaded.pending_interrupt.payload["reason"] == "ambiguous_subject"
    assert loaded.pending_interrupt.resume_schema["selected_option_id"] == "string|null"
