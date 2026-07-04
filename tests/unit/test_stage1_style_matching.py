from pathlib import Path

import pytest

from src.core.graph.state import to_graph_state
from src.core.interpretation.style_phrases import extract_style_phrases
from src.core.interpretation.style_llm_tail import (
    HeuristicStyleLlmTailProvider,
    ScriptedStyleLlmTailProvider,
    pick_style_layer_with_llm_tail,
)
from src.core.interpretation.style_match import resolve_style_from_text
from src.core.interpretation.text_normalize import normalize_lookup_phrase
from src.core.nodes.stage1 import (
    candidate_layer_resolution,
    final_parameter_validation,
    input_analysis,
    metadata_lookup,
)
from src.core.prompts.lookup import match_style_substyle_layers
from src.core.prompts.registry import PromptRegistry
from src.models.schemas import SessionRequest, SessionState

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"


@pytest.fixture
def registry() -> PromptRegistry:
    return PromptRegistry.load(PROMPTS_ROOT)


def test_normalize_lookup_phrase_normalizes_yo_and_punctuation():
    assert normalize_lookup_phrase("  Чуковского!!! ") == "чуковского"
    assert normalize_lookup_phrase("ёжик") == "ежик"


@pytest.mark.parametrize(
    ("text", "expected_fragment"),
    [
        ("Сказка в стиле чуковского для 5 лет", "чуковского"),
        ("3 сказки про лису по чуковскому", "чуковскому"),
        ("3 сказки про лису как чуковский", "чуковский"),
        ("3 сказки про лису как у Чуковского", "чуковского"),
    ],
)
def test_extract_style_phrases_supports_wave11_patterns(text, expected_fragment):
    phrases = extract_style_phrases(text)
    assert phrases
    assert any(expected_fragment in phrase.normalized for phrase in phrases)


def test_extract_style_phrases_marks_hard_requirement():
    phrases = extract_style_phrases("Сказка строго в стиле дисней для 5 лет")
    assert len(phrases) == 1
    assert phrases[0].is_hard_requirement is True


def test_match_style_substyle_layers_resolves_chukovsky_alias(registry):
    candidates = match_style_substyle_layers(
        registry,
        normalized_phrase="чуковского",
        applicability={"truth_modes": "FAIRY_TALE", "ages": "3"},
    )

    assert candidates
    assert candidates[0].layer_id == "CHUKOVSKY_STYLE"
    assert candidates[0].match_score >= 0.90
    assert candidates[0].applicability_status == "applicable"


def test_match_style_substyle_layers_rejects_truth_applicability(registry):
    candidates = match_style_substyle_layers(
        registry,
        normalized_phrase="чуковского",
        applicability={"truth_modes": "TRUTH", "ages": "5"},
    )

    assert candidates
    assert candidates[0].layer_id == "CHUKOVSKY_STYLE"
    assert candidates[0].applicability_status in {"not_applicable", "partially_applicable"}


def test_resolve_style_from_text_sets_layer_for_fairy_tale(registry):
    outcome = resolve_style_from_text(
        registry,
        "Сделай 2 сказки про лису для 3 лет в стиле чуковского",
        applicability={"truth_modes": "FAIRY_TALE", "ages": "3", "content_formats": "story"},
    )

    assert outcome is not None
    assert outcome.resolved is True
    assert outcome.layer_id == "CHUKOVSKY_STYLE"


def test_input_analysis_wires_chukovsky_substyle(registry):
    session = SessionState(
        request=SessionRequest(
            raw_text="Сделай 2 сказки про лису для 3 лет в стиле чуковского",
            current_config={"count": 2},
        )
    )

    result = input_analysis(to_graph_state(session), registry)

    normalized = result["session"].normalized_request
    assert normalized.truth_mode == "FAIRY_TALE"
    assert normalized.target_age == "3"
    assert normalized.substyle == "CHUKOVSKY_STYLE"


