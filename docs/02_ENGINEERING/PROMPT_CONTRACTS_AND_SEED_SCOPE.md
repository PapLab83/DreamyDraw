# PROMPT_CONTRACTS_AND_SEED_SCOPE.md

# Контракты prompt-базы и минимальный seed scope

Статус: рабочий draft.

Документ фиксирует первый связный контракт между логикой оркестрации, prompt-базой и вторым этапом генерации текстов. Он не заменяет `TARGET_ORCHESTRATION_LOGIC.md`, а уточняет, какие данные должны передаваться между этапами и как эти данные превращаются в prompt execution context.

Если отдельные разделы вырастут, документ можно разнести на самостоятельные файлы:

```text
docs/02_ENGINEERING/contracts/
  README.md
  NORMALIZED_STATE_CONTRACT.md
  PROMPT_FILE_CONTRACT.md
  PROMPT_LOOKUP_CONTRACT.md
  PROMPT_COMPOSITION_CONTRACT.md
  STAGE_CONTRACTS.md
  SEED_SCOPE_AND_GOLDEN_SCENARIOS.md
```

На текущем этапе удобнее держать контракты рядом, чтобы не потерять связи между параметрами, prompt lookup, prompt composition и stage-specific агентами.

---

## 1. Назначение документа

Документ отвечает на практические вопросы перед подготовкой seed prompts и реализацией нового контура:

* какие параметры должны выходить из первого этапа оркестрации;
* как описывать `.md` prompt layers;
* как система ищет подходящие prompt layers;
* что делать, если точного слоя нет;
* как из параметров и найденных слоёв собрать prompt context для конкретного этапа pipeline;
* какие входы и выходы должны быть у агентов второго этапа;
* какой минимальный набор prompt-файлов нужен для MVP-проверки;
* какие golden scenarios помогут отлаживать поведение без фиксации конкретного текста.

Документ находится между бизнес-логикой и технической реализацией:

* бизнес-логика говорит, что должно происходить;
* эти контракты говорят, какие данные и prompt assets нужны для этого;
* техническая спецификация позже решит, какие Pydantic-модели, ноды LangGraph и классы загрузки промптов это реализуют.

---

## 2. Normalized State Contract

### 2.1 Назначение

`normalized_request` — структурированный результат первого этапа оркестрации. Он должен быть достаточно полным, чтобы второй этап мог генерировать тексты без повторного выяснения базовых намерений пользователя.

Это не финальная Pydantic-схема, но логический контракт для будущей реализации.

### 2.2 Минимальные поля

```json
{
  "content_format": "story",
  "truth_mode": "TRUTH",
  "utility_mode": "NARRATIVE",
  "target_age": "3",
  "output_count": 5,
  "audience_language": "ru",
  "result_language": "ru",
  "main_subject": "ёжик",
  "subjects": [
    {
      "id": "hedgehog",
      "label": "ёжик",
      "type": "animal",
      "role": "main",
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
  "subject_continuity_policy": "same_main_subject_all_texts",
  "hard_details": [
    "главный персонаж — ёжик",
    "действие происходит зимой в лесу",
    "истории должны быть реалистичными"
  ],
  "soft_preferences": [
    "мягкий тон",
    "простые фразы"
  ],
  "user_context": null,
  "prompt_context": {
    "resolved_layers": [],
    "fallback_layers": [],
    "unresolved_details": []
  }
}
```

### 2.3 Поля первого этапа

| Поле | Смысл |
| --- | --- |
| `content_format` | Формат результата: на MVP основной формат `story`. |
| `truth_mode` | Режим отношения к реальности: `TRUTH`, `MYTH`, `FAIRY_TALE`. |
| `utility_mode` | Цель результата: `NARRATIVE`, `TEACHING`, позже `ENGLISH`. |
| `target_age` | Возрастной профиль: на MVP достаточно `3` и `5`. |
| `output_count` | Сколько итоговых approved texts нужно пользователю. |
| `audience_language` | Язык общения с пользователем. На старте `ru`. |
| `result_language` | Язык результата. На старте `ru`. |
| `main_subject` | Главное человеко-понятное обозначение темы или персонажа. |
| `subjects` | Структурированный список сущностей запроса. |
| `setting` | Место, сезон, время и другие обстоятельства. |
| `text_style_base` | Базовый тон текста. |
| `substyle` | Конкретный подстиль, если есть поддерживаемый слой. Может быть `null`. |
| `character_profile` | Профиль устойчивого персонажа, если он нужен. |
| `subject_continuity_policy` | Правило сохранения сущностей между текстами. |
| `hard_details` | Жёсткие требования пользователя. |
| `soft_preferences` | Мягкие пожелания пользователя. |
| `user_context` | Будущий минимальный контекст пользователя, если появится история. |
| `prompt_context` | Результат prompt lookup и candidate layer resolution. |

