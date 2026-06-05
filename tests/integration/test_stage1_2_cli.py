from __future__ import annotations

import os
import re
import subprocess
import sys

SCRIPT = "scripts/run_stage1_2_mvp.py"
SUPPORTED_REQUEST = "Сделай сказку про лису для 5 лет и научи безопасности на дороге"


def test_supported_request_exits_successfully_and_prints_approved_texts(tmp_path):
    result = _run_cli(tmp_path, SUPPORTED_REQUEST, "--count", "2")

    assert result.returncode == 0
    assert "approved_texts" in result.stdout
    assert "Лиса ждёт зелёный" in result.stdout
    assert "image generation" not in result.stdout.lower()


def test_empty_request_prints_waiting_clarification_and_session_id(tmp_path):
    result = _run_cli(tmp_path, "")

    assert result.returncode == 0
    assert "waiting_user" in result.stdout
    assert "session_id:" in result.stdout
    assert "interrupt_node: empty_input_interrupt" in result.stdout


def test_session_can_resume_using_saved_session_id(tmp_path):
    paused = _run_cli(tmp_path, "")
    session_id = re.search(r"session_id:\s*([0-9a-f-]+)", paused.stdout).group(1)

    resumed = _run_cli(tmp_path, "--session", session_id, "--resume", SUPPORTED_REQUEST)

    assert resumed.returncode == 0
    assert "approved_texts" in resumed.stdout
    assert "Лиса ждёт зелёный" in resumed.stdout


def test_cli_output_does_not_mention_image_generation_as_next_step(tmp_path):
    result = _run_cli(tmp_path, SUPPORTED_REQUEST)

    assert "image generation" not in result.stdout.lower()
    assert "генерац" not in result.stdout.lower() or "картин" not in result.stdout.lower()


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
