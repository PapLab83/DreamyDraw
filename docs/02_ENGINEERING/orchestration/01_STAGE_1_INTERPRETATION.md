# Stage 1 Interpretation

> **MVP note (Stage 1–2):** Сейчас нода `input_analysis` реализована как deterministic regex/heuristics и registry matching в `src/core/nodes/stage1.py`, а не как полный LLM-интерпретатор. Ниже — целевая спецификация; расширение интерпретации — `implementation/MVP_FOLLOW_UP_MASTER_PLAN.md` §3.2.

### Stage 1 nodes

#### `input_analysis`

Type: LLM (target). **MVP actual:** deterministic heuristics in `src/core/nodes/stage1.py`.

Purpose:

- interpret raw user input and resume answers;
- extract candidate generation parameters;
- apply explicit current request priority over defaults/context;
- separate hard details from soft preferences;
- fill/update `normalized_request`;
- fill/update `interpretation_state.confidence`;
- detect preliminary ambiguity or missing fields.

Inputs:

- `session.request.raw_text` or equivalent initial input;
- normalized transient resume payload from `GraphState.user_input` if present;
- `current_config`;
- `user_context`;
- prompt metadata summaries if available from prior iteration.

Outputs:

- draft `normalized_request`;
- `interpretation_state.analysis_summary`;
- `interpretation_state.confidence`;
- `interpretation_state.detected_issues`;
- cleared transient resume value.

Правила:

- `normalized_request` describes the generation task only.
- Do not write `preview_text` here.
- Do not finalize prompt layers here.
- If a resume answer is received, re-analyze the whole updated interpretation.

#### `metadata_lookup`

Type: deterministic with optional LLM-assisted disambiguation.

Purpose:

- query `PromptRegistry` metadata index;
- match exact ids/names/aliases;
- check `applies_to`;
- identify candidate fallback layers;
- identify unresolved details;
- identify unsupported hard requirements.

Outputs:

- `interpretation_state.lookup_hints`;
- per-field lookup confidence.

Rules:

- Read YAML metadata only.
- Do not load full prompt bodies.
- Не писать в `normalized_request.prompt_context`.
- Не писать в top-level `session.prompt_context`.
- Сохранять результат lookup только в `interpretation_state.lookup_hints`: `candidate_layers`, `fallback_candidates`, `unresolved_details_candidates`, applicability notes и clarification signals.
- Не создавать final execution context.
- Не обещать unsupported layers.

#### `request_classification`

Type: deterministic/LLM-assisted.

Purpose:

Classify current request state as one of:

```text
complete
needs_clarification
empty_or_meaningless
contradictory
unsupported_hard_requirement
stop
```

Outputs:

- `interpretation_state.classification`;
- `interpretation_state.requires_clarification`;
- `interpretation_state.clarification_reason`;
- `interpretation_state.clarification_options`.

Rules:

- Classification uses analysis + metadata lookup + confidence.
- Если вход произошёл после failure в `final_parameter_validation`, classification должна также использовать `interpretation_state.validation_result`.
- Если вход произошёл после failure в execution lookup/preparation, classification должна также использовать `interpretation_state.execution_lookup_result`.
- Missing base parameters can be resolved by safe defaults only if the default is explicit and explainable.
- If there is no meaningful theme after clarification limit, route to `stop`.

#### `clarification_interrupt`

Type: LangGraph interrupt.

Purpose:

- ask user for missing/ambiguous/contradictory/unsupported choices;
- explain product for empty input;
- offer starter variants when useful.

Payload shape:

```json
{
  "type": "request_clarification",
  "reason": "ambiguous_subject",
  "message": "Нужно уточнить...",
  "options": [
    {
      "id": "opt_1",
      "label": "...",
      "normalized_patch": {}
    }
  ],
  "freeform_allowed": true,
  "attempt": 1,
  "max_attempts": 5
}
```

Resume value:

```json
{
  "interrupt_type": "request_clarification",
  "selected_option_id": "opt_1",
  "freeform_text": null
}
```

Правила:

