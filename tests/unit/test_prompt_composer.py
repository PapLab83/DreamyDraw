from pathlib import Path

from src.core.prompts.composer import PromptComposer
from src.core.prompts.registry import PromptRegistry
from src.models.schemas import (
    ExecutionPromptContext,
    NormalizedRequest,
    PromptFallbackLayer,
    PromptLayerRef,
    PromptUnresolvedDetail,
    SessionRequest,
    SessionState,
    Subject,
)

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"


def test_generator_context_uses_expected_layer_order_and_static_entry():
    composer = PromptComposer(PromptRegistry.load(PROMPTS_ROOT))
    normalized_request = _normalized_request()
    prompt_context = _prompt_context()

    result = composer.build_stage_context(
        normalized_request=normalized_request,
        prompt_context=prompt_context,
        stage="candidate_text_generator",
    )

    assert result.durable_entry.stage == "candidate_text_generator"
    assert result.durable_entry.candidate_id is None
    assert result.durable_entry.version_id is None
    assert result.durable_entry.attempt is None
    assert result.durable_entry.layer_ids == [
        "CONTENT_FORMAT_STORY",
        "FAIRY_TALE_BASE",
        "UTILITY_TEACHING_BASE",
        "UTILITY_TOPIC_ROAD_SAFETY",
        "AGE_5",
        "LANGUAGE_RU_AUDIENCE",
        "LANGUAGE_RU_RESULT",
        "RUSSIAN_FOLK_TALE",
        "FAIRY_TALE_ANIMAL_FOX",
        "STAGE_CANDIDATE_TEXT_GENERATOR",
    ]
    assert result.runtime_context["hard_details"] == ["Не переходить дорогу одному."]
    assert result.runtime_context["soft_preferences"] == ["Тёплый спокойный финал."]
    assert result.runtime_context["context_blocks"].index("hard_details") < (
        result.runtime_context["context_blocks"].index("soft_preferences")
    )
    assert result.runtime_context["unresolved_details"] == [
        {
            "label": "любимый синий шарф",
            "type": "character_detail",
            "instruction": "Можно использовать как свободную деталь, без отдельного layer id.",
        }
    ]
    assert "любимый синий шарф" not in result.durable_entry.layer_ids
    assert result.durable_entry.unresolved_detail_labels == ["любимый синий шарф"]
    assert result.durable_entry.body_policy == "lazy_not_persisted"
    assert "bodies" not in result.runtime_context
    assert "# Назначение слоя" not in str(result.durable_entry.model_dump())


def test_compact_stage_contexts_are_body_free_by_default():
    composer = PromptComposer(PromptRegistry.load(PROMPTS_ROOT))

    dedup = composer.build_stage_context(
        normalized_request=_normalized_request(),
        prompt_context=_prompt_context(),
        stage="topic_deduplicator",
        stage_inputs={"candidate_themes": ["Лиса у перехода", "Лиса ждёт зелёный"]},
    )
    scorer = composer.build_stage_context(
        normalized_request=_normalized_request(),
        prompt_context=_prompt_context(),
        stage="scorer",
        stage_inputs={"candidate_texts": [{"candidate_id": "c01", "text": "Текст"}]},
    )
    selector = composer.build_stage_context(
        normalized_request=_normalized_request(),
        prompt_context=_prompt_context(),
        stage="approved_text_selector",
        stage_inputs={
            "ranked_candidates": [{"candidate_id": "c01", "rank": 1}],
            "validated_versions": [{"candidate_id": "c01", "version_id": "c01_v1"}],
            "shortage_policy": "normal_only",
        },
    )

    assert dedup.durable_entry.layer_ids == [
        "UTILITY_TEACHING_BASE",
        "UTILITY_TOPIC_ROAD_SAFETY",
        "FAIRY_TALE_ANIMAL_FOX",
        "STAGE_TOPIC_DEDUPLICATOR",
    ]
    assert dedup.runtime_context["stage_inputs_summary"]["candidate_themes_count"] == 2
    assert scorer.runtime_context["stage_instructions"]["hard_gates"] == [
        "safety",
        "truth_fit",
        "age_fit",
        "utility_goal",
        "subject_continuity",
        "hard_details",
        "character_consistency",
    ]
    assert selector.runtime_context["stage_inputs_summary"]["output_count"] == 2
    assert selector.runtime_context["stage_inputs_summary"]["shortage_policy"] == "normal_only"
    assert "bodies" not in dedup.runtime_context
    assert "bodies" not in scorer.runtime_context
    assert "bodies" not in selector.runtime_context
    assert "# Назначение stage" not in str(dedup.durable_entry.model_dump())


