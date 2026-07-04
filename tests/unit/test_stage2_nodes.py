from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from src.core.graph.state import to_graph_state
from src.core.nodes.stage2 import (
    active_candidate_text,
    advance_validation_cursor,
    approved_text_selector,
    candidate_refiner,
    candidate_text_generator,
    candidate_validator,
    has_validation_queue_exhausted,
    ranker,
    scorer,
    topic_deduplicator,
    _normalize_score,
)
from src.core.prompts.composer import PromptComposer
from src.core.prompts.registry import PromptRegistry
from src.models.schemas import (
    CandidateScore,
    CandidateText,
    ExecutionPromptContext,
    PromptLayerRef,
    RankedCandidate,
    RefinedCandidateVersion,
    SessionRequest,
    SessionState,
    Subject,
    ValidatedCandidateVersion,
    ValidationResult,
)

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"
REQUIRED_GATES = {
    "safety",
    "truth_fit",
    "age_fit",
    "utility_goal",
    "subject_continuity",
    "hard_details",
    "character_consistency",
}


def test_generator_writes_canonical_candidates_context_and_no_version_ids():
    registry, composer = _registry_composer()
    session = _stage1_ready_session(output_count=2)
    executor = FakeStage2TextExecutor()

    result = candidate_text_generator(
        to_graph_state(session),
        registry,
        composer,
        executor,
        candidate_count=3,
    )["session"]

    assert [candidate.candidate_id for candidate in result.candidate_texts] == ["c01", "c02", "c03"]
    assert all(candidate.status == "draft" for candidate in result.candidate_texts)
    assert all(not hasattr(candidate, "version_id") for candidate in result.candidate_texts)
    assert result.candidate_texts[0].used_subjects == ["fox"]
    assert result.candidate_texts[0].used_context.model_dump() == result.normalized_request.prompt_context.model_dump()
    assert result.pipeline_counters.generated_candidates == 3
    assert result.stage_status.candidate_text_generator.status == "completed"
    assert result.stage_prompt_context.entries[-1].stage == "candidate_text_generator"
    assert result.stage_prompt_context.entries[-1].body_policy == "include_bodies_runtime"
    runtime_context = executor.calls["generate_candidates"][0]["runtime_context"]
    assert "bodies" in runtime_context
    assert "FAIRY_TALE_BASE" in runtime_context["bodies"]
    assert "# Назначение слоя" in runtime_context["bodies"]["FAIRY_TALE_BASE"]
    assert "metadata_constraints" in runtime_context
    assert "FAIRY_TALE_BASE" in runtime_context["metadata_constraints"]


def test_generator_rewrites_noncanonical_executor_ids_to_canonical_ids():
    registry, composer = _registry_composer()
    session = _stage1_ready_session(output_count=2)
    executor = NoncanonicalIdExecutor()

    result = candidate_text_generator(
        to_graph_state(session),
        registry,
        composer,
        executor,
        candidate_count=2,
    )["session"]

    assert [candidate.candidate_id for candidate in result.candidate_texts] == ["c01", "c02"]


def test_generator_refuses_when_stage1_prompt_context_is_not_ready():
    registry, composer = _registry_composer()
    session = _stage1_ready_session(output_count=2)
    session.prompt_context.snapshot_hash = None

    with pytest.raises(ValueError, match="Stage 1"):
        candidate_text_generator(to_graph_state(session), registry, composer, FakeStage2TextExecutor())


def test_deduplicator_marks_exact_duplicate_themes_and_writes_one_result_per_candidate():
    registry, composer = _registry_composer()
    session = _stage1_ready_session()
    session.candidate_texts = [
        _candidate("c01", "Лиса ждёт зелёный"),
        _candidate("c02", " лиса   ждёт зелёный "),
        _candidate("c03", "Лиса смотрит налево"),
    ]

    result = topic_deduplicator(to_graph_state(session), registry, composer)["session"]

    assert [item.candidate_id for item in result.deduplication_results] == ["c01", "c02", "c03"]
    duplicate = next(item for item in result.deduplication_results if item.candidate_id == "c02")
    assert duplicate.is_duplicate is True
    assert duplicate.duplicate_of == "c01"
    assert result.pipeline_counters.deduplicated_candidates == 3
    assert result.stage_status.topic_deduplicator.status == "completed"