### 2.4 Subject and Character Contract

`subjects` фиксирует, о ком или о чём должен быть результат. Это не обязательно “персонажи” в художественном смысле.

Пример:

```json
{
  "main_subject": "лиса, заяц и белка",
  "subjects": [
    {"id": "fox", "label": "лиса", "type": "animal", "role": "main"},
    {"id": "hare", "label": "заяц", "type": "animal", "role": "main"},
    {"id": "squirrel", "label": "белка", "type": "animal", "role": "main"}
  ],
  "subject_continuity_policy": "distribute_subjects_across_texts"
}
```

`character_profile` появляется, если система интерпретирует тему как устойчивого героя.

Пример:

```json
{
  "main_subject": "маленький бельчонок",
  "subjects": [
    {"id": "squirrel_child", "label": "маленький бельчонок", "type": "animal_character", "role": "main"}
  ],
  "character_profile": {
    "name": null,
    "stable_traits": ["маленький", "любопытный"],
    "must_remain_same_character": true
  },
  "subject_continuity_policy": "same_character_all_texts"
}
```

Правила по умолчанию являются продуктовой политикой и могут меняться без переписывания всего контракта. Например, для запроса “Сделай 3 истории про лису, зайца и белку зимой” система может:

* распределить животных по разным историям;
* смешивать их в каждой истории;
* сделать одного главным, а остальных второстепенными.

Важно, чтобы выбранная политика была явно зафиксирована в `subject_continuity_policy` и не терялась на втором этапе.

---

## 3. Prompt File Contract

### 3.1 Общий формат `.md` prompt layer

Каждый prompt layer хранится в одном `.md` файле и состоит из двух частей:

1. YAML metadata block;
2. markdown prompt body.

Пример:

```markdown
---
id: TRUTH_ANIMAL_HEDGEHOG
type: entity
namespace: truth_modes/TRUTH/characters/animals
name: Ёжик
aliases:
  - ёж
  - ежик
  - hedgehog
applies_to:
  content_formats: [story]
  truth_modes: [TRUTH]
  utility_modes: [NARRATIVE, TEACHING]
  ages: ["3", "5"]
user_description: Реалистичные сведения о ёжике как животном для детских историй.
short_description: Ёжик, его поведение, среда обитания и безопасные факты для детей 3-5 лет.
constraints:
  - Не изображать ёжика домашним питомцем по умолчанию.
  - Не приписывать ёжику человеческую речь в режиме TRUTH.
good_for:
  - правдивые истории о животных
  - зимний лес
bad_for:
  - сказочный говорящий персонаж без переключения в FAIRY_TALE
fallback_priority: 80
---

# Prompt body

Используй этот слой, когда нужно писать о ёжике как о реальном животном...
```

### 3.2 Обязательные metadata-поля

| Поле | Смысл |
| --- | --- |
| `id` | Стабильный уникальный идентификатор слоя. |
| `type` | Тип слоя: `base`, `style`, `substyle`, `entity`, `utility`, `age`, `stage`, `validator`, `refiner`. |
| `namespace` | Логическое расположение слоя в prompt-базе. |
| `name` | Человеко-понятное имя. |
| `aliases` | Формулировки пользователя, которые могут указывать на этот слой. |
| `applies_to` | Ограничения применимости по формату, режиму, возрасту, utility. |
| `short_description` | Короткое описание для metadata lookup и preview. |
| `constraints` | Ограничения, которые слой добавляет в prompt context. |

### 3.3 Опциональные metadata-поля

| Поле | Смысл |
| --- | --- |
| `user_description` | Описание для пользовательских уточнений. |
| `good_for` | Когда слой особенно уместен. |
| `bad_for` | Когда слой нежелателен или конфликтует с режимом. |
| `fallback_priority` | Приоритет слоя как fallback-кандидата. |
| `requires_user_confirmation` | Нужно ли уточнять выбор у пользователя при совпадении. |
| `example_result_ids` | Ссылки на best-case examples для будущего UI. |
| `sample_text` | Короткий пример результата, если нужен для UX. |
| `safety_notes` | Особые ограничения безопасности. |

