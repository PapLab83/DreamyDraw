from __future__ import annotations

from typing import Any

from src.core.prompts.models import (
    ExecutionLookupEnvelope,
    MetadataLookupCandidate,
    PromptLayerMetadata,
)
from src.core.prompts.registry import PromptRegistry, normalize_lookup_term


def lookup_prompt_metadata(
    registry: PromptRegistry,
    *,
    user_terms: list[str] | None = None,
    type: str | None = None,
    role: str | None = None,
    applicability: dict[str, str] | None = None,
    fallback: bool = False,
    limit: int = 10,
) -> list[MetadataLookupCandidate]:
    if type and type not in registry.by_type:
        return []
    if role and role not in registry.by_role:
        return []

    candidates = registry.list_metadata()
    if type:
        allowed_ids = set(registry.by_type[type])
        candidates = [layer for layer in candidates if layer.id in allowed_ids]
    if role:
        allowed_ids = set(registry.by_role[role])
        candidates = [layer for layer in candidates if layer.id in allowed_ids]

    terms = [normalize_lookup_term(term) for term in user_terms or [] if term.strip()]
    scored: dict[str, MetadataLookupCandidate] = {}

    for layer in candidates:
        match = _match_layer(layer, terms)
        if match is None:
            if not fallback:
                continue
            match_level = "fallback"
            score = _fallback_score(layer)
            reason = "fallback candidate"
        else:
            match_level, score, reason = match

        applicability_status = _applicability_status(layer, applicability or {})
        candidate = MetadataLookupCandidate(
            layer_id=layer.id,
            type=layer.type,
            role=layer.role,
            source=layer.source,
            match_level=match_level,
            match_score=score,
            match_reason=reason,
            applicability_status=applicability_status,
            ambiguity_group_id=_ambiguity_group_id(layer),
            short_description=layer.short_description,
        )
        scored[layer.id] = candidate

    return sorted(
        scored.values(),
        key=lambda item: (-item.match_score, item.source, item.layer_id),
    )[:limit]


def execute_prompt_lookup(
    registry: PromptRegistry,
    *,
    resolved_layers: list[dict[str, Any]] | None = None,
    fallback_layers: list[dict[str, Any]] | None = None,
    unresolved_details: list[dict[str, Any]] | None = None,
) -> ExecutionLookupEnvelope:
    resolved_payload: list[dict[str, Any]] = []
    fallback_payload: list[dict[str, Any]] = []
    unresolved_payload = list(unresolved_details or [])

    for layer_ref in resolved_layers or []:
        layer_id = layer_ref.get("id")
        failure = _verify_layer_ref(registry, layer_ref, layer_id_key="id")
        if failure:
            return failure
        layer = registry.get(layer_id)
        resolved_payload.append(_enrich_layer_ref(layer_ref, layer))

    for fallback_ref in fallback_layers or []:
        layer_id = fallback_ref.get("fallback_layer_id")
        failure = _verify_layer_ref(
            registry,
            fallback_ref,
            layer_id_key="fallback_layer_id",
        )
        if failure:
            return failure
        layer = registry.get(layer_id)
        fallback_payload.append(_enrich_fallback_ref(fallback_ref, layer))

    return ExecutionLookupEnvelope(
        status="pass",
        resolved_layers=tuple(resolved_payload),
        fallback_layers=tuple(fallback_payload),
        unresolved_details=unresolved_payload,
    )


def _match_layer(
    layer: PromptLayerMetadata,
    normalized_terms: list[str],
) -> tuple[str, float, str] | None:
    if not normalized_terms:
        return None

    layer_id = normalize_lookup_term(layer.id)
    name = normalize_lookup_term(layer.name)
    aliases = {normalize_lookup_term(alias): alias for alias in layer.aliases}

    for term in normalized_terms:
        if term == layer_id:
            return ("exact", 1.0, f"id match: {layer.id}")
        if term == name:
            return ("name", 0.96, f"name match: {layer.name}")
        if term in aliases:
            return ("alias", 0.92, f"alias match: {aliases[term]}")
    for term in normalized_terms:
        if term and term in name:
            return ("name", 0.82, f"name contains: {term}")
        for alias, original_alias in aliases.items():
            if term and term in alias:
                return ("alias", 0.78, f"alias contains: {original_alias}")
    return None