def test_deduplicator_executor_receives_candidate_payloads_for_semantic_decisions():
    registry, composer = _registry_composer()
    session = _stage1_ready_session()
    session.candidate_texts = [
        _candidate("c01", "Лиса ждёт зелёный"),
        _candidate("c02", "Лиса ждёт безопасный сигнал"),
    ]
    executor = FakeStage2TextExecutor()

    topic_deduplicator(to_graph_state(session), registry, composer, executor)

    runtime_context = executor.calls["deduplicate_topics"][0]["runtime_context"]
    assert runtime_context["candidate_themes"] == [
        "Лиса ждёт зелёный",
        "Лиса ждёт безопасный сигнал",
    ]
    assert runtime_context["candidate_texts"][0]["candidate_id"] == "c01"
    assert runtime_context["candidate_texts"][1]["text"] == "draft text c02"


def test_scorer_writes_required_hard_gates_and_numeric_components():
    registry, composer = _registry_composer()
    session = _stage1_ready_session()
    session.candidate_texts = [_candidate("c01", "Лиса ждёт зелёный"), _candidate("c02", "Повтор")]
    session.deduplication_results = []

    result = scorer(to_graph_state(session), registry, composer, FakeStage2TextExecutor())["session"]

    assert [score.candidate_id for score in result.scores] == ["c01", "c02"]
    assert set(result.scores[0].hard_gates) == REQUIRED_GATES
    assert isinstance(result.scores[0].total_score, float)
    assert all(isinstance(value, float) for value in result.scores[0].score_components.values())
    assert result.pipeline_counters.scored_candidates == 2
    assert result.stage_prompt_context.entries[-1].stage == "scorer"


def test_normalize_score_defaults_missing_hard_gate_to_unknown():
    score = _normalize_score(
        {"candidate_id": "c01", "hard_gates": {"safety": "pass"}},
        summary={"character_profile": None, "subjects": [{"is_character": True}]},
    )

    assert score.hard_gates["safety"] == "pass"
    assert score.hard_gates["truth_fit"] == "unknown"


def test_normalize_score_auto_passes_character_consistency_without_character():
    hard_gates = {gate: "pass" for gate in REQUIRED_GATES}
    hard_gates["character_consistency"] = "fail"
    score = _normalize_score(
        {"candidate_id": "c01", "hard_gates": hard_gates},
        summary={"character_profile": None, "subjects": [{"is_character": False}]},
    )

    assert score.hard_gates["character_consistency"] == "pass"


def test_ranker_orders_excludes_failed_gates_and_initializes_cursor_idempotently():
    session = _stage1_ready_session()
    session.scores = [
        _score("c01", total=0.70),
        _score("c02", total=0.95),
        _score("c03", total=0.99, gates={"safety": "fail"}),
    ]
    session.deduplication_results = []

    first = ranker(to_graph_state(session))["session"]
    first.validation_loop_state.active_candidate_id = "custom"
    first.validation_loop_state.active_version_id = "custom_v9"
    first.stage_status.validation_loop.status = "running"
    second = ranker(to_graph_state(first))["session"]

    assert [item.candidate_id for item in first.ranked_candidates] == ["c02", "c01"]
    assert [item.rank for item in first.ranked_candidates] == [1, 2]
    assert first.validation_loop_state.current_rank_index == 0
    assert first.validation_loop_state.active_candidate_id == "custom"
    assert first.validation_loop_state.active_version_id == "custom_v9"
    assert second.validation_loop_state.active_candidate_id == "custom"


