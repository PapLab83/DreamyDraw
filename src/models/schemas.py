import uuid
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, conint

from src.config.settings import settings


class TruthMode(str, Enum):
    TRUTH = "Правда"
    MYTH = "Миф"
    FAIRY_TALE = "Сказка"


class TextStyle(str, Enum):
    GENTLE = "Ласковый"
    EDUCATIONAL = "Познавательный"
    PLAYFUL = "Игровой"


class ImageStyle(str, Enum):
    CARTOON = "Мультяшный"
    WATERCOLOR = "Акварельный"
    CLAY = "Пластилиновый"
    NIGHT = "Ночной/тихий"


class WorkMode(str, Enum):
    FAST = "fast"
    CHECK = "check"


class CompletionStatus(str, Enum):
    RUNNING = "running"
    WAITING_USER = "waiting_user"
    COMPLETED_ENOUGH = "completed_enough"
    COMPLETED_WITH_SHORTAGE = "completed_with_shortage"
    COMPLETED_WITH_SHORTAGE_USER_ACCEPTED = "completed_with_shortage_user_accepted"
    STOPPED_UNRESOLVED_REQUEST = "stopped_unresolved_request"
    STOPPED_BY_USER = "stopped_by_user"
    FAILED = "failed"


class StageStatusValue(str, Enum):
    NOT_STARTED = "not_started"
    COMPLETED = "completed"
    FAILED = "failed"


