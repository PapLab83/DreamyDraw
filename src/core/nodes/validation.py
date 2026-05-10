"""
Ноды фазы валидации плана: plan_validator, plan_reviewer, plan_refiner, plan_arbitration.

Цикл: validator → (reviewer → refiner) → validator → ...
После USER_ARBITRATION_THRESHOLD REJECTED-циклов — interrupt в plan_arbitration.
"""

import json
import logging
from typing import Callable

from langfuse import observe
from langgraph.types import interrupt

from src.config import constants
from src.config.settings import settings
from src.core.graph.state import GraphState
from src.core.prompt_builder import PromptBuilder
from src.core.utils.json_parser import parse_llm_json
from src.providers.base import BaseLLMProvider
from src.storage.json_storage import JSONStorage

logger = logging.getLogger(__name__)

USER_ARBITRATION_THRESHOLD = settings.USER_ARBITRATION_THRESHOLD
MAX_VALIDATION_RETRIES = settings.MAX_VALIDATION_RETRIES


# --- Фабрика: plan_validator --------------------------------------------------

def make_plan_validator(
    llm: BaseLLMProvider,
    storage: JSONStorage,
    prompt_builder: PromptBuilder,
) -> Callable[[GraphState], GraphState]:
    """
    LLM-нода: проверяет план на соответствие режиму.
    Темы из approved_indices пропускает. При REJECTED — инкремент validation_cycles.
    """

    @observe(name="plan_validator")
    def plan_validator(state: GraphState) -> GraphState:
        session = state["session"]
        logger.info("[STEP] plan-validator | Проверка плана на соответствие режиму...")
        logger.info(
            "[CYCLE] validation_cycles (до запуска) = %s/%s",
            session.validation_cycles,
            USER_ARBITRATION_THRESHOLD,
        )

        approved_indices = list(session.approved_indices)
        current_plan_full = session.full_plan_items

        # Синхронизируем full_plan_items с approved_plan_items
        for i, _ in enumerate(current_plan_full):
            if str(i) in session.approved_plan_items:
                current_plan_full[i] = session.approved_plan_items[str(i)]
                if i not in approved_indices:
                    approved_indices.append(i)
        session.full_plan_items = current_plan_full

        # Готовим список тем, которые надо валидировать (не одобренные)
        plan_to_verify = []
        for i, item in enumerate(current_plan_full):
            if i in approved_indices:
                content_preview = _preview(
                    item.get("content", ""),
                    constants.VALIDATOR_CONTENT_PREVIEW_CHARS,
                )
                logger.info(
                    "  [OK] Тема %s (%s): Уже одобрена. (%s)",
                    i + 1,
                    item.get("theme", "N/A"),
                    content_preview,
                )
            else:
                plan_to_verify.append(
                    {
                        "index": i,
                        "theme": item.get("theme", ""),
                        "content": item.get("content", ""),
                    }
                )

        # Все темы уже одобрены — выходим
        if not plan_to_verify:
            logger.info("[STEP] plan-validator | Статус: APPROVED (все темы одобрены)")
            if session.validation_cycles != 0:
                logger.info("[CYCLE] validation_cycles reset -> 0 (все темы одобрены)")
            session.validation_cycles = 0
            session.current_node = "plan_approved"
            storage.save_session(session)
            return {"session": session}

        # Вызываем валидатор
        full_plan_json = json.dumps(plan_to_verify, ensure_ascii=False)
        prompt = prompt_builder.build_plan_validator_prompt(
            full_plan_json,
            session.global_context,
            session.request.truth_mode.value,
        )
        response_raw = llm.generate_text(prompt)

        result = parse_llm_json(response_raw, default={}, context="plan_validator")
        if not result:
            logger.error("[STEP] plan-validator | ERROR: не удалось распарсить ответ")
            # В оригинале при ошибке шли в plan_approved — сохраняем поведение
            session.current_node = "plan_approved"
            storage.save_session(session)
            return {"session": session}

        raw_invalid = result.get("invalid_indices", [])

        # Мэппинг: индексы в plan_to_verify → абсолютные индексы в full_plan_items
        mapping = {i: item["index"] for i, item in enumerate(plan_to_verify)}
        invalid_indices = [mapping[i] for i in raw_invalid if i in mapping]

        if not invalid_indices:
            # APPROVED — все темы прошли
            logger.info("[STEP] plan-validator | Статус: APPROVED")
            verified_indices = [item["index"] for item in plan_to_verify]
            for idx in verified_indices:
                topic_data = next(
                    (it for it in plan_to_verify if it["index"] == idx), None
                )
                if topic_data:
                    session.approved_plan_items[str(idx)] = {
                        "theme": topic_data["theme"],
                        "content": topic_data["content"],
                    }
            session.approved_indices = list(
                set(approved_indices) | set(verified_indices)
            )
            session.current_node = "plan_approved"

            if session.validation_cycles != 0:
                logger.info(
                    "[CYCLE] validation_cycles reset -> 0 (план одобрен полностью)"
                )
            session.validation_cycles = 0
            storage.save_session(session)
            return {"session": session}

        # REJECTED — есть что править
        logger.warning("[STEP] plan-validator | Статус: REJECTED")
        final_reasons, final_suggestions, final_indices = [], [], []

        for i, rel_idx in enumerate(raw_invalid):
            abs_idx = mapping.get(rel_idx)
            if abs_idx is None:
                continue

            reasons = result.get("reasons", [])
            suggestions = result.get("suggestions", [])
            reason = reasons[i] if i < len(reasons) else "Ошибка"
            suggestion = suggestions[i] if i < len(suggestions) else ""

            theme_title = current_plan_full[abs_idx].get("theme", "")
            logger.warning("  - Тема %s (%s): %s", abs_idx + 1, theme_title, reason)
            if suggestion:
                logger.warning("    Рекомендация: %s", suggestion)

            final_indices.append(abs_idx)
            final_reasons.append(reason)
            final_suggestions.append(suggestion)

            # Запись в историю
            hist_key = str(abs_idx)
            if hist_key not in session.revision_history:
                session.revision_history[hist_key] = []
            session.revision_history[hist_key].append(
                {
                    "source": "validator",
                    "theme": current_plan_full[abs_idx].get("theme", ""),
                    "content": current_plan_full[abs_idx].get("content", ""),
                    "note": (
                        f"REJECTED. Причина: {reason}. "
                        f"Рекомендация: "
                        f"{suggestion if isinstance(suggestion, str) else json.dumps(suggestion, ensure_ascii=False)}"
                    ),
                }
            )

        # Темы, которые НЕ в invalid — одобряем
        verified_indices = [item["index"] for item in plan_to_verify]
        passed_indices = [i for i in verified_indices if i not in final_indices]
        for idx in passed_indices:
            topic_data = next(
                (it for it in plan_to_verify if it["index"] == idx), None
            )
            if topic_data:
                logger.info(
                    "  [OK] Тема %s (%s): Проверка пройдена.",
                    idx + 1,
                    topic_data["theme"],
                )
                session.approved_plan_items[str(idx)] = {
                    "theme": topic_data["theme"],
                    "content": topic_data["content"],
                }
        session.approved_indices = list(set(approved_indices) | set(passed_indices))

        # Сохраняем фидбек валидатора для рефайнера
        session.validator_feedback = json.dumps(
            {
                "invalid_indices": final_indices,
                "reasons": final_reasons,
                "suggestions": final_suggestions,
            },
            ensure_ascii=False,
        )

        # Инкремент счётчика
        session.validation_cycles += 1
        logger.info(
            "[CYCLE] validation_cycles += 1 -> %s/%s",
            session.validation_cycles,
            USER_ARBITRATION_THRESHOLD,
        )

        # Жёсткий предел
        if session.validation_cycles > MAX_VALIDATION_RETRIES:
            logger.error(
                "[!!!] ОШИБКА: Превышен абсолютный лимит попыток (%s).",
                MAX_VALIDATION_RETRIES,
            )
            session.current_node = "failed"
            storage.save_session(session)
            return {"session": session}

        # Порог арбитража пользователя
        if session.validation_cycles >= USER_ARBITRATION_THRESHOLD:
            logger.warning(
                "[CYCLE] Достигнут порог %s REJECTED - требуется вмешательство пользователя",
                USER_ARBITRATION_THRESHOLD,
            )
            session.current_node = "plan_needs_user_arbitration"
        else:
            logger.info(
                "[CYCLE] Авто-режим: ревьюер и редактор работают самостоятельно"
            )
            session.current_node = "plan_needs_refine"

        storage.save_session(session)
        return {"session": session}

    return plan_validator


