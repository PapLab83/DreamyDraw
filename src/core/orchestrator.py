import os
import json
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
        if session.current_node == "start":
            session = self._step_safety_gate(session)
            if session.current_node == "failed": return session
        
        if session.current_node == "safety_passed":
            session = self._step_config_match(session)
            if session.current_node == "failed": return session

        if session.current_node == "config_passed":
            session = self._step_series_planner(session)
            if session.current_node == "failed": return session

        # Временная логика старого пайплайна для совместимости
        if session.current_node == "series_planned":
            return self._legacy_run(session)

        return session

    def _step_safety_gate(self, session: SessionState) -> SessionState:
        """[🤖 ИИ] Шаг проверки безопасности и цензуры"""
        print(f"[STEP] safety-gate | Начало проверки темы: {session.request.topic}")
        
        prompt = self.prompt_builder.build_safety_prompt(session.request.topic)
        response_raw = self.llm.generate_text(prompt)
        
        try:
            clean_json = response_raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_json)
            
            if result.get("is_safe"):
                print(f"[STEP] safety-gate | Статус: OK | Тема безопасна")
                session.current_node = "safety_passed"
            else:
                reason = result.get("reason", "Неизвестная причина")
                print(f"[STEP] safety-gate | Статус: FAILED | Причина: {reason}")
                session.current_node = "failed"
        except Exception as e:
            print(f"[STEP] safety-gate | Статус: ERROR | Ошибка парсинга JSON: {e}")
            if "true" in response_raw.lower():
                session.current_node = "safety_passed"
            else:
                session.current_node = "failed"
        
        self.storage.save_session(session)
        return session

    def _step_config_match(self, session: SessionState) -> SessionState:
        """[🤖 ИИ] Шаг проверки логической совместимости темы и режима"""
        current_mode_val = session.request.truth_mode.value
        print(f"[STEP] config-match | Проверка совместимости темы '{session.request.topic}' и режима '{current_mode_val}'")
        
        prompt = self.prompt_builder.build_config_match_prompt(
            session.request.topic, 
            current_mode_val
        )
        response_raw = self.llm.generate_text(prompt)
        
        try:
            clean_json = response_raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_json)
            
            if result.get("is_compatible"):
                print(f"[STEP] config-match | Статус: OK | Конфигурация логична")
                session.current_node = "config_passed"
            else:
                reason = result.get("reason", "Несоответствие темы и режима")
                suggested = result.get("suggested_mode", "")
                
                print(f"\n[!] ВНИМАНИЕ: {reason}")
                if suggested:
                    print(f"Тема больше подходит для режима '{suggested}'.")
                    choice = input(f"Переключить режим на '{suggested}' и продолжить? (y/n): ").lower()
                    if choice == 'y':
                        # Пытаемся найти соответствие в Enum
                        from src.models.schemas import TruthMode
                        for mode in TruthMode:
                            if mode.value.lower() == suggested.lower() or suggested.lower() in mode.value.lower():
                                session.request.truth_mode = mode
                                break
                        print(f"--- Режим изменен на '{session.request.truth_mode.value}'. Продолжаем... ---")
                        session.current_node = "config_passed"
                    else:
                        print("Генерация отменена пользователем.")
                        session.current_node = "failed"
                else:
                    print("Автоматическое исправление невозможно.")
                    session.current_node = "failed"
        except Exception as e:
            print(f"[STEP] config-match | Статус: ERROR | Ошибка парсинга JSON: {e}")
            if "true" in response_raw.lower():
                session.current_node = "config_passed"
            else:
                session.current_node = "failed"
        
        self.storage.save_session(session)
        return session

    def _step_series_planner(self, session: SessionState) -> SessionState:
        """[🤖 ИИ] Шаг планирования серии историй"""
        print(f"[STEP] series-planner | Составление плана для {session.request.count} историй")
        
        # Если количество = 1, планирование упрощено
        if session.request.count == 1:
            session.series_plan = [session.request.topic]
            session.global_context = f"Герой темы {session.request.topic} в добром детском стиле."
            session.current_node = "series_planned"
            print(f"[STEP] series-planner | Статус: OK | Одиночная история")
            self.storage.save_session(session)
            return session

        prompt = self.prompt_builder.build_series_plan_prompt(
            session.request.topic, 
            session.request.count
        )
        response_raw = self.llm.generate_text(prompt)
        
        try:
            clean_json = response_raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_json)
            
            session.series_plan = result.get("plan", [])
            session.global_context = result.get("global_context", "")
            
            # Обновляем подтемы в существующих StoryItem
            for i, sub_topic in enumerate(session.series_plan):
                if i < len(session.stories):
                    session.stories[i].sub_topic = sub_topic
            
            print(f"[STEP] series-planner | Статус: OK | План составлен: {', '.join(session.series_plan)}")
            session.current_node = "series_planned"
        except Exception as e:
            print(f"[STEP] series-planner | Статус: ERROR | Ошибка парсинга JSON: {e}")
            session.current_node = "failed"
            
        self.storage.save_session(session)
        return session

    def _legacy_run(self, session: SessionState) -> SessionState:
        """Временный метод для работы старой логики генерации"""
        request = session.request
        for i in range(session.current_step, request.count):
            story = session.stories[i]
            if not story.text:
                prompt = self.prompt_builder.build_text_prompt(request)
                raw_response = self.llm.generate_text(prompt)
                story.text, story.questions = self._parse_llm_response(raw_response)
                self.storage.save_session(session)

            if request.work_mode == WorkMode.CHECK and not story.is_confirmed:
                return session

            if not story.image_path:
                image_filename = f"story_{i}.png"
                image_path = os.path.join("output", session.session_id, image_filename)
                prompt = self.prompt_builder.build_image_prompt(story.text, request.image_style)
                print(f"\n[DEBUG] Финальный промпт для картинки:\n{prompt}\n")
                story.image_path = self.image.generate_image(prompt, story.text, image_path)
                self.storage.save_session(session)

            session.current_step = i + 1
            if session.current_step >= request.count:
                session.is_completed = True
            self.storage.save_session(session)
        return session

    def _parse_llm_response(self, text: str):
        story_part = ""
        questions = []
        story_markers = ["Текст истории:", "История:"]
        question_markers = ["Вопросы:"]
        q_start = -1
        for q_m in question_markers:
            q_start = text.find(q_m)
            if q_start != -1: break
        
        if q_start != -1:
            full_story_part = text[:q_start].strip()
            for s_m in story_markers:
                if s_m in full_story_part:
                    full_story_part = full_story_part.replace(s_m, "").strip()
                    break
            story_part = full_story_part
            q_block = text[q_start:].strip()
            for q_m in question_markers:
                q_block = q_block.replace(q_m, "").strip()
            q_list = q_block.split("\n")
            questions = [q.strip(" 1234567890. -") for q in q_list if q.strip()]
        else:
            story_part = text
            for s_m in story_markers:
                if s_m in story_part:
                    story_part = story_part.replace(s_m, "").strip()
                    break
        return story_part, questions

    def confirm_story(self, session_id: str, index: int) -> SessionState:
        session = self.storage.get_session(session_id)
        if session and index < len(session.stories):
            session.stories[index].is_confirmed = True
            self.storage.save_session(session)
        return session
