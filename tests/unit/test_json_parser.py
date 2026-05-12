"""Тесты для parse_llm_json — устойчивость к markdown и мусору."""

import pytest

from src.core.utils.json_parser import LLMJsonParseError, parse_llm_json


class TestParseLLMJson:
    def test_pure_json(self):
        assert parse_llm_json('{"x": 1}') == {"x": 1}

    def test_pure_json_array(self):
        assert parse_llm_json('[1, 2, 3]') == [1, 2, 3]

    def test_markdown_fence_with_json_label(self):
        raw = '```json\n{"x": 1}\n```'
        assert parse_llm_json(raw) == {"x": 1}

    def test_markdown_fence_without_label(self):
        raw = '```\n{"x": 1}\n```'
        assert parse_llm_json(raw) == {"x": 1}

    def test_markdown_fence_uppercase(self):
        raw = '```JSON\n{"x": 1}\n```'
        assert parse_llm_json(raw) == {"x": 1}

    def test_text_before_json(self):
        raw = 'Вот ответ: {"x": 1}'
        assert parse_llm_json(raw) == {"x": 1}

    def test_text_after_json(self):
        raw = '{"x": 1} — это всё, что нужно'
        assert parse_llm_json(raw) == {"x": 1}

    def test_nested_objects(self):
        raw = '```json\n{"a": {"b": {"c": 1}}}\n```'
        assert parse_llm_json(raw) == {"a": {"b": {"c": 1}}}

    def test_strings_with_braces(self):
        """Строки внутри JSON могут содержать { и } — парсер не должен запутаться."""
        raw = '{"text": "это {скобка}"}'
        assert parse_llm_json(raw) == {"text": "это {скобка}"}

    def test_empty_response_with_default(self):
        result = parse_llm_json("", default={}, context="test")
        assert result == {}

    def test_empty_response_without_default_raises(self):
        with pytest.raises(LLMJsonParseError, match="Пустой ответ"):
            parse_llm_json("")

    def test_unparseable_with_default(self):
        result = parse_llm_json("это не json вообще", default={}, context="test")
        assert result == {}

    def test_unparseable_without_default_raises(self):
        with pytest.raises(LLMJsonParseError, match="Не удалось распарсить"):
            parse_llm_json("это не json вообще")