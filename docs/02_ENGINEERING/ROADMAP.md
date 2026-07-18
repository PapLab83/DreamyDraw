# ROADMAP.md - DreamyDraw

Status: release roadmap index.

## Release 1 - Stage 1-2 Text MVP

Goal:

```text
request -> Stage 1 interpretation -> prompt layers -> Stage 2 text pipeline -> approved_texts
```

Acceptance scope:

- text-only CLI through `scripts/run_stage1_2_mvp.py`;
- `mock` executor by default;
- optional manual `--executor llm`;
- automated tests with mock/scripted providers only;
- no image generation, animation, UI or Stage 3;
- legacy `main.py` / `fast/check` / old image path are not the release contour.

Operational docs:

- `implementation/STAGE_1_2_MVP_RUNBOOK.md`
- `implementation/STAGE_1_2_MVP_ACCEPTANCE_CHECKLIST.md`
- `implementation/RELEASE_1_CLEANUP_TASK.md`

## Release 1 Cleanup Status

Completed:

- inventory and dependency audit;
- documentation sync and Release 2 backlog;
- legacy runtime cleanup for `main.py`, old `Orchestrator`, old graph builder, old nodes, old `PromptBuilder`, old CLI parser and their legacy tests;
- smoke/regression checks for the active Stage 1-2 MVP.

Remaining cleanup is intentionally narrower:

- shared-file cleanup for mixed active/legacy modules such as `providers/*`, `src/core/factory.py`, `src/core/graph/routing.py` and `src/models/schemas.py`;
- docs/assets cleanup for `docs/03_PROMPTS/**`, historical wave docs and backup material.

Do not remove shared compatibility code without a fresh dependency audit.

## Release 2+

Active backlog:

```text
implementation/RELEASE_2_BACKLOG.md
```

Major themes:

- semantic resolver and parameter extraction;
- prompt architecture and final prompt diagnostics;
- animal/entity redesign;
- style/substyle architecture, including Russian folk and Chukovsky/reference labels;
- educational domains and English-learning direction;
- Stage 2 quality tuning;
- diversity/content banks;
- image generation, animation and Stage 3.

## Historical Roadmap

Older wave plans, implementation plans and legacy roadmap notes are historical context. They should not be used as Release 1 source of truth unless their decisions have been folded into current docs or `RELEASE_2_BACKLOG.md`.
