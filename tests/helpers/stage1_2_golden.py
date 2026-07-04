from __future__ import annotations

from pathlib import Path
from typing import Any

from src.core.stage1_2_orchestrator import Stage1_2Orchestrator
from src.models.schemas import SessionState
from src.storage.json_storage import JSONStorage

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"

REQUIRED_GATES = {
    "safety",
    "truth_fit",
    "age_fit",
    "utility_goal",
    "subject_continuity",
    "hard_details",
    "character_consistency",
}


class GoldenStage2Executor:
    """Scenario-aware fake for Stage 1-2 golden regression tests."""

    def __init__(self, *, mutate_tim_refiner: bool = False) -> None:
        self.mutate_tim_refiner = mutate_tim_refiner
        self.calls = {
            "generate_candidates": 0,
            "deduplicate_topics": 0,
            "score_candidates": 0,
            "validate_candidate": 0,
            "refine_candidate": 0,
        }

    def generate_candidates(self, runtime_context: dict[str, Any], count: int) -> list[dict[str, Any]]:
        self.calls["generate_candidates"] += 1
        summary = runtime_context["normalized_request_summary"]
        scenario = _scenario(summary)
        candidates = _scenario_candidates(scenario, summary)
        return candidates[:count]

    def deduplicate_topics(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls["deduplicate_topics"] += 1
        return []

    def score_candidates(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        self.calls["score_candidates"] += 1
        results = []
        for index, candidate in enumerate(runtime_context["candidate_texts"]):
            text = candidate["text"].casefold()
            hard_gates = {gate: "pass" for gate in REQUIRED_GATES}
            if "__score_fail_subject__" in text:
                hard_gates["subject_continuity"] = "fail"
            if "__score_fail_safety__" in text:
                hard_gates["safety"] = "fail"
            results.append(
                {
                    "candidate_id": candidate["candidate_id"],
                    "hard_gates": hard_gates,
                    "score_components": {
                        "child_interest": 0.95 - index * 0.03,
                        "age_fit": 0.9,
                        "utility_fit": 0.9,
                        "style_fit": 0.9,
                        "novelty": 0.85 - index * 0.02,
                        "visual_potential": 0.8,
                    },
                    "total_score": 0.95 - index * 0.03,
                }
            )
        return results

    def validate_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        self.calls["validate_candidate"] += 1
        candidate = runtime_context["candidate_text"]
        text = candidate.get("text", "")
        summary = runtime_context["normalized_request_summary"]
        issues = []
        fixes = []

        checks = [
            ("__bad_talking__", "truth_fit", "Убрать человеческую речь животного в TRUTH."),
            ("__unsafe_road__", "safety", "Вернуть безопасное правило перехода дороги."),
            ("__unsafe_candy__", "safety", "Не разрешать брать конфету у незнакомца."),
            ("__fearmongering__", "safety", "Сделать тон спокойным, без запугивания."),
            ("__drop_subject__", "subject_continuity", "Вернуть всех обязательных героев."),
            ("__fantastic_truth__", "truth_fit", "Убрать фантастическое утверждение из TRUTH."),
            ("__tim_mutated__", "character_consistency", "Вернуть имя Тим и стабильные черты."),
        ]
        for marker, issue_type, fix in checks:
            if marker in text.casefold():
                issues.append({"type": issue_type, "severity": "major", "description": fix})
                fixes.append(fix)

        if _missing_required_subject(text, summary):
            issues.append(
                {
                    "type": "subject_continuity",
                    "severity": "major",
                    "description": "Текст потерял обязательного героя.",
                }
            )
            fixes.append("Вернуть обязательных героев в текст.")
        if summary.get("character_profile") and "Тим" not in text:
            issues.append(
                {
                    "type": "character_consistency",
                    "severity": "major",
                    "description": "Имя персонажа изменено.",
                }
            )
            fixes.append("Сохранить имя Тим.")

        if issues:
            status = "rejected" if runtime_context["attempt"] >= 3 else "needs_revision"
            return {
                "status": status,
                "summary": "needs fixes",
                "issues": issues,
                "required_fixes": fixes,
            }
        return {"status": "accepted", "summary": "golden fake accepted", "issues": [], "required_fixes": []}

    def refine_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        self.calls["refine_candidate"] += 1
        candidate = runtime_context["candidate_text"]
        summary = runtime_context["normalized_request_summary"]
        scenario = _scenario(summary)
        if self.mutate_tim_refiner and scenario == "tim_squirrel":
            return {
                "theme": candidate["theme"],
                "text": "__TIM_MUTATED__ Бельчонок Том стал осторожным и забыл про жёлуди.",
                "questions": candidate.get("questions", []),
                "changes_summary": "Неверно изменили защищённый профиль.",
            }
        return {
            "theme": candidate["theme"],
            "text": _approved_text(scenario, summary, variant="refined"),
            "questions": candidate.get("questions", []),
            "changes_summary": "Исправили hard-gate нарушения без изменения защищённых деталей.",
        }


class LenientStage2Executor(GoldenStage2Executor):
    """Simulates lenient real LLM scorer/validator; TRUTH safety net is deterministic post-check."""

    def __init__(self, *, mutate_tim_refiner: bool = False) -> None:
        super().__init__(mutate_tim_refiner=mutate_tim_refiner)
        self.runtime_contexts: dict[str, list[dict[str, Any]]] = {
            "generate_candidates": [],
            "score_candidates": [],
            "validate_candidate": [],
        }

    def score_candidates(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]:
        self.runtime_contexts["score_candidates"].append(runtime_context)
        self.calls["score_candidates"] += 1
        return [
            {
                "candidate_id": candidate["candidate_id"],
                "hard_gates": {gate: "pass" for gate in REQUIRED_GATES},
                "score_components": {
                    "child_interest": 0.95 - index * 0.03,
                    "age_fit": 0.9,
                    "utility_fit": 0.9,
                    "style_fit": 0.9,
                    "novelty": 0.85 - index * 0.02,
                    "visual_potential": 0.8,
                },
                "total_score": 0.95 - index * 0.03,
            }
            for index, candidate in enumerate(runtime_context["candidate_texts"])
        ]

    def validate_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]:
        self.runtime_contexts["validate_candidate"].append(runtime_context)
        self.calls["validate_candidate"] += 1
        return {
            "status": "accepted",
            "summary": "lenient fake accepted",
            "issues": [],
            "required_fixes": [],
        }

    def generate_candidates(self, runtime_context: dict[str, Any], count: int) -> list[dict[str, Any]]:
        self.runtime_contexts["generate_candidates"].append(runtime_context)
        self.calls["generate_candidates"] += 1
        summary = runtime_context["normalized_request_summary"]
        scenario = _scenario(summary)
        candidates: list[dict[str, Any]] = []
        natural_violation = _natural_truth_violation(scenario)
        if natural_violation:
            candidates.append(_candidate("Lenient TRUTH violation", natural_violation, summary))
        for index in range(1, 6):
            candidates.append(
                _candidate(
                    f"{_theme_prefix(scenario)} {index}",
                    _approved_text(scenario, summary, variant=str(index)),
                    summary,
                )
            )
        return candidates[:count]


def run_golden_pipeline(
    tmp_path,
    request: str,
    *,
    count: int | None = None,
    candidate_count: int = 6,
    executor: GoldenStage2Executor | LenientStage2Executor | None = None,
):
    fake = executor or GoldenStage2Executor()
    orchestrator = Stage1_2Orchestrator(
        storage=JSONStorage(str(tmp_path)),
        text_executor=fake,
        prompts_root=PROMPTS_ROOT,
        candidate_count=candidate_count,
    )
    current_config = {"count": count} if count is not None else None
    session = orchestrator.start_session(request, current_config=current_config)
    return orchestrator.run_pipeline(session.session_id), fake


def layer_ids(session: SessionState) -> set[str]:
    return {ref.id for ref in session.normalized_request.prompt_context.resolved_layers}


def unresolved_labels(session: SessionState) -> set[str]:
    return {detail.label for detail in session.normalized_request.prompt_context.unresolved_details}


def fallback_layer_ids(session: SessionState) -> set[str]:
    return {fallback.fallback_layer_id for fallback in session.normalized_request.prompt_context.fallback_layers}


def approved_text(session: SessionState) -> str:
    return "\n".join(item.text for item in session.approved_texts)


def approved_themes(session: SessionState) -> list[str]:
    return [item.theme.casefold().strip() for item in session.approved_texts]


def _scenario(summary: dict[str, Any]) -> str:
    subject_ids = {subject["id"] for subject in summary.get("subjects", [])}
    utility_topic = summary.get("utility_topic")
    truth_mode = summary.get("truth_mode")
    profile = summary.get("character_profile") or {}
    if profile.get("name") == "Тим":
        return "tim_squirrel"
    if {"fox", "hare", "squirrel"}.issubset(subject_ids):
        return "continuity"
    if utility_topic == "STRANGERS_AND_CANDY":
        return "stranger_candy"
    if utility_topic == "ROAD_SAFETY":
        return "road_safety"
    if utility_topic == "HAND_WASHING_AFTER_WALK":
        return "hand_washing"
    if "parrot" in subject_ids:
        return "cockatoo_parrot"
    if truth_mode == "MYTH":
        return "myth_nature"
    if "hedgehog" in subject_ids:
        return "truth_hedgehog"
    if "fox" in subject_ids and truth_mode == "TRUTH":
        return "truth_fox"
    if "fox" in subject_ids and truth_mode == "FAIRY_TALE":
        return "fairy_fox"
    return "generic"


def _natural_truth_violation(scenario: str) -> str | None:
    return {
        "truth_hedgehog": "Жила-была маленькая ёжиха, и она сказала: «Сегодня будет снег».",
        "truth_fox": "Жила-была лиса в лесу и однажды сказала: «Пойдём гулять».",
    }.get(scenario)


def _scenario_candidates(scenario: str, summary: dict[str, Any]) -> list[dict[str, Any]]:
    bad_text = {
        "truth_hedgehog": "__BAD_TALKING__ Ёжик сказал человеческим голосом и наколдовал чай.",
        "road_safety": "__UNSAFE_ROAD__ Лиса перебежала дорогу на красный свет.",
        "stranger_candy": "__UNSAFE_CANDY__ Ребёнок взял конфету у незнакомца и пошёл за ним.",
        "continuity": "__DROP_SUBJECT__ Лиса и заяц гуляли зимой, а белка исчезла из истории.",
        "tim_squirrel": "__TIM_MUTATED__ Бельчонок Том стал робким и не любил жёлуди.",
    }.get(scenario)
    candidates = []
    if bad_text:
        candidates.append(_candidate("Исправляемый вариант", bad_text, summary))
    for index in range(1, 6):
        candidates.append(
            _candidate(
                f"{_theme_prefix(scenario)} {index}",
                _approved_text(scenario, summary, variant=str(index)),
                summary,
            )
        )
    return candidates


def _candidate(theme: str, text: str, summary: dict[str, Any]) -> dict[str, Any]:
    subjects = [subject["id"] for subject in summary.get("subjects", [])]
    return {
        "theme": theme,
        "text": text,
        "questions": ["Что было самым важным?"],
        "utility_points": _utility_points(summary),
        "used_subjects": subjects,
        "expected_visual_idea": "Stage 1-2 text only; no image generation.",
    }


def _theme_prefix(scenario: str) -> str:
    return {
        "truth_hedgehog": "Ёжик зимой",
        "truth_fox": "Лиса в лесу",
        "fairy_fox": "Сказочная лиса",
        "myth_nature": "Мягкий миф",
        "hand_washing": "Чистые руки",
        "road_safety": "Безопасный переход",
        "stranger_candy": "Правило конфеты",
        "cockatoo_parrot": "Попугай какаду",
        "continuity": "Лиса заяц белка",
        "tim_squirrel": "Бельчонок Тим",
    }.get(scenario, "История")


def _approved_text(scenario: str, summary: dict[str, Any], *, variant: str) -> str:
    suffix = f" Вариант {variant}."
    return {
        "truth_hedgehog": "Правдивая короткая история: ёжик зимой тихо ищет укрытие в лесу, не говорит и не колдует.",
        "truth_fox": "Правдивая короткая история: лиса зимой осторожно идёт по лесу и слушает звуки вокруг.",
        "fairy_fox": "Сказочная история: лиса в тёплом лесу вежливо разговаривает с ветром и делает добрый выбор.",
        "myth_nature": "Мягкий миф: солнце и ветер показаны как образы древней истории, а не как научное объяснение.",
        "hand_washing": "Поучительная правдивая история: ребёнок после прогулки моет руки с мылом и тёплой водой.",
        "road_safety": "Поучительная сказка: герой ждёт зелёный свет, смотрит по сторонам и переходит рядом со взрослым.",
        "stranger_candy": "Поучительная история: ребёнок не берёт конфету у незнакомца, не уходит с ним и зовёт заботливого взрослого.",
        "cockatoo_parrot": "Правдивая история: попугай какаду сидит на жердочке, чистит перья и остаётся птицей-попугаем.",
        "continuity": "Зимняя история: лиса, заяц и белка вместе идут по снегу, и каждый герой остаётся в событии.",
        "tim_squirrel": "История: маленький бельчонок Тим смелый, любит жёлуди и остаётся тем же персонажем.",
    }.get(_scenario(summary), "Короткая детская история с сохранёнными деталями.") + suffix


def _utility_points(summary: dict[str, Any]) -> list[str]:
    topic = summary.get("utility_topic")
    if topic == "ROAD_SAFETY":
        return ["ждать зелёный свет", "смотреть по сторонам", "идти со взрослым"]
    if topic == "HAND_WASHING_AFTER_WALK":
        return ["мыть руки после прогулки", "использовать мыло", "смывать грязь водой"]
    if topic == "STRANGERS_AND_CANDY":
        return ["не брать угощение у незнакомца", "не уходить с незнакомцем", "позвать заботливого взрослого"]
    return []


def _missing_required_subject(text: str, summary: dict[str, Any]) -> bool:
    policy = summary.get("subject_continuity_policy") or {}
    required = set(policy.get("required_subjects") or [])
    if not required:
        return False
    text_l = text.casefold()
    labels = {
        "fox": ("лиса", "лису", "лис"),
        "hare": ("заяц", "зайца", "зайчик"),
        "squirrel": ("белка", "белку", "бельчонок", "тим"),
        "hedgehog": ("ёжик", "ежик", "ежа"),
        "parrot": ("попугай", "какаду"),
    }
    for subject_id in required:
        if not any(label in text_l for label in labels.get(subject_id, (subject_id,))):
            return True
    return False
