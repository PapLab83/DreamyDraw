# CLI Usage Guide - DreamyDraw

Status: Release 2 CLI guide.

## 1. Active Release 2 CLI

Use the Stage 1-2 MVP runner:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py "Короткие истории про лису" --count 2 --age 5 --truth-mode FAIRY_TALE --cultural-context RUSSIAN_FOLK --utility-mode NARRATIVE
```

Release 2 output is text-only and ends at `approved_texts`.

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
| `--count N` | Approved text count, `1..10`; default `3`. |
| `--age 3|5` | Target age; default `5`. |
| `--truth-mode TRUTH|FAIRY_TALE` | Truth mode; default `TRUTH`. |
| `--cultural-context RUSSIAN_FOLK` | Prompt cultural root; default and only Release 2 value `RUSSIAN_FOLK`. |
| `--utility-mode NARRATIVE|TEACHING` | Result purpose; default `NARRATIVE`. |
| `--session ID` | Resume an existing session. |
| `--resume TEXT` | Clarification answer for an existing session. |
| `--output-dir PATH` | Session storage directory. Defaults to `output/stage1_2_mvp` or `DREAMYDRAW_STAGE1_2_OUTPUT_DIR`. |
| `--executor mock|llm` | Stage 2 executor. Default: `mock`. |
| `--provider NAME` | LLM provider for `--executor llm`. |
| `--model NAME` | LLM model for `--executor llm`. |
| `--debug-llm` | Write LLM prompt/response debug artifacts for manual analysis. |

## 3. Default Executor

The default path is local. Controlled-looking words in `request` do not override CLI/config/defaults:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py "История про лису"
```

It must not call a real LLM or image provider.

## 4. Manual LLM Executor

The LLM executor is explicit and manual-only:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py "Истории про лису" --count 2 --age 5 --truth-mode FAIRY_TALE --executor llm
```

Provider configuration must be available through env or `.env`. Automated tests use scripted/mock providers only.

## 5. Clarification And Resume

Empty or unsupported input may pause for clarification:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py ""
venv/bin/python scripts/run_stage1_2_mvp.py --session <session_id> --resume "Сделай сказку про лису для 5 лет."
```

## 6. Legacy CLI

`main.py`, `--mode fast`, `--mode check`, `--image-style` and the old text->image flow belong to the deprecated legacy pipeline. They are not the Release 2 acceptance path.

Do not use the legacy CLI as a model for new Stage 1-2 work.
