from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any, Protocol

from src.core.graph.state import GraphState
from src.core.prompts.composer import PromptComposer
from src.core.prompts.registry import PromptRegistry
from src.models.schemas import (
    ApprovedText,
    CandidateScore,
    CandidateText,
    DeduplicationResult,
    RefinedCandidateVersion,
    RankedCandidate,
    SessionState,
    ValidatedCandidateVersion,
    ValidationIssue,
    ValidationResult,
)

DEFAULT_CANDIDATE_COUNT = 20
REQUIRED_HARD_GATES = (
    "safety",
    "truth_fit",
    "age_fit",
    "utility_goal",
    "subject_continuity",
    "hard_details",
    "character_consistency",
)
_CRITICAL_HARD_GATES = set(REQUIRED_HARD_GATES)


class Stage2TextExecutor(Protocol):
    def generate_candidates(self, runtime_context: dict[str, Any], count: int) -> list[dict[str, Any]]: ...

    def deduplicate_topics(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]: ...

    def score_candidates(self, runtime_context: dict[str, Any]) -> list[dict[str, Any]]: ...

    def validate_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]: ...

    def refine_candidate(self, runtime_context: dict[str, Any]) -> dict[str, Any]: ...


def candidate_text_generator(
    state: GraphState,
    registry: PromptRegistry,
    composer: PromptComposer,
    text_executor: Stage2TextExecutor,
    candidate_count: int | None = None,
) -> GraphState:
    session = state["session"]
    _require_stage1_ready(session)
    count = candidate_count or DEFAULT_CANDIDATE_COUNT
    build = composer.build_stage_context(
        normalized_request=session.normalized_request,
        prompt_context=session.prompt_context,
        stage="candidate_text_generator",
        stage_inputs={"output_count": session.normalized_request.output_count, "candidate_count": count},
    )
    session.stage_prompt_context.entries.append(build.durable_entry)

    raw_candidates = text_executor.generate_candidates(build.runtime_context, count)
    session.candidate_texts = _normalize_candidates(session, raw_candidates)
    session.pipeline_counters.generated_candidates = len(session.candidate_texts)
    _complete_stage(session, "candidate_text_generator")
    session.current_node = "candidate_text_generator"
    return state


def topic_deduplicator(
    state: GraphState,
    registry: PromptRegistry,
    composer: PromptComposer,
    text_executor: Stage2TextExecutor | None = None,
) -> GraphState:
    session = state["session"]
    _require_stage1_ready(session)
    build = composer.build_stage_context(
        normalized_request=session.normalized_request,
        prompt_context=session.prompt_context,
        stage="topic_deduplicator",
        stage_inputs={
            "candidate_themes": [candidate.theme for candidate in session.candidate_texts],
            "candidate_texts": [_compact_candidate(candidate) for candidate in session.candidate_texts],
        },
    )
    build.runtime_context["candidate_themes"] = [candidate.theme for candidate in session.candidate_texts]
    build.runtime_context["candidate_texts"] = [_compact_candidate(candidate) for candidate in session.candidate_texts]
    session.stage_prompt_context.entries.append(build.durable_entry)

    results = _exact_theme_duplicates(session.candidate_texts)
    if text_executor is not None:
        for decision in text_executor.deduplicate_topics(build.runtime_context):
            candidate_id = str(decision.get("candidate_id", ""))
            if candidate_id in results:
                results[candidate_id] = DeduplicationResult(
                    candidate_id=candidate_id,
                    is_duplicate=bool(decision.get("is_duplicate", results[candidate_id].is_duplicate)),
                    duplicate_of=decision.get("duplicate_of") or results[candidate_id].duplicate_of,
                    reason=decision.get("reason") or results[candidate_id].reason,
                )

    session.deduplication_results = [results[candidate.candidate_id] for candidate in session.candidate_texts]
    session.pipeline_counters.deduplicated_candidates = len(session.deduplication_results)
    _complete_stage(session, "topic_deduplicator")
    session.current_node = "topic_deduplicator"
    return state