- Увеличивать `interpretation_state.clarification_attempts` только при создании нового clarification `pending_interrupt`.
- Не увеличивать attempts при идемпотентном повторном показе существующего `pending_interrupt`.
- Не увеличивать attempts при обработке `recovered_resume_value`.
- Сохранять session перед interrupt, когда это возможно.
- При создании `pending_interrupt` выставлять `is_completed = false`, `completion_status = "waiting_user"`, `current_node = "clarification_interrupt"`.
- После resume вести граф в `input_analysis`, а не в validation.
- Выбранный option является input для re-analysis, а не final patch, который применяется вслепую.
- `max_clarification_attempts = 5` by default.
- Clarification attempts apply to the whole clarification contour: incomplete, ambiguous, empty/meaningless, contradictory and unsupported-hard-requirement cases.
- Each clarification option must represent a complete-enough interpretation candidate for all currently known missing/ambiguous base fields. It may be encoded as `normalized_patch`, but it must not intentionally leave base fields unresolved if the option text claims to be executable.
- Raw UI/LangGraph resume payload may be shorter, but CLI/API or the interrupt node must normalize it into `GraphState.user_input` before re-analysis.

#### `candidate_layer_resolution`

Type: deterministic/LLM-assisted.

Purpose:

- convert lookup candidates into final executable layer decisions;
- apply lookup-derived normalized field resolutions;
- select exact layers where available;
- select fallback layers where acceptable;
- store unresolved details as freeform context;
- ensure preview will not promise unsupported behavior.

Outputs:

- lookup-derived normalized field updates such as `utility_topic`, `subjects[].resolved_layer_id`, supported `substyle` and similar resolved fields;
- `normalized_request.prompt_context`;
- `interpretation_state.layer_resolution_summary`;
- `interpretation_state.layer_resolution_result.status`.

Layer resolution statuses:

```text
resolved
needs_clarification
unsupported_hard_requirement
stop
```

Rules:

- The canonical layer id is stable UPPER_SNAKE `id`.
- File path is stored separately in `source`.
- Fallback decisions include `requested`, `fallback_layer_id`, `source`, `reason`.
- Hard unsupported requirements must route back to clarification or stop.
- `candidate_layer_resolution` is the only Stage 1 node that may apply `interpretation_state.lookup_hints` into lookup-derived `normalized_request` fields.
- `metadata_lookup` must not mutate `normalized_request`; it only writes hints.
- Lookup-derived normalized field updates must not silently change user intent. If applying a hint changes meaning, conflicts with classification, or requires user choice, route to `request_classification` / `clarification_interrupt`.
- Examples of lookup-derived fields owned here: `utility_topic`, `subjects[].resolved_layer_id`, `substyle`, supported style/entity layer ids and unresolved detail placement.
- When `utility_mode = TEACHING` and a supported teaching topic is resolved, this node writes `normalized_request.utility_topic` and the matching `type = "utility"`, `role = "utility_topic"` layer in `normalized_request.prompt_context.resolved_layers`.
- `normalized_request.prompt_context` — canonical interpretation result: только resolved/fallback/unresolved decisions.
- `normalized_request.prompt_context` не является runtime/debug object и не должен содержать `frozen_at`, trace refs, execution hashes, prompt body policy или Langfuse metadata.
- `resolved` ведёт к `final_parameter_validation`.
- `needs_clarification` и `unsupported_hard_requirement` ведут в `clarification_interrupt`, если пользователь может выбрать fallback/relaxation.
- `stop` ведёт в `END`, если hard unsupported requirement cannot be relaxed or clarified.

#### `final_parameter_validation`

Type: deterministic/LLM-assisted.

Purpose:

Verify that `normalized_request` is complete, consistent and executable.

Must check:

- base required fields;
- supported enum values;
- `subjects`;
- lookup-derived field consistency:
  - `utility_topic` must match a `type = "utility"`, `role = "utility_topic"` resolved layer when registry match exists;
  - every `subjects[].resolved_layer_id` must match a resolved entity layer or an explicit fallback/unresolved detail;
  - supported `substyle` must match a style/substyle resolved layer;
  - `audience_language` and `result_language` must match language resolved layers with correct `role`;
- `subject_continuity_policy`;
- `character_profile` when needed;
- hard details;
- prompt context availability;
- fallback acceptability;
- safety/age/truth-mode contradictions at parameter level.