def test_validator_reads_active_draft_version_and_writes_validated_version():
    registry, composer = _registry_composer()
    session = _session_with_ranked_candidates()
    session.validation_loop_state.active_candidate_id = "c01"
    session.validation_loop_state.active_version_id = "c01_v1"
    session.validation_loop_state.active_version_origin = "draft"
    session.validation_loop_state.active_text_source = "candidate_texts"
    executor = FakeStage2TextExecutor()

    result = candidate_validator(to_graph_state(session), registry, composer, executor)["session"]

    assert executor.calls["validate_candidate"][0]["runtime_context"]["candidate_id"] == "c01"
    assert executor.calls["validate_candidate"][0]["candidate_text"]["text"] == "draft text c01"
    assert result.validation_results[-1].status == "accepted"
    assert result.validated_candidate_versions[-1].candidate_id == "c01"
    assert result.validated_candidate_versions[-1].version_id == "c01_v1"
    assert result.validated_candidate_versions[-1].source == "candidate"
    assert result.validation_loop_state.candidate_attempts["c01"] == 1
    assert result.validation_loop_state.accepted_count == 1
    assert result.approved_texts == []


def test_validator_reads_active_refined_version_from_loop_state():
    registry, composer = _registry_composer()
    session = _session_with_ranked_candidates()
    session.refined_candidate_versions = [
        RefinedCandidateVersion(
            candidate_id="c01",
            version_id="c01_v2",
            source_version_id="c01_v1",
            theme="Refined theme",
            text="refined text c01",
            questions=["Почему лиса ждала?"],
        )
    ]
    session.validation_loop_state.active_candidate_id = "c01"
    session.validation_loop_state.active_version_id = "c01_v2"
    session.validation_loop_state.active_version_origin = "refined"
    session.validation_loop_state.active_text_source = "refined_candidate_versions"
    executor = FakeStage2TextExecutor()

    result = candidate_validator(to_graph_state(session), registry, composer, executor)["session"]

    assert executor.calls["validate_candidate"][0]["candidate_text"]["text"] == "refined text c01"
    assert result.validated_candidate_versions[-1].version_id == "c01_v2"
    assert result.validated_candidate_versions[-1].source == "refinement"


def test_refiner_writes_refined_versions_only_and_updates_active_cursor():
    registry, composer = _registry_composer()
    session = _session_with_ranked_candidates()
    session.validation_loop_state.active_candidate_id = "c02"
    session.validation_loop_state.active_version_id = "c02_v1"
    session.validation_loop_state.active_version_origin = "draft"
    session.validation_loop_state.active_text_source = "candidate_texts"
    session.validation_results = [
        ValidationResult(
            candidate_id="c02",
            version_id="c02_v1",
            status="needs_revision",
            required_fixes=["Сделать короче."],
        )
    ]
    before_text = session.candidate_texts[1].text

    result = candidate_refiner(to_graph_state(session), registry, composer, FakeStage2TextExecutor())["session"]

    assert result.candidate_texts[1].text == before_text
    assert result.refined_candidate_versions[-1].candidate_id == "c02"
    assert result.refined_candidate_versions[-1].version_id == "c02_v2"
    assert result.validation_loop_state.active_version_id == "c02_v2"
    assert result.validation_loop_state.active_version_origin == "refined"
    assert result.validation_loop_state.active_text_source == "refined_candidate_versions"
    assert result.validated_candidate_versions == []


