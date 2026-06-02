# STAGE_CONTRACTS.md

# Stage-Specific Contracts

Статус: рабочий контракт.

Документ описывает stage второго этапа подготовки текстового результата: что каждый stage получает, что возвращает и какие поля не имеет права менять.

На MVP несколько stage может выполнять один LLM-вызов. Контракт от этого не меняется: позже роли можно разнести по разным агентам без изменения бизнес-логики.

Источник истины по составу prompt context для каждого stage — `PROMPT_COMPOSITION_CONTRACT.md`. Этот документ является источником истины по input/output структурам, статусам и правилам изменения данных.

---

## 1. Список stage

| Stage | Короткое описание |
| --- | --- |
| `CandidateTextGenerator` | Генерирует пул текстов. |
| `TopicDeduplicator` | Проверяет повторы тем. |
| `Scorer` | Оценивает кандидатов. |
| `Ranker` | Сортирует по score. |
| `Validator` | Проверяет один текст. |
| `Refiner` | Исправляет один текст. |
| `ApprovedTextSelector` | Набирает итоговые тексты. |

Общий поток:

```text
prompt execution context
        │
        ▼
CandidateTextGenerator
        │
        ▼
TopicDeduplicator
        │
        ▼
Scorer
        │
        ▼
Ranker
        │
        ▼
Validator / Refiner loop
        │
        ▼
ApprovedTextSelector
        │
        ▼
approved_texts
```

---

## 2. CandidateTextGenerator

### 2.1 Input

| Поле | Краткое объяснение |
| --- | --- |
| `normalized_request` | Полные параметры запроса. |
| `prompt_context` | Resolved/fallback/unresolved layers. |
| `candidate_count` | Сколько кандидатов создать; приходит из config/default policy. |
| `stage_prompt_context` | Prompt для генератора. |

### 2.2 Output

```json
{
  "candidate_texts": [
    {
      "candidate_id": "c01",
      "theme": "ёжик ищет сухие листья для зимнего укрытия",
      "text": "Короткий текст...",
      "questions": ["Что ёжик искал?", "Почему сухие листья полезны?"],
      "used_subjects": ["hedgehog"],
      "utility_points": [],
      "expected_visual_idea": "ёжик рядом с сухими листьями на снегу",
      "used_context": {
        "resolved_layers": [],
        "fallback_layers": [],
        "unresolved_details": []
      },
      "status": "draft"
    }
  ]
}
```

| Поле | Краткое объяснение |
| --- | --- |
| `candidate_id` | Стабильный id кандидата. |
| `theme` | Уникальная тема текста. |
| `text` | Сгенерированный текст. |
| `questions` | Вопросы к ребёнку. |
| `used_subjects` | Какие subject ids использованы. |
| `utility_points` | Какие обучающие идеи покрыты. |
| `expected_visual_idea` | Необязательная идея для визуализации. |
| `used_context` | Какие слои и детали реально учтены. |
| `status` | Состояние кандидата. |

### 2.3 Rules

* генерировать пул кандидатов, а не сразу только итоговое количество;
* каждому кандидату назначать тему;
* не повторять темы внутри пула;
* соблюдать `subject_continuity_policy`;
* учитывать `truth_mode`, `utility_mode`, `target_age`, style/substyle и hard details одновременно.

---

## 3. TopicDeduplicator

### 3.1 Input

| Поле | Краткое объяснение |
| --- | --- |
| `candidate_texts` | Пул текстовых кандидатов. |
| `subjects` | Сущности из запроса. |
| `subject_continuity_policy` | Правило сохранения subjects. |

### 3.2 Output

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

| Поле | Краткое объяснение |
| --- | --- |
| `candidate_id` | Какой кандидат проверен. |
| `is_duplicate` | Есть ли смысловой повтор. |
| `duplicate_of` | На какой текст похож. |
| `reason` | Почему признан повтором. |

### 3.3 Rules

