"""
Ноды фазы валидации входа: safety_gate, config_match, config_arbitration.

Каждая фабрика make_<node>(deps) возвращает функцию-ноду
с сигнатурой (GraphState) -> GraphState, готовую для add_node в LangGraph.
"""

import logging
from typing import Callable

from langfuse import observe
from langgraph.types import interrupt

from src.core.graph.state import GraphState
from src.core.prompt_builder import PromptBuilder
from src.core.utils.json_parser import parse_llm_json
from src.models.schemas import TruthMode
from src.providers.base import BaseLLMProvider
from src.storage.json_storage import JSONStorage

logger = logging.getLogger(__name__)


# --- Фабрика: safety_gate -----------------------------------------------------

def make_safety_gate(
    llm: BaseLLMProvider,
    storage: JSONStorage,
    prompt_builder: PromptBuilder,
) -> Callable[[GraphState], GraphState]:
    """Создаёт ноду safety_gate с инжектированными зависимостями."""

    @observe(name="safety_gate")
    def safety_gate(state: GraphState) -> GraphState:
        session = state["session"]
        logger.info("[STEP] safety-gate | Проверка темы: %s", session.request.topic)

        prompt = prompt_builder.build_safety_prompt(session.request.topic)
        response_raw = llm.generate_text(prompt)

        result = parse_llm_json(response_raw, default={}, context="safety_gate")

        if result.get("is_safe"):
            logger.info("[STEP] safety-gate | Статус: OK")
            session.current_node = "safety_passed"
        elif not result:
            # parse_llm_json вернул default={} — fallback на текстовый поиск
            session.current_node = (
                "safety_passed" if "true" in response_raw.lower() else "failed"
            )
            logger.warning(
                "[STEP] safety-gate | JSON не распарсился, fallback -> %s",
                session.current_node,
            )
        else:
            logger.error(
                "[STEP] safety-gate | Статус: FAILED | %s",
                result.get("reason"),
            )
            session.current_node = "failed"

        storage.save_session(session)
        return {"session": session}

    return safety_gate


# --- Фабрика: config_match ----------------------------------------------------

def make_config_match(
    llm: BaseLLMProvider,
    storage: JSONStorage,
    prompt_builder: PromptBuilder,
) -> Callable[[GraphState], GraphState]:
    """
    Создаёт ноду config_match.

    В отличие от старой реализации, здесь НЕТ блокирующего input().
    Если режим несовместим — нода кладёт в session.user_feedback
    предложенный режим (для config_arbitration) и помечает current_node
    как 'config_needs_arbitration'. Маршрутизация — в routing.py.
    """

    @observe(name="config_match")
    def config_match(state: GraphState) -> GraphState:
        session = state["session"]
        mode_val = session.request.truth_mode.value
        logger.info(
            "[STEP] config-match | Проверка совместимости темы и режима '%s'",
            mode_val,
        )

        prompt = prompt_builder.build_config_match_prompt(
            session.request.topic, mode_val
        )
        response_raw = llm.generate_text(prompt)

        result = parse_llm_json(response_raw, default={}, context="config_match")

        if not result:
            # Не смогли распарсить — считаем совместимым (как в старой логике)
            logger.warning("[STEP] config-match | JSON не распарсился, считаем OK")
            session.current_node = "config_passed"
            storage.save_session(session)
            return {"session": session}

        if result.get("is_compatible"):
            logger.info("[STEP] config-match | Статус: OK")
            session.current_node = "config_passed"
        else:
            reason = result.get("reason", "")
            suggested = result.get("suggested_mode", "")
            logger.warning("[!] ВНИМАНИЕ: %s", reason)
            session.validator_feedback = _pack_config_feedback(reason, suggested)
            session.current_node = "config_needs_arbitration"

        storage.save_session(session)
        return {"session": session}

    return config_match


# --- Фабрика: config_arbitration (interrupt) ----------------------------------

def make_config_arbitration(
    storage: JSONStorage,
) -> Callable[[GraphState], GraphState]:
    """
    Interrupt-нода: спрашивает пользователя, переключить ли режим
    на предложенный валидатором.

    Снаружи получит через Command(resume=<value>) одно из:
        - 'y' / 'yes' / 'д' — переключить и продолжить
        - что-либо ещё — остановить пайплайн
    """

    @observe(name="config_arbitration")
    def config_arbitration(state: GraphState) -> GraphState:
        session = state["session"]

        reason, suggested = _unpack_config_feedback(session.validator_feedback)

        user_input = interrupt(
            {
                "type": "config_arbitration",
                "reason": reason,
                "suggested_mode": suggested,
                "current_mode": session.request.truth_mode.value,
            }
        )

        choice = (user_input or "").strip().lower()
        if choice in ("y", "yes", "д", "да"):
            # Переключаем режим
            for m in TruthMode:
                if (
                    m.value.lower() in suggested.lower()
                    or suggested.lower() in m.value.lower()
                ):
                    session.request.truth_mode = m
                    logger.info(
                        "[USER] Режим переключён на '%s'", m.value
                    )
                    break
            session.current_node = "config_passed"
        else:
            logger.info("[USER] Пользователь отказался переключать режим")
            session.current_node = "failed"

        # Чистим временные данные
        session.validator_feedback = "{}"
        storage.save_session(session)
        return {"session": session}

    return config_arbitration


# --- Внутренние утилиты для упаковки фидбека config_match ---------------------

def _pack_config_feedback(reason: str, suggested: str) -> str:
    """Упаковка reason/suggested в validator_feedback (JSON-строка)."""
    import json
    return json.dumps(
        {"reason": reason, "suggested_mode": suggested},
        ensure_ascii=False,
    )


def _unpack_config_feedback(raw: str) -> tuple[str, str]:
    """Распаковка validator_feedback обратно в (reason, suggested)."""
    if not raw or raw == "{}":
        return "", ""
    try:
        data = parse_llm_json(raw, default={}, context="config_arbitration")
        return data.get("reason", ""), data.get("suggested_mode", "")
    except Exception:
        return "", ""