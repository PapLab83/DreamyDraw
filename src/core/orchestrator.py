import os
import json
import logging
from typing import List
from src.config import constants
from src.config.settings import settings
from src.models.schemas import GenerationRequest, SessionState, StoryItem, WorkMode
from src.providers.base import BaseLLMProvider, BaseImageProvider
from src.storage.json_storage import JSONStorage
from src.core.prompt_builder import PromptBuilder

USER_ARBITRATION_THRESHOLD = settings.USER_ARBITRATION_THRESHOLD
MAX_VALIDATION_RETRIES = settings.MAX_VALIDATION_RETRIES
logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(
            self,
            llm_provider: BaseLLMProvider,
            image_provider: BaseImageProvider,
            storage: JSONStorage,
            prompt_builder: PromptBuilder = None
    ):
        self.llm = llm_provider
        self.image = image_provider
        self.storage = storage
        self.prompt_builder = prompt_builder or PromptBuilder()

    def start_session(self, request: GenerationRequest) -> SessionState:
        session = SessionState(request=request)
        for i in range(request.count):
            session.stories.append(StoryItem(index=i))

        os.makedirs(os.path.join(self.storage.base_dir, session.session_id), exist_ok=True)

        self.storage.save_session(session)
        return session

    def run_pipeline(self, session_id: str) -> SessionState:
        session = self.storage.get_session(session_id)
        if not session or session.is_completed:
            return session

        from langfuse import observe
        from src.utils.langfuse_client import update_current_trace, log_trace_url

        # Оборачиваем всю работу пайплайна в один трейс через @observe
        @observe(name="orchestrator.run_pipeline")
        def _run() -> SessionState:
            nonlocal session

            # Обогащаем трейс метаданными
            update_current_trace(
                session_id=session.session_id,
                user_id="cli",
                tags=[
                    f"truth_mode:{session.request.truth_mode.value}",
                    f"work_mode:{session.request.work_mode.value}",
                    f"image_style:{session.request.image_style.value}",
                ],
                input={
                    "session_id": session_id,
                    "topic": session.request.topic,
                },
                metadata={
                    "truth_mode": session.request.truth_mode.value,
                    "text_style": session.request.text_style.value,
                    "image_style": session.request.image_style.value,
                    "work_mode": session.request.work_mode.value,
                    "count": session.request.count,
                    "current_node": session.current_node,
                },
            )
            log_trace_url()

            while session.current_node in [
                "start", "safety_passed", "config_passed",
                "series_planned", "plan_needs_refine", "plan_needs_user_arbitration"
            ]:
                if session.current_node == "start":
                    session = self._step_safety_gate(session)
                elif session.current_node == "safety_passed":
                    session = self._step_config_match(session)
                elif session.current_node == "config_passed":
                    session = self._step_series_planner(session)
                elif session.current_node == "series_planned":
                    session = self._step_plan_validator(session)
                    if session.current_node == "plan_needs_user_arbitration":
                        return session
                    if session.current_node == "plan_needs_refine":
                        continue
                elif session.current_node == "plan_needs_refine":
                    session = self._step_plan_refine(session)
                elif session.current_node == "plan_needs_user_arbitration":
                    session = self._step_plan_refine(session)

                if session.current_node == "failed":
                    return session

            if session.current_node == "plan_approved":
                logger.info("--- ФИНАЛЬНЫЙ ПЛАН СЕРИИ ---")
                for i in range(len(session.series_plan)):
                    item = session.approved_plan_items.get(str(i))
                    if not item and i < len(session.full_plan_items):
                        item = session.full_plan_items[i]
                    if item:
                        logger.info("  %s. %s | %s", i + 1, item.get("theme"), item.get("content"))
                logger.info("----------------------------")

                return self._pipeline_content_generation(session)

            return session

        try:
            return _run()
        finally:
            # Обновим итоговый output трейса (выполнится уже после @observe закрытия,
            # но на этот трейс не повлияет — данные уйдут в обновление)
            update_current_trace(
                output={
                    "current_node": session.current_node,
                    "is_completed": session.is_completed,
                    "validation_cycles": session.validation_cycles,
                },
            )

    def _pipeline_content_generation(self, session: SessionState) -> SessionState:
        from langfuse import observe

        @observe(name="content_generation")
        def _impl() -> SessionState:
            nonlocal session
            request = session.request

            for i in range(request.count):
                story = session.stories[i]

                if not story.text:
                    current_plan_full = session.full_plan_items
                    current_topic = ""
                    current_content = ""

                    if str(i) in session.approved_plan_items:
                        current_topic = session.approved_plan_items[str(i)].get("theme", "")
                        current_content = session.approved_plan_items[str(i)].get("content", "")
                    elif i < len(current_plan_full):
                        current_topic = current_plan_full[i].get("theme", "")
                        current_content = current_plan_full[i].get("content", "")

                    if current_topic:
                        story.sub_topic = current_topic
                    else:
                        current_topic = story.sub_topic if story.sub_topic else request.topic

                    temp_request = request.model_copy(update={"topic": current_topic})
                    prompt = self.prompt_builder.build_text_prompt(temp_request, session.global_context)

                    if current_content:
                        logger.debug("[DEBUG] История %s: Используется одобренный сюжет", i + 1)
                        logger.debug("Входящий сюжет: %s", current_content)
                        prompt += f"\n\nИСПОЛЬЗУЙ СЛЕДУЮЩИЙ СЮЖЕТ (ОДОБРЕНО): {current_content}"

                    raw_response = self.llm.generate_text(prompt)
                    story.text, story.questions = self._parse_llm_response(raw_response)
                    self.storage.save_session(session)

            if request.work_mode == WorkMode.CHECK:
                all_confirmed = all(s.is_confirmed for s in session.stories)
                if not all_confirmed:
                    return session

            for i in range(request.count):
                story = session.stories[i]
                if not story.image_path:
                    image_filename = constants.STORY_IMAGE_FILENAME_TEMPLATE.format(index=i)
                    image_path = os.path.join(self.storage.base_dir, session.session_id, image_filename)
                    prompt = self.prompt_builder.build_image_prompt(story.text, request.image_style.value)
                    story.image_path = self.image.generate_image(prompt, story.text, image_path)
                    self.storage.save_session(session)

            session.is_completed = True
            self.storage.save_session(session)
            return session

        return _impl()

    def _step_safety_gate(self, session: SessionState) -> SessionState:
        from langfuse import observe

        @observe(name="safety_gate")
        def _impl() -> SessionState:
            nonlocal session
            logger.info("[STEP] safety-gate | Проверка темы: %s", session.request.topic)
            prompt = self.prompt_builder.build_safety_prompt(session.request.topic)
            response_raw = self.llm.generate_text(prompt)
            try:
                clean_json = response_raw.replace("```json", "").replace("```", "").strip()
                result = json.loads(clean_json)
                if result.get("is_safe"):
                    logger.info("[STEP] safety-gate | Статус: OK")
                    session.current_node = "safety_passed"
                else:
                    logger.error("[STEP] safety-gate | Статус: FAILED | %s", result.get("reason"))
                    session.current_node = "failed"
            except Exception:
                session.current_node = "safety_passed" if "true" in response_raw.lower() else "failed"
            self.storage.save_session(session)
            return session

        return _impl()

    def _step_config_match(self, session: SessionState) -> SessionState:
        from langfuse import observe

        @observe(name="config_match")
        def _impl() -> SessionState:
            nonlocal session
            mode_val = session.request.truth_mode.value
            logger.info("[STEP] config-match | Проверка совместимости темы и режима '%s'", mode_val)
            prompt = self.prompt_builder.build_config_match_prompt(session.request.topic, mode_val)
            response_raw = self.llm.generate_text(prompt)
            try:
                clean_json = response_raw.replace("```json", "").replace("```", "").strip()
                result = json.loads(clean_json)
                if result.get("is_compatible"):
                    logger.info("[STEP] config-match | Статус: OK")
                    session.current_node = "config_passed"
                else:
                    suggested = result.get("suggested_mode", "")
                    logger.warning("[!] ВНИМАНИЕ: %s", result.get("reason"))
                    choice = input(f"Переключить на '{suggested}' и продолжить? (y/n): ").lower()
                    if choice == 'y':
                        from src.models.schemas import TruthMode
                        for m in TruthMode:
                            if m.value.lower() in suggested.lower() or suggested.lower() in m.value.lower():
                                session.request.truth_mode = m
                                break
                        session.current_node = "config_passed"
                    else:
                        session.current_node = "failed"
            except Exception:
                session.current_node = "config_passed"
            self.storage.save_session(session)
            return session

        return _impl()

    def _step_idea_scoring(self, session: SessionState) -> SessionState:
        if not session.ideas_pool:
            return session

        logger.info("  [STEP] idea-scoring | Оценка %s идей", len(session.ideas_pool))
        ideas_list = [
            {"index": i, "title": it.title, "summary": it.summary}
            for i, it in enumerate(session.ideas_pool)
        ]

        prompt = self.prompt_builder.build_idea_scoring_prompt(
            json.dumps(ideas_list, ensure_ascii=False),
            session.request.truth_mode.value
        )
        response_raw = self.llm.generate_text(prompt)

        try:
            clean_json = response_raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_json)
            scores = result.get("scores", [])

            for score_data in scores:
                idx = score_data.get("index")
                if 0 <= idx < len(session.ideas_pool):
                    session.ideas_pool[idx].child_index = score_data.get("child_index", 0.0)

            original_count = len(session.ideas_pool)
            session.ideas_pool = [it for it in session.ideas_pool if it.child_index >= settings.MIN_CHILD_INDEX]
            if len(session.ideas_pool) < original_count:
                logger.warning("  [!] Отсеяно %s небезопасных идей.", original_count - len(session.ideas_pool))

            if not session.ideas_pool:
                logger.warning("  [!] Пул идей пуст после фильтрации. Восстанавливаем fallback.")
                from src.models.schemas import Idea
                session.ideas_pool = [
                    Idea(title="Прогулка в лесу", summary="Маленький лис гуляет по лесу и изучает природу.")]
                session.ideas_pool[0].child_index = settings.FALLBACK_IDEA_CHILD_INDEX

        except Exception as e:
            logger.error("  [ERROR] idea-scoring: %s", e)
            for it in session.ideas_pool:
                it.child_index = settings.DEFAULT_IDEA_CHILD_INDEX

        return session

    def _step_score_normalize(self, session: SessionState) -> SessionState:
        if not session.ideas_pool:
            return session

        logger.info("  [STEP] score-normalize | Линейная нормализация весов")

        try:
            total_score = sum(it.child_index + settings.SCORE_NORMALIZATION_EPSILON for it in session.ideas_pool)

            for it in session.ideas_pool:
                it.normalized_weight = (it.child_index + settings.SCORE_NORMALIZATION_EPSILON) / total_score

        except Exception as e:
            logger.error("  [ERROR] score-normalize: %s", e)
            for it in session.ideas_pool:
                it.normalized_weight = 1.0 / len(session.ideas_pool)

        return session

    def _step_idea_sampler(self, session: SessionState, count: int = constants.DEFAULT_SAMPLER_COUNT) -> List[dict]:
        if not session.ideas_pool:
            return []

        import random

        k = min(count, len(session.ideas_pool))

        pool = list(session.ideas_pool)
        selected_items = []

        for _ in range(k):
            weights = [it.normalized_weight for it in pool]
            idx = random.choices(range(len(pool)), weights=weights, k=1)[0]
            it = pool.pop(idx)
            selected_items.append({
                "theme": it.title,
                "content": it.summary
            })
            total_w = sum(p.normalized_weight for p in pool)
            if total_w > 0:
                for p in pool:
                    p.normalized_weight /= total_w

        logger.info("  [STEP] idea-sampler | Выбрано %s уникальных идей из пула", len(selected_items))
        return selected_items

    def _step_series_planner(self, session: SessionState) -> SessionState:
        from langfuse import observe

        @observe(name="series_planner")
        def _impl() -> SessionState:
            nonlocal session

            logger.info("[STEP] series-planner | Составление пула идей для темы: %s", session.request.topic)

            prompt = self.prompt_builder.build_series_plan_prompt(
                session.request.topic,
                session.request.truth_mode.value
            )
            response_raw = self.llm.generate_text(prompt)

            try:
                clean_json = response_raw.replace("```json", "").replace("```", "").strip()
                result = json.loads(clean_json)
                session.global_context = result.get("global_context", "")
                raw_ideas = result.get("ideas", [])

                from src.models.schemas import Idea
                session.ideas_pool = [
                    Idea(title=it.get("theme", "Без названия"), summary=it.get("content", ""))
                    for it in raw_ideas
                ]
            except Exception as e:
                logger.error("[STEP] series-planner | ERROR: %s", e)
                session.current_node = "failed"
                return session

            if not session.ideas_pool:
                logger.error("[STEP] series-planner | ERROR: Не удалось получить пул идей")
                session.current_node = "failed"
                return session

            session = self._step_idea_scoring(session)
            session = self._step_score_normalize(session)

            final_plan = self._step_idea_sampler(session, count=session.request.count)

            if not final_plan:
                logger.error("[STEP] series-planner | ERROR: Не удалось выбрать идеи")
                session.current_node = "failed"
                return session

            session.series_plan = [item["theme"] for item in final_plan]
            session.full_plan_items = final_plan

            for i, item in enumerate(final_plan):
                session.revision_history[str(i)] = [{
                    "source": "planner",
                    "theme": item.get("theme", ""),
                    "content": item.get("content", ""),
                    "note": "Исходная версия от планировщика"
                }]

            logger.info("[STEP] series-planner | Статус: OK | План из %s историй сформирован", len(final_plan))
            for i, item in enumerate(final_plan):
                logger.info("  %s. %s | %s", i + 1, item.get("theme"), item.get("content"))

            session.current_node = "series_planned"
            self.storage.save_session(session)
            return session

        return _impl()

    def _step_plan_validator(self, session: SessionState) -> SessionState:
        from langfuse import observe

        @observe(name="plan_validator")
        def _impl() -> SessionState:
            nonlocal session
            logger.info("[STEP] plan-validator | Проверка плана на соответствие режиму...")
            logger.info(
                "[CYCLE] validation_cycles (до запуска) = %s/%s",
                session.validation_cycles,
                USER_ARBITRATION_THRESHOLD,
            )

            approved_indices = session.approved_indices
            current_plan_full = session.full_plan_items

            for i, item in enumerate(current_plan_full):
                if str(i) in session.approved_plan_items:
                    current_plan_full[i] = session.approved_plan_items[str(i)]
                    if i not in approved_indices:
                        approved_indices.append(i)

            session.full_plan_items = current_plan_full

            plan_to_verify = []
            already_approved_indices = []
            for i, item in enumerate(current_plan_full):
                if i in approved_indices:
                    content_preview = item.get('content', '')[
                                          :constants.VALIDATOR_CONTENT_PREVIEW_CHARS] + "..." if len(
                        item.get('content', '')) > constants.VALIDATOR_CONTENT_PREVIEW_CHARS else item.get('content',
                                                                                                           '')
                    logger.info(
                        "  [OK] Тема %s (%s): Уже одобрена. (%s)",
                        i + 1,
                        item.get("theme", "N/A"),
                        content_preview,
                    )
                    already_approved_indices.append(i)
                else:
                    plan_to_verify.append({
                        "index": i,
                        "theme": item.get("theme", ""),
                        "content": item.get("content", "")
                    })

            if not plan_to_verify:
                logger.info("[STEP] plan-validator | Статус: APPROVED (все темы уже одобрены)")
                if session.validation_cycles != 0:
                    logger.info("[CYCLE] validation_cycles reset -> 0 (все темы одобрены)")
                session.validation_cycles = 0
                session.current_node = "plan_approved"
                self.storage.save_session(session)
                return session

            full_plan_json = json.dumps(plan_to_verify, ensure_ascii=False)
            prompt = self.prompt_builder.build_plan_validator_prompt(full_plan_json, session.global_context,
                                                                     session.request.truth_mode.value)
            response_raw = self.llm.generate_text(prompt)

            try:
                clean_json = response_raw.replace("```json", "").replace("```", "").strip()
                result = json.loads(clean_json)
                raw_invalid = result.get("invalid_indices", [])

                mapping = {i: item["index"] for i, item in enumerate(plan_to_verify)}
                invalid_indices = [mapping[i] for i in raw_invalid if i in mapping]

                if not invalid_indices:
                    logger.info("[STEP] plan-validator | Статус: APPROVED")
                    session.current_node = "plan_approved"
                    verified_indices = [item["index"] for item in plan_to_verify]
                    for idx in verified_indices:
                        topic_data = next((it for it in plan_to_verify if it["index"] == idx), None)
                        if topic_data:
                            session.approved_plan_items[str(idx)] = {
                                "theme": topic_data["theme"],
                                "content": topic_data["content"]
                            }
                    session.approved_indices = list(set(approved_indices) | set(verified_indices))

                    if session.validation_cycles != 0:
                        logger.info("[CYCLE] validation_cycles reset -> 0 (план одобрен полностью)")
                    session.validation_cycles = 0
                else:
                    logger.warning("[STEP] plan-validator | Статус: REJECTED")
                    final_reasons, final_suggestions, final_indices = [], [], []

                    for i, rel_idx in enumerate(raw_invalid):
                        abs_idx = mapping.get(rel_idx)
                        if abs_idx is None: continue

                        reason = result.get("reasons", [])[i] if i < len(result.get("reasons", [])) else "Ошибка"
                        suggestion = result.get("suggestions", [])[i] if i < len(result.get("suggestions", [])) else ""

                        theme_title = current_plan_full[abs_idx].get("theme", "")
                        logger.warning("  - Тема %s (%s): %s", abs_idx + 1, theme_title, reason)
                        if suggestion:
                            logger.warning("    Рекомендация: %s", suggestion)

                        final_indices.append(abs_idx)
                        final_reasons.append(reason)
                        final_suggestions.append(suggestion)

                        hist_key = str(abs_idx)
                        if hist_key not in session.revision_history:
                            session.revision_history[hist_key] = []
                        session.revision_history[hist_key].append({
                            "source": "validator",
                            "theme": current_plan_full[abs_idx].get("theme", ""),
                            "content": current_plan_full[abs_idx].get("content", ""),
                            "note": f"REJECTED. Причина: {reason}. Рекомендация: {suggestion if isinstance(suggestion, str) else json.dumps(suggestion, ensure_ascii=False)}"
                        })

                    verified_indices = [item["index"] for item in plan_to_verify]
                    passed_indices = [i for i in verified_indices if i not in final_indices]

                    for idx in passed_indices:
                        topic_data = next((it for it in plan_to_verify if it["index"] == idx), None)
                        if topic_data:
                            logger.info("  [OK] Тема %s (%s): Проверка пройдена.", idx + 1, topic_data["theme"])
                            session.approved_plan_items[str(idx)] = {
                                "theme": topic_data["theme"],
                                "content": topic_data["content"]
                            }

                    session.approved_indices = list(set(approved_indices) | set(passed_indices))

                    session.validator_feedback = json.dumps({
                        "invalid_indices": final_indices,
                        "reasons": final_reasons,
                        "suggestions": final_suggestions
                    }, ensure_ascii=False)

                    session.validation_cycles += 1
                    logger.info(
                        "[CYCLE] validation_cycles += 1 -> %s/%s",
                        session.validation_cycles,
                        USER_ARBITRATION_THRESHOLD,
                    )

                    if session.validation_cycles > MAX_VALIDATION_RETRIES:
                        logger.error("[!!!] ОШИБКА: Превышен абсолютный лимит попыток (%s).", MAX_VALIDATION_RETRIES)
                        session.current_node = "failed"
                        self.storage.save_session(session)
                        return session

                    if session.validation_cycles >= USER_ARBITRATION_THRESHOLD:
                        logger.warning(
                            "[CYCLE] Достигнут порог %s REJECTED - требуется вмешательство пользователя",
                            USER_ARBITRATION_THRESHOLD,
                        )
                        session.current_node = "plan_needs_user_arbitration"
                    else:
                        logger.info(
                            "[CYCLE] Авто-режим: ревьюер и редактор работают самостоятельно (без участия пользователя)")
                        session.current_node = "plan_needs_refine"
            except Exception as e:
                logger.error("[STEP] plan-validator | ERROR: %s", e)
                session.current_node = "plan_approved"
            self.storage.save_session(session)
            return session

        return _impl()

    def _build_fallback_decisions(self, current_plan_full, currently_rejected, v_map, user_comment):
        """Fallback: если ревьюер не ответил, генерируем разумные решения сами.
        Логика: все отклонённые темы → REVISE (редактор разберётся), остальные → ALREADY_OK."""
        decisions = []
        for i, item in enumerate(current_plan_full):
            if i in currently_rejected:
                suggestion = v_map.get(i)
                decisions.append({
                    "index": i,
                    "decision": "REVISE",
                    "original_data": item,
                    "validator_suggestion": suggestion if isinstance(suggestion, dict) else None,
                    "user_comment": user_comment,
                    "reason_for_decision": "[FALLBACK] Ревьюер не ответил, отправляем редактору"
                })
            else:
                decisions.append({
                    "index": i,
                    "decision": "ALREADY_OK",
                    "original_data": item,
                    "validator_suggestion": None,
                    "user_comment": "",
                    "reason_for_decision": "[FALLBACK] Тема не в списке invalid_indices"
                })
        return decisions

    def _step_plan_refine(self, session: SessionState) -> SessionState:
        from langfuse import observe

        @observe(name="plan_refine")
        def _impl() -> SessionState:
            nonlocal session
            separator = "=" * constants.DEBUG_TEXT_SEPARATOR_WIDTH
            logger.info(separator)
            logger.info(
                "[STEP] plan-refine | Цикл %s/%s (абс. лимит %s)",
                session.validation_cycles,
                USER_ARBITRATION_THRESHOLD,
                MAX_VALIDATION_RETRIES,
            )
            logger.info(separator)

            current_plan_full = session.full_plan_items
            if not current_plan_full:
                current_plan_full = [{"theme": t, "content": ""} for t in session.series_plan]

            current_plan_json = json.dumps(current_plan_full, ensure_ascii=False)
            validator_feedback = getattr(session, "validator_feedback", "{}")
            user_comment = session.user_feedback if session.user_feedback is not None else ""

            v_feedback = {}
            try:
                v_feedback = json.loads(validator_feedback)
            except:
                pass
            v_suggestions = v_feedback.get("suggestions", [])
            v_indices = v_feedback.get("invalid_indices", [])
            v_reasons = v_feedback.get("reasons", [])
            v_map = {idx: v_suggestions[i] for i, idx in enumerate(v_indices) if i < len(v_suggestions)}
            currently_rejected = set(v_indices)

            logger.debug("[DEBUG/REVIEWER-INPUT] Текущий план (%s тем):", len(current_plan_full))
            for i, item in enumerate(current_plan_full):
                logger.debug(
                    "  [%s] %s | %s...",
                    i,
                    item.get("theme"),
                    (item.get("content") or "")[:constants.DEBUG_CONTENT_PREVIEW_CHARS],
                )
            logger.debug("[DEBUG/REVIEWER-INPUT] Замечания валидатора:")
            logger.debug("  invalid_indices: %s", v_indices)
            for i, idx in enumerate(v_indices):
                reason = v_reasons[i] if i < len(v_reasons) else "?"
                sug = v_map.get(idx, {})
                logger.debug("  - Тема %s: %s", idx + 1, reason)
                if isinstance(sug, dict):
                    logger.debug(
                        "    Рекомендация валидатора: theme='%s', content='%s...'",
                        sug.get("theme"),
                        (sug.get("content") or "")[:constants.DEBUG_CONTENT_PREVIEW_CHARS],
                    )
                else:
                    logger.debug("    Рекомендация валидатора (raw): %s", sug)
            if user_comment:
                logger.debug("[DEBUG/REVIEWER-INPUT] Комментарий пользователя: '%s'", user_comment)
            else:
                logger.debug("[DEBUG/REVIEWER-INPUT] Комментарий пользователя: <пустой>")

            reviewer_prompt = self.prompt_builder.build_plan_reviewer_prompt(
                current_plan_json,
                validator_feedback,
                user_comment
            )
            reviewer_response = self.llm.generate_text(reviewer_prompt)

            logger.debug("[DEBUG/REVIEWER-OUTPUT] Сырой ответ ревьюера:\n---START---\n%s\n---END---", reviewer_response)

            decisions = []
            try:
                reviewer_json = reviewer_response.replace("```json", "").replace("```", "").strip()
                if not reviewer_json:
                    raise ValueError("Пустой ответ от ревьюера")
                reviewer_result = json.loads(reviewer_json)
                decisions = reviewer_result.get("decisions", [])
                logger.debug("[DEBUG/REVIEWER-OUTPUT] Распарсено решений: %s", len(decisions))
            except Exception as e:
                logger.error("[STEP] plan-refine | Reviewer ERROR: %s", e)
                logger.warning("[FALLBACK] Ревьюер не дал валидного ответа - генерируем решения автоматически")
                decisions = self._build_fallback_decisions(
                    current_plan_full, currently_rejected, v_map, user_comment
                )
                logger.warning("[FALLBACK] Сгенерировано %s решений", len(decisions))

            logger.debug("[DEBUG/REVIEWER-DECISIONS] Решения по каждой теме:")
            for d in decisions:
                idx_print = d.get('index', '?')
                idx_print = idx_print + 1 if isinstance(idx_print, int) else '?'
                logger.debug(
                    "  Тема %s: decision=%s, reason='%s'",
                    idx_print,
                    d.get("decision"),
                    d.get("reason_for_decision", ""),
                )

            logger.info("--- ОБРАБОТКА РЕШЕНИЙ РЕВЬЮЕРА ---")
            items_to_revise = []
            new_approved_indices = []

            for d in decisions:
                idx = d.get("index")
                decision = d.get("decision")

                if not isinstance(idx, int):
                    logger.warning("  [?] Пропускаем решение без валидного индекса: %s", d)
                    continue

                if decision == "KEEP_ORIGINAL" and idx in currently_rejected and not user_comment:
                    logger.warning(
                        "  [GUARD] Тема %s: KEEP_ORIGINAL для отклонённой темы при пустом комментарии -> принудительно REVISE",
                        idx + 1,
                    )
                    decision = "REVISE"
                    d["decision"] = decision

                if decision == "REVISE":
                    if str(idx) in session.approved_plan_items:
                        del session.approved_plan_items[str(idx)]

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
                        orig_data = current_plan_full[idx] if idx < len(current_plan_full) else {}

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
                    session.revision_history[hist_key].append({
                        "source": "reviewer:keep_original",
                        "theme": orig_data.get("theme", ""),
                        "content": orig_data.get("content", ""),
                        "note": "Ревьюер настоял на исходной версии"
                    })

                elif decision == "ALREADY_OK":
                    orig_data = d.get("original_data")
                    if not (orig_data and isinstance(orig_data, dict)):
                        orig_data = current_plan_full[idx] if idx < len(current_plan_full) else {}

                    session.approved_plan_items[str(idx)] = orig_data
                    new_approved_indices.append(idx)
                    logger.info("  [OK] Тема %s: ALREADY_OK -> '%s'", idx + 1, orig_data.get("theme"))

                else:
                    logger.warning("  [?] Тема %s: неизвестное решение '%s' - пропускаем", idx + 1, decision)
            logger.info("----------------------------------")

            current_approved = set(session.approved_indices)
            session.approved_indices = list(current_approved | set(new_approved_indices))

            if items_to_revise:
                logger.debug("[DEBUG/REFINER-INPUT] Редактор получает %s тем(ы) на правку:", len(items_to_revise))
                for it in items_to_revise:
                    idx = it.get("index")
                    orig = it.get("original_data", {}) or {}
                    sug = it.get("validator_suggestion")
                    uc = it.get("user_comment", "") or ""
                    idx_print = idx + 1 if isinstance(idx, int) else '?'
                    logger.debug("  --- Тема %s ---", idx_print)
                    logger.debug(
                        "    original_data:        theme='%s', content='%s...'",
                        orig.get("theme"),
                        (orig.get("content") or "")[:constants.DEBUG_CONTENT_PREVIEW_CHARS],
                    )
                    if isinstance(sug, dict):
                        logger.debug(
                            "    validator_suggestion: theme='%s', content='%s...'",
                            sug.get("theme"),
                            (sug.get("content") or "")[:constants.DEBUG_CONTENT_PREVIEW_CHARS],
                        )
                    else:
                        logger.debug("    validator_suggestion: %s", sug)
                    logger.debug("    user_comment:         '%s'", uc)
                    logger.debug("    reason_for_decision:  '%s'", it.get("reason_for_decision", ""))

                refine_payload = json.dumps({"items_to_revise": items_to_revise}, ensure_ascii=False)

                refine_plan_context = []
                for i in range(len(session.series_plan)):
                    item = session.approved_plan_items.get(str(i))
                    if not item:
                        item = current_plan_full[i]
                    refine_plan_context.append(item)

                prompt = self.prompt_builder.build_plan_refine_prompt(
                    json.dumps(refine_plan_context, ensure_ascii=False),
                    refine_payload,
                    session.request.truth_mode.value
                )
                response_raw = self.llm.generate_text(prompt)

                logger.debug("[DEBUG/REFINER-OUTPUT] Сырой ответ редактора:\n---START---\n%s\n---END---", response_raw)

                try:
                    clean_json = response_raw.replace("```json", "").replace("```", "").strip()
                    if not clean_json:
                        raise ValueError("Пустой ответ от редактора")
                    result = json.loads(clean_json)
                    revised_items = result.get("revised_items", [])

                    logger.debug("[DEBUG/REFINER-OUTPUT] Распарсено правок: %s", len(revised_items))

                    for item in revised_items:
                        idx = item.get("index")
                        new_theme = item.get("theme")
                        new_content = item.get("content")

                        if idx is None or not isinstance(idx, int):
                            logger.warning("  [!] Пропускаем правку без индекса: %s", item)
                            continue

                        if idx < len(current_plan_full):
                            current_plan_full[idx] = {"theme": new_theme, "content": new_content}

                        logger.info("  [OK] Тема %s обновлена редактором:", idx + 1)
                        logger.info("       Тема: %s", new_theme)
                        logger.info("       Сюжет: %s", new_content)

                        hist_key = str(idx)
                        if hist_key not in session.revision_history:
                            session.revision_history[hist_key] = []
                        session.revision_history[hist_key].append({
                            "source": "refiner",
                            "theme": new_theme or "",
                            "content": new_content or "",
                            "note": "Редактор переписал по фидбеку валидатора" + (
                                f" + комментарий пользователя: {user_comment}" if user_comment else "")
                        })
                except Exception as e:
                    logger.error("[STEP] plan-refine | Refiner ERROR: %s", e)
                    session.current_node = "failed"
                    return session
            else:
                logger.debug("[DEBUG/REFINER] Редактор не вызывался - нет тем с REVISE")

            final_plan = []
            for i in range(len(session.series_plan)):
                item = session.approved_plan_items.get(str(i))
                if not item:
                    item = current_plan_full[i]
                final_plan.append(item)

            session.full_plan_items = final_plan
            session.series_plan = [it["theme"] for it in final_plan]

            logger.debug("[DEBUG/POST-REFINE] План, который уйдет на повторную валидацию:")
            for i, item in enumerate(final_plan):
                approved = "✓" if str(i) in session.approved_plan_items else " "
                logger.debug(
                    "  [%s] Тема %s: '%s' | %s...",
                    approved,
                    i + 1,
                    item.get("theme"),
                    (item.get("content") or "")[:constants.DEBUG_CONTENT_PREVIEW_CHARS],
                )
            logger.debug("  approved_indices: %s", session.approved_indices)
            logger.debug(separator)

            session.user_feedback = None
            session.current_node = "series_planned"

            self.storage.save_session(session)
            return session

        return _impl()

    def _parse_llm_response(self, text: str):
        story_part, questions = "", []
        q_start = text.find("Вопросы:")
        if q_start != -1:
            story_part = text[:q_start].replace("История:", "").replace("Текст истории:", "").strip()
            q_list = text[q_start:].replace("Вопросы:", "").strip().split("\n")
            questions = [q.strip(constants.QUESTION_NUMBERING_STRIP_CHARS) for q in q_list if q.strip()]
        else:
            story_part = text.replace("История:", "").replace("Текст истории:", "").strip()
        return story_part, questions

    def confirm_story(self, session_id: str, index: int) -> SessionState:
        session = self.storage.get_session(session_id)
        if session and index < len(session.stories):
            session.stories[index].is_confirmed = True
            self.storage.save_session(session)
        return session
