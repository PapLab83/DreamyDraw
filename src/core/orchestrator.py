import os
import json
import time
from typing import List
from src.models.schemas import GenerationRequest, SessionState, StoryItem, WorkMode
from src.providers.base import BaseLLMProvider, BaseImageProvider
from src.storage.json_storage import JSONStorage
from src.core.prompt_builder import PromptBuilder

# Порог автоматических циклов валидатор↔редактор до подключения пользователя
USER_ARBITRATION_THRESHOLD = 3
# Абсолютный потолок попыток (защита от бесконечного цикла)
MAX_VALIDATION_RETRIES = 5


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
                # Если требуется арбитраж пользователя — выходим в main.py
                if session.current_node == "plan_needs_user_arbitration":
                    return session
                # Иначе при REJECTED продолжаем автоматически (без выхода к юзеру)
                if session.current_node == "plan_needs_refine":
                    # автоматически переходим к рефайну в этой же итерации while
                    continue
            elif session.current_node == "plan_needs_refine":
                # Сюда попадаем автоматически после REJECTED (без user_feedback)
                session = self._step_plan_refine(session)
            elif session.current_node == "plan_needs_user_arbitration":
                # Возврат из main.py с user_feedback (или без — тогда ревьюер сам решит)
                session = self._step_plan_refine(session)

            if session.current_node == "failed":
                return session

        if session.current_node == "plan_approved":
            print("\n--- ФИНАЛЬНЫЙ ПЛАН СЕРИИ ---")
            for i in range(len(session.series_plan)):
                item = session.approved_plan_items.get(str(i))
                if not item and i < len(session.full_plan_items):
                    item = session.full_plan_items[i]

                if item:
                    print(f"  {i + 1}. {item.get('theme')} | {item.get('content')}")
            print("----------------------------\n")

            return self._pipeline_content_generation(session)

        return session

    def _pipeline_content_generation(self, session: SessionState) -> SessionState:
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
                    print(f"  [DEBUG] История {i + 1}: Используется одобренный сюжет")
                    print(f"          Входящий сюжет: {current_content}")
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
                image_path = os.path.join("output", session.session_id, f"story_{i}.png")
                prompt = self.prompt_builder.build_image_prompt(story.text, request.image_style.value)
                story.image_path = self.image.generate_image(prompt, story.text, image_path)
                self.storage.save_session(session)

        session.is_completed = True
        self.storage.save_session(session)
        return session

    def _step_safety_gate(self, session: SessionState) -> SessionState:
        print(f"[STEP] safety-gate | Проверка темы: {session.request.topic}")
        prompt = self.prompt_builder.build_safety_prompt(session.request.topic)
        response_raw = self.llm.generate_text(prompt)
        try:
            clean_json = response_raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_json)
            if result.get("is_safe"):
                print(f"[STEP] safety-gate | Статус: OK")
                session.current_node = "safety_passed"
            else:
                print(f"[STEP] safety-gate | Статус: FAILED | {result.get('reason')}")
                session.current_node = "failed"
        except Exception:
            session.current_node = "safety_passed" if "true" in response_raw.lower() else "failed"
        self.storage.save_session(session)
        return session

    def _step_config_match(self, session: SessionState) -> SessionState:
        mode_val = session.request.truth_mode.value
        print(f"[STEP] config-match | Проверка совместимости темы и режима '{mode_val}'")
        prompt = self.prompt_builder.build_config_match_prompt(session.request.topic, mode_val)
        response_raw = self.llm.generate_text(prompt)
        try:
            clean_json = response_raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_json)
            if result.get("is_compatible"):
                print(f"[STEP] config-match | Статус: OK")
                session.current_node = "config_passed"
            else:
                suggested = result.get("suggested_mode", "")
                print(f"\n[!] ВНИМАНИЕ: {result.get('reason')}")
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

    def _step_idea_scoring(self, session: SessionState) -> SessionState:
        if not session.ideas_pool:
            return session

        print(f"  [STEP] idea-scoring | Оценка {len(session.ideas_pool)} идей")
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
            session.ideas_pool = [it for it in session.ideas_pool if it.child_index >= 0.3]
            if len(session.ideas_pool) < original_count:
                print(f"  [!] Отсеяно {original_count - len(session.ideas_pool)} небезопасных идей.")

            if not session.ideas_pool:
                print("  [!] Пул идей пуст после фильтрации. Восстанавливаем fallback.")
                from src.models.schemas import Idea
                session.ideas_pool = [
                    Idea(title="Прогулка в лесу", summary="Маленький лис гуляет по лесу и изучает природу.")]
                session.ideas_pool[0].child_index = 0.7

        except Exception as e:
            print(f"  [ERROR] idea-scoring: {e}")
            for it in session.ideas_pool:
                it.child_index = 0.5

        return session

    def _step_score_normalize(self, session: SessionState) -> SessionState:
        if not session.ideas_pool:
            return session

        print(f"  [STEP] score-normalize | Линейная нормализация весов")

        epsilon = 0.2

        try:
            total_score = sum(it.child_index + epsilon for it in session.ideas_pool)

            for it in session.ideas_pool:
                it.normalized_weight = (it.child_index + epsilon) / total_score

        except Exception as e:
            print(f"  [ERROR] score-normalize: {e}")
            for it in session.ideas_pool:
                it.normalized_weight = 1.0 / len(session.ideas_pool)

        return session

    def _step_idea_sampler(self, session: SessionState, count: int = 1) -> List[dict]:
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

        print(f"  [STEP] idea-sampler | Выбрано {len(selected_items)} уникальных идей из пула")
        return selected_items

    def _step_series_planner(self, session: SessionState) -> SessionState:
        print(f"[STEP] series-planner | Составление пула идей для темы: {session.request.topic}")

        prompt = self.prompt_builder.build_series_plan_prompt(session.request.topic)
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
            print(f"[STEP] series-planner | ERROR: {e}")
            session.current_node = "failed"
            return session

        if not session.ideas_pool:
            print(f"[STEP] series-planner | ERROR: Не удалось получить пул идей")
            session.current_node = "failed"
            return session

        session = self._step_idea_scoring(session)
        session = self._step_score_normalize(session)

        final_plan = self._step_idea_sampler(session, count=session.request.count)

        if not final_plan:
            print(f"[STEP] series-planner | ERROR: Не удалось выбрать идеи")
            session.current_node = "failed"
            return session

        session.series_plan = [item["theme"] for item in final_plan]
        session.full_plan_items = final_plan

        # Инициализируем историю правок начальными версиями
        for i, item in enumerate(final_plan):
            session.revision_history[str(i)] = [{
                "source": "planner",
                "theme": item.get("theme", ""),
                "content": item.get("content", ""),
                "note": "Исходная версия от планировщика"
            }]

        print(f"[STEP] series-planner | Статус: OK | План из {len(final_plan)} историй сформирован")
        for i, item in enumerate(final_plan):
            print(f"  {i + 1}. {item.get('theme')} | {item.get('content')}")

        session.current_node = "series_planned"
        self.storage.save_session(session)
        return session

    def _step_plan_validator(self, session: SessionState) -> SessionState:
        print(f"[STEP] plan-validator | Проверка плана на соответствие режиму...")
        print(f"[CYCLE] validation_cycles (до запуска) = {session.validation_cycles}/{USER_ARBITRATION_THRESHOLD}")

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
                content_preview = item.get('content', '')[:100] + "..." if len(
                    item.get('content', '')) > 100 else item.get('content', '')
                print(f"  [OK] Тема {i + 1} ({item.get('theme', 'N/A')}): Уже одобрена. ({content_preview})")
                already_approved_indices.append(i)
            else:
                plan_to_verify.append({
                    "index": i,
                    "theme": item.get("theme", ""),
                    "content": item.get("content", "")
                })

        if not plan_to_verify:
            print(f"[STEP] plan-validator | Статус: APPROVED (все темы уже одобрены)")
            # Сброс счетчика — все темы одобрены
            if session.validation_cycles != 0:
                print(f"[CYCLE] validation_cycles reset → 0 (все темы одобрены)")
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
                print(f"[STEP] plan-validator | Статус: APPROVED")
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

                # Сброс счетчика — все одобрено
                if session.validation_cycles != 0:
                    print(f"[CYCLE] validation_cycles reset → 0 (план одобрен полностью)")
                session.validation_cycles = 0
            else:
                print(f"[STEP] plan-validator | Статус: REJECTED")
                final_reasons, final_suggestions, final_indices = [], [], []

                for i, rel_idx in enumerate(raw_invalid):
                    abs_idx = mapping.get(rel_idx)
                    if abs_idx is None: continue

                    reason = result.get("reasons", [])[i] if i < len(result.get("reasons", [])) else "Ошибка"
                    suggestion = result.get("suggestions", [])[i] if i < len(result.get("suggestions", [])) else ""

                    theme_title = current_plan_full[abs_idx].get("theme", "")
                    print(f"  - Тема {abs_idx + 1} ({theme_title}): {reason}")
                    if suggestion:
                        print(f"    Рекомендация: {suggestion}")

                    final_indices.append(abs_idx)
                    final_reasons.append(reason)
                    final_suggestions.append(suggestion)

                    # Записываем замечания валидатора в историю правок
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
                        print(f"  [OK] Тема {idx + 1} ({topic_data['theme']}): Проверка пройдена.")
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

                # Инкремент счетчика — REJECTED
                session.validation_cycles += 1
                print(f"[CYCLE] validation_cycles += 1 → {session.validation_cycles}/{USER_ARBITRATION_THRESHOLD}")

                # Защита от абсолютного потолка
                if session.validation_cycles > MAX_VALIDATION_RETRIES:
                    print(f"\n[!!!] ОШИБКА: Превышен абсолютный лимит попыток ({MAX_VALIDATION_RETRIES}).")
                    session.current_node = "failed"
                    self.storage.save_session(session)
                    return session

                # Решаем: вмешательство пользователя или автоматический рефайн
                if session.validation_cycles >= USER_ARBITRATION_THRESHOLD:
                    print(
                        f"[CYCLE] Достигнут порог {USER_ARBITRATION_THRESHOLD} REJECTED — требуется вмешательство пользователя")
                    session.current_node = "plan_needs_user_arbitration"
                else:
                    print(f"[CYCLE] Авто-режим: ревьюер и редактор работают самостоятельно (без участия пользователя)")
                    session.current_node = "plan_needs_refine"
        except Exception as e:
            print(f"[STEP] plan-validator | ERROR: {e}")
            session.current_node = "plan_approved"
        self.storage.save_session(session)
        return session

    def _step_plan_refine(self, session: SessionState) -> SessionState:
        """[🤖 ИИ] Шаг точечной редактуры плана"""
        print(
            f"[STEP] plan-refine | Анализ решений и исправление плана (цикл {session.validation_cycles}/{USER_ARBITRATION_THRESHOLD}, абс. лимит {MAX_VALIDATION_RETRIES})")

        current_plan_full = session.full_plan_items
        if not current_plan_full:
            current_plan_full = [{"theme": t, "content": ""} for t in session.series_plan]

        current_plan_json = json.dumps(current_plan_full, ensure_ascii=False)
        validator_feedback = getattr(session, "validator_feedback", "{}")
        user_comment = session.user_feedback if session.user_feedback is not None else ""

        if user_comment:
            print(f"  [USER] Получен комментарий пользователя: {user_comment}")

        # Парсим фидбек валидатора заранее — нам нужны invalid_indices
        v_feedback = {}
        try:
            v_feedback = json.loads(validator_feedback)
        except:
            pass
        v_suggestions = v_feedback.get("suggestions", [])
        v_indices = v_feedback.get("invalid_indices", [])
        v_map = {idx: v_suggestions[i] for i, idx in enumerate(v_indices) if i < len(v_suggestions)}
        currently_rejected = set(v_indices)

        # 1. REVIEWER
        reviewer_prompt = self.prompt_builder.build_plan_reviewer_prompt(
            current_plan_json,
            validator_feedback,
            user_comment
        )
        reviewer_response = self.llm.generate_text(reviewer_prompt)

        try:
            reviewer_json = reviewer_response.replace("```json", "").replace("```", "").strip()
            reviewer_result = json.loads(reviewer_json)
            decisions = reviewer_result.get("decisions", [])
        except Exception as e:
            print(f"[STEP] plan-refine | Reviewer ERROR: {e}")
            decisions = []

        print("  --- РЕШЕНИЯ РЕВЬЮЕРА ---")
        items_to_revise = []
        new_approved_indices = []

        for d in decisions:
            idx = d.get("index")
            decision = d.get("decision")

            # === СТРАХОВКА: KEEP_ORIGINAL недопустим для отклонённых тем без user_feedback ===
            if decision == "KEEP_ORIGINAL" and idx in currently_rejected and not user_comment:
                print(
                    f"  [GUARD] Тема {idx + 1}: ревьюер выбрал KEEP_ORIGINAL, но валидатор её отклонил, а пользователь не вмешался → принудительно отправляем РЕДАКТОРУ")
                decision = "REVISE_BY_USER"
                d["decision"] = decision
            # =================================================================================

            if decision == "ACCEPT_SUGGESTION":
                suggestion = d.get("validator_suggestion")
                if not (suggestion and isinstance(suggestion, dict)):
                    suggestion = v_map.get(idx)

                if suggestion and isinstance(suggestion, dict):
                    session.approved_plan_items[str(idx)] = {
                        "theme": suggestion.get("theme", ""),
                        "content": suggestion.get("content", "")
                    }
                    new_approved_indices.append(idx)
                    print(f"  [OK] Тема {idx + 1}: Принято решение ВАЛИДАТОРА (Название: {suggestion.get('theme')})")

                    hist_key = str(idx)
                    if hist_key not in session.revision_history:
                        session.revision_history[hist_key] = []
                    session.revision_history[hist_key].append({
                        "source": "reviewer:accept_suggestion",
                        "theme": suggestion.get("theme", ""),
                        "content": suggestion.get("content", ""),
                        "note": "Ревьюер принял рекомендацию валидатора"
                    })
                else:
                    print(f"  [!] Ошибка: Не удалось найти текст рекомендации для темы {idx + 1}")

            elif decision == "KEEP_ORIGINAL":
                orig_data = d.get("original_data")
                if not (orig_data and isinstance(orig_data, dict)):
                    orig_data = current_plan_full[idx] if idx < len(current_plan_full) else {}

                if str(idx) in session.approved_plan_items:
                    del session.approved_plan_items[str(idx)]
                print(f"  [!] Тема {idx + 1}: Оставлен ОРИГИНАЛ по запросу автора (Название: {orig_data.get('theme')})")

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
                print(f"  [OK] Тема {idx + 1}: Уже ОДОБРЕНО ранее (Название: {orig_data.get('theme')})")

            elif decision == "REVISE_BY_USER":
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
                print(f"  [!] Тема {idx + 1}: Отправлено РЕДАКТОРУ на правку (Название: {orig.get('theme')})")
        print("  -------------------------")

        current_approved = set(session.approved_indices)
        session.approved_indices = list(current_approved | set(new_approved_indices))

        # 3. REFINER: исправляет только те, что REVISE_BY_USER
        if items_to_revise:
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

            try:
                clean_json = response_raw.replace("```json", "").replace("```", "").strip()
                result = json.loads(clean_json)
                revised_items = result.get("revised_items", [])

                for item in revised_items:
                    idx = item.get("index")
                    new_theme = item.get("theme")
                    new_content = item.get("content")

                    if idx < len(current_plan_full):
                        current_plan_full[idx] = {"theme": new_theme, "content": new_content}

                    print(f"  [OK] Тема {idx + 1} подготовлена (исправлена редактором):")
                    print(f"       Тема: {new_theme}")
                    print(f"       Сюжет: {new_content}")

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
                print(f"[STEP] plan-refine | Refiner ERROR: {e}")
                session.current_node = "failed"
                return session

        final_plan = []
        for i in range(len(session.series_plan)):
            item = session.approved_plan_items.get(str(i))
            if not item:
                item = current_plan_full[i]
            final_plan.append(item)

        session.full_plan_items = final_plan
        session.series_plan = [it["theme"] for it in final_plan]

        session.user_feedback = None
        session.current_node = "series_planned"

        self.storage.save_session(session)
        return session

    def _parse_llm_response(self, text: str):
        story_part, questions = "", []
        q_start = text.find("Вопросы:")
        if q_start != -1:
            story_part = text[:q_start].replace("История:", "").replace("Текст истории:", "").strip()
            q_list = text[q_start:].replace("Вопросы:", "").strip().split("\n")
            questions = [q.strip(" 1234567890. -") for q in q_list if q.strip()]
        else:
            story_part = text.replace("История:", "").replace("Текст истории:", "").strip()
        return story_part, questions

    def confirm_story(self, session_id: str, index: int) -> SessionState:
        session = self.storage.get_session(session_id)
        if session and index < len(session.stories):
            session.stories[index].is_confirmed = True
            self.storage.save_session(session)
        return session