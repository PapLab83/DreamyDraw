from __future__ import annotations

from pathlib import Path

import pytest

from src.core.stage1_2_orchestrator import Stage1_2Orchestrator
from src.models.schemas import GenerationRequest, ImageStyle, SessionRequest, TextStyle, TruthMode, WorkMode
from src.storage.json_storage import JSONStorage
from tests.integration.test_stage1_2_graph import FakePipelineExecutor, ShortageExecutor, SUPPORTED_REQUEST

pytestmark = pytest.mark.integration

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts" / "cultural_contexts" / "russian_folk"

def test_start_from_raw_string_and_run_to_approved_texts(tmp_path):
    executor = FakePipelineExecutor()
    orchestrator = _orchestrator(tmp_path, executor=executor)

    session = orchestrator.start_session(SUPPORTED_REQUEST, current_config={"count": 2})
    result = orchestrator.run_pipeline(session.session_id)

    assert result.is_done
    assert not result.is_waiting_user
    assert [item.candidate_id for item in result.session.approved_texts] == ["c01", "c02"]
    assert result.session.request.raw_text == SUPPORTED_REQUEST


def test_generation_request_compatibility_input_runs_to_approved_texts(tmp_path):
    orchestrator = _orchestrator(tmp_path)
    request = GenerationRequest(
        topic=SUPPORTED_REQUEST,
        count=2,
        truth_mode=TruthMode.FAIRY_TALE,
        text_style=TextStyle.GENTLE,
        image_style=ImageStyle.NIGHT,
        work_mode=WorkMode.CHECK,
    )

    session = orchestrator.start_session(request)
    result = orchestrator.run_pipeline(session.session_id)

    assert result.is_done
    assert result.session.approved_texts
    assert result.session.request.current_config["work_mode"] == "check"
    assert result.session.request.current_config["image_style"] == "NIGHT"


def test_empty_request_returns_waiting_user_result(tmp_path):
    orchestrator = _orchestrator(tmp_path)
    session = orchestrator.start_session(" ", current_config={"count": 2})

    result = orchestrator.run_pipeline(session.session_id)

    assert result.is_waiting_user
    assert not result.is_done
    assert result.interrupt_type == "request_clarification"
    assert result.interrupt["node"] == "empty_input_interrupt"


def test_resume_from_clarification_reaches_stage2_and_completes(tmp_path):
    orchestrator = _orchestrator(tmp_path)
    session = orchestrator.start_session("", current_config={"count": 2})
    paused = orchestrator.run_pipeline(session.session_id)

    result = orchestrator.run_pipeline(
        paused.session.session_id,
        resume_value={"freeform_text": SUPPORTED_REQUEST},
    )

    assert result.is_done
    assert result.session.pending_interrupt is None
    assert result.session.approved_texts


def test_shortage_with_hitl_disabled_returns_done_completed_with_shortage(tmp_path):
    orchestrator = _orchestrator(tmp_path, executor=ShortageExecutor(), candidate_count=2)
    session = orchestrator.start_session(SUPPORTED_REQUEST, current_config={"count": 3})

    result = orchestrator.run_pipeline(session.session_id)

    assert result.is_done
    assert not result.is_waiting_user
    assert result.session.completion_status == "completed_with_shortage"
    assert len(result.session.approved_texts) == 1


def test_unknown_session_raises_clear_value_error(tmp_path):
    orchestrator = _orchestrator(tmp_path)

    with pytest.raises(ValueError, match="Session missing not found"):
        orchestrator.run_pipeline("missing")


def test_completed_session_returns_without_invoking_executor_again(tmp_path):
    executor = FakePipelineExecutor()
    orchestrator = _orchestrator(tmp_path, executor=executor)
    session = orchestrator.start_session(SUPPORTED_REQUEST, current_config={"count": 1})
    first = orchestrator.run_pipeline(session.session_id)
    calls_after_first_run = executor.calls["refine_candidate"]

    second = orchestrator.run_pipeline(first.session.session_id)

    assert second.is_done
    assert executor.calls["refine_candidate"] == calls_after_first_run


def test_no_image_provider_is_required_to_construct_or_run_facade(tmp_path):
    orchestrator = _orchestrator(tmp_path)
    session = orchestrator.start_session(SessionRequest(raw_text=SUPPORTED_REQUEST, current_config={"count": 1}))

    result = orchestrator.run_pipeline(session.session_id)

    assert result.session.approved_texts


def _orchestrator(tmp_path, executor=None, candidate_count=3):
    return Stage1_2Orchestrator(
        storage=JSONStorage(str(tmp_path)),
        text_executor=executor or FakePipelineExecutor(),
        prompts_root=PROMPTS_ROOT,
        candidate_count=candidate_count,
    )