def test_ranker_context_is_static_compact_and_scorer_hash_uses_candidate_payload():
    composer = PromptComposer(PromptRegistry.load(PROMPTS_ROOT))
    first_scorer = composer.build_stage_context(
        normalized_request=_normalized_request(),
        prompt_context=_prompt_context(),
        stage="scorer",
        stage_inputs={"candidate_texts": [{"candidate_id": "c01", "text": "Первый текст"}]},
    )
    changed_scorer = composer.build_stage_context(
        normalized_request=_normalized_request(),
        prompt_context=_prompt_context(),
        stage="scorer",
        stage_inputs={"candidate_texts": [{"candidate_id": "c01", "text": "Другой текст"}]},
    )
    ranker = composer.build_stage_context(
        normalized_request=_normalized_request(),
        prompt_context=_prompt_context(),
        stage="ranker",
        stage_inputs={"scores": [{"candidate_id": "c01", "total_score": 0.9}]},
    )

    assert first_scorer.durable_entry.stage_context_hash != (
        changed_scorer.durable_entry.stage_context_hash
    )
    assert ranker.durable_entry.candidate_id is None
    assert ranker.durable_entry.version_id is None
    assert ranker.durable_entry.attempt is None
    assert ranker.durable_entry.layer_ids == ["STAGE_RANKER"]
    assert ranker.runtime_context["stage_inputs_summary"]["scores_count"] == 1
    assert ranker.runtime_context["stage_instructions"]["ranking_policy"] == (
        "hard_gates_first_total_score_desc"
    )


def test_relevant_fallback_layers_are_kept_even_when_not_resolved_layers():
    composer = PromptComposer(PromptRegistry.load(PROMPTS_ROOT))
    prompt_context = _prompt_context()
    prompt_context.resolved_layers = [
        layer
        for layer in prompt_context.resolved_layers
        if layer.id != "FAIRY_TALE_ANIMAL_FOX"
    ]

    result = composer.build_stage_context(
        normalized_request=_normalized_request(),
        prompt_context=prompt_context,
        stage="candidate_text_generator",
    )

    assert "FAIRY_TALE_ANIMAL_FOX" not in result.durable_entry.layer_ids
    assert result.durable_entry.fallback_layer_ids == ["FAIRY_TALE_ANIMAL_FOX"]
    assert result.runtime_context["fallback_layer_refs"][0]["fallback_layer_id"] == (
        "FAIRY_TALE_ANIMAL_FOX"
    )


def test_static_stages_reject_candidate_identity():
    composer = PromptComposer(PromptRegistry.load(PROMPTS_ROOT))

    try:
        composer.build_stage_context(
            normalized_request=_normalized_request(),
            prompt_context=_prompt_context(),
            stage="candidate_text_generator",
            candidate_id="c99",
        )
    except ValueError as exc:
        assert "does not accept candidate identity" in str(exc)
    else:
        raise AssertionError("Static stage accepted candidate identity.")