### 3.4 Типы prompt layers

| Тип | Пример | Назначение |
| --- | --- | --- |
| `format` | `content_formats/story/BASE.md` | Форма результата и общий output contract. |
| `truth_mode` | `truth_modes/TRUTH/BASE.md` | Правила мира: правда, миф, сказка. |
| `style` / `substyle` | `truth_modes/FAIRY_TALE/styles/folklore/RUSSIAN_FOLK.md` | Стиль или подстиль внутри режима. |
| `entity` | `truth_modes/TRUTH/characters/animals/FOX.md` | Сущность, объект, персонаж или явление. |
| `utility` | `utility/TEACHING/topics/ROAD_SAFETY.md` | Цель результата и обучающий слой. |
| `age` | `ages/3/BASE.md` | Возрастная сложность. |
| `language` | `languages/result/ru.md` | Язык результата. |
| `stage` | `stage_profiles/TEXT_GENERATION.md` | Инструкции конкретного этапа pipeline. |
| `validator` | `validators/TEXT_VALIDATOR.md` | Правила проверки. |
| `refiner` | `refiners/TEXT_REFINER.md` | Правила редактуры. |

---

## 4. Prompt Lookup Contract

### 4.1 Назначение

Prompt lookup превращает нормализованные параметры в набор resolved, fallback и unresolved prompt references.

Lookup использует metadata, а не полные prompt bodies. Полные bodies могут загружаться позже, stage-specific, когда конкретному агенту нужен prompt context.

### 4.2 Результат lookup

```json
{
  "resolved_layers": [
    {
      "layer_id": "CONTENT_FORMAT_STORY",
      "source": "content_formats/story/BASE.md",
      "reason": "content_format=story"
    },
    {
      "layer_id": "TRUTH_BASE",
      "source": "truth_modes/TRUTH/BASE.md",
      "reason": "truth_mode=TRUTH"
    }
  ],
  "fallback_layers": [
    {
      "requested": "какаду",
      "fallback_layer_id": "TRUTH_ANIMAL_PARROT",
      "source": "truth_modes/TRUTH/characters/animals/PARROT.md",
      "reason": "точного слоя COCKATOO нет, есть общий слой PARROT"
    }
  ],
  "unresolved_details": [
    {
      "label": "какаду",
      "type": "animal_detail",
      "instruction": "использовать общие знания модели, не обещая отдельный поддерживаемый слой"
    }
  ]
}
```

### 4.3 Порядок lookup

Базовый порядок:

1. Найти слой формата результата по `content_format`.
2. Найти базовый слой режима по `truth_mode`.
3. Найти utility-слой по `utility_mode`.
4. Найти возрастной слой по `target_age`.
5. Найти языковые слои по `audience_language` и `result_language`.
6. Найти style/substyle слои.
7. Найти entity/subject слои.
8. Найти stage profiles, validators и refiners, если они нужны для конкретного этапа.

Порядок не означает, что каждый слой “переписывает” предыдущий. Он фиксирует зависимость: старшие плоскости ограничивают применимость младших.

### 4.4 Exact match, aliases и fallback

Lookup должен использовать три уровня сопоставления:

1. **Exact match**
   Пользовательский или нормализованный параметр прямо соответствует `id` или `name`.

2. **Aliases**
   Формулировка пользователя совпадает с одним из `aliases`.

3. **Fallback**
   Точного слоя нет, но есть более общий или близкий слой.

Пример:

```text
Запрос: расскажи про попугая какаду

exact:
  TRUTH_ANIMAL_COCKATOO отсутствует

fallback:
  TRUTH_ANIMAL_PARROT найден

unresolved_detail:
  "какаду" сохраняется как уточнение, которое агент может раскрыть через общие знания модели
```

### 4.5 Когда нужно уточнение пользователя

Уточнение нужно, если:

* пользователь сформулировал неподдерживаемый слой как жёсткое требование;
* fallback существенно меняет смысл запроса;
* есть несколько близких fallback-кандидатов без очевидного лидера;
* слой конфликтует с `truth_mode`, возрастом или безопасностью;
* preview иначе будет обещать то, чего prompt-база не поддерживает.