# --- Фабрика: plan_reviewer ---------------------------------------------------

def make_plan_reviewer(
    llm: BaseLLMProvider,
    storage: JSONStorage,
    prompt_builder: PromptBuilder,
) -> Callable[[GraphState], GraphState]:
    """
    LLM-нода: ревьюер принимает решения по каждой отклонённой теме.
    Записывает items_to_revise в session.pending_revisions.
    Темы с ALREADY_OK сразу одобряет, KEEP_ORIGINAL — записывает в историю.
    """

    @observe(name="plan_reviewer")
    def plan_reviewer(state: GraphState) -> GraphState:
        session = state["session"]
        separator = "=" * constants.DEBUG_TEXT_SEPARATOR_WIDTH
        logger.info(separator)
        logger.info(
            "[STEP] plan-reviewer | Цикл %s/%s (абс. лимит %s)",
            session.validation_cycles,
            USER_ARBITRATION_THRESHOLD,
            MAX_VALIDATION_RETRIES,
        )
        logger.info(separator)

        current_plan_full = session.full_plan_items
        if not current_plan_full:
            current_plan_full = [
                {"theme": t, "content": ""} for t in session.series_plan
            ]

        validator_feedback = session.validator_feedback or "{}"
        user_comment = session.user_feedback if session.user_feedback is not None else ""

        v_feedback = parse_llm_json(validator_feedback, default={}, context="reviewer:v_feedback")
        v_suggestions = v_feedback.get("suggestions", [])
        v_indices = v_feedback.get("invalid_indices", [])
        v_map = {
            idx: v_suggestions[i]
            for i, idx in enumerate(v_indices)
            if i < len(v_suggestions)
        }
        currently_rejected = set(v_indices)

        _debug_log_reviewer_input(current_plan_full, v_indices, v_feedback.get("reasons", []), v_map, user_comment)

        # Вызов ревьюера
        current_plan_json = json.dumps(current_plan_full, ensure_ascii=False)
        reviewer_prompt = prompt_builder.build_plan_reviewer_prompt(
            current_plan_json, validator_feedback, user_comment
        )
        reviewer_response = llm.generate_text(reviewer_prompt)

        logger.debug(
            "[DEBUG/REVIEWER-OUTPUT] Сырой ответ:\n---START---\n%s\n---END---",
            reviewer_response,
        )

        reviewer_result = parse_llm_json(
            reviewer_response, default={}, context="plan_reviewer"
        )

        if not reviewer_result or "decisions" not in reviewer_result:
            logger.warning(
                "[FALLBACK] Ревьюер не дал валидного ответа - генерируем решения автоматически"
            )
            decisions = _build_fallback_decisions(
                current_plan_full, currently_rejected, v_map, user_comment
            )
            logger.warning("[FALLBACK] Сгенерировано %s решений", len(decisions))
        else:
            decisions = reviewer_result.get("decisions", [])
            logger.debug(
                "[DEBUG/REVIEWER-OUTPUT] Распарсено решений: %s", len(decisions)
            )

        _debug_log_reviewer_decisions(decisions)

        logger.info("--- ОБРАБОТКА РЕШЕНИЙ РЕВЬЮЕРА ---")
        items_to_revise = []
        new_approved_indices = []

        for d in decisions:
            idx = d.get("index")
            decision = d.get("decision")

            if not isinstance(idx, int):
                logger.warning("  [?] Пропускаем решение без валидного индекса: %s", d)
                continue

            # Страховка: KEEP_ORIGINAL для отклонённой темы при пустом комментарии → REVISE
            if (
                decision == "KEEP_ORIGINAL"
                and idx in currently_rejected
                and not user_comment
            ):
                logger.warning(
                    "  [GUARD] Тема %s: KEEP_ORIGINAL для отклонённой при пустом комментарии -> REVISE",
                    idx + 1,
                )
                decision = "REVISE"
                d["decision"] = decision

            if decision == "REVISE":
                # Убираем из одобренных, если там была
                if str(idx) in session.approved_plan_items:
                    del session.approved_plan_items[str(idx)]

                # Гарантируем наличие original_data и validator_suggestion
                orig = d.get("original_data", {})
                if not (orig and isinstance(orig, dict)) or not orig.get("content"):
                    if idx < len(current_plan_full):
                        orig = current_plan_full[idx]
                        d["original_data"] = orig
                if not d.get("validator_suggestion"):
                    d["validator_suggestion"] = v_map.get(idx)

                items_to_revise.append(d)
                logger.info("  [->] Тема %s: REVISE -> отправляем РЕДАКТОРУ", idx + 1)

            elif decision == "KEEP_ORIGINAL":
                orig_data = d.get("original_data")
                if not (orig_data and isinstance(orig_data, dict)):
                    orig_data = (
                        current_plan_full[idx] if idx < len(current_plan_full) else {}
                    )

                if str(idx) in session.approved_plan_items:
                    del session.approved_plan_items[str(idx)]
                logger.warning(
                    "  [!] Тема %s: KEEP_ORIGINAL -> '%s' (по требованию автора)",
                    idx + 1,
                    orig_data.get("theme"),
                )

                hist_key = str(idx)
                if hist_key not in session.revision_history:
                    session.revision_history[hist_key] = []
                session.revision_history[hist_key].append(
                    {
                        "source": "reviewer:keep_original",
                        "theme": orig_data.get("theme", ""),
                        "content": orig_data.get("content", ""),
                        "note": "Ревьюер настоял на исходной версии",
                    }
                )

            elif decision == "ALREADY_OK":
                orig_data = d.get("original_data")
                if not (orig_data and isinstance(orig_data, dict)):
                    orig_data = (
                        current_plan_full[idx] if idx < len(current_plan_full) else {}
                    )

                session.approved_plan_items[str(idx)] = orig_data
                new_approved_indices.append(idx)
                logger.info(
                    "  [OK] Тема %s: ALREADY_OK -> '%s'",
                    idx + 1,
                    orig_data.get("theme"),
                )

            else:
                logger.warning(
                    "  [?] Тема %s: неизвестное решение '%s' - пропускаем",
                    idx + 1,
                    decision,
                )
        logger.info("----------------------------------")

        # Обновляем approved_indices
        current_approved = set(session.approved_indices)
        session.approved_indices = list(current_approved | set(new_approved_indices))

        # Сохраняем items_to_revise для рефайнера
        session.pending_revisions = items_to_revise

        session.current_node = "reviewer_done"
        storage.save_session(session)
        return {"session": session}

    return plan_reviewer


