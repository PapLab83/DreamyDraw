# NORMALIZED_STATE_CONTRACT.md

# Normalized State Contract

Статус: рабочий контракт.

Документ описывает `normalized_request` — структурированный результат первого этапа оркестрации. Он должен быть достаточно полным, чтобы второй этап мог генерировать тексты без повторного выяснения базовых намерений пользователя.

Это не финальная Pydantic-схема, но логический контракт для будущей реализации.

`normalized_request` описывает саму задачу генерации. Процессные данные первого этапа — confidence, необходимость уточнения, причина уточнения и preview — должны жить отдельно, например в `interpretation_state` и `preview_state`.

---

## 1. Минимальный объект

```json
{
  "content_format": "story",
  "truth_mode": "TRUTH",
  "utility_mode": "NARRATIVE",
  "utility_topic": null,
  "target_age": "3",
  "output_count": 5,
  "cultural_context": "RUSSIAN_FOLK",
  "audience_language": "ru",
  "result_language": "ru",
  "current_config": {
    "truth_mode": "TRUTH",
    "utility_mode": "NARRATIVE",
    "target_age": "3",
    "cultural_context": "RUSSIAN_FOLK",
    "text_style_base": "calm",
    "image_style": "cartoon"
  },
  "main_subject": "ёжик",
  "subjects": [
    {
      "id": "hedgehog",
      "label": "ёжик",
      "type": "animal",
      "role": "main",
      "is_character": false,
      "base_species": "hedgehog",
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
  "subject_continuity_policy": {
    "mode": "single_subject_all_items",
    "required_subjects": ["hedgehog"],
    "coverage": "item_level",
    "allowed_distribution": "all_items",
    "can_mix_subjects_in_one_item": true,
    "can_introduce_new_subjects": true,
    "can_replace_required_subjects": false
  },
  "hard_details": [
    "главный объект — ёжик",
    "действие происходит зимой в лесу",
    "истории должны быть реалистичными"
  ],
  "soft_preferences": [
    "мягкий тон",
    "простые фразы"
  ],
  "user_context": {
    "available": false,
    "source": null,
    "defaults": {},
    "preferences": {},
    "avoid": [],
    "recent_topics": []
  },
  "visual_preferences": {
    "image_style": "cartoon",
    "target_device": null,
    "visual_output_type": "single_image_card"
  },
  "prompt_context": {
    "resolved_layers": [],
    "fallback_layers": [],
    "unresolved_details": []
  }
}
```

---

## 2. Поля первого этапа

| Поле | Смысл |
| --- | --- |
| `content_format` | Формат результата: на MVP основной формат `story`. |
| `truth_mode` | Режим отношения к реальности: `TRUTH` или `FAIRY_TALE`. MYTH не поддерживается в Release 2. |
| `utility_mode` | Цель результата: `NARRATIVE`, `TEACHING`, позже `ENGLISH`. |
| `utility_topic` | Конкретная teaching/practical тема, если есть: например `hygiene_handwashing`, `road_crossing`, `stranger_candy_safety`; иначе `null`. |
| `target_age` | Возрастной профиль: `3` или `5`; default `5`. |
| `output_count` | Сколько итоговых approved texts нужно пользователю. |
| `cultural_context` | Canonical культурный root selector. Release 2: только `RUSSIAN_FOLK`. |
| `audience_language` | Язык общения с пользователем. На старте `ru`. |
| `result_language` | Язык результата. На старте `ru`. |
| `current_config` | Настройки, с которыми пользователь пришёл в запрос. |
| `main_subject` | Главное человеко-понятное обозначение темы, объекта или персонажа. |
| `subjects` | Структурированный список сущностей запроса. |
| `setting` | Место, сезон, время и другие обстоятельства. |
| `text_style_base` | Базовый тон текста. |
| `substyle` | Конкретный подстиль, если найден поддерживаемый prompt layer. На MVP хранится **canonical layer id** (например `CHUKOVSKY_STYLE`), не slug. Может быть `null`. |
| `character_profile` | Профиль устойчивого персонажа, если он нужен. |
| `subject_continuity_policy` | Правило сохранения сущностей между текстами. |
| `hard_details` | Жёсткие требования пользователя. |
| `soft_preferences` | Мягкие пожелания пользователя. |
| `user_context` | Минимальный контекст пользователя. Если истории нет, объект существует с `available=false`. |
| `visual_preferences` | Настройки для будущего визуального этапа. Text pipeline их сохраняет, но не обязан использовать. |
| `prompt_context` | Результат prompt lookup и candidate layer resolution. |

