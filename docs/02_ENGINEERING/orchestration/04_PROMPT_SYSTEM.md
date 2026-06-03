# Prompt System

## Prompt System

### Prompt file format

Every prompt layer is one `.md` file:

```markdown
---
id: TRUTH_ANIMAL_HEDGEHOG
type: entity
namespace: truth_modes/TRUTH/characters/animals
name: Ёжик
aliases:
  - ёж
  - ежик
  - hedgehog
applies_to:
  content_formats: [story]
  truth_modes: [TRUTH]
  utility_modes: [NARRATIVE, TEACHING]
  ages: ["3", "5"]
short_description: Ёжик, его поведение, среда обитания и безопасные факты.
constraints:
  - Не приписывать ёжику человеческую речь в режиме TRUTH.
fallback_priority: 80
---

# Назначение слоя

...
```

Required metadata:

- `id`;
- `type`;
- `namespace`;
- `name`;
- `aliases`;
- `applies_to`;
- `short_description`;
- `constraints`.

Optional metadata:

- `user_description`;
- `good_for`;
- `bad_for`;
- `fallback_priority`;
- `requires_user_confirmation`;
- `sample_text`;
- `example_result_ids`;
- `safety_notes`.

### PromptRegistry

Responsibilities:

- scan prompt directories;
- parse YAML metadata;
- provide prompt body loading by layer id/source when requested by `PromptComposer`;
- validate required fields;
- validate unique `id`;
- store deterministic layer indexes by id, type, role, namespace, alias, applicability and prompt source hash;
- return metadata lookup candidates;
- return execution lookup results;
- cache parsed metadata by file hash or mtime;
- compute and expose metadata/body hashes for execution snapshots and prompt traces.

Boundary:

- `PromptRegistry` owns prompt file parsing, metadata indexing and low-level body retrieval.
- `PromptRegistry` does not decide stage composition and does not build per-stage prompt contexts.
- Stage nodes must not read prompt `.md` files directly; they receive stage context through `PromptComposer`.
- `PromptRegistry` may scan the full prompt base locally, but it must expose compact lookup candidates to nodes/LLM-assisted steps rather than dumping the full registry metadata.

Lookup levels:

1. exact match by id/name;
2. alias match;
3. fallback by applicability and priority;
4. unresolved detail.

Ambiguity rules:

- `PromptRegistry` must not auto-pick between multiple applicable exact/name/alias matches with close confidence when the choice can change user-facing meaning.
- Multiple applicable matches are returned as ambiguity candidates to metadata lookup and stored in `interpretation_state.lookup_hints`.
- `request_classification` decides whether the ambiguity requires clarification.
- `fallback_priority` may break ties only when candidates are in the same semantic family and the selected fallback does not materially change user intent.
- If tie-breaking would change preview semantics, route through clarification rather than choosing silently.
- The close-confidence threshold is configuration owned by metadata lookup policy; `PromptRegistry` returns candidate scores, match reasons and applicability notes, not a final user-facing choice.

Minimum match candidate schema-like shape:

```text
{
  "layer_id": "TRUTH_ANIMAL_PARROT",
  "match_level": "exact|name|alias|fallback",
  "match_score": 0.92,
  "match_reason": "alias match: попугай",
  "applicability_status": "applicable|partially_applicable|not_applicable",
  "ambiguity_group_id": "subject:parrot"
}
```

### Metadata lookup

Used before preview.

Purpose:

- understand available modes, utility modes/topics, audience/result languages, styles/substyles and entities;
- avoid promising unsupported stylization;
- find teaching-topic and language layer candidates before preview;
- identify fallback candidates;
- decide whether user clarification is needed.

It must not load full prompt bodies.

Registry-index narrowing:

- Metadata lookup is registry-index based.
- It must not pass the full prompt registry metadata to the LLM.
- It first narrows candidates deterministically by draft request fields, user terms, `type`, `role`, aliases, namespace, `applies_to`, fallback priority and applicability.
- Only compact candidate sets may be passed to an LLM-assisted disambiguation step.
- Compact candidates include ids, type/role, short descriptions, aliases or matched terms, match reasons, applicability notes and fallback notes.
- Full prompt bodies are not loaded during metadata lookup.
- If deterministic narrowing finds one exact applicable candidate, no LLM disambiguation is required.
- If deterministic narrowing finds multiple close candidates whose choice changes user-facing meaning, store ambiguity in `interpretation_state.lookup_hints` and let `request_classification` decide clarification.