# --- Фабрика: plan_refiner ----------------------------------------------------

def make_plan_refiner(
    llm: BaseLLMProvider,
    storage: JSONStorage,
    prompt_builder: PromptBuilder,
) -> Callable[[GraphState], GraphState]:
    """
    LLM-нода: переписывает темы с decision=REVISE по фидбеку валидатора.
    Читает session.pending_revisions. Если список пуст — пропускает LLM-вызов.
    После работы обнуляет user_feedback и возвращает план на повторную валидацию.
    """

    @observe(name="plan_refiner")
    def plan_refiner(state: GraphState) -> GraphState:
        session = state["session"]
        items_to_revise = session.pending_revisions or []
        user_comment = session.user_feedback if session.user_feedback is not None else ""

        current_plan_full = session.full_plan_items
        if not current_plan_full:
            current_plan_full = [
                {"theme": t, "content": ""} for t in session.series_plan
            ]

        if items_to_revise:
            _debug_log_refiner_input(items_to_revise)

            refine_payload = json.dumps(
                {"items_to_revise": items_to_revise}, ensure_ascii=False
            )

            # Контекст для редактора = текущее состояние плана с одобренными темами
            refine_plan_context = []
            for i in range(len(session.series_plan)):
                item = session.approved_plan_items.get(str(i))
                if not item:
                    item = current_plan_full[i]
                refine_plan_context.append(item)

            prompt = prompt_builder.build_plan_refine_prompt(
                json.dumps(refine_plan_context, ensure_ascii=False),
                refine_payload,
                session.request.truth_mode.value,
            )
            response_raw = llm.generate_text(prompt)

            logger.debug(
                "[DEBUG/REFINER-OUTPUT] Сырой ответ:\n---START---\n%s\n---END---",
                response_raw,
            )

            result = parse_llm_json(response_raw, default={}, context="plan_refiner")
            if not result or "revised_items" not in result:
                logger.error("[STEP] plan-refiner | ERROR: пустой/некорректный ответ")
                session.current_node = "failed"
                storage.save_session(session)
                return {"session": session}

            revised_items = result.get("revised_items", [])
            logger.debug(
                "[DEBUG/REFINER-OUTPUT] Распарсено правок: %s", len(revised_items)
            )

            for item in revised_items:
                idx = item.get("index")
                new_theme = item.get("theme")
                new_content = item.get("content")

                if idx is None or not isinstance(idx, int):
                    logger.warning("  [!] Пропускаем правку без индекса: %s", item)
                    continue

                if idx < len(current_plan_full):
                    current_plan_full[idx] = {
                        "theme": new_theme,
                        "content": new_content,
                    }

                logger.info("  [OK] Тема %s обновлена редактором:", idx + 1)
                logger.info("       Тема: %s", new_theme)
                logger.info("       Сюжет: %s", new_content)

                hist_key = str(idx)
                if hist_key not in session.revision_history:
                    session.revision_history[hist_key] = []
                session.revision_history[hist_key].append(
                    {
                        "source": "refiner",
                        "theme": new_theme or "",
                        "content": new_content or "",
                        "note": "Редактор переписал по фидбеку валидатора"
                        + (
                            f" + комментарий пользователя: {user_comment}"
                            if user_comment
                            else ""
                        ),
                    }
                )
        else:
            logger.debug("[DEBUG/REFINER] Редактор не вызывался - нет тем с REVISE")

        # Собираем финальный план
        final_plan = []
        for i in range(len(session.series_plan)):
            item = session.approved_plan_items.get(str(i))
            if not item:
                item = current_plan_full[i]
            final_plan.append(item)

        session.full_plan_items = final_plan
        session.series_plan = [it["theme"] for it in final_plan]

        _debug_log_post_refine(final_plan, session.approved_plan_items, session.approved_indices)

        # Обнуляем временные данные
        session.user_feedback = None
        session.pending_revisions = []
        session.current_node = "series_planned"

        storage.save_session(session)
        return {"session": session}

    return plan_refiner


