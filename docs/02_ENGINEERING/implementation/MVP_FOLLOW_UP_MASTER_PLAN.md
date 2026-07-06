# DreamyDraw MVP Follow-Up — Master Plan

Status: **active backlog for lead → developer handoff**  
Last updated: 2026-07-03  
Audience: developers, project lead, technical reviewer

---

## 0. Как пользоваться этим документом

### 0.1 Назначение

Этот документ **не является финальной спецификацией реализации**.

Он фиксирует:

- контекст проекта и границы MVP;
- приоритетный backlog задач после Wave 11;
- формулировку **проблем** и **возможных направлений решения**;
- черновые acceptance criteria и open questions;
- что читать, а что сознательно не читать.

**Ожидаемый workflow для каждой задачи:**

```text
1. Прочитать §0 + §1 + Reading guide + свой § задачи
2. Провести дополнительный анализ кода/доков по задаче
3. Подготовить Implementation Plan (отдельный файл или PR-comment / doc)
4. Согласовать план с lead (+ technical reviewer при необходимости)
5. Реализовать
6. Обновить статус задачи в §7; новые продуктовые решения — через lead, при необходимости строка в §6 Changelog
```

### 0.2 Handoff разработчику (шаблон для чата)

```text
Задача: §3.X — <название>
Документ: docs/02_ENGINEERING/implementation/MVP_FOLLOW_UP_MASTER_PLAN.md
Прочитать: §0, §1, §2, §3.X
Перед кодом: прислать Implementation Plan на согласование
Owner: <имя>
Не трогать: <ссылка на out of scope задачи>
```

### 0.3 Статусы задач

| Status | Meaning |
|--------|---------|
| `draft` | Описана проблема, реализация не начата |
| `analysis` | Исполнитель изучает код/доки |
| `plan_review` | План реализации на согласовании |
| `in_progress` | Код / doc changes в работе |
| `done` | Acceptance выполнен, PR merged |
| `blocked` | Ждёт другую задачу или продуктовое решение |

---

## 1. Контекст проекта (кратко)

### 1.1 Продукт

**DreamyDraw** — генератор познавательно-развлекательного контента для детей **3–5 лет** (в vision — более точные возрастные ступени). Текущий MVP-формат: **короткая иллюстрированная история** (текст + вопросы; картинки — за пределами Stage 1–2 MVP).

Ключевые оси контента:

- **`truth_mode`**: Правда / Миф / Сказка
- стиль текста и (в будущем) картинки
- в перспективе — `utility_mode` (повествование / поучительное / английский)

### 1.2 Два контура в репозитории

| Контур | Entry point | Scope | Статус |
|--------|-------------|-------|--------|
| **Stage 1–2 MVP (целевой)** | `scripts/run_stage1_2_mvp.py` → `Stage1_2Orchestrator` | LangGraph: интерпретация запроса → `approved_texts` | **активная разработка** |
| **Legacy** | `main.py` → `Orchestrator` | Старый pipeline: plan → text → image | **deprecated, удаление — задача §3.7** |

Все задачи этого backlog относятся к **Stage 1–2 MVP**, если не указано иное.

### 1.3 Текущая граница MVP

- **In scope:** Stage 1 interpretation, prompt registry/lookup/composition, Stage 2 text pipeline до `approved_texts`
- **Out of scope:** image generation, animation, Stage 3, legacy CLI `fast/check` как целевой продукт

Опорные Wave-документы с описанием найденных дефектов и manual matrix:

- `WAVE_11_FINAL.md`
- `WAVE_11_FOLLOW_UP_DEVELOPMENT_TASKS.md`

### 1.4 Почему этот backlog

После Wave 11 подключили real LLM для Stage 2. Автотесты на mock/scripted executors проходят, но **ручные прогоны** показали расхождение docs ↔ code ↔ ожидания продукта.

Задачи §3 сгруппированы по этим темам (подробности — в каждой задаче, не здесь):

| Тема | Задача |
|------|--------|
| Доки обещают одно, код/lead — другое (defaults, scope Stage 1) | §3.1, позже §3.6 |
| Запрос пользователя не превращается в prompt layers (стиль, параметры) | §3.2 |
| `truth_mode=TRUTH` в state, но текст на Stage 2 сказочный | §3.3 |
| Нет лимита длины approved text | §3.4 |
| Нужен structured manual pass после фиксов | §3.5 |
| Legacy мешает ориентироваться в репо | §3.7 |

