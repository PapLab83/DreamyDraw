import pytest

from src.core.pipeline_result import PipelineResult
from src.models.schemas import CompletionStatus, PendingInterrupt, SessionRequest, SessionState


def _session(status=CompletionStatus.RUNNING) -> SessionState:
    return SessionState(request=SessionRequest(raw_text="Лиса"), completion_status=status)


def test_is_waiting_user_reads_durable_pending_interrupt():
    session = _session(CompletionStatus.WAITING_USER)
    session.pending_interrupt = PendingInterrupt(type="clarification", node="clarification_interrupt", status="waiting")

    result = PipelineResult(session=session)

    assert result.is_waiting_user
    assert not result.is_done


def test_is_done_is_false_for_running_without_interrupt():
    result = PipelineResult(session=_session(CompletionStatus.RUNNING))

    assert not result.is_done
    assert not result.is_waiting_user


@pytest.mark.parametrize(
    "status",
    [
        CompletionStatus.COMPLETED_ENOUGH,
        CompletionStatus.COMPLETED_WITH_SHORTAGE,
        CompletionStatus.COMPLETED_WITH_SHORTAGE_USER_ACCEPTED,
        CompletionStatus.STOPPED_UNRESOLVED_REQUEST,
        CompletionStatus.STOPPED_BY_USER,
        CompletionStatus.FAILED,
    ],
)
def test_is_done_is_true_for_terminal_completion_statuses(status):
    assert PipelineResult(session=_session(status)).is_done


def test_interrupt_type_works_with_durable_pending_interrupt():
    session = _session(CompletionStatus.WAITING_USER)
    session.pending_interrupt = PendingInterrupt(
        type="request_clarification",
        node="empty_input_interrupt",
        status="waiting",
        payload={"type": "empty_input"},
    )

    assert PipelineResult(session=session).interrupt_type == "request_clarification"


def test_interrupt_payload_type_takes_precedence():
    session = _session(CompletionStatus.WAITING_USER)
    session.pending_interrupt = PendingInterrupt(type="durable", node="node", status="waiting")

    assert PipelineResult(session=session, interrupt={"type": "payload"}).interrupt_type == "payload"
