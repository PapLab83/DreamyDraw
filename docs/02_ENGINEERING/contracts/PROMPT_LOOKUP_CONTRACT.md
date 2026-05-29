# PROMPT_LOOKUP_CONTRACT.md

# Prompt Lookup Contract

Статус: рабочий контракт.

Документ описывает, как система сопоставляет пользовательский запрос и нормализованные параметры с prompt-базой.

Проще:

```text
Prompt lookup отвечает на вопрос:
какие prompt-файлы мы можем использовать, какие заменяем fallback-слоями,
а какие детали оставляем как свободный контекст модели.
```

---

## 1. Два режима lookup

Prompt layers участвуют в оркестрации в двух разных режимах.

### 1.1 Prompt-aware metadata lookup

Используется на первом этапе, когда система ещё понимает запрос.

Цель:

* понять, какие режимы, стили, подстили и сущности вообще поддерживаются;
* сопоставить слова пользователя с `aliases`;
* не обещать неподдерживаемую стилизацию;
* понять, нужен ли fallback;
* решить, нужно ли уточнение пользователя.

Этот lookup работает с metadata, а не с полными prompt bodies.

Пример:

```text
Хочу сказку как у Чуковского про ёжика.
```

Metadata lookup может определить:

```json
{
  "truth_mode": "FAIRY_TALE",
  "substyle": "CHUKOVSKY",
  "main_subject": "ёжик"
}
```

### 1.2 Execution lookup

Используется после нормализации и candidate layer resolution.

Цель:

* превратить уже согласованные параметры в список `resolved_layers`;
* зафиксировать `fallback_layers`;
* сохранить `unresolved_details`;
* подготовить основу для `prompt_context`;
* не менять обещание, показанное пользователю в preview.

Этот lookup тоже может начинаться с metadata. Полные prompt bodies загружаются позже stage-specific, когда конкретному этапу нужен prompt context.

---

## 2. Результат lookup

```json
{
  "resolved_layers": [
    {
      "type": "content_format",
      "id": "CONTENT_FORMAT_STORY",
      "source": "content_formats/story/BASE.md",
      "reason": "content_format=story"
    },
    {
      "type": "truth_mode",
      "id": "TRUTH_BASE",
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

---

## 3. Базовый порядок поиска

1. Найти слой формата результата по `content_format`.
2. Найти базовый слой режима по `truth_mode`.
3. Найти utility-слой по `utility_mode`.
4. Найти возрастной слой по `target_age`.
5. Найти языковые слои по `audience_language` и `result_language`.
6. Найти style/substyle слои.
7. Найти entity/subject слои.
8. Найти stage profiles, validators и refiners, если они нужны конкретному этапу.

Порядок фиксирует зависимость: старшие плоскости ограничивают применимость младших. Например, `TRUTH` и `FAIRY_TALE` могут иметь разные слои для `FOX`.

---

## 4. Exact match, aliases и fallback

Lookup использует три уровня сопоставления.

### 4.1 Exact match

Пользовательский или нормализованный параметр прямо соответствует `id` или `name`.

### 4.2 Aliases

Формулировка пользователя совпадает с одним из `aliases`.

### 4.3 Fallback

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

---

## 5. Когда нужно уточнение пользователя

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

## 6. Что относится к техспеке

Этот контракт не описывает техническую реализацию индекса.

В технической спецификации оркестратора нужно отдельно описать:

* как сканируются директории prompt-базы;
* как парсится YAML metadata;
* где хранится prompt index;
* как работает кеширование;
* как валидируется уникальность `id`;
* как lookup вызывается из LangGraph-ноды;
* как результат lookup сохраняется в `SessionState`.
