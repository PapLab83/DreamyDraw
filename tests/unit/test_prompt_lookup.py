from pathlib import Path

from src.core.prompts.lookup import execute_prompt_lookup, lookup_prompt_metadata
from src.core.prompts.registry import PromptRegistry

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"


def test_metadata_lookup_finds_alias_candidate_without_body():
    registry = PromptRegistry.load(PROMPTS_ROOT)

    candidates = lookup_prompt_metadata(
        registry,
        user_terms=["попугай"],
        type="entity",
        applicability={"truth_modes": "TRUTH"},
    )

    assert candidates[0].layer_id == "TRUTH_ANIMAL_PARROT"
    assert candidates[0].match_level == "alias"
    assert candidates[0].applicability_status == "applicable"
    dumped = candidates[0].to_dict()
    assert "body" not in dumped
    assert "prompt_body" not in dumped
    assert "# Назначение слоя" not in str(dumped)


def test_metadata_lookup_separates_type_and_role_filters():
    registry = PromptRegistry.load(PROMPTS_ROOT)

    by_type = lookup_prompt_metadata(registry, user_terms=["story"], type="format")
    by_role = lookup_prompt_metadata(
        registry,
        user_terms=["story"],
        role="content_format",
    )
    mixed_wrong = lookup_prompt_metadata(
        registry,
        user_terms=["story"],
        type="content_format",
    )

    assert by_type[0].layer_id == "CONTENT_FORMAT_STORY"
    assert by_role[0].layer_id == "CONTENT_FORMAT_STORY"
    assert mixed_wrong == []


def test_metadata_lookup_returns_fallback_candidates_deterministically():
    registry = PromptRegistry.load(PROMPTS_ROOT)

    candidates = lookup_prompt_metadata(
        registry,
        user_terms=["unknown-subject"],
        type="entity",
        fallback=True,
        applicability={"truth_modes": "TRUTH"},
    )

    assert candidates
    assert candidates == sorted(
        candidates,
        key=lambda item: (-item.match_score, item.source, item.layer_id),
    )
    assert candidates[0].match_level == "fallback"


def test_execution_lookup_passes_and_adds_hashes_without_changing_payloads():
    registry = PromptRegistry.load(PROMPTS_ROOT)
    unresolved_details = [
        {
            "label": "какаду",
            "type": "animal_detail",
            "instruction": "use general knowledge carefully",
        }
    ]

    envelope = execute_prompt_lookup(
        registry,
        resolved_layers=[
            {
                "type": "entity",
                "id": "TRUTH_ANIMAL_PARROT",
                "source": "truth_modes/TRUTH/characters/animals/PARROT.md",
                "reason": "alias match: какаду",
            }
        ],
        fallback_layers=[
            {
                "requested": "какаду",
                "fallback_layer_id": "TRUTH_ANIMAL_PARROT",
                "source": "truth_modes/TRUTH/characters/animals/PARROT.md",
                "reason": "generic parrot fallback",
            }
        ],
        unresolved_details=unresolved_details,
    )

    assert envelope.status == "pass"
    assert envelope.resolved_layers[0]["id"] == "TRUTH_ANIMAL_PARROT"
    assert envelope.resolved_layers[0]["source_hash"]
    assert envelope.fallback_layers[0]["fallback_layer_id"] == "TRUTH_ANIMAL_PARROT"
    assert envelope.unresolved_details == unresolved_details


def test_execution_lookup_fails_on_missing_layer_id():
    registry = PromptRegistry.load(PROMPTS_ROOT)

    envelope = execute_prompt_lookup(
        registry,
        resolved_layers=[{"type": "entity", "id": "MISSING_LAYER"}],
    )

    assert envelope.status == "fail_reresolve"
    assert envelope.failure_type == "missing_layer_id"
    assert envelope.failed_layer_id == "MISSING_LAYER"


