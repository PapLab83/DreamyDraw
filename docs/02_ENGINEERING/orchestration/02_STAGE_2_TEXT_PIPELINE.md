# Stage 2 Text Pipeline

### Stage 2 nodes

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
- `candidate_text_generator` не обязан писать `version_id`; initial draft version id создаётся при входе в validation loop.

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
- `visual_potential` is a text-only heuristic based on theme clarity and illustration readiness; it must not call image generation, image prompt execution, visual validation or any Stage 3 pipeline.

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

Rules:

- `ranker` is the owner of primary `validation_loop_state` initialization.
- After writing `ranked_candidates`, `ranker` initializes `validation_loop_state` idempotently if `stage_status.validation_loop.status = "not_started"`.
- Initial cursor points to the first ranked candidate that can enter validation.
- Initial draft version id is `{candidate_id}_v1`, for example `c01_v1`.
- Initial `active_version_origin = "draft"` and `active_text_source = "candidate_texts"`.
- If recovery re-enters after ranker completed, `ranker` must not overwrite a non-empty/running `validation_loop_state`.

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
- Validator читает текущий текст через `validation_loop_state.active_candidate_id`, `active_version_id` и `active_text_source`.
- Для draft version `active_text_source = "candidate_texts"`, для версии после refiner — `active_text_source = "refined_candidate_versions"`.
- Validator не должен выбирать текст только по `candidate_id`, если `validation_loop_state.active_version_id` указывает на revised version.
- Останавливать validation loop, когда `validation_loop_state.selector_eligible_unique_accepted_count` достигает `output_count`, или когда ranked queue исчерпана.
- Увеличивать validation attempt counter per candidate.
- Если status = `accepted`, записывать принятую версию кандидата в `validated_candidate_versions`.
- `validation_results` хранит историю попыток; `validated_candidate_versions` хранит версии кандидатов, пригодные для финального выбора.
- Если validator принимает исходный draft без refiner, всё равно создаётся version object, например `c01_v1`, в `validated_candidate_versions`.
- `accepted_count` остаётся metric/debug counter и не является достаточным stop condition, потому что selector обязан исключать duplicate themes.
- `selector_eligible_unique_accepted_count` считает accepted versions, которые могут быть выбраны selector после duplicate-theme exclusion и critical gate exclusion.
- When validator returns `accepted`, the validator node or the immediate routing transition must atomically update `validated_candidate_versions`, `validation_loop_state.accepted_count` and `validation_loop_state.selector_eligible_unique_accepted_count`.
- `selector_eligible_unique_accepted_count` must be recomputed or updated from accepted validated versions, `deduplication_results`, accepted themes and critical gate status.

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
- `refined_candidate_versions` хранит revised versions до повторной validation; это не source of truth для final approval.

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
- `utility_topic`;
- `target_age`;
- hard details.

Правила:

- Максимум refinement attempts per candidate в MVP: `2`.
- Refiner не должен молча менять immutable fields.
- Если исправление невозможно без изменения immutable fields, stage возвращает issue/failure и граф переходит к следующему кандидату.
- Исправленная версия записывается в `refined_candidate_versions` как durable candidate version, ожидающая validation.
- После `status = "revised"` refiner обновляет `validation_loop_state.active_version_id`, `active_version_origin = "refined"` и `active_text_source = "refined_candidate_versions"`.
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
- `shortage` всегда существует как state object; при normal success selector выставляет `shortage.status = "enough"`.
- Normal success означает, что `output_count` набран только из `validated_candidate_versions`, без HITL fallback.
- Если набрано достаточно accepted versions из `validated_candidate_versions`, выставлять `completion_status = "completed_enough"` и сохранять `shortage.requested` / `shortage.approved`.
- Если accepted versions меньше, чем `output_count`, выставлять `shortage.status = "not_enough_valid_candidates"`, сохранять `shortage.requested` / `shortage.approved` и `safe_fallback_candidates`.
- Если shortage есть и HITL disabled, выставлять `completion_status = "completed_with_shortage"`.
- Если shortage есть и HITL enabled, selector не создаёт `pending_interrupt` и не выставляет terminal shortage status; routing ведёт в `shortage_fallback_interrupt`.
- `completed_with_shortage` является terminal status, но не success-equivalent к `completed_enough`; UI/API должны явно показывать shortage.
- Safe fallback candidates нельзя включать без явной durable HITL fallback acceptance policy в `shortage.fallback_acceptance_policy`.

