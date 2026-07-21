"""
Условные функции для add_conditional_edges в LangGraph.

Каждая функция получает GraphState и возвращает строку — имя следующей ноды
(или специальное значение END). Логика вынесена сюда, чтобы builder остался
декларативным, а условия маршрутизации были тестируемыми отдельно.
"""

from langgraph.graph import END

from src.core.graph.state import GraphState
from src.core.nodes.stage2 import advance_validation_cursor, has_validation_queue_exhausted
from src.models.schemas import CompletionStatus, WorkMode

# --- Имена нод графа (единый источник правды) ---

NODE_INPUT_ANALYSIS = "input_analysis"
NODE_METADATA_LOOKUP = "metadata_lookup"
NODE_REQUEST_CLASSIFICATION = "request_classification"
NODE_CLARIFICATION_INTERRUPT = "clarification_interrupt"
NODE_EMPTY_INPUT_INTERRUPT = "empty_input_interrupt"
NODE_UNSUPPORTED_INTERRUPT_OR_STOP = "unsupported_interrupt_or_stop"
NODE_CANDIDATE_LAYER_RESOLUTION = "candidate_layer_resolution"
NODE_FINAL_PARAMETER_VALIDATION = "final_parameter_validation"
NODE_PREVIEW = "preview"
NODE_PROMPT_CONTEXT_PREPARATION = "prompt_context_preparation"
NODE_CANDIDATE_TEXT_GENERATOR = "candidate_text_generator"
NODE_TOPIC_DEDUPLICATOR = "topic_deduplicator"
NODE_SCORER = "scorer"
NODE_RANKER = "ranker"
NODE_CANDIDATE_VALIDATOR = "candidate_validator"
NODE_CANDIDATE_REFINER = "candidate_refiner"
NODE_APPROVED_TEXT_SELECTOR = "approved_text_selector"
NODE_SHORTAGE_FALLBACK_INTERRUPT = "shortage_fallback_interrupt"

MAX_PROMPT_CONTEXT_RERESOLVE_ATTEMPTS = 1

NODE_SAFETY_GATE = "safety_gate"
NODE_CONFIG_MATCH = "config_match"
NODE_CONFIG_ARBITRATION = "config_arbitration"
NODE_SERIES_PLANNER = "series_planner"
NODE_IDEA_SCORING = "idea_scoring"
NODE_SCORE_NORMALIZE = "score_normalize"
NODE_IDEA_SAMPLER = "idea_sampler"
NODE_PLAN_VALIDATOR = "plan_validator"
NODE_PLAN_REVIEWER = "plan_reviewer"
NODE_PLAN_REFINER = "plan_refiner"
NODE_PLAN_ARBITRATION = "plan_arbitration"
NODE_TEXT_GENERATION = "text_generation"
NODE_USER_CONFIRMATION = "user_confirmation"
NODE_IMAGE_GENERATION = "image_generation"


# --- Stage 1-2 routing --------------------------------------------------------

def route_after_request_classification(state: GraphState) -> str:
    session = state["session"]
    classification = session.interpretation_state.classification
    if classification == "complete":
        return NODE_CANDIDATE_LAYER_RESOLUTION
    if classification == "needs_clarification":
        return NODE_CLARIFICATION_INTERRUPT
    if classification == "empty_or_meaningless":
        return NODE_EMPTY_INPUT_INTERRUPT
    if classification == "contradictory":
        return NODE_CLARIFICATION_INTERRUPT
    if classification == "unsupported_hard_requirement":
        return NODE_UNSUPPORTED_INTERRUPT_OR_STOP
    if classification == "stop":
        return END
    return NODE_CLARIFICATION_INTERRUPT


def route_after_candidate_layer_resolution(state: GraphState) -> str:
    status = state["session"].interpretation_state.layer_resolution_result.status
    if status == "resolved":
        return NODE_FINAL_PARAMETER_VALIDATION
    if status == "needs_clarification":
        return NODE_CLARIFICATION_INTERRUPT
    if status == "unsupported_hard_requirement":
        return NODE_UNSUPPORTED_INTERRUPT_OR_STOP
    if status == "stop":
        return END
    return NODE_CLARIFICATION_INTERRUPT


