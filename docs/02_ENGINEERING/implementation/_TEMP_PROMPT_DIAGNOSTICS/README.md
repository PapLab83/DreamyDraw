# Temporary generator prompt diagnostics

This directory contains reproducible Wave 14 snapshots of the exact prompt passed to the local provider boundary by `LLMStage2TextExecutor.generate_candidates()`.

The Markdown cases are diagnostic artifacts only. They are not prompt assets, are not a source of truth, and are outside `prompts/**`, so `PromptRegistry` must never load them.

## Reproduce

From the repository root:

```bash
venv/bin/python docs/02_ENGINEERING/implementation/_TEMP_PROMPT_DIAGNOSTICS/export_generator_prompts.py
```

Generate only the case 02 prototype:

```bash
venv/bin/python docs/02_ENGINEERING/implementation/_TEMP_PROMPT_DIAGNOSTICS/export_generator_prompts.py --case 02
```

The exporter:

- runs the active Stage 1 normalization and prompt-resolution path;
- loads only `prompts/cultural_contexts/russian_folk/`;
- invokes the real `candidate_text_generator` node and `LLMStage2TextExecutor`;
- captures the exact prompt at a local in-memory provider boundary;
- never initializes or calls an external LLM provider;
- verifies that exact prompt artifacts are byte-for-byte equal to the captured prompt and have the recorded SHA-256 hash;
- overwrites the three generated case files deterministically apart from the diagnostic timestamp.

Generated files:

- `01_FAIRY_FOX_BASE.md`
- `02_FAIRY_FOX_RUSSIAN_FOLK.md`
- `02_FAIRY_FOX_RUSSIAN_FOLK_EXACT_PROMPT.md` — raw byte-exact provider argument without headings, fences or a trailing newline;
- `03_FAIRY_FOX_CHUKOVSKY.md`

The exporter itself is temporary diagnostic tooling. This whole directory must be removed after prompt analysis and the corresponding prompt-redesign implementation are complete. That removal belongs to the cleanup phase of the next relevant wave.
