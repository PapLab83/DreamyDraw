"""
Сборка LangGraph для оркестратора DreamyDraw.

build_graph(...) принимает все зависимости (llm, image, storage, prompt_builder)
и возвращает скомпилированный граф с checkpointer.

Граф собирается один раз на жизнь Orchestrator — кэш зависимостей через closure.

Стратегия HITL:
    - 3 interrupt-ноды: config_arbitration, plan_arbitration, user_confirmation
    - Все используют функциональный interrupt() внутри ноды (динамический HITL,
      см. langgraph >=0.2.50).
    - Checkpointer MemorySaver хранит паузу в рамках процесса.
    - Долгосрочное восстановление между процессами — через JSONStorage
      и entry_point_from_session() в routing.py.
"""

import logging
from typing import Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from src.core.graph import routing as r
from src.core.graph.state import GraphState
from src.core.nodes.content import (
    make_image_generation,
    make_text_generation,
    make_user_confirmation,
)
from src.core.nodes.planning import (
    make_idea_sampler,
    make_idea_scoring,
    make_score_normalize,
    make_series_planner,
)
from src.core.nodes.safety import (
    make_config_arbitration,
    make_config_match,
    make_safety_gate,
)
from src.core.nodes.validation import (
    make_plan_arbitration,
    make_plan_refiner,
    make_plan_reviewer,
    make_plan_validator,
)
from src.core.prompt_builder import PromptBuilder
from src.providers.base import BaseImageProvider, BaseLLMProvider
from src.storage.json_storage import JSONStorage

logger = logging.getLogger(__name__)