Конкретные продуктовые решения (default режима, возраст, персонажи в TRUTH и т.д.) **не сводятся в одну таблицу** — они появляются в Problem / Open questions соответствующей задачи и фиксируются в Implementation Plan после согласования с lead.

---

## 2. Reading guide

### 2.1 Обязательно (все исполнители, ~30–45 мин)

| Документ | Зачем |
|----------|-------|
| `docs/01_PRODUCT/WHAT_IS_DREAMYDRAW.md` | Продукт «как для пользователя» |
| `docs/01_PRODUCT/PRODUCT_VISION.md` | Настройки, сценарии, принципы (после §3.1 — проверить defaults) |
| `docs/02_ENGINEERING/TARGET_ORCHESTRATION_LOGIC.md` | §4 Stage 1, §5 Stage 2 — бизнес-логика |
| `docs/02_ENGINEERING/ORCHESTRATOR_SPEC.md` | Индекс; далее `orchestration/00_OVERVIEW.md` |
| `docs/02_ENGINEERING/orchestration/01_STAGE_1_INTERPRETATION.md` | Целевые ноды Stage 1 |
| `docs/02_ENGINEERING/orchestration/02_STAGE_2_TEXT_PIPELINE.md` | Целевые ноды Stage 2 |
| `implementation/WAVE_11_FINAL.md` | Known issues + manual test appendix |
| `implementation/WAVE_11_FOLLOW_UP_DEVELOPMENT_TASKS.md` | Chukovsky + TRUTH defects |

### 2.2 По задаче

| Задача | Дополнительно читать |
|--------|----------------------|
| §3.1 Doc mini-pass | `PRODUCT_VISION.md` §2 defaults; `CONFIGURATION_CONSTANTS.md` при необходимости |
| §3.2 Stage 1 | `contracts/NORMALIZED_STATE_CONTRACT.md`, `PROMPT_LOOKUP_CONTRACT.md`, `src/core/nodes/stage1.py`, `src/core/prompts/lookup.py`, `prompts/.../CHUKOVSKY_STYLE.md` |
| §3.3 Stage 2 TRUTH | `src/core/stage2_llm_executor.py`, `src/core/nodes/stage2.py`, `prompts/truth_modes/TRUTH/BASE.md`, entity layers (FOX, HEDGEHOG, …) |
| §3.4 Length | `IMPLEMENTATION_PLAN_3_4_STAGE2_LENGTH_ENFORCEMENT.md`, `WAVE_12_STAGE2_LENGTH_LIMITS_TASK.md`, age layers в `prompts/ages/` |
| §3.5 Manual tests | `STAGE_1_2_MVP_RUNBOOK.md`, `STAGE_1_2_MVP_ACCEPTANCE_CHECKLIST.md` |
| §3.6 Doc alignment | `ARCHITECTURE.md`, `ROADMAP.md`, `MODULES.md` — сверка с фактом |
| §3.7 Legacy cleanup | `main.py`, `src/core/orchestrator.py`, `implementation/WAVE_0_LEGACY_POLICY.md` |

### 2.3 Не читать / не тратить время (пока)

| Путь | Причина |
|------|---------|
| `docs/03_PROMPTS/` | Legacy artifact; планируется перенос/удаление (§3.7) |
| `docs/99_BACKUP/` | Архив, не source of truth |
| Legacy orchestrator code | Только для §3.7 audit; не использовать как образец для Stage 1–2 |

### 2.4 Код — минимальный orientation

```text
scripts/run_stage1_2_mvp.py     # CLI Stage 1–2 MVP
src/core/stage1_2_orchestrator.py
src/core/nodes/stage1.py        # Stage 1 (сейчас regex/heuristics)
src/core/nodes/stage2.py        # Stage 2 graph nodes
src/core/stage2_llm_executor.py # Real LLM Stage 2
src/core/prompts/               # registry, lookup, composer
prompts/                        # seed prompt layers (YAML + body)
tests/helpers/stage1_2_golden.py
tests/integration/test_stage1_2_*.py
```

---

## 3. Backlog (приоритетный порядок)

### Зависимости (overview)

