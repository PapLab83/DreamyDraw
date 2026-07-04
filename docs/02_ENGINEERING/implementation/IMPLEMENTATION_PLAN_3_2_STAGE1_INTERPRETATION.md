# Implementation Plan — §3.2 Stage 1 — интерпретация пользовательского запроса

Author: Dev B  
Date: 2026-07-03  
Status: **done**  
Review: lead + tech reviewer (2026-07-03)  
Closed: 2026-07-04 (merged; heuristic style tail, no external LLM in CI)

---

## 1. Problem understanding

Stage 1 MVP (`input_analysis` → … → `candidate_layer_resolution`) извлекает базовые параметры через regex/heuristics, но **не связывает пользовательские фразы о стиле с PromptRegistry**. Главный дефект Wave 11:

```text
Запрос: «Сделай 2 сказки про лису для 3 лет в стиле чуковского»
Ожидание: CHUKOVSKY_STYLE in resolved_layers
Факт:     substyle=None, слой отсутствует
```

Связанные проблемы в scope §3.2:

| # | Проблема | Статус в коде |
|---|----------|---------------|
| P1 | Style/substyle/reference labels не матчатся | **Broken** — нет phrase extraction; `_SUPPORTED_LAYER_IDS` не содержит `CHUKOVSKY_STYLE` |
| P2 | Unsupported vs missed style policy (§3.2.1) | **Partial** — Disney/impossibility работает; «строго X» без registry — через generic `hard_details` |
| P3 | TRUTH + «про лису» → `is_character=true` | **Wrong default** — все животные создаются с `is_character=True` |
| P4 | Defaults TRUTH / age 5 | **OK** — регрессию сохранить |

Out of scope §3.2: Stage 2 TRUTH enforcement (§3.3), length (§3.4), legacy (§3.7).

**Отдельный epic (не §3.2):** полный LLM `input_analysis` по TARGET §4 — confidence по всем полям, batch clarification («про ёжика»), preview и т.д. Дополняет каскад на low-confidence / incomplete запросах, **не заменяет** regex + fuzzy fast path.

---

## 2. Current state analysis

### 2.1 Файлы и поведение

| Компонент | Наблюдение |
|-----------|------------|
| `stage1.py` `_extract_normalized_request` | Regex для truth/utility/age/subjects; substyle только для `russian_folk_tale` и `myth_soft`; **нет** «в стиле X» |
| `stage1.py` `_SUPPORTED_LAYER_IDS` | Hardcoded map ~30 id; substyles: `myth_soft`, `naturalistic_animal_story`, `russian_folk_tale` — **нет CHUKOVSKY** |
| `stage1.py` `_add_subject` | Все вызовы для fox/hedgehog/… передают `is_character=True` |
| `stage1.py` unsupported policy | `_UNSUPPORTED_RE` (Disney/…), `_SOFT_STYLE_RE` + «строго» → `hard_details`; soft mood → `soft_preferences` |
| `lookup.py` | Exact/contains match по `user_terms`; **не вызывается** с извлечёнными style phrases из текста |
| `registry.py` | 43 layers, 5 substyles; `by_alias` index есть, но Stage 1 его не использует для free-text |
| `CHUKOVSKY_STYLE.md` | Aliases: `в стиле Чуковского`, `как у Чуковского`, `чуковский`, `Chukovsky`; `applies_to.truth_modes: [FAIRY_TALE]` |

### 2.2 Wave 11 reference session

```text
session_id: 613742b6-fa7a-49fd-940f-e25df474f20d
request:    Сделай 2 сказки про лису для 3 лет в стиле чуковского.
state:      truth_mode=FAIRY_TALE, target_age=3, substyle=None, no CHUKOVSKY_STYLE
```

Root cause: цепочка обрывается **до** lookup — фраза «в стиле чуковского» никогда не попадает в `user_terms` / `request.substyle`.

### 2.3 Что уже работает (не ломать)

- TRUTH default при meaningful text без «сказк*» (§3.1 defaults)
- FAIRY_TALE при «сказк*»
- Teaching topics (road, hand washing, stranger+candy)
- Age extract + default 5
- Subject regex (fox, hedgehog, hare, squirrel, parrot+cockatoo fallback)
- Disney / impossible visual → clarification path
- Soft watercolor mood → `soft_preferences`, Stage 2 стартует
- Character Tim + continuity policy
- Golden / negative integration tests (mock executor, no real LLM)

