import subprocess
import sys
from pathlib import Path

from src.core.stage1_runner import Stage1Runner
from src.models.schemas import SessionRequest, SessionState
from src.storage.json_storage import JSONStorage

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"
SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "run_stage1_preview.py"
SUPPORTED_REQUEST = "Сделай сказку про лису для 5 лет и научи безопасности на дороге"


def test_successful_stage1_checkpoint(tmp_path):
    runner = Stage1Runner(storage=JSONStorage(str(tmp_path)), prompts_root=PROMPTS_ROOT)

    result = runner.start(SUPPORTED_REQUEST, current_config={"count": 2})

    assert result.is_stage1_ready is True
    assert result.is_waiting_user is False
    assert result.is_done is True
    session = result.session
    assert session.completion_status == "running"
    assert session.is_completed is False
    assert session.pending_interrupt is None
    assert session.normalized_request.truth_mode == "FAIRY_TALE"
    assert session.normalized_request.utility_topic == "ROAD_SAFETY"
    assert session.normalized_request.target_age == "5"
    assert session.normalized_request.main_subject == "fox"
    assert session.interpretation_state.classification == "complete"
    assert session.interpretation_state.layer_resolution_result.status == "resolved"
    assert session.interpretation_state.validation_result.status == "pass"
    assert session.interpretation_state.execution_lookup_result.status == "pass"
    assert session.preview_state.preview_text
    assert session.preview_state.shown_to_user is True
    assert session.preview_state.accepted_by_user is True
    assert session.prompt_context.snapshot_hash
    assert any(
        entry.stage == "candidate_text_generator"
        for entry in session.stage_prompt_context.entries
    )
    _assert_stage2_not_started(session)


def test_empty_request_creates_durable_idempotent_clarification(tmp_path):
    storage = JSONStorage(str(tmp_path))
    runner = Stage1Runner(storage=storage, prompts_root=PROMPTS_ROOT)

    result = runner.start("")

    assert result.is_waiting_user is True
    assert result.interrupt_type == "request_clarification"
    assert result.interrupt["payload"]["reason"] == "empty_or_meaningless"
    assert result.session.interpretation_state.clarification_attempts == 1
    persisted = storage.get_session(result.session.session_id)
    assert persisted is not None
    assert persisted.pending_interrupt is not None
    assert persisted.pending_interrupt.payload["reason"] == "empty_or_meaningless"

    rerun = runner.run(persisted)

    assert rerun.is_waiting_user is True
    assert rerun.session.interpretation_state.clarification_attempts == 1
    assert rerun.session.pending_interrupt.created_at == persisted.pending_interrupt.created_at
    _assert_stage2_not_started(rerun.session)


def test_resume_from_clarification_reaches_stage1_ready(tmp_path):
    storage = JSONStorage(str(tmp_path))
    runner = Stage1Runner(storage=storage, prompts_root=PROMPTS_ROOT)
    waiting = runner.start("")

    result = runner.resume(
        waiting.session.session_id,
        {"selected_option_id": "opt_1", "freeform_text": "научи безопасности на дороге"},
    )

    assert result.is_stage1_ready is True
    assert result.session.pending_interrupt is None
    assert result.session.completion_status == "running"
    assert result.session.current_node == "prompt_context_preparation"
    assert result.session.normalized_request.main_subject == "fox"
    assert result.session.prompt_context.snapshot_hash
    _assert_stage2_not_started(result.session)


def test_invalid_resume_does_not_clear_pending_interrupt(tmp_path):
    storage = JSONStorage(str(tmp_path))
    runner = Stage1Runner(storage=storage, prompts_root=PROMPTS_ROOT)
    waiting = runner.start("")
    created_at = waiting.session.pending_interrupt.created_at

    result = runner.resume(
        waiting.session.session_id,
        {"selected_option_id": "missing_option", "freeform_text": None},
    )

    assert result.is_waiting_user is True
    assert result.session.pending_interrupt is not None
    assert result.session.pending_interrupt.created_at == created_at
    assert result.session.interpretation_state.clarification_attempts == 1
    assert result.session.prompt_context.snapshot_hash is None
    _assert_stage2_not_started(result.session)


def test_unsupported_hard_requirement_stops_when_attempts_exhausted(tmp_path):
    storage = JSONStorage(str(tmp_path))
    runner = Stage1Runner(storage=storage, prompts_root=PROMPTS_ROOT)
    session = SessionState(
        request=SessionRequest(raw_text="Сделай сказку про Микки Мауса для 5 лет")
    )
    session.interpretation_state.clarification_attempts = 5
    session.interpretation_state.max_clarification_attempts = 5

    result = runner.run(session)

    assert result.is_done is True
    assert result.is_stage1_ready is False
    assert result.session.is_completed is True
    assert result.session.completion_status == "stopped_unresolved_request"
    assert result.session.pending_interrupt is None
    assert result.session.interpretation_state.stop_reason == "unsupported_hard_requirement"
    assert result.session.interpretation_state.stop_issues
    assert result.session.approved_texts == []
    _assert_stage2_not_started(result.session)


def test_console_script_smoke(tmp_path):
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--storage-dir",
            str(tmp_path),
            SUPPORTED_REQUEST,
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "stage1_ready" in completed.stdout
    assert "session_id:" in completed.stdout
    assert "preview:" in completed.stdout

    session_id = _line_value(completed.stdout, "session_id:")
    loaded = JSONStorage(str(tmp_path)).get_session(session_id)
    assert loaded is not None
    assert loaded.prompt_context.snapshot_hash
    _assert_stage2_not_started(loaded)


def test_stable_fail_reresolve_is_bounded_and_persisted(tmp_path, monkeypatch):
    storage = JSONStorage(str(tmp_path))
    runner = Stage1Runner(storage=storage, prompts_root=PROMPTS_ROOT)
    monkeypatch.setattr(runner.registry, "source_exists", lambda _layer_id: False)

    result = runner.start(SUPPORTED_REQUEST)

    assert result.is_stage1_ready is False
    assert result.is_waiting_user is False
    assert result.is_done is False
    assert result.session.interpretation_state.execution_lookup_result.status == "fail_reresolve"
    assert result.session.interpretation_state.execution_lookup_result.details["failure_type"] == (
        "missing_source"
    )
    persisted = storage.get_session(result.session.session_id)
    assert persisted is not None
    assert persisted.interpretation_state.execution_lookup_result.status == "fail_reresolve"
    assert persisted.prompt_context.snapshot_hash
    _assert_stage2_not_started(persisted)


def _line_value(output: str, prefix: str) -> str:
    for line in output.splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    raise AssertionError(f"Missing line prefix: {prefix}")


def _assert_stage2_not_started(session):
    assert session.candidate_texts == []
    assert session.ranked_candidates == []
    assert session.validated_candidate_versions == []
    assert session.approved_texts == []
    assert session.stage_status.candidate_text_generator.status == "not_started"
    assert session.stage_status.topic_deduplicator.status == "not_started"
    assert session.stage_status.scorer.status == "not_started"
    assert session.stage_status.ranker.status == "not_started"
    assert session.stage_status.validation_loop.status == "not_started"
    assert session.stage_status.approved_text_selector.status == "not_started"
