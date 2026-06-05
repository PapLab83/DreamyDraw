from langgraph.graph import END

from src.core.graph import routing as r
from src.core.graph.state import to_graph_state
from src.models.schemas import PendingInterrupt, SessionRequest, SessionState


def test_classification_complete_routes_to_layer_resolution():
    session = SessionState(request=SessionRequest(raw_text="ok"))
    session.interpretation_state.classification = "complete"

    assert r.route_after_request_classification(to_graph_state(session)) == r.NODE_CANDIDATE_LAYER_RESOLUTION


def test_classification_clarification_like_routes_to_interrupts():
    session = SessionState(request=SessionRequest(raw_text=""))
    session.interpretation_state.classification = "needs_clarification"
    assert r.route_after_request_classification(to_graph_state(session)) == r.NODE_CLARIFICATION_INTERRUPT

    session.interpretation_state.classification = "empty_or_meaningless"
    assert r.route_after_request_classification(to_graph_state(session)) == r.NODE_EMPTY_INPUT_INTERRUPT

    session.interpretation_state.classification = "contradictory"
    assert r.route_after_request_classification(to_graph_state(session)) == r.NODE_CLARIFICATION_INTERRUPT

    session.interpretation_state.classification = "unsupported_hard_requirement"
    assert r.route_after_request_classification(to_graph_state(session)) == r.NODE_UNSUPPORTED_INTERRUPT_OR_STOP


def test_classification_stop_routes_to_end_without_stage2():
    session = SessionState(request=SessionRequest(raw_text=""))
    session.interpretation_state.classification = "stop"

    assert r.route_after_request_classification(to_graph_state(session)) == END


def test_layer_resolution_resolved_routes_to_final_validation():
    session = SessionState(request=SessionRequest(raw_text="ok"))
    session.interpretation_state.layer_resolution_result.status = "resolved"

    assert r.route_after_candidate_layer_resolution(to_graph_state(session)) == r.NODE_FINAL_PARAMETER_VALIDATION


def test_final_validation_fail_reclassify_routes_back_to_classification():
    session = SessionState(request=SessionRequest(raw_text="ok"))
    session.interpretation_state.validation_result.status = "fail_reclassify"

    assert r.route_after_final_parameter_validation(to_graph_state(session)) == r.NODE_REQUEST_CLASSIFICATION


def test_prompt_context_pass_routes_to_candidate_generation():
    session = SessionState(request=SessionRequest(raw_text="ok"))
    session.interpretation_state.execution_lookup_result.status = "pass"

    assert r.route_after_prompt_context_preparation(to_graph_state(session)) == r.NODE_CANDIDATE_TEXT_GENERATOR


def test_prompt_context_fail_reresolve_is_bounded():
    session = SessionState(request=SessionRequest(raw_text="ok"))
    session.interpretation_state.execution_lookup_result.status = "fail_reresolve"
    session.trace_refs["prompt_context_reresolve_attempts"] = 0
    assert r.route_after_prompt_context_preparation(to_graph_state(session)) == r.NODE_CANDIDATE_LAYER_RESOLUTION

    session.trace_refs["prompt_context_reresolve_attempts"] = r.MAX_PROMPT_CONTEXT_RERESOLVE_ATTEMPTS
    assert r.route_after_prompt_context_preparation(to_graph_state(session)) == END
    assert session.is_completed is True
    assert session.completion_status == "failed"
    assert session.shortage.failure_details["reason"] == "prompt_context_reresolve_limit_exceeded"


def test_entry_waiting_user_requires_durable_pending_interrupt():
    session = SessionState(request=SessionRequest(raw_text=""))
    session.completion_status = "waiting_user"
    session.pending_interrupt = None

    assert r.entry_point_from_session(to_graph_state(session)) != r.NODE_CLARIFICATION_INTERRUPT

    session.pending_interrupt = PendingInterrupt(
        type="request_clarification",
        node=r.NODE_CLARIFICATION_INTERRUPT,
        status="waiting",
        payload={"reason": "needs_clarification"},
    )
    assert r.entry_point_from_session(to_graph_state(session)) == r.NODE_CLARIFICATION_INTERRUPT
