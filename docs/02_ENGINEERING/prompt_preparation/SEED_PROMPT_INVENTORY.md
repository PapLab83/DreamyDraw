# Seed Prompt Inventory

Статус: актуализированный Release 2 manifest минимального seed prompt set.

Этот документ является навигационным manifest для подготовки seed prompt-базы Stage 1-2. Подробные layer requirements, golden coverage и writer tasks вынесены в соседние временные документы, чтобы inventory не превращался в большой монолит.

После создания реальных seed prompt files этот manifest можно сократить до checklist/coverage index или перенести постоянные части в README prompt-базы.

Current scope ends at `approved_texts`. Do not add Stage 3, image generation, image prompt execution, visual validation, animation or micro-cartoon prompts here.

## 1. Source Documents

Read first:

- `SEED_PROMPT_WORKPLAN.md`
- `SEED_PROMPT_INVENTORY_PLAN.md`
- `../contracts/PROMPT_FILE_CONTRACT.md`
- `../contracts/PROMPT_LOOKUP_CONTRACT.md`
- `../contracts/PROMPT_COMPOSITION_CONTRACT.md`
- `../contracts/NORMALIZED_STATE_CONTRACT.md`
- `../contracts/STAGE_CONTRACTS.md`
- `../contracts/SEED_SCOPE.md`
- `../contracts/GOLDEN_SCENARIOS.md`
- `../contracts/SCOPE_BOUNDARIES.md`

## 2. Detail Documents

| Document | Purpose |
| --- | --- |
| `SEED_PROMPT_METADATA.md` | Shared metadata decision, `role` rules, naming and namespace conventions. |
| `SEED_PROMPT_LAYERS_CORE.md` | Content format, truth modes, style/substyle, utility modes/topics, age and language layers. |
| `SEED_PROMPT_LAYERS_ENTITIES.md` | Entity layers, fallback entities and character profile requirements. |
| `SEED_PROMPT_LAYERS_STAGE.md` | Stage prompt layers for Stage 2 text pipeline. |
| `SEED_PROMPT_GOLDEN_COVERAGE.md` | Golden scenario coverage matrix and provocative scenario checks. |
| `SEED_PROMPT_WRITER_TASKS.md` | Independent writer tasks and final acceptance checklist. |

## 3. Required Groups

Minimum seed groups:

1. Content format.
2. Truth modes.
3. Text style/substyle.
4. Utility modes.
5. Utility topics.
6. Age layers.
7. Language layers.
8. Entity layers and fallback entities.
9. Character profiles and continuity.
10. Stage prompt layers.

## 4. Current Decisions

- `role` is an optional prompt-file metadata field in `PROMPT_FILE_CONTRACT.md`.
- For this seed set, `role` is required when orchestration meaning would otherwise be ambiguous.
- `role` must never replace `type`.
- `SEED_SCOPE.md` is the canonical base for minimum seed coverage.
- Extra entities may be included only when required by `GOLDEN_SCENARIOS.md` or seed utility topics.
- Release 2 seed scope contains only `TRUTH` and `FAIRY_TALE`; `MYTH` and Scandinavian style are deferred and absent from the active `RUSSIAN_FOLK` tree.
- `CHUKOVSKY_STYLE` is an MVP lookup/reference label and must be written as a stylistic transformation brief, not copying instructions.
- Stage prompt briefs must be stricter than artistic/content layer briefs.

## 5. Final Acceptance

Inventory planning is ready for prompt writers when:

- all detail documents exist;
- every proposed layer has `id`, `type`, `role` when needed, `namespace` and purpose;
- every golden scenario maps to required prompt layers or explicit freeform/hard-detail handling;
- writer tasks are independent enough for separate prompt writers;
- no task asks writers to implement Stage 3, image generation, animation, PromptRegistry or PromptComposer;
- no task introduces new prompt file `type` enum values.
