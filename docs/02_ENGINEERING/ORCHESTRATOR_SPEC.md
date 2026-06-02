# ORCHESTRATOR_SPEC.md

# Техническая спецификация оркестратора DreamyDraw

Статус: draft новой целевой спецификации.

Этот документ является активным техническим контрактом новой оркестрации DreamyDraw. Он описывает реализацию первых двух этапов:

1. сбор, нормализация, уточнение и финальная фиксация параметров генерации;
2. text pipeline до итогового набора `approved_texts`.

Третий этап визуализации в текущий scope не входит. Текущий orchestration boundary заканчивается на `approved_texts`; будущий image/animation pipeline должен потреблять их как downstream input.

Документ должен быть достаточен для реализации кода оркестратора без обращения к старой orchestration-реализации. Бизнес-логика и контракты сохранены в целевой форме: `normalized_request` описывает задачу генерации, процессные данные живут отдельно, prompt lookup разделён на metadata/execution phases, а Stage 2 выбирает approved texts только из validated candidate versions.

Эта спецификация определяет ownership оркестрации: ноды, routing, state placement, interrupt/resume, persistence и observability. Вложенные контракты данных являются активными источниками истины:

- `contracts/NORMALIZED_STATE_CONTRACT.md`;
- `contracts/PROMPT_FILE_CONTRACT.md`;
- `contracts/PROMPT_LOOKUP_CONTRACT.md`;
- `contracts/PROMPT_COMPOSITION_CONTRACT.md`;
- `contracts/STAGE_CONTRACTS.md`;
- `contracts/SCOPE_BOUNDARIES.md`;
- `contracts/GOLDEN_SCENARIOS.md`.

Если эта спецификация и контракт расходятся по форме вложенного объекта, приоритет у контрактного документа. Если контракт не описывает routing, ownership или порядок нод, приоритет у этой спецификации.

---

## 1. Scope

### 1.1 In scope

В scope входят:

- LangGraph-граф новой оркестрации;
- новые ноды Stage 1 и Stage 2;
- routing-функции;
- структура `GraphState`;
- расширение `SessionState`;
- interrupt/resume точки;
- PromptRegistry;
- PromptComposer;
- prompt metadata lookup;
- prompt execution lookup;
- stage-specific prompt context;
- text candidate pipeline;
- validation/refinement loop;
- shortage/fallback branch;
- JSONStorage persistence;
- Langfuse observability;
- migration-ready implementation constraints.

Финальный успешный output:

```text
SessionState.approved_texts
```

### 1.2 Out of scope

В текущую реализацию не входят:

- генерация картинок;
- image prompt execution;
- серии изображений;
- анимации;
- loop/pendulum animation;
- микро-мультики;
- visual validation;
- full visual pipeline;
- UI личного кабинета;
- долгосрочная история пользователя;
- vector search по prompt базе;
- отдельный агент для каждого score component.

`visual_preferences` сохраняются в `normalized_request` для будущего downstream этапа, но Stage 2 не использует их как управляющие параметры текстовой генерации. Допустимое исключение: текстовый кандидат может заполнить `expected_visual_idea` как подсказку для будущей визуализации.

---

## 2. Core Architecture

### 2.1 Principle

Оркестратор является тонким фасадом над LangGraph:

```text
CLI/API
  -> Orchestrator.start_session(...)
  -> Orchestrator.run_pipeline(...)
  -> LangGraph
  -> SessionState in JSONStorage
```

Фасад не содержит бизнес-ветвлений. Он отвечает только за:

- создание `SessionState`;
- загрузку сессии из `JSONStorage`;
- запуск/возобновление LangGraph;
- передачу `Command(resume=...)` после interrupt;
- извлечение interrupt payload;
- возврат `PipelineResult`;
- создание root trace для observability.

Бизнес-логика находится в нодах. Переходы находятся в graph builder и routing-функциях.

### 2.2 Runtime components

| Component | Responsibility |
| --- | --- |
| `Orchestrator` | Thin facade for session lifecycle and graph invocation. |
| `GraphState` | Transport wrapper around `SessionState` plus resume/service fields. |
| `SessionState` | Durable state and source of truth between nodes/processes. |
| `JSONStorage` | Long-term session persistence. |
| `MemorySaver` | In-process LangGraph checkpointer for interrupt/resume mechanics. |
| `PromptRegistry` | Prompt layer metadata index and lookup service. |
| `PromptComposer` | Stage-specific prompt context builder. |
| Langfuse client | Tracing, span metadata, prompt/context debug refs. |

### 2.3 GraphState

`GraphState` остаётся минимальным:

```python
class GraphState(TypedDict, total=False):
    session: SessionState
    user_input: Optional[Any]
```

Правила:

- `session` — единственное долговременное бизнес-состояние.
- `user_input` — временное значение после resume.
- Бизнес-данные не должны храниться только в `GraphState`.
- Ноды возвращают обновлённый `{"session": session}`.
- `current_node` — маркер прогресса/debug, а не imperative router.

---

## 3. Target LangGraph

### 3.1 Node names

Recommended node constants:

```text
NODE_INPUT_ANALYSIS
NODE_METADATA_LOOKUP
NODE_REQUEST_CLASSIFICATION
NODE_CLARIFICATION_INTERRUPT
NODE_CANDIDATE_LAYER_RESOLUTION
NODE_FINAL_PARAMETER_VALIDATION
NODE_PREVIEW
NODE_PROMPT_CONTEXT_PREPARATION
NODE_CANDIDATE_TEXT_GENERATOR
NODE_TOPIC_DEDUPLICATOR
NODE_SCORER
NODE_RANKER
NODE_CANDIDATE_VALIDATOR
NODE_CANDIDATE_REFINER
NODE_APPROVED_TEXT_SELECTOR
NODE_SHORTAGE_FALLBACK_INTERRUPT
```

Canonical `stage_id` использует snake_case и совпадает с graph node ids / ключами `stage_prompt_context`. PascalCase names остаются только display/contract labels.

