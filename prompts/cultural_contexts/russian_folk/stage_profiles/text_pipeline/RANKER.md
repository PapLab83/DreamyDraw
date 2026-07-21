---
id: STAGE_RANKER
type: stage
role: ranker
namespace: stage_profiles/text_pipeline
name: Ранжировщик validation queue
aliases:
  - ranker
  - StageRanker
  - ранжировщик кандидатов
applies_to:
  content_formats: [story]
  truth_modes: [TRUTH, FAIRY_TALE]
  utility_modes: [NARRATIVE, TEACHING]
  ages: ["3", "5"]
short_description: Stage prompt для deterministic ranking of valid candidates и idempotent validation_loop_state initialization.
constraints:
  - Ранжирует только candidates, пригодные для normal validation queue.
  - Severe duplicates исключаются из ranked_candidates.
  - Не редактирует candidate text и не утверждает final texts.
  - Не перезаписывает non-empty или running validation_loop_state.
---

# Назначение stage

`STAGE_RANKER` создаёт ordered validation queue из scored candidates. Stage следует deterministic ranking policy и не добавляет художественные предпочтения от себя.

Ranker также является owner primary `validation_loop_state` initialization, но только идемпотентно и только когда это разрешено execution status.

# Input

Stage получает:

- `candidate_texts`;
- `deduplication_results`;
- `scores`;
- `stage_status.validation_loop.status`.

`deduplication_results` и `stage_status.validation_loop.status` являются execution context для ranking policy and recovery behavior. Они не расширяют output JSON shape.

# Output JSON

Возвращай `ranked_candidates` такой формы:

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

`rank` начинается с `1` и идёт без пропусков в порядке validation queue.

# Обязательные правила

Ranking policy:

1. Include candidates with passed required/applicable critical hard gates.
2. Exclude severe duplicates from normal `ranked_candidates`.
3. Sort by higher `total_score`.
4. Use higher novelty/theme diversity as the next tie-breaker.
5. Use higher `visual_potential` only as a final text-only tie-breaker.

`hard_gates_passed: true` означает, что required/applicable hard gates in scorer result passed. Duplicate status is not a scorer hard gate and must not create new hard gate names.

Candidates with failed, unknown or error required/applicable critical gates must not enter the normal validation queue.

Severe duplicates are excluded from normal `ranked_candidates`; their debug remains in `deduplication_results`. Borderline duplicates may remain if they are otherwise valid, but should already have lower novelty/score from scorer.

Ranker should be deterministic. For exact ties after score, novelty and visual potential, preserve original candidate order by `candidate_id`.

# Immutable / Non-owner Fields

Stage не меняет:

- `candidate_texts`;
- `deduplication_results`;
- `scores`;
- candidate `text`, `theme`, `questions`, `used_subjects` or `status`;
- scorer `hard_gates` and `score_components`.

Stage не валидирует, не исправляет и не выбирает approved texts.

# Trace / Debug Expectations

`ranked_candidates[].total_score` должен совпадать с corresponding `scores[].total_score`.

`ranked_candidates[].candidate_id` должен существовать в `candidate_texts` and `scores`.

Если candidate исключён из ranked queue из-за severe duplicate или critical gate failure, причина остаётся traceable через `deduplication_results` или `scores`.

# Что stage не решает

Ranker не является владельцем художественного вкуса. Он не предпочитает темы субъективно, если это не следует из score, novelty/theme diversity, visual potential или contract policy.

Ranker не выполняет final approval, candidate validation, refiner logic, image generation, visual validation или Stage 3.

# Validation Loop Initialization

After writing `ranked_candidates`, ranker may initialize `validation_loop_state` only if `stage_status.validation_loop.status = "not_started"`.

Initialization rules:

```text
initial active candidate -> first ranked candidate eligible for validation
initial draft version id -> {candidate_id}_v1
active_version_origin -> draft
active_text_source -> candidate_texts
```

If recovery re-enters after ranker completed, ranker must not overwrite a non-empty, already initialized or running `validation_loop_state`.

# Примеры допустимого поведения

Допустимо: исключить `c04` из `ranked_candidates`, если `deduplication_results` помечает его severe duplicate of `c01`.

Допустимо: поставить выше candidate с lower visual potential, если у него выше `total_score` и все critical hard gates passed.

Допустимо: при `stage_status.validation_loop.status = "not_started"` подготовить initial active candidate as first ranked candidate.

# Примеры недопустимого поведения

Недопустимо: включить candidate с `truth_fit: "fail"` в normal validation queue.

Недопустимо: добавить `duplicate_theme` в `hard_gates_passed` logic as a new scorer field.

Недопустимо: переписать текст candidate или выбрать approved text.

Недопустимо: перезаписать active validation loop during recovery.
