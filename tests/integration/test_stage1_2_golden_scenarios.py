from __future__ import annotations

import pytest

from tests.helpers.stage1_2_golden import (
    approved_text,
    approved_themes,
    fallback_layer_ids,
    layer_ids,
    run_golden_pipeline,
    unresolved_labels,
)

pytestmark = pytest.mark.integration


def test_truth_hedgehog_winter_stories_reach_approved_texts(tmp_path):
    result, executor = run_golden_pipeline(
        tmp_path,
        "Сделай 2 правдивые короткие истории про ёжика зимой в лесу для ребёнка 3 лет.",
        count=2,
    )
    session = result.session

    assert result.is_done
    assert session.normalized_request.content_format == "story"
    assert session.normalized_request.truth_mode == "TRUTH"
    assert session.normalized_request.utility_mode == "NARRATIVE"
    assert session.normalized_request.target_age == "3"
    assert session.normalized_request.main_subject == "hedgehog"
    assert {"CONTENT_FORMAT_STORY", "TRUTH_BASE", "UTILITY_NARRATIVE_BASE", "AGE_3", "LANGUAGE_RU_AUDIENCE", "LANGUAGE_RU_RESULT", "TRUTH_ANIMAL_HEDGEHOG"} <= layer_ids(session)
    assert {"winter", "forest"} <= unresolved_labels(session)
    assert len(session.approved_texts) == 2
    assert "ёжик" in approved_text(session).casefold()
    assert "__bad_talking__" not in approved_text(session).casefold()
    assert len(approved_themes(session)) == len(set(approved_themes(session)))
    assert executor.calls["refine_candidate"] >= 1


def test_fairy_tale_fox_stories_allow_fairy_tale_behavior(tmp_path):
    result, _ = run_golden_pipeline(
        tmp_path,
        "Сделай 2 сказочные истории про лису для 5 лет.",
        count=2,
    )
    session = result.session

    assert result.is_done
    assert session.normalized_request.truth_mode == "FAIRY_TALE"
    assert session.normalized_request.utility_mode == "NARRATIVE"
    assert session.normalized_request.target_age == "5"
    assert {"FAIRY_TALE_BASE", "UTILITY_NARRATIVE_BASE", "AGE_5", "FAIRY_TALE_ANIMAL_FOX"} <= layer_ids(session)
    assert "разговаривает" in approved_text(session).casefold()
    assert all(result.validation_status == "accepted" for result in session.approved_texts)


def test_gentle_myth_about_sun_and_wind_preserves_freeform_nature_subject(tmp_path):
    result, _ = run_golden_pipeline(
        tmp_path,
        "Сделай мягкую мифологическую историю про солнце и ветер для ребёнка 5 лет.",
        count=1,
    )
    session = result.session

    assert result.is_done
    assert session.normalized_request.truth_mode == "MYTH"
    assert session.normalized_request.utility_mode == "NARRATIVE"
    assert session.normalized_request.target_age == "5"
    assert {"MYTH_BASE", "MYTH_SOFT_BASE", "UTILITY_NARRATIVE_BASE", "AGE_5"} <= layer_ids(session)
    assert {"солнце", "ветер"} <= unresolved_labels(session)
    text = approved_text(session).casefold()
    assert "образ" in text
    assert "не объясняют науку" in text


def test_teaching_truth_story_about_hand_washing_keeps_hygiene_points(tmp_path):
    result, _ = run_golden_pipeline(
        tmp_path,
        "Сделай поучительную правдивую историю про мытьё рук после прогулки.",
        count=1,
    )
    session = result.session

    assert result.is_done
    assert session.normalized_request.truth_mode == "TRUTH"
    assert session.normalized_request.utility_mode == "TEACHING"
    assert session.normalized_request.utility_topic == "HAND_WASHING_AFTER_WALK"
    assert {"TRUTH_BASE", "UTILITY_TEACHING_BASE", "UTILITY_TOPIC_HAND_WASHING_AFTER_WALK", "ENTITY_HANDS"} <= layer_ids(session)
    text = approved_text(session).casefold()
    assert "моет руки" in text
    assert "мылом" in text
    assert "не мыть" not in text
    assert any(score.hard_gates["utility_goal"] == "pass" for score in session.scores)