| `stage_id` | Contract/display label |
| --- | --- |
| `candidate_text_generator` | `CandidateTextGenerator` |
| `topic_deduplicator` | `TopicDeduplicator` |
| `scorer` | `Scorer` |
| `ranker` | `Ranker` |
| `candidate_validator` | `Validator` |
| `candidate_refiner` | `Refiner` |
| `approved_text_selector` | `ApprovedTextSelector` |

### 3.2 Graph overview

```text
START
  -> input_analysis
  -> metadata_lookup
  -> request_classification
      complete
        -> candidate_layer_resolution
      incomplete / ambiguous / empty / contradictory / unsupported hard requirement
        -> clarification_interrupt
        -> input_analysis
      stop
        -> END

candidate_layer_resolution
  -> final_parameter_validation
      pass
        -> preview
      fail
        -> request_classification
      stop
        -> END

preview
  -> prompt_context_preparation
      pass
        -> candidate_text_generator
      fail_reresolve
        -> candidate_layer_resolution
      fail_clarify
        -> clarification_interrupt
      fail_stop
        -> END

candidate_text_generator
  -> topic_deduplicator
  -> scorer
  -> ranker
  -> candidate_validator
      accepted
        -> approved_text_selector? / next candidate
      needs_revision
        -> candidate_refiner
        -> candidate_validator
      rejected
        -> next candidate
      enough_approved
        -> approved_text_selector
      queue_exhausted
        -> approved_text_selector

approved_text_selector
  -> END with completion_status=completed_enough if enough
  -> shortage_fallback_interrupt if shortage HITL enabled
  -> END with completion_status=completed_with_shortage if shortage HITL disabled
```

### 3.3 Stage 1 nodes

#### `input_analysis`

