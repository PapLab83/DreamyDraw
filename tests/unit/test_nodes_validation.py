"""Тесты нод validation.py."""

import json

from src.core.graph.state import to_graph_state
from src.core.nodes.validation import (
    make_plan_refiner,
    make_plan_reviewer,
    make_plan_validator,
)
from tests.conftest import (
    ScriptedLLM,
    make_session_with_plan,
    refiner_revise_one,
    reviewer_revise_one,
    validator_approved,
    validator_rejected,
)


class TestPlanValidator:
    def test_approved(self, tmp_storage, prompt_builder):
        llm = ScriptedLLM([validator_approved()])
        node = make_plan_validator(llm, tmp_storage, prompt_builder)
        session = make_session_with_plan(count=2)
        # Сбросим approved_plan_items, чтобы валидатор реально запустился
        session.approved_plan_items = {}
        session.approved_indices = []
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "plan_approved"

    def test_rejected_first_time(self, tmp_storage, prompt_builder):
        llm = ScriptedLLM([validator_rejected(idx=1, theme="Новая", content="Сюжет")])
        node = make_plan_validator(llm, tmp_storage, prompt_builder)
        session = make_session_with_plan(count=2)
        session.approved_plan_items = {}
        session.approved_indices = []
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "plan_needs_refine"
        assert result["session"].validation_cycles == 1

    def test_threshold_triggers_arbitration(self, tmp_storage, prompt_builder):
        """При validation_cycles=2 после REJECTED станет 3 ≥ порог → arbitration."""
        llm = ScriptedLLM([validator_rejected(idx=0)])
        node = make_plan_validator(llm, tmp_storage, prompt_builder)
        session = make_session_with_plan(count=2)
        session.approved_plan_items = {}
        session.approved_indices = []
        session.validation_cycles = 2
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "plan_needs_user_arbitration"

    def test_max_attempts_fails(self, tmp_storage, prompt_builder):
        """При validation_cycles=5 после REJECTED станет 6 > MAX (5) → failed."""
        llm = ScriptedLLM([validator_rejected(idx=0)])
        node = make_plan_validator(llm, tmp_storage, prompt_builder)
        session = make_session_with_plan(count=2)
        session.approved_plan_items = {}
        session.approved_indices = []
        session.validation_cycles = 5  # на инкременте станет 6 > MAX_VALIDATION_RETRIES (5)
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "failed"


class TestPlanReviewer:
    def test_empty_feedback_no_op(self, tmp_storage, prompt_builder):
        """
        Когда validator_feedback пуст (нет invalid_indices) — ревьюер всё равно
        вызывает LLM (так устроен код), но решений не принимает.
        Проверяем, что нода доходит до reviewer_done без падений.
        Используем fallback (пустой ответ LLM → автогенерация решений).
        """
        # Пустой ответ → fallback. Так как currently_rejected пуст,
        # все темы получат ALREADY_OK.
        llm = ScriptedLLM([""])
        node = make_plan_reviewer(llm, tmp_storage, prompt_builder)
        session = make_session_with_plan(count=2)
        session.validator_feedback = json.dumps({
            "invalid_indices": [],
            "reasons": [],
            "suggestions": [],
        })
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "reviewer_done"
        # pending_revisions пуст, потому что некого revise-ить
        assert result["session"].pending_revisions == []

    def test_revise_decision_writes_pending(self, tmp_storage, prompt_builder):
        """REVISE → ревьюер кладёт элемент в pending_revisions."""
        plan_size = 2
        llm = ScriptedLLM([reviewer_revise_one(idx=0, plan_size=plan_size)])
        node = make_plan_reviewer(llm, tmp_storage, prompt_builder)
        session = make_session_with_plan(count=plan_size)
        # Имитируем, что валидатор отклонил idx=0
        session.validator_feedback = json.dumps({
            "invalid_indices": [0],
            "reasons": ["Тестовая причина"],
            "suggestions": [{"theme": "Suggested", "content": "По плану"}],
        })
        # approved_plan_items имеет обе темы — REVISE должен удалить idx=0
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "reviewer_done"
        assert len(result["session"].pending_revisions) == 1
        assert result["session"].pending_revisions[0]["index"] == 0
        assert result["session"].pending_revisions[0]["decision"] == "REVISE"
        # idx=0 должен быть удалён из approved_plan_items
        assert "0" not in result["session"].approved_plan_items


class TestPlanRefiner:
    def test_empty_pending_no_llm_call(self, tmp_storage, prompt_builder):
        """Когда pending_revisions пуст — refiner не вызывает LLM."""
        llm = ScriptedLLM([])
        node = make_plan_refiner(llm, tmp_storage, prompt_builder)
        session = make_session_with_plan(count=2)
        session.pending_revisions = []
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "series_planned"
        assert llm.calls == 0

    def test_applies_revision(self, tmp_storage, prompt_builder):
        """Refiner применяет правки и обнуляет user_feedback."""
        llm = ScriptedLLM([refiner_revise_one(0, "Новая тема", "Новый сюжет")])
        node = make_plan_refiner(llm, tmp_storage, prompt_builder)
        session = make_session_with_plan(count=2)
        # Имитируем состояние после ревьюера: idx=0 удалён из approved
        # (его правит refiner), idx=1 остался одобренным.
        session.approved_plan_items.pop("0", None)
        session.approved_indices = [1]
        session.pending_revisions = [{
            "index": 0,
            "decision": "REVISE",
            "original_data": session.full_plan_items[0],
            "validator_suggestion": {"theme": "Suggested", "content": "По плану"},
            "user_comment": "Сделай мягче",
            "reason_for_decision": "Тест",
        }]
        session.user_feedback = "Сделай мягче"
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "series_planned"
        assert result["session"].full_plan_items[0]["theme"] == "Новая тема"
        assert result["session"].full_plan_items[0]["content"] == "Новый сюжет"
        assert result["session"].full_plan_items[1]["theme"] == "Тема 2"
        assert result["session"].user_feedback is None
        assert result["session"].pending_revisions == []