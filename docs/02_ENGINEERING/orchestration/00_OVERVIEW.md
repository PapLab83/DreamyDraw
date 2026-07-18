# Orchestration Overview

Статус: активная техническая спецификация реализации Stage 1-2.

Этот каталог описывает clean-slate LangGraph-оркестрацию DreamyDraw. Текущий scope заканчивается на `approved_texts`; image/animation/full visual pipeline является отдельной будущей итерацией.

## Sources And Priority

Business source:

- `../TARGET_ORCHESTRATION_LOGIC.md` — бизнес-логика и продуктовый поток.

Contract sources:

- `../contracts/NORMALIZED_STATE_CONTRACT.md`
- `../contracts/PROMPT_FILE_CONTRACT.md`
- `../contracts/PROMPT_LOOKUP_CONTRACT.md`
- `../contracts/PROMPT_COMPOSITION_CONTRACT.md`
- `../contracts/STAGE_CONTRACTS.md`
- `../contracts/SCOPE_BOUNDARIES.md`
- `../contracts/GOLDEN_SCENARIOS.md`

Technical mapping:

- files in this `orchestration/` directory.

Priority rule: when a nested object shape conflicts with a contract file, update the contract and the orchestration spec together. Do not silently choose a convenient shape in implementation.

## Reading Order

1. `00_OVERVIEW.md` — scope, architecture, graph summary.
2. `01_STAGE_1_INTERPRETATION.md` — Stage 1 interpretation and prompt context preparation.
3. `02_STAGE_2_TEXT_PIPELINE.md` — Stage 2 text pipeline to `approved_texts`.
4. `03_STATE_AND_RECOVERY.md` — SessionState, persistence, interrupts, restart/recovery.
5. `04_PROMPT_SYSTEM.md` — PromptRegistry, lookup, PromptComposer.
6. `05_GRAPH_ROUTING.md` — routing functions and executable route tables.
7. `06_OBSERVABILITY.md` — Langfuse, trace refs.
8. `07_IMPLEMENTATION_READINESS.md` — implementation order, golden scenarios, completion criteria.

## Scope

### In scope

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
- shortage detection and fallback state;
- JSONStorage persistence;
- Langfuse observability;
- migration-ready implementation constraints.

Финальный успешный output:

```text
SessionState.approved_texts
```

### Out of scope

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

## Core Architecture

### Principle

Активный Release 1 фасад является тонким слоем над LangGraph:

```text
CLI
  -> Stage1_2Orchestrator.start_session(...)
  -> Stage1_2Orchestrator.run_pipeline(...)
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

### Runtime components

| Component | Responsibility |
| --- | --- |
| `Stage1_2Orchestrator` | Thin facade for session lifecycle and graph invocation. |
| `GraphState` | Transport wrapper around `SessionState` plus resume/service fields. |
| `SessionState` | Durable state and source of truth between nodes/processes. |
| `JSONStorage` | Long-term session persistence. |
| `MemorySaver` | In-process LangGraph checkpointer for interrupt/resume mechanics. |
| `PromptRegistry` | Prompt layer metadata index and lookup service. |
| `PromptComposer` | Stage-specific prompt context builder. |
| Langfuse client | Tracing, span metadata, prompt/context debug refs. |

### GraphState

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

Resume input contract:

```json
{
  "interrupt_type": "request_clarification",
  "selected_option_id": "opt_1",
  "freeform_text": null,
  "action": null,
  "accepted_candidate_ids": null,
  "known_issues_acknowledged": null
}
```

Rules:

- Allowed `interrupt_type` values: `request_clarification`, `shortage_fallback`.
- `user_input` is transient and is cleared after the relevant interrupt node handles it.
- There is no canonical top-level `session.user_feedback` field in the new orchestration contract.
- If durable history of user choices is needed, it must be written explicitly into a process/history field owned by the interrupt node, not inferred from `GraphState`.

---

## Target LangGraph

### Node names

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

Canonical `stage_id` использует snake_case и совпадает с graph node ids / `stage_prompt_context.entries[].stage`. PascalCase names остаются только display/contract labels.

| `stage_id` | Contract/display label |
| --- | --- |
| `candidate_text_generator` | `CandidateTextGenerator` |
| `topic_deduplicator` | `TopicDeduplicator` |
| `scorer` | `Scorer` |
| `ranker` | `Ranker` |
| `candidate_validator` | `Validator` |
| `candidate_refiner` | `Refiner` |
| `approved_text_selector` | `ApprovedTextSelector` |

### Graph overview

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
  resolved
    -> final_parameter_validation
  needs_clarification / unsupported_hard_requirement
    -> clarification_interrupt
  stop
    -> END

final_parameter_validation
  pass
    -> preview
  fail
    -> request_classification
  stop
    -> END

preview
  -> prompt_context_preparation

prompt_context_preparation
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
        -> approved_text_selector if selector_eligible_unique_accepted_count >= output_count
        -> next candidate if selector_eligible_unique_accepted_count < output_count
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