def test_dynamic_validator_and_refiner_include_candidate_identity_and_hash_inputs():
    composer = PromptComposer(PromptRegistry.load(PROMPTS_ROOT))
    validator = composer.build_stage_context(
        normalized_request=_normalized_request(),
        prompt_context=_prompt_context(),
        stage="candidate_validator",
        candidate_id="c02",
        version_id="c02_v2",
        attempt=2,
        stage_inputs={"candidate_text": {"candidate_id": "c02", "text": "Черновик"}},
    )
    other_validator = composer.build_stage_context(
        normalized_request=_normalized_request(),
        prompt_context=_prompt_context(),
        stage="candidate_validator",
        candidate_id="c03",
        version_id="c03_v1",
        attempt=1,
        stage_inputs={"candidate_text": {"candidate_id": "c03", "text": "Другой"}},
    )
    refiner = composer.build_stage_context(
        normalized_request=_normalized_request(),
        prompt_context=_prompt_context(),
        stage="candidate_refiner",
        candidate_id="c02",
        version_id="c02_v2",
        attempt=2,
        stage_inputs={
            "candidate_text": {"candidate_id": "c02", "text": "Черновик"},
            "validator_issues": [{"type": "age_fit", "severity": "major"}],
            "required_fixes": ["Сделать фразы короче."],
        },
    )

    assert validator.durable_entry.candidate_id == "c02"
    assert validator.durable_entry.version_id == "c02_v2"
    assert validator.durable_entry.attempt == 2
    assert validator.durable_entry.layer_ids[-1] == "VALIDATOR_CANDIDATE_TEXT"
    assert validator.runtime_context["stage_inputs_summary"]["candidate_id"] == "c02"
    assert other_validator.durable_entry.stage_context_hash != (
        validator.durable_entry.stage_context_hash
    )
    assert refiner.durable_entry.layer_ids[-1] == "REFINER_CANDIDATE_TEXT"
    assert refiner.runtime_context["stage_inputs_summary"]["validator_issues_count"] == 1
    assert refiner.runtime_context["stage_inputs_summary"]["required_fixes_count"] == 1


def test_refiner_context_includes_canonical_immutable_fields_and_snapshot():
    composer = PromptComposer(PromptRegistry.load(PROMPTS_ROOT))

    refiner = composer.build_stage_context(
        normalized_request=_normalized_request(),
        prompt_context=_prompt_context(),
        stage="candidate_refiner",
        candidate_id="c02",
        version_id="c02_v2",
        attempt=2,
        stage_inputs={
            "candidate_text": {
                "candidate_id": "c02",
                "version_id": "c02_v2",
                "source_version_id": "c02_v1",
                "theme": "Лиса учится ждать зелёный сигнал",
                "text": "Черновик",
            },
            "validator_issues": [{"type": "age_fit", "severity": "major"}],
            "required_fixes": ["Сделать фразы короче."],
        },
    )

    summary = refiner.runtime_context["stage_inputs_summary"]

    assert summary["immutable_fields"] == [
        "candidate_id",
        "source_version_id",
        "theme",
        "content_format",
        "truth_mode",
        "utility_mode",
        "utility_topic",
        "target_age",
        "audience_language",
        "result_language",
        "main_subject",
        "required_subjects",
        "subject_continuity_policy",
        "character_profile",
        "hard_details",
    ]
    assert summary["immutable_snapshot"]["theme"] == (
        "Лиса учится ждать зелёный сигнал"
    )
    assert summary["immutable_snapshot"]["content_format"] == "story"
    assert summary["immutable_snapshot"]["truth_mode"] == "FAIRY_TALE"
    assert summary["immutable_snapshot"]["utility_mode"] == "TEACHING"
    assert summary["immutable_snapshot"]["utility_topic"] == "ROAD_SAFETY"
    assert summary["immutable_snapshot"]["target_age"] == "5"
    assert summary["immutable_snapshot"]["main_subject"] == "лиса"
    assert summary["immutable_snapshot"]["required_subjects"] == ["fox"]
    assert summary["immutable_snapshot"]["hard_details"] == [
        "Не переходить дорогу одному."
    ]


def test_stage_hash_changes_for_relevant_prompt_and_detail_inputs_only():
    composer = PromptComposer(PromptRegistry.load(PROMPTS_ROOT))
    base = composer.build_stage_context(
        normalized_request=_normalized_request(),
        prompt_context=_prompt_context(),
        stage="candidate_text_generator",
    )
    changed_detail = _normalized_request()
    changed_detail.hard_details.append("Добавить правило про красный свет.")
    changed_layer_context = _prompt_context()
    changed_layer_context.resolved_layers = [
        layer
        for layer in changed_layer_context.resolved_layers
        if layer.id != "RUSSIAN_FOLK_TALE"
    ]

    detail_result = composer.build_stage_context(
        normalized_request=changed_detail,
        prompt_context=_prompt_context(),
        stage="candidate_text_generator",
    )
    layer_result = composer.build_stage_context(
        normalized_request=_normalized_request(),
        prompt_context=changed_layer_context,
        stage="candidate_text_generator",
    )

    assert base.durable_entry.source_prompt_context_hash == "snapshot-1"
    assert detail_result.durable_entry.stage_context_hash != base.durable_entry.stage_context_hash
    assert layer_result.durable_entry.stage_context_hash != base.durable_entry.stage_context_hash


