# Seed Prompt Golden Coverage

Статус: актуализированный Release 2 detail document для `SEED_PROMPT_INVENTORY.md`.

Этот документ maps golden scenarios to seed prompt layers and acceptance invariants.

## 1. Golden Scenario Coverage Matrix

| Scenario | Required normalized params | Required layers | Fallback/freeform | Key checks |
| --- | --- | --- | --- | --- |
| Правдивые истории про ёжика зимой для 3 лет | `story`, `TRUTH`, `NARRATIVE`, age `3`, subject hedgehog, setting winter/forest | `CONTENT_FORMAT_STORY`, `TRUTH_BASE`, `UTILITY_NARRATIVE_BASE`, `AGE_3`, `LANGUAGE_RU_AUDIENCE`, `LANGUAGE_RU_RESULT`, `NATURALISTIC_ANIMAL_STORY`, `TRUTH_ANIMAL_HEDGEHOG` | `winter`, `forest` can stay hard/context details | no fairy-tale behavior; no duplicate themes; hedgehog remains main subject |
| Сказочные истории про лису для 5 лет | `story`, `FAIRY_TALE`, `NARRATIVE`, age `5`, subject fox | `CONTENT_FORMAT_STORY`, `FAIRY_TALE_BASE`, `UTILITY_NARRATIVE_BASE`, `AGE_5`, `LANGUAGE_RU_AUDIENCE`, `LANGUAGE_RU_RESULT`, `RUSSIAN_FOLK_TALE`, `FAIRY_TALE_ANIMAL_FOX` | none expected | fairy-tale behavior allowed; age 5 complexity |
| Поучительная правдивая история про мытьё рук после прогулки | `story`, `TRUTH`, `TEACHING`, topic handwashing, explicit/default age | `CONTENT_FORMAT_STORY`, `TRUTH_BASE`, `UTILITY_TEACHING_BASE`, `UTILITY_TOPIC_HAND_WASHING_AFTER_WALK`, `AGE_3` or `AGE_5`, `LANGUAGE_RU_AUDIENCE`, `LANGUAGE_RU_RESULT`, `ENTITY_SOAP`, `ENTITY_HANDS`, optionally `ENTITY_CHILD` / `ENTITY_CARING_ADULT` | walk context can be hard detail | `utility_goal` critical; hygiene advice correct |
| Поучительная сказка про переход через дорогу | `story`, `FAIRY_TALE`, `TEACHING`, topic road safety | `CONTENT_FORMAT_STORY`, `FAIRY_TALE_BASE`, `UTILITY_TEACHING_BASE`, `UTILITY_TOPIC_ROAD_SAFETY`, `AGE_3` or `AGE_5`, `LANGUAGE_RU_AUDIENCE`, `LANGUAGE_RU_RESULT`, `ENTITY_ROAD`, `ENTITY_TRAFFIC_LIGHT` | crossing context can be hard detail | fairy-tale style cannot make unsafe road advice acceptable |
| Поучительная история про незнакомца и конфету | `story`, explicitly configured truth/fairy-tale mode, `TEACHING`, topic stranger/candy | `CONTENT_FORMAT_STORY`, `TRUTH_BASE` or `FAIRY_TALE_BASE`, `UTILITY_TEACHING_BASE`, `UTILITY_TOPIC_STRANGERS_AND_CANDY`, `AGE_3` or `AGE_5`, `LANGUAGE_RU_AUDIENCE`, `LANGUAGE_RU_RESULT`, `ENTITY_STRANGER`, `ENTITY_CANDY`, `ENTITY_CARING_ADULT`, `ENTITY_CHILD` | none expected | no fearmongering; no unsafe advice; caring adult resolution |
| Попугай какаду | `story`, likely `TRUTH`, subject parrot with cockatoo detail | `CONTENT_FORMAT_STORY`, `TRUTH_BASE`, `AGE_3` or `AGE_5`, `LANGUAGE_RU_AUDIENCE`, `LANGUAGE_RU_RESULT`, `TRUTH_ANIMAL_PARROT` | fallback `какаду -> PARROT`; unresolved detail `какаду` | preview must not promise exact cockatoo layer |
| Лиса, заяц и белка зимой | multiple subjects, continuity policy explicit | `CONTENT_FORMAT_STORY`, `TRUTH_BASE` or `FAIRY_TALE_BASE`, `AGE_3` or `AGE_5`, `LANGUAGE_RU_AUDIENCE`, `LANGUAGE_RU_RESULT`, `TRUTH_ANIMAL_FOX` or `FAIRY_TALE_ANIMAL_FOX`, `TRUTH_ANIMAL_HARE` or `FAIRY_TALE_ANIMAL_HARE`, `TRUTH_ANIMAL_SQUIRREL` or `FAIRY_TALE_ANIMAL_SQUIRREL` | winter can be hard/context detail | required subjects do not disappear; policy preserved |
| Маленький бельчонок Тим | `is_character = true`, squirrel base species, character profile | `CONTENT_FORMAT_STORY`, `TRUTH_BASE` or `FAIRY_TALE_BASE`, `AGE_3` or `AGE_5`, `LANGUAGE_RU_AUDIENCE`, `LANGUAGE_RU_RESULT`, `TRUTH_ANIMAL_SQUIRREL` or `FAIRY_TALE_ANIMAL_SQUIRREL` | name/traits in `character_profile` and hard details, not a Tim-specific prompt file | refiner cannot change Tim or character traits |

## 2. Provocative Scenario Checks

Provocative scenarios must be covered by validator/refiner/stage requirements:

- unsupported style as soft preference -> preserve as soft preference or unresolved detail;
- unsupported style as hard requirement -> clarification or stop;
- `TRUTH` + fantastic hard detail -> clarification or validation failure;
- empty/meta input -> Stage 1 clarification/stop, no Stage 2 prompts needed;
- subject disappears -> subject continuity hard gate failure;
- refiner changes theme/profile -> validation/refiner invariant failure;
- stranger/candy becomes scary or unsafe -> safety/utility hard gate failure;
- `TRUTH` animal talks like a person -> truth fit failure.
