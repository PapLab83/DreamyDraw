# Seed Prompt Core Layers

Статус: актуализированный Release 2 detail document для `SEED_PROMPT_INVENTORY.md`.

Этот документ описывает content format, truth mode, style/substyle, utility, age и language layers.

## 1. Content Format

| id | type | role | namespace | Purpose |
| --- | --- | --- | --- | --- |
| `CONTENT_FORMAT_STORY` | `format` | `content_format` | `content_formats/story` | Base contract for short child-facing stories with questions. |

Required aliases:

- `story`;
- `stories`;
- `рассказ`;
- `рассказы`;
- `история`;
- `истории`;
- `сказка`, only as a format hint unless truth mode also resolves to `FAIRY_TALE`.

Required `applies_to`:

- `content_formats: [story]`;
- `truth_modes: [TRUTH, FAIRY_TALE]`;
- `utility_modes: [NARRATIVE, TEACHING]`;
- `ages: ["3", "5"]`.

Body must define:

- expected candidate fields: `theme`, `text`, `questions`, `used_subjects`, `utility_points`, `expected_visual_idea`;
- story length and structure guidance for age layers to refine;
- requirement that questions remain age-appropriate;
- prohibition on deciding truth mode or utility mode.

## 2. Truth Modes

| id | type | role | namespace | Purpose |
| --- | --- | --- | --- | --- |
| `TRUTH_BASE` | `truth_mode` | not required | `truth_modes/TRUTH` | Realistic/factual world rules. |
| `FAIRY_TALE_BASE` | `truth_mode` | not required | `truth_modes/FAIRY_TALE` | Fairy-tale world rules. |

Base style mapping:

- `TRUTH -> NATURALISTIC_ANIMAL_STORY` or base factual style;
- `FAIRY_TALE -> RUSSIAN_FOLK_TALE` or `CHUKOVSKY_STYLE`.

Required aliases:

- `TRUTH_BASE`: `правдиво`, `реалистично`, `натуралистично`, `как в жизни`, `без сказки`;
- `FAIRY_TALE_BASE`: `сказка`, `сказочно`, `волшебно`, `как сказку`;

Body must define:

- ontology constraints: what can be real, fictional or symbolic;
- allowed/prohibited animal speech and human-like agency;
- how to treat soft preferences like "волшебная атмосфера" in `TRUTH`;
- validator/refiner checks for mode violations.

## 3. Style And Substyle

| id | type | role | namespace | Purpose |
| --- | --- | --- | --- | --- |
| `NATURALISTIC_ANIMAL_STORY` | `substyle` | not required | `truth_modes/TRUTH/styles/naturalistic` | Calm realistic animal storytelling. |
| `RUSSIAN_FOLK_TALE` | `substyle` | not required | `truth_modes/FAIRY_TALE/styles/folklore` | Russian folk-tale cadence and imagery. |
| `CHUKOVSKY_STYLE` | `substyle` | not required | `truth_modes/FAIRY_TALE/styles/reference_labels` | MVP lookup/reference label for playful rhythmic children's style. |

Required aliases:

- `NATURALISTIC_ANIMAL_STORY`: `натуралистично`, `реалистичная история про животных`, `как про настоящих животных`;
- `RUSSIAN_FOLK_TALE`: `русская народная`, `народная сказка`, `в русском народном стиле`;
- `CHUKOVSKY_STYLE`: `в стиле Чуковского`, `как у Чуковского`, `чуковский`;

`CHUKOVSKY_STYLE` requirements:

- may use Chukovsky only as explicit MVP lookup/reference label;
- body must phrase the style as a transformation brief: детская абсурдность, ритмичность, звукопись, динамика;
- do not copy specific texts, characters, unique passages or signature plot situations.

All style bodies must state:

- style cannot override `truth_mode`, `utility_mode`, `utility_topic`, required subjects, hard details or `character_profile`;
- style fit can be scored, but hard gates win over style.

## 4. Utility Modes

| id | type | role | namespace | Purpose |
| --- | --- | --- | --- | --- |
| `UTILITY_NARRATIVE_BASE` | `utility` | `utility_mode` | `utility_modes/NARRATIVE` | General story value without explicit teaching goal. |
| `UTILITY_TEACHING_BASE` | `utility` | `utility_mode` | `utility_modes/TEACHING` | Story with explicit child-safe teaching goal. |

Required aliases:

- `UTILITY_NARRATIVE_BASE`: `просто историю`, `без поучения`, `на ночь`, `интересную историю`;
- `UTILITY_TEACHING_BASE`: `поучительную`, `научи`, `объясни ребёнку`, `чтобы понял`.

Body must define:

- when `utility_goal` is a hard gate;
- that `TEACHING` must not become moralizing, frightening or unsafe;
- interaction with utility topics and age wording.

## 5. Utility Topics

| id | type | role | namespace | Purpose |
| --- | --- | --- | --- | --- |
| `UTILITY_TOPIC_HAND_WASHING_AFTER_WALK` | `utility` | `utility_topic` | `utility_modes/TEACHING/topics/hygiene` | Handwashing/hygiene after walking. |
| `UTILITY_TOPIC_ROAD_SAFETY` | `utility` | `utility_topic` | `utility_modes/TEACHING/topics/safety` | Safe road crossing. |
| `UTILITY_TOPIC_STRANGERS_AND_CANDY` | `utility` | `utility_topic` | `utility_modes/TEACHING/topics/safety` | Stranger/candy safety. |

Required aliases:

- handwashing: `мыть руки`, `после прогулки`, `гигиена`, `мыло`;
- road safety: `переходить дорогу`, `светофор`, `дорога`, `пешеходный переход`;
- strangers/candy: `незнакомец`, `конфета`, `не брать конфеты`, `чужой взрослый`.

Sensitive topic requirements:

- `STRANGERS_AND_CANDY` must include `safety_notes`;
- wording must avoid panic, threats or graphic danger;
- preferred resolution: pause, do not take the candy, go to a familiar caring adult;
- validator must treat unsafe advice as critical `utility_goal` or `safety` failure.

## 6. Age Layers

| id | type | role | namespace | Purpose |
| --- | --- | --- | --- | --- |
| `AGE_3` | `age` | not required | `ages/3` | Story and question complexity for age 3. |
| `AGE_5` | `age` | not required | `ages/5` | Story and question complexity for age 5. |

Required aliases:

- `AGE_3`: `3 года`, `трёх лет`, `для малыша 3 лет`;
- `AGE_5`: `5 лет`, `пяти лет`, `для ребёнка 5 лет`.

Body must define:

- vocabulary level;
- sentence length;
- causal complexity;
- acceptable question complexity;
- safety wording differences by age.

## 7. Language Layers

| id | type | role | namespace | Purpose |
| --- | --- | --- | --- | --- |
| `LANGUAGE_RU_AUDIENCE` | `language` | `audience_language` | `languages/ru/audience` | User-facing and child-facing Russian wording constraints. |
| `LANGUAGE_RU_RESULT` | `language` | `result_language` | `languages/ru/result` | Final generated text language. |

Inventory decision:

- use separate files for audience/result roles in the seed set;
- if implementation later supports shared physical file, execution traces must still preserve both roles.

Required aliases:

- `русский`;
- `на русском`;
- `ru`;
- `Russian`.

Body must define:

- final output language rules;
- whether questions and story text are both in Russian;
- no accidental English in child-facing result unless explicitly requested by a future scope.
