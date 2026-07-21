# ARCHITECTURE.md - DreamyDraw

Status: current Release 2 architecture overview.

## 1. Current Release 2 Actual

Release 2 is a Stage 1-2 text-only MVP. The active product path is:

```text
CLI/config/defaults + raw request
  -> effective controlled config
  -> cultural prompt root selection
  -> Stage 1 interpretation
  -> prompt layer lookup/composition
  -> Stage 2 text pipeline
  -> approved_texts
```

The current release boundary is `SessionState.approved_texts`. Image generation, animation, visual QA and Stage 3 are target/future work, not part of Release 2 acceptance.

## 2. Active Components

| Area | Active implementation |
| --- | --- |
| CLI | `scripts/run_stage1_2_mvp.py` |
| Orchestration facade | `src/core/stage1_2_orchestrator.py` |
| Graph | `src/core/graph/stage1_2_builder.py`, `src/core/graph/routing.py`, `src/core/graph/state.py` |
| Stage 1 nodes | `src/core/nodes/stage1.py` |
| Stage 2 nodes | `src/core/nodes/stage2.py` |
| Prompt registry/composition | `src/core/prompts/` |
| Active prompt assets | `prompts/cultural_contexts/russian_folk/` |
| Text executors | `src/core/stage2_mock_executor.py`, `src/core/stage2_llm_executor.py` |
| Storage | `src/storage/json_storage.py` |
| State models | `src/models/schemas.py` |

The controlled fields `output_count`, `target_age`, `truth_mode`, `cultural_context` and `utility_mode` come only from CLI/config/defaults. Stage 1 does not extract or reconcile them from `raw_text`. The CLI uses the local `mock` Stage 2 executor by default. A real LLM executor is available only through explicit manual `--executor llm` runs and provider configuration.

Automated tests must use mock/scripted providers and must not call a real LLM or image provider.

## 3. Prompt System

The active prompt system is metadata-driven:

```text
prompts/cultural_contexts/russian_folk/**/*.md
  -> PromptRegistry
  -> lookup / fallback / unresolved details
  -> PromptComposer
  -> stage-specific runtime context
```

`cultural_context` selects the registry root through an allowlist and is not composed as a prompt layer. Release 2 supports only `RUSSIAN_FOLK`. MYTH and Scandinavian assets are not part of the active tree.

The legacy `docs/03_PROMPTS/**` prompt assets and old `src/core/prompt_builder.py` runtime module were removed during Release 1 cleanup. Current prompt work must use the selected cultural tree.

## 4. Legacy Boundary

The old plan/text/image runtime pipeline was removed during Release 1 cleanup after dependency audit and legacy test cleanup:

```text
main.py
src/core/orchestrator.py
src/core/graph/builder.py
src/core/prompt_builder.py
src/core/nodes/safety.py
src/core/nodes/planning.py
src/core/nodes/validation.py
src/core/nodes/content.py
```

These modules and their legacy tests are no longer part of the active repository runtime. New Stage 1-2 work must use the active components listed above.

The legacy prompt asset tree was removed in the docs/assets cleanup pass:

```text
docs/03_PROMPTS/**
```

Historical references to that tree may still exist in target/reference documents, but it is no longer part of the active repository assets.

## 5. Target Vision

The target product still includes illustrated stories, richer visual formats, animation and possibly other clients. Those directions are tracked outside the current Release 2 Stage 1-2 acceptance, primarily in `implementation/RELEASE_2_BACKLOG.md` and target/reference documents.
