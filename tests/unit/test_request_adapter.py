import pytest
from pydantic import ValidationError

from src.core.request_adapter import to_session_request
from src.models.schemas import (
    GenerationRequest,
    ImageStyle,
    SessionRequest,
    TextStyle,
    TruthMode,
    WorkMode,
)


def test_session_request_passes_through_and_merges_current_config():
    request = SessionRequest(raw_text="Сказка про лису", current_config={"count": 1, "tone": "soft"})

    result = to_session_request(request, current_config={"count": 2, "age": 5})

    assert result.raw_text == "Сказка про лису"
    assert result.current_config == {
        "tone": "soft",
        "output_count": 2,
        "target_age": "5",
        "truth_mode": "TRUTH",
        "cultural_context": "RUSSIAN_FOLK",
        "utility_mode": "NARRATIVE",
    }


def test_raw_string_becomes_session_request_raw_text():
    result = to_session_request("История про лису", current_config={"count": 2})

    assert result.raw_text == "История про лису"
    assert result.current_config == {
        "output_count": 2,
        "target_age": "5",
        "truth_mode": "TRUTH",
        "cultural_context": "RUSSIAN_FOLK",
        "utility_mode": "NARRATIVE",
    }


def test_generation_request_maps_legacy_fields_to_compatibility_preferences():
    request = GenerationRequest(
        topic="Сказка про лису",
        count=3,
        truth_mode=TruthMode.FAIRY_TALE,
        text_style=TextStyle.PLAYFUL,
        image_style=ImageStyle.WATERCOLOR,
        work_mode=WorkMode.CHECK,
    )

    result = to_session_request(request, current_config={"target_age": "5"})

    assert result.raw_text == "Сказка про лису"
    assert result.current_config["output_count"] == 3
    assert result.current_config["target_age"] == "5"
    assert result.current_config["truth_mode"] == "FAIRY_TALE"
    assert result.current_config["cultural_context"] == "RUSSIAN_FOLK"
    assert result.current_config["utility_mode"] == "NARRATIVE"
    assert result.current_config["text_style"] == "PLAYFUL"
    assert result.current_config["image_style"] == "WATERCOLOR"
    assert result.current_config["work_mode"] == "check"


def test_generation_request_image_style_does_not_create_stage3_or_image_routing_flag():
    result = to_session_request(
        GenerationRequest(topic="Лиса", image_style=ImageStyle.NIGHT, work_mode=WorkMode.FAST)
    )

    assert "stage3" not in result.current_config
    assert "image_generation" not in result.current_config
    assert "generate_images" not in result.current_config
    assert result.current_config["image_style"] == "NIGHT"


@pytest.mark.parametrize(
    "config",
    [
        {"count": 0},
        {"count": 11},
        {"target_age": "4"},
        {"truth_mode": "MYTH"},
        {"cultural_context": "UNKNOWN"},
        {"utility_mode": "UNKNOWN"},
    ],
)
def test_invalid_controlled_config_is_rejected(config):
    with pytest.raises(ValidationError):
        to_session_request("История про лису", current_config=config)
