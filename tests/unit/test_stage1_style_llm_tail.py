from src.core.interpretation.style_llm_tail import (
    NoOpStyleLlmTailProvider,
    ScriptedStyleLlmTailProvider,
    StyleLlmTailRequest,
    pick_style_layer_with_llm_tail,
    verify_style_layer_pick,
)
from src.core.prompts.models import MetadataLookupCandidate

PROMPTS_ROOT = __import__("pathlib").Path(__file__).resolve().parents[2] / "prompts"


def test_noop_provider_returns_none():
    provider = NoOpStyleLlmTailProvider()
    candidate = MetadataLookupCandidate(
        layer_id="CHUKOVSKY_STYLE",
        type="substyle",
        role=None,
        source="x",
        match_level="fuzzy",
        match_score=0.8,
        match_reason="test",
        applicability_status="applicable",
        ambiguity_group_id="substyle:reference_labels",
        short_description="test",
    )

    assert provider.pick_style_layer_id(
        StyleLlmTailRequest(phrase="чуйков", draft_params={}, candidates=(candidate,))
    ) is None


def test_scripted_provider_picks_only_allowed_candidate():
    from src.core.prompts.registry import PromptRegistry

    registry = PromptRegistry.load(PROMPTS_ROOT)
    candidates = [
        MetadataLookupCandidate(
            layer_id="CHUKOVSKY_STYLE",
            type="substyle",
            role=None,
            source=registry.get("CHUKOVSKY_STYLE").source,
            match_level="fuzzy",
            match_score=0.82,
            match_reason="test",
            applicability_status="applicable",
            ambiguity_group_id="substyle:reference_labels",
            short_description="test",
        )
    ]
    provider = ScriptedStyleLlmTailProvider(responses={"чуйков": "CHUKOVSKY_STYLE"})

    picked = pick_style_layer_with_llm_tail(
        provider,
        phrase="чуйковкого",
        draft_params={"truth_modes": "FAIRY_TALE"},
        candidates=candidates,
    )

    assert picked == "CHUKOVSKY_STYLE"
    assert verify_style_layer_pick(
        registry,
        picked,
        normalized_phrase="чуйковкого",
        applicability={"truth_modes": "FAIRY_TALE", "ages": "5"},
    )
