import os
import json
import time
from src.models.schemas import GenerationRequest, SessionState, StoryItem, WorkMode
from src.providers.base import BaseLLMProvider, BaseImageProvider
from src.storage.json_storage import JSONStorage
from src.core.prompt_builder import PromptBuilder

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
            
        # Создаем директорию для сессии
        os.makedirs(os.path.join(self.storage.base_dir, session.session_id), exist_ok=True)
        
        self.storage.save_session(session)
        return session

    def run_pipeline(self, session_id: str) -> SessionState:
        session = self.storage.get_session(session_id)
        if not session or session.is_completed:
            return session

        # Машина состояний (Узлы пайплайна)
        while session.current_node in ["start", "safety_passed", "config_passed", "series_planned", "plan_needs_refine"]:
            if session.current_node == "start":
                session = self._step_safety_gate(session)
            elif session.current_node == "safety_passed":
                session = self._step_config_match(session)
            elif session.current_node == "config_passed":
                session = self._step_series_planner(session)
            elif session.current_node == "series_planned":
                session = self._step_plan_validator(session)
                # Если план отклонен ИЛИ пользователь хочет дать фидбек
                if session.current_node == "plan_needs_refine":
                    return session
            elif session.current_node == "plan_needs_refine":
                # Если пользователь явно хочет закончить или просто нажал Enter (если мы решим что Enter = ок)
                # Но текущая проверка слишком жадная. Проверяем более строго.
                if session.user_feedback and session.user_feedback.lower() in ["хватит", "достаточно", "больше не", "ок", "хорошо"]:
                    print("[STEP] plan-refine | Пользователь принудительно одобрил текущий вариант. Завершаем валидацию.")
                    session.current_node = "plan_approved"
                    session.user_feedback = None
                    break
                
                session = self._step_plan_refine(session)
            
            if session.current_node == "failed": 
                return session

        # Только если план утвержден, переходим к пакетной генерации контента
        if session.current_node == "plan_approved":
            # Выводим финальный одобренный план перед генерацией текстов
            print("\n--- ФИНАЛЬНЫЙ ПЛАН СЕРИИ ---")
            for i in range(len(session.series_plan)):
                item = session.approved_plan_items.get(str(i))
                if not item and i < len(session.full_plan_items):
                     item = session.full_plan_items[i]
                
                if item:
                    print(f"  {i+1}. {item.get('theme')} | {item.get('content')}")
            print("----------------------------\n")
            
            return self._pipeline_content_generation(session)

        return session

    def _pipeline_content_generation(self, session: SessionState) -> SessionState:
        """Пакетная генерация текстов и последующая генерация картинок"""
        request = session.request
        
        # ШАГ 1: Генерация ВСЕХ текстов
        for i in range(request.count):
            story = session.stories[i]
            
            if not story.text:
                # ШАГ 0: Синхронизируем из чистовика или текущего плана
                current_plan_full = session.full_plan_items
                current_topic = ""
                current_content = ""
                
                if str(i) in session.approved_plan_items:
                    current_topic = session.approved_plan_items[str(i)].get("theme", "")
                    current_content = session.approved_plan_items[str(i)].get("content", "")
                elif i < len(current_plan_full):
                    current_topic = current_plan_full[i].get("theme", "")
                    current_content = current_plan_full[i].get("content", "")
                
                # Принудительно обновляем sub_topic для истории, чтобы он соответствовал одобренному плану
                if current_topic:
                    story.sub_topic = current_topic
                else:
                    current_topic = story.sub_topic if story.sub_topic else request.topic
                
                temp_request = request.model_copy(update={"topic": current_topic})
                prompt = self.prompt_builder.build_text_prompt(temp_request, session.global_context)
                
                # Если у нас есть одобренное описание, добавляем его в промпт как строгое указание
                if current_content:
                    print(f"  [DEBUG] История {i+1}: Используется одобренный сюжет")
                    print(f"          Входящий сюжет: {current_content}")
                    prompt += f"\n\nИСПОЛЬЗУЙ СЛЕДУЮЩИЙ СЮЖЕТ (ОДОБРЕНО): {current_content}"
                
                raw_response = self.llm.generate_text(prompt)
                story.text, story.questions = self._parse_llm_response(raw_response)
                self.storage.save_session(session)
        
        # ШАГ 2: Согласование (в режиме CHECK)
        if request.work_mode == WorkMode.CHECK:
            # Проверяем, все ли подтверждены
            all_confirmed = all(s.is_confirmed for s in session.stories)
            if not all_confirmed:
                # Возвращаем сессию в main.py для подтверждения первого попавшегося
                return session

        # ШАГ 3: Генерация ВСЕХ картинок (только после подтверждения всех текстов)
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
        """[🤖 ИИ] Шаг проверки безопасности и цензуры"""
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
        """[🤖 ИИ] Шаг проверки логической совместимости"""
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

    def _step_series_planner(self, session: SessionState) -> SessionState:
        """[🤖 ИИ] Шаг первичного планирования"""
        print(f"[STEP] series-planner | Составление плана для {session.request.count} историй")
        if session.request.count == 1:
            session.series_plan = [session.request.topic]
            session.global_context = f"Герой темы {session.request.topic} в добром детском стиле."
            session.current_node = "series_planned"
            return session

        prompt = self.prompt_builder.build_series_plan_prompt(session.request.topic, session.request.count)
        response_raw = self.llm.generate_text(prompt)
        try:
            clean_json = response_raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_json)
            session.global_context = result.get("global_context", "")
            raw_plan = result.get("plan", [])
            session.series_plan = [item["theme"] if isinstance(item, dict) else str(item) for item in raw_plan]
            session.full_plan_items = raw_plan 
            
            print(f"[STEP] series-planner | Статус: OK | План создан")
            for i, item in enumerate(raw_plan):
                t = item.get("theme", "N/A") if isinstance(item, dict) else item
                c = item.get("content", "N/A") if isinstance(item, dict) else ""
                print(f"  {i+1}. {t} | {c}")
            
            session.current_node = "series_planned"
        except Exception as e:
            print(f"[STEP] series-planner | ERROR: {e}")
            session.current_node = "failed"
        self.storage.save_session(session)
        return session

    def _step_plan_validator(self, session: SessionState) -> SessionState:
        """[🤖 ИИ] Шаг валидации плана"""
        print(f"[STEP] plan-validator | Проверка плана на соответствие режиму...")
        
        approved_indices = session.approved_indices
        current_plan_full = session.full_plan_items
        
        # Синхронизируем с approved_plan_items (на случай если мы пришли сюда после рефайна)
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
                # Если тема только что была исправлена, выведем её содержание
                content_preview = item.get('content', '')[:100] + "..." if len(item.get('content', '')) > 100 else item.get('content', '')
                print(f"  [OK] Тема {i+1} ({item.get('theme', 'N/A')}): Уже одобрена. ({content_preview})")
                already_approved_indices.append(i)
            else:
                plan_to_verify.append({
                    "index": i,
                    "theme": item.get("theme", ""),
                    "content": item.get("content", "")
                })

        if not plan_to_verify:
            print(f"[STEP] plan-validator | Статус: APPROVED (все темы уже одобрены)")
            session.current_node = "plan_approved"
            self.storage.save_session(session)
            return session

        full_plan_json = json.dumps(plan_to_verify, ensure_ascii=False)
        prompt = self.prompt_builder.build_plan_validator_prompt(full_plan_json, session.global_context, session.request.truth_mode.value)
        response_raw = self.llm.generate_text(prompt)
        
        try:
            clean_json = response_raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_json)
            raw_invalid = result.get("invalid_indices", [])
            # Сопоставляем индексы обратно, если валидатор вернул их относительно обрезанного списка
            # Но лучше если он будет возвращать "index" из объектов.
            # В Промпте валидатора написано "realism_scores оценивает по порядку".
            # Если мы передали 1 тему, он вернет индекс 0. Нам нужно смапить на оригинальный.
            
            # Создаем карту индексов
            mapping = {i: item["index"] for i, item in enumerate(plan_to_verify)}
            invalid_indices = [mapping[i] for i in raw_invalid if i in mapping]
            
            if not invalid_indices:
                print(f"[STEP] plan-validator | Статус: APPROVED")
                session.current_node = "plan_approved"
                # Все темы, которые проходили валидацию и прошли, помечаем как одобренные
                verified_indices = [item["index"] for item in plan_to_verify]
                for idx in verified_indices:
                    topic_data = next((it for it in plan_to_verify if it["index"] == idx), None)
                    if topic_data:
                        session.approved_plan_items[str(idx)] = {
                            "theme": topic_data["theme"],
                            "content": topic_data["content"]
                        }
                session.approved_indices = list(set(approved_indices) | set(verified_indices))
            else:
                print(f"[STEP] plan-validator | Статус: REJECTED")
                final_reasons, final_suggestions, final_indices = [], [], []

                for i, rel_idx in enumerate(raw_invalid):
                    abs_idx = mapping.get(rel_idx)
                    if abs_idx is None: continue
                
                    reason = result.get("reasons", [])[i] if i < len(result.get("reasons", [])) else "Ошибка"
                    suggestion = result.get("suggestions", [])[i] if i < len(result.get("suggestions", [])) else ""
                
                    theme_title = current_plan_full[abs_idx].get("theme", "")
                    print(f"  - Тема {abs_idx+1} ({theme_title}): {reason}")
                    if suggestion:
                        print(f"    Рекомендация: {suggestion}")
                    
                    final_indices.append(abs_idx)
                    final_reasons.append(reason)
                    final_suggestions.append(suggestion)
            
                # Темы, которые были в проверке, но не попали в invalid, считаются одобренными
                verified_indices = [item["index"] for item in plan_to_verify]
                passed_indices = [i for i in verified_indices if i not in final_indices]
            
                for idx in passed_indices:
                    topic_data = next((it for it in plan_to_verify if it["index"] == idx), None)
                    if topic_data:
                         print(f"  [OK] Тема {idx+1} ({topic_data['theme']}): Проверка пройдена.")
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
                session.current_node = "plan_needs_refine"
        except Exception as e:
            print(f"[STEP] plan-validator | ERROR: {e}")
            session.current_node = "plan_approved"
        self.storage.save_session(session)
        return session

    def _step_plan_refine(self, session: SessionState) -> SessionState:
        """[🤖 ИИ] Шаг точечной редактуры плана"""
        max_retries = 5
        current_retry = session.stories[0].retry_count
        if current_retry >= max_retries:
            print(f"\n[!!!] ОШИБКА: Не удалось исправить план за {max_retries} попыток.")
            session.current_node = "failed"
            return session

        print(f"[STEP] plan-refine | Анализ решений и исправление плана (Попытка {current_retry + 1}/{max_retries})")
        
        current_plan_full = session.full_plan_items
        if not current_plan_full:
            current_plan_full = [{"theme": t, "content": ""} for t in session.series_plan]
        
        current_plan_json = json.dumps(current_plan_full, ensure_ascii=False)
        validator_feedback = getattr(session, "validator_feedback", "{}")
        user_comment = session.user_feedback if session.user_feedback is not None else ""
        
        # 1. REVIEWER: принимает решения по каждой теме
        reviewer_prompt = self.prompt_builder.build_plan_reviewer_prompt(
            current_plan_json, 
            validator_feedback, 
            user_comment
        )
        reviewer_response = self.llm.generate_text(reviewer_prompt)
        # print(f"  [DEBUG] Ответ REVIEWER:\n{reviewer_response}\n")
        
        try:
            reviewer_json = reviewer_response.replace("```json", "").replace("```", "").strip()
            reviewer_result = json.loads(reviewer_json)
            decisions = reviewer_result.get("decisions", [])
        except Exception as e:
            print(f"[STEP] plan-refine | Reviewer ERROR: {e}")
            decisions = []

        # 2. Обработка решений
        print("  --- РЕШЕНИЯ РЕВЬЮЕРА ---")
        items_to_revise = []
        new_approved_indices = []
        
        # Загружаем фидбек валидатора для поиска соответствий, если ревьюер что-то упустил
        v_feedback = {}
        try:
            v_feedback = json.loads(validator_feedback)
        except:
            pass
        v_suggestions = v_feedback.get("suggestions", [])
        v_indices = v_feedback.get("invalid_indices", [])
        v_map = {idx: v_suggestions[i] for i, idx in enumerate(v_indices) if i < len(v_suggestions)}

        for d in decisions:
            idx = d.get("index")
            decision = d.get("decision")
            
            if decision == "ACCEPT_SUGGESTION":
                # Пытаемся взять из ответа ревьюера или из исходного фидбека
                suggestion = d.get("validator_suggestion")
                if not (suggestion and isinstance(suggestion, dict)):
                    suggestion = v_map.get(idx)
                
                if suggestion and isinstance(suggestion, dict):
                    session.approved_plan_items[str(idx)] = {
                        "theme": suggestion.get("theme", ""),
                        "content": suggestion.get("content", "")
                    }
                    new_approved_indices.append(idx)
                    print(f"  [OK] Тема {idx+1}: Принято решение ВАЛИДАТОРА (Название: {suggestion.get('theme')})")
                else:
                    print(f"  [!] Ошибка: Не удалось найти текст рекомендации для темы {idx+1}")
            
            elif decision == "KEEP_ORIGINAL":
                # В чистовик НЕ кладем, чтобы прошла повторную валидацию (если пользователь просто отказался)
                orig_data = d.get("original_data")
                if not (orig_data and isinstance(orig_data, dict)):
                    orig_data = current_plan_full[idx] if idx < len(current_plan_full) else {}
                
                if str(idx) in session.approved_plan_items:
                    del session.approved_plan_items[str(idx)]
                print(f"  [!] Тема {idx+1}: Оставлен ОРИГИНАЛ по запросу автора (Название: {orig_data.get('theme')})")
                
            elif decision == "ALREADY_OK":
                # В чистовик как есть (если её там еще нет)
                orig_data = d.get("original_data")
                if not (orig_data and isinstance(orig_data, dict)):
                    orig_data = current_plan_full[idx] if idx < len(current_plan_full) else {}
                
                session.approved_plan_items[str(idx)] = orig_data
                new_approved_indices.append(idx)
                print(f"  [OK] Тема {idx+1}: Уже ОДОБРЕНО ранее (Название: {orig_data.get('theme')})")
            
            elif decision == "REVISE_BY_USER":
                # В список на доработку. УДАЛЯЕМ из одобренных, так как автор хочет правок
                if str(idx) in session.approved_plan_items:
                    del session.approved_plan_items[str(idx)]
                
                orig = d.get("original_data", {})
                if not (orig and isinstance(orig, dict)) or not orig.get("content"):
                    if idx < len(current_plan_full):
                        orig = current_plan_full[idx]
                        d["original_data"] = orig
                
                # Добавляем suggestion для контекста редактору
                if not d.get("validator_suggestion"):
                    d["validator_suggestion"] = v_map.get(idx)

                items_to_revise.append(d)
                print(f"  [!] Тема {idx+1}: Отправлено РЕДАКТОРУ на правку (Название: {orig.get('theme')})")
        print("  -------------------------")

        # Синхронизируем индексы для следующего шага валидатора
        current_approved = set(session.approved_indices)
        session.approved_indices = list(current_approved | set(new_approved_indices))

        # 3. REFINER: исправляет только те, что REVISE_BY_USER
        if items_to_revise:
            refine_payload = json.dumps({"items_to_revise": items_to_revise}, ensure_ascii=False)
            
            # Нам нужно передать ТЕКУЩИЙ ВЕСЬ ПЛАН, но с наполненным контентом там где он есть
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
            # print(f"  [DEBUG] Ответ PLAN_REFINER:\n{response_raw}\n")
            
            try:
                clean_json = response_raw.replace("```json", "").replace("```", "").strip()
                result = json.loads(clean_json)
                revised_items = result.get("revised_items", [])
                
                for item in revised_items:
                    idx = item.get("index")
                    new_theme = item.get("theme")
                    new_content = item.get("content")
                    
                    # После REFINER мы НЕ добавляем в approved_plan_items сразу,
                    # чтобы тема прошла повторную валидацию, ЕСЛИ это была правка.
                    # Но нам нужно обновить full_plan_items для валидатора.
                    if idx < len(current_plan_full):
                         current_plan_full[idx] = {"theme": new_theme, "content": new_content}
                    
                    print(f"  [OK] Тема {idx+1} подготовлена (исправлена редактором):")
                    print(f"       Тема: {new_theme}")
                    print(f"       Сюжет: {new_content}")
            except Exception as e:
                print(f"[STEP] plan-refine | Refiner ERROR: {e}")
                session.current_node = "failed"
                return session

        # 4. Сборка финального плана (для валидатора или следующего шага)
        # Мы берем данные из approved_plan_items. Если там чего-то нет (что странно), берем старое.
        final_plan = []
        for i in range(len(session.series_plan)):
            item = session.approved_plan_items.get(str(i))
            if not item:
                item = current_plan_full[i]
            final_plan.append(item)
        
        session.full_plan_items = final_plan
        session.series_plan = [it["theme"] for it in final_plan]
        
        # Обновляем approved_indices для валидатора
        # Важно: мы добавляем только те, что были ACCEPT_SUGGESTION или ALREADY_OK.
        # REVISED_BY_USER и KEEP_ORIGINAL темы НЕ помечаются как одобренные, 
        # чтобы они прошли валидатор в следующем цикле.
        
        session.stories[0].retry_count += 1
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
