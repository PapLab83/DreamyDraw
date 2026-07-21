from __future__ import annotations

from pathlib import Path
from typing import Any

from src.core.graph import routing as r
from src.core.graph.stage1_2_builder import build_stage1_2_graph
from src.core.graph.state import to_graph_state
from src.core.prompts.composer import PromptComposer
from src.core.prompts.registry import PromptRegistry
from src.models.schemas import SessionRequest, SessionState
from src.storage.json_storage import JSONStorage
from tests.helpers.compliant_story_text import COMPLIANT_STORY_TEXT, compliant_story_text

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts" / "cultural_contexts" / "russian_folk"
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


def test_supported_request_runs_stage1_2_graph_to_approved_texts(tmp_path):
    graph, executor, storage = _graph(tmp_path)
    session = SessionState(
        request=SessionRequest(raw_text=SUPPORTED_REQUEST, current_config={"count": 2})
    )

    result = graph.invoke(to_graph_state(session), config=_config(session))["session"]

    assert [item.candidate_id for item in result.approved_texts] == ["c01", "c02"]
    assert result.completion_status == "completed_enough"
    assert result.shortage.status == "enough"
    assert storage.get_session(result.session_id).approved_texts
    assert executor.calls["refine_candidate"] == 1


def test_empty_request_pauses_with_durable_clarification_interrupt(tmp_path):
    graph, _, _ = _graph(tmp_path)
    session = SessionState(request=SessionRequest(raw_text=" ", current_config={"count": 2}))

    result = graph.invoke(to_graph_state(session), config=_config(session))["session"]

    assert result.completion_status == "waiting_user"
    assert result.pending_interrupt is not None
    assert result.pending_interrupt.status == "waiting"
    assert result.pending_interrupt.node == r.NODE_EMPTY_INPUT_INTERRUPT


def test_resume_from_clarification_continues_to_stage2(tmp_path):
    graph, _, _ = _graph(tmp_path)
    session = SessionState(request=SessionRequest(raw_text=" ", current_config={"count": 2}))
    paused = graph.invoke(to_graph_state(session), config=_config(session))["session"]

    state = to_graph_state(paused)
    state["user_input"] = {"freeform_text": SUPPORTED_REQUEST}
    result = graph.invoke(state, config=_config(paused))["session"]

    assert result.pending_interrupt is None
    assert result.approved_texts
    assert result.completion_status == "completed_enough"


def test_shortage_path_ends_as_completed_with_shortage(tmp_path):
    graph, _, _ = _graph(tmp_path, executor=ShortageExecutor(), candidate_count=2)
    session = SessionState(
        request=SessionRequest(raw_text=SUPPORTED_REQUEST, current_config={"count": 3})
    )

    result = graph.invoke(to_graph_state(session), config=_config(session))["session"]

    assert len(result.approved_texts) == 1
    assert result.shortage.status == "not_enough_valid_candidates"
    assert result.completion_status == "completed_with_shortage"
    assert result.completion_status != "completed_enough"


def test_shortage_hitl_placeholder_preserves_shortage_and_is_recoverable(tmp_path):
    graph, _, _ = _graph(
        tmp_path,
        executor=ShortageExecutor(),
        candidate_count=2,
        shortage_hitl_enabled=True,
    )
    session = SessionState(
        request=SessionRequest(raw_text=SUPPORTED_REQUEST, current_config={"count": 3})
    )

    result = graph.invoke(to_graph_state(session), config=_config(session))["session"]

    assert result.completion_status == "waiting_user"
    assert result.pending_interrupt is not None
    assert result.pending_interrupt.node == r.NODE_SHORTAGE_FALLBACK_INTERRUPT
    assert result.pending_interrupt.payload["shortage"]["status"] == "not_enough_valid_candidates"
    assert r.entry_point_from_session(to_graph_state(result)) == r.NODE_SHORTAGE_FALLBACK_INTERRUPT


def test_no_attempts_left_skips_refiner_and_continues_to_next_candidate(tmp_path):
    executor = NeedsRevisionFirstExecutor()
    graph, _, _ = _graph(tmp_path, executor=executor, candidate_count=2)
    session = SessionState(
        request=SessionRequest(raw_text=SUPPORTED_REQUEST, current_config={"count": 1})
    )
    session.validation_loop_state.max_refinement_attempts_per_candidate = 0

    result = graph.invoke(to_graph_state(session), config=_config(session))["session"]

    assert executor.calls["refine_candidate"] == 0
    assert [item.candidate_id for item in result.approved_texts] == ["c02"]


def test_graph_does_not_register_image_generation(tmp_path):
    graph, _, _ = _graph(tmp_path)

    assert r.NODE_IMAGE_GENERATION not in graph.get_graph().nodes


def _graph(
    tmp_path,
    executor: "FakePipelineExecutor | None" = None,
    candidate_count: int = 3,
    shortage_hitl_enabled: bool = False,
):
    registry = PromptRegistry.load(PROMPTS_ROOT)
    composer = PromptComposer(registry)
    storage = JSONStorage(str(tmp_path))
    executor = executor or FakePipelineExecutor()
    graph = build_stage1_2_graph(
        registry=registry,
        composer=composer,
        text_executor=executor,
        storage=storage,
        candidate_count=candidate_count,
        shortage_hitl_enabled=shortage_hitl_enabled,
    )
    return graph, executor, storage


def _config(session: SessionState) -> dict[str, Any]:
    return {"configurable": {"thread_id": session.session_id}}


class FakePipelineExecutor:
    def __init__(self) -> None:
        self.calls = {"refine_candidate": 0}

    def generate_candidates(self, runtime_context: dict[str, Any], count: int) -> list[dict[str, Any]]:
        base = [
            ("Лиса ждёт зелёный", COMPLIANT_STORY_TEXT),
            ("Лиса смотрит по сторонам", compliant_story_text(label="Второй текст требует правки")),
            ("Лиса ждёт зелёный", compliant_story_text(label="Дубликат первого текста")),
        ]
        return [
            {
                "theme": theme,
                "text": text,
                "questions": ["Что сделала лиса?"],
                "utility_points": ["остановиться", "посмотреть по сторонам"],
                "used_subjects": ["fox"],
            }
            for theme, text in base[:count]
        ]

    def deduplicate_topics(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        return []

    def score_candidates(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        scores = {"c01": 0.95, "c02": 0.90, "c03": 0.30}
        return [
            {
                "candidate_id": candidate["candidate_id"],
                "hard_gates": {gate: "pass" for gate in REQUIRED_GATES},
                "score_components": {"novelty": 0.8, "visual_potential": 0.8},
                "total_score": scores[candidate["candidate_id"]],
            }
            for candidate in runtime_context["candidate_texts"]
        ]

    def validate_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        if runtime_context["candidate_id"] == "c02" and runtime_context["version_id"] == "c02_v1":
            return {
                "status": "needs_revision",
                "summary": "too long",
                "issues": [{"type": "age_fit", "severity": "major", "description": "Слишком сложно."}],
                "required_fixes": ["Упростить фразы."],
            }
        return {"status": "accepted", "summary": "ok", "issues": [], "required_fixes": []}

    def refine_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        self.calls["refine_candidate"] += 1
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


class NeedsRevisionFirstExecutor(FakePipelineExecutor):
    def validate_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        if runtime_context["candidate_id"] == "c01":
            return {
                "status": "needs_revision",
                "summary": "needs work",
                "issues": [{"type": "age_fit", "severity": "major", "description": "Сложно."}],
                "required_fixes": ["Упростить."],
            }
        return {"status": "accepted", "summary": "ok", "issues": [], "required_fixes": []}
