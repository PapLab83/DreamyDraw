# Prompt Structure Standard - DreamyDraw

Status: Release 1 prompt asset guide.

## 1. Active Prompt Root

Release 1 prompt assets live in:

```text
prompts/
```

They are loaded by `src/core/prompts/registry.py` and composed by `src/core/prompts/composer.py`.

Legacy `docs/03_PROMPTS/**` assets and the old `src/core/prompt_builder.py` runtime module were removed during Release 1 cleanup. Create and edit Release 1 prompt assets only in `prompts/**`.

## 2. Prompt Layer Shape

Each active prompt layer is a Markdown file with:

1. YAML front matter metadata.
2. A human-readable body used as the layer text.

The exact metadata contract is defined in:

```text
docs/02_ENGINEERING/contracts/PROMPT_FILE_CONTRACT.md
```

Related contracts:

```text
docs/02_ENGINEERING/contracts/PROMPT_LOOKUP_CONTRACT.md
docs/02_ENGINEERING/contracts/PROMPT_COMPOSITION_CONTRACT.md
docs/02_ENGINEERING/contracts/SEED_SCOPE.md
```

## 3. Composition Flow

```text
PromptRegistry.load(prompts/)
  -> metadata lookup
  -> resolved / fallback / unresolved details
  -> PromptComposer stage context
  -> Stage 2 executor runtime prompt
```

Prompt bodies are loaded explicitly at runtime. Full prompt bodies should not be persisted in normal session trace refs.

## 4. Editing Guidance

- Keep prompt changes scoped to the active `prompts/` tree.
- Do not rewrite animal/style architecture during Release 1 cleanup.
- Do not add image, animation or Stage 3 prompt paths for Release 1.
- If a prompt issue requires Python policy changes, hand it off to engineering instead of hiding the requirement in an `.md` file.

For prompt-agent onboarding and handoff rules, see:

```text
docs/02_ENGINEERING/PROMPT_AGENT_ROLE.md
```
