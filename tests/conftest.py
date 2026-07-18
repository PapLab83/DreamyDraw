"""
Общие pytest fixtures для тестов DreamyDraw.
"""

import shutil
import tempfile
from typing import Iterator

import pytest

from src.providers.base import BaseLLMProvider
from src.storage.json_storage import JSONStorage


# --- Fake providers ----------------------------------------------------------

class ScriptedLLM(BaseLLMProvider):
    """
    LLM-провайдер с предзаданным скриптом ответов в определённом порядке.
    Если ответы кончились — бросает RuntimeError с информативным сообщением.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def generate_text(self, prompt: str, *, temperature: float | None = None) -> str:
        if self.calls >= len(self.responses):
            raise RuntimeError(
                f"ScriptedLLM: запрошен ответ #{self.calls + 1}, "
                f"но в скрипте только {len(self.responses)}. "
                f"Промпт (200 симв.): {prompt[:200]!r}"
            )
        resp = self.responses[self.calls]
        self.calls += 1
        return resp

    def generate_questions(self, text: str):
        return []


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def tmp_storage() -> Iterator[JSONStorage]:
    """Временный JSONStorage с автоудалением после теста."""
    tmp = tempfile.mkdtemp(prefix="dd_test_")
    try:
        yield JSONStorage(base_dir=tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