def test_refiner_refuses_third_refinement_attempt_without_executor_call():
    registry, composer = _registry_composer()
    session = _session_with_ranked_candidates()
    session.validation_loop_state.active_candidate_id = "c01"
    session.validation_loop_state.active_version_id = "c01_v3"
    session.validation_loop_state.active_version_origin = "refined"
    session.validation_loop_state.active_text_source = "refined_candidate_versions"
    session.validation_loop_state.max_refinement_attempts_per_candidate = 2
    session.refined_candidate_versions = [
        RefinedCandidateVersion(candidate_id="c01", version_id="c01_v2", source_version_id="c01_v1", text="v2"),
        RefinedCandidateVersion(candidate_id="c01", version_id="c01_v3", source_version_id="c01_v2", text="v3"),
    ]
    session.validation_results = [
        ValidationResult(
            candidate_id="c01",
            version_id="c01_v3",
            status="needs_revision",
            required_fixes=["Ещё правка."],
        )
    ]
    executor = FakeStage2TextExecutor()

    with pytest.raises(ValueError, match="refinement attempt limit"):
        candidate_refiner(to_graph_state(session), registry, composer, executor)

    assert len(session.refined_candidate_versions) == 2
    assert executor.calls["refine_candidate"] == []


def test_selector_chooses_only_validated_candidate_versions():
    session = _stage1_ready_session(output_count=2)
    session.candidate_texts = [_candidate("c01", "Draft only")]
    session.ranked_candidates = [RankedCandidate(candidate_id="c01", rank=1, total_score=0.99, hard_gates_passed=True)]

    result = approved_text_selector(to_graph_state(session))["session"]

    assert result.approved_texts == []
    assert result.shortage.status == "not_enough_valid_candidates"
    assert result.completion_status == "completed_with_shortage"


def test_selector_does_not_choose_validated_versions_outside_ranked_queue():
    session = _stage1_ready_session(output_count=1)
    session.ranked_candidates = [
        RankedCandidate(candidate_id="c01", rank=1, total_score=0.99, hard_gates_passed=True)
    ]
    session.validated_candidate_versions = [_validated("c99", "c99_v1", "Unranked")]

    result = approved_text_selector(to_graph_state(session))["session"]

    assert result.approved_texts == []
    assert result.shortage.status == "not_enough_valid_candidates"
    assert result.completion_status == "completed_with_shortage"


def test_selector_does_not_choose_ranked_candidates_with_failed_hard_gates():
    session = _stage1_ready_session(output_count=1)
    session.ranked_candidates = [
        RankedCandidate(candidate_id="c01", rank=1, total_score=0.99, hard_gates_passed=False)
    ]
    session.validated_candidate_versions = [_validated("c01", "c01_v1", "Failed gates")]

    result = approved_text_selector(to_graph_state(session))["session"]

    assert result.approved_texts == []
    assert result.shortage.status == "not_enough_valid_candidates"
    assert result.completion_status == "completed_with_shortage"


def test_selector_writes_completed_enough_when_enough_accepted_versions_exist():
    session = _stage1_ready_session(output_count=2)
    session.ranked_candidates = [
        RankedCandidate(candidate_id="c02", rank=1, total_score=0.90, hard_gates_passed=True),
        RankedCandidate(candidate_id="c01", rank=2, total_score=0.80, hard_gates_passed=True),
    ]
    session.validated_candidate_versions = [
        _validated("c01", "c01_v1", "Theme 1"),
        _validated("c02", "c02_v1", "Theme 2"),
        _validated("c03", "c03_v1", "Theme 3"),
    ]

    result = approved_text_selector(to_graph_state(session))["session"]

    assert [item.candidate_id for item in result.approved_texts] == ["c02", "c01"]
    assert result.shortage.status == "enough"
    assert result.shortage.requested == 2
    assert result.shortage.approved == 2
    assert result.completion_status == "completed_enough"
    assert result.is_completed is True


def test_selector_writes_completed_with_shortage_when_not_enough_accepted_versions():
    session = _stage1_ready_session(output_count=2)
    session.ranked_candidates = [RankedCandidate(candidate_id="c01", rank=1, total_score=0.80, hard_gates_passed=True)]
    session.validated_candidate_versions = [_validated("c01", "c01_v1", "Theme 1")]

    result = approved_text_selector(to_graph_state(session))["session"]

    assert len(result.approved_texts) == 1
    assert result.shortage.status == "not_enough_valid_candidates"
    assert result.shortage.requested == 2
    assert result.shortage.approved == 1
    assert result.completion_status == "completed_with_shortage"
    assert result.is_completed is True