* похожие темы не должны проходить как разные итоговые тексты;
* проверка должна учитывать не только формулировку темы, но и смысл;
* при сомнении можно снижать score, а не сразу удалять кандидата.

---

## 4. Scorer

### 4.1 Input

| Поле | Краткое объяснение |
| --- | --- |
| `candidate_texts` | Пул кандидатов после дедупликации. |
| `normalized_request` | Параметры исходной задачи. |
| `prompt_context` | Использованные слои и fallback. |
| `score_criteria` | Компоненты оценки. |

### 4.2 Output

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

| Поле | Краткое объяснение |
| --- | --- |
| `hard_gates` | Обязательные проходные проверки. |
| `score_components` | Частные оценки качества. |
| `total_score` | Итоговая оценка кандидата. |

### 4.3 Rules

* hard gates имеют приоритет над суммарным score;
* если значимый hard gate провален, кандидат не должен попадать в approved texts;
* общий score считается только для кандидатов, которые прошли обязательные проверки;
* на MVP score может выставлять один агент;
* позже score components можно разнести по нескольким агентам.

---

## 5. Ranker

`Ranker` может быть детерминированным шагом без отдельного LLM-вызова.

### 5.1 Input

| Поле | Краткое объяснение |
| --- | --- |
| `candidate_texts` | Пул кандидатов после scoring. |
| `scores` | Hard gates и score components. |

### 5.2 Output

```json
{
  "ranked_candidates": [
    {
      "candidate_id": "c01",
      "rank": 1,
      "total_score": 0.80,
      "hard_gates_passed": true
    }
  ]
}
```

| Поле | Краткое объяснение |
| --- | --- |
| `ranked_candidates` | Кандидаты в порядке проверки. |
| `rank` | Место кандидата в очереди. |
| `hard_gates_passed` | Можно ли валидировать кандидата. |

### 5.3 Rules

* кандидаты с проваленными критичными hard gates не попадают в обычную очередь validation;
* сортировка идёт по `total_score` сверху вниз;
* при равенстве score можно учитывать novelty и visual potential.

---

## 6. Validator

### 6.1 Input

| Поле | Краткое объяснение |
| --- | --- |
| `candidate_text` | Один текст для проверки. |
| `normalized_request` | Параметры исходной задачи. |
| `prompt_context` | Слои и ограничения. |
| `validation_criteria` | Что именно проверять. |

### 6.2 Output

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

| Поле | Краткое объяснение |
| --- | --- |
| `status` | `accepted`, `needs_revision`, `rejected`. |
| `issues` | Найденные проблемы. |
| `required_fixes` | Что должен исправить refiner. |

### 6.3 Rules

* валидировать кандидатов последовательно по ranking;
* не валидировать весь пул до конца, если уже набрано нужное количество approved texts;
* проверять safety, возраст, truth mode, utility goal, subject continuity, hard details, вопросы к ребёнку;
* возвращать actionable fixes для refiner.

---

## 7. Refiner

### 7.1 Input

| Поле | Краткое объяснение |
| --- | --- |
| `candidate_text` | Текст, который надо исправить. |
| `validator_issues` | Проблемы от validator. |
| `normalized_request` | Параметры исходной задачи. |
| `prompt_context` | Слои и ограничения. |
| `refiner_stage_context` | Prompt для исправления. |

### 7.2 Output

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

| Поле | Краткое объяснение |
| --- | --- |
| `theme` | Тема должна сохраниться. |
| `text` | Исправленный текст. |
| `questions` | Исправленные вопросы. |
| `changes_summary` | Что было изменено. |
| `status` | Состояние после правки. |

### 7.3 Rules

* не менять тему кандидата;
* не менять `main_subject`;
* не терять required subjects;
* не менять `character_profile`;
* не менять `subject_continuity_policy`;
* исправлять только проблемы, найденные validator, и явные локальные дефекты;
* не более 2 циклов validation/refinement на кандидата в MVP.

---

## 8. ApprovedTextSelector

`ApprovedTextSelector` работает после ranking и validation/refinement loop. До validation есть только ranked candidates, но ещё нет approved texts.

