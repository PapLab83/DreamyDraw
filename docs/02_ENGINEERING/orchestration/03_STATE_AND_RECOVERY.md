# State And Recovery

## SessionState Contract

### Top-level fields

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
stage_status
prompt_context
stage_prompt_context
candidate_texts
deduplication_results
scores
ranked_candidates
validation_results
refined_candidate_versions
validated_candidate_versions
approved_texts
shortage
safe_fallback_candidates
validation_loop_state
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
stopped_unresolved_request
stopped_by_user
failed
```

Правила:

- `is_completed = true` означает, что graph достиг terminal state.
- `completion_status = completed_enough` означает, что requested `output_count` выполнен только normal approved texts из `validated_candidate_versions`.
- `completion_status = completed_with_shortage` означает terminal shortage и должен явно отображаться UI/API.
- `completion_status = completed_with_shortage_user_accepted` означает, что пользователь явно принял fewer/fallback results.
- `completion_status = stopped_unresolved_request` означает, что Stage 1 не смог получить исполнимый запрос после clarification/arbitration rules; это не technical failure и не user-approved stop.
- `completion_status = stopped_by_user` означает явное действие пользователя остановить сценарий.
- `completion_status = failed` означает technical или non-recoverable execution failure.
- `completed_with_shortage` и `completed_with_shortage_user_accepted` не эквивалентны full success.

### `request`

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

### `stage_status`

`stage_status` хранит durable progress markers для non-interrupt recovery. Top-level result fields могут существовать как пустые списки или объекты, поэтому recovery не должен полагаться только на `exists/missing`.

Минимальная форма:

```json
{
  "candidate_text_generator": {
    "status": "not_started|completed|failed",
    "completed_at": null,
    "input_hash": null,
    "output_hash": null
  },
  "topic_deduplicator": {
    "status": "not_started|completed|failed",
    "completed_at": null,
    "input_hash": null,
    "output_hash": null
  },
  "scorer": {
    "status": "not_started|completed|failed",
    "completed_at": null,
    "input_hash": null,
    "output_hash": null
  },
  "ranker": {
    "status": "not_started|completed|failed",
    "completed_at": null,
    "input_hash": null,
    "output_hash": null
  },
  "validation_loop": {
    "status": "not_started|running|completed|failed",
    "completed_at": null,
    "input_hash": null,
    "output_hash": null
  },
  "approved_text_selector": {
    "status": "not_started|completed|failed",
    "completed_at": null,
    "input_hash": null,
    "output_hash": null
  }
}
```

Правила:

- `not_started` должен быть явным status value; `null` field value допускается только при миграции, но не как нормальный recovery signal.
- Пустой список результата может быть валидным completed output только если соответствующий `stage_status.<stage>.status = "completed"`.
- `input_hash` и `output_hash` позволяют отличить валидный cached result от устаревшего состояния после изменения upstream snapshot.
- Если status marker и result field противоречат друг другу, recovery ведёт к earliest safe verification node.

### `normalized_request`

`normalized_request` describes the generation task:

```json
{
  "content_format": "story",
  "truth_mode": "TRUTH",
  "utility_mode": "NARRATIVE",
  "utility_topic": null,
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
        "type": "format",
        "role": "content_format",
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
        "type": "utility",
        "role": "utility_mode",
        "id": "UTILITY_NARRATIVE_BASE",
        "source": "utility_modes/NARRATIVE/BASE.md",
        "reason": "utility_mode=NARRATIVE"
      },
      {
        "type": "age",
        "id": "AGE_3",
        "source": "ages/3/BASE.md",
        "reason": "target_age=3"
      },
      {
        "type": "language",
        "role": "audience_language",
        "id": "LANGUAGE_RU_AUDIENCE",
        "source": "languages/ru/AUDIENCE.md",
        "reason": "audience_language=ru"
      },
      {
        "type": "language",
        "role": "result_language",
        "id": "LANGUAGE_RU_RESULT",
        "source": "languages/ru/RESULT.md",
        "reason": "result_language=ru"
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
- `utility_topic` фиксирует конкретную teaching/practical тему, когда она есть: например `hygiene_handwashing`, `road_crossing`, `stranger_candy_safety`.
- Если `utility_mode = TEACHING` и metadata lookup нашёл подходящий topic layer, `normalized_request.utility_topic` должен быть заполнен, а topic layer должен попасть в `normalized_request.prompt_context.resolved_layers` с `type = "utility"` и `role = "utility_topic"`.
- Если конкретный teaching topic не найден в PromptRegistry, он остаётся в unresolved/freeform context и может требовать clarification, fallback или hard unsupported decision по обычным правилам.

### `interpretation_state`

```json
{
  "confidence": {
    "content_format": 90,
    "truth_mode": 85,
    "utility_mode": 80,
    "target_age": 95,
    "main_subject": 95
  },
  "classification": "complete",
  "requires_clarification": false,
  "clarification_reason": null,
  "clarification_options": [],
  "clarification_attempts": 0,
  "max_clarification_attempts": 5,
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
  },
  "stop_reason": null,
  "stop_issues": [],
  "stopped_at": null
}
```

Rules:

- Confidence values use the canonical `0..100` scale.
- Routing thresholds must not treat confidence as `0..1` floats.
- `max_clarification_attempts = 5` applies to the whole clarification contour, not to a single branch.
- `stop_reason` is populated only when classification/final validation stops before Stage 2 because the request remains unresolved.
- `stop_issues` stores structured issues that explain why no executable request could be formed.
- `stopped_at` stores the terminal stop timestamp for `completion_status = "stopped_unresolved_request"`.

### `preview_state`

```json
{
  "preview_text": "Я подготовлю 5 спокойных правдивых историй про ёжика зимой в лесу для ребёнка 3 лет.",
  "shown_to_user": true,
  "approved_implicitly": true
}
```

### `prompt_context`

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
      "type": "format",
      "role": "content_format",
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
      "type": "utility",
      "role": "utility_mode",
      "id": "UTILITY_NARRATIVE_BASE",
      "source": "utility_modes/NARRATIVE/BASE.md",
      "reason": "utility_mode=NARRATIVE"
    },
    {
      "type": "age",
      "id": "AGE_3",
      "source": "ages/3/BASE.md",
      "reason": "target_age=3"
    },
    {
      "type": "language",
      "role": "audience_language",
      "id": "LANGUAGE_RU_AUDIENCE",
      "source": "languages/ru/AUDIENCE.md",
      "reason": "audience_language=ru"
    },
    {
      "type": "language",
      "role": "result_language",
      "id": "LANGUAGE_RU_RESULT",
      "source": "languages/ru/RESULT.md",
      "reason": "result_language=ru"
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
```

Правила:

- `id` — canonical stable UPPER_SNAKE.
- `type` совпадает с enum из `PROMPT_FILE_CONTRACT.md`: `format`, `truth_mode`, `style`, `substyle`, `entity`, `utility`, `age`, `language`, `stage`, `validator`, `refiner`.
- `role` является orchestration role и уточняет назначение слоя внутри resolved context, например `content_format`, `utility_mode`, `utility_topic`, `audience_language`, `result_language`.
- Для слоёв, где contract type уже однозначен для orchestration, `role` может совпадать с `type` или отсутствовать; для `utility` и `language` role обязателен.
- `source` хранит путь к prompt file.
- Узкие детали без точного слоя могут храниться как unresolved freeform context.
- Top-level `prompt_context` является execution snapshot, а не canonical interpretation object.
- Layer decisions копируются из `normalized_request.prompt_context`.
- Execution metadata хранится здесь, а не внутри `normalized_request.prompt_context`.

### `stage_prompt_context`

`stage_prompt_context` хранит компактные per-stage context refs и summaries, созданные `PromptComposer`. По умолчанию он не должен хранить full prompt bodies.

Минимальная форма:

```json
{
  "entries": [
    {
      "stage": "candidate_text_generator",
      "candidate_id": null,
      "version_id": null,
      "attempt": null,
      "source_prompt_context_hash": "hash-of-session-prompt-context",
      "stage_context_hash": "hash-of-stage-context-summary-and-refs",
      "layer_ids": [
        "CONTENT_FORMAT_STORY",
        "TRUTH_BASE",
        "UTILITY_NARRATIVE_BASE",
        "AGE_3",
        "LANGUAGE_RU_AUDIENCE",
        "LANGUAGE_RU_RESULT",
        "TRUTH_ANIMAL_HEDGEHOG"
      ],
      "fallback_layer_ids": [],
      "unresolved_detail_labels": [],
      "body_policy": "lazy_not_persisted",
      "context_summary": "Полный creative context для спокойных правдивых историй про ёжика для возраста 3.",
      "created_at": "2026-06-02T12:10:00Z",
      "version": 1
    },
    {
      "stage": "candidate_validator",
      "candidate_id": "c02",
      "version_id": "c02_v2",
      "attempt": 2,
      "source_prompt_context_hash": "hash-of-session-prompt-context",
      "stage_context_hash": "hash-of-validator-context-for-c02-v2-attempt-2",
      "layer_ids": [],
      "fallback_layer_ids": [],
      "unresolved_detail_labels": [],
      "body_policy": "lazy_not_persisted",
      "context_summary": "Validator context for c02_v2 with truth, age, utility and subject continuity constraints.",
      "created_at": "2026-06-02T12:18:00Z",
      "version": 1
    }
  ]
}
```

Правила:

- `stage_prompt_context.entries[]` является canonical shape; строковые compound keys не являются контрактом.
- Static contexts имеют `candidate_id = null`, `version_id = null`, `attempt = null`.
- Dynamic contexts для `candidate_validator` и `candidate_refiner` должны включать `candidate_id`, `version_id` и `attempt`.
- `source_prompt_context_hash` идентифицирует top-level `session.prompt_context` snapshot, использованный как input.
- `stage_context_hash` идентифицирует конкретный stage context refs/summary.
- Если `session.prompt_context.snapshot_hash` меняется, существующие stage contexts становятся invalid.
- При `retry_generation` все dynamic Stage 2 entries удаляются; static entries можно сохранить только при совпадении `source_prompt_context_hash` с текущим `prompt_context.snapshot_hash`.
- Если есть сомнение в валидности stage context после retry, Stage 2 nodes должны пересоздать нужный entry через `PromptComposer`.
- Full prompt bodies загружаются lazy и по умолчанию не сохраняются в `SessionState`.
- Полный prompt text можно логировать в Langfuse или debug artifacts только согласно debug/prompt logging policy.
- Stage nodes используют эту единую форму и не должны изобретать несовместимые per-node context formats.
- `candidate_text_generator`, `topic_deduplicator`, `scorer`, `ranker` и `approved_text_selector` обычно используют static contexts.
- `candidate_validator` создаёт context для каждой пары candidate/version и каждой validation attempt.
- `candidate_refiner` создаёт context для каждой пары candidate/version и каждой refinement attempt; validator issues входят в stage context summary/hash.

### `refined_candidate_versions`

`refined_candidate_versions` хранит версии, созданные `candidate_refiner` и ожидающие повторной validation. Эти версии durable, но не считаются approved и не могут попасть в `approved_texts` без accepted validation result.

Минимальная форма item:

```json
{
  "candidate_id": "c02",
  "version_id": "c02_v2",
  "source_candidate_id": "c02",
  "source_version_id": "c02_v1",
  "version_origin": "refined",
  "theme": "ёжик ищет сухие листья",
  "text": "Исправленный текст...",
  "questions": ["Что ёжик искал?"],
  "changes_summary": "Убрана человеческая речь, сохранена тема.",
  "created_by_node": "candidate_refiner",
  "created_at": "2026-06-02T12:17:00Z",
  "trace_refs": {}
}
```

Правила:

- `theme`, `main_subject`, required subjects и `character_profile` должны совпадать с исходным candidate.
- `candidate_refiner` пишет сюда revised version перед возвратом в `candidate_validator`.
- `candidate_validator` читает revised text отсюда только когда `validation_loop_state.active_text_source = "refined_candidate_versions"`.
- Accepted item всё равно создаётся отдельно в `validated_candidate_versions`.

### `validation_loop_state`

`validation_loop_state` хранит durable cursor validation/refinement loop. Это canonical source для текущего rank index, active candidate/version, accepted count и selector-eligible accepted count.

Минимальная форма:

```json
{
  "current_rank_index": 0,
  "active_candidate_id": "c02",
  "active_version_id": "c02_v2",
  "active_version_origin": "refined",
  "active_text_source": "refined_candidate_versions",
  "accepted_count": 1,
  "selector_eligible_unique_accepted_count": 1
}
```

Правила:

- `current_rank_index` указывает на позицию в `ranked_candidates`.
- `active_candidate_id` должен совпадать с candidate id на текущей позиции ranked queue.
- `active_version_id` определяет конкретную версию, которую validator должен проверить.
- `active_version_origin` принимает `draft` или `refined`.
- `active_text_source` принимает `candidate_texts` или `refined_candidate_versions`.
- `ranker` создаёт первый canonical draft version id по шаблону `{candidate_id}_v1`, например `c02_v1`, при первичной инициализации `validation_loop_state`.
- Для initial draft version `active_version_id = "{candidate_id}_v1"`, `active_version_origin = "draft"` и `active_text_source = "candidate_texts"`.
- `candidate_texts` не обязаны хранить `version_id`; draft version id является loop-level identity, а не частью generator output contract.
- Все следующие revised versions используют монотонную нумерацию `{candidate_id}_v2`, `{candidate_id}_v3` и хранятся в `refined_candidate_versions`.
- Validator читает active text через `active_text_source`, а не выбирает произвольный latest text по `candidate_id`.
- После успешного refiner output graph сохраняет revised version в `refined_candidate_versions` и обновляет active version fields перед возвратом в validator.
- `accepted_count` считает только normal accepted versions в `validated_candidate_versions`.
- `selector_eligible_unique_accepted_count` считает только normal accepted versions, которые selector сможет использовать после duplicate-theme exclusion и critical gate exclusion.
- Validation loop stop condition uses `selector_eligible_unique_accepted_count >= normalized_request.output_count`, not raw `accepted_count`.
- HITL fallback count для shortage считается отдельно как union `validated_candidate_versions + accepted safe_fallback_candidates`.
- При переходе к следующему ranked candidate routing transition обновляет `current_rank_index`, `active_candidate_id`, создаёт `active_version_id = "{candidate_id}_v1"`, выставляет `active_version_origin = "draft"` и `active_text_source = "candidate_texts"`.

### `pipeline_counters`

```json
{
  "candidate_attempts": {
    "c01": {
      "validation_attempts": 1,
      "refinement_attempts": 0
    }
  }
}
```

Rules:

- Canonical clarification counter lives in `interpretation_state.clarification_attempts`.
- `pipeline_counters` must not duplicate clarification attempt state.
- Validation loop cursor, accepted count и selector-eligible accepted count живут в `validation_loop_state`, а не в `pipeline_counters`.

### `pending_interrupt`

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
    "action": "accept_fewer|accept_safe_fallback|retry_generation|stop",
    "accepted_candidate_ids": ["candidate_id"],
    "known_issues_acknowledged": "boolean"
  }
}
```

Правила shortage resume payload:

- `accepted_candidate_ids` обязателен только для `action = "accept_safe_fallback"`.
- `accepted_candidate_ids` должен быть subset of `safe_fallback_candidates[].candidate_id`.
- `known_issues_acknowledged = true` обязателен для `accept_safe_fallback`, если у выбранных safe fallback candidates есть `known_issues`.
- Interrupt node строит durable `shortage.fallback_acceptance_policy` из resume payload и сохраняет его в `SessionState`.

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


## Interrupts

### Request clarification

Used for:

- incomplete input;
- ambiguous input;
- low-confidence base fields;
- several close fallback candidates;
- user must choose between modes/styles/entities.

After resume: route to `input_analysis`.

### Empty or meaningless input

Used for:

- empty input;
- random characters;
- meta-input that is not a generation request.

Payload should include product explanation and starter variants. If user does not choose a variant or provide meaningful freeform text after attempt limit, route to `END`.

### Contradiction arbitration

Used for:

- hard detail conflicts with truth mode;
- selected/default config conflicts with explicit user request;
- age/safety constraints conflict with request.

Payload should explain the contradiction and offer supported alternatives.

After resume: route to `input_analysis`.

### Hard unsupported prompt requirement

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

### Shortage fallback

Interactive shortage fallback is optional in MVP. Shortage detection and durable shortage state are mandatory.

Default policy:

```text
shortage_hitl_enabled = false
```

Если policy не переопределена явно, MVP завершает pipeline с `completion_status = "completed_with_shortage"` и не создаёт shortage HITL interrupt.

Default MVP shortage behavior:

- detect shortage when approved text count is lower than requested output count;
- write `shortage.requested`, `shortage.approved`, `shortage.status` and `shortage.reason`;
- write `safe_fallback_candidates` when safe non-approved candidates exist;
- finish with `completion_status = "completed_with_shortage"`;
- do not create `pending_interrupt`;
- do not retry generation automatically.

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


## Persistence

### JSONStorage

JSONStorage is the durable source of truth.

Required behavior:

- save session after every mutating node;
- save before interrupt payload when possible;
- save after resume handling;
- store `approved_texts`;
- store `shortage`;
- store compact prompt refs, not necessarily full prompt bodies;
- preserve enough state for process restart.

### MemorySaver

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

Non-interrupt recovery:

```text
completion_status in completed_enough|completed_with_shortage|completed_with_shortage_user_accepted|stopped_unresolved_request|stopped_by_user|failed
  -> END

pending_interrupt.status = waiting
  -> pending_interrupt.node

interpretation_state.classification != complete
  -> input_analysis

interpretation_state.classification = complete
  and normalized_request incomplete/stale
  -> input_analysis

interpretation_state.layer_resolution_result.status = needs_clarification
  -> clarification_interrupt

interpretation_state.layer_resolution_result.status = unsupported_hard_requirement
  -> clarification_interrupt

interpretation_state.layer_resolution_result.status = stop
  and completion_status missing|running
  -> END with completion_status=stopped_unresolved_request

interpretation_state.layer_resolution_result.status = resolved
  and interpretation_state.validation_result missing|not_started
  -> final_parameter_validation

interpretation_state.validation_result missing|not_started
  and normalized_request.prompt_context missing/invalid
  -> candidate_layer_resolution

interpretation_state.validation_result missing|not_started
  and normalized_request.prompt_context resolved
  -> final_parameter_validation

interpretation_state.validation_result.status = fail_reclassify
  -> request_classification

interpretation_state.validation_result.status = stop
  and completion_status missing|running
  -> request_classification

interpretation_state.validation_result.status = pass
  and normalized_request.prompt_context missing/invalid
  -> candidate_layer_resolution

interpretation_state.validation_result.status = pass
  and normalized_request.prompt_context resolved
  and prompt_context missing/invalid
  -> prompt_context_preparation

prompt_context valid and stage_status.candidate_text_generator.status = not_started
  -> candidate_text_generator

stage_status.candidate_text_generator.status = completed
  and stage_status.topic_deduplicator.status = not_started
  -> topic_deduplicator

stage_status.topic_deduplicator.status = completed
  and stage_status.scorer.status = not_started
  -> scorer

stage_status.scorer.status = completed
  and stage_status.ranker.status = not_started
  -> ranker

stage_status.ranker.status = completed
  and stage_status.validation_loop.status in not_started|running
  -> candidate_validator using validation_loop_state

stage_status.validation_loop.status = completed
  and stage_status.approved_text_selector.status = not_started
  -> approved_text_selector

shortage.status != enough and shortage_hitl_enabled = true and shortage.user_decision is null
  -> shortage_fallback_interrupt

shortage.status != enough
  and (shortage.user_decision exists or shortage.fallback_acceptance_policy exists)
  -> approved_text_selector or END according to shortage routing
```

Правила:

- `entry_point_from_session` должен использовать persisted business state, а не только `current_node`.
- Recovery route выбирается по `stage_status`, `completion_status`, `pending_interrupt`, `validation_loop_state` и snapshot hashes.
- Recovery must evaluate `interpretation_state.layer_resolution_result.status` before falling back to `validation_result` or prompt context presence.
- Top-level result fields (`candidate_texts`, `scores`, `ranked_candidates`, `approved_texts` и т.д.) могут быть пустыми валидными результатами; `exists/missing` не является достаточным recovery signal.
- Stage 1 recovery must not jump into `candidate_layer_resolution` or `prompt_context_preparation` from a partial draft `normalized_request`.
- Если Stage 1 recovery ambiguous, route to `input_analysis`.
- Если `interpretation_state.classification != "complete"`, recovery возвращается в `input_analysis`, чтобы повторно прогнать analysis + metadata lookup + classification на persisted input/state.
- Если final validation ещё не запускалась, recovery продолжает Stage 1 через `candidate_layer_resolution` или `final_parameter_validation`, а не через `request_classification`.
- Если `interpretation_state.validation_result.status = "fail_reclassify"` при complete classification, recovery возвращается в `request_classification`, чтобы использовать persisted validation issues и решить clarify/stop/retry path.
- Если `interpretation_state.validation_result.status = "stop"` уже имеет terminal `completion_status`, recovery завершает в `END`; если terminal status missing из-за partial write, recovery возвращается в `request_classification` как earliest safe repair path.
- `prompt_context_preparation` is reachable on recovery only after final parameter validation has passed and `normalized_request.prompt_context` is resolved.
- Recovery не должен повторять Stage 1 или candidate generation, если durable downstream state уже существует и hash/snapshot checks валидны.
- Если recovered state противоречивый или snapshot hashes invalid, graph routes to the earliest safe verification node:
  - classification not complete or normalized request incomplete/stale -> `input_analysis`;
  - final validation missing/not_started and `normalized_request.prompt_context` missing/invalid -> `candidate_layer_resolution`;
  - final validation missing/not_started and `normalized_request.prompt_context` resolved -> `final_parameter_validation`;
  - final validation failed with complete classification -> `request_classification`;
  - final validation stopped with missing terminal status -> `request_classification`;
  - `normalized_request.prompt_context` missing or invalid -> `candidate_layer_resolution`;
  - `normalized_request.prompt_context` valid but top-level `session.prompt_context` missing, stale or invalid -> `prompt_context_preparation`;
  - Stage 2 snapshot/hash invalid -> earliest affected Stage 2 node;
  - validation loop partial -> `candidate_validator` using `validation_loop_state`.
- During validation recovery, `validation_loop_state` is the source of active candidate/version/source.

Persistent LangGraph checkpointer can be introduced later, but is not required for Stage 1-2 MVP.

---
