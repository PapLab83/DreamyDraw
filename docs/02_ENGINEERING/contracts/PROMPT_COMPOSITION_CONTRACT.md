# PROMPT_COMPOSITION_CONTRACT.md

# Prompt Composition Contract

Статус: рабочий контракт.

Документ описывает, как из `normalized_request`, найденных prompt layers и stage-specific правил собирается prompt context для конкретного этапа pipeline.

Важно: composition не обязана заранее склеивать один огромный prompt для всего pipeline. Каждый stage получает только те слои и ограничения, которые нужны ему сейчас.

---

## 1. Что такое prompt composition

Prompt composition отвечает на вопрос:

```text
Какой контекст должен получить конкретный агент,
чтобы выполнить свою задачу и не нарушить параметры запроса?
```

На вход composition получает:

* `normalized_request`;
* `resolved_layers`;
* `fallback_layers`;
* `unresolved_details`;
* `hard_details`;
* `soft_preferences`;
* stage-specific contract.

На выходе:

```text
stage prompt context
```

---

## 2. Общий порядок слоёв

Базовый порядок приоритетов:

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

Этот порядок является общим правилом. Конкретный stage может использовать не все слои.

---

## 3. Общая схема composition

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

---

## 4. Stage-specific recipes

### 4.1 Candidate Text Generator

Получает самый полный творческий контекст.

Нужны:

* format layer;
* truth mode layer;
* utility layer;
* age layer;
* style/substyle layers;
* subject/entity layers;
* character profile, если есть;
* hard details;
* soft preferences;
* unresolved details;
* output contract для candidate texts.

Особенность: generator должен учитывать ключевые слои одновременно. Например, teaching topic нельзя добавлять постфактум к уже готовой истории, если он должен определять тему и причинно-следственную логику текста.

### 4.2 Topic Deduplicator

Получает не полный художественный prompt, а компактный смысловой контекст.

Нужны:

* список candidate themes;
* `subjects`;
* `utility_mode`;
* `subject_continuity_policy`;
* критерии похожести тем.

Не нужны:

* полный body всех style layers;
* image layers;
* подробные примеры художественного тона.

### 4.3 Scorer

Получает criteria-oriented context.

Нужны:

* candidate texts;
* normalized params;
* score components;
* hard gates;
* краткое summary релевантных layers;
* constraints из metadata и body.

Scorer не должен переписывать текст. Он только оценивает.

### 4.4 Validator

Получает constraints-oriented context.

Нужны:

* один candidate text;
* `normalized_request`;
* hard constraints;
* safety constraints;
* age constraints;
* truth mode constraints;
* utility constraints;
* subject continuity rules;
* output contract для validation result.

Validator не должен сам исправлять текст. Он формулирует проблемы и required fixes.

### 4.5 Refiner

Получает repair-oriented context.

Нужны:

* исходный candidate text;
* validator issues;
* immutable fields;
* hard constraints;
* ограниченный набор prompt layers, нужных для исправления;
* output contract для revised candidate.

Refiner не должен заново придумывать тему, менять subject или переписывать всё без необходимости.

### 4.6 Approved Text Selector

Получает selection-oriented context.

Нужны:

* ranked candidates;
* validation results;
* requested `output_count`;
* fallback policy при нехватке approved texts.

Selector не генерирует и не редактирует тексты. Он выбирает итоговый набор.

---

## 5. Hard constraints

`hard_details` и обязательные поля состояния имеют приоритет над стилистическими пожеланиями.

Нельзя:

* менять `main_subject`, если он зафиксирован;
* терять required subjects;
* менять `subject_continuity_policy`;
* превращать real subject в сказочный в режиме `TRUTH`;
* игнорировать `utility_mode`, если он задаёт обучающую цель;
* нарушать возрастные и safety constraints;
* менять `character_profile`, если `is_character = true`.

---

## 6. Soft preferences

`soft_preferences` применяются, если они не конфликтуют с hard constraints.

Пример:

```text
soft_preferences:
  - "немного волшебная атмосфера"

truth_mode=TRUTH:
  можно передать как настроение, игру воображения или рисунок ребёнка,
  но нельзя сделать волшебство фактом реального мира
```

---

## 7. Unresolved details

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

## 8. Что относится к техспеке

В технической спецификации оркестратора нужно отдельно описать:

* какой класс или сервис собирает stage prompt context;
* где загружаются prompt bodies;
* какие prompt bodies можно грузить lazy;
* как stage context сохраняется в Langfuse trace;
* как stage context сохраняется или не сохраняется в `SessionState`;
* как тестировать composition без реального LLM-вызова.
