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
            elif session.current_node == "plan_needs_refine":
                session = self._step_plan_refine(session)
            
            if session.current_node == "failed": 
                return session

        if session.current_node == "plan_approved":
            return self._legacy_run(session)

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
            # Временно сохраним расширенный план для дебага и рефайна
            session._raw_plan_full = raw_plan 
            
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
        
        # Список уже утвержденных индексов (чтобы не проверять их повторно)
        approved_indices = getattr(session, "_approved_indices", [])
        
        full_plan_json = json.dumps(getattr(session, "_raw_plan_full", session.series_plan), ensure_ascii=False)
        prompt = self.prompt_builder.build_plan_validator_prompt(full_plan_json, session.global_context, session.request.truth_mode.value)
        response_raw = self.llm.generate_text(prompt)
        
        try:
            clean_json = response_raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_json)
            
            # Фильтруем ошибки, исключая уже утвержденные индексы
            invalid_indices = [i for i in result.get("invalid_indices", []) if i not in approved_indices]
            
            if not invalid_indices:
                print(f"[STEP] plan-validator | Статус: APPROVED")
                session.current_node = "plan_approved"
            else:
                print(f"[STEP] plan-validator | Статус: REJECTED")
                for idx in invalid_indices:
                    # Находим причину для этого индекса
                    # (Логика сопоставления зависит от того, как LLM вернула списки)
                    reason = "Ошибка в этой теме"
                    try:
                        orig_idx = result.get("invalid_indices", []).index(idx)
                        reason = result.get("reasons", [])[orig_idx]
                    except: pass
                    print(f"  - Тема {idx+1}: {reason}")
                
                # Запоминаем те, что БЫЛИ хорошими в этот раз
                current_all_indices = set(range(len(session.series_plan)))
                newly_approved = list(current_all_indices - set(invalid_indices))
                session._approved_indices = list(set(approved_indices) | set(newly_approved))
                
                session._validator_feedback = json.dumps({
                    "invalid_indices": invalid_indices,
                    "reasons": [result.get("reasons", [])[result.get("invalid_indices", []).index(i)] for i in invalid_indices if i in result.get("invalid_indices", [])],
                    "suggestions": [result.get("suggestions", [])[result.get("invalid_indices", []).index(i)] for i in invalid_indices if i in result.get("invalid_indices", [])]
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

        print(f"[STEP] plan-refine | Исправление плана (Попытка {current_retry + 1}/{max_retries})")
        
        current_plan_json = json.dumps(getattr(session, "_raw_plan_full", session.series_plan), ensure_ascii=False)
        feedback_json = session._validator_feedback
        
        prompt = self.prompt_builder.build_plan_refine_prompt(current_plan_json, feedback_json, session.request.truth_mode.value)
        response_raw = self.llm.generate_text(prompt)
        
        try:
            clean_json = response_raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_json)
            raw_plan = result.get("plan", [])
            session._raw_plan_full = raw_plan
            session.series_plan = [item["theme"] if isinstance(item, dict) else str(item) for item in raw_plan]
            
            print(f"[STEP] plan-refine | Статус: OK | План обновлен")
            for i, item in enumerate(raw_plan):
                t = item.get("theme", "N/A") if isinstance(item, dict) else item
                c = item.get("content", "N/A") if isinstance(item, dict) else ""
                print(f"  {i+1}. {t} | {c}")
            
            session.stories[0].retry_count += 1
            session.current_node = "series_planned" # Возврат к валидатору
        except Exception as e:
            print(f"[STEP] plan-refine | ERROR: {e}")
            session.current_node = "failed"
            
        self.storage.save_session(session)
        return session

    def _legacy_run(self, session: SessionState) -> SessionState:
        request = session.request
        for i in range(session.current_step, request.count):
            story = session.stories[i]
            # Обновляем sub_topic из исправленного плана
            if i < len(session.series_plan):
                story.sub_topic = session.series_plan[i]
            
            current_topic = story.sub_topic if story.sub_topic else request.topic
            if not story.text:
                temp_request = request.model_copy(update={"topic": current_topic})
                prompt = self.prompt_builder.build_text_prompt(temp_request, session.global_context)
                raw_response = self.llm.generate_text(prompt)
                story.text, story.questions = self._parse_llm_response(raw_response)
                self.storage.save_session(session)

            if request.work_mode == WorkMode.CHECK and not story.is_confirmed:
                return session

            if not story.image_path:
                image_path = os.path.join("output", session.session_id, f"story_{i}.png")
                prompt = self.prompt_builder.build_image_prompt(story.text, request.image_style.value)
                story.image_path = self.image.generate_image(prompt, story.text, image_path)
                self.storage.save_session(session)

            session.current_step = i + 1
            if session.current_step >= request.count: session.is_completed = True
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
