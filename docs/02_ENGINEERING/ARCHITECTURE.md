# ARCHITECTURE.md - DreamyDraw

Status: current Release 1 architecture overview.

## 1. Current Release 1 Actual

Release 1 is a Stage 1-2 text-only MVP. The active product path is:

```text
CLI request
  -> Stage 1 interpretation
  -> prompt layer lookup/composition
  -> Stage 2 text pipeline
  -> approved_texts
```

The current release boundary is `SessionState.approved_texts`. Image generation, animation, visual QA and Stage 3 are target/future work, not part of Release 1 acceptance.

## 2. Active Components

| Area | Active implementation |
| --- | --- |
| CLI | `scripts/run_stage1_2_mvp.py` |
| Orchestration facade | `src/core/stage1_2_orchestrator.py` |
| Graph | `src/core/graph/stage1_2_builder.py`, `src/core/graph/routing.py`, `src/core/graph/state.py` |
| Stage 1 nodes | `src/core/nodes/stage1.py` |
| Stage 2 nodes | `src/core/nodes/stage2.py` |
| Prompt registry/composition | `src/core/prompts/` |
| Active prompt assets | `prompts/` |
| Text executors | `src/core/stage2_mock_executor.py`, `src/core/stage2_llm_executor.py` |
| Storage | `src/storage/json_storage.py` |
| State models | `src/models/schemas.py` |

The CLI uses the local `mock` Stage 2 executor by default. A real LLM executor is available only through explicit manual `--executor llm` runs and provider configuration.

Automated tests must use mock/scripted providers and must not call a real LLM or image provider.

## 3. Prompt System

The active prompt system is metadata-driven:

```text
prompts/**/*.md
  -> PromptRegistry
  -> lookup / fallback / unresolved details
  -> PromptComposer
  -> stage-specific runtime context
```

`docs/03_PROMPTS/**` and `src/core/prompt_builder.py` belong to the legacy pipeline and are not the active Release 1 prompt system.

## 4. Legacy Boundary

The old pipeline remains a cleanup candidate until dependency audit and test cleanup are complete:

```text
main.py
src/core/orchestrator.py
src/core/graph/builder.py
src/core/prompt_builder.py
src/core/nodes/safety.py
src/core/nodes/planning.py
src/core/nodes/validation.py
src/core/nodes/content.py
docs/03_PROMPTS/**
```

These files are deprecated and must not be used as the model for new Stage 1-2 work. Remove them only after import/test dependency cleanup.

## 5. Target Vision

The target product still includes illustrated stories, richer visual formats, animation and possibly other clients. Those directions are tracked outside Release 1 acceptance, primarily in `implementation/RELEASE_2_BACKLOG.md` and target/reference documents.