Уточнение не обязательно, если:

* неподдерживаемая деталь является мягким пожеланием;
* есть безопасный базовый слой;
* fallback не меняет главное намерение пользователя;
* деталь можно сохранить в `unresolved_details` и честно передать в prompt context.

---

## 5. Prompt Composition Contract

### 5.1 Назначение

Prompt composition собирает stage-specific prompt context из:

* `normalized_request`;
* `resolved_layers`;
* `fallback_layers`;
* `unresolved_details`;
* `hard_details`;
* `soft_preferences`;
* stage-specific contract.

Composition не обязана заранее склеивать один огромный prompt для всего pipeline. Каждый этап получает только те слои и ограничения, которые ему нужны.

### 5.2 Общий порядок сборки stage context

```text
stage input
  ├─ normalized_request
  ├─ selected layer ids
  ├─ fallback decisions
  ├─ unresolved details
  ├─ hard constraints
  ├─ soft preferences
  └─ stage-specific instructions
        │
        ▼
stage prompt context
```

Рекомендуемый порядок слоёв внутри stage prompt context:

1. `content_format` base;
2. `truth_mode` base;
3. `utility_mode` base and topic layer;
4. `target_age` layer;
5. `result_language` layer;
6. `style` / `substyle` layers;
7. `entity` / `subject` layers;
8. `hard_details`;
9. `soft_preferences`;
10. `unresolved_details`;
11. stage-specific instructions;
12. output contract.

### 5.3 Hard constraints

`hard_details` и обязательные поля состояния имеют приоритет над стилистическими пожеланиями.

Нельзя:

* менять `main_subject`, если он зафиксирован;
* терять required subjects;
* менять `subject_continuity_policy`;
* превращать реальную сущность в сказочную в режиме `TRUTH`;
* игнорировать `utility_mode`, если он задаёт обучающую цель;
* нарушать возрастные и safety constraints.

### 5.4 Soft preferences

`soft_preferences` применяются, если они не конфликтуют с hard constraints.

Пример:

```text
soft_preferences:
  - "немного волшебная атмосфера"

truth_mode=TRUTH:
  можно передать как настроение, игру воображения или рисунок ребёнка,
  но нельзя сделать волшебство фактом реального мира
```

### 5.5 Unresolved details

`unresolved_details` передаются агенту как контекст, но не как гарантированный слой базы знаний.

Пример:

```json
{
  "label": "какаду",
  "type": "animal_detail",
  "instruction": "использовать общие знания модели; не утверждать, что есть отдельный проверенный слой COCKATOO"
}
```

Это позволяет не блокировать генерацию из-за отсутствия узкого prompt layer, но сохраняет честность системы.

---

## 6. Stage-Specific Contracts

### 6.1 Назначение

Stage-specific contract описывает, что конкретный агент получает, что должен вернуть и какие поля не имеет права менять.

На MVP несколько ролей может выполнять один LLM-вызов. Контракт от этого не меняется: позже роли можно разнести по разным агентам без изменения бизнес-логики.

### 6.2 Candidate Text Generator

Вход:

* `normalized_request`;
* `prompt_context`;
* `candidate_count`;
* stage prompt context для генерации текстов.

Выход:

```json
{
  "candidate_texts": [
    {
      "candidate_id": "c01",
      "theme": "ёжик ищет сухие листья для зимнего укрытия",
      "text": "Короткий текст...",
      "questions": ["Что ёжик искал?", "Почему сухие листья полезны?"],
      "used_subjects": ["ёжик"],
      "utility_points": [],
      "status": "draft"
    }
  ]
}
```

Правила:

* генерировать пул кандидатов, а не сразу только итоговое количество;
* каждому кандидату назначать тему;
* не повторять темы внутри пула;
* соблюдать `subject_continuity_policy`;
* учитывать `truth_mode`, `utility_mode`, `target_age`, style/substyle и hard details одновременно.

### 6.3 Topic Deduplication

Вход:

* `candidate_texts`;
* список тем и subjects.

Выход:

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

Правила:

* похожие темы не должны проходить как разные итоговые тексты;
* проверка должна учитывать не только формулировку темы, но и смысл;
* при сомнении можно снижать score, а не сразу удалять кандидата.

### 6.4 Scorer

Вход:

* `candidate_texts`;
* `normalized_request`;
* `prompt_context`;
* score criteria.

Выход:

```json
{
  "scores": [
    {
      "candidate_id": "c01",
      "hard_gates": {
        "safety": "pass",
        "truth_fit": "pass",
        "age_fit": "pass",
        "subject_continuity": "pass"
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

Правила:

* hard gates имеют приоритет над суммарным score;
* если значимый hard gate провален, кандидат не должен попадать в approved texts;
* общий score считается только для кандидатов, которые прошли обязательные проверки;
* на MVP score может выставлять один агент;
* позже score components можно разнести по нескольким агентам.

### 6.5 Validator

Вход:

* один candidate text;
* `normalized_request`;
* `prompt_context`;
* validation criteria.

Выход:

```json
{
  "candidate_id": "c01",
  "status": "accepted",
  "issues": [],
  "required_fixes": []
}
```

или:

```json
{
  "candidate_id": "c02",
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
  ]
}
```

Правила:

* валидировать кандидатов последовательно по ranking;
* не валидировать весь пул до конца, если уже набрано нужное количество approved texts;
* проверять safety, возраст, truth mode, utility goal, subject continuity, hard details, вопросы к ребёнку;
* возвращать actionable fixes для refiner.

### 6.6 Refiner

Вход:

* candidate text;
* validator issues;
* `normalized_request`;
* `prompt_context`;
* refiner stage context.

Выход:

```json
{
  "candidate_id": "c02",
  "theme": "исходная тема остаётся прежней",
  "text": "Исправленный текст...",
  "questions": ["..."],
  "changes_summary": "Убрана человеческая речь, сохранена тема зимнего укрытия.",
  "status": "revised"
}
```

Правила:

* не менять тему кандидата;
* не менять `main_subject`;
* не терять required subjects;
* не менять `character_profile`;
* не менять `subject_continuity_policy`;
* исправлять только проблемы, найденные валидатором, и явные локальные дефекты;
* не более 2 циклов validation/refinement на кандидата в MVP.

### 6.7 Approved Text Selector

Вход:

* ranked candidates;
* validation results;
* requested `output_count`.

Выход:

```json
{
  "approved_texts": [
    {
      "candidate_id": "c01",
      "theme": "ёжик ищет сухие листья",
      "text": "Финальный текст...",
      "questions": ["..."],
      "score": 0.80
    }
  ],
  "shortage": {
    "requested": 5,
    "approved": 5,
    "status": "enough"
  }
}
```

Если approved texts не хватает:

```json
{
  "shortage": {
    "requested": 5,
    "approved": 3,
    "status": "not_enough_valid_candidates",
    "fallback_policy": "offer_best_remaining_candidates"
  }
}
```

MVP-поведение при нехватке approved texts:

* выбрать лучшие по score кандидаты из оставшихся, если они не провалили критичные safety gates;
* предложить пользователю явно выбрать один из вариантов;
* не открывать сложный свободный арбитраж в этой редкой ветке;
* сохранить failure details для анализа.

---

## 7. Minimal Seed Prompt Scope

### 7.1 Цель seed scope

Seed prompts нужны не для полного покрытия будущей базы знаний, а для проверки контракта:

* lookup умеет находить слои;
* fallback работает предсказуемо;
* composition собирает stage context;
* generator/scorer/validator/refiner получают достаточно информации;
* golden scenarios проходят без ручной подгонки под каждый запрос.

### 7.2 MVP-покрытие режимов

```text
truth_modes/
  TRUTH
  FAIRY_TALE
  MYTH
```

Для каждого режима нужен:

* `BASE.md`;
* минимум один базовый style layer;
* минимум один stage profile для text generation;
* минимум один validator/refiner layer или общий слой, применимый к режиму.

### 7.3 MVP-покрытие utility

```text
utility/
  NARRATIVE
  TEACHING
```

Для `TEACHING` нужны seed topics:

* `HAND_WASHING_AFTER_WALK`;
* `ROAD_SAFETY`;
* `STRANGERS_AND_CANDY`.

Тема `STRANGERS_AND_CANDY` должна быть отмечена как sensitive teaching topic: формулировки должны быть осторожными, без запугивания, с акцентом на обращение к знакомому взрослому.

### 7.4 MVP-покрытие возраста

```text
ages/
  3
  5
