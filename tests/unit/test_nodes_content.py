"""Тесты нод content.py."""

import os

from src.core.graph.state import to_graph_state
from src.core.nodes.content import make_image_generation, make_text_generation
from tests.conftest import (
    ScriptedLLM,
    make_session_with_plan,
    text_response,
)


class TestTextGeneration:
    def test_generates_all_texts(self, tmp_storage, prompt_builder):
        llm = ScriptedLLM([
            text_response("Лиса гуляла"),
            text_response("Лиса нашла"),
        ])
        node = make_text_generation(llm, tmp_storage, prompt_builder)
        session = make_session_with_plan(count=2)
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "texts_generated"
        assert all(s.text for s in result["session"].stories)
        assert len(result["session"].stories[0].questions) == 2
        assert llm.calls == 2

    def test_skips_existing_text(self, tmp_storage, prompt_builder):
        llm = ScriptedLLM([text_response("Новая")])
        node = make_text_generation(llm, tmp_storage, prompt_builder)
        session = make_session_with_plan(count=2)
        session.stories[0].text = "Старый текст"
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].stories[0].text == "Старый текст"
        assert "Новая" in result["session"].stories[1].text
        assert llm.calls == 1

    def test_uses_approved_topic(self, tmp_storage, prompt_builder):
        llm = ScriptedLLM([text_response("x"), text_response("y")])
        node = make_text_generation(llm, tmp_storage, prompt_builder)
        session = make_session_with_plan(count=2)
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].stories[0].sub_topic == "Тема 1"
        assert result["session"].stories[1].sub_topic == "Тема 2"

    def test_no_questions_block(self, tmp_storage, prompt_builder):
        llm = ScriptedLLM(["История: Просто текст без вопросов."])
        node = make_text_generation(llm, tmp_storage, prompt_builder)
        session = make_session_with_plan(count=1)
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].stories[0].text == "Просто текст без вопросов."
        assert result["session"].stories[0].questions == []


class TestImageGeneration:
    def test_generates_all_images(self, tmp_storage, prompt_builder, fake_image):
        node = make_image_generation(fake_image, tmp_storage, prompt_builder)
        session = make_session_with_plan(count=2)
        for s in session.stories:
            s.text = "Какой-то текст"
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].is_completed
        assert result["session"].current_node == "completed"
        assert all(s.image_path for s in result["session"].stories)
        assert all(os.path.exists(s.image_path) for s in result["session"].stories)
        assert fake_image.calls == 2

    def test_skips_existing_image(self, tmp_storage, prompt_builder, fake_image):
        node = make_image_generation(fake_image, tmp_storage, prompt_builder)
        session = make_session_with_plan(count=2)
        for s in session.stories:
            s.text = "текст"
        session.stories[0].image_path = "/fake/existing.png"
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert fake_image.calls == 1