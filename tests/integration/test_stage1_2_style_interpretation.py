from pathlib import Path

import pytest

from tests.helpers.stage1_2_golden import layer_ids, run_golden_pipeline

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts" / "cultural_contexts" / "russian_folk"
pytestmark = pytest.mark.integration


def test_chukovsky_wave11_request_reaches_approved_texts(tmp_path):
    result, executor = run_golden_pipeline(
        tmp_path,
        "Сделай 2 сказки про лису для 3 лет в стиле чуковского",
        count=2,
        target_age="3",
        truth_mode="FAIRY_TALE",
    )
    session = result.session

    assert result.is_done
    assert "CHUKOVSKY_STYLE" in layer_ids(session)
    assert session.normalized_request.substyle == "CHUKOVSKY_STYLE"
    assert session.approved_texts
    assert executor.calls["generate_candidates"] == 1


def test_chukovsky_typo_reaches_approved_texts(tmp_path):
    result, _ = run_golden_pipeline(
        tmp_path,
        "3 сказки про лису как у чуйковкого для 5 лет",
        count=1,
        truth_mode="FAIRY_TALE",
    )
    session = result.session

    assert result.is_done
    assert "CHUKOVSKY_STYLE" in layer_ids(session)
    assert session.approved_texts


def test_truth_fox_story_keeps_subject_not_character(tmp_path):
    result, _ = run_golden_pipeline(
        tmp_path,
        "2 правдивых истории про лису для 5 лет",
        count=1,
    )
    session = result.session
    fox = next(subject for subject in session.normalized_request.subjects if subject.id == "fox")

    assert result.is_done
    assert fox.is_character is False
    assert session.approved_texts
