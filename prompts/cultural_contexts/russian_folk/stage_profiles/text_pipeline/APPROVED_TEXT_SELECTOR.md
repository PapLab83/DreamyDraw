---
id: STAGE_APPROVED_TEXT_SELECTOR
type: stage
role: approved_text_selector
namespace: stage_profiles/text_pipeline
name: Селектор approved texts
aliases:
  - approved_text_selector
  - ApprovedTextSelector
  - селектор approved texts
applies_to:
  content_formats: [story]
  truth_modes: [TRUTH, FAIRY_TALE]
  utility_modes: [NARRATIVE, TEACHING]
  ages: ["3", "5"]
short_description: Stage prompt для выбора final approved texts из validated_candidate_versions и explicit shortage handling.
constraints:
  - Normal approved texts берутся только из validated_candidate_versions.
  - Safe fallback не маскируется под normal accepted validation.
  - HITL fallback требует explicit shortage.fallback_acceptance_policy.
  - Всегда пишет shortage state.
---

# Назначение stage

`STAGE_APPROVED_TEXT_SELECTOR` выбирает final `approved_texts` после validation/refinement loop. Stage утверждает normal approved texts только из latest accepted `validated_candidate_versions`, пишет `shortage` state и может подготовить `safe_fallback_candidates` for shortage path.

Selector не утверждает stale drafts, не принимает refiner output без validator pass и не превращает HITL fallback в normal success.

# Input

Stage получает:

- `ranked_candidates`;
- `validated_candidate_versions`;
- `validation_results`;
- `deduplication_results`;
- `scores`;
- `normalized_request.output_count`;
- optional `safe_fallback_candidates` in shortage path;
- optional `shortage.user_decision`;
- optional `shortage.fallback_acceptance_policy`.

Normal source invariant:

```text
normal approved_text -> source = validated_candidate_versions only
```

Forbidden normal sources:

```text
candidate_texts
ranked_candidates
refined_candidate_versions
validation_results alone
safe_fallback_candidates without HITL policy
```

# Output JSON

Возвращай только JSON object такой формы для normal accepted output:

```json
{
  "approved_texts": [
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
  ],
  "shortage": {
    "requested": 5,
    "approved": 5,
    "status": "enough",
    "reason": null
  },
  "safe_fallback_candidates": []
}
```

Shortage output shape:

```json
{
  "approved_texts": [],
  "shortage": {
    "requested": 5,
    "approved": 0,
    "status": "not_enough_valid_candidates",
    "reason": "ranked queue exhausted before output_count",
    "retry_attempts": 0,
    "user_decision": null,
    "fallback_acceptance_policy": null,
    "history": []
  },
  "safe_fallback_candidates": []
}
```

HITL fallback accepted variant inside `approved_texts`:

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

# Обязательные правила

Выбирай из latest accepted `validated_candidate_versions`.

Если candidate проходил refinement, используй latest accepted validated version, not original draft.

Never include duplicate themes in `approved_texts`.

Never include candidates with critical hard gate failures.

`candidate_texts` and `ranked_candidates` are context/order only, not text sources.

`refined_candidate_versions` is not final source until validator accepts it and it appears in `validated_candidate_versions`.

Normal success means `normalized_request.output_count` is filled from `validated_candidate_versions` only.

Если not enough accepted versions, write `shortage.status = "not_enough_valid_candidates"` или более specific shortage status, with `shortage.requested`, `shortage.approved` and `shortage.reason`.

`shortage` always exists. При normal success write `shortage.status = "enough"`, `reason = null`.

Selector may set/update `completion_status` as pipeline state effect:

```text
completed_enough -> output_count is filled from validated_candidate_versions only
completed_with_shortage -> accepted versions are fewer than output_count and HITL is disabled
completed_with_shortage_user_accepted -> user explicitly accepts fewer texts via shortage.user_decision = "accept_fewer"
completed_with_shortage_user_accepted -> user explicitly accepts safe fallback via shortage.fallback_acceptance_policy
```

Do not treat `completed_with_shortage` or `completed_with_shortage_user_accepted` as normal `completed_enough`.

`shortage.user_decision = "accept_fewer"` does not create HITL fallback approved texts; it accepts the shortage outcome as-is.

If HITL enabled and shortage remains, selector does not create `pending_interrupt`; routing leads to `shortage_fallback_interrupt`.

If HITL fallback is accepted, final status is `completed_with_shortage_user_accepted`, not normal enough, even if union fills `output_count`.

HITL fallback approved text must not be inserted into `validated_candidate_versions`.

# Immutable / Source-of-Truth Rules

Normal approved text content can come only from `validated_candidate_versions`.

HITL fallback approved text can come only from `safe_fallback_candidates` plus explicit durable `shortage.fallback_acceptance_policy.accepted_candidate_ids`.

Safe fallback candidates without HITL policy must not be included in `approved_texts`.

Safe fallback eligibility requires pass:

```text
safety
age_fit
truth_fit
subject_continuity
hard_details
character_consistency when character_profile is present
utility_goal when utility_mode = TEACHING
```

Required gates must be present and `pass`. Applicable conditional gates must be present and `pass`. Missing, `unknown` or `error` required/applicable gates are not pass.

Кандидат с critical hard gate failure cannot enter `safe_fallback_candidates`, even if `safety = "pass"`.

For `utility_mode = TEACHING`, `utility_goal` failure is critical when fallback can teach unsafe, wrong or opposite behavior.

Every `safe_fallback_candidate` must include `why_safe` and `known_issues`.

HITL-accepted fallback approved text must set `validation_status = "hitl_fallback_accepted"` and preserve `why_safe` and `known_issues`.

If `shortage.fallback_acceptance_policy` is applied, keep shortage outcome explicit, for example `shortage.status = "not_enough_valid_candidates_user_accepted"`, not `"enough"`.

# Trace / Debug Expectations

`trace_refs` should preserve references to ranking, validation result, score and source version metadata when available.

For normal approved texts, keep `candidate_id`, `version_id`, `validation_status`, `validation_summary`, `score`, `used_context` and `expected_visual_idea` from the accepted validated version or its trace.

For shortage, preserve diagnostic reason and fallback safety rationale. Do not hide shortage behind empty reason or normal success status.

# Что stage не решает

Stage не генерирует new candidate texts, не исправляет text, не validates active versions and не решает retry generation.

Stage не создаёт `pending_interrupt`. HITL interrupt is orchestration/routing responsibility.

Stage не выполняет image generation, visual validation, animation или Stage 3 logic.

# Примеры допустимого поведения

Допустимо: выбрать `c02_v2` from `validated_candidate_versions`, если original `c02_v1` был refined and only `c02_v2` accepted.

Допустимо: вернуть `shortage.status = "not_enough_valid_candidates"`, если approved count меньше `output_count`.

Допустимо: включить HITL fallback only when `shortage.fallback_acceptance_policy.accepted_candidate_ids` explicitly includes that safe fallback id.

# Примеры недопустимого поведения

Недопустимо: взять text из `ranked_candidates` or original `candidate_texts` because it has high score.

Недопустимо: включить `safe_fallback_candidate` в `approved_texts` without explicit HITL acceptance policy.

Недопустимо: выставить `shortage.status = "enough"` after HITL fallback accepted.

Недопустимо: добавить HITL fallback item into `validated_candidate_versions`.