def test_full_prompt_bodies_are_absent_from_stage_prompt_entries():
    registry, composer = _registry_composer()
    session = _stage1_ready_session()
    executor = FakeStage2TextExecutor()

    session = candidate_text_generator(to_graph_state(session), registry, composer, executor, candidate_count=2)["session"]
    session = topic_deduplicator(to_graph_state(session), registry, composer, executor)["session"]
    session = scorer(to_graph_state(session), registry, composer, executor)["session"]

    serialized = str([entry.model_dump() for entry in session.stage_prompt_context.entries])
    assert "# Назначение" not in serialized
    assert "Не изображать животных говорящими" not in serialized
    policies = {entry.stage: entry.body_policy for entry in session.stage_prompt_context.entries}
    assert policies["candidate_text_generator"] == "include_bodies_runtime"
    assert policies["topic_deduplicator"] == "lazy_not_persisted"
    assert policies["scorer"] == "include_bodies_runtime"


def test_validation_cursor_helpers_are_deterministic():
    session = _session_with_ranked_candidates()

    assert active_candidate_text(session).candidate_id == "c01"
    assert has_validation_queue_exhausted(session) is False

    advance_validation_cursor(session)

    assert session.validation_loop_state.current_rank_index == 1
    assert session.validation_loop_state.active_candidate_id == "c02"
    assert session.validation_loop_state.active_version_id == "c02_v1"

    advance_validation_cursor(session)

    assert has_validation_queue_exhausted(session) is True
    assert session.validation_loop_state.active_candidate_id is None
    assert session.stage_status.validation_loop.status == "completed"


def test_validation_cursor_stops_when_output_count_is_already_accepted():
    session = _session_with_ranked_candidates()
    session.normalized_request.output_count = 1
    session.validation_loop_state.accepted_count = 1
    session.validation_loop_state.selector_eligible_unique_accepted_count = 1
    session.validated_candidate_versions = [_validated("c01", "c01_v1", "Theme 1")]

    advance_validation_cursor(session)

    assert session.validation_loop_state.active_candidate_id is None
    assert session.validation_loop_state.active_version_id is None
    assert session.stage_status.validation_loop.status == "completed"
    assert has_validation_queue_exhausted(session) is True


def test_validation_cursor_does_not_stop_on_duplicate_theme_accepted_versions():
    session = _stage1_ready_session(output_count=2)
    session.ranked_candidates = [
        RankedCandidate(candidate_id="c01", rank=1, total_score=0.9, hard_gates_passed=True),
        RankedCandidate(candidate_id="c02", rank=2, total_score=0.8, hard_gates_passed=True),
        RankedCandidate(candidate_id="c03", rank=3, total_score=0.7, hard_gates_passed=True),
    ]
    session.validation_loop_state.current_rank_index = 1
    session.validation_loop_state.active_candidate_id = "c02"
    session.validation_loop_state.active_version_id = "c02_v1"
    session.validation_loop_state.active_version_origin = "draft"
    session.validation_loop_state.active_text_source = "candidate_texts"
    session.validation_loop_state.accepted_count = 2
    session.validation_loop_state.selector_eligible_unique_accepted_count = 2
    session.validated_candidate_versions = [
        _validated("c01", "c01_v1", "Same theme"),
        _validated("c02", "c02_v1", " same   theme "),
    ]

    advance_validation_cursor(session)

    assert session.validation_loop_state.selector_eligible_unique_accepted_count == 1
    assert session.validation_loop_state.current_rank_index == 2
    assert session.validation_loop_state.active_candidate_id == "c03"
    assert session.validation_loop_state.active_version_id == "c03_v1"
    assert session.stage_status.validation_loop.status == "running"


