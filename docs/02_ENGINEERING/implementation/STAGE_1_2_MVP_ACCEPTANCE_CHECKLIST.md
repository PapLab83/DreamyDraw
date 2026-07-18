# Stage 1-2 MVP Acceptance Checklist

Status: Wave 11 acceptance checklist.

Use this checklist after running the manual smoke commands and regression suite from `STAGE_1_2_MVP_RUNBOOK.md`.

## Checklist

- [ ] Stage 1 interpretation produces a durable normalized request.
- [ ] Prompt layer resolution uses registry layers plus explicit unresolved/fallback details.
- [ ] Stage 2 produces durable `approved_texts` on the happy path.
- [ ] Empty request clarification and resume work from the CLI.
- [ ] Unsupported hard requirements do not silently pass.
- [ ] Truth/fantasy contradictions do not produce approved text.
- [ ] Golden scenarios pass.
- [ ] Negative scenarios pass.
- [ ] CLI MVP smoke passes.
- [ ] Stage 1-2 MVP does not use image generation, animation, visual pipeline, legacy `fast/check`, or Stage 3.
- [ ] Default Stage 1-2 CLI path does not call external LLM/image providers.
- [ ] `--executor llm` calls only the configured LLM provider and fails clearly if required config is missing.
- [ ] Automated tests use scripted/mock providers only and do not call external providers.
- [ ] Observability trace refs exist and do not persist full prompt bodies by default.
- [ ] Full `venv/bin/pytest -q` suite passes.
- [ ] Known limitations are documented in the runbook.

## Commands To Record

```bash
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай 2 поучительные сказки про лису и переход через дорогу для 5 лет." --count 2
venv/bin/python scripts/run_stage1_2_mvp.py ""
venv/bin/python scripts/run_stage1_2_mvp.py --session <session_id> --resume "Сделай сказку про лису для 5 лет."
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай сказку про лису для 5 лет строго в стиле Дисней."
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай правдивую историю про лису для 5 лет, обязательно чтобы она летала на волшебном ковре."
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай 2 короткие сказки про лису для 5 лет." --count 2 --executor llm
venv/bin/pytest tests/unit/test_stage2_llm_executor.py -q
venv/bin/pytest tests/integration/test_stage1_2_llm_executor_cli.py -q
venv/bin/pytest tests/integration/test_stage1_2_mvp_smoke.py -q
venv/bin/pytest tests/integration/test_stage1_2_golden_scenarios.py tests/integration/test_stage1_2_negative_scenarios.py -q
venv/bin/pytest -q
```

## Acceptance Boundary

Accepted output is text-only and ends at `approved_texts`. Any behavior that starts image generation, animation, visual validation, or Stage 3 is outside this MVP acceptance. External LLM provider calls are allowed only in explicit manual `--executor llm` runs, never in automated tests or default CLI smoke.
