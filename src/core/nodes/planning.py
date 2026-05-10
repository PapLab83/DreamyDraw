"""
Ноды фазы планирования: series_planner, idea_scoring, score_normalize, idea_sampler.

Каждая нода — отдельная единица в графе, видна как отдельный span в Langfuse.
"""

import json
import logging
import random
from typing import Callable, List

from langfuse import observe

from src.config import constants
from src.config.settings import settings
from src.core.graph.state import GraphState
from src.core.prompt_builder import PromptBuilder
from src.core.utils.json_parser import parse_llm_json
from src.models.schemas import Idea
from src.providers.base import BaseLLMProvider
from src.storage.json_storage import JSONStorage

logger = logging.getLogger(__name__)


# --- Фабрика: series_planner --------------------------------------------------

def make_series_planner(
    llm: BaseLLMProvider,
    storage: JSONStorage,
    prompt_builder: PromptBuilder,
) -> Callable[[GraphState], GraphState]:
    """
    LLM-нода: генерирует пул идей и global_context.
    НЕ выполняет scoring/normalize/sampler — это отдельные ноды.
    """

    @observe(name="series_planner")
    def series_planner(state: GraphState) -> GraphState:
        session = state["session"]
        logger.info(
            "[STEP] series-planner | Составление пула идей для темы: %s",
            session.request.topic,
        )

        prompt = prompt_builder.build_series_plan_prompt(
            session.request.topic,
            session.request.truth_mode.value,
        )
        response_raw = llm.generate_text(prompt)

        result = parse_llm_json(response_raw, default=None, context="series_planner")

        if result is None:
            logger.error("[STEP] series-planner | ERROR: не удалось распарсить ответ")
            session.current_node = "failed"
            storage.save_session(session)
            return {"session": session}

        session.global_context = result.get("global_context", "")
        raw_ideas = result.get("ideas", [])

        session.ideas_pool = [
            Idea(
                title=it.get("theme", "Без названия"),
                summary=it.get("content", ""),
            )
            for it in raw_ideas
        ]

        if not session.ideas_pool:
            logger.error("[STEP] series-planner | ERROR: пустой пул идей")
            session.current_node = "failed"
            storage.save_session(session)
            return {"session": session}

        logger.info(
            "[STEP] series-planner | OK | сгенерировано %s идей",
            len(session.ideas_pool),
        )
        session.current_node = "ideas_generated"
        storage.save_session(session)
        return {"session": session}

    return series_planner


# --- Фабрика: idea_scoring ----------------------------------------------------

def make_idea_scoring(
    llm: BaseLLMProvider,
    storage: JSONStorage,
    prompt_builder: PromptBuilder,
) -> Callable[[GraphState], GraphState]:
    """
    LLM-нода: оценивает каждую идею по child_index.
    Отсеивает идеи ниже MIN_CHILD_INDEX. При пустом пуле — fallback-идея.
    """

    @observe(name="idea_scoring")
    def idea_scoring(state: GraphState) -> GraphState:
        session = state["session"]

        if not session.ideas_pool:
            logger.warning("[STEP] idea-scoring | Пул идей пуст, пропускаем")
            session.current_node = "ideas_scored"
            storage.save_session(session)
            return {"session": session}

        logger.info(
            "  [STEP] idea-scoring | Оценка %s идей",
            len(session.ideas_pool),
        )
        ideas_list = [
            {"index": i, "title": it.title, "summary": it.summary}
            for i, it in enumerate(session.ideas_pool)
        ]

        prompt = prompt_builder.build_idea_scoring_prompt(
            json.dumps(ideas_list, ensure_ascii=False),
            session.request.truth_mode.value,
        )
        response_raw = llm.generate_text(prompt)

        result = parse_llm_json(response_raw, default=None, context="idea_scoring")

        if result is None:
            logger.error("  [ERROR] idea-scoring: не удалось распарсить ответ")
            for it in session.ideas_pool:
                it.child_index = settings.DEFAULT_IDEA_CHILD_INDEX
        else:
            scores = result.get("scores", [])
            for score_data in scores:
                idx = score_data.get("index")
                if isinstance(idx, int) and 0 <= idx < len(session.ideas_pool):
                    session.ideas_pool[idx].child_index = score_data.get(
                        "child_index", 0.0
                    )

        # Фильтрация по MIN_CHILD_INDEX
        original_count = len(session.ideas_pool)
        session.ideas_pool = [
            it
            for it in session.ideas_pool
            if it.child_index >= settings.MIN_CHILD_INDEX
        ]
        if len(session.ideas_pool) < original_count:
            logger.warning(
                "  [!] Отсеяно %s небезопасных идей.",
                original_count - len(session.ideas_pool),
            )

        # Fallback: если пул пуст — добавляем дефолтную идею
        if not session.ideas_pool:
            logger.warning(
                "  [!] Пул идей пуст после фильтрации. Восстанавливаем fallback."
            )
            fallback = Idea(
                title="Прогулка в лесу",
                summary="Маленький лис гуляет по лесу и изучает природу.",
            )
            fallback.child_index = settings.FALLBACK_IDEA_CHILD_INDEX
            session.ideas_pool = [fallback]

        session.current_node = "ideas_scored"
        storage.save_session(session)
        return {"session": session}

    return idea_scoring


