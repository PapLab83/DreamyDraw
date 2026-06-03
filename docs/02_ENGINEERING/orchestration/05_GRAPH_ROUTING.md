# Graph Routing

## Routing Functions

Routing lives in `src/core/graph/routing.py`.

Recommended functions:

```text
route_after_request_classification
route_after_candidate_layer_resolution
route_after_final_parameter_validation
route_after_prompt_context_preparation
route_after_candidate_validator
route_after_candidate_refiner
route_after_approved_text_selector
route_after_shortage_fallback
entry_point_from_session
```

### Classification routing

```text
complete -> candidate_layer_resolution
needs_clarification -> clarification_interrupt
empty_or_meaningless -> clarification_interrupt
contradictory -> clarification_interrupt
unsupported_hard_requirement -> clarification_interrupt
stop -> END
```

После `clarification_interrupt` граф идёт в `input_analysis`.

Правила terminal stop:

- `stop` из `request_classification` используется, когда запрос нельзя довести до исполнимой интерпретации без нового осмысленного ввода: empty/meaningless после лимита, unresolved contradiction, unsupported hard requirement without relaxation или отсутствие понятной темы.
- `stop` из `request_classification` выставляет `is_completed = true`, `completion_status = "stopped_unresolved_request"`, очищает `pending_interrupt` и сохраняет причину в `interpretation_state.stop_reason` или эквивалентном structured issue field.
- `failed` не используется для продуктового unresolved request; он зарезервирован для technical/non-recoverable failures.
- `stopped_by_user` используется только для явного пользовательского stop action.
- `approved_texts` остаётся пустым, и Stage 2 не запускается.

### Candidate layer resolution routing

`route_after_candidate_layer_resolution`:

```text
resolved -> final_parameter_validation
needs_clarification -> clarification_interrupt
unsupported_hard_requirement -> clarification_interrupt
stop -> END
```

Правила:

- Routing читает `interpretation_state.layer_resolution_result.status`.
- `needs_clarification` используется, когда fallback/relaxation требует выбора пользователя.
- `unsupported_hard_requirement` ведёт в `clarification_interrupt`, если можно предложить relaxation; иначе node должна выставить `stop`.
- После `clarification_interrupt` граф возвращается в `input_analysis`.
- `stop` выставляет `is_completed = true`, `completion_status = "stopped_unresolved_request"`, очищает `pending_interrupt`, сохраняет причину в `interpretation_state.stop_reason` / structured `stop_issues`, выставляет `stopped_at`, оставляет `approved_texts` пустым и не запускает Stage 2.

### Prompt context preparation routing

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

### Final parameter validation routing

`route_after_final_parameter_validation`:

```text
pass -> preview
fail_reclassify -> request_classification
stop -> END
```

Правила:

- Routing читает `interpretation_state.validation_result.status`.
- `fail_reclassify` должен передать `interpretation_state.validation_result` в `request_classification`; classification учитывает причину validation failure, а не повторяет старую классификацию только по analysis/lookup hints.
- `stop` for product/unresolved request writes `is_completed = true`, `completion_status = "stopped_unresolved_request"`, `interpretation_state.stop_reason`, `interpretation_state.stop_issues` and `interpretation_state.stopped_at`.
- Technical/non-recoverable validation failure writes `completion_status = "failed"` and diagnostic issues, but does not introduce `interpretation_state.validation_result.status = "failed"`.
- `completion_status = "failed"` is used only for technical/non-recoverable validation failures, not for hard unsupported user requirements.
- Если причина является hard unsupported requirement без acceptable relaxation, пользовательский сценарий завершается как `stopped_unresolved_request` без Stage 2.

### Validation loop routing

`candidate_validator` routing uses:

- accepted count;
- selector-eligible unique accepted count;
- текущий candidate id;
- active version id/source;
- candidate status;
- refinement attempts;
- ranked queue pointer;
- output count.

Routing:

```text
accepted and selector_eligible_unique_accepted_count >= output_count -> approved_text_selector
accepted and selector_eligible_unique_accepted_count < output_count -> next ranked candidate validator
needs_revision and attempts_left -> candidate_refiner
needs_revision and no_attempts_left -> next ranked candidate validator
rejected -> next ranked candidate validator
queue_exhausted -> approved_text_selector
```

Реализация может представить "next ranked candidate validator" как обновление `validation_loop_state` и возврат в ту же ноду `candidate_validator`.

### Shortage routing

`route_after_approved_text_selector`:

```text
shortage.status = enough
  -> END

shortage.status != enough and shortage_hitl_enabled = false
  -> END

shortage.status != enough and shortage_hitl_enabled = true
  -> shortage_fallback_interrupt
```

Дополнительное правило:

- Если для текущего shortage episode уже применён `shortage.user_decision = "accept_fewer"` или сохранён `shortage.fallback_acceptance_policy`, `route_after_approved_text_selector` не должен снова вести в `shortage_fallback_interrupt`; terminal status должен быть `completed_with_shortage_user_accepted`.

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
