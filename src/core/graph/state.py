"""
Состояние графа LangGraph.

GraphState — TypedDict, который LangGraph использует для передачи данных
между нодами. Под капотом мы оборачиваем SessionState — это позволяет
не дублировать модель и пользоваться валидацией Pydantic.

## Контракт:
- В графе живёт `session: SessionState` (целиком).
- Дополнительно — служебные поля для interrupt-возвратов и маршрутизации.
- Любая нода читает state["session"], мутирует его, возвращает {"session": session}.
"""

from typing import Any, Optional, TypedDict
from src.models.schemas import SessionState


class GraphState(TypedDict, total=False):
    """
    Состояние, передаваемое между нодами LangGraph.

    Поля:
        session: основной объект сессии (Pydantic SessionState).
        user_input: значение от пользователя после resume из interrupt.
                    Заполняется снаружи через Command(resume=...).
                    Нода читает и обнуляет.
    """
    session: SessionState
    user_input: Optional[Any]


def to_graph_state(session: SessionState) -> GraphState:
    """Обёртка SessionState → GraphState для входа в граф."""
    return {"session": session, "user_input": None}


def from_graph_state(state: GraphState) -> SessionState:
    """Извлечение SessionState из GraphState после завершения графа."""
    return state["session"]