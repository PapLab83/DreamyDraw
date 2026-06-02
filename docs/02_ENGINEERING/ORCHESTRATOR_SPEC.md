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
  -> candidate_text_generator
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
  -> END if enough
  -> shortage_fallback_interrupt? if shortage HITL enabled
  -> END if shortage HITL disabled
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
- draft `prompt_context` candidates;
- per-field lookup confidence.

Rules:

- Read YAML metadata only.
- Do not load full prompt bodies.
- Do not produce final execution context.
- Do not promise unsupported layers.

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

Rules:

- Increment `interpretation_state.clarification_attempts`.
- Persist session before interrupt when possible.
- After resume, route to `input_analysis`, not to validation.
- A selected option is input for re-analysis, not a final patch blindly applied.

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
- session-level `prompt_context`;
- `interpretation_state.layer_resolution_summary`.

Rules:

- The canonical layer id is stable UPPER_SNAKE `id`.
- File path is stored separately in `source`.
- Fallback decisions include `requested`, `fallback_layer_id`, `source`, `reason`.
- Hard unsupported requirements must route back to clarification or stop.

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

- freeze execution-level `prompt_context`;
- prepare Stage 2 context references;
- ensure stage prompts can be composed without changing normalized parameters.

Outputs:

- `prompt_context`;
- initial `stage_prompt_context` refs/summaries.

Rules:

- Do not change `normalized_request`.
- Do not load all prompt bodies eagerly unless required.
- Store ids/hashes/summaries in state, not huge full prompts.

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

Правила:

- Выбирать из `validated_candidate_versions`, а не из исходных drafts.
- Если кандидат проходил refinement, использовать latest accepted validated version.
- Никогда не включать кандидатов с critical hard gate failures.
- Не включать duplicate themes.
- `candidate_texts` и `ranked_candidates` не являются допустимыми источниками финального текста для selector; это только context и ordering inputs.

Approved text shape:

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

Shortage shape:

```json
{
  "requested": 5,
  "approved": 3,
  "status": "not_enough_valid_candidates",
  "reason": "ranked queue exhausted before output_count"
}
```

#### `shortage_fallback_interrupt`

Type: optional LangGraph interrupt.

MVP may skip this interrupt and finish with shortage. If enabled, options are:

- accept fewer approved texts;
- accept safe fallback candidates with known issues;
- retry candidate generation;
- stop.

`safe_fallback_candidates` exist only for shortage path and must not be mixed into `approved_texts` without explicit selector/user decision.

---

## 4. Routing Functions

Routing lives in `src/core/graph/routing.py`.

Recommended functions:

```text
route_after_request_classification
route_after_final_parameter_validation
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

After `clarification_interrupt`, the graph routes to `input_analysis`.

### 4.2 Validation loop routing

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

Implementation can represent "next ranked candidate validator" by updating loop cursor in state and returning to the same `candidate_validator` node.

---

## 5. SessionState Contract

### 5.1 Top-level fields

`SessionState` must include:

```text
session_id
request
current_node
is_completed
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
```

Old fields from the previous orchestration model should not be part of the new business flow. If kept temporarily for CLI compatibility, they must be marked as deprecated and not read by new nodes.

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

Rules:

- `confidence`, `requires_clarification` and `preview_text` are not inside `normalized_request`.
- `current_config` is a snapshot/default source, not Stage 2 execution source.
- `user_context` is object-with-empty-state, not `null`.
- `visual_preferences` are preserved for downstream but not used directly by text pipeline.

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

Rules:

- `id` is canonical stable UPPER_SNAKE.
- `source` stores the prompt file path.
- Missing narrow details can be stored as unresolved freeform context.

### 5.7 `pipeline_counters`

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

Used after request is complete enough to execute.

Output:

```json
{
  "resolved_layers": [],
  "fallback_layers": [],
  "unresolved_details": []
}
```

Execution lookup fixes what Stage 2 will use. It must not change the interpretation shown in preview.

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
- pending HITL fields;
- validation loop cursor;
- JSONStorage.

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
- selector must use validated candidate versions.

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
- selector approves validated versions only;
- final output is `approved_texts`;
- shortage is explicit when output count is not met;
- no image/animation node is part of current graph;
- JSONStorage can restore meaningful progress;
- Langfuse traces contain enough debug refs to inspect approved text decisions.
