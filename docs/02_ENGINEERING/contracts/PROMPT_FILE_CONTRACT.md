# PROMPT_FILE_CONTRACT.md

# Prompt File Contract

Статус: рабочий контракт.

Документ описывает структуру `.md` prompt layer. Эта структура нужна не только для чтения человеком: YAML metadata должна парситься детерминированно и использоваться для prompt-aware lookup, preview, fallback и валидации prompt-базы.

Release 2 active files live under `prompts/cultural_contexts/russian_folk/`. Paths in examples below are relative to the selected cultural root.

---

## 1. Общий формат

Каждый prompt layer хранится в одном `.md` файле и состоит из двух частей:

1. YAML metadata block;
2. markdown prompt body.

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

# Назначение слоя

Используй этот слой, когда нужно писать о ёжике как о реальном животном...
```

---

## 2. Обязательные metadata-поля

| Поле | Смысл |
| --- | --- |
| `id` | Стабильный уникальный идентификатор слоя. |
| `type` | Тип слоя: `format`, `truth_mode`, `style`, `substyle`, `entity`, `utility`, `age`, `language`, `stage`, `validator`, `refiner`. |
| `namespace` | Логическое расположение слоя в prompt-базе. |
| `name` | Человеко-понятное имя. |
| `aliases` | Формулировки пользователя, которые могут указывать на этот слой. |
| `applies_to` | Ограничения применимости по формату, режиму, возрасту, utility. |
| `short_description` | Короткое описание для metadata lookup и preview. |
| `constraints` | Короткие машинно-читаемые ограничения, которые слой добавляет в prompt context. |

---

## 3. Опциональные metadata-поля

| Поле | Смысл |
| --- | --- |
| `user_description` | Описание для пользовательских уточнений. |
| `role` | Orchestration-смысл слоя внутри resolved context, если `type` недостаточно точен для lookup/composition. |
| `good_for` | Когда слой особенно уместен. |
| `bad_for` | Когда слой нежелателен или конфликтует с режимом. |
| `fallback_priority` | Приоритет слоя как fallback-кандидата. |
| `requires_user_confirmation` | Нужно ли уточнять выбор у пользователя при совпадении. |
| `example_result_ids` | Ссылки на best-case examples для будущего UI. |
| `sample_text` | Короткий пример результата, если нужен для UX. |
| `safety_notes` | Особые ограничения безопасности. |

`role` не заменяет `type`: `type` всегда остаётся значением из enum prompt layer types. `role` уточняет назначение слоя для оркестрации, например `content_format`, `utility_mode`, `utility_topic`, `audience_language`, `result_language`.

В общем контракте `role` является optional, но конкретный seed inventory или prompt family может сделать его обязательным для слоёв, где без него lookup/composition становятся неоднозначными. Для текущего seed set `role` должен быть указан как минимум для:

* `type = "format"`: `role = "content_format"`;
* `type = "utility"`: `role = "utility_mode"` или `role = "utility_topic"`;
* `type = "language"`: `role = "audience_language"` или `role = "result_language"`;
* stage-related layers, если inventory различает их orchestration назначение через `role`.

---

## 4. Metadata constraints vs body constraints

Ограничения могут встречаться и в metadata, и в prompt body. Это нормально, но роли разные.

```text
metadata constraints
  → короткие, структурные, машинно-читаемые
  → нужны для lookup, preview, fallback, автоматической проверки базы

body constraints
  → подробные, объяснительные, ориентированные на LLM-агента
  → нужны для фактической генерации, валидации или редактуры
```

Пример:

```yaml
constraints:
  - Не приписывать ёжику человеческую речь в режиме TRUTH.
```

В body это может быть раскрыто подробнее:

```markdown
Если история создаётся в режиме TRUTH, ёжик не должен говорить, думать человеческими словами или принимать социальные решения как ребёнок. Можно описывать его поведение через наблюдение взрослого или ребёнка.
```

---

## 5. Prompt Body Contract

Prompt body не обязан иметь одинаковую структуру для всех типов слоёв, но должен быть достаточно предсказуемым для авторов промптов и ревью.

Рекомендуемые разделы:

```markdown
# Назначение слоя

# Что добавить в результат

# Ограничения

# Как сочетать с другими слоями

# Примеры допустимого поведения

# Примеры недопустимого поведения
```

Минимальные требования к body:

* ясно объяснить, когда слой применяется;
* описать, что слой должен добавить в генерацию;
* описать, что слой запрещает или ограничивает;
* не дублировать весь базовый prompt другого слоя;
* не противоречить `applies_to`, `bad_for` и `constraints` из metadata;
* писать инструкции так, чтобы их можно было использовать в generator, validator или refiner context.

Для простых слоёв некоторые разделы могут быть опущены. Для sensitive teaching topics разделы `Ограничения` и `Примеры недопустимого поведения` обязательны.

---

## 6. Типы prompt layers

| Тип | Пример | Назначение |
| --- | --- | --- |
| `format` | `content_formats/story/BASE.md` | Форма результата и общий output contract. |
| `truth_mode` | `truth_modes/TRUTH/BASE.md` | Правила мира: правда или сказка. |
| `style` / `substyle` | `truth_modes/FAIRY_TALE/styles/folklore/RUSSIAN_FOLK.md` | Стиль или подстиль внутри режима. |
| `entity` | `truth_modes/TRUTH/characters/animals/FOX.md` | Сущность, объект, персонаж или явление. |
| `utility` | `utility/TEACHING/topics/ROAD_SAFETY.md` | Цель результата и обучающий слой. |
| `age` | `ages/3/BASE.md` | Возрастная сложность. |
| `language` | `languages/result/ru.md` | Язык результата. |
| `stage` | `stage_profiles/TEXT_GENERATION.md` | Инструкции конкретного этапа pipeline. |
| `validator` | `validators/TEXT_VALIDATOR.md` | Правила проверки. |
| `refiner` | `refiners/TEXT_REFINER.md` | Правила редактуры. |