# --- Фабрика: plan_arbitration (interrupt) ------------------------------------

def make_plan_arbitration(
    storage: JSONStorage,
) -> Callable[[GraphState], GraphState]:
    """
    Interrupt-нода: вмешательство пользователя при validation_cycles >= порога.

    Через Command(resume=<value>) получает:
    - 'ок' / 'хорошо' / 'хватит' / 'достаточно' / 'больше не' — форсированное одобрение
    - любой другой текст — комментарий передаётся ревьюеру/редактору
    - пустая строка — продолжаем без комментария
    """

    @observe(name="plan_arbitration")
    def plan_arbitration(state: GraphState) -> GraphState:
        session = state["session"]

        # Собираем данные для отображения пользователю
        v_feedback = parse_llm_json(
            session.validator_feedback or "{}",
            default={},
            context="arbitration:v_feedback",
        )
        problem_indices = v_feedback.get("invalid_indices", [])

        # Готовим краткую сводку проблемных тем для interrupt-payload
        problems_summary = []
        for idx in problem_indices:
            history = session.revision_history.get(str(idx), [])
            last_validator = next(
                (r for r in reversed(history) if r.get("source") == "validator"), None
            )
            last_refiner = next(
                (r for r in reversed(history) if r.get("source") == "refiner"), None
            )
            problems_summary.append(
                {
                    "index": idx,
                    "current_theme": (last_refiner or {}).get("theme"),
                    "current_content": (last_refiner or {}).get("content"),
                    "last_validator_note": (last_validator or {}).get("note"),
                    "history_size": len(history),
                }
            )

        user_input = interrupt(
            {
                "type": "plan_arbitration",
                "validation_cycles": session.validation_cycles,
                "threshold": USER_ARBITRATION_THRESHOLD,
                "problem_indices": problem_indices,
                "problems": problems_summary,
            }
        )

        user_text = (user_input or "").strip()
        user_text_lower = user_text.lower()

        # Форсированное одобрение
        if user_text_lower in constants.FORCE_APPROVE_COMMANDS:
            logger.info("[USER] Принудительное одобрение текущего варианта.")
            for idx in problem_indices:
                if idx < len(session.full_plan_items):
                    session.approved_plan_items[str(idx)] = session.full_plan_items[idx]
                    if idx not in session.approved_indices:
                        session.approved_indices.append(idx)
            logger.info(
                "[CYCLE] validation_cycles reset -> 0 (форсированное одобрение)"
            )
            session.validation_cycles = 0
            session.current_node = "plan_approved"
            session.user_feedback = None
        else:
            # Свободный комментарий или пустая строка
            if user_text:
                session.user_feedback = user_text
                logger.info("[USER] Комментарий передан ревьюеру/редактору.")
            else:
                session.user_feedback = None
                logger.info(
                    "[USER] Без комментария — ревьюер и редактор работают сами."
                )
            session.current_node = "plan_needs_refine"

        storage.save_session(session)
        return {"session": session}

    return plan_arbitration


