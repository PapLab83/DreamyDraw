# DreamyDraw Orchestrator Technical Spec

Статус: активный индекс технической спецификации оркестрации.

Подробная спецификация разделена на файлы в `docs/02_ENGINEERING/orchestration/`, потому что прежний монолитный документ стал слишком большим для ревью и разработки.

## Current Scope

In scope:

- Stage 1: input analysis, normalization, lookup-aware clarification/arbitration, preview, execution prompt context preparation.
- Stage 2: text pipeline from candidate generation to `approved_texts`.
- LangGraph orchestration with thin facade, node-owned business logic, graph-owned routing and `SessionState` / `JSONStorage` durable state.

Out of scope:

- image generation;
- image series;
- animation;
- micro-cartoons;
- full visual pipeline.

Current boundary: `approved_texts`. Future Stage 3 must consume `approved_texts` as downstream input and be specified separately.

## Sources And Priority

Business source:

- `TARGET_ORCHESTRATION_LOGIC.md`

Contract sources:

- `contracts/NORMALIZED_STATE_CONTRACT.md`
- `contracts/PROMPT_FILE_CONTRACT.md`
- `contracts/PROMPT_LOOKUP_CONTRACT.md`
- `contracts/PROMPT_COMPOSITION_CONTRACT.md`
- `contracts/STAGE_CONTRACTS.md`
- `contracts/SCOPE_BOUNDARIES.md`
- `contracts/GOLDEN_SCENARIOS.md`

Technical implementation specs:

- `orchestration/00_OVERVIEW.md`
- `orchestration/01_STAGE_1_INTERPRETATION.md`
- `orchestration/02_STAGE_2_TEXT_PIPELINE.md`
- `orchestration/03_STATE_AND_RECOVERY.md`
- `orchestration/04_PROMPT_SYSTEM.md`
- `orchestration/05_GRAPH_ROUTING.md`
- `orchestration/06_OBSERVABILITY.md`
- `orchestration/07_IMPLEMENTATION_READINESS.md`

Priority rule: if a nested object shape conflicts with a contract file, update the contract and the orchestration spec together before implementation.

## Recommended Reading Order

1. `orchestration/00_OVERVIEW.md`
2. `orchestration/01_STAGE_1_INTERPRETATION.md`
3. `orchestration/02_STAGE_2_TEXT_PIPELINE.md`
4. `orchestration/03_STATE_AND_RECOVERY.md`
5. `orchestration/04_PROMPT_SYSTEM.md`
6. `orchestration/05_GRAPH_ROUTING.md`
7. `orchestration/06_OBSERVABILITY.md`
8. `orchestration/07_IMPLEMENTATION_READINESS.md`

## Implementation Gate

Implementation can start when `orchestration/07_IMPLEMENTATION_READINESS.md` has no open P0/P1 findings against the active contracts.