def test_teaching_fairy_tale_about_road_crossing_preserves_safety(tmp_path):
    result, executor = run_golden_pipeline(
        tmp_path,
        "Сделай поучительную сказку про переход через дорогу для 5 лет.",
        count=1,
    )
    session = result.session

    assert result.is_done
    assert session.normalized_request.truth_mode == "FAIRY_TALE"
    assert session.normalized_request.utility_mode == "TEACHING"
    assert session.normalized_request.utility_topic == "ROAD_SAFETY"
    assert {"FAIRY_TALE_BASE", "UTILITY_TEACHING_BASE", "UTILITY_TOPIC_ROAD_SAFETY"} <= layer_ids(session)
    text = approved_text(session).casefold()
    assert "зелёный" in text
    assert "со взрослым" in text
    assert "на красный" not in text
    assert executor.calls["refine_candidate"] >= 1


def test_stranger_and_candy_story_rejects_unsafe_candidate(tmp_path):
    result, executor = run_golden_pipeline(
        tmp_path,
        "Сделай поучительную историю про незнакомца и конфету для ребёнка 5 лет.",
        count=1,
    )
    session = result.session

    assert result.is_done
    assert session.normalized_request.utility_mode == "TEACHING"
    assert session.normalized_request.utility_topic == "STRANGERS_AND_CANDY"
    assert {"UTILITY_TOPIC_STRANGERS_AND_CANDY", "ENTITY_STRANGER", "ENTITY_CANDY", "ENTITY_CARING_ADULT"} <= layer_ids(session)
    text = approved_text(session).casefold()
    assert "не берёт конфету" in text
    assert "заботливого взрослого" in text
    assert "пошёл за ним" not in text
    assert executor.calls["refine_candidate"] >= 1


def test_cockatoo_uses_parrot_fallback_without_claiming_cockatoo_layer(tmp_path):
    result, _ = run_golden_pipeline(
        tmp_path,
        "Сделай правдивую историю про попугая какаду для 5 лет.",
        count=1,
    )
    session = result.session

    assert result.is_done
    assert session.normalized_request.truth_mode == "TRUTH"
    assert session.normalized_request.main_subject == "parrot"
    assert "TRUTH_ANIMAL_PARROT" in fallback_layer_ids(session) | layer_ids(session)
    assert "какаду" in unresolved_labels(session)
    assert "COCKATOO" not in " ".join(layer_ids(session))
    assert "какаду" in approved_text(session).casefold()
    assert "попугай" in approved_text(session).casefold()


def test_fox_hare_squirrel_continuity_refines_subject_drop(tmp_path):
    result, executor = run_golden_pipeline(
        tmp_path,
        "Сделай 3 истории про лису, зайца и белку зимой, чтобы герои не исчезали.",
        count=3,
    )
    session = result.session

    assert result.is_done
    assert {subject.id for subject in session.normalized_request.subjects} >= {"fox", "hare", "squirrel"}
    assert set(session.normalized_request.subject_continuity_policy.required_subjects) >= {"fox", "hare", "squirrel"}
    assert session.normalized_request.subject_continuity_policy.can_replace_required_subjects is False
    for item in session.approved_texts:
        text = item.text.casefold()
        assert "лиса" in text
        assert "заяц" in text
        assert "белка" in text
    assert any(issue.type == "subject_continuity" for result in session.validation_results for issue in result.issues)
    assert executor.calls["refine_candidate"] >= 1


def test_custom_squirrel_character_tim_preserves_profile_and_trace_refs(tmp_path):
    result, executor = run_golden_pipeline(
        tmp_path,
        "Сделай историю про маленького бельчонка Тима, он смелый и любит жёлуди.",
        count=1,
    )
    session = result.session

    assert result.is_done
    assert session.normalized_request.main_subject == "squirrel"
    assert "TRUTH_ANIMAL_SQUIRREL" in layer_ids(session)
    assert session.normalized_request.character_profile is not None
    assert session.normalized_request.character_profile.name == "Тим"
    assert "смелый" in session.normalized_request.character_profile.stable_traits
    assert "любит жёлуди" in session.normalized_request.character_profile.stable_details
    text = approved_text(session)
    assert "Тим" in text
    assert "смелый" in text
    assert "жёлуди" in text
    assert session.approved_texts[0].trace_refs.get("candidate_id") == session.approved_texts[0].candidate_id
    assert session.approved_texts[0].trace_refs.get("version_id") == session.approved_texts[0].version_id
    assert executor.calls["refine_candidate"] >= 1