Outputs:

- `interpretation_state.validation_result`.

Persisted `interpretation_state.validation_result.status` values:

```text
not_started
pass
fail_reclassify
stop
```

Routes:

- `pass` -> `preview`;
- `fail_reclassify` -> `request_classification`;
- `stop` -> `END`.

#### `preview`

Type: deterministic/LLM-assisted.

Purpose:

Create user-facing summary of executable interpretation.

Outputs:

- `preview_state.preview_text`;
- `preview_state.shown_to_user`;
- optional `preview_state.approved_implicitly = true`.

Rules:

- Preview is based on final validated parameters and resolved/fallback prompt context.
- Preview must not mention unsupported styling as guaranteed.
- In MVP, preview does not require another user confirmation unless product later requests it.

#### `prompt_context_preparation`

Type: deterministic.

Purpose:

- создать top-level execution snapshot `session.prompt_context` из `normalized_request.prompt_context`;
- подготовить Stage 2 context references;
- гарантировать, что stage prompts можно собрать без изменения normalized parameters.

Outputs:

- `prompt_context`;
- initial `stage_prompt_context` refs/summaries;
- `interpretation_state.execution_lookup_result`.

Rules:

- Не менять `normalized_request`.
- Не менять layer ids, fallback decisions или unresolved details из `normalized_request.prompt_context`.
- `session.prompt_context` — runtime execution snapshot и может добавлять `frozen_at`, `source_hash`, `snapshot_hash`, prompt body policy, trace/debug refs и version metadata.
- Stage 2 читает top-level `session.prompt_context`, а не `normalized_request.prompt_context`.
- Не загружать все prompt bodies eagerly без необходимости.
- Хранить в state ids/hashes/summaries, а не большие full prompts.
- При failure нельзя silently swap layers, fallback layers или unresolved details.

Execution lookup result statuses:

```text
pass
fail_reresolve
fail_clarify
fail_stop
```

Failure examples:

- prompt layer id not found;
- missing prompt source file;
- invalid metadata;
- stale source hash;
- `applies_to` no longer valid;
- fallback source unavailable;
- prompt registry/index unavailable.

Routing:

```text
pass -> candidate_text_generator
fail_reresolve -> candidate_layer_resolution
fail_clarify -> clarification_interrupt
fail_stop -> END
```

Правила:

- `fail_reresolve` используется для technical/materialization failures, которые можно исправить повторным `candidate_layer_resolution` без изменения user intent.
- `fail_clarify` используется для failures, где нужен выбор пользователя или relaxation of a hard requirement.
- `fail_stop` используется для non-recoverable execution lookup failures.
- Если нужен routing через `request_classification`, она должна читать `interpretation_state.execution_lookup_result` и `interpretation_state.validation_result`; нельзя классифицировать только по старым analysis/confidence.


## Business Mapping

Maps `../TARGET_ORCHESTRATION_LOGIC.md` sections 3-4 to LangGraph nodes, state updates, interrupt/resume and prompt context preparation.

| Business logic area | Technical mapping |
| --- | --- |
| Raw request analysis and default extraction | `input_analysis` writes analysis fields and normalized draft candidates without final prompt layers. |
| Prompt-aware support discovery | `metadata_lookup` reads PromptRegistry metadata and writes only `interpretation_state.lookup_hints`. |
| Complete vs ambiguous/incomplete/unsupported classification | `request_classification` writes classification, clarification reason/options and stop decisions. |
| Human clarification/arbitration | `clarification_interrupt` creates durable `pending_interrupt`; resume returns to `input_analysis`. |
| Supported/fallback/unresolved layer decisions | `candidate_layer_resolution` applies lookup-derived normalized fields and writes `normalized_request.prompt_context`. |
| Final executable interpretation gate | `final_parameter_validation` checks required fields, lookup-derived field/layer consistency, fallback acceptability and contradictions. |
| User-facing interpretation preview | `preview` writes `preview_state` and must not promise unsupported behavior. |
| Execution snapshot for Stage 2 | `prompt_context_preparation` verifies/materializes `session.prompt_context` and initial `stage_prompt_context` without changing resolved layer decisions. |