def test_body_loading_is_explicit_runtime_only_and_composer_does_not_mutate_session():
    composer = PromptComposer(PromptRegistry.load(PROMPTS_ROOT))
    session = SessionState(
        request=SessionRequest(raw_text="Сказка про лису у дороги."),
        normalized_request=_normalized_request(),
        prompt_context=_prompt_context(),
    )
    before = session.model_dump()

    result = composer.build_stage_context(
        normalized_request=session.normalized_request,
        prompt_context=session.prompt_context,
        stage="candidate_text_generator",
        body_policy="include_bodies_runtime",
    )

    assert session.model_dump() == before
    assert result.durable_entry.body_policy == "include_bodies_runtime"
    assert "bodies" in result.runtime_context
    assert "STAGE_CANDIDATE_TEXT_GENERATOR" in result.runtime_context["bodies"]
    assert "# Назначение stage" in result.runtime_context["bodies"]["STAGE_CANDIDATE_TEXT_GENERATOR"]
    assert "# Назначение stage" not in str(result.durable_entry.model_dump())


def _normalized_request() -> NormalizedRequest:
    return NormalizedRequest(
        content_format="story",
        truth_mode="FAIRY_TALE",
        utility_mode="TEACHING",
        utility_topic="ROAD_SAFETY",
        target_age="5",
        output_count=2,
        audience_language="ru",
        result_language="ru",
        main_subject="лиса",
        subjects=[
            Subject(
                id="fox",
                label="лиса",
                type="animal",
                role="main",
                is_character=True,
                resolved_layer_id="FAIRY_TALE_ANIMAL_FOX",
            )
        ],
        text_style_base="folklore",
        substyle="russian_folk_tale",
        hard_details=["Не переходить дорогу одному."],
        soft_preferences=["Тёплый спокойный финал."],
    )


def _prompt_context() -> ExecutionPromptContext:
    return ExecutionPromptContext(
        resolved_layers=[
            _layer("format", "CONTENT_FORMAT_STORY", "content_formats/story/BASE.md", "content_format"),
            _layer("truth_mode", "FAIRY_TALE_BASE", "truth_modes/FAIRY_TALE/BASE.md"),
            _layer("utility", "UTILITY_TEACHING_BASE", "utility_modes/TEACHING/BASE.md", "utility_mode"),
            _layer(
                "utility",
                "UTILITY_TOPIC_ROAD_SAFETY",
                "utility_modes/TEACHING/topics/safety/ROAD_SAFETY.md",
                "utility_topic",
            ),
            _layer("age", "AGE_5", "ages/5/BASE.md"),
            _layer("language", "LANGUAGE_RU_AUDIENCE", "languages/ru/AUDIENCE.md", "audience_language"),
            _layer("language", "LANGUAGE_RU_RESULT", "languages/ru/RESULT.md", "result_language"),
            _layer(
                "substyle",
                "RUSSIAN_FOLK_TALE",
                "truth_modes/FAIRY_TALE/styles/folklore/RUSSIAN_FOLK_TALE.md",
            ),
            _layer(
                "entity",
                "FAIRY_TALE_ANIMAL_FOX",
                "truth_modes/FAIRY_TALE/characters/animals/FOX.md",
            ),
        ],
        fallback_layers=[
            PromptFallbackLayer(
                requested="лисица",
                fallback_layer_id="FAIRY_TALE_ANIMAL_FOX",
                source="truth_modes/FAIRY_TALE/characters/animals/FOX.md",
                reason="generic fox layer",
            )
        ],
        unresolved_details=[
            PromptUnresolvedDetail(
                label="любимый синий шарф",
                type="character_detail",
                instruction="Можно использовать как свободную деталь, без отдельного layer id.",
            )
        ],
        snapshot_hash="snapshot-1",
        source_hash="source-1",
        body_policy="metadata_only",
        version="wave-2",
    )


def _layer(
    type_: str,
    layer_id: str,
    source: str,
    role: str | None = None,
) -> PromptLayerRef:
    return PromptLayerRef(type=type_, id=layer_id, source=source, role=role)