def route_after_final_parameter_validation(state: GraphState) -> str:
    status = state["session"].interpretation_state.validation_result.status
    if status == "pass":
        return NODE_PREVIEW
    if status == "fail_reclassify":
        return NODE_REQUEST_CLASSIFICATION
    if status == "stop":
        return END
    return END


def route_after_prompt_context_preparation(state: GraphState) -> str:
    session = state["session"]
    status = session.interpretation_state.execution_lookup_result.status
    if status == "pass":
        return NODE_CANDIDATE_TEXT_GENERATOR
    if status == "fail_reresolve":
        attempts = int(session.trace_refs.get("prompt_context_reresolve_attempts", 0))
        if attempts < MAX_PROMPT_CONTEXT_RERESOLVE_ATTEMPTS:
            return NODE_CANDIDATE_LAYER_RESOLUTION
        session.is_completed = True
        session.completion_status = CompletionStatus.FAILED
        session.shortage.failure_details["reason"] = "prompt_context_reresolve_limit_exceeded"
        session.shortage.failure_details["execution_lookup_result"] = (
            session.interpretation_state.execution_lookup_result.model_dump()
        )
        return END
    if status == "fail_clarify":
        return NODE_CLARIFICATION_INTERRUPT
    if status == "fail_stop":
        return END
    return END


def route_after_ranker(state: GraphState) -> str:
    session = state["session"]
    if not session.ranked_candidates or has_validation_queue_exhausted(session):
        return NODE_APPROVED_TEXT_SELECTOR
    return NODE_CANDIDATE_VALIDATOR


def route_after_candidate_validator(state: GraphState) -> str:
    session = state["session"]
    latest = _latest_validation_status(state)
    if latest == "accepted":
        if _selector_eligible_unique_count(session) >= session.normalized_request.output_count:
            advance_validation_cursor(session)
            return NODE_APPROVED_TEXT_SELECTOR
        return _advance_or_select(state)
    if latest == "needs_revision":
        if _refinement_attempts_left(state):
            return NODE_CANDIDATE_REFINER
        return _advance_or_select(state)
    if latest == "rejected":
        return _advance_or_select(state)
    if has_validation_queue_exhausted(session):
        return NODE_APPROVED_TEXT_SELECTOR
    return END


def route_after_candidate_refiner(state: GraphState) -> str:
    session = state["session"]
    loop = session.validation_loop_state
    if (
        loop.active_candidate_id
        and loop.active_version_id
        and loop.active_text_source == "refined_candidate_versions"
        and any(
            version.candidate_id == loop.active_candidate_id
            and version.version_id == loop.active_version_id
            for version in session.refined_candidate_versions
        )
    ):
        return NODE_CANDIDATE_VALIDATOR
    return END


def route_after_approved_text_selector(state: GraphState, shortage_hitl_enabled: bool = False) -> str:
    status = state["session"].shortage.status
    if status == "enough":
        return END
    if shortage_hitl_enabled:
        return NODE_SHORTAGE_FALLBACK_INTERRUPT
    return END


def route_after_shortage_fallback(state: GraphState) -> str:
    session = state["session"]
    if session.shortage.status == "enough":
        return END
    return END


