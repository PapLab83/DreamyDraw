"""Интеграционные тесты Orchestrator (включая HITL/interrupt)."""

import pytest

from src.core.orchestrator import Orchestrator
from src.models.schemas import WorkMode
from tests.conftest import (
    ScriptedLLM,
    config_ok,
    make_request,
    planner_ok,
    safety_ok,
    safety_unsafe,
    scoring_ok,
    text_response,
    validator_approved,
)


pytestmark = pytest.mark.integration


class TestOrchestratorBasics:
    def test_happy_path_fast(self, tmp_storage, prompt_builder, fake_image):
        responses = [
            safety_ok(),
            config_ok(),
            planner_ok(2),
            scoring_ok(4),
            validator_approved(),
            text_response("Текст 1"),
            text_response("Текст 2"),
        ]
        llm = ScriptedLLM(responses)
        orch = Orchestrator(llm, fake_image, tmp_storage, prompt_builder)

        session = orch.start_session(make_request(count=2))
        result = orch.run_pipeline(session.session_id)

        assert result.is_done
        assert not result.is_waiting_user
        assert result.session.is_completed
        assert fake_image.calls == 2

    def test_fail_at_safety_returns_done(self, tmp_storage, prompt_builder, fake_image):
        llm = ScriptedLLM([safety_unsafe()])
        orch = Orchestrator(llm, fake_image, tmp_storage, prompt_builder)

        session = orch.start_session(make_request(count=2))
        result = orch.run_pipeline(session.session_id)

        assert result.is_done
        assert result.session.current_node == "failed"
        assert not result.session.is_completed

    def test_unknown_session_raises(self, tmp_storage, prompt_builder, fake_image):
        llm = ScriptedLLM([])
        orch = Orchestrator(llm, fake_image, tmp_storage, prompt_builder)

        with pytest.raises(ValueError, match="not found"):
            orch.run_pipeline("nonexistent")

    def test_completed_session_early_return(self, tmp_storage, prompt_builder, fake_image):
        llm = ScriptedLLM([])
        orch = Orchestrator(llm, fake_image, tmp_storage, prompt_builder)

        session = orch.start_session(make_request(count=1))
        session.is_completed = True
        tmp_storage.save_session(session)

        result = orch.run_pipeline(session.session_id)
        assert result.is_done
        assert llm.calls == 0


class TestOrchestratorInterrupt:
    def test_check_mode_interrupts_on_confirmation(
        self, tmp_storage, prompt_builder, fake_image
    ):
        responses = [
            safety_ok(),
            config_ok(),
            planner_ok(2),
            scoring_ok(4),
            validator_approved(),
            text_response("Текст 1"),
            text_response("Текст 2"),
        ]
        llm = ScriptedLLM(responses)
        orch = Orchestrator(llm, fake_image, tmp_storage, prompt_builder)

        session = orch.start_session(make_request(count=2, work_mode=WorkMode.CHECK))
        result = orch.run_pipeline(session.session_id)

        assert result.is_waiting_user
        assert result.interrupt_type == "user_confirmation"
        assert len(result.interrupt["stories"]) == 2
        assert fake_image.calls == 0

    def test_check_mode_resume_yes_completes(
        self, tmp_storage, prompt_builder, fake_image
    ):
        responses = [
            safety_ok(),
            config_ok(),
            planner_ok(2),
            scoring_ok(4),
            validator_approved(),
            text_response("Текст 1"),
            text_response("Текст 2"),
        ]
        llm = ScriptedLLM(responses)
        orch = Orchestrator(llm, fake_image, tmp_storage, prompt_builder)

        session = orch.start_session(make_request(count=2, work_mode=WorkMode.CHECK))
        orch.run_pipeline(session.session_id)  # доходит до interrupt
        result = orch.run_pipeline(session.session_id, resume_value="y")

        assert result.is_done
        assert result.session.is_completed
        assert fake_image.calls == 2

    def test_check_mode_resume_no_cancels(
        self, tmp_storage, prompt_builder, fake_image
    ):
        responses = [
            safety_ok(),
            config_ok(),
            planner_ok(2),
            scoring_ok(4),
            validator_approved(),
            text_response("Текст 1"),
            text_response("Текст 2"),
        ]
        llm = ScriptedLLM(responses)
        orch = Orchestrator(llm, fake_image, tmp_storage, prompt_builder)

        session = orch.start_session(make_request(count=2, work_mode=WorkMode.CHECK))
        orch.run_pipeline(session.session_id)
        result = orch.run_pipeline(session.session_id, resume_value="n")

        assert result.is_done
        assert result.session.current_node == "failed"
        assert not result.session.is_completed
        assert fake_image.calls == 0