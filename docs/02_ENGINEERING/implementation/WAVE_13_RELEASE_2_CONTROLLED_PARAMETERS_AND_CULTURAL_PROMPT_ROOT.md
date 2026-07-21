# Wave 13 Task — Release 2 controlled parameters and cultural prompt root

Status: **implemented; final verification complete**.
Owner: **Engineering Agent**.  
Release: **Release 2**.

---

## Goal

Make the Stage 1–2 MVP more controllable and reproducible by moving the main generation modes out of free-form request interpretation and into explicit CLI/config settings, and by isolating prompt assets under a selected cultural-context root.

The target split is:

```text
CLI/config/defaults:
- output_count
- target_age
- truth_mode
- cultural_context
- utility_mode

raw_text:
- subject and characters
- setting
- plot details
- supported style/reference labels
- additional hard and soft details
```

## Approved product decisions

### Controlled parameters

The effective generation config must always contain all five controlled parameters:

| Internal field | CLI flag | Release 2 values | Default |
| --- | --- | --- | --- |
| `output_count` | `--count` | positive bounded integer | `3` |
| `target_age` | `--age` | `3`, `5` | `5` |
| `truth_mode` | `--truth-mode` | `TRUTH`, `FAIRY_TALE` | `TRUTH` |
| `cultural_context` | `--cultural-context` | `RUSSIAN_FOLK` | `RUSSIAN_FOLK` |
| `utility_mode` | `--utility-mode` | `NARRATIVE`, `TEACHING` | `NARRATIVE` |

“Required” means required in the effective config and normalized state. CLI flags may be omitted because every controlled parameter has an explicit documented default.

`reference_style` is not added as a controlled parameter in this wave.

### Source-of-truth rule

CLI/config/defaults are the only source of truth for the five controlled parameters.

Stage 1 must not extract, infer, override, reconcile or conflict-check these fields from `raw_text`:

```text
output_count
target_age
truth_mode
cultural_context
utility_mode
```

For example, with no flags:

```text
raw_text: "Сделай 2 сказки про лису для 3 лет"

effective controlled parameters:
output_count = 3
target_age = 5
truth_mode = TRUTH
cultural_context = RUSSIAN_FOLK
utility_mode = NARRATIVE
```

The parameter-like wording in `raw_text` does not change these values. Stage 1 continues to interpret the request only for non-controlled details such as the fox subject, setting, characters, plot constraints and supported style/reference labels.

### Cultural context is a prompt root selector

`cultural_context` selects an independent prompt asset tree. It is not a prompt layer and must not be appended to prompt composition as another body.

Release 2 has one allowed mapping:

```text
RUSSIAN_FOLK
  -> prompts/cultural_contexts/russian_folk/
```

The runtime must:

1. resolve the effective `cultural_context` through a fixed allowlist;
2. reject unknown values before Stage 2;
3. construct `PromptRegistry` from the selected cultural root only;
4. perform metadata lookup, execution lookup and composition inside that registry;
5. persist the canonical context and expose it in normalized summaries and observability;
6. retain the selected root identity and registry hash in diagnostics.

Future contexts may be added as independent trees, for example:

```text
prompts/cultural_contexts/
├── russian_folk/
├── british_english/
└── spanish_spain/
```

They are not translations or overlays of the Russian tree.

## Prompt asset migration and cleanup

Move the current active prompt tree under:

```text
prompts/cultural_contexts/russian_folk/
```

Do not leave a second loadable copy of the same layer IDs under `prompts/**`.

Remove the following unsupported assets from the active repository tree during this wave:

- `prompts/cultural_contexts/russian_folk/truth_modes/MYTH/**`;
- `prompts/cultural_contexts/russian_folk/truth_modes/FAIRY_TALE/styles/folklore/SCANDINAVIAN_TALE.md`.

Git history is the backup. Do not create a backup directory inside `prompts/**`, because `PromptRegistry` recursively loads Markdown files and an archive there could become active accidentally.

Remove or update runtime mappings, parsing branches, tests and active documentation that claim current `MYTH` support. Record `MYTH` as deferred product work rather than an available Release 2 mode. This cleanup does not authorize redesigning the remaining prompt bodies.

## Implementation scope

Expected code areas:

- `scripts/run_stage1_2_mvp.py`;
- request/config models and `src/core/request_adapter.py`;
- `NormalizedRequest` and `SessionState` models;
- `src/core/nodes/stage1.py` normalization and final parameter validation;
- `src/core/stage1_2_orchestrator.py` registry construction;
- `src/core/prompts/registry.py`, lookup and composer integration where required;
- normalized summaries, preview, persistence and observability;
- prompt-root fixtures and source-path expectations in tests;
- `prompts/**` migration and approved cleanup;
- contracts, architecture, prompt guide, CLI guide and Release 2 backlog.

Stage 2 business logic is outside the scope. It may receive the new normalized values through the existing contracts, but its generation/scoring/validation pipeline must not be redesigned in this wave.

## Proposed implementation sequence

### Phase 0 — implementation plan gate

1. Trace all readers and writers of the five controlled fields.
2. Specify canonical enums/models, config precedence and validation bounds.
3. Specify the allowlisted cultural-root resolver and registry lifecycle.
4. Enumerate prompt moves and all tests/docs with hard-coded source paths.
5. Write the detailed implementation plan and obtain lead approval before code changes.

### Phase 1 — controlled config contract

1. Add canonical values and defaults for all five fields.
2. Add CLI flags and build one effective config before session creation.
3. Persist effective settings in the request/session state.
4. Remove Stage 1 extraction and hidden defaults for these fields from `raw_text`.
5. Validate the effective values before Stage 2.

### Phase 2 — cultural prompt root

1. Add the allowlisted `cultural_context -> prompt root` mapping.
2. Select the root before constructing `PromptRegistry`.
3. Load exactly one context registry per orchestrator run.
4. Persist and expose context/root/hash diagnostics.

### Phase 3 — prompt migration and first test checkpoint

1. Move active assets to `cultural_contexts/russian_folk/`.
2. Update source paths and fixtures required by the cultural-root migration.
3. Verify global layer-ID uniqueness in the selected tree.
4. Run the focused CLI/config, state persistence, root-selection, lookup and composition tests.
5. Run the complete automated suite without external provider calls.

**Checkpoint A exit criteria:** controlled parameters and `RUSSIAN_FOLK` root selection work with the migrated prompt inventory; the complete suite is green before any MYTH or Scandinavian assets are removed.

### Phase 4 — unsupported asset cleanup

1. Remove `MYTH/**` and `SCANDINAVIAN_TALE.md`.
2. Remove stale MYTH runtime mappings, parsing branches, tests and active-support claims.
3. Record MYTH as deferred product work and Scandinavian style as unavailable in the Russian context.
4. Run focused negative tests proving that MYTH and Scandinavian style are no longer available.
5. Run the complete automated suite again without external provider calls.

**Checkpoint B exit criteria:** cleanup is complete, negative availability tests pass and the complete post-cleanup suite is green.

### Phase 5 — final tests, documentation and report

1. Confirm all required unit and integration coverage is present.
2. Confirm CLI/config/default precedence and `raw_text` non-override coverage.
3. Confirm state persistence, normalized-summary and observability coverage.
4. Confirm registry-selection and unsupported-context coverage.
5. Update all required documentation.
6. Run the final complete automated suite and publish the implementation report.

## Validation and precedence rules

The intended precedence is:

```text
explicit CLI/config value
  -> documented default
```

`raw_text` is not part of this precedence chain.

Validation must happen before Stage 2:

- `output_count`: positive and bounded by the agreed MVP limit;
- `target_age`: exactly `3` or `5`;
- `truth_mode`: exactly `TRUTH` or `FAIRY_TALE`;
- `cultural_context`: exactly `RUSSIAN_FOLK` in Release 2;
- `utility_mode`: exactly `NARRATIVE` or `TEACHING`.

Invalid explicit values must fail clearly; they must not silently fall back to defaults.

## Required test coverage

- CLI accepts all five flags and persists canonical values.
- Omitting all flags produces the five approved defaults.
- Config values reach normalized state and Stage 2 runtime summary.
- Text containing different count/age/truth/utility wording does not change effective settings.
- Controlled fields survive session persistence and resume.
- Preview, normalized summary and observability include all five values.
- `RUSSIAN_FOLK` selects only `prompts/cultural_contexts/russian_folk/`.
- Unknown cultural context is rejected before registry lookup/Stage 2.
- Registry sources are relative to the selected cultural root and remain verifiable.
- No duplicate active layer IDs remain after migration.
- MYTH is no longer accepted as a Release 2 `truth_mode`.
- Scandinavian style is no longer discoverable in the Russian context.
- Existing TRUTH and FAIRY_TALE Stage 1–2 scenarios remain green after test inputs are migrated to explicit config.
- Full automated test suite passes without external LLM calls.