def entry_point_from_session(state: GraphState) -> str:
    session = state["session"]
    completion_status = _status_value(session.completion_status)
    if session.is_completed or completion_status in {
        "completed_enough",
        "completed_with_shortage",
        "completed_with_shortage_user_accepted",
        "stopped_unresolved_request",
        "stopped_by_user",
        "failed",
    }:
        return END

    if completion_status == "waiting_user":
        pending = session.pending_interrupt
        if pending and pending.status == "waiting":
            if pending.node in {
                NODE_CLARIFICATION_INTERRUPT,
                NODE_EMPTY_INPUT_INTERRUPT,
                NODE_UNSUPPORTED_INTERRUPT_OR_STOP,
                NODE_SHORTAGE_FALLBACK_INTERRUPT,
            }:
                return pending.node
        return NODE_INPUT_ANALYSIS

    if session.interpretation_state.execution_lookup_result.status == "pass" and session.prompt_context.snapshot_hash:
        if session.stage_status.approved_text_selector.status == "completed":
            return END
        if session.stage_status.validation_loop.status == "completed":
            return NODE_APPROVED_TEXT_SELECTOR
        if session.stage_status.validation_loop.status == "running":
            if _latest_validation_matches_active(session):
                return route_after_candidate_validator(state)
            return NODE_CANDIDATE_VALIDATOR
        if session.stage_status.ranker.status == "completed":
            return route_after_ranker(state)
        if session.stage_status.scorer.status == "completed":
            return NODE_RANKER
        if session.stage_status.topic_deduplicator.status == "completed":
            return NODE_SCORER
        if session.stage_status.candidate_text_generator.status == "completed":
            return NODE_TOPIC_DEDUPLICATOR
        return NODE_CANDIDATE_TEXT_GENERATOR

    if session.preview_state.accepted_by_user and session.preview_state.shown_to_user:
        return NODE_PROMPT_CONTEXT_PREPARATION
    if session.interpretation_state.validation_result.status == "pass":
        return NODE_PREVIEW
    if session.interpretation_state.layer_resolution_result.status == "resolved":
        return NODE_FINAL_PARAMETER_VALIDATION
    if session.interpretation_state.classification:
        return route_after_request_classification(state)
    if session.interpretation_state.lookup_hints:
        return NODE_REQUEST_CLASSIFICATION
    if session.normalized_request.main_subject:
        return NODE_METADATA_LOOKUP
    return NODE_INPUT_ANALYSIS


def record_prompt_context_reresolve_attempt(state: GraphState) -> GraphState:
    session = state["session"]
    attempts = int(session.trace_refs.get("prompt_context_reresolve_attempts", 0))
    session.trace_refs["prompt_context_reresolve_attempts"] = attempts + 1
    return state


def _advance_or_select(state: GraphState) -> str:
    session = state["session"]
    advance_validation_cursor(session)
    if has_validation_queue_exhausted(session):
        return NODE_APPROVED_TEXT_SELECTOR
    return NODE_CANDIDATE_VALIDATOR


def _latest_validation_status(state: GraphState) -> str:
    session = state["session"]
    if not session.validation_results:
        return "queue_exhausted" if has_validation_queue_exhausted(session) else "missing"
    return session.validation_results[-1].status


def _latest_validation_matches_active(session) -> bool:
    if not session.validation_results:
        return False
    latest = session.validation_results[-1]
    loop = session.validation_loop_state
    return (
        latest.candidate_id == loop.active_candidate_id
        and latest.version_id == loop.active_version_id
    )


def _selector_eligible_unique_count(session) -> int:
    by_candidate = {
        item.candidate_id: item
        for item in session.validated_candidate_versions
        if item.validation_status == "accepted"
    }
    seen_themes: set[str] = set()
    count = 0
    for ranked in sorted(session.ranked_candidates, key=lambda item: item.rank):
        if ranked.hard_gates_passed is not True:
            continue
        version = by_candidate.get(ranked.candidate_id)
        if version is None:
            continue
        normalized_theme = " ".join(version.theme.casefold().split())
        if normalized_theme in seen_themes:
            continue
        seen_themes.add(normalized_theme)
        count += 1
    return count


def _refinement_attempts_left(state: GraphState) -> bool:
    session = state["session"]
    candidate_id = session.validation_loop_state.active_candidate_id
    if not candidate_id:
        return False
    used = sum(1 for version in session.refined_candidate_versions if version.candidate_id == candidate_id)
    return used < session.validation_loop_state.max_refinement_attempts_per_candidate


def _status_value(status) -> str:
    return getattr(status, "value", status)


