# MODULES.md - Modules And Interfaces

Status: current Release 1 module map.

## 1. Active Release 1 Modules

| Module | Purpose |
| --- | --- |
| `scripts/run_stage1_2_mvp.py` | Main CLI for the Stage 1-2 text-only MVP. |
| `src/core/stage1_2_orchestrator.py` | Thin public facade for session lifecycle and graph invocation. |
| `src/core/graph/stage1_2_builder.py` | Builds the active Stage 1-2 LangGraph. |
| `src/core/graph/routing.py` | Routing rules for Stage 1 and Stage 2. Also contains legacy routing functions pending cleanup. |
| `src/core/graph/state.py` | Graph state conversion and shared graph state type. |
| `src/core/nodes/stage1.py` | Request interpretation, clarification, layer resolution and prompt context preparation. |
| `src/core/nodes/stage2.py` | Candidate generation, deduplication, scoring, validation/refinement and approved text selection. |
| `src/core/prompts/` | Prompt registry, lookup, composition and prompt metadata models. |
| `src/core/stage2_mock_executor.py` | Default local Stage 2 text executor. |
| `src/core/stage2_llm_executor.py` | Optional manual LLM-backed Stage 2 executor. |
| `src/core/stage2_*policy.py`, `src/core/stage2_*post_check.py` | Deterministic Stage 2 guardrails and prompt task suffixes. |
| `src/models/schemas.py` | Pydantic state and request models. Includes compatibility models for the old entrypoint. |
| `src/storage/json_storage.py` | JSON-backed session persistence. |
| `src/providers/` | LLM/provider interfaces and implementations. Image provider classes remain for legacy/future compatibility. |

## 2. Active Prompt Assets

Release 1 prompt assets live under:

```text
prompts/
```

They are loaded by `PromptRegistry` and composed by `PromptComposer`.

## 3. Legacy Modules

The following modules belong to the deprecated plan/text/image pipeline:

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

They are cleanup candidates, but deletion requires dependency audit and removal/rewiring of legacy tests.

## 4. File Structure

```text
dreamydraw/
├── prompts/                         # Active Stage 1-2 prompt layers
├── scripts/
│   └── run_stage1_2_mvp.py           # Active Release 1 CLI
├── src/
│   ├── core/
│   │   ├── stage1_2_orchestrator.py
│   │   ├── graph/
│   │   ├── nodes/
│   │   ├── prompts/
│   │   └── stage2_*                  # Text executor/policy/post-check modules
│   ├── models/
│   ├── providers/
│   ├── storage/
│   └── config/
├── tests/
└── docs/
```

## 5. Future Modules

Image generation, animation, visual QA, UI and Stage 3 are target/future modules. They should be specified separately and must consume the text result from `approved_texts` rather than reintroducing the old `fast/check` image pipeline.
