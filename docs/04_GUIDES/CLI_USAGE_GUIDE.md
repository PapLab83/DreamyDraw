# CLI Usage Guide - DreamyDraw

Status: Release 1 CLI guide.

## 1. Active Release 1 CLI

Use the Stage 1-2 MVP runner:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай 2 сказки про лису для 5 лет." --count 2
```

Release 1 output is text-only and ends at `approved_texts`.

Expected shape:

```text
session_id: ...
completion_status: completed_enough
approved_count: 2
approved_texts:
...
```

## 2. Arguments

| Argument | Meaning |
| --- | --- |
| `request` | Raw user request in natural language. |
| `--count N` | Requested number of approved texts. Overrides count inferred from the request. |
| `--session ID` | Resume an existing session. |
| `--resume TEXT` | Clarification answer for an existing session. |
| `--output-dir PATH` | Session storage directory. Defaults to `output/stage1_2_mvp` or `DREAMYDRAW_STAGE1_2_OUTPUT_DIR`. |
| `--executor mock|llm` | Stage 2 executor. Default: `mock`. |
| `--provider NAME` | LLM provider for `--executor llm`. |
| `--model NAME` | LLM model for `--executor llm`. |
| `--debug-llm` | Write LLM prompt/response debug artifacts for manual analysis. |

## 3. Default Executor

The default path is local:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай 1 правдивую историю про лису для 5 лет."
```

It must not call a real LLM or image provider.

## 4. Manual LLM Executor

The LLM executor is explicit and manual-only:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай 2 сказки про лису для 5 лет." --count 2 --executor llm
```

Provider configuration must be available through env or `.env`. Automated tests use scripted/mock providers only.

## 5. Clarification And Resume

Empty or unsupported input may pause for clarification:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py ""
venv/bin/python scripts/run_stage1_2_mvp.py --session <session_id> --resume "Сделай сказку про лису для 5 лет."
```

## 6. Legacy CLI

`main.py`, `--mode fast`, `--mode check`, `--image-style` and the old text->image flow belong to the deprecated legacy pipeline. They are not the Release 1 acceptance path.

Do not use the legacy CLI as a model for new Stage 1-2 work.
