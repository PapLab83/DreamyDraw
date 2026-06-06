from __future__ import annotations

import json

from src.core.observability import (
    build_node_trace_metadata,
    build_root_trace_metadata,
    enrich_approved_text_trace_refs,
    record_node_trace,
    redact_trace_payload,
)
from src.models.schemas import (
    ApprovedText,
    CandidateScore,
    CandidateText,
    PromptLayerRef,
    SessionRequest,
    SessionState,
    StagePromptContextEntry,
    Subject,
    ValidatedCandidateVersion,
)


def test_root_trace_metadata_includes_compact_session_summary():
    session = _session()

    metadata = build_root_trace_metadata(session)

    assert metadata["session_id"] == session.session_id
    assert metadata["completion_status"] == "running"
    assert metadata["normalized_summary"] == {
        "truth_mode": "FAIRY_TALE",
        "utility_mode": "TEACHING",
        "target_age": "5",
        "main_subject": "fox",
        "output_count": 2,
    }
    assert metadata["approved_count"] == 0
    assert metadata["candidate_count"] == 0


def test_root_trace_raw_input_summary_is_bounded():
    session = _session(raw_text="x" * 300)

    metadata = build_root_trace_metadata(session)

    assert len(metadata["raw_input_summary"]) == 240


def test_stage1_node_metadata_has_classification_layer_ids_and_no_prompt_bodies():
    session = _session()
    session.interpretation_state.classification = "complete"
    session.interpretation_state.confidence = {"input_analysis": 90}
    session.interpretation_state.layer_resolution_result.details = {
        "resolved_layer_ids": ["FAIRY_TALE_BASE"],
        "unresolved_detail_labels": [],
    }
    session.stage_prompt_context.entries = [
        StagePromptContextEntry(
            stage="candidate_text_generator",
            stage_context_hash="generator-hash",
            layer_ids=["FAIRY_TALE_BASE"],
            body_policy="lazy_not_persisted",
        )
    ]

    metadata = build_node_trace_metadata(session, "request_classification")
    serialized = json.dumps(metadata, ensure_ascii=False, sort_keys=True)

    assert metadata["stage1"]["classification"] == "complete"
    assert metadata["stage1"]["confidence"] == {"input_analysis": 90}
    assert metadata["prompt"]["layer_ids"] == ["FAIRY_TALE_BASE"]
    assert "# Назначение" not in serialized
    assert "prompt_body" not in serialized


def test_stage2_node_metadata_includes_counters_ranked_ids_and_active_candidate():
    session = _session()
    session.candidate_texts = [
        CandidateText(candidate_id="c01", theme="One", text="large body one"),
        CandidateText(candidate_id="c02", theme="Two", text="large body two"),
    ]
    session.deduplication_results = []
    session.scores = [
        CandidateScore(candidate_id="c01", hard_gates={"safety": "pass"}, total_score=0.9),
        CandidateScore(candidate_id="c02", hard_gates={"safety": "fail"}, total_score=0.2),
    ]
    session.ranked_candidates = []
    session.validation_loop_state.active_candidate_id = "c01"
    session.validation_loop_state.active_version_id = "c01_v1"
    session.pipeline_counters.validation_attempts = 2

    metadata = build_node_trace_metadata(session, "candidate_validator")

    assert metadata["stage2"]["candidate_count"] == {"requested": 2, "generated": 2}
    assert metadata["stage2"]["hard_gate_failure_counts"] == {"safety": 1}
    assert metadata["stage2"]["active_candidate"] == {"candidate_id": "c01", "version_id": "c01_v1"}
    assert "candidate_texts" not in metadata["stage2"]


def test_prompt_metadata_includes_context_hashes_sources_and_body_policy():
    session = _session()
    session.stage_prompt_context.entries = [
        StagePromptContextEntry(
            stage="candidate_validator",
            candidate_id="c01",
            version_id="c01_v1",
            attempt=1,
            source_prompt_context_hash="source-hash",
            stage_context_hash="validator-hash",
            layer_ids=["FAIRY_TALE_BASE"],
            body_policy="lazy_not_persisted",
        )
    ]

    metadata = build_node_trace_metadata(session, "candidate_validator")

    assert metadata["prompt"]["source_prompt_context_hash"] == "source-hash"
    assert metadata["prompt"]["stage_context_hash"] == "validator-hash"
    assert metadata["prompt"]["source_paths"] == ["prompts/truth_modes/FAIRY_TALE/BASE.md"]
    assert metadata["prompt"]["body_policy"] == "lazy_not_persisted"