def build_graph(
    llm: BaseLLMProvider,
    image: BaseImageProvider,
    storage: JSONStorage,
    prompt_builder: PromptBuilder,
    checkpointer: Optional[MemorySaver] = None,
):
    """
    Собирает StateGraph и компилирует его с checkpointer.

    Args:
        llm: LLM-провайдер
        image: image-провайдер
        storage: JSON-хранилище сессий
        prompt_builder: построитель промптов
        checkpointer: если не задан — создаётся новый MemorySaver

    Returns:
        Скомпилированный граф (CompiledStateGraph)
    """
    g = StateGraph(GraphState)

    # --- Регистрация нод (через фабрики с инжектом зависимостей) ---

    # Фаза I. Валидация входа
    g.add_node(r.NODE_SAFETY_GATE, make_safety_gate(llm, storage, prompt_builder))
    g.add_node(r.NODE_CONFIG_MATCH, make_config_match(llm, storage, prompt_builder))
    g.add_node(r.NODE_CONFIG_ARBITRATION, make_config_arbitration(storage))

    # Фаза II. Планирование серии
    g.add_node(r.NODE_SERIES_PLANNER, make_series_planner(llm, storage, prompt_builder))
    g.add_node(r.NODE_IDEA_SCORING, make_idea_scoring(llm, storage, prompt_builder))
    g.add_node(r.NODE_SCORE_NORMALIZE, make_score_normalize(storage))
    g.add_node(r.NODE_IDEA_SAMPLER, make_idea_sampler(storage))

    # Фаза III. Валидация плана (циклы)
    g.add_node(r.NODE_PLAN_VALIDATOR, make_plan_validator(llm, storage, prompt_builder))
    g.add_node(r.NODE_PLAN_REVIEWER, make_plan_reviewer(llm, storage, prompt_builder))
    g.add_node(r.NODE_PLAN_REFINER, make_plan_refiner(llm, storage, prompt_builder))
    g.add_node(r.NODE_PLAN_ARBITRATION, make_plan_arbitration(storage))

    # Фаза IV. Генерация контента
    g.add_node(r.NODE_TEXT_GENERATION, make_text_generation(llm, storage, prompt_builder))
    g.add_node(r.NODE_USER_CONFIRMATION, make_user_confirmation(storage))
    g.add_node(r.NODE_IMAGE_GENERATION, make_image_generation(image, storage, prompt_builder))

    # --- Точка входа ---
    g.add_edge(START, r.NODE_SAFETY_GATE)

    # --- Рёбра ---

    # Фаза I: safety_gate → config_match → [config_arbitration] → series_planner
    g.add_conditional_edges(
        r.NODE_SAFETY_GATE,
        r.route_after_safety,
        {
            r.NODE_CONFIG_MATCH: r.NODE_CONFIG_MATCH,
            END: END,
        },
    )
    g.add_conditional_edges(
        r.NODE_CONFIG_MATCH,
        r.route_after_config_match,
        {
            r.NODE_SERIES_PLANNER: r.NODE_SERIES_PLANNER,
            r.NODE_CONFIG_ARBITRATION: r.NODE_CONFIG_ARBITRATION,
            END: END,
        },
    )
    g.add_conditional_edges(
        r.NODE_CONFIG_ARBITRATION,
        r.route_after_config_arbitration,
        {
            r.NODE_SERIES_PLANNER: r.NODE_SERIES_PLANNER,
            END: END,
        },
    )

    # Фаза II: planning — линейная цепочка
    g.add_edge(r.NODE_SERIES_PLANNER, r.NODE_IDEA_SCORING)
    g.add_edge(r.NODE_IDEA_SCORING, r.NODE_SCORE_NORMALIZE)
    g.add_edge(r.NODE_SCORE_NORMALIZE, r.NODE_IDEA_SAMPLER)
    # После sampler — переход к валидации (с учётом failed)
    g.add_conditional_edges(
        r.NODE_IDEA_SAMPLER,
        _route_after_sampler,
        {
            r.NODE_PLAN_VALIDATOR: r.NODE_PLAN_VALIDATOR,
            END: END,
        },
    )

    # Фаза III: цикл валидации
    g.add_conditional_edges(
        r.NODE_PLAN_VALIDATOR,
        r.route_after_validator,
        {
            r.NODE_TEXT_GENERATION: r.NODE_TEXT_GENERATION,
            r.NODE_PLAN_REVIEWER: r.NODE_PLAN_REVIEWER,
            r.NODE_PLAN_ARBITRATION: r.NODE_PLAN_ARBITRATION,
            END: END,
        },
    )
    g.add_conditional_edges(
        r.NODE_PLAN_REVIEWER,
        r.route_after_reviewer,
        {
            r.NODE_PLAN_REFINER: r.NODE_PLAN_REFINER,
            END: END,
        },
    )
    g.add_conditional_edges(
        r.NODE_PLAN_REFINER,
        r.route_after_refiner,
        {
            r.NODE_PLAN_VALIDATOR: r.NODE_PLAN_VALIDATOR,
            END: END,
        },
    )
    g.add_conditional_edges(
        r.NODE_PLAN_ARBITRATION,
        r.route_after_arbitration,
        {
            r.NODE_TEXT_GENERATION: r.NODE_TEXT_GENERATION,
            r.NODE_PLAN_REVIEWER: r.NODE_PLAN_REVIEWER,
        },
    )

    # Фаза IV: генерация контента
    g.add_conditional_edges(
        r.NODE_TEXT_GENERATION,
        r.route_after_text_generation,
        {
            r.NODE_USER_CONFIRMATION: r.NODE_USER_CONFIRMATION,
            r.NODE_IMAGE_GENERATION: r.NODE_IMAGE_GENERATION,
        },
    )
    g.add_conditional_edges(
        r.NODE_USER_CONFIRMATION,
        r.route_after_user_confirmation,
        {
            r.NODE_IMAGE_GENERATION: r.NODE_IMAGE_GENERATION,
            r.NODE_TEXT_GENERATION: r.NODE_TEXT_GENERATION,
            END: END,
        },
    )
    g.add_edge(r.NODE_IMAGE_GENERATION, END)

    # --- Компиляция ---
    checkpointer = checkpointer or MemorySaver()
    compiled = g.compile(checkpointer=checkpointer)

    logger.debug("Graph compiled successfully")
    return compiled


# --- Локальные routing-функции (специфичны для builder.py) --------------------

def _route_after_sampler(state: GraphState) -> str:
    """После idea_sampler: failed → END, иначе → plan_validator."""
    session = state["session"]
    if session.current_node == "failed":
        return END
    return r.NODE_PLAN_VALIDATOR