## Documentation updates

At minimum reconcile:

- `docs/01_PRODUCT/WHAT_IS_DREAMYDRAW.md`;
- `docs/02_ENGINEERING/ARCHITECTURE.md`;
- `docs/04_GUIDES/PROMPT_GUIDE.md`;
- `docs/02_ENGINEERING/PROMPT_AGENT_ROLE.md`;
- `docs/02_ENGINEERING/TARGET_ORCHESTRATION_LOGIC.md`;
- normalized state, prompt lookup, prompt composition, prompt file and stage contracts;
- CLI/runbook documentation;
- `docs/02_ENGINEERING/implementation/RELEASE_2_GOALS_AND_TASKS.md`;
- `docs/02_ENGINEERING/implementation/RELEASE_2_BACKLOG.md`.

Documentation must clearly distinguish the previous Release 1 behavior from the Release 2 controlled-parameter contract.

## Out of scope

- extracting any controlled parameter from free text;
- universal semantic resolver;
- `reference_style` as a CLI/config field;
- new cultures or translations;
- new truth modes;
- new reference styles, animals or content formats;
- prompt-body redesign or payload compression;
- fox-specific builder;
- Stage 2 pipeline redesign;
- image generation or Stage 3.

## Acceptance criteria

- [x] All five controlled parameters always have canonical effective values.
- [x] Approved defaults are `3`, `5`, `TRUTH`, `RUSSIAN_FOLK`, `NARRATIVE`.
- [x] Stage 1 does not derive or override any controlled value from `raw_text`.
- [x] Invalid explicit values fail before Stage 2.
- [x] `cultural_context` selects a single allowlisted prompt root, not a prompt layer.
- [x] The active prompt tree lives only under `cultural_contexts/russian_folk/`.
- [x] MYTH and Scandinavian prompt assets are absent from the active tree.
- [x] State, preview, normalized summary and observability expose the five values.
- [x] CLI/config, persistence, root selection and non-override behavior are covered by tests.
- [x] Checkpoint A is green after parameter/root migration and before asset cleanup.
- [x] Checkpoint B is green after MYTH/Scandinavian cleanup.
- [x] Relevant contracts and active documentation match the implementation.
- [x] Full automated suite is green without external provider calls.
- [x] Final report lists changed files, defaults/validation, test results and deferred product work.

## Implementation report

- Effective config is canonicalized at the request boundary and persisted in `SessionRequest.current_config`; unknown or invalid controlled values fail validation before Stage 2.
- Stage 1 reads the five controlled values only from the effective config. Conflicting count, age, truth or utility wording in `raw_text` has no control effect.
- `RUSSIAN_FOLK` resolves through an allowlist to `prompts/cultural_contexts/russian_folk/` before `PromptRegistry` loading. Registry lookup and composition remain scoped to that selected root.
- The migrated pre-cleanup registry contained 43 unique layers. Checkpoint A passed the complete suite: **296 passed**.
- `MYTH/**` and `SCANDINAVIAN_TALE.md` were then removed together with runtime support and active-support claims. The post-cleanup registry contains 40 unique layers. Checkpoint B passed the complete suite: **302 passed**.
- Final coverage additionally verifies CLI persistence plus cultural root visibility in prompt context and observability. No automated run uses external LLM or image providers.
- Final complete suite after post-review corrections: **305 passed in 25.29s**.

Deferred product work: any future `MYTH` mode, Scandinavian style or additional cultural context must be designed as new context-appropriate assets and explicitly added to the allowlist/contracts. Git history is the only backup for the removed assets.

Post-review correction: base and override configs are canonicalized separately before merging, so a later `count` overrides an earlier `output_count` and a later `age` overrides an earlier `target_age` (with the reverse alias directions covered too). Current-looking Stage 2 and seed prompt preparation documents were reconciled with the two active Release 2 truth modes.

## Definition of Done

Wave 13 is done only when implementation, migration, tests, documentation and the final report are complete. Writing this task file alone does not start or complete implementation.
