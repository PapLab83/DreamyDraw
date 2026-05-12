"""Интеграционные тесты собранного графа."""

import os

import pytest

from src.core.graph.builder import build_graph
from src.core.graph.state import to_graph_state
from src.models.schemas import WorkMode
from tests.conftest import (
    ScriptedLLM,
    config_ok,
    make_session,
    planner_ok,
    refiner_revise_one,
    reviewer_revise_one,
    safety_ok,
    safety_unsafe,
    scoring_ok,
    text_response,
    validator_approved,
    validator_rejected,
)


pytestmark = pytest.mark.integration


class TestGraphHappyPath:
    def test_full_pipeline_fast(self, tmp_storage, prompt_builder, fake_image):
        count = 2
        responses = [
            safety_ok(),
            config_ok(),
            planner_ok(count),
            scoring_ok(4),
            validator_approved(),
            text_response("Текст 1"),
            text_response("Текст 2"),
        ]
        llm = ScriptedLLM(responses)
        graph = build_graph(llm, fake_image, tmp_storage, prompt_builder)

        session = make_session(count=count, work_mode=WorkMode.FAST)
        tmp_storage.save_session(session)
        config = {"configurable": {"thread_id": session.session_id}}

        result = graph.invoke(to_graph_state(session), config=config)
        final = result["session"]

        assert final.is_completed
        assert final.current_node == "completed"
        assert all(s.text for s in final.stories)
        assert all(s.image_path for s in final.stories)
        assert all(os.path.exists(s.image_path) for s in final.stories)
        assert final.validation_cycles == 0
        assert fake_image.calls == count


class TestGraphValidationCycle:
    def test_rejected_then_approved(self, tmp_storage, prompt_builder, fake_image):
        count = 2
        responses = [
            safety_ok(),
            config_ok(),
            planner_ok(count),
            scoring_ok(4),
            validator_rejected(0, "Тема 1 (fixed)", "Безопасный"),
            reviewer_revise_one(0, count),
            refiner_revise_one(0, "Тема 1 (fixed)", "Безопасный"),
            validator_approved(),
            text_response("Текст 1"),
            text_response("Текст 2"),
        ]
        llm = ScriptedLLM(responses)
        graph = build_graph(llm, fake_image, tmp_storage, prompt_builder)

        session = make_session(count=count, work_mode=WorkMode.FAST)
        tmp_storage.save_session(session)
        config = {"configurable": {"thread_id": session.session_id}}

        result = graph.invoke(to_graph_state(session), config=config)
        final = result["session"]

        assert final.is_completed
        assert final.validation_cycles == 0  # сброшен после APPROVED
        assert final.full_plan_items[0]["theme"] == "Тема 1 (fixed)"
        # Должна быть запись от refiner
        assert any(
            r["source"] == "refiner"
            for r in final.revision_history.get("0", [])
        )


class TestGraphFailures:
    def test_fail_at_safety(self, tmp_storage, prompt_builder, fake_image):
        llm = ScriptedLLM([safety_unsafe()])
        graph = build_graph(llm, fake_image, tmp_storage, prompt_builder)

        session = make_session(count=2)
        tmp_storage.save_session(session)
        config = {"configurable": {"thread_id": session.session_id}}

        result = graph.invoke(to_graph_state(session), config=config)
        final = result["session"]

        assert final.current_node == "failed"
        assert not final.is_completed