"""Тесты нод safety.py."""

from src.core.graph.state import to_graph_state
from src.core.nodes.safety import make_config_match, make_safety_gate
from tests.conftest import (
    ScriptedLLM,
    config_incompatible,
    config_ok,
    make_session,
    safety_ok,
    safety_unsafe,
)


class TestSafetyGate:
    def test_safe_topic_passes(self, tmp_storage, prompt_builder):
        llm = ScriptedLLM([safety_ok()])
        node = make_safety_gate(llm, tmp_storage, prompt_builder)
        session = make_session()
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "safety_passed"

    def test_unsafe_topic_fails(self, tmp_storage, prompt_builder):
        llm = ScriptedLLM([safety_unsafe()])
        node = make_safety_gate(llm, tmp_storage, prompt_builder)
        session = make_session(topic="опасная тема") if False else make_session()
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "failed"

    def test_broken_json_with_true_fallback(self, tmp_storage, prompt_builder):
        """Когда LLM вернул не-JSON, но содержит 'true' — считаем безопасным."""
        llm = ScriptedLLM(["безопасная тема, true и ещё текст"])
        node = make_safety_gate(llm, tmp_storage, prompt_builder)
        session = make_session()
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "safety_passed"


class TestConfigMatch:
    def test_compatible_passes(self, tmp_storage, prompt_builder):
        llm = ScriptedLLM([config_ok()])
        node = make_config_match(llm, tmp_storage, prompt_builder)
        session = make_session()
        session.current_node = "safety_passed"
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "config_passed"

    def test_incompatible_goes_to_arbitration(self, tmp_storage, prompt_builder):
        llm = ScriptedLLM([config_incompatible(suggested="Сказка")])
        node = make_config_match(llm, tmp_storage, prompt_builder)
        session = make_session()
        session.current_node = "safety_passed"
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "config_needs_arbitration"
        assert "Сказка" in result["session"].validator_feedback