def scorer(
    state: GraphState,
    registry: PromptRegistry,
    composer: PromptComposer,
    text_executor: Stage2TextExecutor,
) -> GraphState:
    session = state["session"]
    _require_stage1_ready(session)
    duplicate_ids = _duplicate_candidate_ids(session)
    scoreable = [candidate for candidate in session.candidate_texts if candidate.candidate_id not in duplicate_ids]
    candidate_payloads = [_compact_candidate(candidate) for candidate in scoreable]
    build = composer.build_stage_context(
        normalized_request=session.normalized_request,
        prompt_context=session.prompt_context,
        stage="scorer",
        stage_inputs={"candidate_texts": candidate_payloads},
    )
    build.runtime_context["candidate_texts"] = candidate_payloads
    session.stage_prompt_context.entries.append(build.durable_entry)

    raw_scores = text_executor.score_candidates(build.runtime_context)
    session.scores = [_normalize_score(item) for item in raw_scores]
    session.pipeline_counters.scored_candidates = len(session.scores)
    _complete_stage(session, "scorer")
    session.current_node = "scorer"
    return state


def ranker(state: GraphState) -> GraphState:
    session = state["session"]
    duplicate_ids = _duplicate_candidate_ids(session)
    ranked_source = [
        score
        for score in session.scores
        if score.candidate_id not in duplicate_ids and _hard_gates_passed(score)
    ]
    ranked_source.sort(
        key=lambda score: (
            -(score.total_score or 0.0),
            -float(score.score_components.get("novelty", 0.0)),
            -float(score.score_components.get("visual_potential", 0.0)),
            score.candidate_id,
        )
    )
    session.ranked_candidates = [
        RankedCandidate(
            candidate_id=score.candidate_id,
            rank=index,
            total_score=score.total_score,
            hard_gates_passed=True,
        )
        for index, score in enumerate(ranked_source, start=1)
    ]
    session.pipeline_counters.ranked_candidates = len(session.ranked_candidates)
    _complete_stage(session, "ranker")
    if session.stage_status.validation_loop.status == "not_started":
        _initialize_validation_loop(session)
    session.current_node = "ranker"
    return state


def candidate_validator(
    state: GraphState,
    registry: PromptRegistry,
    composer: PromptComposer,
    text_executor: Stage2TextExecutor,
) -> GraphState:
    session = state["session"]
    active = active_candidate_text(session)
    loop = session.validation_loop_state
    candidate_id = loop.active_candidate_id
    version_id = loop.active_version_id
    if candidate_id is None or version_id is None:
        raise ValueError("Validation loop has no active candidate/version.")

    attempt = loop.candidate_attempts.get(candidate_id, 0) + 1
    loop.candidate_attempts[candidate_id] = attempt
    candidate_payload = _active_text_payload(active)
    build = composer.build_stage_context(
        normalized_request=session.normalized_request,
        prompt_context=session.prompt_context,
        stage="candidate_validator",
        candidate_id=candidate_id,
        version_id=version_id,
        attempt=attempt,
        stage_inputs={"candidate_text": candidate_payload},
    )
    build.runtime_context["candidate_text"] = candidate_payload
    session.stage_prompt_context.entries.append(build.durable_entry)

    raw_result = text_executor.validate_candidate(build.runtime_context)
    validation = ValidationResult(
        candidate_id=candidate_id,
        version_id=version_id,
        status=raw_result.get("status", "needs_revision"),
        issues=[ValidationIssue(**issue) for issue in raw_result.get("issues", [])],
        required_fixes=list(raw_result.get("required_fixes", [])),
        summary=raw_result.get("summary"),
    )
    session.validation_results.append(validation)
    session.pipeline_counters.validation_attempts += 1

    if validation.status == "accepted":
        source = "refinement" if loop.active_text_source == "refined_candidate_versions" else "candidate"
        if not _has_validated_version(session, candidate_id, version_id):
            session.validated_candidate_versions.append(
                ValidatedCandidateVersion(
                    candidate_id=candidate_id,
                    version_id=version_id,
                    source=source,
                    theme=getattr(active, "theme", ""),
                    text=getattr(active, "text", ""),
                    questions=list(getattr(active, "questions", [])),
                    validation_status="accepted",
                    validation_summary=validation.summary,
                    used_context=_candidate_used_context(session, candidate_id),
                    trace_refs={"stage_context_hash": build.durable_entry.stage_context_hash},
                )
            )
        loop.accepted_count = len(session.validated_candidate_versions)
        loop.selector_eligible_unique_accepted_count = _selector_eligible_accepted_count(session)

    session.stage_status.validation_loop.status = "running"
    session.current_node = "candidate_validator"
    return state


