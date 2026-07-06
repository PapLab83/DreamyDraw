from __future__ import annotations

from pathlib import Path
from typing import Any

from src.core.graph.state import to_graph_state
from src.core.nodes.stage2 import (
    advance_validation_cursor,
    approved_text_selector,
    candidate_refiner,
    candidate_text_generator,
    candidate_validator,
    ranker,
    scorer,
    topic_deduplicator,
)
from src.core.prompts.composer import PromptComposer
from src.core.prompts.registry import PromptRegistry
from src.core.stage1_runner import Stage1Runner
from src.models.schemas import SessionState
from src.storage.json_storage import JSONStorage
from tests.helpers.compliant_story_text import COMPLIANT_STORY_TEXT, compliant_story_text

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"
SUPPORTED_REQUEST = "Сделай сказку про лису для 5 лет и научи безопасности на дороге"
REQUIRED_GATES = {
    "safety",
    "truth_fit",
    "age_fit",
    "utility_goal",
    "subject_continuity",
    "hard_details",
    "character_consistency",
}


def test_stage1_runner_plus_stage2_chain_produces_approved_texts(tmp_path):
    registry = PromptRegistry.load(PROMPTS_ROOT)
    composer = PromptComposer(registry)
    stage1 = Stage1Runner(
        storage=JSONStorage(str(tmp_path)),
        prompts_root=PROMPTS_ROOT,
        registry=registry,
        composer=composer,
    ).start(SUPPORTED_REQUEST, current_config={"count": 2})
    executor = FakePipelineExecutor()

    session = _run_until_selector_ready(stage1.session, registry, composer, executor)
    session = approved_text_selector(to_graph_state(session))["session"]

    assert stage1.is_stage1_ready is True
    assert [item.candidate_id for item in session.approved_texts] == ["c01", "c02"]
    assert session.completion_status == "completed_enough"
    assert session.shortage.status == "enough"
    assert session.pipeline_counters.approved_texts == 2


def test_revision_candidate_flows_validator_refiner_validator_then_selector(tmp_path):
    registry = PromptRegistry.load(PROMPTS_ROOT)
    composer = PromptComposer(registry)
    session = Stage1Runner(
        storage=JSONStorage(str(tmp_path)),
        prompts_root=PROMPTS_ROOT,
        registry=registry,
        composer=composer,
    ).start(SUPPORTED_REQUEST, current_config={"count": 2}).session
    executor = FakePipelineExecutor()

    session = candidate_text_generator(to_graph_state(session), registry, composer, executor, candidate_count=3)["session"]
    session = topic_deduplicator(to_graph_state(session), registry, composer, executor)["session"]
    session = scorer(to_graph_state(session), registry, composer, executor)["session"]
    session = ranker(to_graph_state(session))["session"]

    session = candidate_validator(to_graph_state(session), registry, composer, executor)["session"]
    advance_validation_cursor(session)
    session = candidate_validator(to_graph_state(session), registry, composer, executor)["session"]
    assert session.validation_results[-1].status == "needs_revision"
    session = candidate_refiner(to_graph_state(session), registry, composer, executor)["session"]
    session = candidate_validator(to_graph_state(session), registry, composer, executor)["session"]
    session = approved_text_selector(to_graph_state(session))["session"]

    assert ("c02", "c02_v2") in {
        (item.candidate_id, item.version_id) for item in session.validated_candidate_versions
    }
    assert any(item.candidate_id == "c02" and item.version_id == "c02_v2" for item in session.approved_texts)
    assert session.validated_candidate_versions[-1].source == "refinement"
    assert session.completion_status == "completed_enough"


def test_shortage_path_completes_with_explicit_shortage_without_interrupt(tmp_path):
    registry = PromptRegistry.load(PROMPTS_ROOT)
    composer = PromptComposer(registry)
    session = Stage1Runner(
        storage=JSONStorage(str(tmp_path)),
        prompts_root=PROMPTS_ROOT,
        registry=registry,
        composer=composer,
    ).start(SUPPORTED_REQUEST, current_config={"count": 3}).session
    executor = ShortageExecutor()

    session = _run_until_selector_ready(session, registry, composer, executor, candidate_count=2)
    session = approved_text_selector(to_graph_state(session))["session"]

    assert len(session.approved_texts) == 1
    assert session.shortage.status == "not_enough_valid_candidates"
    assert session.shortage.requested == 3
    assert session.shortage.approved == 1
    assert session.completion_status == "completed_with_shortage"
    assert session.pending_interrupt is None
    assert session.is_completed is True