---

## 3. Proposed solution

### 3.1 Целевая архитектура Stage 1 (фиксированный каскад)

**Это не временный костыль — целевая основа Stage 1.** Полный LLM interpreter (отдельный epic) встраивается **после** этого каскада на low-confidence полях, не заменяя fast path.

```text
regex / rules (truth, age, subjects, teaching, unsupported markers)
  → normalize
  → registry match (exact alias → contains)
  → RapidFuzz (style phrases, typos)
  → LLM tail ТОЛЬКО если выше не уверены (style/substyle, ≤10 candidates из registry)
  → deterministic post-verify (registry, applies_to, contradictions)
  → classification / routing → candidate_layer_resolution
```

**Hybrid default:** LLM-only Stage 1 — **нет**.

| Слой | Модуль | §3.2 |
|------|--------|------|
| Regex / rules | `stage1.py` (preserve) | ✅ |
| Normalization | `interpretation/text_normalize.py` | ✅ |
| Phrase extract | `interpretation/style_phrases.py` | ✅ |
| Registry match | `lookup.py` extend | ✅ |
| RapidFuzz | `interpretation/style_match.py` | ✅ |
| LLM style tail | `interpretation/style_llm_tail.py` + provider interface | ✅ |
| Post-verify | `lookup.py` / `stage1.py` | ✅ |

**Dependency:** `rapidfuzz` (добавить в project deps). Blocker'ов нет — стандартная pure-Python lib, CI-friendly.

### 3.2 Модули

| Модуль | Ответственность |
|--------|-----------------|
| `src/core/interpretation/text_normalize.py` | NFKC, lower, ё→е, punctuation, collapse whitespace |
| `src/core/interpretation/style_phrases.py` | Extract «в стиле …», «как у …», «по …», «как …», «похоже на …» + hard/soft flag |
| `src/core/interpretation/style_match.py` | Orchestrate exact → contains → RapidFuzz; score + rank candidates |
| `src/core/interpretation/style_llm_tail.py` | Narrow LLM disambiguation; scripted provider for tests |
| `src/core/prompts/lookup.py` (extend) | `match_style_layers()`, post-verify helpers |
| `src/core/nodes/stage1.py` | Wire pipeline; `is_character`; classification |
| `candidate_layer_resolution` | Dynamic substyle resolution from registry (less `_SUPPORTED_LAYER_IDS` hardcode) |

**`substyle` field:** canonical **layer id** (`CHUKOVSKY_STYLE`). Backward compat: slug → id map in resolution (`russian_folk_tale` → `RUSSIAN_FOLK_TALE`, `myth_soft` → `MYTH_SOFT_BASE`).

### 3.3 Unsupported / missed style policy (§3.2.1)

| Вход | Hard? | Registry | Действие |
|------|-------|----------|----------|
| «строго в стиле Дисней» | hard | нет | `unsupported_hard_requirement` → clarification (сохранить) |
| «в стиле чуковского» | soft | CHUKOVSKY_STYLE | `substyle=CHUKOVSKY_STYLE`, layer in resolved |
| «акварельное настроение» | soft | нет | `soft_preferences` (сохранить) |
| «строго в стиле X», X ∉ registry | hard | нет | clarification + UX ниже |
| «в стиле X», X ∉ registry | soft | нет | `soft_preferences` или `unresolved_details` (type=`style_preference`); **не** fabricate layer |
| Match есть, но `applies_to` конфликт (TRUTH + CHUKOVSKY) | — | mismatch | clarification: «этот стиль доступен для сказок, не для правдивых историй» — **не silent resolve** |

UX для «строго X», X ∉ registry:

```text
message: «Стиль „X“ пока не поддерживается в MVP. Мы можем сделать сказку без этого стиля или в базовой сказочной манере.»
options:
  - id: opt_no_style — label: «Сказка без особого стиля»
  - id: opt_fairy_base — label: «Обычная сказка про <subject>»
freeform_allowed: true
```

Detection порядок: phrase extraction + registry cascade; затем `_UNSUPPORTED_RE` brand blocklist.

