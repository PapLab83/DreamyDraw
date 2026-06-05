from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TYPE_CHECKING

if TYPE_CHECKING:
    from src.models.schemas import StagePromptContextEntry

PromptType = Literal[
    "format",
    "truth_mode",
    "style",
    "substyle",
    "entity",
    "utility",
    "age",
    "language",
    "stage",
    "validator",
    "refiner",
]

MatchLevel = Literal["exact", "name", "alias", "fallback"]
ApplicabilityStatus = Literal[
    "applicable",
    "partially_applicable",
    "not_applicable",
]
ExecutionLookupStatus = Literal[
    "pass",
    "fail_reresolve",
    "fail_clarify",
    "fail_stop",
]


ALLOWED_TYPES: set[str] = {
    "age",
    "entity",
    "format",
    "language",
    "refiner",
    "stage",
    "style",
    "substyle",
    "truth_mode",
    "utility",
    "validator",
}

REQUIRED_FIELDS: set[str] = {
    "id",
    "type",
    "namespace",
    "name",
    "aliases",
    "applies_to",
    "short_description",
    "constraints",
}

UTILITY_ROLES = {"utility_mode", "utility_topic"}
LANGUAGE_ROLES = {"audience_language", "result_language"}


@dataclass(frozen=True)
class PromptLayerMetadata:
    id: str
    type: str
    role: str | None
    namespace: str
    name: str
    aliases: tuple[str, ...]
    applies_to: dict[str, list[str]]
    short_description: str
    constraints: tuple[str, ...]
    source: str
    source_hash: str
    metadata_hash: str
    body_hash: str
    user_description: str | None = None
    good_for: tuple[str, ...] = ()
    bad_for: tuple[str, ...] = ()
    fallback_priority: int | None = None
    requires_user_confirmation: bool | None = None
    example_result_ids: tuple[str, ...] = ()
    sample_text: str | None = None
    safety_notes: tuple[str, ...] = ()
    extra_metadata: dict[str, Any] = field(default_factory=dict)

    def compact_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "role": self.role,
            "namespace": self.namespace,
            "name": self.name,
            "aliases": list(self.aliases),
            "applies_to": self.applies_to,
            "short_description": self.short_description,
            "constraints": list(self.constraints),
            "source": self.source,
            "source_hash": self.source_hash,
            "metadata_hash": self.metadata_hash,
            "body_hash": self.body_hash,
            "fallback_priority": self.fallback_priority,
        }


@dataclass(frozen=True)
class MetadataLookupCandidate:
    layer_id: str
    type: str
    role: str | None
    source: str
    match_level: MatchLevel
    match_score: float
    match_reason: str
    applicability_status: ApplicabilityStatus
    ambiguity_group_id: str
    short_description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "layer_id": self.layer_id,
            "type": self.type,
            "role": self.role,
            "source": self.source,
            "match_level": self.match_level,
            "match_score": self.match_score,
            "match_reason": self.match_reason,
            "applicability_status": self.applicability_status,
            "ambiguity_group_id": self.ambiguity_group_id,
            "short_description": self.short_description,
        }


@dataclass(frozen=True)
class ExecutionLookupEnvelope:
    status: ExecutionLookupStatus
    failure_type: str | None = None
    failed_layer_id: str | None = None
    failed_source: str | None = None
    issues: tuple[str, ...] = ()
    route_reason: str | None = None
    resolved_layers: tuple[dict[str, Any], ...] = ()
    fallback_layers: tuple[dict[str, Any], ...] = ()
    unresolved_details: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "failure_type": self.failure_type,
            "failed_layer_id": self.failed_layer_id,
            "failed_source": self.failed_source,
            "issues": list(self.issues),
            "route_reason": self.route_reason,
            "resolved_layers": list(self.resolved_layers),
            "fallback_layers": list(self.fallback_layers),
            "unresolved_details": self.unresolved_details,
        }


@dataclass(frozen=True)
class StagePromptContextBuild:
    durable_entry: "StagePromptContextEntry"
    runtime_context: dict[str, Any]
