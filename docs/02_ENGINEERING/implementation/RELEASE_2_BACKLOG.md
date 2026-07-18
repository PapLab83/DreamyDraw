# Release 2 Backlog

Status: active handoff from Release 1 cleanup.
Audience: product lead, engineering, prompt agent.

## Purpose

This document keeps Release 2+ work visible after Release 1 is accepted. Release 1 is the Stage 1-2 text-only MVP: request interpretation, prompt layer composition, text generation/checking and final `approved_texts`.

Anything below is **not** Release 1 cleanup unless explicitly re-scoped by the lead.

## Concrete Known Inputs From Wave 11

These observations must remain visible when planning Release 2. They are not just historical notes; they are concrete inputs for semantic resolver, prompt architecture and Stage 2 quality work.

### Known Manual Sessions

| Case | Session | Request | Observed problem | Current status |
| --- | --- | --- | --- | --- |
| Chukovsky style lookup | `613742b6-fa7a-49fd-940f-e25df474f20d` | `Сделай 2 сказки про лису для 3 лет в стиле чуковского.` | Existing `CHUKOVSKY_STYLE` layer did not reach normalized state / resolved layers. | Basic Stage 1 matching was later improved; keep as regression input for semantic resolver/reference labels. |
| TRUTH enforcement | `5f0b5dc9-d459-4621-82a5-fd6304bb6f41` | `2 правдивых истории про лису` | Stage 1 selected `TRUTH`, but Stage 2 approved fairy-tale framing such as `Жила-была...`. | Deterministic TRUTH post-check exists; real LLM manual checklist remains an important quality gate. |

Primary historical inputs:

- `WAVE_11_FINAL.md`
- `WAVE_11_FOLLOW_UP_DEVELOPMENT_TASKS.md`
- `STAGE_1_2_MVP_RUNBOOK.md` manual TRUTH and length checklists
- any future manual LLM report created from the Wave 11 matrix

### Wave 11 Manual Matrix To Preserve

Use these requests as Release 2 regression/diagnostic seeds before redesigning interpretation, prompt architecture or Stage 2 quality:

1. `Сделай 2 сказки про лису для 5 лет`
2. `Сделай 2 правдивые истории про лису для 5 лет`
3. `Сделай 2 сказки про лису`
4. `2 сказки`
5. `Сделай сказку про лису для 5 лет в стиле Чуковского`
6. `Сделай сказку про лису для 5 лет строго в стиле Дисней`
7. `Сделай сказку про лису для 5 лет в акварельном настроении`
8. `Сделай правдивую историю про лису для 5 лет, обязательно чтобы она летала на волшебном ковре`
9. `Сделай 2 поучительные сказки про лису и переход через дорогу для 5 лет`
10. `Сделай поучительную историю про незнакомца и конфету для ребёнка 5 лет`
11. `Сделай 3 истории про лису, зайца и белку зимой, чтобы герои не исчезали`
12. `Сделай историю про бельчонка Тима, он смелый и любит жёлуди, для 5 лет`
13. `Сделай правдивую историю про попугая какаду для 5 лет`
14. `Сделай мягкую мифологическую историю про солнце и ветер для ребёнка 5 лет`
15. `Сделай 2 сказки про лису для 5 лет` - run three times and compare diversity.

### Product/Engineering Decisions Still Open

- Missing age: keep MVP default `target_age=5` or ask clarification?
- Length: define per-age sentence/paragraph/character limits for product acceptance, not just technical post-checks.
- Cross-session variety: decide whether repeated similar requests need diversity memory, seeding or prompt-level novelty rules.
- Approved text quality: define user-facing acceptance criteria beyond JSON shape and technical gates.
- Layer semantics: make sure selected prompt layers are operationalized by generation, scoring, validation and refiner behavior.

## Release 2 Candidate Themes

### 1. Semantic Resolver And Parameter Extraction

- Standardize parameter extraction across rules, aliases, normalization, fuzzy matching and narrow LLM fallback.
- Design a full semantic resolver for `truth_mode`, `utility_mode`, age, subjects, styles, substyles, hard details and soft preferences.
- Define clarification behavior for ambiguous or unsupported requirements.
- Keep deterministic behavior testable; real provider calls must remain outside automated tests.

