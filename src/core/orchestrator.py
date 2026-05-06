import os
from typing import List, Optional
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
        # Инициализируем пустые элементы историй
        for i in range(request.count):
            session.stories.append(StoryItem(index=i))
        self.storage.save_session(session)
        return session

    def run_pipeline(self, session_id: str) -> SessionState:
        session = self.storage.get_session(session_id)
        if not session or session.is_completed:
            return session

        request = session.request
        
        for i in range(session.current_step, request.count):
            story = session.stories[i]
            
            # Шаг 1: Генерация текста
            if not story.text:
                prompt = self.prompt_builder.build_text_prompt(request)
                raw_response = self.llm.generate_text(prompt)
                
                # Парсинг ответа (Текст истории: ... Вопросы: ...)
                story.text, story.questions = self._parse_llm_response(raw_response)
                self.storage.save_session(session)

            # Шаг 2: Режим проверки
            if request.work_mode == WorkMode.CHECK and not story.is_confirmed:
                # Прерываемся, чтобы пользователь подтвердил текст
                return session

            # Шаг 3: Генерация картинки
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
        """Парсит ответ от LLM согласно заданному формату"""
        story_part = ""
        questions = []
        
        # Маркеры для поиска (в порядке приоритета)
        story_markers = ["Текст истории:", "История:"]
        question_markers = ["Вопросы:"]
        
        # Находим начало блока вопросов
        q_start = -1
        for q_m in question_markers:
            q_start = text.find(q_m)
            if q_start != -1:
                break
        
        if q_start != -1:
            # Извлекаем часть с историей
            full_story_part = text[:q_start].strip()
            # Убираем заголовок "История:" или "Текст истории:"
            for s_m in story_markers:
                if s_m in full_story_part:
                    full_story_part = full_story_part.replace(s_m, "").strip()
                    break
            story_part = full_story_part
            
            # Извлекаем вопросы
            q_block = text[q_start:].strip()
            for q_m in question_markers:
                q_block = q_block.replace(q_m, "").strip()
            
            q_list = q_block.split("\n")
            questions = [q.strip(" 1234567890. -") for q in q_list if q.strip()]
        else:
            # Если маркера вопросов нет, пробуем хотя бы вычистить заголовок истории
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
