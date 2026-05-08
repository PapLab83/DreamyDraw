import os
from typing import List
from src.config import constants
from src.providers.base import BaseLLMProvider

class LLMMockProvider(BaseLLMProvider):
    def __init__(self, mock_file: str = "assets/mocks/fox_story.txt"):
        self.mock_file = mock_file
        self.mock_content = self._load_mock()

    def _load_mock(self):
        if os.path.exists(self.mock_file):
            with open(self.mock_file, "r") as f:
                return f.read()
        return "Мок-текст не найден."

    def generate_text(self, prompt: str) -> str:
        # В реальности здесь будет парсинг или выбор части мока
        # Для прототипа возвращаем основную часть текста про лису
        lines = self.mock_content.split("\n\n")
        return lines[0] if lines else self.mock_content

    def generate_questions(self, text: str) -> List[str]:
        # Извлекаем вопросы из мока
        if "Вопросы:" in self.mock_content:
            q_part = self.mock_content.split("Вопросы:")[1]
            questions = [q.strip() for q in q_part.strip().split("\n") if q.strip()]
            return questions[:constants.MAX_QUESTIONS]
        return ["Как зовут лису?", "Где она живет?"]
