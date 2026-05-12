"""Тесты нод planning.py."""

import json

from src.core.graph.state import to_graph_state
from src.core.nodes.planning import (
    make_idea_sampler,
    make_idea_scoring,
    make_score_normalize,
    make_series_planner,
)
from src.models.schemas import Idea
from tests.conftest import (
    ScriptedLLM,
    make_session,
    planner_ok,
    scoring_ok,
)


class TestSeriesPlanner:
    def test_generates_pool(self, tmp_storage, prompt_builder):
        llm = ScriptedLLM([planner_ok(count=2)])
        node = make_series_planner(llm, tmp_storage, prompt_builder)
        session = make_session(count=2)
        session.current_node = "config_passed"
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "ideas_generated"
        assert len(result["session"].ideas_pool) == 4
        assert "Рыжик" in result["session"].global_context

    def test_empty_pool_fails(self, tmp_storage, prompt_builder):
        llm = ScriptedLLM(['{"global_context": "x", "ideas": []}'])
        node = make_series_planner(llm, tmp_storage, prompt_builder)
        session = make_session(count=2)
        session.current_node = "config_passed"
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "failed"


class TestIdeaScoring:
    def test_filters_low_scores(self, tmp_storage, prompt_builder):
        scoring_json = json.dumps({
            "scores": [
                {"index": 0, "child_index": 0.9},
                {"index": 1, "child_index": 0.8},
                {"index": 2, "child_index": 0.7},
                {"index": 3, "child_index": 0.1},  # отсеется
            ]
        })
        llm = ScriptedLLM([scoring_json])
        node = make_idea_scoring(llm, tmp_storage, prompt_builder)
        session = make_session(count=2)
        session.ideas_pool = [Idea(title=f"Т{i}", summary=f"С{i}") for i in range(4)]
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "ideas_scored"
        assert len(result["session"].ideas_pool) == 3

    def test_fallback_when_all_filtered(self, tmp_storage, prompt_builder):
        scoring_json = json.dumps({"scores": [{"index": 0, "child_index": 0.05}]})
        llm = ScriptedLLM([scoring_json])
        node = make_idea_scoring(llm, tmp_storage, prompt_builder)
        session = make_session(count=1)
        session.ideas_pool = [Idea(title="Плохая", summary="идея")]
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        # Должен быть fallback на дефолтную идею
        assert len(result["session"].ideas_pool) == 1
        assert result["session"].ideas_pool[0].title == "Прогулка в лесу"


class TestScoreNormalize:
    def test_weights_sum_to_one(self, tmp_storage):
        node = make_score_normalize(tmp_storage)
        session = make_session()
        session.ideas_pool = [
            Idea(title="A", summary="a", child_index=0.9),
            Idea(title="B", summary="b", child_index=0.5),
            Idea(title="C", summary="c", child_index=0.3),
        ]
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "scores_normalized"
        total = sum(it.normalized_weight for it in result["session"].ideas_pool)
        assert abs(total - 1.0) < 1e-9

    def test_higher_score_higher_weight(self, tmp_storage):
        node = make_score_normalize(tmp_storage)
        session = make_session()
        session.ideas_pool = [
            Idea(title="A", summary="a", child_index=0.9),
            Idea(title="B", summary="b", child_index=0.5),
            Idea(title="C", summary="c", child_index=0.3),
        ]
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        weights = [it.normalized_weight for it in result["session"].ideas_pool]
        assert weights[0] > weights[1] > weights[2]


class TestIdeaSampler:
    def test_picks_count_unique(self, tmp_storage):
        node = make_idea_sampler(tmp_storage)
        session = make_session(count=2)
        session.ideas_pool = [
            Idea(title=f"Т{i}", summary=f"С{i}", normalized_weight=0.2)
            for i in range(5)
        ]
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "series_planned"
        assert len(result["session"].series_plan) == 2
        assert len(set(result["session"].series_plan)) == 2
        # revision_history заполнен от planner
        assert "0" in result["session"].revision_history

    def test_count_larger_than_pool(self, tmp_storage):
        node = make_idea_sampler(tmp_storage)
        session = make_session(count=10)
        session.ideas_pool = [
            Idea(title=f"Т{i}", summary=f"С{i}", normalized_weight=0.33)
            for i in range(3)
        ]
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert len(result["session"].series_plan) == 3

    def test_empty_pool_fails(self, tmp_storage):
        node = make_idea_sampler(tmp_storage)
        session = make_session()
        session.ideas_pool = []
        tmp_storage.save_session(session)

        result = node(to_graph_state(session))
        assert result["session"].current_node == "failed"