Status: pending architecture decision.

### 2. Prompt Architecture

- Review the final prompt payload that is actually sent to the LLM.
- Separate animal/entity constraints from style/substyle constraints where useful.
- Decide whether Russian folk specificity belongs in animal layers, style layers or a dedicated substyle layer.
- Simplify the generation prompt if diagnostics show overload.
- Keep `prompts/**/*.md` as the active prompt asset root; `docs/03_PROMPTS/**` is legacy reference only.

Status: pending prompt/engineering design.

### 3. Animal And Character Layers

- Redesign animal prompts only after Release 1 acceptance.
- Do not make the current fox layer the unquestioned template for all animals.
- Define how TRUTH animals differ from FAIRY_TALE animals.
- Clarify when an animal is a subject vs a character.
- Expand animal coverage only through a scoped seed/backlog task.

Known examples:

- fox;
- hedgehog;
- squirrel;
- hare;
- parrot/cockatoo fallback;
- future animals such as cat, horse, mouse and others.

Status: pending prompt architecture.

### 4. Reference Styles And Chukovsky

- Improve handling and quality of reference labels such as `CHUKOVSKY_STYLE`.
- Decide which reference styles are supported, blocked or clarification-only.
- Keep style quality work separate from Release 1 cleanup.

Status: candidate for prompt quality work.

### 5. Educational And Product Domains

Prioritize future knowledge/utility areas:

- animals and nature;
- city infrastructure and road safety;
- hygiene and everyday habits;
- strangers/candy and sensitive safety stories;
- professions;
- energy, water supply and simple science;
- English-learning cards or stories.

`docs/01_PRODUCT/APPENDIX_ENGLISH.md` contains an early English-learning concept. If kept, fold the useful ideas into product vision or a scoped Release 2 feature brief before removing it from active navigation.

Status: pending product prioritization.

### 6. Stage 2 Quality

- Tune temperature/model/stage policies.
- Tune validator strictness, scorer behavior and refiner loops.
- Improve truth, fairy-tale, length and expressiveness quality based on manual LLM sessions.
- Explore the pipeline: factual base content -> child adaptation -> scorer/validator/post-check.

Status: candidate for quality sprint.

### 7. Diversity And Content Sources

- Define cross-session diversity expectations.
- Consider plot banks, seeded subsets, randomizer behavior or factual content banks.
- Keep any knowledge base/RAG/vector store work out of Release 1 cleanup.

Status: pending product/architecture decision.

### 8. Visual Product: Image, Animation And Stage 3

- Design Stage 3 as a downstream consumer of `approved_texts`.
- Specify image generation, visual QA, image prompt execution and media storage separately.
- Explore story card series, picture riddles, animation loops and learning micro-cartoons.
- Consider web, mobile, Telegram or another visual client before treating these as full product workflows.

Status: future stage, not Release 1.

## Deferred From Release 1 Cleanup

Do not do these during Release 1 cleanup:

- rewrite animal prompt architecture;
- align all animals to the current fox;
- extract Russian folk style into a new component;
- implement semantic resolver;
- perform deep final prompt diagnostics unless it directly supports Release 1 acceptance;
- connect image generation, animation or Stage 3;
- add new animals, objects, substyles or domains as product expansion.

## Suggested Inputs To Review Later

- `docs/02_ENGINEERING/TARGET_ORCHESTRATION_LOGIC.md`
- `docs/02_ENGINEERING/PROMPT_AGENT_ROLE.md`
- `docs/02_ENGINEERING/PROMPT_CONTRACTS_AND_SEED_SCOPE.md`
- `docs/02_ENGINEERING/prompt_preparation/**`
- `docs/02_ENGINEERING/implementation/WAVE_11_FINAL.md`
- `docs/02_ENGINEERING/implementation/WAVE_11_FOLLOW_UP_DEVELOPMENT_TASKS.md`
- other historical `WAVE_*.md` and `IMPLEMENTATION_PLAN_*.md` after important decisions are folded into current docs.