Type: LLM.

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
- `session.user_feedback` / resume payload if present;
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
  "max_attempts": 3
}
```

Resume value:

```json
{
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

#### `candidate_layer_resolution`

Type: deterministic/LLM-assisted.

Purpose:

- convert lookup candidates into final executable layer decisions;
- select exact layers where available;
- select fallback layers where acceptable;
- store unresolved details as freeform context;
- ensure preview will not promise unsupported behavior.

Outputs:

- `normalized_request.prompt_context`;
- `interpretation_state.layer_resolution_summary`.

Rules:

- The canonical layer id is stable UPPER_SNAKE `id`.
- File path is stored separately in `source`.
- Fallback decisions include `requested`, `fallback_layer_id`, `source`, `reason`.
- Hard unsupported requirements must route back to clarification or stop.
- `normalized_request.prompt_context` — canonical interpretation result: только resolved/fallback/unresolved decisions.
- `normalized_request.prompt_context` не является runtime/debug object и не должен содержать `frozen_at`, trace refs, execution hashes, prompt body policy или Langfuse metadata.

#### `final_parameter_validation`

Type: deterministic/LLM-assisted.

Purpose:

Verify that `normalized_request` is complete, consistent and executable.

Must check:

- base required fields;
- supported enum values;
- `subjects`;
- `subject_continuity_policy`;
- `character_profile` when needed;
- hard details;
- prompt context availability;
- fallback acceptability;
- safety/age/truth-mode contradictions at parameter level.

Outputs:

- `interpretation_state.validation_result`.

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

### 3.4 Stage 2 nodes

#### `candidate_text_generator`

Type: LLM.

Policy:

```text
candidate_count_default = 20
```

Purpose:

Generate a pool of text candidates larger than `output_count`.

Inputs:

- `normalized_request`;
- `prompt_context`;
- generator `stage_prompt_context`;
- `candidate_count`.

Candidate output shape:

```json
{
  "candidate_id": "c01",
  "theme": "ёжик ищет сухие листья для зимнего укрытия",
  "text": "Короткий текст...",
  "questions": ["Что ёжик искал?", "Почему сухие листья полезны?"],
  "utility_points": [],
  "used_subjects": ["hedgehog"],
  "expected_visual_idea": "ёжик рядом с сухими листьями на снегу",
  "used_context": {
    "resolved_layers": [],
    "fallback_layers": [],
    "unresolved_details": []
  },
  "status": "draft"
}
```

Rules:

- Every candidate has a unique `theme`.
- Themes should be semantically different, not only worded differently.
- Respect `subject_continuity_policy`.
- Preserve `main_subject`, required subjects and `character_profile`.
- Use `visual_preferences` only indirectly, if at all, for `expected_visual_idea`.

#### `topic_deduplicator`

Type: LLM/deterministic.

Purpose:

- detect duplicate themes;
- mark duplicate candidates;
- preserve debug history.

Output shape:

```json
{
  "deduplication_results": [
    {
      "candidate_id": "c01",
      "is_duplicate": false,
      "duplicate_of": null,
      "reason": null
    }
  ]
}
```

Rules:

- Severe duplicates are excluded from normal ranking.
- Borderline duplicates can remain but receive lower novelty score.
- `approved_texts` must not contain duplicate themes.

#### `scorer`

Type: LLM in MVP.

Purpose:

- apply hard gates;
- assign score components;
- calculate or request `total_score`.

Output shape:

```json
{
  "scores": [
    {
      "candidate_id": "c01",
      "hard_gates": {
        "safety": "pass",
        "truth_fit": "pass",
        "age_fit": "pass",
        "utility_goal": "pass",
        "subject_continuity": "pass",
        "hard_details": "pass",
        "character_consistency": "pass"
      },
      "score_components": {
        "child_interest": 0.84,
        "age_fit": 0.91,
        "utility_fit": 0.78,
        "style_fit": 0.80,
        "novelty": 0.75,
        "visual_potential": 0.70
      },
      "total_score": 0.80
    }
  ]
}
```

Rules:

- Critical hard gate failure prevents approval.
- Total score is meaningful only for candidates that pass critical gates.
- MVP may use one agent for all components.
- Schema remains multi-component for future split agents.
- `utility_goal` является critical hard gate для `utility_mode = TEACHING`.
- Для `utility_mode = NARRATIVE` utility fit может оставаться score component, если нет конкретной hard utility goal.

#### `ranker`

Type: deterministic.

Purpose:

- create validation queue.

Ranking policy:

1. candidates with critical hard gates passed;
2. higher `total_score`;
3. higher novelty/theme diversity;
4. higher visual potential as tie-breaker.

Output:

```json
{
  "ranked_candidates": [
    {
      "candidate_id": "c01",
      "rank": 1,
      "total_score": 0.80,
      "hard_gates_passed": true
    }
  ]
}
```

#### `candidate_validator`

Type: LLM.

Purpose:

Validate one candidate version from ranked queue.

Checks:

- safety;
- target age;
- truth mode;
- utility mode;
- style/substyle fit;
- subject continuity;
- required subjects;
- hard details;
- character profile;
- questions;
- output format.

Output:

```json
{
  "candidate_id": "c02",
  "version_id": "c02_v1",
  "status": "needs_revision",
  "issues": [
    {
      "type": "truth_mode_violation",
      "severity": "major",
      "description": "В режиме TRUTH ёжик начал разговаривать как человек."
    }
  ],
  "required_fixes": [
    "Убрать человеческую речь ёжика или перевести её в наблюдение ребёнка."
  ],
  "validation_summary": "Нужно исправить нарушение режима правды."
}
```

Statuses:

```text
accepted
needs_revision
rejected
```

Rules:

- Валидировать кандидатов последовательно по ranking.
- Останавливать validation loop, когда accepted count достигает `output_count`.
- Увеличивать validation attempt counter per candidate.
- Если status = `accepted`, записывать принятую версию кандидата в `validated_candidate_versions`.
- `validation_results` хранит историю попыток; `validated_candidate_versions` хранит версии кандидатов, пригодные для финального выбора.
- Если validator принимает исходный draft без refiner, всё равно создаётся version object, например `c01_v1`, в `validated_candidate_versions`.

Форма `validated_candidate_versions`:

```json
{
  "candidate_id": "c02",
  "version_id": "c02_v2",
  "source_candidate_id": "c02",
  "source_version_id": "c02_v1",
  "version_origin": "refined",
  "theme": "ёжик ищет сухие листья",
  "text": "Финальный или исправленный текст...",
  "questions": ["Что ёжик искал?"],
  "score": 0.82,
  "validation_status": "accepted",
  "validation_summary": "Возраст, truth_mode, utility goal и subject continuity соблюдены.",
  "used_context": {
    "resolved_layers": [],
    "fallback_layers": [],
    "unresolved_details": []
  },
  "rank_source": {
    "rank": 1,
    "total_score": 0.82,
    "ranked_at": "2026-06-02T12:15:00Z",
    "ranker_version": 1
  },
  "lineage": {
    "generator_attempt": 1,
    "validation_attempts": 2,
    "refinement_attempts": 1,
    "refiner_changes_summary": "Убрана человеческая речь, сохранена тема."
  },
  "trace_refs": {}
}
```

Правила:

- `validated_candidate_versions` — source of truth для normal approved text content.
- `rank_source` сохраняет ranking/order metadata, не превращая `ranked_candidates` в source of text content.
- `version_origin` = `draft`, если original candidate был accepted без refinement, и `refined`, если версия accepted после refiner.

#### `candidate_refiner`

Type: LLM.

Purpose:

Repair one candidate according to validator issues.

Output:

```json
{
  "candidate_id": "c02",
  "version_id": "c02_v2",
  "theme": "исходная тема остаётся прежней",
  "text": "Исправленный текст...",
  "questions": ["..."],
  "changes_summary": "Убрана человеческая речь, сохранена тема зимнего укрытия.",
  "status": "revised"
}
```

Immutable fields:

- `theme`;
- `main_subject`;
- required subjects;
- `character_profile`;
- `subject_continuity_policy`;
- `content_format`;
- `truth_mode`;
- `utility_mode`;
- `target_age`;
- hard details.

Правила:

- Максимум refinement attempts per candidate в MVP: `2`.
- Refiner не должен молча менять immutable fields.
- Если исправление невозможно без изменения immutable fields, stage возвращает issue/failure и граф переходит к следующему кандидату.
- Исправленная версия не утверждается самим refiner. Она должна вернуться в `candidate_validator`; только accepted validation result может добавить её в `validated_candidate_versions`.

`route_after_candidate_refiner`:

```text
revised -> candidate_validator
cannot_repair -> next ranked candidate validator
attempts_exhausted -> next ranked candidate validator
queue_exhausted -> approved_text_selector
```

Правила:

- `revised` возвращает граф в `candidate_validator` для того же кандидата с новым `version_id`.
- `cannot_repair` и `attempts_exhausted` двигают rank cursor к следующему кандидату.
- Если при переходе к следующему кандидату ranked queue исчерпана, route ведёт в `approved_text_selector`.

#### `approved_text_selector`

Type: deterministic/LLM-assisted.

Purpose:

- choose final accepted versions;
- write `approved_texts`;
- write `shortage`;
- optionally prepare `safe_fallback_candidates`.

Inputs:

- `ranked_candidates`;
- `validated_candidate_versions`;
- `validation_results`;
- `normalized_request.output_count`.
- optional `safe_fallback_candidates` in shortage path only;
- optional `shortage.fallback_acceptance_policy` after HITL fallback acceptance only.

Правила:

- Выбирать из `validated_candidate_versions`, а не из исходных drafts.
- Если кандидат проходил refinement, использовать latest accepted validated version.
- Никогда не включать кандидатов с critical hard gate failures.
- Не включать duplicate themes.
- `candidate_texts` и `ranked_candidates` не являются допустимыми источниками финального текста для selector; это только context и ordering inputs.
- Если набрано достаточно accepted versions, выставлять `completion_status = "completed_enough"`.
- Если accepted versions меньше, чем `output_count`, выставлять `completion_status = "completed_with_shortage"` и сохранять `shortage.requested` / `shortage.approved`.
- `completed_with_shortage` является terminal status, но не success-equivalent к `completed_enough`; UI/API должны явно показывать shortage.
- Safe fallback candidates нельзя включать без явной durable HITL fallback acceptance policy в `shortage.fallback_acceptance_policy`.

Source invariants:

```text
normal approved_text
  -> source = validated_candidate_versions only

HITL fallback approved_text
  -> source = safe_fallback_candidates + explicit shortage.fallback_acceptance_policy only
```

Правила:

- Normal approved text может появиться только из `validated_candidate_versions`.
- HITL fallback approved text может появиться только если `shortage.fallback_acceptance_policy.accepted_candidate_ids` явно содержит candidate id.
- HITL fallback approved text должен выставлять `validation_status = "hitl_fallback_accepted"`.
- HITL fallback approved text должен сохранять `known_issues` и `why_safe`.
- HITL fallback approved text не должен вставляться в `validated_candidate_versions`.

Approved text shape:

`approved_texts` is a union of normal accepted texts and HITL fallback accepted texts.

Normal accepted variant:

```json
{
  "candidate_id": "c01",
  "version_id": "c01_v1",
  "theme": "ёжик ищет сухие листья",
  "text": "Финальный текст...",
  "questions": ["..."],
  "score": 0.80,
  "validation_status": "accepted",
  "validation_summary": "Возраст, truth_mode, subject continuity и safety соблюдены.",
  "expected_visual_idea": "ёжик рядом с сухими листьями",
  "used_context": {
    "resolved_layers": [],
    "fallback_layers": [],
    "unresolved_details": []
  },
  "trace_refs": {}
}
```

HITL fallback accepted variant:

```json
{
  "candidate_id": "c07",
  "source": "safe_fallback_candidate",
  "theme": "ёжик замечает следы на снегу",
  "text": "Текст безопасного fallback-кандидата...",
  "questions": ["..."],
  "score": 0.71,
  "validation_status": "hitl_fallback_accepted",
  "validation_summary": "Пользователь явно принял safe fallback candidate при shortage.",
  "why_safe": "Не провалил safety и age gates.",
  "known_issues": ["Слабее выражена поучительная цель."],
  "expected_visual_idea": "ёжик у следов на снегу",
  "used_context": {
    "resolved_layers": [],
    "fallback_layers": [],
    "unresolved_details": []
  },
  "trace_refs": {}
}
```

Форма `shortage`:

```json
{
  "requested": 5,
  "approved": 3,
  "status": "not_enough_valid_candidates",
  "reason": "ranked queue exhausted before output_count",
  "retry_attempts": 0,
  "user_decision": null,
  "fallback_acceptance_policy": null,
  "history": [
    {
      "attempt": 1,
      "requested": 5,
      "approved": 3,
      "status": "not_enough_valid_candidates",
      "reason": "ranked queue exhausted before output_count",
      "hard_gate_failure_counts": {
        "truth_fit": 4,
        "age_fit": 2,
        "utility_goal": 1
      },
      "user_decision": "retry_generation",
      "created_at": "2026-06-02T12:20:00Z"
    }
  ]
}
```

Форма `shortage.fallback_acceptance_policy`:

```json
{
  "accepted_candidate_ids": ["c07"],
  "accepted_at": "2026-06-02T12:25:00Z",
  "accepted_by": "user",
  "known_issues_acknowledged": true
}
```

#### `shortage_fallback_interrupt`

Type: optional LangGraph interrupt.

MVP может пропустить этот interrupt и завершиться с shortage. Если HITL включён, доступны варианты:

- принять меньше approved texts;
- принять safe fallback candidates с known issues;
- повторить candidate generation;
- остановиться.

`safe_fallback_candidates` существуют только для shortage path и не должны смешиваться с `approved_texts` без явного решения selector/user.

Исполнимый routing:

```text
approved_text_selector
  enough -> END
  shortage + shortage_hitl_enabled=false -> END
  shortage + shortage_hitl_enabled=true -> shortage_fallback_interrupt

shortage_fallback_interrupt
  accept_fewer -> END
  accept_safe_fallback -> approved_text_selector
  retry_generation -> candidate_text_generator
  stop -> END
```

Правила:

- `accept_fewer` сохраняет текущие `approved_texts`, сохраняет `shortage.status` и выставляет `completion_status = "completed_with_shortage_user_accepted"`.
- `accept_safe_fallback` пишет `shortage.user_decision = "accept_safe_fallback"` и сохраняет durable `shortage.fallback_acceptance_policy`.
- `shortage.fallback_acceptance_policy.accepted_candidate_ids` содержит явные safe fallback candidate ids, которые пользователь согласился принять.
- Selector может включить только явно принятые safe fallback candidates и должен пометить их `validation_status = "hitl_fallback_accepted"`.
- HITL-accepted fallback candidates не считаются обычными `validated_candidate_versions`; они отдельно маркируются в `approved_texts` и сохраняют `known_issues` / `why_safe`.
- Перед `retry_generation` текущий shortage snapshot добавляется в `shortage.history`.
- `retry_generation` увеличивает `shortage.retry_attempts`, пересоздаёт active shortage state и ведёт в `candidate_text_generator`.
- `stop` выставляет `completion_status = "stopped_by_user"` без изменения `approved_texts`.

При `retry_generation` сохраняются:

- `normalized_request`;
- `interpretation_state`;
- `preview_state`;
- `prompt_context`;
- базовые refs из `stage_prompt_context`;
- `shortage.history`.

При `retry_generation` очищаются или пересоздаются:

- `candidate_texts`;
- `deduplication_results`;
- `scores`;
- `ranked_candidates`;
- `validation_results`;
- `validated_candidate_versions`;
- `approved_texts`;
- `safe_fallback_candidates`;
- active `shortage.user_decision`;
- active `shortage.fallback_acceptance_policy`;
- `pipeline_counters.current_rank_index`;
- `pipeline_counters.accepted_count`;
- per-candidate validation/refinement counters.

---

## 4. Routing Functions

Routing lives in `src/core/graph/routing.py`.

Recommended functions:

```text
route_after_request_classification
route_after_final_parameter_validation
route_after_prompt_context_preparation
route_after_candidate_validator
route_after_candidate_refiner
route_after_approved_text_selector
route_after_shortage_fallback
entry_point_from_session
```

### 4.1 Classification routing

```text
complete -> candidate_layer_resolution
needs_clarification -> clarification_interrupt
empty_or_meaningless -> clarification_interrupt
contradictory -> clarification_interrupt
unsupported_hard_requirement -> clarification_interrupt
stop -> END
```

После `clarification_interrupt` граф идёт в `input_analysis`.

### 4.2 Prompt context preparation routing

`route_after_prompt_context_preparation`:

```text
pass -> candidate_text_generator
fail_reresolve -> candidate_layer_resolution
fail_clarify -> clarification_interrupt
fail_stop -> END
```

Правила:

- Routing читает `interpretation_state.execution_lookup_result.status`.
- `fail_reresolve` не является user clarification; это повторный resolution без silent layer swap.
- `fail_clarify` создаёт/обновляет clarification payload с причиной execution lookup failure.
- `fail_stop` выставляет `is_completed = true`, `completion_status = "failed"` и сохраняет `interpretation_state.execution_lookup_result` с issues.

### 4.3 Validation loop routing

`candidate_validator` routing uses:

- accepted count;
- current candidate id;
- candidate status;
- refinement attempts;
- ranked queue pointer;
- output count.

Routing:

```text
accepted and accepted_count >= output_count -> approved_text_selector
accepted and accepted_count < output_count -> next ranked candidate validator
needs_revision and attempts_left -> candidate_refiner
needs_revision and no_attempts_left -> next ranked candidate validator
rejected -> next ranked candidate validator
queue_exhausted -> approved_text_selector
```

Реализация может представить "next ranked candidate validator" как обновление loop cursor в state и возврат в ту же ноду `candidate_validator`.

### 4.4 Shortage routing

`route_after_approved_text_selector`:

```text
shortage.status = enough
  -> END

shortage.status != enough and shortage_hitl_enabled = false
  -> END

shortage.status != enough and shortage_hitl_enabled = true
  -> shortage_fallback_interrupt
```

`route_after_shortage_fallback`:

```text
accept_fewer
  -> END

accept_safe_fallback
  -> approved_text_selector

retry_generation
  -> candidate_text_generator

stop
  -> END
```

Правила routing:

- `END` после shortage должен сохранять `completion_status = "completed_with_shortage"`, `completed_with_shortage_user_accepted` или `stopped_by_user` в зависимости от действия пользователя, а не `completed_enough`.
- `retry_generation` должен reset Stage 2 candidate/ranking/validation state согласно правилам в `shortage_fallback_interrupt`.
- `accept_safe_fallback` должен сохранить durable `shortage.fallback_acceptance_policy`; selector читает это поле и не должен выводить acceptance только из наличия кандидатов.

---

## 5. SessionState Contract

### 5.1 Top-level fields

`SessionState` must include:

```text
session_id
request
current_node
is_completed
completion_status
normalized_request
interpretation_state
preview_state
prompt_context
stage_prompt_context
candidate_texts
deduplication_results
scores
ranked_candidates
validation_results
validated_candidate_versions
approved_texts
shortage
safe_fallback_candidates
pipeline_counters
trace_refs
pending_interrupt
```

Старые поля предыдущей orchestration model не должны быть частью нового business flow. Если они временно сохраняются для CLI compatibility, их нужно пометить deprecated и не читать в новых нодах.

Значения `completion_status`:

```text
running
waiting_user
completed_enough
completed_with_shortage
completed_with_shortage_user_accepted
stopped_by_user
failed
```

Правила:

- `is_completed = true` означает, что graph достиг terminal state.
- `completion_status = completed_enough` означает, что requested `output_count` выполнен.
- `completion_status = completed_with_shortage` означает terminal shortage и должен явно отображаться UI/API.
- `completion_status = completed_with_shortage_user_accepted` означает, что пользователь явно принял fewer/fallback results.
- `completed_with_shortage` и `completed_with_shortage_user_accepted` не эквивалентны full success.

### 5.2 `request`

Minimum input request:

```json
{
  "raw_text": "Сделай 5 коротких натуралистичных историй про ёжика зимой в лесу для ребёнка 3 лет.",
  "current_config": {
    "truth_mode": "TRUTH",
    "utility_mode": "NARRATIVE",
    "target_age": "3",
    "text_style_base": "calm",
    "image_style": "cartoon"
  },
  "user_context": {
    "available": false
  }
}
```

`request` is raw/user-facing input. Resolved execution fields live in `normalized_request`.

Старая семантика `fast/check` не является частью нового контракта оркестрации. В текущем scope нет режима, который переводит pipeline к image generation. Если позже понадобится подтверждение preview или approved texts, это должно быть отдельной UI/HITL policy, а не возвратом старого `fast/check`.

### 5.3 `normalized_request`

`normalized_request` describes the generation task:

```json
{
  "content_format": "story",
  "truth_mode": "TRUTH",
  "utility_mode": "NARRATIVE",
  "target_age": "3",
  "output_count": 5,
  "audience_language": "ru",
  "result_language": "ru",
  "current_config": {
    "truth_mode": "TRUTH",
    "utility_mode": "NARRATIVE",
    "target_age": "3",
    "text_style_base": "calm",
    "image_style": "cartoon"
  },
  "main_subject": "ёжик",
  "subjects": [
    {
      "id": "hedgehog",
      "label": "ёжик",
      "type": "animal",
      "role": "main",
      "is_character": false,
      "base_species": "hedgehog",
      "resolved_layer_id": "TRUTH_ANIMAL_HEDGEHOG",
      "unresolved_detail": null
    }
  ],
  "setting": {
    "place": "лес",
    "season": "зима",
    "time": null
  },
  "text_style_base": "calm",
  "substyle": "naturalistic",
  "character_profile": null,
  "subject_continuity_policy": {
    "mode": "single_subject_all_items",
    "required_subjects": ["hedgehog"],
    "coverage": "item_level",
    "allowed_distribution": "all_items",
    "can_mix_subjects_in_one_item": true,
    "can_introduce_new_subjects": true,
    "can_replace_required_subjects": false
  },
  "hard_details": [
    "главный объект — ёжик",
    "действие происходит зимой в лесу",
    "истории должны быть реалистичными"
  ],
  "soft_preferences": [
    "спокойный тон",
    "простые фразы"
  ],
  "user_context": {
    "available": false,
    "source": null,
    "defaults": {},
    "preferences": {},
    "avoid": [],
    "recent_topics": []
  },
  "visual_preferences": {
    "image_style": "cartoon",
    "target_device": null,
    "visual_output_type": "single_image_card"
  },
  "prompt_context": {
    "resolved_layers": [
      {
        "type": "content_format",
        "id": "CONTENT_FORMAT_STORY",
        "source": "content_formats/story/BASE.md",
        "reason": "content_format=story"
      },
      {
        "type": "truth_mode",
        "id": "TRUTH_BASE",
        "source": "truth_modes/TRUTH/BASE.md",
        "reason": "truth_mode=TRUTH"
      },
      {
        "type": "age",
        "id": "AGE_3",
        "source": "ages/3/BASE.md",
        "reason": "target_age=3"
      },
      {
        "type": "entity",
        "id": "TRUTH_ANIMAL_HEDGEHOG",
        "source": "truth_modes/TRUTH/characters/animals/HEDGEHOG.md",
        "reason": "main_subject=ёжик"
      }
    ],
    "fallback_layers": [],
    "unresolved_details": []
  }
}
```

Правила:

- `confidence`, `requires_clarification` и `preview_text` не находятся внутри `normalized_request`.
- `current_config` — snapshot/default source, а не Stage 2 execution source.
- `user_context` — object-with-empty-state, не `null`.
- `visual_preferences` сохраняются для downstream, но text pipeline не использует их напрямую.

### 5.4 `interpretation_state`

```json
{
  "confidence": {
    "content_format": 0.9,
    "truth_mode": 0.85,
    "utility_mode": 0.8,
    "target_age": 0.95,
    "main_subject": 0.95
  },
  "classification": "complete",
  "requires_clarification": false,
  "clarification_reason": null,
  "clarification_options": [],
  "clarification_attempts": 0,
  "max_clarification_attempts": 3,
  "lookup_hints": {},
  "validation_result": {
    "status": "pass",
    "issues": []
  },
  "execution_lookup_result": {
    "status": "pass",
    "failure_type": null,
    "failed_layer_id": null,
    "failed_source": null,
    "issues": [],
    "route_reason": null
  }
}
```

### 5.5 `preview_state`

```json
{
  "preview_text": "Я подготовлю 5 спокойных правдивых историй про ёжика зимой в лесу для ребёнка 3 лет.",
  "shown_to_user": true,
  "approved_implicitly": true
}
```

### 5.6 `prompt_context`

```json
{
  "source": "normalized_request.prompt_context",
  "frozen_at": "2026-06-02T12:08:00Z",
  "version": 1,
  "source_hash": "hash-of-normalized-request-prompt-context",
  "snapshot_hash": "hash-of-execution-snapshot",
  "body_policy": "lazy_not_persisted",
  "resolved_layers": [
    {
      "type": "entity",
      "id": "TRUTH_ANIMAL_HEDGEHOG",
      "source": "truth_modes/TRUTH/characters/animals/HEDGEHOG.md",
      "reason": "main_subject=ёжик"
    }
  ],
  "fallback_layers": [],
  "unresolved_details": []
}
```

Правила:

- `id` — canonical stable UPPER_SNAKE.
- `source` хранит путь к prompt file.
- Узкие детали без точного слоя могут храниться как unresolved freeform context.
- Top-level `prompt_context` является execution snapshot, а не canonical interpretation object.
- Layer decisions копируются из `normalized_request.prompt_context`.
- Execution metadata хранится здесь, а не внутри `normalized_request.prompt_context`.

### 5.7 `stage_prompt_context`

`stage_prompt_context` хранит компактные per-stage context refs и summaries, созданные `PromptComposer`. По умолчанию он не должен хранить full prompt bodies.

Минимальная форма:

```json
{
  "candidate_text_generator": {
    "stage": "candidate_text_generator",
    "source_prompt_context_hash": "hash-of-session-prompt-context",
    "stage_context_hash": "hash-of-stage-context-summary-and-refs",
    "layer_ids": [
      "CONTENT_FORMAT_STORY",
      "TRUTH_BASE",
      "AGE_3",
      "TRUTH_ANIMAL_HEDGEHOG"
    ],
    "fallback_layer_ids": [],
    "unresolved_detail_labels": [],
    "body_policy": "lazy_not_persisted",
    "context_summary": "Полный creative context для спокойных правдивых историй про ёжика для возраста 3.",
    "created_at": "2026-06-02T12:10:00Z",
    "version": 1
  }
}
```

Правила:

- Key — stage id.
- `source_prompt_context_hash` идентифицирует top-level `session.prompt_context` snapshot, использованный как input.
- `stage_context_hash` идентифицирует конкретный stage context refs/summary.
- Если `session.prompt_context.snapshot_hash` меняется, существующие stage contexts становятся invalid.
- Full prompt bodies загружаются lazy и по умолчанию не сохраняются в `SessionState`.
- Полный prompt text можно логировать в Langfuse или debug artifacts только согласно debug/prompt logging policy.
- Stage nodes используют эту единую форму и не должны изобретать несовместимые per-node context formats.

### 5.8 `pipeline_counters`

```json
{
  "clarification_attempts": 0,
  "candidate_attempts": {
    "c01": {
      "validation_attempts": 1,
      "refinement_attempts": 0
    }
  },
  "current_rank_index": 0,
  "accepted_count": 0
}
```

### 5.9 `pending_interrupt`

`pending_interrupt` — durable state для восстановления HITL после restart процесса. Он хранится в `SessionState` / `JSONStorage`, а не в `MemorySaver`.

Clarification example:

```json
{
  "type": "request_clarification",
  "node": "clarification_interrupt",
  "status": "waiting",
  "payload": {
    "type": "request_clarification",
    "reason": "ambiguous_subject",
    "message": "Нужно уточнить тему.",
    "options": []
  },
  "created_at": "2026-06-02T12:00:00Z",
  "attempt": 1,
  "resume_schema": {
    "selected_option_id": "string|null",
    "freeform_text": "string|null"
  }
}
```

Shortage example:

```json
{
  "type": "shortage_fallback",
  "node": "shortage_fallback_interrupt",
  "status": "waiting",
  "payload": {
    "type": "shortage_fallback",
    "shortage": {
      "requested": 5,
      "approved": 3,
      "status": "not_enough_valid_candidates"
    }
  },
  "created_at": "2026-06-02T12:05:00Z",
  "attempt": 1,
  "resume_schema": {
    "action": "accept_fewer|accept_safe_fallback|retry_generation|stop"
  }
}
```

Правила:

- Interrupt node создаёт `pending_interrupt`, сохраняет session, затем вызывает LangGraph `interrupt(payload)`.
- При создании `pending_interrupt` interrupt node выставляет `is_completed = false`, `completion_status = "waiting_user"`, `current_node = pending_interrupt.node`.
- После успешной обработки resume interrupt node очищает `pending_interrupt`.
- После успешной обработки resume interrupt node выставляет `completion_status = "running"` до следующего terminal/waiting state.
- Повторный вход в interrupt node только для повторного показа существующего `pending_interrupt` должен быть идемпотентным.
- Повторный показ существующего pending payload не должен увеличивать clarification attempts или shortage attempts.
- Attempt counters увеличиваются только при создании нового interrupt payload, а не при восстановлении pending payload из JSONStorage.
- Если состояние `MemorySaver` ещё доступно, resume может использовать `Command(resume=...)`.
- Если состояние `MemorySaver` потеряно, CLI/API читает `pending_interrupt` из JSONStorage, получает ответ пользователя и вызывает graph с recovered resume value в `GraphState.user_input` или эквивалентном поле.
- `entry_point_from_session` ведёт в `pending_interrupt.node`, когда `pending_interrupt.status = "waiting"`.
- Interrupt node, запущенная с recovered resume value, обрабатывает его без повторного вызова `interrupt()`.

---

## 6. Prompt System

### 6.1 Prompt file format

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
- `safety_notes`.

### 6.2 PromptRegistry

Responsibilities:

- scan prompt directories;
- parse YAML metadata;
- validate required fields;
- validate unique `id`;
- store layer index by id/type/alias/applicability;
- return metadata lookup candidates;
- return execution lookup results;
- cache parsed metadata by file hash or mtime.

Lookup levels:

1. exact match by id/name;
2. alias match;
3. fallback by applicability and priority;
4. unresolved detail.

### 6.3 Metadata lookup

Used before preview.

Purpose:

- understand available modes/styles/substyles/entities;
- avoid promising unsupported stylization;
- identify fallback candidates;
- decide whether user clarification is needed.

It must not load full prompt bodies.

### 6.4 Execution lookup

Used after request is complete enough to execute and after `candidate_layer_resolution` has already written `normalized_request.prompt_context`.

Output:

```json
{
  "resolved_layers": [],
  "fallback_layers": [],
  "unresolved_details": []
}
```

Execution lookup/preparation materializes and verifies the already resolved `normalized_request.prompt_context` into top-level `session.prompt_context`.

Rules:

- It may add source refs, hashes, `frozen_at`, version and runtime metadata.
- It must not choose different layer ids.
- It must not choose different fallback layers.
- It must not change unresolved details.
- It must not change the interpretation shown in preview.
- If verification fails, route via `pass`, `fail_reresolve`, `fail_clarify` or `fail_stop` as defined in `prompt_context_preparation`.
- It must not silently swap to a different prompt layer to recover from missing source, invalid metadata or stale hashes.

### 6.5 PromptComposer

Responsibilities:

- build stage-specific prompt context;
- lazy-load prompt bodies when needed;
- preserve layer ordering;
- include hard constraints before soft preferences;
- include unresolved details as freeform context, not guaranteed layer knowledge;
- generate compact debug summaries and hashes.

General layer priority:

1. content format;
2. truth mode;
3. utility mode;
4. target age;
5. result language;
6. style/substyle;
7. entity/subject;
8. hard details;
9. soft preferences;
10. unresolved details;
11. stage-specific instructions;
12. output contract.

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

## 7. Interrupts

### 7.1 Request clarification

Used for:

- incomplete input;
- ambiguous input;
- low-confidence base fields;
- several close fallback candidates;
- user must choose between modes/styles/entities.

After resume: route to `input_analysis`.

### 7.2 Empty or meaningless input

Used for:

- empty input;
- random characters;
- meta-input that is not a generation request.

Payload should include product explanation and starter variants. If user does not choose a variant or provide meaningful freeform text after attempt limit, route to `END`.

### 7.3 Contradiction arbitration

Used for:

- hard detail conflicts with truth mode;
- selected/default config conflicts with explicit user request;
- age/safety constraints conflict with request.

Payload should explain the contradiction and offer supported alternatives.

After resume: route to `input_analysis`.

### 7.4 Hard unsupported prompt requirement

Used when:

- requested prompt layer is unavailable;
- fallback would materially change meaning;
- unsupported style/entity is stated as mandatory.

Payload should include:

- unsupported requirement;
- possible fallback layers;
- unresolved detail option if allowed;
- option to relax requirement or stop.

After resume: route to `input_analysis`.

### 7.5 Shortage fallback

Optional in MVP.

Used when:

```text
approved_texts.length < normalized_request.output_count
```

Options:

- accept fewer approved texts;
- accept safe fallback candidates;
- retry candidate generation;
- stop.

---

## 8. Persistence

### 8.1 JSONStorage

JSONStorage is the durable source of truth.

Required behavior:

- save session after every mutating node;
- save before interrupt payload when possible;
- save after resume handling;
- store `approved_texts`;
- store `shortage`;
- store compact prompt refs, not necessarily full prompt bodies;
- preserve enough state for process restart.

### 8.2 MemorySaver

MemorySaver stores in-process LangGraph interrupt state. It is not durable across process restarts.

Between process restarts, recovery uses:

- `SessionState`;
- `current_node`;
- `pending_interrupt`;
- validation loop cursor;
- JSONStorage.

Re-entry rules:

- Если `pending_interrupt.status = "waiting"`, `entry_point_from_session` ведёт в `pending_interrupt.node`.
- `current_node` remains a debug marker; it is not the sole router for HITL recovery.
- Если recovered resume value присутствует, interrupt node обрабатывает его и очищает `pending_interrupt`.
- Если recovered resume value отсутствует, CLI/API показывает `pending_interrupt.payload` и ждёт ввод пользователя без создания новой попытки.

Persistent LangGraph checkpointer can be introduced later, but is not required for Stage 1-2 MVP.

---

## 9. Observability

Every node should be traced as a separate Langfuse span.

Root trace metadata:

- `session_id`;
- user id if available;
- raw input;
- normalized summary;
- final status;
- current node;
- shortage status.

Stage 1 span metadata:

- classification;
- confidence summary;
- clarification reason;
- clarification attempts;
- selected option id/freeform marker;
- resolved layer ids;
- fallback layer ids;
- unresolved details;
- final validation status;
- preview hash/text summary.

Stage 2 span metadata:

- candidate count requested/generated;
- duplicate count;
- hard gate failure counts;
- score component summaries;
- ranked candidate ids;
- validation attempts;
- refinement attempts;
- approved count;
- shortage reason.

Prompt trace metadata:

- layer ids;
- source paths;
- prompt hashes;
- stage context hash;
- model/provider;
- token and cost metadata if available.

Approved text `trace_refs`:

```json
{
  "trace_id": "...",
  "generator_span_id": "...",
  "scorer_span_id": "...",
  "validator_span_ids": [],
  "refiner_span_ids": [],
  "prompt_context_hash": "...",
  "candidate_id": "c01",
  "version_id": "c01_v1"
}
```

---

## 10. Implementation Order

Recommended implementation order:

1. Replace old `SessionState` orchestration fields with new models.
2. Implement `PromptRegistry`.
3. Implement `PromptComposer`.
4. Implement Stage 1 nodes and routing.
5. Implement CLI/API interrupt handlers for Stage 1.
6. Implement Stage 2 candidate generation.
7. Implement deduplication/scoring/ranking.
8. Implement validation/refinement loop.
9. Implement `ApprovedTextSelector` and shortage object.
10. Connect seed prompt layers.
11. Add golden scenario tests.
12. Only after Stage 1-2 are stable, write separate Stage 3 visual pipeline spec.

---

## 11. Golden Scenario Acceptance

At minimum, implementation must pass scenarios for:

- правдивые истории про ёжика зимой для 3 лет;
- сказочные истории про лису для 5 лет;
- мифологическая мягкая история про солнце или ветер;
- поучительная история про мытьё рук;
- поучительная сказка про переход через дорогу;
- fallback `PARROT` for `какаду` with unresolved detail;
- multiple subjects with explicit `subject_continuity_policy`;
- character request with `character_profile`;
- empty/meaningless input;
- contradiction `TRUTH` + fantastic hard detail;
- unsupported hard style requirement;
- refiner must not change theme/main subject/character profile;
- selector must use validated candidate versions;
- accepted draft создаёт item в `validated_candidate_versions` даже без refinement;
- execution lookup missing source ведёт в reresolve/clarify/stop и не делает silent layer swap;
- interrupt restart сохраняет `completion_status = waiting_user` и `pending_interrupt`;
- recovered interrupt resume не увеличивает clarification attempts дважды;
- HITL fallback approved text маркируется `hitl_fallback_accepted`;
- `retry_generation` очищает active `shortage.fallback_acceptance_policy`.

Acceptance is behavioral, not snapshot text equality.

---

## 12. Completion Criteria

The orchestrator implementation is complete when:

- active graph starts at Stage 1 analysis;
- all Stage 1 nodes persist state;
- all clarification branches route back to analysis/classification;
- `normalized_request` is separate from process metadata;
- `PromptRegistry` validates metadata and stable ids;
- `PromptComposer` creates stage-specific contexts;
- Stage 2 generates candidate pool with default count 20;
- duplicate themes are filtered or marked;
- hard gates can exclude candidates before approval;
- validation/refinement loop respects per-candidate counters;
- refiner preserves immutable fields;
- selector читает normal approved text content из `validated_candidate_versions`, а не из `candidate_texts` или `ranked_candidates`;
- selector может включить HITL fallback только из `safe_fallback_candidates` плюс explicit `shortage.fallback_acceptance_policy`;
- accepted draft создаёт объект `validated_candidate_versions`;
- execution lookup failure никогда не делает silent prompt layer swap;
- interrupt nodes сохраняют `completion_status = waiting_user` и `pending_interrupt`;
- final output is `approved_texts`;
- shortage is explicit when output count is not met;
- no image/animation node is part of current graph;
- JSONStorage can restore meaningful progress;
- Langfuse traces contain enough debug refs to inspect approved text decisions.