def test_redaction_removes_forbidden_keys_and_strings():
    payload = {
        "safe": "ok",
        "full_prompt": "# Назначение\nlong",
        "nested": {"prompt_body": "secret", "body_policy": "lazy_not_persisted"},
        "list": [{"bodies": {"x": "hidden"}}, "# Назначение appears in text"],
    }

    redacted = redact_trace_payload(payload)
    serialized = json.dumps(redacted, ensure_ascii=False, sort_keys=True)

    assert redacted["safe"] == "ok"
    assert "full_prompt" not in serialized
    assert "prompt_body" not in serialized
    assert "bodies" not in serialized
    assert "# Назначение" not in serialized
    assert redacted["nested"]["body_policy"] == "lazy_not_persisted"


def test_record_node_trace_appends_json_serializable_compact_events():
    session = _session()

    record_node_trace(
        session,
        node_name="candidate_validator",
        status="completed",
        metadata={"candidate_texts": ["should be removed"], "safe": "ok"},
        trace_id="trace-1",
        span_id="span-1",
    )

    events = session.trace_refs["node_events"]
    json.dumps(events, ensure_ascii=False, sort_keys=True)
    assert events == [
        {
            "node_name": "candidate_validator",
            "status": "completed",
            "trace_id": "trace-1",
            "span_id": "span-1",
            "metadata": {"safe": "ok"},
        }
    ]


def test_helpers_handle_missing_optional_fields_without_crashing():
    session = SessionState(request=SessionRequest(raw_text="minimal"))

    assert build_root_trace_metadata(session)["session_id"] == session.session_id
    assert build_node_trace_metadata(session, "unknown_node")["node_name"] == "unknown_node"
    record_node_trace(session, node_name="unknown_node", status="completed")


def test_enrich_approved_text_trace_refs_adds_candidate_prompt_hashes_without_text_body():
    session = _session()
    session.stage_prompt_context.entries = [
        StagePromptContextEntry(stage="candidate_text_generator", stage_context_hash="generator-hash"),
        StagePromptContextEntry(
            stage="candidate_validator",
            candidate_id="c01",
            version_id="c01_v1",
            attempt=1,
            stage_context_hash="validator-hash",
        ),
        StagePromptContextEntry(stage="approved_text_selector", stage_context_hash="selector-hash"),
    ]
    session.validated_candidate_versions = [
        ValidatedCandidateVersion(
            candidate_id="c01",
            version_id="c01_v1",
            text="approved body",
            trace_refs={"stage_context_hash": "validator-hash"},
        )
    ]
    session.approved_texts = [
        ApprovedText(candidate_id="c01", version_id="c01_v1", text="approved body")
    ]

    enrich_approved_text_trace_refs(session)

    refs = session.approved_texts[0].trace_refs
    assert refs["prompt_context_hash"] == session.prompt_context.snapshot_hash
    assert refs["candidate_id"] == "c01"
    assert refs["version_id"] == "c01_v1"
    assert refs["generator_stage_context_hash"] == "generator-hash"
    assert refs["validator_stage_context_hash"] == "validator-hash"
    assert refs["refiner_stage_context_hash"] is None
    assert refs["selector_stage_context_hash"] == "selector-hash"
    assert refs["trace_id"] is None
    assert refs["span_ids"] == {}
    assert "approved body" not in json.dumps(refs, ensure_ascii=False)


def _session(raw_text: str | None = None) -> SessionState:
    session = SessionState(
        request=SessionRequest(
            raw_text=raw_text or "Сделай сказку про лису для 5 лет и научи безопасности на дороге",
            current_config={"count": 2},
        )
    )
    session.normalized_request.truth_mode = "FAIRY_TALE"
    session.normalized_request.utility_mode = "TEACHING"
    session.normalized_request.utility_topic = "ROAD_SAFETY"
    session.normalized_request.target_age = "5"
    session.normalized_request.main_subject = "fox"
    session.normalized_request.output_count = 2
    session.normalized_request.subjects = [
        Subject(id="fox", label="лиса", type="animal", role="main", is_character=True)
    ]
    session.prompt_context.snapshot_hash = "prompt-context-hash"
    session.prompt_context.resolved_layers = [
        PromptLayerRef(
            id="FAIRY_TALE_BASE",
            type="truth_mode",
            source="prompts/truth_modes/FAIRY_TALE/BASE.md",
        )
    ]
    return session
