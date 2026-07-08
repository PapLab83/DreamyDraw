"""
Общие pytest fixtures для тестов DreamyDraw.
"""

import json
import os
import shutil
import tempfile
from typing import Iterator

import pytest

from src.core.prompt_builder import PromptBuilder
from src.models.schemas import (
    GenerationRequest,
    ImageStyle,
    SessionState,
    StoryItem,
    TextStyle,
    TruthMode,
    WorkMode,
)
from src.providers.base import BaseImageProvider, BaseLLMProvider
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


class FakeImage(BaseImageProvider):
    """Mock-провайдер картинок: создаёт пустой файл и возвращает путь."""

    def __init__(self):
        self.calls = 0

    def generate_image(self, prompt: str, overlay_text: str, output_path: str) -> str:
        self.calls += 1
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(b"")
        return output_path


# --- Fixtures ---------------------------------------------------------------

@pytest.fixture
def tmp_storage() -> Iterator[JSONStorage]:
    """Временный JSONStorage с автоудалением после теста."""
    tmp = tempfile.mkdtemp(prefix="dd_test_")
    try:
        yield JSONStorage(base_dir=tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture
def prompt_builder() -> PromptBuilder:
    return PromptBuilder()


@pytest.fixture
def fake_image() -> FakeImage:
    return FakeImage()


# --- Helpers ----------------------------------------------------------------

def make_request(
    topic: str = "лиса",
    count: int = 2,
    work_mode: WorkMode = WorkMode.FAST,
    truth_mode: TruthMode = TruthMode.TRUTH,
) -> GenerationRequest:
    return GenerationRequest(
        topic=topic,
        truth_mode=truth_mode,
        text_style=TextStyle.GENTLE,
        image_style=ImageStyle.CARTOON,
        work_mode=work_mode,
        count=count,
    )


def make_session(
    count: int = 2,
    work_mode: WorkMode = WorkMode.FAST,
    truth_mode: TruthMode = TruthMode.TRUTH,
    with_stories: bool = True,
) -> SessionState:
    """Готовая сессия для тестов нод."""
    s = SessionState(request=make_request(count=count, work_mode=work_mode, truth_mode=truth_mode))
    if with_stories:
        s.stories = [StoryItem(index=i) for i in range(count)]
    return s


def make_session_with_plan(count: int = 2, work_mode: WorkMode = WorkMode.FAST) -> SessionState:
    """Сессия с уже подготовленным планом — для тестов content-нод."""
    s = make_session(count=count, work_mode=work_mode)
    s.current_node = "plan_approved"
    s.series_plan = [f"Тема {i+1}" for i in range(count)]
    s.full_plan_items = [
        {"theme": f"Тема {i+1}", "content": f"Сюжет {i+1}"} for i in range(count)
    ]
    s.approved_plan_items = {
        str(i): s.full_plan_items[i] for i in range(count)
    }
    s.approved_indices = list(range(count))
    s.global_context = "Контекст серии"
    return s


# --- LLM response builders --------------------------------------------------

def safety_ok() -> str:
    return '{"is_safe": true}'


def safety_unsafe(reason: str = "Тестовая причина") -> str:
    return json.dumps({"is_safe": False, "reason": reason}, ensure_ascii=False)


def config_ok() -> str:
    return '{"is_compatible": true}'


def config_incompatible(reason: str = "Не подходит", suggested: str = "Сказка") -> str:
    return json.dumps(
        {"is_compatible": False, "reason": reason, "suggested_mode": suggested},
        ensure_ascii=False,
    )


def planner_ok(count: int = 2) -> str:
    ideas = [
        {"theme": f"Тема {i+1}", "content": f"Сюжет {i+1}"}
        for i in range(count + 2)  # +2 для запаса при сэмплинге
    ]
    return json.dumps(
        {"global_context": "Лисёнок Рыжик в лесу.", "ideas": ideas},
        ensure_ascii=False,
    )


def scoring_ok(count: int = 4, score: float = 0.8) -> str:
    scores = [{"index": i, "child_index": score} for i in range(count)]
    return json.dumps({"scores": scores})


def validator_approved() -> str:
    return '{"invalid_indices": []}'


def validator_rejected(idx: int, theme: str = "Новая тема", content: str = "Новый сюжет") -> str:
    return json.dumps({
        "invalid_indices": [idx],
        "reasons": ["Тестовая причина"],
        "suggestions": [{"theme": theme, "content": content}],
    })


def reviewer_revise_one(idx: int, plan_size: int) -> str:
    decisions = []
    for i in range(plan_size):
        decisions.append({
            "index": i,
            "decision": "REVISE" if i == idx else "ALREADY_OK",
            "original_data": {"theme": f"Тема {i+1}", "content": f"Сюжет {i+1}"},
            "validator_suggestion": None,
            "user_comment": "",
            "reason_for_decision": "Тест",
        })
    return json.dumps({"decisions": decisions})


def refiner_revise_one(idx: int, theme: str, content: str) -> str:
    return json.dumps({
        "revised_items": [{"index": idx, "theme": theme, "content": content}]
    })


def text_response(story_text: str) -> str:
    return f"История: {story_text}\nВопросы:\n1. Вопрос 1?\n2. Вопрос 2?"