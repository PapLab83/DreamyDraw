from __future__ import annotations

import json
import os
import subprocess
import sys

from src.core.factory import build_stage2_text_executor
from src.core.stage1_2_orchestrator import Stage1_2Orchestrator
from src.core.stage2_llm_executor import REQUIRED_HARD_GATES
from src.providers.base import BaseLLMProvider
from src.storage.json_storage import JSONStorage

SCRIPT = "scripts/run_stage1_2_mvp.py"
REQUEST = "Сделай 2 сказки про лису для 5 лет."

_COMPLIANT_FOX_STORY_1 = (
    "Лиса увидела звезду. "
    "Она загадала доброе желание. "
    "Потом пошла домой."
)
_COMPLIANT_FOX_STORY_2 = (
    "Лиса слушала ручей. "
    "Она помогла другу перейти по камням. "
    "Все обрадовались."
)


class ScriptedLLMProvider(BaseLLMProvider):
    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.model = "initial-model"

    def generate_text(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            return json.dumps(
                {
                    "candidates": [
                        {"theme": "Лиса и звезда", "text": _COMPLIANT_FOX_STORY_1, "questions": ["Что увидела лиса?"]},
                        {"theme": "Лиса и ручей", "text": _COMPLIANT_FOX_STORY_2, "questions": ["Кому помогла лиса?"]},
                    ]
                }
            )
        if len(self.prompts) == 2:
            return json.dumps({"decisions": []})
        if len(self.prompts) == 3:
            return json.dumps(
                {
                    "scores": [
                        {
                            "candidate_id": candidate_id,
                            "hard_gates": {gate: "pass" for gate in REQUIRED_HARD_GATES},
                            "score_components": {"novelty": 0.8, "visual_potential": 0.7},
                            "total_score": score,
                        }
                        for candidate_id, score in [("c01", 0.9), ("c02", 0.85)]
                    ]
                }
            )
        return json.dumps({"status": "accepted", "summary": "ok", "issues": [], "required_fixes": []})

    def generate_questions(self, text: str) -> list[str]:
        raise AssertionError("Stage 1-2 LLM path must not call generate_questions")


def test_default_cli_uses_mock_and_does_not_require_provider_env(tmp_path) -> None:
    result = _run_cli(tmp_path, REQUEST, "--count", "2")

    assert result.returncode == 0
    assert "approved_texts:" in result.stdout
    assert "gptunnel" not in result.stdout.casefold()
    assert "provider" not in result.stdout.casefold()


def test_llm_cli_with_missing_api_key_exits_before_running_graph(tmp_path) -> None:
    result = _run_cli(tmp_path, REQUEST, "--count", "2", "--executor", "llm", extra_env={"GPTTUNNEL_API_KEY": ""})

    assert result.returncode != 0
    assert "GPTTUNNEL_API_KEY" in result.stderr
    assert "session_id:" not in result.stdout


def test_factory_builds_llm_executor_from_scripted_provider_without_image_provider() -> None:
    provider = ScriptedLLMProvider()
    executor = build_stage2_text_executor(executor_type="llm", llm_provider=provider, model_name="scripted")

    assert executor.generate_candidates(_runtime_context(), 1)[0]["theme"] == "Лиса и звезда"
    assert len(provider.prompts) == 1
    assert provider.model == "scripted"


def test_stage1_2_graph_reaches_approved_texts_with_scripted_llm_provider(tmp_path) -> None:
    provider = ScriptedLLMProvider()
    executor = build_stage2_text_executor(executor_type="llm", llm_provider=provider, model_name="scripted")
    orchestrator = Stage1_2Orchestrator(
        storage=JSONStorage(tmp_path),
        text_executor=executor,
        candidate_count=2,
    )
    session = orchestrator.start_session(REQUEST, current_config={"count": 2})

    result = orchestrator.run_pipeline(session.session_id)

    assert result.is_done
    assert len(result.session.approved_texts) == 2
    assert len(provider.prompts) == 5
    state_text = result.session.model_dump_json().casefold()
    assert "image_provider" not in state_text
    assert "stage 3" not in state_text


def test_stage1_2_graph_writes_llm_debug_artifacts_for_bad_scorer_response(tmp_path) -> None:
    class BadScorerProvider(ScriptedLLMProvider):
        def generate_text(self, prompt: str) -> str:
            self.prompts.append(prompt)
            if len(self.prompts) == 1:
                return json.dumps({"candidates": [{"theme": "Лиса", "text": _COMPLIANT_FOX_STORY_1}]})
            if len(self.prompts) == 2:
                return json.dumps({"decisions": []})
            return json.dumps({"scores": [{"candidate_id": "wrong-id", "hard_gates": {}, "score_components": {}, "total_score": 0.5}]})

    provider = BadScorerProvider()
    debug_dir = tmp_path / "debug" / "llm"
    executor = build_stage2_text_executor(
        executor_type="llm",
        llm_provider=provider,
        model_name="scripted",
        debug_artifact_dir=debug_dir,
    )
    orchestrator = Stage1_2Orchestrator(
        storage=JSONStorage(tmp_path),
        text_executor=executor,
        candidate_count=1,
    )
    session = orchestrator.start_session(REQUEST, current_config={"count": 1})

    result = orchestrator.run_pipeline(session.session_id)

    assert result.session.shortage.status == "not_enough_valid_candidates"
    scorer_artifact = next(path for path in debug_dir.glob("*.json") if "scorer" in path.name)
    artifact = json.loads(scorer_artifact.read_text(encoding="utf-8"))
    assert artifact["diagnostics"]["valid_items"] == 0
    assert artifact["diagnostics"]["rejected_items"][0]["reason"] == "unknown_candidate_id"


def _run_cli(tmp_path, *args: str, extra_env: dict[str, str] | None = None):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.pop("GPTTUNNEL_API_KEY", None)
    env["DREAMYDRAW_STAGE1_2_OUTPUT_DIR"] = str(tmp_path)
    if extra_env:
        env.update(extra_env)
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        cwd=os.getcwd(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _runtime_context() -> dict:
    return {
        "stage": "candidate_text_generator",
        "normalized_request_summary": {"truth_mode": "fairy_tale", "target_age": "5", "main_subject": "fox", "output_count": 2},
        "ordered_layer_refs": [],
        "fallback_layer_refs": [],
        "unresolved_details": [],
        "stage_instructions": [],
        "context_blocks": [],
        "length_policy": {"target_age": "5", "sentences_min": 3, "sentences_max": 5, "complexity_profile": "moderate"},
    }
