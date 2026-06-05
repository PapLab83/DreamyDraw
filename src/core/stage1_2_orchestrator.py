from __future__ import annotations

from pathlib import Path
from typing import Any

from src.core.graph.stage1_2_builder import build_stage1_2_graph
from src.core.graph.state import to_graph_state
from src.core.nodes.stage2 import DEFAULT_CANDIDATE_COUNT, Stage2TextExecutor
from src.core.pipeline_result import PipelineResult
from src.core.prompts.composer import PromptComposer
from src.core.prompts.registry import PromptRegistry
from src.core.request_adapter import to_session_request
from src.models.schemas import GenerationRequest, SessionRequest, SessionState
from src.storage.json_storage import JSONStorage


class Stage1_2Orchestrator:
    """Thin public facade for the clean-slate Stage 1-2 text graph."""

    def __init__(
        self,
        *,
        storage: JSONStorage,
        registry: PromptRegistry | None = None,
        composer: PromptComposer | None = None,
        text_executor: Stage2TextExecutor,
        prompts_root: str | Path = "prompts",
        shortage_hitl_enabled: bool = False,
        candidate_count: int | None = None,
    ) -> None:
        self.storage = storage
        self.registry = registry or PromptRegistry.load(Path(prompts_root))
        self.composer = composer or PromptComposer(self.registry)
        self.text_executor = text_executor
        self.graph = build_stage1_2_graph(
            registry=self.registry,
            composer=self.composer,
            text_executor=self.text_executor,
            storage=self.storage,
            shortage_hitl_enabled=shortage_hitl_enabled,
            candidate_count=candidate_count or DEFAULT_CANDIDATE_COUNT,
        )

    def start_session(
        self,
        request: SessionRequest | GenerationRequest | str,
        current_config: dict[str, Any] | None = None,
    ) -> SessionState:
        session_request = to_session_request(request, current_config=current_config)
        session = SessionState(request=session_request)
        self.storage.save_session(session)
        return session

    def run_pipeline(
        self,
        session_id: str,
        resume_value: Any | None = None,
    ) -> PipelineResult:
        session = self.storage.get_session(session_id)
        if session is None:
            raise ValueError(f"Session {session_id} not found")

        if PipelineResult(session=session).is_done:
            return PipelineResult(session=session)

        state = to_graph_state(session)
        state["user_input"] = resume_value
        final_state = self.graph.invoke(state, config={"configurable": {"thread_id": session_id}})
        actual_session = self.storage.get_session(session_id) or final_state["session"]
        interrupt = None
        if actual_session.pending_interrupt and actual_session.pending_interrupt.status == "waiting":
            interrupt = dict(actual_session.pending_interrupt.payload)
            interrupt.setdefault("type", actual_session.pending_interrupt.type)
            interrupt.setdefault("node", actual_session.pending_interrupt.node)
        return PipelineResult(session=actual_session, interrupt=interrupt)

    def get_session(self, session_id: str) -> SessionState | None:
        return self.storage.get_session(session_id)