def _fallback_score(layer: PromptLayerMetadata) -> float:
    priority = layer.fallback_priority if layer.fallback_priority is not None else 0
    return 0.4 + min(priority, 100) / 1000


def _applicability_status(
    layer: PromptLayerMetadata,
    requested: dict[str, str],
) -> str:
    if not requested:
        return "applicable"
    matches = 0
    checked = 0
    for key, value in requested.items():
        if key not in layer.applies_to:
            continue
        checked += 1
        if str(value) in layer.applies_to[key]:
            matches += 1
    if checked == 0 or matches == checked:
        return "applicable"
    if matches:
        return "partially_applicable"
    return "not_applicable"


def _ambiguity_group_id(layer: PromptLayerMetadata) -> str:
    namespace_tail = layer.namespace.rsplit("/", maxsplit=1)[-1]
    return f"{layer.type}:{layer.role or namespace_tail}"


def _verify_layer_ref(
    registry: PromptRegistry,
    layer_ref: dict[str, Any],
    *,
    layer_id_key: str,
) -> ExecutionLookupEnvelope | None:
    layer_id = layer_ref.get(layer_id_key)
    if not layer_id or layer_id not in registry.layers_by_id:
        return _failure(
            "missing_layer_id",
            layer_id,
            layer_ref.get("source"),
            "Resolved layer id is not present in PromptRegistry.",
        )

    layer = registry.get(layer_id)
    expected_source = layer_ref.get("source")
    if not expected_source:
        return _failure(
            "missing_source",
            layer_id,
            None,
            "Resolved layer source is missing.",
        )
    if expected_source != layer.source:
        return _failure(
            "missing_source",
            layer_id,
            expected_source,
            "Resolved layer source does not match registry source.",
        )
    expected_type = layer_ref.get("type")
    if expected_type and expected_type != layer.type:
        return _failure(
            "metadata_mismatch",
            layer_id,
            expected_source,
            "Resolved layer type does not match registry metadata.",
        )
    expected_role = layer_ref.get("role")
    if expected_role and expected_role != layer.role:
        return _failure(
            "metadata_mismatch",
            layer_id,
            expected_source,
            "Resolved layer role does not match registry metadata.",
        )
    if not registry.source_exists(layer_id):
        return _failure(
            "missing_source",
            layer_id,
            expected_source or layer.source,
            "Resolved layer source file is missing.",
        )

    expected_hash = layer_ref.get("source_hash")
    if expected_hash and expected_hash != layer.source_hash:
        return _failure(
            "stale_source_hash",
            layer_id,
            expected_source or layer.source,
            "Resolved layer source hash is stale.",
        )
    return None


def _failure(
    failure_type: str,
    layer_id: str | None,
    source: str | None,
    issue: str,
) -> ExecutionLookupEnvelope:
    return ExecutionLookupEnvelope(
        status="fail_reresolve",
        failure_type=failure_type,
        failed_layer_id=layer_id,
        failed_source=source,
        issues=(issue,),
        route_reason=failure_type,
    )


def _enrich_layer_ref(
    layer_ref: dict[str, Any],
    layer: PromptLayerMetadata,
) -> dict[str, Any]:
    enriched = dict(layer_ref)
    enriched.setdefault("type", layer.type)
    enriched.setdefault("role", layer.role)
    enriched.setdefault("source", layer.source)
    enriched["source_hash"] = layer.source_hash
    enriched["metadata_hash"] = layer.metadata_hash
    return enriched


def _enrich_fallback_ref(
    fallback_ref: dict[str, Any],
    layer: PromptLayerMetadata,
) -> dict[str, Any]:
    enriched = dict(fallback_ref)
    enriched.setdefault("source", layer.source)
    enriched["source_hash"] = layer.source_hash
    enriched["metadata_hash"] = layer.metadata_hash
    return enriched
