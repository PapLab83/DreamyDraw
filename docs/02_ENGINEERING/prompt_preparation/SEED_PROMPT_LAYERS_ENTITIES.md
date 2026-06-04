# Seed Prompt Entity Layers

Статус: временный detail document для `SEED_PROMPT_INVENTORY.md`.

Этот документ описывает entity layers, fallback entities и character profile requirements.

## 1. Entity Layers

Canonical base follows `SEED_SCOPE.md`. Extra entities below are required by `GOLDEN_SCENARIOS.md` or seed utility topics.

| id | type | role | namespace | Purpose |
| --- | --- | --- | --- | --- |
| `TRUTH_ANIMAL_HEDGEHOG` | `entity` | not required | `truth_modes/TRUTH/characters/animals` | Realistic hedgehog facts and constraints. |
| `FAIRY_TALE_ANIMAL_HEDGEHOG` | `entity` | not required | `truth_modes/FAIRY_TALE/characters/animals` | Hedgehog as fairy-tale character when needed. |
| `TRUTH_ANIMAL_FOX` | `entity` | not required | `truth_modes/TRUTH/characters/animals` | Realistic fox facts and constraints. |
| `FAIRY_TALE_ANIMAL_FOX` | `entity` | not required | `truth_modes/FAIRY_TALE/characters/animals` | Fox as fairy-tale character. |
| `TRUTH_ANIMAL_SQUIRREL` | `entity` | not required | `truth_modes/TRUTH/characters/animals` | Realistic squirrel facts and fallback for squirrel child character. |
| `FAIRY_TALE_ANIMAL_SQUIRREL` | `entity` | not required | `truth_modes/FAIRY_TALE/characters/animals` | Squirrel as fairy-tale character. |
| `TRUTH_ANIMAL_HARE` | `entity` | not required | `truth_modes/TRUTH/characters/animals` | Hare for multi-subject winter scenario. |
| `FAIRY_TALE_ANIMAL_HARE` | `entity` | not required | `truth_modes/FAIRY_TALE/characters/animals` | Hare as fairy-tale character. |
| `TRUTH_ANIMAL_PARROT` | `entity` | not required | `truth_modes/TRUTH/characters/animals` | Parrot fallback for cockatoo. |
| `ENTITY_CHILD` | `entity` | not required | `entities/people` | Child role for teaching stories. |
| `ENTITY_DOCTOR` | `entity` | not required | `entities/people/professions` | Doctor/profession seed subject. |
| `ENTITY_STRANGER` | `entity` | not required | `entities/people/safety_roles` | Stranger role for stranger/candy safety. |
| `ENTITY_CARING_ADULT` | `entity` | not required | `entities/people/safety_roles` | Parent/caring adult safe-resolution role. |
| `ENTITY_SOAP` | `entity` | not required | `entities/objects/hygiene` | Soap for handwashing. |
| `ENTITY_HANDS` | `entity` | not required | `entities/objects/hygiene` | Hands for handwashing wording. |
| `ENTITY_ROAD` | `entity` | not required | `entities/environment/safety` | Road for road safety. |
| `ENTITY_TRAFFIC_LIGHT` | `entity` | not required | `entities/objects/safety` | Traffic light for road safety. |
| `ENTITY_CANDY` | `entity` | not required | `entities/objects/safety` | Candy object for stranger/candy safety. |

Required fallback:

```text
requested: cockatoo / какаду
fallback_layer_id: TRUTH_ANIMAL_PARROT
unresolved_detail: какаду
```

Entity bodies must define:

- aliases;
- factual constraints;
- truth-mode applicability;
- whether the entity can be a character;
- whether the entity is animal, human role, profession, object, environment subject or safety object;
- whether it can be required subject, context subject or utility support subject.

For real animal layers:

- `TRUTH` animal layers must prohibit human speech and human-like decision-making;
- `FAIRY_TALE` animal layers may allow speech/personality within age and safety constraints.

## 2. Character Profile Requirements

Character profile coverage is a normalized-state and continuity requirement, not a requirement to create a Tim-specific prompt file.

For the seed scope, `маленький бельчонок Тим` must be represented by:

- `subjects[].base_species = squirrel`;
- lookup to `TRUTH_ANIMAL_SQUIRREL` or `FAIRY_TALE_ANIMAL_SQUIRREL`;
- `is_character = true`;
- `character_profile.name = Тим`;
- stable traits and hard details stored in `character_profile` / `hard_details`.

Reusable profile layers are optional and may be created only if useful for continuity smoke tests:

| id | type | role | namespace | Purpose |
| --- | --- | --- | --- | --- |
| `CHARACTER_PROFILE_ANIMAL_FRIEND` | `entity` | not required | `character_profiles/reusable` | Optional reusable animal friend profile for continuity smoke. |
| `CHARACTER_PROFILE_CARING_ADULT` | `entity` | not required | `character_profiles/reusable` | Optional caring adult profile for teaching/safety continuity. |

Important: `маленький бельчонок Тим` must not require a dedicated prompt file or species layer. Lookup uses `TRUTH_ANIMAL_SQUIRREL` or `FAIRY_TALE_ANIMAL_SQUIRREL`; the name and traits belong in `character_profile`, `hard_details` and subject continuity data.

Profile body must define:

- stable identity;
- allowed aliases;
- role in story;
- stable traits and stable details;
- immutable fields for validator/refiner;
- relation to `main_subject`, `subjects[].id`, `used_subjects` and `subject_continuity_policy`.