```text
§3.1 Doc mini-pass ──────────────┐
                                 ├──► §3.5 Manual tests ──► §3.6 Doc alignment ──► §3.7 Legacy
§3.2 Stage 1 interpretation ───┤
§3.3 Stage 2 TRUTH ────────────┤
§3.4 Length limits ────────────┘

§3.2 и §3.3 могут идти параллельно разными исполнителями после §3.1 (или параллельно с §3.1).
§3.5 — только после §3.2–§3.4 (минимум Block 1 из WAVE_11).
```

---

### §3.1 Doc mini-pass

| Field | Value |
|-------|-------|
| **Status** | `done` |
| **Owner** | Dev A (docs / любой исполнитель без deep code) |
| **Estimate** | 0.5–1 day |
| **Blocks** | Семантическая ясность для §3.2+; не блокирует код жёстко |

#### Problem

Продуктовые и engineering-доки расходятся с тем, как MVP **фактически** работает и с тем, что lead хочет зафиксировать на ближайший sprint:

- в `PRODUCT_VISION.md` default `truth_mode` = **Сказка**, тогда как для MVP lead ориентируется на **Правду (TRUTH)** как основной режим — это нужно явно согласовать в тексте доков;
- не описано явно: seed layers только для возрастов **3 и 5**, а при отсутствии возраста в запросе код ставит **5** (`stage1.py`);
- в orchestration spec Stage 1 описан как LLM `input_analysis`, в коде — regex/heuristics; без ремарки разработчики будут ожидать другое.

#### Possible approaches (не финально)

**A. Minimal diff (рекомендуется для MVP)**  
Точечные правки 2–4 файлов: defaults, MVP scope note, ссылка на этот master plan.

**B. Расширенный pass сейчас**  
Сразу править `ARCHITECTURE.md`, `ROADMAP.md` — **не рекомендуется**; перенести в §3.6.

#### Draft acceptance criteria

- [x] `PRODUCT_VISION.md`: default `truth_mode` = Правда / TRUTH
- [x] Зафиксировано: MVP seed ages **3, 5**; при отсутствии возраста в запросе → **5**
- [x] Краткая ремарка: Stage 1 MVP = deterministic extraction + registry matching; полный LLM-интерпретатор — follow-up
- [x] Ссылка на `MVP_FOLLOW_UP_MASTER_PLAN.md` из runbook или implementation index (опционально)

#### Out of scope

- Полный аудит всех docs
- Правки `docs/03_PROMPTS`, legacy backup
- Изменения кода

#### Open questions

- Нужна ли одна строка в `WHAT_IS_DREAMYDRAW.md` про default «Правда»?

#### Deliverable before code

**Implementation Plan** (краткий): список файлов и предлагаемых diff-ов на review.

---

### §3.2 Stage 1 — интерпретация пользовательского запроса

| Field | Value |
|-------|-------|
| **Status** | `done` |
| **Owner** | Dev B (orchestration / backend) |
| **Estimate** | 8–12 days (Уровень B: cascade + RapidFuzz + LLM style tail) |
| **Plan** | `implementation/IMPLEMENTATION_PLAN_3_2_STAGE1_INTERPRETATION.md` (**approved** 2026-07-03) |
| **Depends on** | §3.1 желательно; не блокирует старт анализа |
| **Blocks** | §3.5 manual tests (Chukovsky, style cases) |

#### Problem

Stage 1 извлекает параметры через **regex/heuristics** (`src/core/nodes/stage1.py`). Registry содержит prompt layers (напр. `CHUKOVSKY_STYLE`), но **пользовательские фразы не доходят до state**:

```text
Запрос: «… в стиле чуковского»
Ожидание: CHUKOVSKY_STYLE in resolved_layers
Факт (Wave 11): substyle None, layer отсутствует
```

Связанные подпроблемы в scope этой задачи:

- matching style/substyle/reference labels;
- unsupported vs missed style (см. §3.2.1);
- в режиме TRUTH животное из запроса («про лису») сейчас помечается как персонаж (`is_character=true`), хотя продуктово это скорее **тема/ subject**, не герой с характером — поведение нужно согласовать и поправить (см. Open questions).

#### §3.2.1 Unsupported / missed styles (в scope §3.2, не отдельный этап)

