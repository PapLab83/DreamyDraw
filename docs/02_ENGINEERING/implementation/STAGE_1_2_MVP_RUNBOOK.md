# Stage 1-2 MVP Runbook

Status: Wave 11 developer/operator smoke guide.

## What This MVP Does

Stage 1-2 MVP runs the text-only DreamyDraw flow:

```text
manual request / CLI -> Stage 1 interpretation -> Stage 2 text pipeline -> approved_texts
```

It accepts a raw Russian request, normalizes the generation intent, resolves available prompt layers, asks for clarification when the request is not executable, and produces approved text drafts. The CLI uses the local mock Stage 2 executor by default; a real LLM-backed Stage 2 executor is available only when explicitly requested.

## What It Does Not Do

This MVP does not call image generation, animation, visual validation, UI, legacy `fast/check`, or Stage 3. The scope ends at durable `approved_texts`. Real LLM calls happen only for the explicit `--executor llm` manual path.

## Setup

Run commands from the repository root and use the project virtualenv:

```bash
cd /path/to/DreamyDraw
venv/bin/python scripts/run_stage1_2_mvp.py --help
```

By default, sessions are stored under:

```text
output/stage1_2_mvp/<session_id>/state.json
```

Override the output directory when running smoke checks:

```bash
export DREAMYDRAW_STAGE1_2_OUTPUT_DIR=/tmp/dreamydraw-stage1-2-smoke
```

You can also pass `--output-dir <path>` directly.

## Manual Smoke Commands

Happy path:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай 2 поучительные сказки про лису и переход через дорогу для 5 лет." --count 2
```

Expected shape:

```text
session_id: ...
completion_status: completed_enough
current_node: ...
approved_count: 2
approved_texts:
...
```

Empty request and resume:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py ""
venv/bin/python scripts/run_stage1_2_mvp.py --session <session_id> --resume "Сделай сказку про лису для 5 лет."
```

The first command should print `waiting_user: true`, `interrupt_node`, `interrupt_reason`, and either options or `freeform_allowed: true`. The resume command should keep the same `session_id` and reach `approved_texts`.

Unsupported hard requirement:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай сказку про лису для 5 лет строго в стиле Дисней."
```

Expected result is `waiting_user` or `stopped_unresolved_request`, with no `approved_texts` and no fabricated Disney prompt layer.

Truth/fantasy contradiction:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай правдивую историю про лису для 5 лет, обязательно чтобы она летала на волшебном ковре."
```

Expected result is clarification/waiting or unresolved stop, with no approved text. The stored state should contain the unsupported/contradictory detail.

## Manual Real LLM Smoke