### 8.1 Input

| Поле | Краткое объяснение |
| --- | --- |
| `ranked_candidates` | Кандидаты по убыванию score. |
| `validated_candidate_versions` | Финальные версии кандидатов после validation/refinement loop. |
| `validation_results` | Результаты validation loop. |
| `output_count` | Сколько текстов нужно. |

`ApprovedTextSelector` утверждает именно `validated_candidate_versions`, а не исходные drafts из `ranked_candidates`. Если кандидат проходил refinement, selector должен брать последнюю валидированную версию текста и вопросов.

### 8.2 Output

```json
{
  "approved_texts": [
    {
      "candidate_id": "c01",
      "theme": "ёжик ищет сухие листья",
      "text": "Финальный текст...",
      "questions": ["..."],
      "score": 0.80,
      "validation_status": "accepted",
      "validation_summary": "Возраст, truth_mode, subject continuity и safety соблюдены.",
      "used_context": {
        "resolved_layers": [],
        "fallback_layers": [],
        "unresolved_details": []
      },
      "trace_refs": {}
    }
  ],
  "shortage": {
    "requested": 5,
    "approved": 5,
    "status": "enough"
  },
  "safe_fallback_candidates": []
}
```

| Поле | Краткое объяснение |
| --- | --- |
| `approved_texts` | Итоговые тексты второго этапа. |
| `validation_status` | Итоговое состояние проверки текста. |
| `validation_summary` | Краткое резюме пройденной проверки. |
| `used_context` | Какие prompt layers и детали реально учтены. |
| `trace_refs` | Ссылки на trace/debug metadata, если есть. |
| `shortage` | Хватило ли валидных текстов. |
| `requested` | Сколько просил пользователь. |
| `approved` | Сколько удалось набрать. |
| `status` | `enough` или причина нехватки. |
| `safe_fallback_candidates` | Лучшие безопасные кандидаты, если approved texts не хватило. |
| `why_safe` | Почему fallback можно показать пользователю. |
| `known_issues` | Известные некритичные проблемы fallback-кандидата. |

### 8.3 MVP fallback

Если approved texts не хватает:

* selector возвращает статус нехватки;
* selector может вернуть лучшие safe fallback candidates из оставшихся, если они не провалили критичные safety gates;
* selector сохраняет failure details для анализа;
* повторная генерация, предложение вариантов пользователю или STOP являются orchestration-level решениями, а не обязанностью selector.

Пример shortage output:

```json
{
  "approved_texts": [
    {
      "candidate_id": "c01",
      "theme": "ёжик ищет сухие листья",
      "text": "Финальный текст...",
      "questions": ["..."],
      "score": 0.80,
      "validation_status": "accepted",
      "validation_summary": "Возраст, truth_mode, subject continuity и safety соблюдены.",
      "used_context": {
        "resolved_layers": [],
        "fallback_layers": [],
        "unresolved_details": []
      },
      "trace_refs": {}
    }
  ],
  "shortage": {
    "requested": 5,
    "approved": 1,
    "status": "not_enough_valid_candidates"
  },
  "safe_fallback_candidates": [
    {
      "candidate_id": "c07",
      "theme": "ёжик замечает следы на снегу",
      "text": "Текст безопасного fallback-кандидата...",
      "questions": ["..."],
      "score": 0.71,
      "why_safe": "Не провалил safety и age gates.",
      "known_issues": ["Слабее выражена поучительная цель."]
    }
  ]
}
```

---

## 9. Общие immutable fields

Следующие поля нельзя менять после первого этапа без отдельной логики уточнения:

* `content_format`;
* `truth_mode`;
* `utility_mode`;
* `utility_topic`;
* `target_age`;
* `main_subject`;
* required `subjects`;
* `is_character`;
* `character_profile`;
* `subject_continuity_policy`;
* `hard_details`.

Если stage считает, что одно из этих полей невозможно соблюсти, он должен вернуть ошибку/issue, а не молча менять контракт.
