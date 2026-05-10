"""Проверка нод validation.py — без реальных LLM, на моках."""

import json
import os
import shutil
import tempfile

from src.core.graph.state import to_graph_state
from src.core.nodes.validation import (
    make_plan_refiner,
    make_plan_reviewer,
    make_plan_validator,
)
from src.core.prompt_builder import PromptBuilder
from src.models.schemas import (
    GenerationRequest,
    ImageStyle,
    SessionState,
    TextStyle,
    TruthMode,
    WorkMode,
)
from src.providers.base import BaseLLMProvider
from src.storage.json_storage import JSONStorage


class FakeLLM(BaseLLMProvider):
    def __init__(self, responses):
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


def make_session_with_plan(count: int = 3) -> SessionState:
    req = GenerationRequest(
        topic="лиса",
        truth_mode=TruthMode.TRUTH,
        text_style=TextStyle.GENTLE,
        image_style=ImageStyle.CARTOON,
        work_mode=WorkMode.FAST,
        count=count,
    )
    s = SessionState(request=req)
    s.current_node = "series_planned"
    s.series_plan = [f"Тема {i+1}" for i in range(count)]
    s.full_plan_items = [
        {"theme": f"Тема {i+1}", "content": f"Сюжет {i+1}"} for i in range(count)
    ]
    s.global_context = "Контекст серии"
    return s


