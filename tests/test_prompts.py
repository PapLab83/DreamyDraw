from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = ROOT / "prompts"

ALLOWED_TYPES = {
    "age",
    "entity",
    "format",
    "language",
    "refiner",
    "stage",
    "style",
    "substyle",
    "truth_mode",
    "utility",
    "validator",
}

ROLE_REQUIRED_TYPES = {
    "format",
    "language",
    "refiner",
    "stage",
    "utility",
    "validator",
}

REQUIRED_FIELDS = {
    "id",
    "type",
    "namespace",
    "name",
    "aliases",
    "applies_to",
    "short_description",
    "constraints",
}

REQUIRED_PROMPT_IDS = {
    "AGE_3",
    "AGE_5",
    "CHUKOVSKY_STYLE",
    "CONTENT_FORMAT_STORY",
    "ENTITY_CANDY",
    "ENTITY_CARING_ADULT",
    "ENTITY_CHILD",
    "ENTITY_DOCTOR",
    "ENTITY_HANDS",
    "ENTITY_ROAD",
    "ENTITY_SOAP",
    "ENTITY_STRANGER",
    "ENTITY_TRAFFIC_LIGHT",
    "FAIRY_TALE_ANIMAL_FOX",
    "FAIRY_TALE_ANIMAL_HARE",
    "FAIRY_TALE_ANIMAL_HEDGEHOG",
    "FAIRY_TALE_ANIMAL_SQUIRREL",
    "FAIRY_TALE_BASE",
    "LANGUAGE_RU_AUDIENCE",
    "LANGUAGE_RU_RESULT",
    "NATURALISTIC_ANIMAL_STORY",
    "REFINER_CANDIDATE_TEXT",
    "RUSSIAN_FOLK_TALE",
    "STAGE_APPROVED_TEXT_SELECTOR",
    "STAGE_CANDIDATE_TEXT_GENERATOR",
    "STAGE_RANKER",
    "STAGE_SCORER",
    "STAGE_TOPIC_DEDUPLICATOR",
    "TRUTH_ANIMAL_FOX",
    "TRUTH_ANIMAL_HARE",
    "TRUTH_ANIMAL_HEDGEHOG",
    "TRUTH_ANIMAL_PARROT",
    "TRUTH_ANIMAL_SQUIRREL",
    "TRUTH_BASE",
    "UTILITY_NARRATIVE_BASE",
    "UTILITY_TEACHING_BASE",
    "UTILITY_TOPIC_HAND_WASHING_AFTER_WALK",
    "UTILITY_TOPIC_ROAD_SAFETY",
    "UTILITY_TOPIC_STRANGERS_AND_CANDY",
    "VALIDATOR_CANDIDATE_TEXT",
}

STAGE3_TERMS = (
    "stage 3",
    "image generation",
    "image prompt execution",
    "visual validation",
    "animation",
    "micro-cartoon",
    "promptregistry",
    "promptcomposer",
)

BOUNDARY_MARKERS = (
    "not ",
    "no ",
    "do not",
    "does not",
    "must not",
    "never ",
    "forbidden",
    "не ",
    "нельзя",
    "не нужно",
    "не добав",
    "не выполня",
    "не запуска",
    "не созда",
    "не реализ",
    "не превращ",
    "не команд",
    "запрещ",
    "недопустимо",
)


def prompt_files() -> list[Path]:
    return sorted(PROMPTS_DIR.rglob("*.md"))


def split_front_matter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"{path} must start with YAML front matter"

    try:
        _, raw_yaml, body = text.split("---\n", 2)
    except ValueError as exc:
        raise AssertionError(f"{path} must contain closing YAML front matter marker") from exc

    metadata = yaml.safe_load(raw_yaml)
    assert isinstance(metadata, dict), f"{path} front matter must parse as a mapping"
    return metadata, body


def test_prompt_metadata_contract() -> None:
    files = prompt_files()
    assert files, "expected prompt markdown files"

    ids_by_path = {}
    for path in files:
        metadata, _ = split_front_matter(path)

        missing = REQUIRED_FIELDS - metadata.keys()
        assert not missing, f"{path} missing required metadata fields: {sorted(missing)}"

        prompt_type = metadata["type"]
        assert prompt_type in ALLOWED_TYPES, f"{path} has unsupported type {prompt_type!r}"

        if prompt_type in ROLE_REQUIRED_TYPES:
            assert metadata.get("role"), f"{path} must define role for type {prompt_type!r}"

        assert isinstance(metadata["aliases"], list) and metadata["aliases"], (
            f"{path} aliases must be a non-empty list"
        )
        assert isinstance(metadata["constraints"], list) and metadata["constraints"], (
            f"{path} constraints must be a non-empty list"
        )
        assert isinstance(metadata["applies_to"], dict), f"{path} applies_to must be a mapping"

        prompt_id = metadata["id"]
        assert prompt_id not in ids_by_path, (
            f"duplicate prompt id {prompt_id!r}: {ids_by_path[prompt_id]} and {path}"
        )
        ids_by_path[prompt_id] = path


def test_required_seed_prompt_ids_are_present() -> None:
    found_ids = {split_front_matter(path)[0]["id"] for path in prompt_files()}
    missing = REQUIRED_PROMPT_IDS - found_ids
    assert not missing, f"missing required seed prompt ids: {sorted(missing)}"


def test_stage3_terms_only_appear_as_boundaries() -> None:
    offenders = []

    for path in prompt_files():
        for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            lower = line.lower()
            if not any(term in lower for term in STAGE3_TERMS):
                continue
            if any(marker in lower for marker in BOUNDARY_MARKERS):
                continue
            offenders.append(f"{path}:{line_no}: {line}")

    assert not offenders, "active Stage 3 / implementation scope found:\n" + "\n".join(offenders)