# --- Условные функции маршрутизации ---

def route_after_safety(state: GraphState) -> str:
    """После safety_gate: failed → END, иначе → config_match."""
    session = state["session"]
    if session.current_node == "failed":
        return END
    return NODE_CONFIG_MATCH


def route_after_config_match(state: GraphState) -> str:
    """
    После config_match:
    - совместимо → series_planner
    - несовместимо → config_arbitration (interrupt)
    - failed → END
    """
    session = state["session"]
    if session.current_node == "failed":
        return END
    if session.current_node == "config_passed":
        return NODE_SERIES_PLANNER
    return NODE_CONFIG_ARBITRATION


def route_after_config_arbitration(state: GraphState) -> str:
    """После арбитража конфига: либо продолжаем, либо завершаем."""
    session = state["session"]
    if session.current_node == "failed":
        return END
    return NODE_SERIES_PLANNER


def route_after_validator(state: GraphState) -> str:
    """
    После plan_validator:
    - plan_approved → text_generation
    - plan_needs_refine → plan_reviewer (auto-loop)
    - plan_needs_user_arbitration → plan_arbitration (interrupt)
    - failed → END
    """
    session = state["session"]
    if session.current_node == "failed":
        return END
    if session.current_node == "plan_approved":
        return NODE_TEXT_GENERATION
    if session.current_node == "plan_needs_user_arbitration":
        return NODE_PLAN_ARBITRATION
    return NODE_PLAN_REVIEWER


def route_after_reviewer(state: GraphState) -> str:
    """После plan_reviewer: всегда идём к рефайнеру (он сам решит, есть ли что править)."""
    session = state["session"]
    if session.current_node == "failed":
        return END
    return NODE_PLAN_REFINER


def route_after_refiner(state: GraphState) -> str:
    """После plan_refiner: возвращаемся к валидатору на повторную проверку."""
    session = state["session"]
    if session.current_node == "failed":
        return END
    return NODE_PLAN_VALIDATOR


def route_after_arbitration(state: GraphState) -> str:
    """
    После арбитража пользователя:
    - plan_approved (форсированное одобрение) → text_generation
    - иначе → plan_reviewer (новый цикл с user_feedback)
    """
    session = state["session"]
    if session.current_node == "plan_approved":
        return NODE_TEXT_GENERATION
    return NODE_PLAN_REVIEWER


def route_after_text_generation(state: GraphState) -> str:
    """
    После генерации текстов:
    - CHECK-режим → user_confirmation (interrupt)
    - FAST-режим → image_generation
    """
    session = state["session"]
    if session.request.work_mode == WorkMode.CHECK:
        return NODE_USER_CONFIRMATION
    return NODE_IMAGE_GENERATION


def route_after_user_confirmation(state: GraphState) -> str:
    """
    После подтверждения пользователем:
    - все is_confirmed=True → image_generation
    - хотя бы у одного text="" (regenerate) → text_generation (повторный цикл)
    - иначе (отмена) → END
    """
    session = state["session"]
    if all(s.is_confirmed for s in session.stories):
        return NODE_IMAGE_GENERATION
    if any(not s.text for s in session.stories):
        return NODE_TEXT_GENERATION
    return END


def legacy_entry_point_from_session(state: GraphState) -> str:
    """
    Точка входа в граф при восстановлении сессии (--session <id>).
    Определяет, с какой ноды стартовать, исходя из session.current_node.
    """
    session = state["session"]
    node = session.current_node

    mapping = {
        "start": NODE_SAFETY_GATE,
        "safety_passed": NODE_CONFIG_MATCH,
        "config_passed": NODE_SERIES_PLANNER,
        "series_planned": NODE_PLAN_VALIDATOR,
        "plan_needs_refine": NODE_PLAN_REVIEWER,
        "plan_needs_user_arbitration": NODE_PLAN_ARBITRATION,
        "plan_approved": NODE_TEXT_GENERATION,
    }
    return mapping.get(node, NODE_SAFETY_GATE)