def test_execution_lookup_fails_on_missing_source():
    registry = PromptRegistry.load(PROMPTS_ROOT)

    envelope = execute_prompt_lookup(
        registry,
        resolved_layers=[
            {
                "type": "entity",
                "id": "TRUTH_ANIMAL_PARROT",
                "source": "wrong/path.md",
            }
        ],
    )

    assert envelope.status == "fail_reresolve"
    assert envelope.failure_type == "missing_source"
    assert envelope.failed_layer_id == "TRUTH_ANIMAL_PARROT"
    assert envelope.failed_source == "wrong/path.md"


def test_execution_lookup_fails_when_source_ref_is_absent():
    registry = PromptRegistry.load(PROMPTS_ROOT)

    envelope = execute_prompt_lookup(
        registry,
        resolved_layers=[
            {
                "type": "entity",
                "id": "TRUTH_ANIMAL_PARROT",
            }
        ],
    )

    assert envelope.status == "fail_reresolve"
    assert envelope.failure_type == "missing_source"
    assert envelope.failed_layer_id == "TRUTH_ANIMAL_PARROT"


def test_execution_lookup_fails_when_fallback_source_ref_is_absent():
    registry = PromptRegistry.load(PROMPTS_ROOT)

    envelope = execute_prompt_lookup(
        registry,
        fallback_layers=[
            {
                "requested": "какаду",
                "fallback_layer_id": "TRUTH_ANIMAL_PARROT",
            }
        ],
    )

    assert envelope.status == "fail_reresolve"
    assert envelope.failure_type == "missing_source"
    assert envelope.failed_layer_id == "TRUTH_ANIMAL_PARROT"


def test_execution_lookup_fails_when_source_file_disappears(tmp_path):
    prompt_path = tmp_path / "PARROT.md"
    prompt_path.write_text(
        "\n".join(
            [
                "---",
                "id: TRUTH_ANIMAL_PARROT",
                "type: entity",
                "namespace: tests",
                "name: Попугай",
                "aliases:",
                "  - попугай",
                "applies_to:",
                "  truth_modes: [TRUTH]",
                "short_description: Test parrot.",
                "constraints:",
                "  - Keep it safe.",
                "---",
                "",
                "# Body",
            ]
        ),
        encoding="utf-8",
    )
    registry = PromptRegistry.load(tmp_path)
    prompt_path.unlink()

    envelope = execute_prompt_lookup(
        registry,
        resolved_layers=[
            {
                "type": "entity",
                "id": "TRUTH_ANIMAL_PARROT",
                "source": "PARROT.md",
            }
        ],
    )

    assert envelope.status == "fail_reresolve"
    assert envelope.failure_type == "missing_source"
    assert envelope.failed_source == "PARROT.md"


def test_execution_lookup_fails_on_type_mismatch():
    registry = PromptRegistry.load(PROMPTS_ROOT)

    envelope = execute_prompt_lookup(
        registry,
        resolved_layers=[
            {
                "type": "content_format",
                "id": "CONTENT_FORMAT_STORY",
                "source": "content_formats/story/BASE.md",
            }
        ],
    )

    assert envelope.status == "fail_reresolve"
    assert envelope.failure_type == "metadata_mismatch"
    assert envelope.failed_layer_id == "CONTENT_FORMAT_STORY"


def test_execution_lookup_fails_on_stale_source_hash():
    registry = PromptRegistry.load(PROMPTS_ROOT)

    envelope = execute_prompt_lookup(
        registry,
        resolved_layers=[
            {
                "type": "entity",
                "id": "TRUTH_ANIMAL_PARROT",
                "source": "truth_modes/TRUTH/characters/animals/PARROT.md",
                "source_hash": "stale",
            }
        ],
    )

    assert envelope.status == "fail_reresolve"
    assert envelope.failure_type == "stale_source_hash"
    assert envelope.failed_layer_id == "TRUTH_ANIMAL_PARROT"