# --- Фабрика: score_normalize -------------------------------------------------

def make_score_normalize(
    storage: JSONStorage,
) -> Callable[[GraphState], GraphState]:
    """
    Детерминированная нода: линейная нормализация весов идей.
    Без LLM-вызова. @observe нужен для трассировки структуры графа.
    """

    @observe(name="score_normalize")
    def score_normalize(state: GraphState) -> GraphState:
        session = state["session"]

        if not session.ideas_pool:
            logger.warning("[STEP] score-normalize | Пул идей пуст, пропускаем")
            session.current_node = "scores_normalized"
            storage.save_session(session)
            return {"session": session}

        logger.info("  [STEP] score-normalize | Линейная нормализация весов")

        try:
            total_score = sum(
                it.child_index + settings.SCORE_NORMALIZATION_EPSILON
                for it in session.ideas_pool
            )
            for it in session.ideas_pool:
                it.normalized_weight = (
                    it.child_index + settings.SCORE_NORMALIZATION_EPSILON
                ) / total_score
        except Exception as e:
            logger.error("  [ERROR] score-normalize: %s", e)
            equal_weight = 1.0 / len(session.ideas_pool)
            for it in session.ideas_pool:
                it.normalized_weight = equal_weight

        session.current_node = "scores_normalized"
        storage.save_session(session)
        return {"session": session}

    return score_normalize


# --- Фабрика: idea_sampler ----------------------------------------------------

def make_idea_sampler(
    storage: JSONStorage,
) -> Callable[[GraphState], GraphState]:
    """
    Детерминированная нода (с псевдослучайностью): взвешенная выборка
    финального плана из пула идей.
    Заполняет session.series_plan, session.full_plan_items, session.revision_history.
    """

    @observe(name="idea_sampler")
    def idea_sampler(state: GraphState) -> GraphState:
        session = state["session"]

        if not session.ideas_pool:
            logger.error("[STEP] idea-sampler | ERROR: пустой пул идей")
            session.current_node = "failed"
            storage.save_session(session)
            return {"session": session}

        count = session.request.count
        final_plan = _weighted_sample(session.ideas_pool, count)

        if not final_plan:
            logger.error("[STEP] idea-sampler | ERROR: не удалось выбрать идеи")
            session.current_node = "failed"
            storage.save_session(session)
            return {"session": session}

        session.series_plan = [item["theme"] for item in final_plan]
        session.full_plan_items = final_plan

        # Инициализируем историю правок исходной версией от планировщика
        for i, item in enumerate(final_plan):
            session.revision_history[str(i)] = [
                {
                    "source": "planner",
                    "theme": item.get("theme", ""),
                    "content": item.get("content", ""),
                    "note": "Исходная версия от планировщика",
                }
            ]

        logger.info(
            "  [STEP] idea-sampler | Выбрано %s уникальных идей из пула",
            len(final_plan),
        )
        logger.info(
            "[STEP] series-planner | Статус: OK | План из %s историй сформирован",
            len(final_plan),
        )
        for i, item in enumerate(final_plan):
            logger.info(
                "  %s. %s | %s", i + 1, item.get("theme"), item.get("content")
            )

        session.current_node = "series_planned"
        storage.save_session(session)
        return {"session": session}

    return idea_sampler


# --- Внутренние утилиты -------------------------------------------------------

def _weighted_sample(pool: List[Idea], count: int) -> List[dict]:
    """
    Взвешенная выборка без повторений с ренормализацией после каждого пика.
    Возвращает список dict-ов вида {"theme": str, "content": str}.
    """
    k = min(count, len(pool))
    pool_copy = list(pool)
    selected: List[dict] = []

    for _ in range(k):
        weights = [it.normalized_weight for it in pool_copy]
        idx = random.choices(range(len(pool_copy)), weights=weights, k=1)[0]
        it = pool_copy.pop(idx)
        selected.append({"theme": it.title, "content": it.summary})

        total_w = sum(p.normalized_weight for p in pool_copy)
        if total_w > 0:
            for p in pool_copy:
                p.normalized_weight /= total_w

    return selected