# Prompt Guide - DreamyDraw

Status: Release 1 prompt guide.

## 1. Active Prompt System

Release 1 uses Markdown prompt layers under:

```text
prompts/
```

The active code path is:

```text
PromptRegistry
  -> prompt lookup
  -> PromptComposer
  -> Stage 2 text executor
```

Do not add Release 1 prompt assets to `docs/03_PROMPTS/**`; that tree belongs to the legacy `PromptBuilder` pipeline.

## 2. What Prompt Layers Control

Prompt layers may describe:

- content format;
- truth mode;
- utility mode/topic;
- target age;
- language;
- entity/subject constraints;
- style or reference label;
- stage profile;
- validator/refiner behavior.

The exact file metadata contract is in:

```text
docs/02_ENGINEERING/contracts/PROMPT_FILE_CONTRACT.md
```

## 3. Release 1 Boundary

Release 1 prompt work is text-only and must end at `approved_texts`.

Do not add prompt paths for:

- image generation;
- image prompt execution;
- animation;
- visual QA;
- Stage 3.

Those are Release 2+ topics tracked in:

```text
docs/02_ENGINEERING/implementation/RELEASE_2_BACKLOG.md
```

## 4. Editing Rules

- Keep changes scoped to the active prompt layer you are improving.
- Do not redesign all animal prompts during Release 1 cleanup.
- Do not move Russian folk style into a new architecture during Release 1 cleanup.
- Preserve prompt metadata compatibility with `PromptRegistry`.
- If the problem is caused by routing, post-checks or task suffixes in Python, hand it off to engineering.

## 5. Prompt Agent

For deeper prompt-quality work and handoff format, use:

```text
docs/02_ENGINEERING/PROMPT_AGENT_ROLE.md
```