В Release 2 `output_count`, `target_age`, `truth_mode`, `cultural_context` и `utility_mode` всегда заполнены из CLI/config/defaults. `raw_text` не участвует в их извлечении, переопределении, reconciliation или conflict-check. Defaults: `3`, `5`, `TRUTH`, `RUSSIAN_FOLK`, `NARRATIVE`; `output_count` валиден в диапазоне `1..10`.

`utility_topic` фиксирует конкретную прикладную тему только тогда, когда она действительно извлечена из запроса или выбрана после clarification. Если `utility_mode = TEACHING` и prompt lookup нашёл подходящий topic layer, `utility_topic` должен быть заполнен, а соответствующий слой должен попасть в `prompt_context.resolved_layers` с `type = "utility"` и `role = "utility_topic"`. Если подходящий слой не найден, тема остаётся в `prompt_context.unresolved_details` или требует clarification/fallback по правилам оркестрации.

---

## 3. Interpretation State and Preview State

Эти блоки не являются частью `normalized_request`, потому что описывают процесс интерпретации, а не саму задачу генерации.

Пример:

```json
{
  "interpretation_state": {
    "confidence": {
      "content_format": 90,
      "truth_mode": 85,
      "utility_mode": 80,
      "target_age": 95,
      "main_subject": 95
    },
    "requires_clarification": false,
    "clarification_reason": null
  },
  "preview_state": {
    "preview_text": "Я подготовлю 5 спокойных правдивых историй про ёжика зимой в лесу для ребёнка 3 лет.",
    "shown_to_user": true
  }
}
```

Правило:

```text
normalized_request
  → input второго этапа

interpretation_state / preview_state
  → состояние первого этапа и UI/session metadata
```

---

## 4. Subject Contract

`subjects` фиксирует, о ком или о чём должен быть результат. Это не обязательно персонажи в художественном смысле.

Минимальная структура subject:

```json
{
  "id": "fox",
  "label": "лиса",
  "type": "animal",
  "role": "main",
  "is_character": false,
  "base_species": "fox",
  "resolved_layer_id": "TRUTH_ANIMAL_FOX",
  "unresolved_detail": null
}
```

| Поле | Смысл |
| --- | --- |
| `id` | Нормализованный идентификатор сущности. |
| `label` | Человеко-понятное имя из запроса. |
| `type` | Тип сущности: `animal`, `person`, `profession`, `object`, `place`, `nature`, `custom`. |
| `role` | Роль в результате: `main`, `secondary`, `context`. |
| `is_character` | Является ли сущность устойчивым персонажем. |

**MVP (Stage 1 actual):** при `truth_mode = TRUTH` животное из запроса («про лису») по умолчанию **`is_character = false`** (subject/тема, не герой). `is_character = true` — только при явных маркерах: имя, «герой/персонаж/зовут», «маленький \<species\>» + trait (например бельчонок Тим). В `FAIRY_TALE` животные могут оставаться `is_character = true` по умолчанию.
| `base_species` | Базовый вид или родовая сущность, если применимо. |
| `resolved_layer_id` | Найденный prompt layer, если он есть. |
| `unresolved_detail` | Деталь, для которой нет точного слоя. |

---

## 5. Character Contract

Если `subject.is_character = true`, система должна заполнить или подготовить `character_profile`.

Пример:

```json
{
  "main_subject": "маленький бельчонок Тим",
  "subjects": [
    {
      "id": "squirrel_child_tim",
      "label": "маленький бельчонок Тим",
      "type": "animal_character",
      "role": "main",
      "is_character": true,
      "base_species": "squirrel",
      "resolved_layer_id": "TRUTH_ANIMAL_SQUIRREL",
      "unresolved_detail": "маленький бельчонок по имени Тим"
    }
  ],
  "character_profile": {
    "name": "Тим",
    "base_subject_id": "squirrel_child_tim",
    "stable_traits": ["маленький", "любопытный"],
    "stable_details": ["бельчонок"],
    "speech_style": null,
    "must_remain_same_character": true
  },
  "subject_continuity_policy": {
    "mode": "single_character_all_items",
    "required_subjects": ["squirrel_child_tim"],
    "coverage": "item_level",
    "allowed_distribution": "all_items",
    "can_mix_subjects_in_one_item": true,
    "can_introduce_new_subjects": true,
    "can_replace_required_subjects": false
  }
}
```