| Ситуация | Текущее поведение | Целевое MVP (draft) |
|----------|-------------------|---------------------|
| «строго в стиле Дисней» | clarification, Stage 2 не стартует | сохранить |
| «акварельное настроение» (мягко) | soft_preferences, генерация идёт | сохранить |
| «в стиле чуковского» (есть в registry) | **игнорируется** | **resolve CHUKOVSKY_STYLE** |
| «строго в стиле X», X нет в registry | частично через hard_details | clarification + честное сообщение |

#### Possible approaches (не финально)

**Phase 1 — Must (MVP gate)**

```text
raw text
  → normalize
  → [keep] regex signals: truth_mode, utility, age, subjects, teaching topics
  → phrase extraction: «в стиле …», «как у …», «по …», «как …»
  → registry match: exact alias → contains → (optional) fuzzy / RapidFuzz
  → applicability check (truth_mode, content_format, age)
  → write substyle / lookup_hints / resolved_layers
```

**Phase 2 — Should**

- Generalized matching для reference_labels / substyles (не только Chukovsky)
- Ambiguity: top-2 candidates близко → clarification с options из registry metadata
- LLM fallback **только** для disambiguation среди **известных** registry candidates

**Phase 3 — Later (отдельный backlog)**

- Полный LLM `input_analysis` с confidence по всем base params (TARGET §4.5)
- Пакетное уточнение неполных запросов

**`is_character` для TRUTH (draft, на согласование в Implementation Plan):**

- TRUTH + animal без явного запроса персонажа → `is_character = false`
- Явные маркеры («бельчонок Тим», «назови его…») — отдельная ветка интерпретации
- Проверить downstream: gate `character_consistency` не должен требовать persona там, где её нет

#### Draft acceptance criteria (Phase 1 minimum)

- [x] `Сделай 2 сказки про лису для 3 лет в стиле чуковского` → `FAIRY_TALE`, `target_age=3`, `CHUKOVSKY_STYLE` in resolved layers
- [x] Typos/variants из `WAVE_11_FOLLOW_UP` (≥3) — unit tests
- [x] `2 правдивых истории про лису` → `TRUTH` без регрессии
- [x] `2 сказки про лису` без возраста → `target_age=5`
- [x] Unsupported hard style → clarification, no `approved_texts` until resume
- [x] No fabricated layer ids
- [x] TRUTH + «про лису» → subject with `is_character=false` (unless explicit character request)
- [x] `pytest` integration/unit green; CI без external LLM

#### Key files (orientation)

- `src/core/nodes/stage1.py`
- `src/core/prompts/lookup.py`
- `src/core/prompts/registry.py`
- `prompts/truth_modes/FAIRY_TALE/styles/reference_labels/CHUKOVSKY_STYLE.md`
- `tests/integration/test_stage1_2_golden_scenarios.py`
- `tests/integration/test_stage1_2_negative_scenarios.py`

#### Out of scope

- Stage 2 TRUTH enforcement (§3.3)
- Text length (§3.4)
- Legacy removal (§3.7)
- Full LLM interpreter all fields (Phase 3)

#### Open questions for Implementation Plan

- RapidFuzz в dependencies — да/нет для Phase 1?
- Где жить phrase extractor — отдельный модуль vs `lookup.py`?
- Формат поля: `substyle` string vs resolved reference label id?
- TRUTH + «про лису»: всегда `is_character=false` или уточнять у пользователя?

#### Deliverable before code

**Implementation Plan** with: proposed architecture diagram, phase split, test matrix, risk notes.

---

### §3.3 Stage 2 — удержание режима правды (TRUTH)

