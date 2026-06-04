# Seed Prompt Stage Layers

Статус: временный detail document для `SEED_PROMPT_INVENTORY.md`.

Этот документ описывает Stage 2 prompt layers. Stage prompt briefs must be stricter than artistic/content layer briefs.

## 1. Stage Prompt Layers

| id | type | role | namespace | Purpose |
| --- | --- | --- | --- | --- |
| `STAGE_CANDIDATE_TEXT_GENERATOR` | `stage` | `candidate_text_generator` | `stage_profiles/text_pipeline` | Generate candidate pool. |
| `STAGE_TOPIC_DEDUPLICATOR` | `stage` | `topic_deduplicator` | `stage_profiles/text_pipeline` | Detect duplicate themes. |
| `STAGE_SCORER` | `stage` | `scorer` | `stage_profiles/text_pipeline` | Apply hard gates and score components. |
| `STAGE_RANKER` | `stage` | `ranker` | `stage_profiles/text_pipeline` | Ranking policy summary, even if deterministic. |
| `VALIDATOR_CANDIDATE_TEXT` | `validator` | `candidate_validator` | `validators/text_pipeline` | Validate active candidate version. |
| `REFINER_CANDIDATE_TEXT` | `refiner` | `candidate_refiner` | `refiners/text_pipeline` | Repair candidate according to validator issues. |
| `STAGE_APPROVED_TEXT_SELECTOR` | `stage` | `approved_text_selector` | `stage_profiles/text_pipeline` | Select final approved texts and shortage output. |

All stage prompt bodies must include:

- exact input object names;
- output JSON shape;
- hard constraints;
- immutable fields;
- trace/debug expectations;
- what the stage must not decide.

## 2. Stage-Specific Notes

- Generator produces a pool, not final approved texts.
- Deduplicator marks duplicate themes and preserves debug reasons.
- Scorer must output canonical hard gates: `safety`, `truth_fit`, `age_fit`, `utility_goal`, `subject_continuity`, `hard_details`, `character_consistency`.
- Ranker may be deterministic; its prompt layer is a policy/reference layer, not permission to reorder by taste.
- Validator validates the active version from `validation_loop_state`, not stale drafts by `candidate_id`.
- Refiner must preserve theme, subjects, `character_profile`, `truth_mode`, `utility_mode`, `utility_topic`, `target_age` and hard details.
- Selector chooses from `validated_candidate_versions`; safe fallback candidates are not normal approved texts without explicit HITL fallback acceptance.

## 3. Required Boundaries

Stage prompts must not:

- decide graph routing;
- silently change `normalized_request`;
- approve refiner output without validator;
- select normal approved texts from drafts or ranked candidates;
- create Stage 3 image/animation behavior;
- invent new hard gate field names.