Safe fallback eligibility:

```text
safe_fallback_candidate requires pass:
  - safety
  - age_fit
  - truth_fit
  - subject_continuity
  - hard_details
  - character_consistency when `character_profile` is present
  - utility_goal when `utility_mode = TEACHING`

safe_fallback_candidate may have known_issues:
  - weaker style_fit
  - lower novelty
  - weaker utility expression when it is not safety-critical
  - minor wording quality issues
  - lower score than normal approved text
```

Правила:

- Safe fallback не является normal approved text и не должен маскироваться под accepted validation result.
- Для `utility_mode = TEACHING`, `utility_goal` failure является critical, если fallback может научить неверному, небезопасному или противоположному поведению.
- Кандидат с critical hard gate failure не может попасть в `safe_fallback_candidates`, даже если `safety = pass`.
- Eligibility проверяется по canonical fields из `scores[].hard_gates`: `safety`, `truth_fit`, `age_fit`, `utility_goal`, `subject_continuity`, `hard_details`, `character_consistency`.
- Required gates must be present and `pass`: `safety`, `age_fit`, `truth_fit`, `subject_continuity` and `hard_details`.
- Conditional gates may be absent only when not applicable: `character_consistency` may be absent when `character_profile` is not present; `utility_goal` may be absent when `utility_mode != TEACHING`.
- Если required or applicable conditional hard gate отсутствует или имеет unknown/error status, selector не должен считать его pass для safe fallback; он должен исключить candidate или записать diagnostic issue.
- Каждый `safe_fallback_candidate` должен иметь `why_safe` и `known_issues`; пустой `known_issues` допустим только если кандидат не принят normal approval по некачественной/ранжировочной причине, а не по hard gate failure.
- Future extension may allow non-critical `hard_details` issues only when hard gate results carry explicit severity and selector policy allows it. MVP requires `hard_details = pass`.

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
- После применения `shortage.fallback_acceptance_policy` selector считает итоговый набор как union `validated_candidate_versions + accepted safe_fallback_candidates`.
- Если применена `shortage.fallback_acceptance_policy`, selector всегда выставляет `completion_status = "completed_with_shortage_user_accepted"`, даже если union добирает `output_count`.
- Если применена `shortage.fallback_acceptance_policy`, `shortage.status` не должен превращаться в обычный `enough`; он должен сохранить shortage outcome, например `not_enough_valid_candidates_user_accepted`.
- После `accept_fewer` или применения `shortage.fallback_acceptance_policy` `route_after_approved_text_selector` не должен повторно вести в `shortage_fallback_interrupt` для того же shortage episode.
- `completed_with_shortage_user_accepted` используется и для accepted fewer, и для accepted fallback; детализация хранится в `shortage.user_decision` и `shortage.fallback_acceptance_policy`.

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
  "why_safe": "Прошёл required/applicable hard gates: safety, age_fit, truth_fit, subject_continuity, hard_details и utility_goal для TEACHING.",
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

Правила:

- `shortage` всегда присутствует в `SessionState`.
- При достаточном количестве normal approved texts из `validated_candidate_versions` selector пишет `shortage.status = "enough"`, `requested = output_count`, `approved = approved_texts.length`, `reason = null`.
- При нехватке approved texts selector пишет `shortage.status = "not_enough_valid_candidates"` или более конкретный shortage status.
- При HITL-accepted fallback selector сохраняет shortage status как user-accepted shortage, например `not_enough_valid_candidates_user_accepted`, и не пишет `status = "enough"`.
- Routing не должен использовать отсутствие `shortage` как признак успеха.

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