class ValidationLoopStatus(str, Enum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class SessionRequestUserContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    available: bool = False


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    raw_text: str = ""
    current_config: Dict[str, Any] = Field(default_factory=dict)
    user_context: SessionRequestUserContext = Field(default_factory=SessionRequestUserContext)


class GenerationRequest(BaseModel):
    """Deprecated compatibility request for the old CLI/API entrypoint."""

    model_config = ConfigDict(populate_by_name=True)

    topic: str
    truth_mode: TruthMode = TruthMode.TRUTH
    text_style: TextStyle = TextStyle.EDUCATIONAL
    image_style: ImageStyle = ImageStyle.CARTOON
    work_mode: WorkMode = Field(
        default=WorkMode.FAST,
        validation_alias=AliasChoices("work_mode", "mode"),
    )
    count: int = settings.DEFAULT_COUNT


class PromptLayerRef(BaseModel):
    type: str
    id: str
    source: Optional[str] = None
    reason: Optional[str] = None
    role: Optional[str] = None


class PromptFallbackLayer(BaseModel):
    requested: str
    fallback_layer_id: str
    source: Optional[str] = None
    reason: Optional[str] = None


class PromptUnresolvedDetail(BaseModel):
    label: str
    type: str
    instruction: str


class NormalizedPromptContext(BaseModel):
    resolved_layers: List[PromptLayerRef] = Field(default_factory=list)
    fallback_layers: List[PromptFallbackLayer] = Field(default_factory=list)
    unresolved_details: List[PromptUnresolvedDetail] = Field(default_factory=list)


class ExecutionPromptContext(NormalizedPromptContext):
    frozen_at: Optional[str] = None
    source_hash: Optional[str] = None
    snapshot_hash: Optional[str] = None
    body_policy: str = "metadata_only"
    version: Optional[str] = None


class StagePromptContextEntry(BaseModel):
    stage: str
    candidate_id: Optional[str] = None
    version_id: Optional[str] = None
    attempt: Optional[int] = None
    source_prompt_context_hash: Optional[str] = None
    stage_context_hash: Optional[str] = None
    layer_ids: List[str] = Field(default_factory=list)
    fallback_layer_ids: List[str] = Field(default_factory=list)
    unresolved_detail_labels: List[str] = Field(default_factory=list)
    body_policy: str = "lazy_not_persisted"
    context_summary: Optional[str] = None
    created_at: Optional[str] = None
    version: int = 1


class StagePromptContext(BaseModel):
    entries: List[StagePromptContextEntry] = Field(default_factory=list)


class UserContext(BaseModel):
    available: bool = False
    source: Optional[str] = None
    defaults: Dict[str, Any] = Field(default_factory=dict)
    preferences: Dict[str, Any] = Field(default_factory=dict)
    avoid: List[str] = Field(default_factory=list)
    recent_topics: List[str] = Field(default_factory=list)


class VisualPreferences(BaseModel):
    image_style: Optional[str] = None
    target_device: Optional[str] = None
    visual_output_type: Optional[str] = "single_image_card"


class Subject(BaseModel):
    id: str
    label: str
    type: str
    role: str = "main"
    is_character: bool = False
    base_species: Optional[str] = None
    resolved_layer_id: Optional[str] = None
    unresolved_detail: Optional[str] = None


class Setting(BaseModel):
    place: Optional[str] = None
    season: Optional[str] = None
    time: Optional[str] = None


class CharacterProfile(BaseModel):
    name: Optional[str] = None
    base_subject_id: Optional[str] = None
    stable_traits: List[str] = Field(default_factory=list)
    stable_details: List[str] = Field(default_factory=list)
    speech_style: Optional[str] = None
    must_remain_same_character: bool = True


class SubjectContinuityPolicy(BaseModel):
    mode: str = "unspecified"
    required_subjects: List[str] = Field(default_factory=list)
    coverage: str = "item_level"
    allowed_distribution: str = "all_items"
    can_mix_subjects_in_one_item: bool = True
    can_introduce_new_subjects: bool = True
    can_replace_required_subjects: bool = False


class NormalizedRequest(BaseModel):
    content_format: str = "story"
    truth_mode: Optional[str] = None
    utility_mode: Optional[str] = None
    utility_topic: Optional[str] = None
    target_age: Optional[str] = None
    output_count: int = settings.DEFAULT_COUNT
    audience_language: str = "ru"
    result_language: str = "ru"
    current_config: Dict[str, Any] = Field(default_factory=dict)
    main_subject: Optional[str] = None
    subjects: List[Subject] = Field(default_factory=list)
    setting: Setting = Field(default_factory=Setting)
    text_style_base: Optional[str] = None
    substyle: Optional[str] = None
    character_profile: Optional[CharacterProfile] = None
    subject_continuity_policy: SubjectContinuityPolicy = Field(default_factory=SubjectContinuityPolicy)
    hard_details: List[str] = Field(default_factory=list)
    soft_preferences: List[str] = Field(default_factory=list)
    user_context: UserContext = Field(default_factory=UserContext)
    visual_preferences: VisualPreferences = Field(default_factory=VisualPreferences)
    prompt_context: NormalizedPromptContext = Field(default_factory=NormalizedPromptContext)


class StatusResult(BaseModel):
    status: str = "not_started"
    issues: List[str] = Field(default_factory=list)
    details: Dict[str, Any] = Field(default_factory=dict)


class InterpretationState(BaseModel):
    confidence: Dict[str, conint(ge=0, le=100)] = Field(default_factory=dict)
    classification: Optional[str] = None
    requires_clarification: bool = False
    clarification_reason: Optional[str] = None
    clarification_options: List[str] = Field(default_factory=list)
    clarification_attempts: int = 0
    max_clarification_attempts: int = 5
    lookup_hints: Dict[str, Any] = Field(default_factory=dict)
    validation_result: StatusResult = Field(default_factory=StatusResult)
    execution_lookup_result: StatusResult = Field(default_factory=StatusResult)
    stop_reason: Optional[str] = None
    stop_issues: List[str] = Field(default_factory=list)
    stopped_at: Optional[str] = None


class PreviewState(BaseModel):
    preview_text: Optional[str] = None
    shown_to_user: bool = False
    accepted_by_user: bool = False
    shown_at: Optional[str] = None
    accepted_at: Optional[str] = None


class StageMarker(BaseModel):
    status: StageStatusValue = StageStatusValue.NOT_STARTED
    completed_at: Optional[str] = None
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None


class ValidationLoopMarker(BaseModel):
    status: ValidationLoopStatus = ValidationLoopStatus.NOT_STARTED
    completed_at: Optional[str] = None
    input_hash: Optional[str] = None
    output_hash: Optional[str] = None


class StageStatus(BaseModel):
    candidate_text_generator: StageMarker = Field(default_factory=StageMarker)
    topic_deduplicator: StageMarker = Field(default_factory=StageMarker)
    scorer: StageMarker = Field(default_factory=StageMarker)
    ranker: StageMarker = Field(default_factory=StageMarker)
    validation_loop: ValidationLoopMarker = Field(default_factory=ValidationLoopMarker)
    approved_text_selector: StageMarker = Field(default_factory=StageMarker)


class CandidateText(BaseModel):
    candidate_id: str
    theme: str = ""
    text: str = ""
    questions: List[str] = Field(default_factory=list)
    used_subjects: List[str] = Field(default_factory=list)
    utility_points: List[str] = Field(default_factory=list)
    expected_visual_idea: Optional[str] = None
    used_context: NormalizedPromptContext = Field(default_factory=NormalizedPromptContext)
    status: str = "draft"


class DeduplicationResult(BaseModel):
    candidate_id: str
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None
    reason: Optional[str] = None


class CandidateScore(BaseModel):
    candidate_id: str
    hard_gates: Dict[str, str] = Field(default_factory=dict)
    score_components: Dict[str, float] = Field(default_factory=dict)
    total_score: Optional[float] = None


class RankedCandidate(BaseModel):
    candidate_id: str
    rank: int
    total_score: Optional[float] = None
    hard_gates_passed: bool = False


class ValidationIssue(BaseModel):
    type: str
    severity: str
    description: str


class ValidationResult(BaseModel):
    candidate_id: str
    version_id: Optional[str] = None
    status: Literal["accepted", "needs_revision", "rejected"] = "needs_revision"
    issues: List[ValidationIssue] = Field(default_factory=list)
    required_fixes: List[str] = Field(default_factory=list)
    summary: Optional[str] = None


class RefinedCandidateVersion(BaseModel):
    candidate_id: str
    version_id: str
    source_version_id: Optional[str] = None
    theme: str = ""
    text: str = ""
    questions: List[str] = Field(default_factory=list)
    changes_summary: Optional[str] = None
    status: str = "revised"


class ValidatedCandidateVersion(BaseModel):
    candidate_id: str
    version_id: str
    source: Literal["candidate", "refinement"] = "candidate"
    theme: str = ""
    text: str = ""
    questions: List[str] = Field(default_factory=list)
    validation_status: Literal["accepted", "needs_revision", "rejected"] = "accepted"
    validation_summary: Optional[str] = None
    used_context: NormalizedPromptContext = Field(default_factory=NormalizedPromptContext)
    trace_refs: Dict[str, Any] = Field(default_factory=dict)


class ApprovedText(BaseModel):
    candidate_id: str
    version_id: Optional[str] = None
    theme: str = ""
    text: str = ""
    questions: List[str] = Field(default_factory=list)
    score: Optional[float] = None
    validation_status: str = "accepted"
    validation_summary: Optional[str] = None
    used_context: NormalizedPromptContext = Field(default_factory=NormalizedPromptContext)
    trace_refs: Dict[str, Any] = Field(default_factory=dict)


class SafeFallbackCandidate(BaseModel):
    candidate_id: str
    theme: str = ""
    text: str = ""
    questions: List[str] = Field(default_factory=list)
    score: Optional[float] = None
    why_safe: str = ""
    known_issues: List[str] = Field(default_factory=list)


class ShortageState(BaseModel):
    requested: int = 0
    approved: int = 0
    status: str = "not_started"
    reason: Optional[str] = None
    failure_details: Dict[str, Any] = Field(default_factory=dict)


class ValidationLoopState(BaseModel):
    current_rank_index: Optional[int] = None
    active_candidate_id: Optional[str] = None
    active_version_id: Optional[str] = None
    active_version_origin: Optional[Literal["draft", "refined"]] = None
    active_text_source: Optional[Literal["candidate_texts", "refined_candidate_versions"]] = None
    accepted_count: int = 0
    selector_eligible_unique_accepted_count: int = 0
    candidate_attempts: Dict[str, int] = Field(default_factory=dict)
    max_refinement_attempts_per_candidate: int = 2


class PipelineCounters(BaseModel):
    generated_candidates: int = 0
    deduplicated_candidates: int = 0
    scored_candidates: int = 0
    ranked_candidates: int = 0
    validation_attempts: int = 0
    refinement_attempts: int = 0
    approved_texts: int = 0
    safe_fallback_candidates: int = 0


class PendingInterrupt(BaseModel):
    type: str
    node: str
    status: str = "waiting"
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    attempt: int = 1
    resume_schema: Dict[str, Any] = Field(default_factory=dict)
    resume_token: Optional[str] = None


class StoryItem(BaseModel):
    """Deprecated compatibility model for the legacy story/image flow."""

    index: int
    sub_topic: str = ""
    text: str = ""
    image_path: Optional[str] = None
    questions: List[str] = Field(default_factory=list)
    is_confirmed: bool = False
    validation_notes: List[str] = Field(default_factory=list)
    retry_count: int = 0


class Idea(BaseModel):
    """Deprecated compatibility model for the legacy planning flow."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    summary: str
    child_index: float = 0.0
    normalized_weight: float = 0.0
    is_selected: bool = False


class SessionState(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request: Union[SessionRequest, GenerationRequest]
    current_node: str = "start"
    is_completed: bool = False
    completion_status: CompletionStatus = CompletionStatus.RUNNING

    normalized_request: NormalizedRequest = Field(default_factory=NormalizedRequest)
    interpretation_state: InterpretationState = Field(default_factory=InterpretationState)
    preview_state: PreviewState = Field(default_factory=PreviewState)
    stage_status: StageStatus = Field(default_factory=StageStatus)
    prompt_context: ExecutionPromptContext = Field(default_factory=ExecutionPromptContext)
    stage_prompt_context: StagePromptContext = Field(default_factory=StagePromptContext)
    candidate_texts: List[CandidateText] = Field(default_factory=list)
    deduplication_results: List[DeduplicationResult] = Field(default_factory=list)
    scores: List[CandidateScore] = Field(default_factory=list)
    ranked_candidates: List[RankedCandidate] = Field(default_factory=list)
    validation_results: List[ValidationResult] = Field(default_factory=list)
    refined_candidate_versions: List[RefinedCandidateVersion] = Field(default_factory=list)
    validated_candidate_versions: List[ValidatedCandidateVersion] = Field(default_factory=list)
    approved_texts: List[ApprovedText] = Field(default_factory=list)
    shortage: ShortageState = Field(default_factory=ShortageState)
    safe_fallback_candidates: List[SafeFallbackCandidate] = Field(default_factory=list)
    validation_loop_state: ValidationLoopState = Field(default_factory=ValidationLoopState)
    pipeline_counters: PipelineCounters = Field(default_factory=PipelineCounters)
    trace_refs: Dict[str, Any] = Field(default_factory=dict)
    pending_interrupt: Optional[PendingInterrupt] = None

    # Deprecated compatibility fields for the previous orchestration model.
    series_plan: List[str] = Field(default_factory=list)
    global_context: str = ""
    ideas_pool: List[Idea] = Field(default_factory=list)
    stories: List[StoryItem] = Field(default_factory=list)
    current_step: int = 0
    approved_plan_items: Dict[str, Any] = Field(default_factory=dict)
    full_plan_items: List[Dict[str, Any]] = Field(default_factory=list)
    user_feedback: Optional[str] = None
    validator_feedback: str = "{}"
    approved_indices: List[int] = Field(default_factory=list)
    validation_cycles: int = 0
    pending_revisions: List[Any] = Field(default_factory=list)
    revision_history: Dict[str, Any] = Field(default_factory=dict)

    @property
    def plan_retry_counts(self) -> dict:
        """Backward-compatible alias for older debug scripts."""
        return {"validation_cycles": self.validation_cycles}
