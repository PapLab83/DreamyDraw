from __future__ import annotations

import json

import pytest

from src.core import stage1_2_orchestrator
from src.core.graph import stage1_2_builder
from src.core.stage1_2_orchestrator import Stage1_2Orchestrator
from src.storage.json_storage import JSONStorage
from src.utils import langfuse_client
from tests.integration.test_stage1_2_graph import (
    PROMPTS_ROOT,
    SUPPORTED_REQUEST,
    FakePipelineExecutor,
    ShortageExecutor,
)

pytestmark = pytest.mark.integration


def test_facade_run_records_root_and_node_trace_refs(tmp_path):
    orchestrator = _orchestrator(tmp_path)
    session = orchestrator.start_session(SUPPORTED_REQUEST, current_config={"count": 2})

    result = orchestrator.run_pipeline(session.session_id)

    refs = result.session.trace_refs
    assert refs["root"]["session_id"] == session.session_id
    assert refs["root"]["completion_status"] == "completed_enough"
    events = refs["node_events"]
    event_names = [event["node_name"] for event in events]
    assert "request_classification" in event_names
    assert "candidate_validator" in event_names
    assert "approved_text_selector" in event_names
    assert all(event["status"] == "completed" for event in events)


def test_approved_texts_contain_compact_prompt_candidate_trace_refs(tmp_path):
    orchestrator = _orchestrator(tmp_path)
    session = orchestrator.start_session(SUPPORTED_REQUEST, current_config={"count": 2})

    result = orchestrator.run_pipeline(session.session_id)

    refs = result.session.approved_texts[0].trace_refs
    assert refs["candidate_id"] == "c01"
    assert refs["version_id"] == "c01_v1"
    assert refs["prompt_context_hash"]
    assert refs["generator_stage_context_hash"]
    assert refs["validator_stage_context_hash"]
    assert refs["selector_stage_context_hash"]
    assert refs["trace_id"] is None
    assert "text" not in refs


def test_shortage_path_records_status_and_reason_in_trace_refs(tmp_path):
    orchestrator = _orchestrator(tmp_path, executor=ShortageExecutor(), candidate_count=2)
    session = orchestrator.start_session(SUPPORTED_REQUEST, current_config={"count": 3})

    result = orchestrator.run_pipeline(session.session_id)

    root = result.session.trace_refs["root"]
    selector_event = _event(result.session.trace_refs["node_events"], "approved_text_selector")
    assert root["shortage_status"] == "not_enough_valid_candidates"
    assert selector_event["metadata"]["stage2"]["shortage"] == {
        "status": "not_enough_valid_candidates",
        "reason": "Not enough accepted validated candidate versions.",
        "requested": 3,
        "approved": 1,
    }


def test_noop_langfuse_still_records_local_trace_refs_and_completes(tmp_path, monkeypatch):
    monkeypatch.setattr(langfuse_client, "is_enabled", lambda: False)
    orchestrator = _orchestrator(tmp_path)
    session = orchestrator.start_session(SUPPORTED_REQUEST, current_config={"count": 1})

    result = orchestrator.run_pipeline(session.session_id)

    assert result.is_done
    assert result.session.trace_refs["root"]["trace_id"] is None
    assert result.session.trace_refs["node_events"]


def test_mocked_langfuse_failure_does_not_fail_generation(tmp_path, monkeypatch):
    class BrokenSpan:
        trace_id = "trace-broken"
        id = "span-broken"

    class BrokenRootSpan:
        def __enter__(self):
            return BrokenSpan()

        def __exit__(self, exc_type, exc, tb):
            return False

    monkeypatch.setattr(langfuse_client, "is_enabled", lambda: True)
    monkeypatch.setattr(langfuse_client, "start_root_span", lambda name: BrokenRootSpan())
    monkeypatch.setattr(
        langfuse_client,
        "update_current_trace",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("langfuse failed")),
    )
    orchestrator = _orchestrator(tmp_path)
    session = orchestrator.start_session(SUPPORTED_REQUEST, current_config={"count": 1})

    result = orchestrator.run_pipeline(session.session_id)

    assert result.is_done
    assert result.session.trace_refs["root"]["trace_id"] == "trace-broken"
    assert result.session.trace_refs["node_events"]


def test_node_observability_helper_failure_does_not_fail_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(
        stage1_2_builder,
        "build_node_trace_metadata",
        lambda session, node_name: (_ for _ in ()).throw(RuntimeError("node trace failed")),
    )
    orchestrator = _orchestrator(tmp_path)
    session = orchestrator.start_session(SUPPORTED_REQUEST, current_config={"count": 1})

    result = orchestrator.run_pipeline(session.session_id)

    assert result.is_done
    assert result.session.approved_texts


def test_root_observability_helper_failure_does_not_fail_generation(tmp_path, monkeypatch):
    monkeypatch.setattr(
        stage1_2_orchestrator,
        "build_root_trace_metadata",
        lambda session: (_ for _ in ()).throw(RuntimeError("root trace failed")),
    )
    orchestrator = _orchestrator(tmp_path)
    session = orchestrator.start_session(SUPPORTED_REQUEST, current_config={"count": 1})

    result = orchestrator.run_pipeline(session.session_id)

    assert result.is_done
    assert result.session.approved_texts


def test_persisted_session_json_does_not_store_prompt_bodies_in_trace_refs(tmp_path):
    orchestrator = _orchestrator(tmp_path)
    session = orchestrator.start_session(SUPPORTED_REQUEST, current_config={"count": 1})

    result = orchestrator.run_pipeline(session.session_id)
    persisted = json.loads((tmp_path / result.session.session_id / "state.json").read_text(encoding="utf-8"))
    serialized_trace_refs = json.dumps(persisted["trace_refs"], ensure_ascii=False, sort_keys=True)

    assert "# Назначение" not in serialized_trace_refs
    assert "full_prompt" not in serialized_trace_refs
    assert "prompt_body" not in serialized_trace_refs
    assert "Не изображать животных говорящими" not in serialized_trace_refs
    assert "Первый спокойный текст." not in serialized_trace_refs


def _orchestrator(tmp_path, executor=None, candidate_count=3):
    return Stage1_2Orchestrator(
        storage=JSONStorage(str(tmp_path)),
        text_executor=executor or FakePipelineExecutor(),
        prompts_root=PROMPTS_ROOT,
        candidate_count=candidate_count,
    )


def _event(events, node_name):
    return next(event for event in events if event["node_name"] == node_name)