Правило:

```text
is_character = false
  → subject является объектом, темой, животным, профессией, явлением или местом.

is_character = true
  → subject должен вести себя как устойчивый герой.
  → character_profile фиксирует имя, черты и правила сохранения.
```

Система может сама определить `is_character = true`, даже если пользователь не сказал слово “персонаж”.

Пример:

```text
Сделай историю про маленького бельчонка.
```

Ожидаемая интерпретация:

```json
{
  "label": "маленький бельчонок",
  "is_character": true
}
```

---

## 6. Subject Continuity Policy

`subject_continuity_policy` фиксирует, как subjects должны сохраняться между несколькими итоговыми текстами.

Это объект, а не строка. Так валидатор и редактор могут явно понимать, какие subjects обязательны, где они должны появиться и можно ли добавлять новых.

Минимальная структура:

```json
{
  "mode": "multiple_subjects_distributed",
  "required_subjects": ["fox", "hare", "squirrel"],
  "coverage": "series_level",
  "allowed_distribution": "across_items",
  "can_mix_subjects_in_one_item": true,
  "can_introduce_new_subjects": true,
  "can_replace_required_subjects": false
}
```

Возможные `mode`:

| Значение | Смысл |
| --- | --- |
| `single_subject_all_items` | Один главный subject должен быть во всех текстах. |
| `single_character_all_items` | Один персонаж с профилем должен сохраняться во всех текстах. |
| `multiple_subjects_distributed` | Несколько subjects покрываются на уровне серии, но не обязаны быть в каждом тексте. |
| `multiple_subjects_together` | Все основные subjects должны присутствовать в каждом тексте или почти в каждом. |
| `main_plus_secondary` | Один subject главный, остальные могут быть второстепенными. |
| `subject_pool_optional` | Есть пул допустимых subjects, но не каждый обязан появиться. |
| `topic_only_no_continuity` | Запрос задаёт тему, но не требует устойчивого героя или объекта через серию. |

Пример:

```text
Сделай 3 истории про лису, зайца и белку зимой.
```

Вариант политики:

```json
{
  "subject_continuity_policy": {
    "mode": "multiple_subjects_distributed",
    "required_subjects": ["fox", "hare", "squirrel"],
    "coverage": "series_level",
    "allowed_distribution": "across_items",
    "can_mix_subjects_in_one_item": true,
    "can_introduce_new_subjects": true,
    "can_replace_required_subjects": false
  }
}
```

Это продуктовая политика, а не техническое ограничение. Если позже команда решит, что такие запросы должны означать “все герои в каждой истории”, контракт не меняется: меняется только значение policy.

---

## 7. Prompt Context

`prompt_context` хранит результат prompt lookup.

```json
{
  "resolved_layers": [],
  "fallback_layers": [],
  "unresolved_details": []
}
```

| Поле | Смысл |
| --- | --- |
| `resolved_layers` | Точно найденные prompt layers. |
| `fallback_layers` | Поддерживаемые слои, выбранные вместо отсутствующих точных. |
| `unresolved_details` | Детали запроса, для которых нет слоя, но которые нужно передать агентам. |

Пример:

```text
расскажи про попугая какаду
```

Если есть `PARROT.md`, но нет `COCKATOO.md`:

```json
{
  "resolved_layers": [
    {
      "type": "entity",
      "id": "TRUTH_ANIMAL_PARROT",
      "source": "truth_modes/TRUTH/characters/animals/PARROT.md"
    }
  ],
  "fallback_layers": [
    {
      "requested": "какаду",
      "fallback_layer_id": "TRUTH_ANIMAL_PARROT",
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

### Stage 2 runtime prompt bodies (MVP §3.3)

`prompt_context` in session state stores **metadata only** (`resolved_layers`, ids, hashes). Stage 2 LLM executors load full markdown bodies at runtime via `PromptComposer` with `body_policy = include_bodies_runtime`.

| Storage | Contains layer bodies? |
| --- | --- |
| `prompt_context` / session JSON | No — ids, types, roles, source paths, hashes |
| `stage_prompt_context.entries` (durable) | No — `body_policy`, layer ids, `stage_context_hash` |
| Stage 2 LLM prompt payload (`layer_grounding.bodies`) | Yes — runtime only, not persisted |

All resolved modes benefit (TRUTH, FAIRY_TALE, age, style, entity). TRUTH additionally uses deterministic post-check after LLM validator accept.
