from pathlib import Path

from src.core.graph import routing as r
from src.core.graph.stage1_2_builder import build_stage1_2_graph
from src.core.graph.state import to_graph_state
from src.core.nodes.stage1 import (
    candidate_layer_resolution,
    final_parameter_validation,
    input_analysis,
    metadata_lookup,
    preview,
    prompt_context_preparation,
    request_classification,
)
from src.core.nodes.stage2 import candidate_text_generator, candidate_validator, ranker, scorer, topic_deduplicator
from src.core.prompts.composer import PromptComposer
from src.core.prompts.registry import PromptRegistry
from src.models.schemas import SessionRequest, SessionState
from src.storage.json_storage import JSONStorage
from tests.integration.test_stage1_2_graph import FakePipelineExecutor, SUPPORTED_REQUEST

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"


def test_json_storage_recovery_resumes_after_candidate_generation(tmp_path):
    registry, composer, storage, executor = _deps(tmp_path)
    session = _stage1_ready_session(registry, composer)
    session = candidate_text_generator(to_graph_state(session), registry, composer, executor, candidate_count=3)["session"]
    storage.save_session(session)

    reloaded = JSONStorage(str(tmp_path)).get_session(session.session_id)
    assert r.entry_point_from_session(to_graph_state(reloaded)) == r.NODE_TOPIC_DEDUPLICATOR

    graph = build_stage1_2_graph(
        registry=registry,
        composer=composer,
        text_executor=executor,
        storage=JSONStorage(str(tmp_path)),
        candidate_count=3,
    )
    result = graph.invoke(to_graph_state(reloaded), config={"configurable": {"thread_id": session.session_id}})["session"]

    assert result.approved_texts
    assert result.completion_status == "completed_enough"


def test_json_storage_recovery_resumes_during_validation_loop(tmp_path):
    registry, composer, storage, executor = _deps(tmp_path)
    session = _stage1_ready_session(registry, composer)
    session = candidate_text_generator(to_graph_state(session), registry, composer, executor, candidate_count=3)["session"]
    session = topic_deduplicator(to_graph_state(session), registry, composer, executor)["session"]
    session = scorer(to_graph_state(session), registry, composer, executor)["session"]
    session = ranker(to_graph_state(session))["session"]
    storage.save_session(session)

    reloaded = JSONStorage(str(tmp_path)).get_session(session.session_id)
    assert r.entry_point_from_session(to_graph_state(reloaded)) == r.NODE_CANDIDATE_VALIDATOR

    graph = build_stage1_2_graph(
        registry=registry,
        composer=composer,
        text_executor=executor,
        storage=JSONStorage(str(tmp_path)),
        candidate_count=3,
    )
    result = graph.invoke(to_graph_state(reloaded), config={"configurable": {"thread_id": session.session_id}})["session"]

    assert [item.candidate_id for item in result.approved_texts] == ["c01", "c02"]
    assert result.stage_status.validation_loop.status == "completed"


def test_json_storage_recovery_after_validator_result_resumes_routing_step(tmp_path):
    registry, composer, storage, executor = _deps(tmp_path)
    session = _stage1_ready_session(registry, composer)
    session = candidate_text_generator(to_graph_state(session), registry, composer, executor, candidate_count=3)["session"]
    session = topic_deduplicator(to_graph_state(session), registry, composer, executor)["session"]
    session = scorer(to_graph_state(session), registry, composer, executor)["session"]
    session = ranker(to_graph_state(session))["session"]
    session.validation_loop_state.current_rank_index = 1
    session.validation_loop_state.active_candidate_id = "c02"
    session.validation_loop_state.active_version_id = "c02_v1"
    session.validation_loop_state.active_version_origin = "draft"
    session.validation_loop_state.active_text_source = "candidate_texts"
    session = candidate_validator(to_graph_state(session), registry, composer, executor)["session"]
    storage.save_session(session)

    reloaded = JSONStorage(str(tmp_path)).get_session(session.session_id)
    assert r.entry_point_from_session(to_graph_state(reloaded)) == r.NODE_CANDIDATE_REFINER

    graph = build_stage1_2_graph(
        registry=registry,
        composer=composer,
        text_executor=executor,
        storage=JSONStorage(str(tmp_path)),
        candidate_count=3,
    )
    result = graph.invoke(to_graph_state(reloaded), config={"configurable": {"thread_id": session.session_id}})["session"]

    assert [
        validation.version_id
        for validation in result.validation_results
        if validation.candidate_id == "c02"
    ].count("c02_v1") == 1
    assert any(
        validation.candidate_id == "c02" and validation.version_id == "c02_v2"
        for validation in result.validation_results
    )
    assert any(version.candidate_id == "c02" and version.version_id == "c02_v2" for version in result.refined_candidate_versions)
    assert result.approved_texts


def _deps(tmp_path):
    registry = PromptRegistry.load(PROMPTS_ROOT)
    composer = PromptComposer(registry)
    storage = JSONStorage(str(tmp_path))
    return registry, composer, storage, FakePipelineExecutor()


def _stage1_ready_session(registry, composer):
    session = SessionState(
        request=SessionRequest(raw_text=SUPPORTED_REQUEST, current_config={"count": 2})
    )
    state = to_graph_state(session)
    state = input_analysis(state)
    state = metadata_lookup(state, registry)
    state = request_classification(state)
    state = candidate_layer_resolution(state, registry)
    state = final_parameter_validation(state, registry)
    state = preview(state)
    state = prompt_context_preparation(state, registry, composer)
    return state["session"]
