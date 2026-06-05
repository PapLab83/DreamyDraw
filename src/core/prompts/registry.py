from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from src.core.prompts.models import (
    ALLOWED_TYPES,
    LANGUAGE_ROLES,
    REQUIRED_FIELDS,
    UTILITY_ROLES,
    PromptLayerMetadata,
)


class PromptRegistryError(ValueError):
    pass


def normalize_lookup_term(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold().strip()
    return re.sub(r"\s+", " ", normalized)


class PromptRegistry:
    def __init__(
        self,
        *,
        root: Path,
        layers_by_id: dict[str, PromptLayerMetadata],
        bodies_by_id: dict[str, str],
    ) -> None:
        self.root = root
        self.layers_by_id = layers_by_id
        self._bodies_by_id = bodies_by_id
        self.by_type = _index_many(layers_by_id.values(), "type")
        self.by_role = _index_many(
            (layer for layer in layers_by_id.values() if layer.role),
            "role",
        )
        self.by_namespace = _index_many(layers_by_id.values(), "namespace")
        self.by_alias = self._build_alias_index(layers_by_id.values())
        self.by_applies_to = self._build_applies_to_index(layers_by_id.values())
        self.by_source = {layer.source: layer.id for layer in layers_by_id.values()}
        self.registry_hash = _hash_text(
            "\n".join(
                f"{layer.source}:{layer.id}:{layer.source_hash}"
                for layer in sorted(layers_by_id.values(), key=lambda item: item.source)
            )
        )

    @classmethod
    def load(cls, root: str | Path) -> PromptRegistry:
        prompt_root = Path(root)
        if not prompt_root.exists():
            raise PromptRegistryError(f"Prompt root does not exist: {prompt_root}")

        layers_by_id: dict[str, PromptLayerMetadata] = {}
        bodies_by_id: dict[str, str] = {}

        for path in sorted(prompt_root.rglob("*.md"), key=lambda item: item.as_posix()):
            metadata, body = _parse_prompt_file(prompt_root, path)
            prompt_id = metadata.id
            if prompt_id in layers_by_id:
                raise PromptRegistryError(f"Duplicate prompt id: {prompt_id}")
            layers_by_id[prompt_id] = metadata
            bodies_by_id[prompt_id] = body

        return cls(root=prompt_root, layers_by_id=layers_by_id, bodies_by_id=bodies_by_id)

    def __len__(self) -> int:
        return len(self.layers_by_id)

    def __iter__(self):
        return iter(self.list_metadata())

    def get(self, layer_id: str) -> PromptLayerMetadata:
        try:
            return self.layers_by_id[layer_id]
        except KeyError as exc:
            raise KeyError(f"Unknown prompt layer id: {layer_id}") from exc

    def list_metadata(self) -> list[PromptLayerMetadata]:
        return sorted(self.layers_by_id.values(), key=lambda item: item.source)

    def get_body(self, layer_id: str) -> str:
        self.get(layer_id)
        return self._bodies_by_id[layer_id]

    def source_exists(self, layer_id: str) -> bool:
        layer = self.get(layer_id)
        return (self.root / layer.source).is_file()

    def verify_source(self, layer_id: str, source: str | None) -> bool:
        if source is None:
            return True
        layer = self.get(layer_id)
        return layer.source == source and (self.root / source).is_file()

    @staticmethod
    def _build_alias_index(
        layers: list[PromptLayerMetadata] | Any,
    ) -> dict[str, list[str]]:
        index: dict[str, list[str]] = defaultdict(list)
        for layer in layers:
            for alias in layer.aliases:
                normalized = normalize_lookup_term(alias)
                if layer.id not in index[normalized]:
                    index[normalized].append(layer.id)
        return {key: sorted(value) for key, value in index.items()}

    @staticmethod
    def _build_applies_to_index(
        layers: list[PromptLayerMetadata] | Any,
    ) -> dict[tuple[str, str], list[str]]:
        index: dict[tuple[str, str], list[str]] = defaultdict(list)
        for layer in layers:
            for field_name, values in layer.applies_to.items():
                for value in values:
                    index[(field_name, str(value))].append(layer.id)
        return {key: sorted(value) for key, value in index.items()}


def _parse_prompt_file(root: Path, path: Path) -> tuple[PromptLayerMetadata, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise PromptRegistryError(f"Missing YAML front matter: {path}")
    try:
        _, raw_yaml, body = text.split("---\n", 2)
    except ValueError as exc:
        raise PromptRegistryError(f"Missing closing YAML front matter: {path}") from exc

    raw_metadata = yaml.safe_load(raw_yaml)
    if not isinstance(raw_metadata, dict):
        raise PromptRegistryError(f"YAML front matter must be a mapping: {path}")

    _validate_metadata(raw_metadata, path)
    source = path.relative_to(root).as_posix()
    source_hash = _hash_text(text)
    metadata_hash = _hash_text(
        json.dumps(raw_metadata, ensure_ascii=False, sort_keys=True, default=str)
    )
    body_hash = _hash_text(body)
    known_fields = REQUIRED_FIELDS | {
        "role",
        "user_description",
        "good_for",
        "bad_for",
        "fallback_priority",
        "requires_user_confirmation",
        "example_result_ids",
        "sample_text",
        "safety_notes",
    }

    metadata = PromptLayerMetadata(
        id=str(raw_metadata["id"]),
        type=str(raw_metadata["type"]),
        role=_optional_str(raw_metadata.get("role")),
        namespace=str(raw_metadata["namespace"]),
        name=str(raw_metadata["name"]),
        aliases=tuple(str(item) for item in raw_metadata["aliases"]),
        applies_to=_normalize_applies_to(raw_metadata["applies_to"]),
        short_description=str(raw_metadata["short_description"]),
        constraints=tuple(str(item) for item in raw_metadata["constraints"]),
        source=source,
        source_hash=source_hash,
        metadata_hash=metadata_hash,
        body_hash=body_hash,
        user_description=_optional_str(raw_metadata.get("user_description")),
        good_for=_tuple_of_strings(raw_metadata.get("good_for", [])),
        bad_for=_tuple_of_strings(raw_metadata.get("bad_for", [])),
        fallback_priority=raw_metadata.get("fallback_priority"),
        requires_user_confirmation=raw_metadata.get("requires_user_confirmation"),
        example_result_ids=_tuple_of_strings(raw_metadata.get("example_result_ids", [])),
        sample_text=_optional_str(raw_metadata.get("sample_text")),
        safety_notes=_tuple_of_strings(raw_metadata.get("safety_notes", [])),
        extra_metadata={
            key: value for key, value in raw_metadata.items() if key not in known_fields
        },
    )
    return metadata, body


def _validate_metadata(metadata: dict[str, Any], path: Path) -> None:
    missing = REQUIRED_FIELDS - metadata.keys()
    if missing:
        raise PromptRegistryError(
            f"Missing required metadata in {path}: {sorted(missing)}"
        )

    prompt_type = metadata["type"]
    if prompt_type not in ALLOWED_TYPES:
        raise PromptRegistryError(f"Unsupported prompt type in {path}: {prompt_type!r}")

    if not isinstance(metadata["aliases"], list) or not metadata["aliases"]:
        raise PromptRegistryError(f"aliases must be a non-empty list: {path}")
    if not isinstance(metadata["constraints"], list) or not metadata["constraints"]:
        raise PromptRegistryError(f"constraints must be a non-empty list: {path}")
    if not isinstance(metadata["applies_to"], dict):
        raise PromptRegistryError(f"applies_to must be a mapping: {path}")

    _validate_seed_role(prompt_type=str(prompt_type), role=metadata.get("role"), path=path)


def _validate_seed_role(prompt_type: str, role: str | None, path: Path) -> None:
    if prompt_type == "format" and role != "content_format":
        raise PromptRegistryError(f"Invalid role for {path}: format requires content_format")
    if prompt_type == "utility" and role not in UTILITY_ROLES:
        raise PromptRegistryError(f"Invalid role for {path}: utility requires utility role")
    if prompt_type == "language" and role not in LANGUAGE_ROLES:
        raise PromptRegistryError(f"Invalid role for {path}: language requires language role")
    if prompt_type == "stage" and not role:
        raise PromptRegistryError(f"Invalid role for {path}: stage requires role")
    if prompt_type == "validator" and role != "candidate_validator":
        raise PromptRegistryError(
            f"Invalid role for {path}: validator requires candidate_validator"
        )
    if prompt_type == "refiner" and role != "candidate_refiner":
        raise PromptRegistryError(
            f"Invalid role for {path}: refiner requires candidate_refiner"
        )


def _index_many(
    layers: list[PromptLayerMetadata] | Any,
    attribute: str,
) -> dict[str, list[str]]:
    index: dict[str, list[str]] = defaultdict(list)
    for layer in layers:
        value = getattr(layer, attribute)
        if value:
            index[str(value)].append(layer.id)
    return {key: sorted(value) for key, value in index.items()}


def _normalize_applies_to(value: dict[str, Any]) -> dict[str, list[str]]:
    normalized: dict[str, list[str]] = {}
    for key, nested_value in value.items():
        if isinstance(nested_value, list):
            normalized[str(key)] = [str(item) for item in nested_value]
        else:
            normalized[str(key)] = [str(nested_value)]
    return normalized


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def _tuple_of_strings(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return (str(value),)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