def test_stage2_does_not_mutate_stage1_prompt_layer_decisions(tmp_path):
    registry = PromptRegistry.load(PROMPTS_ROOT)
    composer = PromptComposer(registry)
    session = Stage1Runner(
        storage=JSONStorage(str(tmp_path)),
        prompts_root=PROMPTS_ROOT,
        registry=registry,
        composer=composer,
    ).start(SUPPORTED_REQUEST, current_config={"count": 2}).session
    normalized_prompt_before = session.normalized_request.prompt_context.model_dump()
    execution_prompt_before = session.prompt_context.model_dump()

    session = _run_until_selector_ready(session, registry, composer, FakePipelineExecutor())
    session = approved_text_selector(to_graph_state(session))["session"]

    assert session.normalized_request.prompt_context.model_dump() == normalized_prompt_before
    assert session.prompt_context.model_dump() == execution_prompt_before


def _run_until_selector_ready(
    session: SessionState,
    registry: PromptRegistry,
    composer: PromptComposer,
    executor: "FakePipelineExecutor",
    candidate_count: int = 3,
) -> SessionState:
    session = candidate_text_generator(to_graph_state(session), registry, composer, executor, candidate_count=candidate_count)["session"]
    session = topic_deduplicator(to_graph_state(session), registry, composer, executor)["session"]
    session = scorer(to_graph_state(session), registry, composer, executor)["session"]
    session = ranker(to_graph_state(session))["session"]
    while not session.stage_status.validation_loop.status == "completed":
        session = candidate_validator(to_graph_state(session), registry, composer, executor)["session"]
        latest = session.validation_results[-1]
        if latest.status == "needs_revision":
            session = candidate_refiner(to_graph_state(session), registry, composer, executor)["session"]
            continue
        advance_validation_cursor(session)
    return session


class FakePipelineExecutor:
    def generate_candidates(self, runtime_context: dict[str, Any], count: int) -> list[dict[str, Any]]:
        base = [
            ("c01", "Лиса ждёт зелёный", COMPLIANT_STORY_TEXT),
            ("c02", "Лиса смотрит по сторонам", compliant_story_text(label="Второй текст требует правки")),
            ("c03", "Лиса ждёт зелёный", compliant_story_text(label="Дубликат первого текста")),
        ]
        return [
            {
                "candidate_id": candidate_id,
                "theme": theme,
                "text": text,
                "questions": ["Что сделала лиса?"],
                "utility_points": ["остановиться", "посмотреть по сторонам"],
                "used_subjects": ["fox"],
                "expected_visual_idea": "Лиса рядом с переходом",
            }
            for candidate_id, theme, text in base[:count]
        ]

    def deduplicate_topics(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    def score_candidates(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        scores = {"c01": 0.95, "c02": 0.90, "c03": 0.30}
        return [
            {
                "candidate_id": candidate["candidate_id"],
                "hard_gates": {gate: "pass" for gate in REQUIRED_GATES},
                "score_components": {
                    "child_interest": scores[candidate["candidate_id"]],
                    "age_fit": 0.9,
                    "utility_fit": 0.9,
                    "style_fit": 0.9,
                    "novelty": 0.8,
                    "visual_potential": 0.8,
                },
                "total_score": scores[candidate["candidate_id"]],
            }
            for candidate in runtime_context["candidate_texts"]
        ]

    def validate_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        candidate_id = runtime_context["candidate_id"]
        version_id = runtime_context["version_id"]
        if candidate_id == "c02" and version_id == "c02_v1":
            return {
                "status": "needs_revision",
                "summary": "too long",
                "issues": [{"type": "age_fit", "severity": "major", "description": "Слишком сложно."}],
                "required_fixes": ["Упростить фразы."],
            }
        return {"status": "accepted", "summary": "ok", "issues": [], "required_fixes": []}

    def refine_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        candidate = runtime_context["candidate_text"]
        return {
            "theme": candidate["theme"],
            "text": COMPLIANT_STORY_TEXT,
            "questions": candidate.get("questions", []),
            "changes_summary": "Упростили фразы.",
        }


class ShortageExecutor(FakePipelineExecutor):
    def score_candidates(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "candidate_id": candidate["candidate_id"],
                "hard_gates": {
                    gate: ("fail" if candidate["candidate_id"] == "c02" and gate == "safety" else "pass")
                    for gate in REQUIRED_GATES
                },
                "score_components": {"novelty": 0.5, "visual_potential": 0.5},
                "total_score": 0.5,
            }
            for candidate in runtime_context["candidate_texts"]
        ]