def candidate_refiner(
    state: GraphState,
    registry: PromptRegistry,
    composer: PromptComposer,
    text_executor: Stage2TextExecutor,
) -> GraphState:
    session = state["session"]
    active = active_candidate_text(session)
    loop = session.validation_loop_state
    candidate_id = loop.active_candidate_id
    version_id = loop.active_version_id
    if candidate_id is None or version_id is None:
        raise ValueError("Validation loop has no active candidate/version.")

    latest_validation = _latest_validation_for_active(session)
    candidate_payload = _active_text_payload(active)
    refinement_attempt = _next_refinement_attempt(session, candidate_id)
    if refinement_attempt > loop.max_refinement_attempts_per_candidate:
        raise ValueError(
            f"Candidate {candidate_id} exceeded refinement attempt limit "
            f"({loop.max_refinement_attempts_per_candidate})."
        )
    build = composer.build_stage_context(
        normalized_request=session.normalized_request,
        prompt_context=session.prompt_context,
        stage="candidate_refiner",
        candidate_id=candidate_id,
        version_id=version_id,
        attempt=refinement_attempt,
        stage_inputs={
            "candidate_text": candidate_payload,
            "validator_issues": [issue.model_dump() for issue in latest_validation.issues],
            "required_fixes": list(latest_validation.required_fixes),
        },
    )
    build.runtime_context["candidate_text"] = candidate_payload
    build.runtime_context["validator_issues"] = [issue.model_dump() for issue in latest_validation.issues]
    build.runtime_context["required_fixes"] = list(latest_validation.required_fixes)
    session.stage_prompt_context.entries.append(build.durable_entry)

    raw_refined = text_executor.refine_candidate(build.runtime_context)
    new_version_id = _next_version_id(session, candidate_id)
    session.refined_candidate_versions.append(
        RefinedCandidateVersion(
            candidate_id=candidate_id,
            version_id=new_version_id,
            source_version_id=version_id,
            theme=raw_refined.get("theme", getattr(active, "theme", "")),
            text=raw_refined.get("text", getattr(active, "text", "")),
            questions=list(raw_refined.get("questions", getattr(active, "questions", []))),
            changes_summary=raw_refined.get("changes_summary"),
        )
    )
    loop.active_version_id = new_version_id
    loop.active_version_origin = "refined"
    loop.active_text_source = "refined_candidate_versions"
    session.pipeline_counters.refinement_attempts += 1
    session.stage_status.validation_loop.status = "running"
    session.current_node = "candidate_refiner"
    return state


def approved_text_selector(state: GraphState) -> GraphState:
    session = state["session"]
    selected: list[ApprovedText] = []
    seen_themes: set[str] = set()
    by_candidate = {item.candidate_id: item for item in session.validated_candidate_versions if item.validation_status == "accepted"}
    eligible_ranked = [
        item
        for item in sorted(session.ranked_candidates, key=lambda item: item.rank)
        if item.hard_gates_passed is True
    ]
    rank_order = [item.candidate_id for item in eligible_ranked]
    ordered_ids = rank_order
    score_by_candidate = {item.candidate_id: item.total_score for item in eligible_ranked}

    for candidate_id in ordered_ids:
        if len(selected) >= session.normalized_request.output_count:
            break
        version = by_candidate.get(candidate_id)
        if version is None:
            continue
        normalized_theme = _normalize_theme(version.theme)
        if normalized_theme in seen_themes:
            continue
        seen_themes.add(normalized_theme)
        selected.append(
            ApprovedText(
                candidate_id=version.candidate_id,
                version_id=version.version_id,
                theme=version.theme,
                text=version.text,
                questions=list(version.questions),
                score=score_by_candidate.get(version.candidate_id),
                validation_status=version.validation_status,
                validation_summary=version.validation_summary,
                used_context=version.used_context,
                trace_refs=dict(version.trace_refs),
            )
        )

    session.approved_texts = selected
    session.pipeline_counters.approved_texts = len(selected)
    requested = session.normalized_request.output_count
    session.shortage.requested = requested
    session.shortage.approved = len(selected)
    if len(selected) >= requested:
        session.shortage.status = "enough"
        session.shortage.reason = None
        session.completion_status = "completed_enough"
    else:
        session.shortage.status = "not_enough_valid_candidates"
        session.shortage.reason = "Not enough accepted validated candidate versions."
        session.completion_status = "completed_with_shortage"
    session.is_completed = True
    _complete_stage(session, "approved_text_selector")
    session.current_node = "approved_text_selector"
    return state


