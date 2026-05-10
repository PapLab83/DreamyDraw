"""Проверка нод safety.py — без реальных LLM, на моках."""

from src.core.nodes.safety import (
    make_safety_gate,
    make_config_match,
    make_config_arbitration,
)
from src.core.graph.state import to_graph_state
from src.core.prompt_builder import PromptBuilder
from src.storage.json_storage import JSONStorage
from src.models.schemas import (
    GenerationRequest, SessionState, TruthMode, TextStyle, ImageStyle, WorkMode
)
from src.providers.base import BaseLLMProvider
import tempfile
import shutil
import os


class FakeLLM(BaseLLMProvider):
    """LLM-провайдер с предзаданными ответами."""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.calls = 0

    def generate_text(self, prompt: str) -> str:
        if self.calls >= len(self.responses):
            return "{}"
        resp = self.responses[self.calls]
        self.calls += 1
        return resp

    def generate_questions(self, text: str):
        return []


def make_session(topic: str = "лиса", mode: TruthMode = TruthMode.TRUTH) -> SessionState:
    req = GenerationRequest(
        topic=topic,
        truth_mode=mode,
        text_style=TextStyle.GENTLE,
        image_style=ImageStyle.CARTOON,
        work_mode=WorkMode.FAST,
        count=2,
    )
    return SessionState(request=req)


def run_tests():
    tmp = tempfile.mkdtemp(prefix="dd_test_")
    try:
        storage = JSONStorage(base_dir=tmp)
        pb = PromptBuilder()

        # === 1. safety_gate: безопасная тема ===
        llm = FakeLLM(['{"is_safe": true}'])
        node = make_safety_gate(llm, storage, pb)
        session = make_session()
        storage.save_session(session)
        result = node(to_graph_state(session))
        assert result["session"].current_node == "safety_passed", \
            f"Ожидали safety_passed, получили {result['session'].current_node}"
        print("1. safety_gate OK (safe) ✓")

        # === 2. safety_gate: небезопасная тема ===
        llm = FakeLLM(['{"is_safe": false, "reason": "Тестовая причина"}'])
        node = make_safety_gate(llm, storage, pb)
        session = make_session(topic="что-то опасное")
        storage.save_session(session)
        result = node(to_graph_state(session))
        assert result["session"].current_node == "failed", \
            f"Ожидали failed, получили {result['session'].current_node}"
        print("2. safety_gate OK (unsafe → failed) ✓")

        # === 3. safety_gate: ломаный JSON, fallback по 'true' ===
        llm = FakeLLM(["true и ещё немного текста"])
        node = make_safety_gate(llm, storage, pb)
        session = make_session()
        storage.save_session(session)
        result = node(to_graph_state(session))
        assert result["session"].current_node == "safety_passed", \
            f"Ожидали fallback → safety_passed, получили {result['session'].current_node}"
        print("3. safety_gate OK (fallback) ✓")

        # === 4. config_match: совместимо ===
        llm = FakeLLM(['{"is_compatible": true}'])
        node = make_config_match(llm, storage, pb)
        session = make_session()
        session.current_node = "safety_passed"
        storage.save_session(session)
        result = node(to_graph_state(session))
        assert result["session"].current_node == "config_passed", \
            f"Ожидали config_passed, получили {result['session'].current_node}"
        print("4. config_match OK (compatible) ✓")

        # === 5. config_match: несовместимо → арбитраж ===
        llm = FakeLLM([
            '{"is_compatible": false, "reason": "Тема плохо ложится в правду", '
            '"suggested_mode": "Сказка"}'
        ])
        node = make_config_match(llm, storage, pb)
        session = make_session()
        session.current_node = "safety_passed"
        storage.save_session(session)
        result = node(to_graph_state(session))
        assert result["session"].current_node == "config_needs_arbitration", \
            f"Ожидали config_needs_arbitration, получили {result['session'].current_node}"
        assert "Сказка" in result["session"].validator_feedback, \
            "В validator_feedback должно быть упоминание Сказки"
        print("5. config_match OK (incompatible → arbitration) ✓")

        # === 6. config_arbitration: пропущено (нужен граф с checkpointer) ===
        print("6. config_arbitration: пропущено (нужен граф с checkpointer) ⊘")

        print("\nВсе проверки safety.py пройдены ✓")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run_tests()