```

Различия:

* длина фраз;
* сложность причинно-следственных связей;
* допустимая абстрактность;
* формат вопросов после текста.

### 7.5 MVP-покрытие subjects

Минимальный набор:

```text
animals:
  HEDGEHOG
  FOX
  SQUIRREL
  PARROT

people/professions:
  DOCTOR
  CHILD

objects/safety:
  TRAFFIC_LIGHT
  ROAD
  SOAP
```

`PARROT` нужен как пример fallback для запроса “какаду”: точного слоя может не быть, но общий слой попугая есть.

### 7.6 MVP-покрытие named/custom character

Нужен хотя бы один сценарий, где пользователь задаёт персонажа не из базы:

```text
маленький бельчонок Тим
```

Ожидание:

* `subjects` фиксирует бельчонка;
* `character_profile` фиксирует имя и traits;
* lookup может использовать общий слой `SQUIRREL`;
* имя `Тим` и конкретные черты идут в `hard_details` / `character_profile`, а не требуют отдельного prompt layer.

---

## 8. Golden Scenarios

### 8.1 Назначение

Golden scenarios не должны фиксировать точный финальный текст. Их задача — проверять:

* нормализацию параметров;
* prompt lookup;
* fallback;
* composition;
* subject continuity;
* hard gates;
* scoring/validation behavior.

### 8.2 Формат сценария

```markdown
## GS-001. Правдивые истории про ёжика

Input:
Сделай 5 коротких натуралистичных историй про ёжика зимой в лесу для ребёнка 3 лет.

Expected normalized params:
- content_format = story
- truth_mode = TRUTH
- utility_mode = NARRATIVE
- target_age = 3
- output_count = 5
- main_subject = ёжик
- subjects includes HEDGEHOG
- setting.season = зима

Expected prompt lookup:
- CONTENT_FORMAT_STORY
- TRUTH_BASE
- AGE_3
- TRUTH_ANIMAL_HEDGEHOG
- NATURALISTIC or base factual style

Acceptance:
- no clarification required
- candidate texts do not repeat the same theme
- approved texts keep ёжик as main subject
- no fairy-tale behavior in TRUTH mode
```

### 8.3 Минимальный список golden scenarios

1. Правдивые истории про ёжика зимой для 3 лет.
2. Сказочные истории про лису для 5 лет.
3. Мифологическая мягкая история про солнце или ветер для 5 лет.
4. Поучительная правдивая история про мытьё рук после прогулки.
5. Поучительная сказка про переход через дорогу.
6. Поучительная история про незнакомца и конфету.
7. Запрос “попугай какаду” с fallback `PARROT` и unresolved detail `какаду`.
8. Запрос “лиса, заяц и белка зимой” с явной `subject_continuity_policy`.
9. Запрос “маленький бельчонок Тим” с `character_profile`.
10. Неподдерживаемый стиль как мягкое пожелание.
11. Неподдерживаемый стиль как жёсткое требование.
12. Противоречие `TRUTH` + фантастическая деталь.

---

## 9. Acceptance Criteria

Документ и следующий seed-контур считаются достаточными для перехода к реализации, если:

* каждый seed prompt layer имеет metadata и prompt body;
* lookup для golden scenarios возвращает resolved/fallback/unresolved layers;
* prompt composition может собрать stage context для candidate generator, scorer, validator и refiner;
* `subjects`, `character_profile` и `subject_continuity_policy` не теряются между этапами;
* hard details имеют приоритет над soft preferences;
* fallback не создаёт ложного обещания пользователю;
* генератор может создать пул кандидатов;
* scorer может отранжировать кандидатов;
* validator/refiner могут последовательно набрать approved texts;
* failure при нехватке approved texts сохраняется для анализа.

---

## 10. Что не входит в MVP

В первый контракт и seed scope не входят:

* полная база персонажей и объектов;
* все возрастные градации `3`, `3.5`, `4`, `4.5`, `5`;
* полноценный режим `ENGLISH`;
* картинки-загадки;
* серия картинок по одному рассказу;
* петлевые и маятниковые анимации;
* короткие микро-мультики;
* личный кабинет и долгосрочная история пользователя;
* vector search по prompt-базе;
* отдельный агент для каждого score component;
* сложный пользовательский арбитраж при нехватке approved texts.

Эти направления должны оставаться совместимыми с контрактом, но не блокируют MVP-проверку prompt lookup и text pipeline.
