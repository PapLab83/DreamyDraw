"""
Условные функции для add_conditional_edges в LangGraph.

Каждая функция получает GraphState и возвращает строку — имя следующей ноды
(или специальное значение END). Логика вынесена сюда, чтобы builder остался
декларативным, а условия маршрутизации были тестируемыми отдельно.
"""

from langgraph.graph import END
from src.core.graph.state import GraphState
from src.models.schemas import WorkMode


# --- Имена нод графа (единый источник правды) ---

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


def entry_point_from_session(state: GraphState) -> str:
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