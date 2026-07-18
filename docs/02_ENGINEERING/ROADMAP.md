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

## Release 1 Cleanup

Current cleanup phases:

1. Inventory and dependency audit.
2. Documentation sync and Release 2 backlog.
3. Legacy cleanup after import/test dependency audit.
4. Smoke/regression checks.

Legacy code deletion must happen only after dependency audit. In particular, be careful with `providers/*`, `src/core/factory.py`, `src/utils/cli_parser.py`, `src/models/schemas.py` and shared test fixtures.

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
