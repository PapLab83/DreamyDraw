from __future__ import annotations

import logging
from collections.abc import Callable
from functools import partial
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.core.graph import routing as r
from src.core.graph.state import GraphState
from src.core.nodes import stage1, stage2
from src.core.nodes.stage2 import DEFAULT_CANDIDATE_COUNT, Stage2TextExecutor
from src.core.observability import build_node_trace_metadata, enrich_approved_text_trace_refs, record_node_trace
from src.core.prompts.composer import PromptComposer
from src.core.prompts.registry import PromptRegistry
from src.models.schemas import CompletionStatus, PendingInterrupt
from src.storage.json_storage import JSONStorage

logger = logging.getLogger(__name__)


def build_stage1_2_graph(
    *,
    registry: PromptRegistry,
    composer: PromptComposer,
    text_executor: Stage2TextExecutor,
    storage: JSONStorage | None = None,
    checkpointer: Optional[MemorySaver] = None,
    shortage_hitl_enabled: bool = False,
    candidate_count: int = DEFAULT_CANDIDATE_COUNT,
):
    graph = StateGraph(GraphState)

    graph.add_node(r.NODE_INPUT_ANALYSIS, _persisting(stage1.input_analysis, storage, r.NODE_INPUT_ANALYSIS))
    graph.add_node(r.NODE_METADATA_LOOKUP, _persisting(partial(stage1.metadata_lookup, registry=registry), storage, r.NODE_METADATA_LOOKUP))
    graph.add_node(r.NODE_REQUEST_CLASSIFICATION, _persisting(stage1.request_classification, storage, r.NODE_REQUEST_CLASSIFICATION))
    graph.add_node(r.NODE_CLARIFICATION_INTERRUPT, _persisting(stage1.clarification_interrupt, storage, r.NODE_CLARIFICATION_INTERRUPT))
    graph.add_node(r.NODE_EMPTY_INPUT_INTERRUPT, _persisting(stage1.empty_input_interrupt, storage, r.NODE_EMPTY_INPUT_INTERRUPT))
    graph.add_node(r.NODE_UNSUPPORTED_INTERRUPT_OR_STOP, _persisting(stage1.unsupported_interrupt_or_stop, storage, r.NODE_UNSUPPORTED_INTERRUPT_OR_STOP))
    graph.add_node(
        r.NODE_CANDIDATE_LAYER_RESOLUTION,
        _persisting(partial(stage1.candidate_layer_resolution, registry=registry), storage, r.NODE_CANDIDATE_LAYER_RESOLUTION),
    )
    graph.add_node(
        r.NODE_FINAL_PARAMETER_VALIDATION,
        _persisting(partial(stage1.final_parameter_validation, registry=registry), storage, r.NODE_FINAL_PARAMETER_VALIDATION),
    )
    graph.add_node(r.NODE_PREVIEW, _persisting(stage1.preview, storage, r.NODE_PREVIEW))
    graph.add_node(
        r.NODE_PROMPT_CONTEXT_PREPARATION,
        _persisting(partial(stage1.prompt_context_preparation, registry=registry, composer=composer), storage, r.NODE_PROMPT_CONTEXT_PREPARATION),
    )
    graph.add_node(
        r.NODE_CANDIDATE_TEXT_GENERATOR,
        _persisting(
            partial(
                stage2.candidate_text_generator,
                registry=registry,
                composer=composer,
                text_executor=text_executor,
                candidate_count=candidate_count,
            ),
            storage,
            r.NODE_CANDIDATE_TEXT_GENERATOR,
        ),
    )
    graph.add_node(
        r.NODE_TOPIC_DEDUPLICATOR,
        _persisting(
            partial(
                stage2.topic_deduplicator,
                registry=registry,
                composer=composer,
                text_executor=text_executor,
            ),
            storage,
            r.NODE_TOPIC_DEDUPLICATOR,
        ),
    )
    graph.add_node(
        r.NODE_SCORER,
        _persisting(partial(stage2.scorer, registry=registry, composer=composer, text_executor=text_executor), storage, r.NODE_SCORER),
    )
    graph.add_node(r.NODE_RANKER, _persisting(stage2.ranker, storage, r.NODE_RANKER))
    graph.add_node(
        r.NODE_CANDIDATE_VALIDATOR,
        _persisting(
            partial(stage2.candidate_validator, registry=registry, composer=composer, text_executor=text_executor),
            storage,
            r.NODE_CANDIDATE_VALIDATOR,
        ),
    )
    graph.add_node(
        r.NODE_CANDIDATE_REFINER,
        _persisting(
            partial(stage2.candidate_refiner, registry=registry, composer=composer, text_executor=text_executor),
            storage,
            r.NODE_CANDIDATE_REFINER,
        ),
    )
    graph.add_node(r.NODE_APPROVED_TEXT_SELECTOR, _persisting(stage2.approved_text_selector, storage, r.NODE_APPROVED_TEXT_SELECTOR))
    graph.add_node(r.NODE_SHORTAGE_FALLBACK_INTERRUPT, _persisting(shortage_fallback_interrupt, storage, r.NODE_SHORTAGE_FALLBACK_INTERRUPT))

    graph.add_conditional_edges(
        START,
        _entry_point,
        _edge_map(
            r.NODE_INPUT_ANALYSIS,
            r.NODE_METADATA_LOOKUP,
            r.NODE_REQUEST_CLASSIFICATION,
            r.NODE_CLARIFICATION_INTERRUPT,
            r.NODE_EMPTY_INPUT_INTERRUPT,
            r.NODE_UNSUPPORTED_INTERRUPT_OR_STOP,
            r.NODE_CANDIDATE_LAYER_RESOLUTION,
            r.NODE_FINAL_PARAMETER_VALIDATION,
            r.NODE_PREVIEW,
            r.NODE_PROMPT_CONTEXT_PREPARATION,
            r.NODE_CANDIDATE_TEXT_GENERATOR,
            r.NODE_TOPIC_DEDUPLICATOR,
            r.NODE_SCORER,
            r.NODE_RANKER,
            r.NODE_CANDIDATE_VALIDATOR,
            r.NODE_CANDIDATE_REFINER,
            r.NODE_APPROVED_TEXT_SELECTOR,
            r.NODE_SHORTAGE_FALLBACK_INTERRUPT,
            END,
        ),
    )

    graph.add_edge(r.NODE_INPUT_ANALYSIS, r.NODE_METADATA_LOOKUP)
    graph.add_edge(r.NODE_METADATA_LOOKUP, r.NODE_REQUEST_CLASSIFICATION)
    graph.add_conditional_edges(
        r.NODE_REQUEST_CLASSIFICATION,
        r.route_after_request_classification,
        _edge_map(
            r.NODE_CANDIDATE_LAYER_RESOLUTION,
            r.NODE_CLARIFICATION_INTERRUPT,
            r.NODE_EMPTY_INPUT_INTERRUPT,
            r.NODE_UNSUPPORTED_INTERRUPT_OR_STOP,
            END,
        ),
    )
    graph.add_edge(r.NODE_CLARIFICATION_INTERRUPT, END)
    graph.add_edge(r.NODE_EMPTY_INPUT_INTERRUPT, END)
    graph.add_edge(r.NODE_UNSUPPORTED_INTERRUPT_OR_STOP, END)
    graph.add_conditional_edges(
        r.NODE_CANDIDATE_LAYER_RESOLUTION,
        r.route_after_candidate_layer_resolution,
        _edge_map(r.NODE_FINAL_PARAMETER_VALIDATION, r.NODE_CLARIFICATION_INTERRUPT, r.NODE_UNSUPPORTED_INTERRUPT_OR_STOP, END),
    )
    graph.add_conditional_edges(
        r.NODE_FINAL_PARAMETER_VALIDATION,
        r.route_after_final_parameter_validation,
        _edge_map(r.NODE_PREVIEW, r.NODE_REQUEST_CLASSIFICATION, END),
    )
    graph.add_edge(r.NODE_PREVIEW, r.NODE_PROMPT_CONTEXT_PREPARATION)
    graph.add_conditional_edges(
        r.NODE_PROMPT_CONTEXT_PREPARATION,
        _route_after_prompt_context_preparation,
        _edge_map(r.NODE_CANDIDATE_TEXT_GENERATOR, r.NODE_CANDIDATE_LAYER_RESOLUTION, r.NODE_CLARIFICATION_INTERRUPT, END),
    )

    graph.add_edge(r.NODE_CANDIDATE_TEXT_GENERATOR, r.NODE_TOPIC_DEDUPLICATOR)
    graph.add_edge(r.NODE_TOPIC_DEDUPLICATOR, r.NODE_SCORER)
    graph.add_edge(r.NODE_SCORER, r.NODE_RANKER)
    graph.add_conditional_edges(
        r.NODE_RANKER,
        r.route_after_ranker,
        _edge_map(r.NODE_CANDIDATE_VALIDATOR, r.NODE_APPROVED_TEXT_SELECTOR),
    )
    graph.add_conditional_edges(
        r.NODE_CANDIDATE_VALIDATOR,
        r.route_after_candidate_validator,
        _edge_map(r.NODE_CANDIDATE_VALIDATOR, r.NODE_CANDIDATE_REFINER, r.NODE_APPROVED_TEXT_SELECTOR, END),
    )
    graph.add_conditional_edges(
        r.NODE_CANDIDATE_REFINER,
        r.route_after_candidate_refiner,
        _edge_map(r.NODE_CANDIDATE_VALIDATOR, r.NODE_APPROVED_TEXT_SELECTOR, END),
    )
    graph.add_conditional_edges(
        r.NODE_APPROVED_TEXT_SELECTOR,
        lambda state: r.route_after_approved_text_selector(state, shortage_hitl_enabled=shortage_hitl_enabled),
        _edge_map(r.NODE_SHORTAGE_FALLBACK_INTERRUPT, END),
    )
    graph.add_conditional_edges(
        r.NODE_SHORTAGE_FALLBACK_INTERRUPT,
        r.route_after_shortage_fallback,
        _edge_map(END),
    )

    return graph.compile(checkpointer=checkpointer or MemorySaver())


