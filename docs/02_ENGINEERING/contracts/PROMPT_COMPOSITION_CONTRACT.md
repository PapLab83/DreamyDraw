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

## 4. Stage prompt context profiles

Этот раздел описывает только состав prompt context для stage: какие слои, ограничения и summaries нужно подать в агент. Input/output структуры, статусы и правила изменения данных описаны в `STAGE_CONTRACTS.md`.

### 4.1 Candidate Text Generator

Prompt context profile:

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

Composition note: generator получает самый полный контекст, потому что именно на этом этапе truth mode, utility, age, subjects и style должны работать одновременно.

### 4.2 Topic Deduplicator

Prompt context profile:

* список candidate themes;
* `subjects`;
* `utility_mode`;
* `subject_continuity_policy`;
* критерии похожести тем.

Composition note: deduplicator не должен получать полный художественный prompt, если ему достаточно компактного смыслового контекста.

Usually not needed:

* полный body всех style layers;
* image layers;
* подробные примеры художественного тона.

### 4.3 Scorer

Prompt context profile:

* candidate texts;
* normalized params;
* score components;
* hard gates;
* краткое summary релевантных layers;
* constraints из metadata и body.

Composition note: scorer получает criteria-oriented context, а не creative generation context.

### 4.4 Validator

Prompt context profile:

* один candidate text;
* `normalized_request`;
* hard constraints;
* safety constraints;
* age constraints;
* truth mode constraints;
* utility constraints;
* subject continuity rules;
* output contract для validation result.

Composition note: validator получает constraints-oriented context. Подробные правила validation result описаны в `STAGE_CONTRACTS.md`.

### 4.5 Refiner

Prompt context profile:

* исходный candidate text;
* validator issues;
* immutable fields;
* hard constraints;
* ограниченный набор prompt layers, нужных для исправления;
* output contract для revised candidate.

Composition note: refiner получает repair-oriented context. Он должен видеть immutable fields, но не обязан получать полный creative context, если проблема локальная.

### 4.6 Approved Text Selector

Prompt context profile:

* ranked candidates;
* validation results;
* requested `output_count`;
* fallback policy при нехватке approved texts.

Composition note: selector получает selection-oriented context. Обычно ему не нужны полные prompt bodies style/entity layers, если ranking и validation summaries уже содержат нужные сигналы.

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
