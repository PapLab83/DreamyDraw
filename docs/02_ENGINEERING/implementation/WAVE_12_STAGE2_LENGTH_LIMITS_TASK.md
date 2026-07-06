# Wave 12 Task — §3.4 Stage 2 length and sentence-complexity enforcement

Status: **done (code + CI)**.  
Owner: **Dev C** (same as §3.2 / §3.3).  
Estimate: **1–2 dev-days** after plan approval.

---

## Обращение к разработчику (copy-paste)

Привет!

Следующая задача в цепочке Stage 1–2 MVP — **§3.4: ограничение длины и сложности итогового текста**.

**Полный план работ (единый источник правды):**  
[`IMPLEMENTATION_PLAN_3_4_STAGE2_LENGTH_ENFORCEMENT.md`](./IMPLEMENTATION_PLAN_3_4_STAGE2_LENGTH_ENFORCEMENT.md)

**Зависимости:** §3.3 закрыт (code + CI). Паттерн post-check — как `stage2_truth_post_check.py`.

**Как работать — две фазы:**

1. **Фаза 0 (до кода):** прочитай план §3.4, проверь что решения lead согласованы, добейся **ok от lead** на Implementation Plan, синхронизируй master plan §3.4 и связанные доки. **Код не начинать до gate.**
2. **Фаза 1:** реализация по PR-1..6 из плана (policy dict → age layers → prompts → post-check → tests → docs).

**Ключевые решения (не переоткрывать без lead):**

- Считаем **предложения** в `text`; `questions` вне лимита.
- **3 года:** 3–4 предложения; **5 лет:** 3–5; min 3 жёстко.
- Сложность фраз — через **расширение** `AGE_3` / `AGE_5` (правила + короткие примеры), не новые layer-файлы.
- Числа min/max — из **словаря политик** в коде, подставляются в prompt.
- Enforcement: age prompts + validator LLM + **deterministic post-check** + refiner (подход C).

**DoD:** post-check режет over/under length по возрасту; тесты green; master plan §3.4 → `done (code + CI)`.

Если в плане что-то не сходится с кодом — правь план первым, потом код.

---

## Goal

Enforce per-age story length and sentence-complexity expectations on Stage 2 so `approved_texts` match product rules:

```text
Age 3: 3–4 short sentences in text
Age 5: 3–5 sentences in text (moderate complexity allowed)
```

## Background

Read before Phase 0:

1. [`IMPLEMENTATION_PLAN_3_4_STAGE2_LENGTH_ENFORCEMENT.md`](./IMPLEMENTATION_PLAN_3_4_STAGE2_LENGTH_ENFORCEMENT.md) — **primary spec**
2. [`IMPLEMENTATION_PLAN_3_3_STAGE2_TRUTH_ENFORCEMENT.md`](./IMPLEMENTATION_PLAN_3_3_STAGE2_TRUTH_ENFORCEMENT.md) — post-check pattern
3. [`MVP_FOLLOW_UP_MASTER_PLAN.md`](./MVP_FOLLOW_UP_MASTER_PLAN.md) §3.4
4. `prompts/ages/3/BASE.md`, `prompts/ages/5/BASE.md`
5. `src/core/stage2_truth_post_check.py`, `src/core/nodes/stage2.py`
6. `docs/02_ENGINEERING/CONFIGURATION_CONSTANTS.md`

## Scope

### Allowed

- `AgeStoryLengthPolicy` dict and lookup helpers
- `stage2_length_post_check.py` + wiring in `stage2.py`
- Updates to `AGE_3` / `AGE_5` prompt bodies
- Composer / executor `length_policy` injection
- Validator/refiner prompt checklist updates
- Unit and integration tests (no external LLM)
- Doc updates listed in Implementation Plan §10

### Not allowed

- Character/byte limits
- New `LENGTH_*` prompt layer files
- Per-style length exceptions (Chukovsky) in this wave
- Prompt budget / grounding compression project
- Full §3.5 manual pass (only runbook row for length — prep for later)

## Phase 0 — documents (gate before code)

| Step | Deliverable |
|------|-------------|
| Review Implementation Plan §3.4 with lead | Approved plan (checkbox §11) |
| Update `MVP_FOLLOW_UP_MASTER_PLAN.md` §3.4 | Aligned with approved decisions |
| Update `CONFIGURATION_CONSTANTS.md` | Policy dict documented |

**Exit criteria:** lead ok on Implementation Plan; status `plan_review` → `approved` → start PR-1.

## Phase 1 — implementation

Follow PR table in Implementation Plan §6:

```text
PR-1 policy module
PR-2 age layers + composer injection
PR-3 validator/refiner prompts
PR-4 length post-check + wiring
PR-5 integration tests
PR-6 docs + master plan status
```

## Acceptance criteria

- [ ] `AGE_STORY_LENGTH_POLICIES` for ages `"3"` and `"5"` with extensible dict design
- [ ] Numeric limits visible in Stage 2 LLM payload (`length_policy`)
- [ ] Age layer bodies include complexity rules + compact sentence examples
- [ ] `apply_length_post_check` downgrades validator `accepted` on over/under length
- [ ] Refiner can repair overlength without changing theme/subject (tested)
- [ ] §3.3 TRUTH regressions still green
- [ ] `venv/bin/pytest -q` green without external LLM
- [ ] Master plan §3.4 status → `done (code + CI)`

## Definition of Done

Same as Implementation Plan §12.

## After this wave

- §3.5 structured manual pass (TRUTH + length + style observations)
- Deferred: prompt token budget, image overlay length, age ladder 3.5/4/4.5