def run_tests():
    tmp = tempfile.mkdtemp(prefix="dd_test_")
    try:
        storage = JSONStorage(base_dir=tmp)
        pb = PromptBuilder()

        # === 1. plan_validator: всё одобрено ===
        llm = FakeLLM([json.dumps({"invalid_indices": []})])
        node = make_plan_validator(llm, storage, pb)
        session = make_session_with_plan(3)
        storage.save_session(session)
        result = node(to_graph_state(session))
        assert result["session"].current_node == "plan_approved"
        assert len(result["session"].approved_plan_items) == 3
        assert result["session"].validation_cycles == 0
        print("1. plan_validator OK (APPROVED) ✓")

        # === 2. plan_validator: одна тема отклонена ===
        feedback = json.dumps({
            "invalid_indices": [1],
            "reasons": ["Опасная сцена"],
            "suggestions": [{"theme": "Тема 2 (новая)", "content": "Безопасный сюжет"}],
        })
        llm = FakeLLM([feedback])
        node = make_plan_validator(llm, storage, pb)
        session = make_session_with_plan(3)
        storage.save_session(session)
        result = node(to_graph_state(session))
        assert result["session"].current_node == "plan_needs_refine"
        assert result["session"].validation_cycles == 1
        # Две темы должны быть одобрены
        assert len(result["session"].approved_plan_items) == 2
        # У темы 1 (отклонённой) — запись в revision_history с source=validator
        assert "1" in result["session"].revision_history
        assert any(
            r["source"] == "validator"
            for r in result["session"].revision_history["1"]
        )
        print("2. plan_validator OK (REJECTED → cycles=1, plan_needs_refine) ✓")

        # === 3. plan_validator: достижение порога арбитража ===
        feedback = json.dumps({
            "invalid_indices": [0],
            "reasons": ["причина"],
            "suggestions": [{"theme": "новая", "content": "новый сюжет"}],
        })
        llm = FakeLLM([feedback])
        node = make_plan_validator(llm, storage, pb)
        session = make_session_with_plan(3)
        session.validation_cycles = 2  # после инкремента станет 3 = порог
        storage.save_session(session)
        result = node(to_graph_state(session))
        assert result["session"].current_node == "plan_needs_user_arbitration"
        assert result["session"].validation_cycles == 3
        print("3. plan_validator OK (достижение порога → arbitration) ✓")

        # === 4. plan_validator: превышение MAX_VALIDATION_RETRIES → failed ===
        llm = FakeLLM([feedback])
        node = make_plan_validator(llm, storage, pb)
        session = make_session_with_plan(3)
        session.validation_cycles = 5  # после инкремента станет 6 > MAX (5)
        storage.save_session(session)
        result = node(to_graph_state(session))
        assert result["session"].current_node == "failed"
        print("4. plan_validator OK (превышение MAX → failed) ✓")

        # === 5. plan_reviewer: REVISE → items в pending_revisions ===
        reviewer_response = json.dumps({
            "decisions": [
                {
                    "index": 0,
                    "decision": "REVISE",
                    "original_data": {"theme": "Тема 1", "content": "Сюжет 1"},
                    "validator_suggestion": {"theme": "Тема 1 (исправлено)", "content": "Безопасно"},
                    "user_comment": "",
                    "reason_for_decision": "Тестовая правка",
                },
                {
                    "index": 1,
                    "decision": "ALREADY_OK",
                    "original_data": {"theme": "Тема 2", "content": "Сюжет 2"},
                    "validator_suggestion": None,
                    "user_comment": "",
                    "reason_for_decision": "Тема ок",
                },
            ]
        })
        llm = FakeLLM([reviewer_response])
        node = make_plan_reviewer(llm, storage, pb)
        session = make_session_with_plan(3)
        session.validator_feedback = json.dumps({
            "invalid_indices": [0],
            "reasons": ["причина"],
            "suggestions": [{"theme": "Тема 1 (исправлено)", "content": "Безопасно"}],
        })
        storage.save_session(session)
        result = node(to_graph_state(session))
        assert result["session"].current_node == "reviewer_done"
        assert len(result["session"].pending_revisions) == 1
        assert result["session"].pending_revisions[0]["index"] == 0
        # ALREADY_OK тема (idx=1) должна быть одобрена
        assert "1" in result["session"].approved_plan_items
        print("5. plan_reviewer OK (REVISE → pending, ALREADY_OK → approved) ✓")

        # === 6. plan_reviewer: страховка KEEP_ORIGINAL при пустом комменте ===
        reviewer_response = json.dumps({
            "decisions": [
                {
                    "index": 0,
                    "decision": "KEEP_ORIGINAL",  # ← должно превратиться в REVISE
                    "original_data": {"theme": "Тема 1", "content": "Сюжет 1"},
                    "validator_suggestion": None,
                    "user_comment": "",
                    "reason_for_decision": "Оставить",
                },
            ]
        })
        llm = FakeLLM([reviewer_response])
        node = make_plan_reviewer(llm, storage, pb)
        session = make_session_with_plan(1)
        session.validator_feedback = json.dumps({
            "invalid_indices": [0],
            "reasons": ["причина"],
            "suggestions": [None],
        })
        session.user_feedback = None
        storage.save_session(session)
        result = node(to_graph_state(session))
        assert len(result["session"].pending_revisions) == 1, \
            "Страховка не сработала: KEEP_ORIGINAL для отклонённой темы должен стать REVISE"
        print("6. plan_reviewer OK (страховка KEEP_ORIGINAL → REVISE) ✓")

        # === 7. plan_reviewer: fallback при пустом ответе ===
        llm = FakeLLM([""])  # пустой ответ
        node = make_plan_reviewer(llm, storage, pb)
        session = make_session_with_plan(2)
        session.validator_feedback = json.dumps({
            "invalid_indices": [0],
            "reasons": ["причина"],
            "suggestions": [{"theme": "новая", "content": "новый"}],
        })
        storage.save_session(session)
        result = node(to_graph_state(session))
        # fallback: idx=0 → REVISE, idx=1 → ALREADY_OK
        assert len(result["session"].pending_revisions) == 1
        assert "1" in result["session"].approved_plan_items
        print("7. plan_reviewer OK (fallback при пустом ответе) ✓")

        # === 8. plan_refiner: применяет правки ===
        refiner_response = json.dumps({
            "revised_items": [
                {"index": 0, "theme": "Тема 1 (после правки)", "content": "Новый сюжет"},
            ]
        })
        llm = FakeLLM([refiner_response])
        node = make_plan_refiner(llm, storage, pb)
        session = make_session_with_plan(3)
        session.pending_revisions = [
            {
                "index": 0,
                "decision": "REVISE",
                "original_data": {"theme": "Тема 1", "content": "Сюжет 1"},
                "validator_suggestion": None,
                "user_comment": "",
            }
        ]
        session.user_feedback = "комментарий"
        storage.save_session(session)
        result = node(to_graph_state(session))
        assert result["session"].current_node == "series_planned"
        assert result["session"].full_plan_items[0]["theme"] == "Тема 1 (после правки)"
        assert result["session"].user_feedback is None  # обнулён
        assert result["session"].pending_revisions == []  # обнулён
        # Запись в истории с source=refiner и комментарием пользователя
        assert any(
            r["source"] == "refiner" and "комментарий" in r["note"]
            for r in result["session"].revision_history.get("0", [])
        )
        print("8. plan_refiner OK (правка применена, user_feedback обнулён) ✓")

        # === 9. plan_refiner: нет items_to_revise → не вызывает LLM ===
        llm = FakeLLM([])  # никаких ответов
        node = make_plan_refiner(llm, storage, pb)
        session = make_session_with_plan(2)
        session.pending_revisions = []
        storage.save_session(session)
        result = node(to_graph_state(session))
        assert result["session"].current_node == "series_planned"
        assert llm.calls == 0  # LLM не вызывался
        print("9. plan_refiner OK (пустой pending → без LLM-вызова) ✓")

        # === 10. plan_refiner: ошибка LLM → failed ===
        llm = FakeLLM([""])  # пустой ответ
        node = make_plan_refiner(llm, storage, pb)
        session = make_session_with_plan(1)
        session.pending_revisions = [
            {
                "index": 0,
                "decision": "REVISE",
                "original_data": {"theme": "x", "content": "y"},
            }
        ]
        storage.save_session(session)
        result = node(to_graph_state(session))
        assert result["session"].current_node == "failed"
        print("10. plan_refiner OK (ошибка LLM → failed) ✓")

        # === 11. plan_arbitration: пропущено (нужен граф с checkpointer)
        print("11. plan_arbitration: пропущено (нужен граф с checkpointer) ⊘")

        print("\nВсе проверки validation.py пройдены ✓")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    run_tests()