| Field | Value |
|-------|-------|
| **Status** | `done (code + CI)` — manual `--executor llm` TRUTH checklist pending (runbook) |
| **Owner** | Dev C |
| **Estimate** | 3–5 days |
| **Depends on** | Желательно после/параллельно с §3.2 (`is_character`); анализ можно начать сразу |
| **Blocks** | §3.5 manual tests (requests #2, #8, #13) |

#### Problem

Stage 1 корректно ставит `truth_mode=TRUTH` и resolved layers (`TRUTH_BASE`, `TRUTH_ANIMAL_FOX`, …), но **approved texts** на real LLM содержат сказочные клише:

```text
«Жила-была лиса…», имена, сундуки, anthropomorphic social logic
```

Wave 11 формулировка:

```text
System knows which rule layer was selected,
but generated result does not always behave as if that rule was active.
```

Дополнительный defect (P5): validator `accepted` + non-empty `issues` — **уже закрыт** в executor + unit tests.

#### Approved approach (lead 2026-07-04)

**A. Prompt grounding (PR-1)** — universal  
Generator / scorer / validator / refiner: `include_bodies_runtime` + `layer_grounding` in `_build_prompt` для **всех** режимов.

**B. Scorer / validator hardening (PR-2)**  
TRUTH task strings; `character_consistency` auto-pass без character; `_normalize_score` missing gate → `unknown`.

**C. Deterministic post-check (PR-3 — approved)**  
Categories 1–2: fairy opening + direct animal speech → `needs_revision`. Cat 3 time-permitting; Cat 4 defer.

**D. Validation contract**  
Strict: any non-empty `issues` → `needs_revision` — **не менять** (already in code).

#### Acceptance criteria

- [ ] Request `2 правдивых истории про лису для 5 лет` with `--executor llm` → approved texts **без** сказочного framing — **manual gate** (runbook T1)
- [x] `truth_fit` fail → candidate не попадает in approved (mock + integration: `test_stage1_2_truth_enforcement.py`, post-check)
- [x] Validator: `accepted` + non-empty `issues` → impossible (unit test) — **already covered**
- [x] Golden scenario `test_truth_hedgehog_winter_stories_reach_approved_texts` без регрессии
- [x] Refiner preserves theme/subject while fixing truth violations (golden + LenientStage2Executor)

#### Out of scope

- Style matching (§3.2)
- Length limits (§3.4)
- Teaching utility deep pass (unless regression)

#### Resolved (lead 2026-07-04)

See [`IMPLEMENTATION_PLAN_3_3_STAGE2_TRUTH_ENFORCEMENT.md`](IMPLEMENTATION_PLAN_3_3_STAGE2_TRUTH_ENFORCEMENT.md) §7:

- PR-3 post-check in MVP — **yes** (categories 1–2)
- Marker list §3.4.C — **approved** (+ runbook appendix PR-5)
- Universal grounding — **PR-1 one PR**
- No body token cap in MVP; measure on 3 manual sessions

#### Deliverable before code

**Implementation Plan**: [`IMPLEMENTATION_PLAN_3_3_STAGE2_TRUTH_ENFORCEMENT.md`](IMPLEMENTATION_PLAN_3_3_STAGE2_TRUTH_ENFORCEMENT.md) — **`approved`** (2026-07-04).

**Implementation:** PR-1..5 complete. See [`IMPLEMENTATION_PLAN_3_3_STAGE2_TRUTH_ENFORCEMENT.md`](IMPLEMENTATION_PLAN_3_3_STAGE2_TRUTH_ENFORCEMENT.md).

**Remaining gate:** manual TRUTH checklist in [`STAGE_1_2_MVP_RUNBOOK.md`](STAGE_1_2_MVP_RUNBOOK.md) § TRUTH manual checklist (`--executor llm` T1–T2).

---

### §3.4 Ограничения длины итогового текста

| Field | Value |
|-------|-------|
| **Status** | `done (code + CI)` |
| **Owner** | Dev C |
| **Estimate** | 1–2 days |
| **Depends on** | §3.3 `done`; before §3.5 |
| **Blocks** | §3.5 (length observations in manual report) |
| **Spec** | `implementation/IMPLEMENTATION_PLAN_3_4_STAGE2_LENGTH_ENFORCEMENT.md` |
| **Delegation** | `implementation/WAVE_12_STAGE2_LENGTH_LIMITS_TASK.md` |

#### Problem

Approved texts могут быть **несколько абзацев**; продукт ожидает **короткий текст**. Hard gate / refiner policy отсутствует. Age layers задают сложность качественно, без числового enforcement.

#### Approved decisions (lead 2026-07-06)

| # | Решение |
|---|---------|
| 1 | Единица: **предложения** в `text`; `questions` вне лимита |
| 2 | **Age 3:** 3–4 предложения; **Age 5:** 3–5; min 3 жёстко |
| 3 | Сложность фраз: расширить `AGE_3` / `AGE_5` (правила + примеры), не новые layer-файлы |
| 4 | Числа из **`AGE_STORY_LENGTH_POLICIES`** (расширяемый dict по `target_age`) |
| 5 | Подход **C:** age prompts + validator LLM + deterministic post-check + refiner |
| 6 | Issue types: `text_overlength`, `text_underlength`, `sentence_too_complex` |
| 7 | Post-check по образцу §3.3 TRUTH (`apply_length_post_check`) |

#### Acceptance criteria

- [x] Policy dict + composer injection `length_policy`
- [x] Age layer bodies updated (complexity + compact examples)
- [x] Deterministic post-check flags over/under length by age
- [x] Refiner shortens without changing theme/subject
- [x] Unit test: 8-sentence mock → revision; age 3 + 5 sentences → fail
- [x] Documented in runbook (§3.5 prep) + `CONFIGURATION_CONSTANTS.md`

#### Out of scope

- Character/byte limits; image text overlay length
- Age ladder 3.5 / 4 / 4.5 (добавление = новая запись в dict)
- Prompt budget / grounding compression (отдельная задача)

#### Gate before code

Lead ok на **Implementation Plan §3.4** (Phase 0). Код — Phase 1, PR-1..6 в плане.

---

### §3.5 Детальные ручные тесты

| Field | Value |
|-------|-------|
| **Status** | `draft` |
| **Owner** | Lead + any dev (execution); QA-style report |
| **Estimate** | 1–2 days |
| **Depends on** | §3.2, §3.3, §3.4 minimum (Wave 11 Block 1) |

#### Problem

Automated golden tests use **scripted/mock executors** — не ловят real LLM behavior (TRUTH, length, style). Нужен structured manual pass.

#### Source

`WAVE_11_FINAL.md` — Appendix (15 requests).

#### Procedure (draft)

For each request record:

- request text;
- command: `venv/bin/python scripts/run_stage1_2_mvp.py "<request>" --executor llm --debug-llm` (when LLM available);
- `session_id`;
- `completion_status`, `approved_count`;
- key `normalized_request` fields;
- `resolved_layers` ids;
- snippet / issues in `approved_texts`;
- pass/fail vs expectation;
- follow-up ticket if fail.

#### Draft acceptance criteria

- [ ] All 15 appendix requests executed and recorded
- [ ] Report stored: `implementation/WAVE_11_MANUAL_TEST_REPORT.md` (or agreed location)
- [ ] `STAGE_1_2_MVP_ACCEPTANCE_CHECKLIST.md` updated with checkmarks / known gaps
- [ ] No silent failures: TRUTH requests documented with truth-fit assessment

#### Out of scope

- Fixing failures found (separate tickets)
- Image pipeline tests

---

### §3.6 Doc alignment (полный проход)

| Field | Value |
|-------|-------|
| **Status** | `draft` |
| **Owner** | Dev A or tech writer + dev review |
| **Estimate** | 2–4 days |
| **Depends on** | §3.5 complete |

#### Problem

После кодовых изменений часть engineering docs описывает **legacy** или **target**, не **actual MVP**:

- `ARCHITECTURE.md` — legacy planner pipeline;
- `ROADMAP.md` — mixed checklist;
- possible drift in orchestration specs vs `stage1.py` behavior.

#### Possible approaches

**Inventory → gap list → prioritized fixes**

1. List docs claiming "current behavior"
2. Compare to Stage 1–2 MVP code + manual test report
3. Update or mark `Historical / legacy` sections
4. Add `Current MVP` section pointing to `run_stage1_2_mvp.py`

#### Draft acceptance criteria

- [ ] Gap inventory document or section in this master plan
- [ ] `ARCHITECTURE.md` distinguishes legacy vs Stage 1–2 MVP
- [ ] Runbook matches actual CLI flags and executors
- [ ] No doc promises full LLM Stage 1 if not implemented
- [ ] Defaults из §3.1 (truth, age) отражены везде, где в docs упоминаются «значения по умолчанию»

#### Out of scope

- Rewriting entire TARGET_ORCHESTRATION_LOGIC
- Product marketing copy overhaul

---

### §3.7 Удаление legacy (code, prompts, docs)

| Field | Value |
|-------|-------|
| **Status** | `draft` |
| **Owner** | Senior dev + lead approval |
| **Estimate** | 3–5 days (after audit) |
| **Depends on** | §3.5 green enough; §3.6 inventory |

#### Problem

Два orchestrator, duplicate prompts (`docs/03_PROMPTS` vs `prompts/`), legacy code confuse contributors and tests.

#### Possible approaches

**Phased deletion**

1. **Audit:** list legacy entry points, imports, tests still using legacy
2. **Deprecate:** README notice, delete guards in CI
3. **Remove:** `main.py` legacy path? `Orchestrator`, `docs/03_PROMPTS`, `99_BACKUP` — only after confirm nothing needed for Stage 3 reference
4. **Verify:** full pytest, smoke `run_stage1_2_mvp.py`

#### Draft acceptance criteria

- [ ] Audit doc: what was removed and why
- [ ] Single documented CLI entry for MVP
- [ ] `pytest -q` green
- [ ] No broken links in active docs (or redirects noted)

#### Out of scope

- Stage 3 implementation
- Migrating useful legacy prompts without review

#### Open questions

- Keep `main.py` as thin redirect to Stage 1–2 CLI?
- Archive repo tag before deletion?

---

## 4. Manual test appendix (reference)

Source: `WAVE_11_FINAL.md`. Execute in §3.5.

| # | Request |
|---|---------|
| 1 | `Сделай 2 сказки про лису для 5 лет` |
| 2 | `Сделай 2 правдивые истории про лису для 5 лет` |
| 3 | `Сделай 2 сказки про лису` |
| 4 | `2 сказки` |
| 5 | `Сделай сказку про лису для 5 лет в стиле Чуковского` |
| 6 | `Сделай сказку про лису для 5 лет строго в стиле Дисней` |
| 7 | `Сделай сказку про лису для 5 лет в акварельном настроении` |
| 8 | `Сделай правдивую историю про лису для 5 лет, обязательно чтобы она летала на волшебном ковре` |
| 9 | `Сделай 2 поучительные сказки про лису и переход через дорогу для 5 лет` |
| 10 | `Сделай поучительную историю про незнакомца и конфету для ребёнка 5 лет` |
| 11 | `Сделай 3 истории про лису, зайца и белку зимой, чтобы герои не исчезали` |
| 12 | `Сделай историю про бельчонка Тима, он смелый и любит жёлуди, для 5 лет` |
| 13 | `Сделай правдивую историю про попугая какаду для 5 лет` |
| 14 | `Сделай мягкую мифологическую историю про солнце и ветер для ребёнка 5 лет` |
| 15 | `Сделай 2 сказки про лису для 5 лет` — run 3×, compare diversity |

---

## 5. Implementation Plan template (for developers)

Copy and fill before coding:

```markdown
# Implementation Plan — §3.X <title>

Author: 
Date:
Status: draft | under_review | approved

## 1. Problem understanding
(confirm alignment with master plan §3.X)

## 2. Current state analysis
(files read, behavior observed)

## 3. Proposed solution
(chosen approach and why; rejected alternatives)

## 4. Phase split / PR strategy

## 5. Test plan
(unit, integration, manual if any)

## 6. Risks and open questions

## 7. Doc updates needed

## 8. Estimated effort
```

---

## 6. Changelog

| Date | Change |
|------|--------|
| 2026-07-03 | Initial master plan |
| 2026-07-03 | §1.4: backlog context вместо decision log; решения перенесены в задачи |
| 2026-07-03 | §3.1 done: MVP defaults (TRUTH, ages 3/5, Stage 1 heuristics note) в product/runbook/orchestration docs |
| 2026-07-04 | §3.2 done: Stage 1 style cascade (registry + RapidFuzz + heuristic tail), TRUTH `is_character`, tests |
| 2026-07-04 | §3.3 done (code + CI): Stage 2 layer grounding, TRUTH tasks, post-check cat 1–2, LenientStage2Executor tests; manual llm gate in runbook |

---

## 7. Task status board

| Task | Owner | Status |
|------|-------|--------|
| §3.1 Doc mini-pass | Dev A | `done` |
| §3.2 Stage 1 interpretation | Dev B | `done` |
| §3.3 Stage 2 TRUTH | Dev C | `done (code + CI)` |
| §3.4 Length limits | Dev C | `done (code + CI)` |
| §3.5 Manual tests | TBD | `draft` |
| §3.6 Doc alignment | TBD | `draft` |
| §3.7 Legacy cleanup | TBD | `draft` |