def shortage_fallback_interrupt(state: GraphState) -> GraphState:
    session = state["session"]
    if session.shortage.status != "enough":
        session.is_completed = False
        session.completion_status = CompletionStatus.WAITING_USER
        session.pending_interrupt = PendingInterrupt(
            type="shortage_fallback",
            node=r.NODE_SHORTAGE_FALLBACK_INTERRUPT,
            status="waiting",
            payload={
                "type": "shortage_fallback",
                "shortage": session.shortage.model_dump(),
                "message": "Недостаточно approved_texts. Нужен явный выбор пользователя.",
            },
        )
    session.current_node = r.NODE_SHORTAGE_FALLBACK_INTERRUPT
    return state


def _entry_point(state: GraphState) -> str:
    if state.get("user_input") is not None:
        return r.NODE_INPUT_ANALYSIS
    return r.entry_point_from_session(state)


def _route_after_prompt_context_preparation(state: GraphState) -> str:
    next_node = r.route_after_prompt_context_preparation(state)
    if next_node == r.NODE_CANDIDATE_LAYER_RESOLUTION:
        r.record_prompt_context_reresolve_attempt(state)
    return next_node


def _persisting(node: Callable[[GraphState], GraphState], storage: JSONStorage | None, node_name: str):
    def wrapped(state: GraphState) -> GraphState:
        result = node(state)
        session = result["session"]
        if node_name == r.NODE_APPROVED_TEXT_SELECTOR:
            enrich_approved_text_trace_refs(session)
        metadata = None
        try:
            metadata = build_node_trace_metadata(session, node_name)
        except Exception as exc:
            logger.debug("build_node_trace_metadata failed for %s: %s", node_name, exc)
        record_node_trace(
            session,
            node_name=node_name,
            status="completed",
            metadata=metadata,
            trace_id=session.trace_refs.get("root", {}).get("trace_id"),
        )
        if storage is not None:
            storage.save_session(session)
        return result

    return wrapped


def _edge_map(*names: str) -> dict[str, str]:
    return {name: name for name in names}