### 3.4 `is_character` в TRUTH

```text
truth_mode = TRUTH
  AND subject.type = animal
  AND нет explicit character markers
    → is_character = false
    → character_profile = null
    → subject_continuity_policy.mode = "single_subject_all_items"
```

**Explicit character markers** (any → `is_character = true`):

- собственное имя («бельчонок Тим», «зовут …»);
- **«маленький \<species\>» + trait/detail** — character ok (как Tim); без имени/«персонаж/зовут» — false;
- явные слова: «герой», «персонаж», «назови», «зовут»;
- `character_profile` из resume.

**FAIRY_TALE / MYTH:** default `is_character=true` для животных сохраняем (сказочная онтология).

**Координация Dev C (§3.3):** до merge **PR-3** — sync: gate `character_consistency` **no-op / pass** при `is_character=false`. Иначе TRUTH fox падает на Stage 2 при зелёном Stage 1.

---

## 4. Matching algorithms

### 4.1 Style matching pipeline (§3.2 production path)

```text
1. extract_style_phrases(raw_text) → [(phrase, is_hard_requirement), ...]
2. normalize_phrase(phrase)        → normalized phrase token(s)
3. For each candidate substyle layer in registry (filtered by draft truth_mode, age, utility):
     a. EXACT ALIAS: normalized phrase == normalize(alias)           → score 100, match_level=alias_exact
     b. CONTAINS:    normalized phrase in normalize(alias) or reverse  → score 85–92, match_level=alias_contains
     c. RAPIDFUZZ:  max(WRatio, token_set_ratio) vs all aliases       → score 0–100, match_level=fuzzy
4. Filter by applies_to (truth_mode, target_age, utility_mode, content_format)
5. Rank: exact > contains > fuzzy; tie-break by score, then layer id (deterministic)
6. Decision thresholds (Wave 11 orientir):
     score ≥ 90  AND applicability ok     → auto-resolve substyle + layer ref
     75 ≤ score < 90                    → LLM tail OR clarification (see 4.3)
     score < 75                         → missed style path (soft/hard per §3.3)
7. Post-verify resolved id ∈ registry + applies_to + no contradiction
8. LLM tail (if triggered) → post-verify again
```

### 4.2 Почему RapidFuzz (`WRatio` / `token_set_ratio`), а не голый Levenshtein

| Критерий | Levenshtein (char) | RapidFuzz WRatio / token_set_ratio |
|----------|-------------------|-------------------------------------|
| «чуйковкого» vs «чуковского» | OK для опечаток | OK, нормализованный ratio |
| «как у чуковского» vs alias «как у Чуковского» | Плохо — разная длина, лишние слова | **token_set_ratio** игнорирует порядок/лишние токены |
| «в стиле чуковского» vs «чуковский» | Слабый signal | **WRatio** + partial ratio на extracted phrase vs alias |
| Скорость @ 5 substyles × ~4 aliases | Достаточно | Достаточно (<1ms) |
| Зависимость | stdlib только | `rapidfuzz` — accepted для §3.2 |

**Порядок важен:** exact alias и contains **всегда** выше fuzzy — fuzzy не перебивает явный alias match.

**RapidFuzz scores:** нормализуем в 0–100; `score = max(fuzz.WRatio(phrase, alias), fuzz.token_set_ratio(phrase, alias))` после общей normalization.

### 4.3 Когда вызывается LLM style tail

LLM tail вызывается **только** для style / substyle / reference_labels, **не** для truth_mode, age, subjects, output_count.

**Trigger (any):**

1. **Fuzzy band:** лучший candidate `75 ≤ score < 90` после RapidFuzz (exact/contains не сработали).
2. **Ambiguity:** top-2 candidates оба `score ≥ 75` **и** `score_delta = top1 - top2 < 5` (близкие конкуренты).
3. **Fuzzy miss with signal:** extracted phrase length ≥ 4, hard_requirement=false, best fuzzy score `< 75`, но phrase matches style pattern — optional tail с pre-filtered candidates (contains partial hits).

**Не вызывается:**

- auto-resolve при score ≥ 90 + applicable;
- hard unsupported (X ∉ registry + «строго») → clarification без LLM;
- applicability conflict (TRUTH + CHUKOVSKY) → clarification без LLM;
- empty phrase list.

