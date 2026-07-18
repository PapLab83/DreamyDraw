# REQUIREMENTS.md - Release 1 Requirements

Status: current Release 1 acceptance requirements.

## 1. Release 1 Functional Requirements

- The system accepts a raw Russian text request through `scripts/run_stage1_2_mvp.py`.
- Stage 1 normalizes the request into durable state: format, truth mode, age, count, subjects, details and prompt context.
- Stage 1 resolves prompt layers through the active `prompts/` registry.
- Stage 1 asks for clarification or stops when the request is empty, unsupported, contradictory or not executable within the MVP.
- Stage 2 produces candidate text variants, deduplicates/ranks/checks them and writes final output to `approved_texts`.
- Default CLI execution uses the local `mock` Stage 2 executor.
- Real LLM execution is available only through explicit manual `--executor llm` runs.
- Automated tests must not call real LLM or image providers.

## 2. Release 1 Output Boundary

Release 1 output is text-only:

```text
approved_texts
```

No image generation, image prompt execution, visual validation, animation, micro-cartoon generation, UI or Stage 3 path is required for Release 1 acceptance.

## 3. Product Defaults In The MVP

- Default `truth_mode`: `TRUTH` when the request does not specify a supported mode.
- Seed ages: `3` and `5`.
- Default `target_age`: `5` when age is missing.
- Default executor: `mock`.
- LLM executor: manual explicit mode only.

## 4. Non-Functional Requirements

- Session state is persisted through `JSONStorage`.
- Stored trace/session metadata must remain compact and must not persist full prompt bodies by default.
- Provider configuration errors must fail clearly before running a real LLM session.
- Regression tests must be runnable locally without network access.

## 5. Target/Future Requirements

The target product includes illustrated stories, visual formats and richer clients. Those requirements are not removed; they are deferred to Release 2+ and tracked in `docs/02_ENGINEERING/implementation/RELEASE_2_BACKLOG.md`.

Legacy `main.py`, `fast/check` and text->image behavior are deprecated and are not Release 1 requirements.
