# NORMALIZED_STATE_CONTRACT.md

# Normalized State Contract

Статус: рабочий контракт.

Документ описывает `normalized_request` — структурированный результат первого этапа оркестрации. Он должен быть достаточно полным, чтобы второй этап мог генерировать тексты без повторного выяснения базовых намерений пользователя.

Это не финальная Pydantic-схема, но логический контракт для будущей реализации.

---

## 1. Минимальный объект

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
      "is_character": false,
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
    "главный объект — ёжик",
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

---

## 2. Поля первого этапа

| Поле | Смысл |
| --- | --- |
| `content_format` | Формат результата: на MVP основной формат `story`. |
| `truth_mode` | Режим отношения к реальности: `TRUTH`, `MYTH`, `FAIRY_TALE`. |
| `utility_mode` | Цель результата: `NARRATIVE`, `TEACHING`, позже `ENGLISH`. |
| `target_age` | Возрастной профиль: на MVP достаточно `3` и `5`. |
| `output_count` | Сколько итоговых approved texts нужно пользователю. |
| `audience_language` | Язык общения с пользователем. На старте `ru`. |
| `result_language` | Язык результата. На старте `ru`. |
| `main_subject` | Главное человеко-понятное обозначение темы, объекта или персонажа. |
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

---

## 3. Subject Contract

`subjects` фиксирует, о ком или о чём должен быть результат. Это не обязательно персонажи в художественном смысле.

Минимальная структура subject:

```json
{
  "id": "fox",
  "label": "лиса",
  "type": "animal",
  "role": "main",
  "is_character": false,
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
| `resolved_layer_id` | Найденный prompt layer, если он есть. |
| `unresolved_detail` | Деталь, для которой нет точного слоя. |

---

## 4. Character Contract

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
      "resolved_layer_id": "TRUTH_ANIMAL_SQUIRREL",
      "unresolved_detail": "маленький бельчонок по имени Тим"
    }
  ],
  "character_profile": {
    "name": "Тим",
    "base_subject_id": "squirrel_child_tim",
    "stable_traits": ["маленький", "любопытный"],
    "must_remain_same_character": true
  },
  "subject_continuity_policy": "same_character_all_texts"
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

## 5. Subject Continuity Policy

`subject_continuity_policy` фиксирует, как subjects должны сохраняться между несколькими итоговыми текстами.

Возможные значения:

| Значение | Смысл |
| --- | --- |
| `same_main_subject_all_texts` | Один главный subject должен быть во всех текстах. |
| `same_character_all_texts` | Один персонаж с профилем должен сохраняться во всех текстах. |
| `distribute_subjects_across_texts` | Несколько subjects можно распределять по разным текстам. |
| `combine_subjects_in_each_text` | Все основные subjects должны присутствовать в каждом тексте. |
| `free_subject_variation` | Subjects могут варьироваться, если это не ломает запрос. |

Пример:

```text
Сделай 3 истории про лису, зайца и белку зимой.
```

Вариант политики:

```json
{
  "subject_continuity_policy": "distribute_subjects_across_texts"
}
```

Это продуктовая политика, а не техническое ограничение. Если позже команда решит, что такие запросы должны означать “все герои в каждой истории”, контракт не меняется: меняется только значение policy.

---

## 6. Prompt Context

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
  "resolved_layers": ["TRUTH_ANIMAL_PARROT"],
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
