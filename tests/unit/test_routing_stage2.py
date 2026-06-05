from langgraph.graph import END

from src.core.graph import routing as r
from src.core.graph.state import to_graph_state
from src.models.schemas import (
    CandidateText,
    RankedCandidate,
    SessionRequest,
    SessionState,
    ValidatedCandidateVersion,
    ValidationResult,
)


def test_ranker_empty_queue_routes_to_selector():
    session = _session_with_ranked([])
    assert r.route_after_ranker(to_graph_state(session)) == r.NODE_APPROVED_TEXT_SELECTOR


def test_accepted_enough_routes_to_selector():
    session = _session_with_ranked(["c01"])
    session.validation_results = [ValidationResult(candidate_id="c01", version_id="c01_v1", status="accepted")]
    session.validated_candidate_versions = [_validated("c01", "Unique")]
    session.validation_loop_state.selector_eligible_unique_accepted_count = 1

    assert r.route_after_candidate_validator(to_graph_state(session)) == r.NODE_APPROVED_TEXT_SELECTOR


def test_accepted_not_enough_advances_cursor_and_routes_to_validator():
    session = _session_with_ranked(["c01", "c02"], output_count=2)
    session.validation_results = [ValidationResult(candidate_id="c01", version_id="c01_v1", status="accepted")]
    session.validated_candidate_versions = [_validated("c01", "First")]
    session.validation_loop_state.selector_eligible_unique_accepted_count = 1

    assert r.route_after_candidate_validator(to_graph_state(session)) == r.NODE_CANDIDATE_VALIDATOR
    assert session.validation_loop_state.active_candidate_id == "c02"


def test_duplicate_theme_accepted_count_does_not_finish_loop_early():
    session = _session_with_ranked(["c01", "c02", "c03"], output_count=2)
    session.validation_loop_state.current_rank_index = 1
    session.validation_loop_state.active_candidate_id = "c02"
    session.validation_loop_state.active_version_id = "c02_v1"
    session.validation_results = [ValidationResult(candidate_id="c02", version_id="c02_v1", status="accepted")]
    session.validated_candidate_versions = [
        _validated("c01", "Same theme"),
        _validated("c02", " same   theme "),
    ]
    session.validation_loop_state.selector_eligible_unique_accepted_count = 2

    assert r.route_after_candidate_validator(to_graph_state(session)) == r.NODE_CANDIDATE_VALIDATOR
    assert session.validation_loop_state.selector_eligible_unique_accepted_count == 1
    assert session.validation_loop_state.active_candidate_id == "c03"


def test_needs_revision_with_attempts_left_routes_to_refiner():
    session = _session_with_ranked(["c01"])
    session.validation_results = [ValidationResult(candidate_id="c01", version_id="c01_v1", status="needs_revision")]
    session.validation_loop_state.max_refinement_attempts_per_candidate = 1

    assert r.route_after_candidate_validator(to_graph_state(session)) == r.NODE_CANDIDATE_REFINER


def test_entry_after_saved_active_validation_result_uses_next_routing_step():
    session = _session_with_ranked(["c01"])
    session.interpretation_state.execution_lookup_result.status = "pass"
    session.prompt_context.snapshot_hash = "ready"
    session.validation_results = [ValidationResult(candidate_id="c01", version_id="c01_v1", status="needs_revision")]
    session.validation_loop_state.max_refinement_attempts_per_candidate = 1

    assert r.entry_point_from_session(to_graph_state(session)) == r.NODE_CANDIDATE_REFINER


def test_needs_revision_with_no_attempts_left_advances_and_skips_refiner():
    session = _session_with_ranked(["c01", "c02"])
    session.validation_results = [ValidationResult(candidate_id="c01", version_id="c01_v1", status="needs_revision")]
    session.validation_loop_state.max_refinement_attempts_per_candidate = 0

    assert r.route_after_candidate_validator(to_graph_state(session)) == r.NODE_CANDIDATE_VALIDATOR
    assert session.validation_loop_state.active_candidate_id == "c02"


def test_rejected_advances_cursor():
    session = _session_with_ranked(["c01", "c02"])
    session.validation_results = [ValidationResult(candidate_id="c01", version_id="c01_v1", status="rejected")]

    assert r.route_after_candidate_validator(to_graph_state(session)) == r.NODE_CANDIDATE_VALIDATOR
    assert session.validation_loop_state.active_candidate_id == "c02"


def test_queue_exhausted_routes_to_selector():
    session = _session_with_ranked(["c01"])
    session.validation_results = [ValidationResult(candidate_id="c01", version_id="c01_v1", status="rejected")]

    assert r.route_after_candidate_validator(to_graph_state(session)) == r.NODE_APPROVED_TEXT_SELECTOR


def test_shortage_routing():
    session = SessionState(request=SessionRequest(raw_text="ok"))
    session.shortage.status = "enough"
    assert r.route_after_approved_text_selector(to_graph_state(session)) == END

    session.shortage.status = "not_enough_valid_candidates"
    assert r.route_after_approved_text_selector(to_graph_state(session), shortage_hitl_enabled=False) == END
    assert (
        r.route_after_approved_text_selector(to_graph_state(session), shortage_hitl_enabled=True)
        == r.NODE_SHORTAGE_FALLBACK_INTERRUPT
    )


def _session_with_ranked(candidate_ids: list[str], output_count: int = 1) -> SessionState:
    session = SessionState(request=SessionRequest(raw_text="ok"))
    session.normalized_request.output_count = output_count
    session.candidate_texts = [
        CandidateText(candidate_id=candidate_id, theme=f"Theme {candidate_id}", text="draft")
        for candidate_id in candidate_ids
    ]
    session.ranked_candidates = [
        RankedCandidate(candidate_id=candidate_id, rank=index, total_score=1.0, hard_gates_passed=True)
        for index, candidate_id in enumerate(candidate_ids, start=1)
    ]
    if candidate_ids:
        session.validation_loop_state.current_rank_index = 0
        session.validation_loop_state.active_candidate_id = candidate_ids[0]
        session.validation_loop_state.active_version_id = f"{candidate_ids[0]}_v1"
        session.validation_loop_state.active_version_origin = "draft"
        session.validation_loop_state.active_text_source = "candidate_texts"
        session.stage_status.validation_loop.status = "running"
    else:
        session.stage_status.validation_loop.status = "completed"
    return session


def _validated(candidate_id: str, theme: str) -> ValidatedCandidateVersion:
    return ValidatedCandidateVersion(
        candidate_id=candidate_id,
        version_id=f"{candidate_id}_v1",
        theme=theme,
        text="approved",
        validation_status="accepted",
    )
