# Seed Prompt Metadata

Статус: временный detail document для `SEED_PROMPT_INVENTORY.md`.

Этот документ фиксирует общие metadata decisions, naming conventions и body conventions для seed prompt files.

## 1. Metadata Decision: `role`

`role` is an optional prompt-file metadata field in `PROMPT_FILE_CONTRACT.md`.

For this seed set, `role` is required when orchestration meaning would otherwise be ambiguous:

| Layer kind | Required `type` | Required `role` |
| --- | --- | --- |
| Content format | `format` | `content_format` |
| Utility mode | `utility` | `utility_mode` |
| Utility topic | `utility` | `utility_topic` |
| Audience language | `language` | `audience_language` |
| Result language | `language` | `result_language` |
| Stage profile | `stage` | orchestration stage role, for example `candidate_text_generator` |
| Validator | `validator` | `candidate_validator` |
| Refiner | `refiner` | `candidate_refiner` |

`role` must never replace `type`. `type` must stay one of the enum values from `PROMPT_FILE_CONTRACT.md`.

For `truth_mode`, `age`, `entity`, `style` and `substyle`, `role` may be omitted unless a specific layer needs it for lookup/composition clarity.

## 2. Naming And Namespace Conventions

Use stable UPPER_SNAKE `id` values. File paths in detail documents are proposed source paths; writers may adjust file names only if the resulting `namespace`, `id` and lookup notes remain clear.

Recommended source root for prompt files:

```text
prompts/
```

Common metadata requirements for every prompt file:

- `id`;
- `type`;
- `role` when required by section 1;
- `namespace`;
- `name`;
- `aliases`;
- `applies_to`;
- `short_description`;
- `constraints`.

Common body requirements:

- explain when the layer applies;
- explain what the layer adds;
- explain what the layer prohibits;
- describe how it combines with truth mode, utility, age, style, subjects and stage prompts;
- avoid duplicating another layer's full prompt;
- avoid changing immutable normalized fields.
