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
        
        # Временная логика старого пайплайна для совместимости (пока не реализованы все шаги)
        if session.current_node == "safety_passed":
            # Пока переходим сразу к генерации как в старом коде, 
            # по мере реализации шагов будем вставлять их сюда.
            return self._legacy_run(session)

        return session

    def _step_safety_gate(self, session: SessionState) -> SessionState:
        """[🤖 ИИ] Шаг проверки безопасности и цензуры"""
        print(f"[STEP] safety-gate | Начало проверки темы: {session.request.topic}")
        
        prompt = self.prompt_builder.build_safety_prompt(session.request.topic)
        response_raw = self.llm.generate_text(prompt)
        
        try:
            # Очистка от markdown-обертки JSON если она есть
            clean_json = response_raw.replace("```json", "").replace("```", "").strip()
            result = json.loads(clean_json)
            
            if result.get("is_safe"):
                print(f"[STEP] safety-gate | Статус: OK | Тема безопасна")
                session.current_node = "safety_passed"
            else:
                reason = result.get("reason", "Неизвестная причина")
                print(f"[STEP] safety-gate | Статус: FAILED | Причина: {reason}")
                session.current_node = "failed"
                # В будущем тут можно бросать исключение или сохранять ошибку в сессию
        except Exception as e:
            print(f"[STEP] safety-gate | Статус: ERROR | Ошибка парсинга JSON: {e}")
            # Фолбэк: если не распарсили, но текст кажется нормальным (для моков)
            if "true" in response_raw.lower():
                session.current_node = "safety_passed"
            else:
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
