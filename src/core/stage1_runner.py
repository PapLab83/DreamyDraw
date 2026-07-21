from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.core.graph.state import GraphState, to_graph_state
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
    unsupported_interrupt_or_stop,
)
from src.core.prompts.composer import PromptComposer
from src.core.prompts.cultural_roots import resolve_cultural_prompt_root
from src.core.prompts.registry import PromptRegistry
from src.core.request_adapter import to_session_request
from src.models.schemas import CompletionStatus, SessionState
from src.storage.json_storage import JSONStorage

_TERMINAL_STATUSES = {
    "completed_enough",
    "completed_with_shortage",
    "completed_with_shortage_user_accepted",
    "stopped_unresolved_request",
    "stopped_by_user",
    "failed",
}


@dataclass(frozen=True)
class Stage1RunResult:
    session: SessionState
    is_waiting_user: bool
    is_stage1_ready: bool
    is_done: bool
    interrupt: dict[str, Any] | None = None
    interrupt_type: str | None = None


class Stage1Runner:
    def __init__(
        self,
        *,
        storage: JSONStorage | None = None,
        storage_dir: str | Path = "test_output/stage1_preview",
        prompts_root: str | Path = "prompts",
        registry: PromptRegistry | None = None,
        composer: PromptComposer | None = None,
        max_reresolve_attempts: int = 2,
        cultural_context: str = "RUSSIAN_FOLK",
    ) -> None:
        self.storage = storage or JSONStorage(str(storage_dir))
        self.prompts_root = (
            registry.root
            if registry is not None
            else resolve_cultural_prompt_root(prompts_root, cultural_context)
        )
        self.registry = registry or PromptRegistry.load(self.prompts_root)
        self.composer = composer or PromptComposer(self.registry)
        self.max_reresolve_attempts = max_reresolve_attempts

    def start(
        self,
        raw_text: str,
        current_config: dict[str, Any] | None = None,
    ) -> Stage1RunResult:
        session = SessionState(request=to_session_request(raw_text, current_config=current_config))
        return self.run(session)

    def resume(self, session_id: str, resume_value: Any) -> Stage1RunResult:
        session = self.storage.get_session(session_id)
        if session is None:
            raise ValueError(f"Stage 1 session not found: {session_id}")
        return self.run(session, resume_value=resume_value)

    def run(
        self,
        session: SessionState,
        resume_value: Any | None = None,
    ) -> Stage1RunResult:
        if self._is_terminal(session) or self._is_stage1_ready(session):
            self._save(session)
            return self._result(session)

        if self._is_waiting(session) and resume_value is None:
            self._save(session)
            return self._result(session)

        state = to_graph_state(session)
        state["user_input"] = resume_value

        if resume_value is not None or session.interpretation_state.classification != "complete":
            state = self._step(state, input_analysis, self.registry)
            if self._is_waiting(state["session"]):
                return self._result(state["session"])
            state = self._step(state, metadata_lookup, self.registry)
            state = self._step(state, request_classification)

        session = state["session"]
        classification = session.interpretation_state.classification

        if classification == "stop":
            self._save(session)
            return self._result(session)
        if classification == "empty_or_meaningless":
            state = self._step(state, empty_input_interrupt)
            return self._result(state["session"])
        if classification == "unsupported_hard_requirement":
            state = self._step(state, unsupported_interrupt_or_stop)
            return self._result(state["session"])
        if classification in {"needs_clarification", "contradictory"}:
            state = self._step(state, clarification_interrupt)
            return self._result(state["session"])
        if classification != "complete":
            state = self._step(state, clarification_interrupt)
            return self._result(state["session"])

        return self._run_ready_path(state)

    def _run_ready_path(self, state: GraphState) -> Stage1RunResult:
        reresolve_attempts = 0
        while True:
            for _ in range(3):
                state = self._step(state, candidate_layer_resolution, self.registry)
                state = self._step(state, final_parameter_validation, self.registry)
                validation_status = state["session"].interpretation_state.validation_result.status
                if validation_status == "pass":
                    break
                if validation_status in {"stop"}:
                    state = self._step(state, request_classification)
                    return self._result(state["session"])
                state = self._step(state, request_classification)
                if state["session"].interpretation_state.classification != "complete":
                    return self.run(state["session"])

            state = self._step(state, preview)
            state = self._step(
                state,
                prompt_context_preparation,
                self.registry,
                self.composer,
            )

            execution_status = state["session"].interpretation_state.execution_lookup_result.status
            if execution_status == "pass":
                return self._result(state["session"])
            if execution_status == "fail_reresolve":
                if reresolve_attempts >= self.max_reresolve_attempts:
                    self._save(state["session"])
                    return self._result(state["session"])
                reresolve_attempts += 1
                continue
            if execution_status == "fail_clarify":
                state = self._step(state, clarification_interrupt)
                return self._result(state["session"])

            self._save(state["session"])
            return self._result(state["session"])

    def _step(self, state: GraphState, fn: Any, *args: Any) -> GraphState:
        next_state = fn(state, *args)
        self._save(next_state["session"])
        return next_state

    def _save(self, session: SessionState) -> None:
        if isinstance(session.completion_status, str):
            session.completion_status = CompletionStatus(session.completion_status)
        self.storage.save_session(session)

    def _result(self, session: SessionState) -> Stage1RunResult:
        waiting = self._is_waiting(session)
        ready = self._is_stage1_ready(session)
        interrupt = session.pending_interrupt.model_dump() if session.pending_interrupt else None
        return Stage1RunResult(
            session=session,
            is_waiting_user=waiting,
            is_stage1_ready=ready,
            is_done=session.is_completed or ready,
            interrupt=interrupt,
            interrupt_type=session.pending_interrupt.type if session.pending_interrupt else None,
        )

    @staticmethod
    def _is_terminal(session: SessionState) -> bool:
        return session.is_completed or _status_value(session) in _TERMINAL_STATUSES

    @staticmethod
    def _is_waiting(session: SessionState) -> bool:
        return (
            session.pending_interrupt is not None
            and session.pending_interrupt.status == "waiting"
            and _status_value(session) == "waiting_user"
        )

    @staticmethod
    def _is_stage1_ready(session: SessionState) -> bool:
        return (
            session.interpretation_state.execution_lookup_result.status == "pass"
            and session.prompt_context.snapshot_hash is not None
        )


def _status_value(session: SessionState) -> str:
    return getattr(session.completion_status, "value", session.completion_status)
