from pathlib import Path

import pytest

from src.core.prompts.registry import PromptRegistry, PromptRegistryError

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"


def test_registry_loads_all_seed_prompts_and_builds_indexes():
    registry = PromptRegistry.load(PROMPTS_ROOT)

    assert len(registry) == 43
    assert registry.get("TRUTH_ANIMAL_PARROT").source == (
        "truth_modes/TRUTH/characters/animals/PARROT.md"
    )
    assert "TRUTH_ANIMAL_PARROT" in registry.by_type["entity"]
    assert "CONTENT_FORMAT_STORY" in registry.by_role["content_format"]
    assert "TRUTH_ANIMAL_PARROT" in registry.by_namespace[
        "truth_modes/TRUTH/characters/animals"
    ]
    assert "TRUTH_ANIMAL_PARROT" in registry.by_alias["попугай"]
    assert "TRUTH_ANIMAL_PARROT" in registry.by_applies_to[
        ("truth_modes", "TRUTH")
    ]
    assert registry.registry_hash


def test_prompt_body_is_loaded_explicitly_only():
    registry = PromptRegistry.load(PROMPTS_ROOT)

    body = registry.get_body("TRUTH_ANIMAL_PARROT")

    assert "# Назначение слоя" in body
    assert "Fallback decision:" in body


def test_duplicate_ids_fail(tmp_path):
    _write_prompt(tmp_path / "a.md", prompt_id="DUPLICATE_ID")
    _write_prompt(tmp_path / "nested" / "b.md", prompt_id="DUPLICATE_ID")

    with pytest.raises(PromptRegistryError, match="Duplicate prompt id"):
        PromptRegistry.load(tmp_path)


def test_invalid_type_fails(tmp_path):
    _write_prompt(tmp_path / "bad.md", prompt_type="mood")

    with pytest.raises(PromptRegistryError, match="Unsupported prompt type"):
        PromptRegistry.load(tmp_path)


def test_missing_required_metadata_fails(tmp_path):
    _write_prompt(tmp_path / "bad.md", omit="short_description")

    with pytest.raises(PromptRegistryError, match="Missing required metadata"):
        PromptRegistry.load(tmp_path)


def test_missing_front_matter_fails(tmp_path):
    (tmp_path / "bad.md").write_text("# Body only\n", encoding="utf-8")

    with pytest.raises(PromptRegistryError, match="Missing YAML front matter"):
        PromptRegistry.load(tmp_path)


@pytest.mark.parametrize(
    ("prompt_type", "role"),
    [
        ("format", None),
        ("utility", None),
        ("utility", "content_format"),
        ("language", None),
        ("language", "utility_mode"),
        ("stage", None),
        ("validator", None),
        ("refiner", None),
    ],
)
def test_seed_specific_role_policy_fails(tmp_path, prompt_type, role):
    _write_prompt(tmp_path / "bad.md", prompt_type=prompt_type, role=role)

    with pytest.raises(PromptRegistryError, match="Invalid role"):
        PromptRegistry.load(tmp_path)


def _write_prompt(
    path: Path,
    *,
    prompt_id: str = "TEST_LAYER",
    prompt_type: str = "entity",
    role: str | None = None,
    omit: str | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    metadata = {
        "id": prompt_id,
        "type": prompt_type,
        "namespace": "tests",
        "name": "Test Layer",
        "aliases": ["test"],
        "applies_to": {"content_formats": ["story"]},
        "short_description": "A test layer.",
        "constraints": ["Keep it testable."],
    }
    if role is not None:
        metadata["role"] = role
    if omit is not None:
        metadata.pop(omit)

    lines = ["---"]
    for key, value in metadata.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            lines.extend(f"  - {item}" for item in value)
        elif isinstance(value, dict):
            lines.append(f"{key}:")
            for nested_key, nested_value in value.items():
                lines.append(f"  {nested_key}: {nested_value}")
        else:
            lines.append(f"{key}: {value}")
    lines.extend(["---", "", "# Body", "", "Full prompt body."])
    path.write_text("\n".join(lines), encoding="utf-8")
