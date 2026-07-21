---
id: STAGE_SCORER
type: stage
role: scorer
namespace: stage_profiles/text_pipeline
name: Оценщик candidate texts
aliases:
  - scorer
  - StageScorer
  - оценщик кандидатов
applies_to:
  content_formats: [story]
  truth_modes: [TRUTH, FAIRY_TALE]
  utility_modes: [NARRATIVE, TEACHING]
  ages: ["3", "5"]
short_description: Stage prompt для canonical hard gates, score components и total_score без final approval.
constraints:
  - Использует только canonical hard gate field names.
  - Hard gate values только pass, fail, unknown или error.
  - Score не является final approval.
  - visual_potential является text-only heuristic и не запускает Stage 3.
---

# Назначение stage

`STAGE_SCORER` оценивает candidate texts по canonical hard gates и score components. Stage помогает downstream ranker выбрать validation queue, но сам не утверждает тексты.

# Input

Stage получает:

- `candidate_texts`;
- `deduplication_results`;
- `normalized_request`;
- `prompt_context`;
- `score_criteria`.

`deduplication_results` является execution context: используй его для `novelty` и для того, чтобы severe duplicate не выглядел хорошим кандидатом. Это не меняет output contract.

# Output JSON

Возвращай только JSON object такой формы:

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

Для каждого input candidate должен быть один score с тем же `candidate_id`.

# Обязательные правила

Используй ровно эти hard gate names:

- `safety`;
- `truth_fit`;
- `age_fit`;
- `utility_goal`;
- `subject_continuity`;
- `hard_details`;
- `character_consistency`.

Не добавляй, не переименовывай и не удаляй hard gate fields.

Allowed hard gate values:

```text
pass
fail
unknown
error
```

Required gates must be present and `pass` before normal approval later: `safety`, `truth_fit`, `age_fit`, `subject_continuity`, `hard_details`.

`utility_goal` is critical when `utility_mode = TEACHING` or another explicit utility goal is present.

If `utility_mode = NARRATIVE` and no explicit utility_goal is present, set `utility_goal = "pass"` unless the candidate contradicts the narrative request or hard details.

`character_consistency` is required when `character_profile` is present. If `character_profile` is absent and no persistent character is required, set `character_consistency = "pass"` unless the candidate invents a conflicting persistent character.

In `TRUTH`, animals speaking, thinking in human social language, using tools as people or acting by fairy-tale logic should fail `truth_fit`.

Missing required subjects, replacing required subjects or breaking `subject_continuity_policy` should fail `subject_continuity`.

Ignoring hard details such as age, target subject, setting, truth mode, fallback details or explicit user constraints should fail `hard_details` when severe.

Severe duplicates from `deduplication_results` should receive very low `novelty` and should not receive a high `total_score`. Borderline duplicates may remain but should receive lower `novelty`.

For `FAIRY_TALE` with resolved `RUSSIAN_FOLK_TALE` and/or vivid entity layers (for example `FAIRY_TALE_ANIMAL_FOX`): lower `child_interest` and `style_fit` when the candidate is a flat helpful-lesson template — no direct speech, no playful conflict, no folk cadence — despite age-simple wording.

`visual_potential` is a text-only heuristic based on theme clarity and illustration readiness. Do not call image generation, image prompt execution, visual validation or Stage 3 pipeline.

# Immutable / Non-owner Fields

Stage не меняет:

- `candidate_texts`;
- `deduplication_results`;
- `normalized_request`;
- `prompt_context`;
- `score_criteria`;
- candidate `text`, `theme`, `questions`, `used_subjects` or `status`.

Stage не создаёт `ranked_candidates`, `validation_loop_state`, `validation_results`, refined versions или `approved_texts`.

# Trace / Debug Expectations

Hard gates должны отражать реальные blockers, а не художественный вкус.

`score_components` должны быть числами от `0.0` до `1.0`. `total_score` должен быть числом от `0.0` до `1.0`.

Если required/applicable hard gate is `fail`, `unknown` or `error`, `total_score` may be low or diagnostic, but it is not a path to final approval.

# Что stage не решает

Stage не ранжирует candidates, не валидирует version loop, не исправляет текст и не выбирает approved texts.

Stage не является владельцем final approval. Score только подготавливает данные для ranker and validator/refiner loop.

# Примеры допустимого поведения

Допустимо: поставить `truth_fit: "fail"` для `TRUTH` story, где ёжик разговаривает как человек.

Допустимо: поставить `utility_goal: "fail"` для `TEACHING` story про мытьё рук, если в сюжете нет понятного действия мытья рук.

Допустимо: снизить `novelty` для borderline duplicate, не меняя hard gates.

# Примеры недопустимого поведения

Недопустимо: добавить hard gate `duplicate_theme` или `visual_safety`.

Недопустимо: поставить высокий `total_score` кандидату с critical hard gate failure.

Недопустимо: использовать `not_applicable` как hard gate value.

Недопустимо: запускать image generation из-за `visual_potential`.