# --- Внутренние утилиты -------------------------------------------------------

def _preview(text: str, max_chars: int) -> str:
    """Превью текста с обрезкой."""
    if not text:
        return ""
    return text[:max_chars] + "..." if len(text) > max_chars else text


def _build_fallback_decisions(current_plan_full, currently_rejected, v_map, user_comment):
    """
    Fallback при пустом ответе ревьюера:
    - отклонённые → REVISE
    - остальные → ALREADY_OK
    """
    decisions = []
    for i, item in enumerate(current_plan_full):
        if i in currently_rejected:
            suggestion = v_map.get(i)
            decisions.append(
                {
                    "index": i,
                    "decision": "REVISE",
                    "original_data": item,
                    "validator_suggestion": suggestion if isinstance(suggestion, dict) else None,
                    "user_comment": user_comment,
                    "reason_for_decision": "[FALLBACK] Ревьюер не ответил, отправляем редактору",
                }
            )
        else:
            decisions.append(
                {
                    "index": i,
                    "decision": "ALREADY_OK",
                    "original_data": item,
                    "validator_suggestion": None,
                    "user_comment": "",
                    "reason_for_decision": "[FALLBACK] Тема не в списке invalid_indices",
                }
            )
    return decisions


def _debug_log_reviewer_input(current_plan_full, v_indices, v_reasons, v_map, user_comment):
    """Подробный debug-лог входных данных ревьюера."""
    logger.debug("[DEBUG/REVIEWER-INPUT] Текущий план (%s тем):", len(current_plan_full))
    for i, item in enumerate(current_plan_full):
        logger.debug(
            "  [%s] %s | %s...",
            i,
            item.get("theme"),
            (item.get("content") or "")[: constants.DEBUG_CONTENT_PREVIEW_CHARS],
        )
    logger.debug("[DEBUG/REVIEWER-INPUT] Замечания валидатора:")
    logger.debug("  invalid_indices: %s", v_indices)
    for i, idx in enumerate(v_indices):
        reason = v_reasons[i] if i < len(v_reasons) else "?"
        sug = v_map.get(idx, {})
        logger.debug("  - Тема %s: %s", idx + 1, reason)
        if isinstance(sug, dict):
            logger.debug(
                "    Рекомендация: theme='%s', content='%s...'",
                sug.get("theme"),
                (sug.get("content") or "")[: constants.DEBUG_CONTENT_PREVIEW_CHARS],
            )
        else:
            logger.debug("    Рекомендация (raw): %s", sug)
    if user_comment:
        logger.debug("[DEBUG/REVIEWER-INPUT] Комментарий пользователя: '%s'", user_comment)
    else:
        logger.debug("[DEBUG/REVIEWER-INPUT] Комментарий пользователя: <пустой>")