**LLM contract (жёстко):**

| | |
|---|---|
| Input | extracted phrase + draft `{truth_mode, target_age, utility_mode}` + ≤10 candidates `{layer_id, short_description, matched_alias, score}` |
| Output | exactly one `layer_id` from list **or** `NONE` |
| Post-verify | id ∈ registry; `applies_to` pass; else → soft/unresolved, **не fabricate** |
| Tests | scripted provider; CI **без** external LLM |
| Scope | **только** style/substyle/reference_labels |

**Ambiguity fallback без LLM success:** если LLM вернул `NONE` или post-verify fail → soft preference / unresolved (soft) или clarification (hard).

### 4.4 Что не покрывает §3.2 (отдельный epic — Stage 1 v2)

| Capability | Epic |
|------------|------|
| Full LLM `input_analysis` всех полей + confidence | Stage 1 v2 — incomplete requests & confidence |
| Batch clarification для «про ёжика» / empty input UX | Stage 1 v2 |
| Preview generation через LLM | Stage 1 v2 |
| Multi-field disambiguation одним LLM call | Stage 1 v2 |

Epic **дополняет** каскад §3.2 на low-confidence / incomplete запросах после manual §3.5, если понадобится.

---

## 5. Scope: §3.2 = один sprint (Уровень B)

**Согласовано:** §3.2 закрывается **одним заходом** — matching pipeline целиком, не «Phase 1 done → Phase 2 потом».

| In scope §3.2 | Out of scope §3.2 |
|---------------|-------------------|
| PR-1…PR-5 (см. ниже) | Full LLM interpreter всех полей |
| RapidFuzz для style phrases | Batch clarification / empty input UX |
| LLM style tail (narrow) | Stage 2 TRUTH enforcement (§3.3) |
| TRUTH `is_character`, §3.2.1 unsupported/missed | Length limits (§3.4) |

---

## 6. PR strategy

| PR | Scope | Merge gate |
|----|-------|------------|
| **PR-1** | normalize + phrase extract + registry match (exact → contains) + wire `input_analysis` | unit tests phrase/normalize |
| **PR-1b** | RapidFuzz integration + thresholds (≥90 auto, 75–89 → LLM tail or clarify path) | unit tests typos incl. «чуйковкого» |
| **PR-2** | dynamic substyle resolution; reduce `_SUPPORTED_LAYER_IDS` hardcode for substyles | validation substyle layer ref |
| **PR-3** | TRUTH `is_character` + unsupported style UX | sync Dev C before merge |
| **PR-4** | LLM style tail + provider interface + scripted tests | CI no real LLM |
| **PR-5** | integration/golden (Chukovsky, regressions) — **required** for §3.2 close | full pytest green |

**Merge order:** PR-1 → PR-1b → PR-2 → PR-3 (after Dev C sync) → PR-4 → PR-5.

---

## 7. Test plan

### 7.1 Unit tests (no external LLM)

| ID | Test | Assert |
|----|------|--------|
| U1 | chukovsky_alias_exact | `CHUKOVSKY_STYLE`, match_level alias |
| U2 | chukovsky_variants + typo «чуйковкого» | RapidFuzz → `CHUKOVSKY_STYLE` |
| U3 | TRUTH + «в стиле чуковского» | clarification; no silent CHUKOVSKY |
| U4 | russian_folk regression | `RUSSIAN_FOLK_TALE` |
| U5 | truth_default | `TRUTH`, no regression |
| U6 | age_default | `target_age=5` |
| U7 | truth_fox_not_character | `is_character=false` |
| U8 | tim_still_character | `is_character=true`, profile |
| U9 | disney_hard | unsupported; no DISNEY layer |
| U10 | impressionism_hard | unsupported (regression) |
| U11 | watercolor_soft | soft_preferences |
| U12 | no_fabricated_ids | all ids ∈ registry |
| U13 | fuzzy_threshold_90 | score ≥ 90 auto-resolve |
| U14 | fuzzy_band_75_89 | triggers LLM tail path (scripted) |
| U15 | ambiguity_top2_delta | delta < 5 → LLM tail (scripted) |
| U16 | llm_tail_rejects_hallucination | id not in candidates → NONE/unresolved |