### Execution lookup

Used after request is complete enough to execute and after `candidate_layer_resolution` has already written `normalized_request.prompt_context`.

Output:

```json
{
  "status": "pass",
  "failure_type": null,
  "failed_layer_id": null,
  "failed_source": null,
  "issues": [],
  "route_reason": null,
  "resolved_layers": [],
  "fallback_layers": [],
  "unresolved_details": []
}
```

Execution lookup/preparation materializes and verifies the already resolved `normalized_request.prompt_context` into top-level `session.prompt_context`.

Rules:

- It returns a status envelope compatible with `interpretation_state.execution_lookup_result`.
- `status` must be one of `pass`, `fail_reresolve`, `fail_clarify`, `fail_stop`.
- `resolved_layers`, `fallback_layers` and `unresolved_details` are payload fields, not a replacement for verification status.
- It may add source refs, hashes, `frozen_at`, version and runtime metadata.
- It must not choose different layer ids.
- It must not choose different fallback layers.
- It must not change unresolved details.
- It must not change the interpretation shown in preview.
- If verification fails, route via `pass`, `fail_reresolve`, `fail_clarify` or `fail_stop` as defined in `prompt_context_preparation`.
- It must not silently swap to a different prompt layer to recover from missing source, invalid metadata or stale hashes.

### PromptComposer

Responsibilities:

- build stage-specific prompt context;
- lazy-load prompt bodies through `PromptRegistry` or a dedicated `PromptBodyStore` when needed;
- preserve layer ordering;
- include hard constraints before soft preferences;
- include unresolved details as freeform context, not guaranteed layer knowledge;
- generate compact debug summaries and hashes.

Boundary:

- `PromptComposer` owns stage context assembly.
- When a stage requires full prompt body text, `PromptComposer` requests bodies by layer id/source, computes body/context hashes and returns a runtime context object to the node.
- If a dedicated `PromptBodyStore` exists, it is an internal dependency/adapter used by `PromptRegistry` and/or `PromptComposer`.
- `SessionState.stage_prompt_context` stores ids, hashes, summaries and refs by default, not full prompt bodies.
- Full prompt text may be sent to LLM calls and Langfuse/debug artifacts only according to prompt logging policy.
- Stage nodes must not assemble prompt layers ad hoc or bypass `PromptComposer`.

General layer priority:

1. content format;
2. truth mode;
3. utility mode;
4. utility topic layer, when `utility_mode = TEACHING` or another mode has a concrete utility goal;
5. target age;
6. audience language;
7. result language;
8. style/substyle;
9. entity/subject;
10. hard details;
11. soft preferences;
12. unresolved details;
13. stage-specific instructions;
14. output contract.

Правила:

- `utility mode` отвечает за общий тип пользы (`NARRATIVE`, `TEACHING` и т.д.).
- `utility_topic_layer` отвечает за конкретную обучающую/прикладную тему, например stranger/candy safety, hygiene, road crossing.
- `audience_language` задаёт язык понимания пользователя/ребёнка и может влиять на age wording, vocabulary и clarification phrasing.
- `result_language` задаёт язык итоговых текстов.
- Если `audience_language` и `result_language` совпадают, PromptComposer всё равно сохраняет обе layer decisions или явную ссылку на общий language layer, чтобы lookup trace был однозначным.

Stage context profiles:

| Stage | Context |
| --- | --- |
| CandidateTextGenerator | Full creative context. |
| TopicDeduplicator | Themes, subjects, continuity policy, similarity criteria. |
| Scorer | Hard gates, score components, compact layer summaries. |
| Validator | One candidate, constraints, output contract. |
| Refiner | Candidate, validator issues, immutable fields, repair instructions. |
| Ranker | Usually deterministic ranking policy. |
| ApprovedTextSelector | Validated versions, validation results, output_count, shortage policy. |

---