def test_chukovsky_resolves_to_layer_in_candidate_resolution(registry):
    session = SessionState(
        request=SessionRequest(
            raw_text="Сделай сказку про лису для 5 лет в стиле чуковского",
            current_config={"count": 1},
        )
    )
    state = input_analysis(to_graph_state(session), registry)
    state = metadata_lookup(state, registry)
    state = candidate_layer_resolution(state, registry)
    state = final_parameter_validation(state, registry)

    normalized = state["session"].normalized_request
    layer_ids = {ref.id for ref in normalized.prompt_context.resolved_layers}
    assert "CHUKOVSKY_STYLE" in layer_ids
    assert state["session"].interpretation_state.validation_result.status == "pass"


def test_truth_plus_chukovsky_is_applicability_conflict(registry):
    session = SessionState(
        request=SessionRequest(
            raw_text="2 правдивых истории про лису в стиле чуковского",
            current_config={"count": 2},
        )
    )

    result = input_analysis(to_graph_state(session), registry)
    normalized = result["session"].normalized_request

    assert normalized.truth_mode == "TRUTH"
    assert normalized.substyle is None
    assert any("style applicability conflict" in detail for detail in normalized.hard_details)


def test_fuzzy_typo_resolves_chukovsky(registry):
    candidates = match_style_substyle_layers(
        registry,
        normalized_phrase="чуйковкого",
        applicability={"truth_modes": "FAIRY_TALE", "ages": "5"},
    )

    assert candidates
    assert candidates[0].layer_id == "CHUKOVSKY_STYLE"
    assert candidates[0].match_level == "fuzzy"
    assert candidates[0].match_score >= 0.75


def test_input_analysis_resolves_chukovsky_typo(registry):
    session = SessionState(
        request=SessionRequest(
            raw_text="3 сказки про лису как у чуйковкого для 5 лет",
            current_config={"count": 3},
        )
    )

    result = input_analysis(to_graph_state(session), registry)
    assert result["session"].normalized_request.substyle == "CHUKOVSKY_STYLE"


def test_truth_fox_is_not_character(registry):
    session = SessionState(
        request=SessionRequest(
            raw_text="2 правдивых истории про лису для 5 лет",
            current_config={"count": 2},
        )
    )

    result = input_analysis(to_graph_state(session), registry)
    fox = next(subject for subject in result["session"].normalized_request.subjects if subject.id == "fox")
    assert fox.is_character is False


def test_fairy_tale_fox_remains_character(registry):
    session = SessionState(
        request=SessionRequest(
            raw_text="2 сказки про лису для 5 лет",
            current_config={"count": 2},
        )
    )

    result = input_analysis(to_graph_state(session), registry)
    fox = next(subject for subject in result["session"].normalized_request.subjects if subject.id == "fox")
    assert fox.is_character is True


def test_llm_tail_can_resolve_fuzzy_band(registry):
    provider = ScriptedStyleLlmTailProvider(responses={"чуйков": "CHUKOVSKY_STYLE"})
    outcome = resolve_style_from_text(
        registry,
        "3 сказки про лису как у чуйковкого",
        applicability={"truth_modes": "FAIRY_TALE", "ages": "5", "content_formats": "story"},
        llm_tail_provider=provider,
    )

    assert outcome is not None
    assert outcome.resolved is True
    assert outcome.layer_id == "CHUKOVSKY_STYLE"
    assert outcome.used_llm_tail is True


def test_llm_tail_rejects_unknown_layer_id(registry):
    provider = ScriptedStyleLlmTailProvider(responses={"чуйков": "FAKE_STYLE"})
    picked = pick_style_layer_with_llm_tail(
        provider,
        phrase="чуйковкого",
        draft_params={"truth_modes": "FAIRY_TALE"},
        candidates=match_style_substyle_layers(
            registry,
            normalized_phrase="чуйковкого",
            applicability={"truth_modes": "FAIRY_TALE", "ages": "5"},
        ),
    )

    assert picked is None