class FakeStage2TextExecutor:
    def __init__(self) -> None:
        self.calls: dict[str, list[dict[str, Any]]] = {
            "generate_candidates": [],
            "deduplicate_topics": [],
            "score_candidates": [],
            "validate_candidate": [],
            "refine_candidate": [],
        }

    def generate_candidates(self, runtime_context: dict[str, Any], count: int) -> list[dict[str, Any]]:
        self.calls["generate_candidates"].append({"runtime_context": runtime_context, "count": count})
        return [
            {
                "theme": f"Тема {index}",
                "text": f"draft text c{index:02d}",
                "questions": [f"Вопрос {index}?"],
                "utility_points": ["ждать зелёный"],
                "used_subjects": ["fox"],
                "expected_visual_idea": "Лиса у перехода",
            }
            for index in range(1, count + 1)
        ]

    def deduplicate_topics(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls["deduplicate_topics"].append({"runtime_context": runtime_context})
        return []

    def score_candidates(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls["score_candidates"].append({"runtime_context": runtime_context})
        return [
            {
                "candidate_id": candidate["candidate_id"],
                "hard_gates": {gate: "pass" for gate in REQUIRED_GATES},
                "score_components": {
                    "child_interest": 0.8,
                    "age_fit": 0.9,
                    "utility_fit": 0.9,
                    "style_fit": 0.8,
                    "novelty": 0.7,
                    "visual_potential": 0.8,
                },
                "total_score": 0.82,
            }
            for candidate in runtime_context["candidate_texts"]
        ]

    def validate_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        self.calls["validate_candidate"].append(
            {
                "runtime_context": runtime_context,
                "candidate_text": runtime_context["candidate_text"],
            }
        )
        return {"status": "accepted", "summary": "ok", "issues": [], "required_fixes": []}

    def refine_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        self.calls["refine_candidate"].append({"runtime_context": runtime_context})
        candidate = runtime_context["candidate_text"]
        return {
            "theme": candidate["theme"],
            "text": f"{candidate['text']} refined",
            "questions": candidate.get("questions", []),
            "changes_summary": "shortened",
        }


class NoncanonicalIdExecutor(FakeStage2TextExecutor):
    def generate_candidates(self, runtime_context: dict[str, Any], count: int) -> list[dict[str, Any]]:
        self.calls["generate_candidates"].append({"runtime_context": runtime_context, "count": count})
        return [
            {
                "candidate_id": "idea-alpha",
                "theme": "Тема alpha",
                "text": "draft text alpha",
                "questions": ["Вопрос alpha?"],
                "utility_points": ["ждать зелёный"],
                "used_subjects": ["fox"],
                "expected_visual_idea": "Лиса у перехода",
            },
            {
                "candidate_id": "idea-beta",
                "theme": "Тема beta",
                "text": "draft text beta",
                "questions": ["Вопрос beta?"],
                "utility_points": ["ждать зелёный"],
                "used_subjects": ["fox"],
                "expected_visual_idea": "Лиса у перехода",
            },
        ][:count]


def _registry_composer() -> tuple[PromptRegistry, PromptComposer]:
    registry = PromptRegistry.load(PROMPTS_ROOT)
    return registry, PromptComposer(registry)


def _stage1_ready_session(output_count: int = 2) -> SessionState:
    session = SessionState(request=SessionRequest(raw_text="Сказка про лису"))
    session.normalized_request.output_count = output_count
    session.normalized_request.truth_mode = "FAIRY_TALE"
    session.normalized_request.utility_mode = "TEACHING"
    session.normalized_request.utility_topic = "ROAD_SAFETY"
    session.normalized_request.target_age = "5"
    session.normalized_request.main_subject = "fox"
    session.normalized_request.subjects = [
        Subject(id="fox", label="лиса", type="animal", role="main", is_character=True)
    ]
    prompt_context = _prompt_context()
    session.normalized_request.prompt_context.resolved_layers = list(prompt_context.resolved_layers)
    session.prompt_context = prompt_context
    session.interpretation_state.execution_lookup_result.status = "pass"
    session.preview_state.shown_to_user = True
    return session


def _prompt_context() -> ExecutionPromptContext:
    return ExecutionPromptContext(
        resolved_layers=[
            PromptLayerRef(id="CONTENT_FORMAT_STORY", type="format", role="content_format", source="prompts/content_formats/story/BASE.md"),
            PromptLayerRef(id="FAIRY_TALE_BASE", type="truth_mode", source="prompts/truth_modes/FAIRY_TALE/BASE.md"),
            PromptLayerRef(id="UTILITY_TEACHING_BASE", type="utility", role="utility_mode", source="prompts/utility_modes/TEACHING/BASE.md"),
            PromptLayerRef(id="UTILITY_TOPIC_ROAD_SAFETY", type="utility", role="utility_topic", source="prompts/utility_modes/TEACHING/topics/safety/ROAD_SAFETY.md"),
            PromptLayerRef(id="AGE_5", type="age", source="prompts/ages/5/BASE.md"),
            PromptLayerRef(id="LANGUAGE_RU_AUDIENCE", type="language", role="audience_language", source="prompts/languages/ru/AUDIENCE.md"),
            PromptLayerRef(id="LANGUAGE_RU_RESULT", type="language", role="result_language", source="prompts/languages/ru/RESULT.md"),
            PromptLayerRef(id="FAIRY_TALE_ANIMAL_FOX", type="entity", source="prompts/truth_modes/FAIRY_TALE/characters/animals/FOX.md"),
        ],
        snapshot_hash="stage1-ready-hash",
        body_policy="metadata_only",
        version="test",
    )


def _candidate(candidate_id: str, theme: str) -> CandidateText:
    return CandidateText(
        candidate_id=candidate_id,
        theme=theme,
        text=f"draft text {candidate_id}",
        questions=["Что запомнила лиса?"],
        used_subjects=["fox"],
        utility_points=["ждать зелёный"],
        expected_visual_idea="Лиса у перехода",
    )


def _score(candidate_id: str, total: float, gates: dict[str, str] | None = None) -> CandidateScore:
    hard_gates = {gate: "pass" for gate in REQUIRED_GATES}
    hard_gates.update(gates or {})
    return CandidateScore(
        candidate_id=candidate_id,
        hard_gates=hard_gates,
        score_components={"novelty": total, "visual_potential": total},
        total_score=total,
    )


def _session_with_ranked_candidates() -> SessionState:
    session = _stage1_ready_session(output_count=2)
    session.candidate_texts = [_candidate("c01", "Theme 1"), _candidate("c02", "Theme 2")]
    session.ranked_candidates = [
        RankedCandidate(candidate_id="c01", rank=1, total_score=0.9, hard_gates_passed=True),
        RankedCandidate(candidate_id="c02", rank=2, total_score=0.8, hard_gates_passed=True),
    ]
    session.validation_loop_state.current_rank_index = 0
    session.validation_loop_state.active_candidate_id = "c01"
    session.validation_loop_state.active_version_id = "c01_v1"
    session.validation_loop_state.active_version_origin = "draft"
    session.validation_loop_state.active_text_source = "candidate_texts"
    session.stage_status.validation_loop.status = "running"
    return session


def _validated(candidate_id: str, version_id: str, theme: str) -> ValidatedCandidateVersion:
    return ValidatedCandidateVersion(
        candidate_id=candidate_id,
        version_id=version_id,
        theme=theme,
        text=f"approved text {candidate_id}",
        questions=["Что правильно сделал герой?"],
        validation_status="accepted",
        validation_summary="ok",
    )