def active_candidate_text(session: SessionState) -> CandidateText | RefinedCandidateVersion:
    loop = session.validation_loop_state
    if loop.active_candidate_id is None or loop.active_version_id is None:
        raise ValueError("Validation loop has no active candidate/version.")
    if loop.active_text_source == "candidate_texts":
        for candidate in session.candidate_texts:
            if candidate.candidate_id == loop.active_candidate_id:
                return candidate
    if loop.active_text_source == "refined_candidate_versions":
        for version in session.refined_candidate_versions:
            if version.candidate_id == loop.active_candidate_id and version.version_id == loop.active_version_id:
                return version
    raise ValueError(
        f"Active candidate version not found: {loop.active_candidate_id}/{loop.active_version_id}"
    )


def advance_validation_cursor(session: SessionState) -> None:
    loop = session.validation_loop_state
    loop.selector_eligible_unique_accepted_count = _selector_eligible_accepted_count(session)
    if loop.selector_eligible_unique_accepted_count >= session.normalized_request.output_count:
        _complete_validation_loop(session)
        return
    next_index = 0 if loop.current_rank_index is None else loop.current_rank_index + 1
    if next_index >= len(session.ranked_candidates):
        loop.current_rank_index = next_index
        _complete_validation_loop(session)
        return
    ranked = session.ranked_candidates[next_index]
    loop.current_rank_index = next_index
    loop.active_candidate_id = ranked.candidate_id
    loop.active_version_id = f"{ranked.candidate_id}_v1"
    loop.active_version_origin = "draft"
    loop.active_text_source = "candidate_texts"
    session.stage_status.validation_loop.status = "running"


def has_validation_queue_exhausted(session: SessionState) -> bool:
    loop = session.validation_loop_state
    return (
        session.stage_status.validation_loop.status == "completed"
        or loop.active_candidate_id is None
        or (loop.current_rank_index is not None and loop.current_rank_index >= len(session.ranked_candidates))
    )


def _require_stage1_ready(session: SessionState) -> None:
    if (
        session.interpretation_state.execution_lookup_result.status != "pass"
        or not session.prompt_context.snapshot_hash
        or not session.preview_state.shown_to_user
    ):
        raise ValueError("Stage 2 nodes require Stage 1-ready session state.")


def _normalize_candidates(session: SessionState, raw_candidates: list[dict[str, Any]]) -> list[CandidateText]:
    seen_ids: set[str] = set()
    candidates: list[CandidateText] = []
    for index, raw in enumerate(raw_candidates, start=1):
        candidate_id = f"c{index:02d}"
        if candidate_id in seen_ids:
            raise ValueError(f"Duplicate candidate id after normalization: {candidate_id}")
        seen_ids.add(candidate_id)
        candidates.append(
            CandidateText(
                candidate_id=candidate_id,
                theme=raw.get("theme", ""),
                text=raw.get("text", ""),
                questions=list(raw.get("questions", [])),
                utility_points=list(raw.get("utility_points", [])),
                used_subjects=_candidate_subjects(session, raw),
                expected_visual_idea=raw.get("expected_visual_idea"),
                used_context=session.normalized_request.prompt_context,
                status="draft",
            )
        )
    return candidates


def _candidate_subjects(session: SessionState, raw: dict[str, Any]) -> list[str]:
    subjects = list(raw.get("used_subjects", []))
    required = [subject.id for subject in session.normalized_request.subjects]
    main_subject = session.normalized_request.main_subject
    for subject_id in required:
        if subject_id not in subjects:
            subjects.append(subject_id)
    if main_subject and main_subject not in subjects:
        subjects.append(main_subject)
    return subjects


def _exact_theme_duplicates(candidates: list[CandidateText]) -> dict[str, DeduplicationResult]:
    seen: dict[str, str] = {}
    results: dict[str, DeduplicationResult] = {}
    for candidate in candidates:
        normalized = _normalize_theme(candidate.theme)
        if normalized and normalized in seen:
            results[candidate.candidate_id] = DeduplicationResult(
                candidate_id=candidate.candidate_id,
                is_duplicate=True,
                duplicate_of=seen[normalized],
                reason="exact_normalized_theme_duplicate",
            )
        else:
            if normalized:
                seen[normalized] = candidate.candidate_id
            results[candidate.candidate_id] = DeduplicationResult(candidate_id=candidate.candidate_id)
    return results


def _normalize_theme(theme: str) -> str:
    return re.sub(r"\s+", " ", theme.casefold()).strip()


def _duplicate_candidate_ids(session: SessionState) -> set[str]:
    return {
        result.candidate_id
        for result in session.deduplication_results
        if result.is_duplicate
    }