The default CLI path remains local:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай 2 короткие сказки про лису для 5 лет." --count 2
```

To run Stage 2 through the configured real LLM provider, pass `--executor llm` and provide LLM settings through env or `.env`:

```bash
export LLM_PROVIDER=gptunnel
export GPTTUNNEL_API_KEY=...
export GPTTUNNEL_BASE_URL=https://gptunnel.ru/v1
export LLM_MODEL=gpt-4o-mini
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай 2 короткие сказки про лису для 5 лет." --count 2 --executor llm
```

Expected output is `completion_status: completed_enough` when enough candidates pass validation, or `completion_status: completed_with_shortage` with `shortage_status` explaining why fewer texts were approved. No image, animation, visual QA, or Stage 3 output is produced.

If `--executor llm` is requested and required provider config is missing, the CLI exits non-zero before creating a session:

```text
error: GPTTUNNEL_API_KEY is required when --executor llm uses provider gptunnel.
```

Optional debug artifacts for Stage 2 LLM prompts (includes `layer_grounding.bodies` proof):

```bash
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай 1 правдивую историю про лису для 5 лет." --count 1 --executor llm --debug-llm
```

Artifacts: `output/stage1_2_mvp/<session_id>/debug/llm/001_candidate_text_generator.json` — prompt JSON must contain `TRUTH_BASE` body text.

## TRUTH manual checklist (`--executor llm`)

Required before marking master plan §3.3 fully `done` (does not block CI merge). Record `session_id` and pass/fail for each row.

### Requests

| # | Request | `count` |
|---|---------|---------|
| T1 | `Сделай 2 правдивых истории про лису для 5 лет.` | 2 |
| T2 | `Сделай 1 правдивую короткую историю про ёжика зимой в лесу для ребёнка 3 лет.` | 1 |
| T3 (control) | `Сделай 1 сказочную историю про лису для 5 лет.` | 1 |

### Pass criteria — TRUTH (T1, T2)

For every approved text:

- [ ] `truth_mode = TRUTH` in session state
- [ ] **No fairy opening** — reject if text contains: `жила-была`, `жил-был`, `в некотором царстве`, `однажды в сказочном`, `когда-то давным-давно`
- [ ] **No animal direct speech as fact** — reject if animal speaks with human dialogue (e.g. `лиса сказала:`, `ёжик ответил` as real event, not child imagination frame)
- [ ] Observable / realistic animal or child behavior; no factual magic
- [ ] Theme and main subject preserved vs request

Allowed: soft mood, child imagination framed explicitly (`мальчик представил, что…`, `на самом деле…`).

### Pass criteria — FAIRY_TALE control (T3)

- [ ] Pipeline completes with `approved_texts`
- [ ] Fairy framing **allowed** — post-check must **not** block solely because of сказочное вступление
- [ ] No regression vs pre-§3.3 FAIRY_TALE expectations

### Token note (lead Q5)

If `--debug-llm` shows grounding block consistently **> ~8K tokens**, record size in manual notes for follow-up cap (not an MVP blocker).

## Length manual checklist (`--executor llm`)

Prep for §3.5 structured pass. Record `session_id` and sentence count per approved `text`.

| # | Request | Expected `text` length |
|---|---------|------------------------|
| L1 | `Сделай 1 правдивую историю про ёжика для 3 лет.` | 3–4 sentences; short phrases |
| L2 | `Сделай 2 истории про лису для 5 лет.` | 3–5 sentences each |

Pass: deterministic post-check would accept; phrases age-appropriate (no long participial chains for age 3).

## Test Commands

Focused MVP smoke:

```bash
venv/bin/pytest tests/integration/test_stage1_2_mvp_smoke.py -q
```

LLM executor contract and wiring tests with scripted providers:

```bash
venv/bin/pytest tests/unit/test_stage2_llm_executor.py -q
venv/bin/pytest tests/integration/test_stage1_2_llm_executor_cli.py -q
```

Golden and negative regression smoke:

```bash
venv/bin/pytest tests/integration/test_stage1_2_golden_scenarios.py tests/integration/test_stage1_2_negative_scenarios.py -q
```

Stage 2 TRUTH enforcement (mock / LenientStage2Executor):

```bash
venv/bin/pytest tests/integration/test_stage1_2_truth_enforcement.py -q
```

Full regression suite:

```bash
venv/bin/pytest -q
```

## Status Interpretation

`waiting_user`: Stage 1 needs user input before Stage 2 may run.

`completed_enough`: requested approved text count was produced.

`completed_with_shortage`: Stage 2 ended with fewer approved texts than requested.

`stopped_unresolved_request`: Stage 1 could not make the request executable within MVP rules. This is a product stop, not a provider failure.

## MVP Product Defaults

Stage 1 applies these defaults when the user request is meaningful but omits explicit values:

| Parameter | MVP default | Notes |
|-----------|-------------|-------|
| `truth_mode` | `TRUTH` | Overridden when the request explicitly asks for сказка, миф, правда and similar signals. |
| `target_age` | `5` | Seed prompt layers exist only for ages **3** and **5**. No clarification is asked when age is missing. |

Follow-up backlog and known product/code gaps: `MVP_FOLLOW_UP_MASTER_PLAN.md`.

## Known MVP Limitations

- Stage 2 uses a local mock executor in the CLI unless `--executor llm` is passed.
- Real LLM output quality depends on provider JSON reliability; malformed JSON is rejected or treated conservatively rather than silently approved.
- No visualization, image generation, animation, visual QA, UI, or Stage 3 is invoked.
- Stage 1 interpretation is seed-scope heuristic logic and prompt registry lookup, not an exhaustive natural-language understanding layer.
- Stage 2 TRUTH on real LLM requires manual pass per **TRUTH manual checklist** above before §3.3 is closed in the master plan.
- CLI output is intentionally compact and does not print full prompt bodies or candidate pools.
