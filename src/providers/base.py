from abc import ABC, abstractmethod
from typing import List

class BaseLLMProvider(ABC):
    @abstractmethod
    def generate_text(self, prompt: str) -> str:
        pass

    @abstractmethod
    def generate_questions(self, text: str) -> List[str]:
        pass

class BaseImageProvider(ABC):
    @abstractmethod
    def generate_image(self, prompt: str, overlay_text: str, output_path: str) -> str:
        pass
