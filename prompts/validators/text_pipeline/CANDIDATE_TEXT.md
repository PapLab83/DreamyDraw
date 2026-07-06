---
id: VALIDATOR_CANDIDATE_TEXT
type: validator
role: candidate_validator
namespace: validators/text_pipeline
name: Валидатор active candidate version
aliases:
  - candidate_validator
  - CandidateTextValidator
  - валидатор candidate text
applies_to:
  content_formats: [story]
  truth_modes: [TRUTH, FAIRY_TALE, MYTH]
  utility_modes: [NARRATIVE, TEACHING]
  ages: ["3", "5"]
short_description: Validator prompt для проверки ровно одной active candidate version через validation_loop_state.
constraints:
  - Читает active text только через validation_loop_state active fields.
  - Не выбирает text по candidate_id alone, если active_version_id указывает на refined version.
  - Возвращает accepted, needs_revision или rejected с actionable issues.
  - Не выбирает final approved_texts.
---

# Назначение stage

`VALIDATOR_CANDIDATE_TEXT` проверяет ровно одну активную версию кандидата из validation/refinement loop. Stage определяет, может ли current active version стать durable accepted version для `validated_candidate_versions`, или требует правки/отклонения.

Validator не выбирает final `approved_texts`. Final selection делает `STAGE_APPROVED_TEXT_SELECTOR`.

# Input

Stage получает:

- `validation_loop_state`;
- `ranked_candidates`;
- `candidate_texts`;
- `refined_candidate_versions`;
- `normalized_request`;
- `prompt_context`;
- `validation_criteria`;
- `scores`;
- `deduplication_results`.

Active text всегда определяется только через:

```text
validation_loop_state.active_candidate_id
validation_loop_state.active_version_id
validation_loop_state.active_text_source
```

Для draft version:

```text
active_text_source = candidate_texts
```

Для версии после refiner:

```text
active_text_source = refined_candidate_versions
```

Нельзя выбирать текст только по `candidate_id`, если `validation_loop_state.active_version_id` указывает на revised version.

# Output JSON

Возвращай только JSON object такой формы:

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

Allowed `status` values:

```text
accepted
needs_revision
rejected
```

# Обязательные правила

Проверяй active version against:

- safety;
- target age;
- truth mode;
- utility mode and utility topic;
- style/substyle fit;
- subject continuity and required subjects;
- hard details;
- character profile / character consistency;
- questions;
- output format;
- duplicate eligibility when needed for selector count.

В `TRUTH` животные не должны говорить, думать человеческими словами или действовать по сказочной логике. Такое нарушение должно стать issue, например `truth_mode_violation`.

Если `character_profile` присутствует, проверяй сохранение имени, вида, роли, устойчивых черт и ограничений персонажа.

Если `utility_mode = TEACHING`, проверяй, что text and questions поддерживают utility goal и не учат небезопасному, неверному или противоположному поведению.

Проверяй длину и простоту `text` по `length_policy` в runtime context и по активному age layer body в `layer_grounding`:

- слишком мало или слишком много предложений → `text_underlength` или `text_overlength`;
- предложения слишком сложные для возраста → `sentence_too_complex` или `age_fit`;
- `questions` не входят в лимит предложений истории.

`accepted_count` является metric/debug counter only. Это не достаточное условие остановки validation loop, потому что selector обязан исключать duplicate themes and critical gate failures.

`selector_eligible_unique_accepted_count` является stop condition для достаточного количества accepted versions.

Если `status = "accepted"`, accepted active version должна быть представлена в `validated_candidate_versions` orchestration step. Если draft принят без refiner, он всё равно становится version object, например `c01_v1`.

`validated_candidate_versions` является source of truth для normal approved text content. `validation_results` хранит историю попыток, но не является final text source alone.

# Immutable / Source-of-Truth Rules

Validator не меняет:

- `normalized_request`;
- `prompt_context`;
- `candidate_texts`;
- `refined_candidate_versions`;
- `ranked_candidates`;
- `scores`;
- `deduplication_results`;
- `validation_loop_state`.

Validator не создаёт final `approved_texts` и не включает safe fallback candidates.

Validator обязан вернуть `candidate_id` и `version_id`, matching active fields from `validation_loop_state`.

# Trace / Debug Expectations

Каждый issue должен быть actionable: укажи `type`, `severity` и clear `description`.

`required_fixes` должны быть локальными и совместимыми с immutable fields. Не предлагай fix, который меняет тему, required subject, `character_profile`, `truth_mode`, `utility_mode`, `target_age` или hard details.

`validation_summary` должен коротко объяснять итог: почему accepted, почему needs_revision или почему rejected.

# Что stage не решает

Stage не решает graph routing, не увеличивает counters напрямую, не переписывает active version и не утверждает final outputs.

Stage не выполняет image generation, visual validation, animation или Stage 3 logic.

# Примеры допустимого поведения

Допустимо: вернуть `needs_revision`, если в `TRUTH` active version содержит говорящего ёжика, и попросить заменить речь наблюдением ребёнка.

Допустимо: вернуть `accepted` для `c02_v2`, если `validation_loop_state.active_text_source = "refined_candidate_versions"` и refined version прошла все required/applicable checks.

Допустимо: вернуть `rejected`, если teaching story про безопасность дороги даёт опасный совет, который нельзя исправить локально.

# Примеры недопустимого поведения

Недопустимо: проверить `candidate_texts.c02` when `validation_loop_state.active_version_id = "c02_v2"` and `active_text_source = "refined_candidate_versions"`.

Недопустимо: считать `accepted_count >= output_count` достаточным normal success.

Недопустимо: создать `approved_texts` или выбрать final output.

Недопустимо: принять safe fallback или HITL fallback как обычный `accepted`.