Files: `tests/unit/test_stage1_style_matching.py`, `tests/unit/test_stage1_style_llm_tail.py`.

### 7.2 Integration tests (GoldenStage2Executor)

| ID | Request | Assert |
|----|---------|--------|
| I1 | Wave 11 Chukovsky full request | `CHUKOVSKY_STYLE` in layers; approved |
| I2 | TRUTH fox | `is_character=false`; golden green |
| I3 | Disney unsupported | no Stage 2 |
| I4 | «2 сказки про лису» | age 5; completes |
| I5 | Chukovsky typo variant end-to-end | RapidFuzz path in production |

### 7.3 Manual (§3.5 prep, after PR-5)

Wave 11 appendix #5, #6, #7 — CLI session_ids recorded.

---

## 8. Risks and mitigations

| Risk | Mitigation |
|------|------------|
| `_SUPPORTED_LAYER_IDS` drift | PR-2 dynamic substyle from registry |
| False positive contains match | min phrase length; applicability; exact > contains > fuzzy |
| `is_character` breaks golden | TRUTH-only assertion updates |
| §3.3 character_consistency | **Dev C sync before PR-3 merge** |
| LLM tail non-determinism in CI | scripted provider only; no network in tests |
| RapidFuzz version drift | pin in deps; golden scores in unit tests |

**Blockers:** none identified for RapidFuzz thresholds or LLM tail scope.

---

## 9. Doc updates (after code)

- [x] `NORMALIZED_STATE_CONTRACT.md` — TRUTH `is_character=false`; substyle = layer id
- [x] `01_STAGE_1_INTERPRETATION.md` — MVP cascade paragraph
- [x] `MVP_FOLLOW_UP_MASTER_PLAN.md` §7 — §3.2 → `done`

---

## 10. Estimated effort

| Scope | Effort |
|-------|--------|
| **§3.2 целиком (Уровень B)** | **8–12 dev-days** |
| Stage 1 v2 epic (post §3.5) | TBD |

---

## 11. Approval checklist (lead + tech reviewer)

- [x] Hybrid default; LLM-only Stage 1 — **нет**
- [x] `substyle` = layer id (`CHUKOVSKY_STYLE`) + backward compat slug → id
- [x] TRUTH + animal → `is_character=false` по умолчанию; «маленький \<species\>» + trait → character ok (Tim)
- [x] TRUTH + CHUKOVSKY → clarification (applicability), не silent resolve
- [x] Unsupported «строго X», X ∉ registry — UX согласован
- [x] Module `src/core/interpretation/` — ok
- [x] **RapidFuzz — в §3.2**
- [x] **LLM style tail — в §3.2**, narrow scope
- [x] §3.2 = один sprint (PR-1…PR-5), не split Phase 1/2
- [x] Full LLM interpreter — отдельный epic (Stage 1 v2)

---

## 12. Definition of Done — §3.2

- [x] Wave 11 Chukovsky + variants (incl. typo via RapidFuzz) → `CHUKOVSKY_STYLE`
- [x] §3.2.1 unsupported/missed policy
- [x] TRUTH `is_character` + regression golden
- [x] **RapidFuzz + style tail** in production path (heuristic tail; real LLM provider — backlog)
- [x] `pytest` green, CI без external LLM
- [x] Plan doc обновлён, status `done`

**Follow-up (не блокирует §3.2):** real LLM `StyleLlmTailProvider`; Stage 1 v2 full interpreter epic; `_SUPPORTED_LAYER_IDS` substyle cleanup.

---

## 13. Historical: answers to lead questions (v1 plan)

Сохранено для traceability; актуальный scope — §3.1–§6 выше.

**Q1 LLM-only:** rejected — ~2.5–3.8K tokens/request vs 0 on fast path; hallucination risk.

**Q2 Hybrid savings:** ~90% token reduction vs LLM-only @ MVP traffic; LLM tail ~5–15% requests.

**Q3 Phase split:** **superseded** — §3.2 = single sprint with RapidFuzz + LLM tail.

**Q4–Q6:** incorporated in §3.3, §3.4, §4.3.

**Next step (§3.2 closed):** §3.3 Stage 2 TRUTH enforcement — см. `MVP_FOLLOW_UP_MASTER_PLAN.md` §3.3.