def _debug_log_reviewer_decisions(decisions):
    """Debug-лог решений ревьюера."""
    logger.debug("[DEBUG/REVIEWER-DECISIONS] Решения по каждой теме:")
    for d in decisions:
        idx_print = d.get("index", "?")
        idx_print = idx_print + 1 if isinstance(idx_print, int) else "?"
        logger.debug(
            "  Тема %s: decision=%s, reason='%s'",
            idx_print,
            d.get("decision"),
            d.get("reason_for_decision", ""),
        )


def _debug_log_refiner_input(items_to_revise):
    """Debug-лог входных данных рефайнера."""
    logger.debug(
        "[DEBUG/REFINER-INPUT] Редактор получает %s тем(ы) на правку:",
        len(items_to_revise),
    )
    for it in items_to_revise:
        idx = it.get("index")
        orig = it.get("original_data", {}) or {}
        sug = it.get("validator_suggestion")
        uc = it.get("user_comment", "") or ""
        idx_print = idx + 1 if isinstance(idx, int) else "?"
        logger.debug("  --- Тема %s ---", idx_print)
        logger.debug(
            "    original_data:        theme='%s', content='%s...'",
            orig.get("theme"),
            (orig.get("content") or "")[: constants.DEBUG_CONTENT_PREVIEW_CHARS],
        )
        if isinstance(sug, dict):
            logger.debug(
                "    validator_suggestion: theme='%s', content='%s...'",
                sug.get("theme"),
                (sug.get("content") or "")[: constants.DEBUG_CONTENT_PREVIEW_CHARS],
            )
        else:
            logger.debug("    validator_suggestion: %s", sug)
        logger.debug("    user_comment:         '%s'", uc)
        logger.debug(
            "    reason_for_decision:  '%s'", it.get("reason_for_decision", "")
        )


def _debug_log_post_refine(final_plan, approved_plan_items, approved_indices):
    """Debug-лог состояния плана после работы рефайнера."""
    separator = "=" * constants.DEBUG_TEXT_SEPARATOR_WIDTH
    logger.debug("[DEBUG/POST-REFINE] План, который уйдет на повторную валидацию:")
    for i, item in enumerate(final_plan):
        approved = "✓" if str(i) in approved_plan_items else " "
        logger.debug(
            "  [%s] Тема %s: '%s' | %s...",
            approved,
            i + 1,
            item.get("theme"),
            (item.get("content") or "")[: constants.DEBUG_CONTENT_PREVIEW_CHARS],
        )
    logger.debug("  approved_indices: %s", approved_indices)
    logger.debug(separator)