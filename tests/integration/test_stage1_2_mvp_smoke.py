from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCRIPT = "scripts/run_stage1_2_mvp.py"
HAPPY_REQUEST = "Сделай 2 поучительные сказки про лису и переход через дорогу для 5 лет."
RESUME_REQUEST = "Сделай сказку про лису для 5 лет."
UNSUPPORTED_REQUEST = "Сделай сказку про лису для 5 лет строго в стиле Дисней."
CONTRADICTION_REQUEST = (
    "Сделай правдивую историю про лису для 5 лет, обязательно чтобы она летала "
    "на волшебном ковре."
)


def test_happy_path_cli_reaches_approved_texts_and_persists_text_only_state(tmp_path):
    result = _run_cli(tmp_path, HAPPY_REQUEST, "--count", "2")

    assert result.returncode == 0
    assert "session_id:" in result.stdout
    assert "completion_status: completed_enough" in result.stdout
    assert "current_node:" in result.stdout
    assert "approved_count: 2" in result.stdout
    assert result.stdout.count("theme:") >= 2
    assert "approved_texts:" in result.stdout
    _assert_no_visual_or_provider_output(result.stdout)

    state = _load_state(tmp_path, _session_id(result.stdout))
    assert len(state["approved_texts"]) == 2
    assert state["completion_status"] == "completed_enough"
    assert "image" not in " ".join(state["stage_status"].keys()).casefold()
    assert "animation" not in " ".join(state["stage_status"].keys()).casefold()


def test_empty_request_cli_waits_then_resume_uses_same_session_without_extra_attempt(tmp_path):
    paused = _run_cli(tmp_path, "")

    assert paused.returncode == 0
    assert "waiting_user: true" in paused.stdout
    assert "session_id:" in paused.stdout
    assert "interrupt_node: empty_input_interrupt" in paused.stdout
    assert "interrupt_reason:" in paused.stdout
    assert "freeform_allowed: true" in paused.stdout
    assert "approved_texts:" not in paused.stdout

    session_id = _session_id(paused.stdout)
    paused_state = _load_state(tmp_path, session_id)
    assert paused_state["stage_status"]["candidate_text_generator"]["status"] == "not_started"
    paused_attempts = paused_state["interpretation_state"]["clarification_attempts"]

    resumed = _run_cli(tmp_path, "--session", session_id, "--resume", RESUME_REQUEST)

    assert resumed.returncode == 0
    assert f"session_id: {session_id}" in resumed.stdout
    assert "approved_texts:" in resumed.stdout
    assert "approved_count:" in resumed.stdout
    _assert_no_visual_or_provider_output(resumed.stdout)

    resumed_state = _load_state(tmp_path, session_id)
    assert resumed_state["approved_texts"]
    assert resumed_state["interpretation_state"]["clarification_attempts"] == paused_attempts


def test_unsupported_hard_requirement_cli_stops_without_approved_texts_or_fabricated_layer(tmp_path):
    result = _run_cli(tmp_path, UNSUPPORTED_REQUEST)

    assert result.returncode == 0
    assert (
        "waiting_user: true" in result.stdout
        or "completion_status: stopped_unresolved_request" in result.stdout
    )
    assert "approved_texts:" not in result.stdout
    assert "DISNEY" not in result.stdout
    _assert_no_visual_or_provider_output(result.stdout)

    state = _load_state(tmp_path, _session_id(result.stdout))
    assert not state["approved_texts"]
    assert "DISNEY" not in json.dumps(state["normalized_request"]["prompt_context"], ensure_ascii=False)
    assert state["stage_status"]["candidate_text_generator"]["status"] == "not_started"


def test_truth_fantasy_contradiction_cli_stops_with_unsupported_state_detail(tmp_path):
    result = _run_cli(tmp_path, CONTRADICTION_REQUEST)

    assert result.returncode == 0
    assert (
        "waiting_user: true" in result.stdout
        or "completion_status: stopped_unresolved_request" in result.stdout
    )
    assert "approved_texts:" not in result.stdout
    _assert_no_visual_or_provider_output(result.stdout)

    state = _load_state(tmp_path, _session_id(result.stdout))
    assert not state["approved_texts"]
    state_text = json.dumps(state, ensure_ascii=False).casefold()
    assert "unsupported" in state_text
    assert "fantastic" in state_text or "волшеб" in state_text
    assert state["stage_status"]["candidate_text_generator"]["status"] == "not_started"


def _run_cli(tmp_path, *args):
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["DREAMYDRAW_STAGE1_2_OUTPUT_DIR"] = str(tmp_path)
    return subprocess.run(
        [sys.executable, SCRIPT, *args],
        cwd=os.getcwd(),
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _session_id(output: str) -> str:
    match = re.search(r"session_id:\s*([0-9a-f-]+)", output)
    assert match, output
    return match.group(1)


def _load_state(tmp_path: Path, session_id: str) -> dict:
    with (tmp_path / session_id / "state.json").open(encoding="utf-8") as file:
        return json.load(file)


def _assert_no_visual_or_provider_output(output: str) -> None:
    lowered = output.casefold()
    forbidden = [
        "image generation",
        "animation",
        "stage 3",
        "openai",
        "gptunnel",
        "provider",
        "картин",
        "изображен",
        "анимац",
    ]
    for marker in forbidden:
        assert marker not in lowered