Default MVP shortage behavior:

- shortage detection is mandatory;
- `approved_text_selector` always writes a durable `shortage` object;
- if normal approved texts are fewer than `output_count`, selector writes `completion_status = "completed_with_shortage"`;
- selector may prepare `safe_fallback_candidates` for diagnostics or future HITL;
- interactive shortage HITL/retry is available only when `shortage_hitl_enabled = true`.

Ownership:

- `approved_text_selector` writes `shortage` and `safe_fallback_candidates`.
- `approved_text_selector` does not create `pending_interrupt`.
- `route_after_approved_text_selector` routes to `shortage_fallback_interrupt` when shortage HITL is required.
- `shortage_fallback_interrupt` is the only node that creates shortage-related `pending_interrupt`, sets `completion_status = "waiting_user"` and calls `interrupt(payload)`.

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

- `accept_fewer` пишет `shortage.user_decision = "accept_fewer"`, сохраняет текущие `approved_texts`, сохраняет `shortage.status` и выставляет `completion_status = "completed_with_shortage_user_accepted"`.
- `accept_safe_fallback` пишет `shortage.user_decision = "accept_safe_fallback"` и сохраняет durable `shortage.fallback_acceptance_policy`.
- `shortage.fallback_acceptance_policy.accepted_candidate_ids` содержит явные safe fallback candidate ids, которые пользователь согласился принять.
- Selector может включить только явно принятые safe fallback candidates и должен пометить их `validation_status = "hitl_fallback_accepted"`.
- `shortage.fallback_acceptance_policy` является exit decision для текущего shortage episode, а не обычным дополнительным selector input.
- HITL-accepted fallback candidates не считаются обычными `validated_candidate_versions`; они отдельно маркируются в `approved_texts` и сохраняют `known_issues` / `why_safe`.
- Перед `retry_generation` текущий shortage snapshot добавляется в `shortage.history`.
- `retry_generation` увеличивает `shortage.retry_attempts`, пересоздаёт active shortage state и ведёт в `candidate_text_generator`.
- `stop` выставляет `completion_status = "stopped_by_user"` без изменения `approved_texts`.

При `retry_generation` сохраняются:

- `normalized_request`;
- `interpretation_state`;
- `preview_state`;
- `prompt_context`;
- reusable static refs из `stage_prompt_context` только если `source_prompt_context_hash` совпадает с текущим `prompt_context.snapshot_hash`;
- `shortage.history`.

При `retry_generation` очищаются или пересоздаются:

- `candidate_texts`;
- `deduplication_results`;
- `scores`;
- `ranked_candidates`;
- `validation_results`;
- `refined_candidate_versions`;
- `validated_candidate_versions`;
- `approved_texts`;
- `safe_fallback_candidates`;
- active `shortage.user_decision`;
- active `shortage.fallback_acceptance_policy`;
- dynamic Stage 2 `stage_prompt_context.entries` where `candidate_id`, `version_id` or `attempt` is not null;
- static Stage 2 `stage_prompt_context.entries` with stale `source_prompt_context_hash`;
- `validation_loop_state.current_rank_index`;
- `validation_loop_state.active_candidate_id`;
- `validation_loop_state.active_version_id`;
- `validation_loop_state.active_version_origin`;
- `validation_loop_state.active_text_source`;
- `validation_loop_state.accepted_count`;
- `validation_loop_state.selector_eligible_unique_accepted_count`;
- all Stage 2 `stage_status` entries back to `not_started`;
- Stage 2 `stage_status.*.completed_at`;
- Stage 2 `stage_status.*.input_hash`;
- Stage 2 `stage_status.*.output_hash`;
- per-candidate validation/refinement counters.

---


## Business Mapping

Maps `../TARGET_ORCHESTRATION_LOGIC.md` section 5 to candidate generation, scoring, validation/refinement and final `approved_texts` selection.