def _normalize_score(raw: dict[str, Any]) -> CandidateScore:
    gates = {gate: raw.get("hard_gates", {}).get(gate, "pass") for gate in REQUIRED_HARD_GATES}
    components = {
        str(key): float(value)
        for key, value in raw.get("score_components", {}).items()
    }
    total = raw.get("total_score")
    return CandidateScore(
        candidate_id=str(raw["candidate_id"]),
        hard_gates=gates,
        score_components=components,
        total_score=float(total) if total is not None else None,
    )


def _hard_gates_passed(score: CandidateScore) -> bool:
    return all(score.hard_gates.get(gate) == "pass" for gate in _CRITICAL_HARD_GATES)


def _initialize_validation_loop(session: SessionState) -> None:
    loop = session.validation_loop_state
    loop.current_rank_index = 0
    if session.ranked_candidates:
        first = session.ranked_candidates[0]
        loop.active_candidate_id = first.candidate_id
        loop.active_version_id = f"{first.candidate_id}_v1"
        loop.active_version_origin = "draft"
        loop.active_text_source = "candidate_texts"
        session.stage_status.validation_loop.status = "running"
    else:
        loop.active_candidate_id = None
        loop.active_version_id = None
        loop.active_version_origin = None
        loop.active_text_source = None
        session.stage_status.validation_loop.status = "completed"
        session.stage_status.validation_loop.completed_at = _now()
    loop.accepted_count = len(session.validated_candidate_versions)
    loop.selector_eligible_unique_accepted_count = _selector_eligible_accepted_count(session)


def _complete_validation_loop(session: SessionState) -> None:
    loop = session.validation_loop_state
    loop.active_candidate_id = None
    loop.active_version_id = None
    loop.active_version_origin = None
    loop.active_text_source = None
    session.stage_status.validation_loop.status = "completed"
    session.stage_status.validation_loop.completed_at = _now()


def _selector_eligible_accepted_count(session: SessionState) -> int:
    by_candidate = {
        item.candidate_id: item
        for item in session.validated_candidate_versions
        if item.validation_status == "accepted"
    }
    seen_themes: set[str] = set()
    count = 0
    for ranked in sorted(session.ranked_candidates, key=lambda item: item.rank):
        if ranked.hard_gates_passed is not True:
            continue
        version = by_candidate.get(ranked.candidate_id)
        if version is None:
            continue
        normalized_theme = _normalize_theme(version.theme)
        if normalized_theme in seen_themes:
            continue
        seen_themes.add(normalized_theme)
        count += 1
    return count


def _active_text_payload(active: CandidateText | RefinedCandidateVersion) -> dict[str, Any]:
    payload = active.model_dump()
    payload.pop("used_context", None)
    return payload


def _compact_candidate(candidate: CandidateText) -> dict[str, Any]:
    return {
        "candidate_id": candidate.candidate_id,
        "theme": candidate.theme,
        "text": candidate.text,
        "questions": list(candidate.questions),
        "utility_points": list(candidate.utility_points),
        "used_subjects": list(candidate.used_subjects),
        "expected_visual_idea": candidate.expected_visual_idea,
        "status": candidate.status,
    }


def _latest_validation_for_active(session: SessionState) -> ValidationResult:
    loop = session.validation_loop_state
    for validation in reversed(session.validation_results):
        if validation.candidate_id == loop.active_candidate_id and validation.version_id == loop.active_version_id:
            return validation
    raise ValueError("No validation result for active candidate version.")


def _next_refinement_attempt(session: SessionState, candidate_id: str) -> int:
    return 1 + sum(1 for version in session.refined_candidate_versions if version.candidate_id == candidate_id)


def _next_version_id(session: SessionState, candidate_id: str) -> str:
    max_version = 1
    prefix = f"{candidate_id}_v"
    for version in session.refined_candidate_versions:
        if version.candidate_id == candidate_id and version.version_id.startswith(prefix):
            try:
                max_version = max(max_version, int(version.version_id.removeprefix(prefix)))
            except ValueError:
                continue
    return f"{candidate_id}_v{max_version + 1}"


def _has_validated_version(session: SessionState, candidate_id: str, version_id: str) -> bool:
    return any(
        item.candidate_id == candidate_id and item.version_id == version_id
        for item in session.validated_candidate_versions
    )


def _candidate_used_context(session: SessionState, candidate_id: str):
    for candidate in session.candidate_texts:
        if candidate.candidate_id == candidate_id:
            return candidate.used_context
    return session.normalized_request.prompt_context


def _complete_stage(session: SessionState, field_name: str) -> None:
    marker = getattr(session.stage_status, field_name)
    marker.status = "completed"
    marker.completed_at = _now()


def _now() -> str:
    return datetime.now(UTC).isoformat()
