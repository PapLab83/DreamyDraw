from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from src.core.graph.stage1_2_builder import build_stage1_2_graph
from src.core.graph.state import to_graph_state
from src.core.nodes.stage2 import Stage2TextExecutor
from src.core.observability import build_root_trace_metadata
from src.core.pipeline_result import PipelineResult
from src.core.prompts.composer import PromptComposer
from src.core.prompts.registry import PromptRegistry
from src.core.request_adapter import to_session_request
from src.models.schemas import GenerationRequest, SessionRequest, SessionState
from src.storage.json_storage import JSONStorage
from src.utils import langfuse_client

logger = logging.getLogger(__name__)


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
            candidate_count=candidate_count,
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
        final_state = self._invoke_with_root_trace(session, state)
        actual_session = self.storage.get_session(session_id) or final_state["session"]
        self._record_root_trace(actual_session, actual_session.trace_refs.get("root", {}).get("trace_id"))
        self.storage.save_session(actual_session)
        interrupt = None
        if actual_session.pending_interrupt and actual_session.pending_interrupt.status == "waiting":
            interrupt = dict(actual_session.pending_interrupt.payload)
            interrupt.setdefault("type", actual_session.pending_interrupt.type)
            interrupt.setdefault("node", actual_session.pending_interrupt.node)
        return PipelineResult(session=actual_session, interrupt=interrupt)

    def get_session(self, session_id: str) -> SessionState | None:
        return self.storage.get_session(session_id)

    def _invoke_with_root_trace(self, session: SessionState, state: dict[str, Any]) -> dict[str, Any]:
        trace_id = None
        if not langfuse_client.is_enabled():
            self._record_root_trace(session, trace_id)
            self.storage.save_session(session)
            return self.graph.invoke(state, config={"configurable": {"thread_id": session.session_id}})
        span_cm = None
        span_exc = (None, None, None)
        try:
            span_cm = langfuse_client.start_root_span("stage1_2.run_pipeline")
            span = span_cm.__enter__()
            trace_id = getattr(span, "trace_id", None) if span else None
        except Exception:
            span_cm = None
        self._record_root_trace(session, trace_id)
        try:
            langfuse_client.update_current_trace(
                session_id=session.session_id,
                metadata=session.trace_refs["root"],
            )
        except Exception:
            pass
        self.storage.save_session(session)
        try:
            return self.graph.invoke(state, config={"configurable": {"thread_id": session.session_id}})
        except BaseException as exc:
            span_exc = (type(exc), exc, exc.__traceback__)
            raise
        finally:
            if span_cm is not None:
                try:
                    span_cm.__exit__(*span_exc)
                except Exception:
                    pass

    def _record_root_trace(self, session: SessionState, trace_id: str | None) -> None:
        try:
            metadata = build_root_trace_metadata(session)
        except Exception as exc:
            logger.debug("build_root_trace_metadata failed: %s", exc)
            metadata = {
                "session_id": session.session_id,
                "completion_status": str(session.completion_status),
                "current_node": session.current_node,
            }
        metadata["trace_id"] = trace_id
        session.trace_refs["root"] = metadata
