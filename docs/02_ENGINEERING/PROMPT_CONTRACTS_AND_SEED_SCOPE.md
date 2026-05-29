# PROMPT_CONTRACTS_AND_SEED_SCOPE.md

# Контракты prompt-базы и минимальный seed scope

Статус: навигационный документ.

Этот файл является точкой входа в набор контрактов для prompt-базы, prompt lookup, prompt composition и второго этапа генерации текстов. Подробные контракты вынесены в `docs/02_ENGINEERING/contracts/`, чтобы каждый раздел можно было читать и развивать отдельно.

Документ не заменяет `TARGET_ORCHESTRATION_LOGIC.md`. Он уточняет, какие данные и prompt assets нужны для реализации логики первого и второго этапов.

---

## 1. Что описывают эти контракты

Контракты отвечают на практические вопросы перед подготовкой seed prompts и реализацией нового контура:

* какие параметры должны выходить из первого этапа оркестрации;
* как описывать `.md` prompt layers;
* как система ищет подходящие prompt layers;
* что делать, если точного слоя нет;
* как из параметров и найденных слоёв собрать stage-specific prompt context;
* какие входы и выходы должны быть у stage второго этапа;
* какой минимальный набор prompt-файлов нужен для первых прогонов;
* какие smoke/golden scenarios нужны для регрессий.

---

## 2. Карта документов

| Документ | Зачем читать |
| --- | --- |
| `contracts/NORMALIZED_STATE_CONTRACT.md` | Контракт `normalized_request`, `subjects`, `is_character`, `character_profile`, `prompt_context`. |
| `contracts/PROMPT_FILE_CONTRACT.md` | Структура `.md` prompt layer: YAML metadata + prompt body contract. |
| `contracts/PROMPT_LOOKUP_CONTRACT.md` | Два режима поиска: metadata lookup при анализе запроса и execution lookup после нормализации. |
| `contracts/PROMPT_COMPOSITION_CONTRACT.md` | Как layers, hard constraints, soft preferences и unresolved details собираются в prompt context. |
| `contracts/STAGE_CONTRACTS.md` | Stage второго этапа: generator, deduplicator, scorer, validator, refiner, selector. |
| `contracts/SEED_SCOPE.md` | Минимальный набор seed prompts для первых прогонов. |
| `contracts/GOLDEN_SCENARIOS.md` | Smoke/golden scenarios для проверки логики и будущих регрессий. |
| `contracts/SCOPE_BOUNDARIES.md` | Что не входит в MVP-контур контрактов и не должно блокировать первые прогоны. |

Рекомендуемый порядок чтения:

1. `NORMALIZED_STATE_CONTRACT.md`
2. `PROMPT_FILE_CONTRACT.md`
3. `PROMPT_LOOKUP_CONTRACT.md`
4. `PROMPT_COMPOSITION_CONTRACT.md`
5. `STAGE_CONTRACTS.md`
6. `SEED_SCOPE.md`
7. `GOLDEN_SCENARIOS.md`
8. `SCOPE_BOUNDARIES.md`

---

## 3. Граница между бизнес-логикой и технической реализацией

`TARGET_ORCHESTRATION_LOGIC.md` фиксирует, что продукт должен делать с точки зрения пользователя и бизнес-процесса.

Контракты в этой папке фиксируют промежуточный слой:

```text
бизнес-логика
        │
        ▼
контракты данных и prompt assets
        │
        ▼
техническая реализация в LangGraph / Pydantic / PromptRegistry / PromptComposer
```

Техническая спецификация оркестратора должна позже описать:

* какие Pydantic-модели соответствуют этим контрактам;
* какие LangGraph-ноды создают и потребляют эти данные;
* где выполняется metadata lookup;
* где выполняется execution lookup;
* где собирается `prompt_context`;
* где сохраняются candidate texts, scores, validation results и approved texts.

---

## 4. Принцип эволюции

На MVP один агент может выполнять несколько stage или несколько видов scoring. Контракты при этом должны оставаться стабильными: если позже один агент будет разнесён на несколько нод, бизнес-логика и структура данных не должны ломаться.

Seed scope и golden scenarios являются рабочими документами. После появления реальных prompt-файлов они могут уточняться, но не должны исчезать полностью: golden scenarios должны стать основой smoke/regression проверки.
