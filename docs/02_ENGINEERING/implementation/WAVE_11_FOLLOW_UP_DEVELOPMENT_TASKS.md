# Wave 11 Follow-Up Development Tasks

Status: draft for lead review after first real-LLM manual testing.

This note captures follow-up problems found after connecting the real LLM-backed Stage 2 executor. The goal is to fix known interpretation and constraint-following defects before expanding the manual test matrix.

## Context

Wave 11 connected the real `LLMStage2TextExecutor` and added debug artifacts for manual LLM runs. Manual testing showed that the executor wiring works, but two product-critical behavior classes need attention before broad testing:

1. user phrasing does not reliably resolve to known prompt layers;
2. selected prompt layers are not always enforced strongly enough by Stage 2 generation, scoring and validation.

Known reference sessions:

```text
Chukovsky style request:
session_id: 613742b6-fa7a-49fd-940f-e25df474f20d
request: Сделай 2 сказки про лису для 3 лет в стиле чуковского.

Truth mode request:
session_id: 5f0b5dc9-d459-4621-82a5-fd6304bb6f41
request: 2 правдивых истории про лису
```

## Problem 1: User Phrase To Known Layer Matching

The request:

```text
Сделай 2 сказки про лису для 3 лет в стиле чуковского.
```

should resolve the existing layer:

```text
prompts/truth_modes/FAIRY_TALE/styles/reference_labels/CHUKOVSKY_STYLE.md
```

Observed state:

```text
truth_mode: FAIRY_TALE
target_age: 3
text_style_base: None
substyle: None
resolved_layers: no CHUKOVSKY_STYLE
```

This is an implementation issue in Stage 1 / prompt lookup. The business logic and prompt registry already contain the Chukovsky reference label and aliases. The current implementation does not extract the user phrase into a supported `substyle` and does not resolve `CHUKOVSKY_STYLE`.

### Proposed Matching Algorithm

Use a layered matching pipeline:

```text
user text
-> normalize text
-> exact alias matching
-> phrase extraction
-> fuzzy alias matching
-> optional LLM fallback
-> registry verification
-> resolved layer or clarification/unresolved detail
```

Rules:

- LLM fallback may select only from known registry candidates.
- LLM fallback must not invent new styles, modes or layer ids.
- Every selected layer must pass registry verification.
- Applicability must be checked against current normalized fields, including `content_format`, `truth_mode`, `utility_mode` and `target_age`.
- If confidence is low or multiple candidates are close, ask for clarification or preserve as unresolved detail instead of silently selecting.

### RapidFuzz Discussion

RapidFuzz is a good candidate for deterministic fuzzy matching because it is fast, local and testable.

Suggested approach:

1. Normalize user text and layer aliases:
   - lowercase;
   - `ё -> е`;
   - strip punctuation;
   - collapse whitespace;
   - optionally normalize common Russian endings for extracted phrases.

2. Extract likely style phrases:
   - `в стиле ...`;
   - `как у ...`;
   - `как ...`;
   - `по ...`;
   - `похоже на ...`.

3. Compare extracted phrase against registry aliases using RapidFuzz:
   - `WRatio` for general short phrase matching;
   - `token_set_ratio` when word order varies;
   - direct normalized substring match remains higher priority than fuzzy score.

4. Suggested thresholds:

```text
>= 90: auto match if applicability passes
75-89: candidate for LLM fallback or clarification
< 75: unresolved
```

5. Ambiguity handling:
   - if the top two candidates are close, do not choose silently;
   - clarify or use LLM fallback with only those candidates.

Examples to support:

```text
3 сказки про лису в стиле чуковского
3 сказки про лису по чуковскому
3 сказки про лису как чуковский
3 сказки про лису как у чуйковкого
```

## Problem 2: Truth Mode Is Recognized But Not Enforced

The request:

```text
2 правдивых истории про лису
```

was correctly interpreted by Stage 1:

```text
truth_mode: TRUTH
resolved_layers: TRUTH_BASE, NATURALISTIC_ANIMAL_STORY, TRUTH_ANIMAL_FOX
```

But Stage 2 approved texts with fairy-tale phrasing and logic:

```text
Жила-была лиса по имени Лисичка...
старый сундук...
жила-бывала хитрая рыжая лиса...
```

This is a Stage 2 quality and validation issue. The selected truth layers exist in state, but their operational constraints are not enforced strongly enough during generation, scoring and validation.

### Required Direction

Strengthen Stage 2 grounding for active prompt layers:

- generator must receive clear TRUTH constraints;
- scorer must fail `truth_fit` for fairy-tale markers and human-like animal behavior in `TRUTH`;
- validator must reject or request revision when `TRUTH` text contains fairy-tale framing, speaking animals, human social reasoning by animals, impossible objects/events, or magical story hooks;
- refiner must convert violations into observable realistic animal behavior.

The fix should preserve the current safety rule: do not silently approve malformed or contradictory LLM output.

## Shared Systemic Observation

The two bugs are not identical, but they point to a common weakness:

```text
The pipeline preserves prompt layer ids better than it operationalizes prompt layer semantics.
```

In product terms:

```text
The system may know which rule layer was selected, but the generated result does not always behave as if that rule was active.
```

For Chukovsky, the selected layer never reaches state. For TRUTH, the layer reaches state but is not enforced reliably by Stage 2.

## Additional Product Issues To Record

These are not the first fixes, but should be recorded for business logic follow-up.

### Result Length Is Uncontrolled

Approved texts can be several paragraphs long. The current MVP has no explicit business rule for target text length by age and format.

Needs decision:

- max sentences;
- max paragraphs;
- max characters;
- whether overlength text should be rejected, refined, or accepted with warning.

### Missing Age Defaults To 5

If the user does not specify age, Stage 1 currently defaults to `target_age=5` without asking clarification.

Needs decision:

- keep default age 5 for MVP;
- ask clarification when age is missing;
- use default only in specific modes.

### Cross-Session Variety Is Not Controlled

Within a session, candidate topics are deduplicated. Across separate sessions with similar requests, topic ordering and themes may repeat.

Needs decision:

- acceptable for MVP;
- introduce random seed;
- introduce recent-session memory;
- add novelty instructions across runs.

### Approved Does Not Yet Mean Strong Product Fit

Current approval may pass technical shape and some validation, but still miss user-visible expectations such as truth mode, style, tone, or length.

Needs stronger business-facing acceptance criteria for `approved_texts`.

## Suggested Implementation Order

1. Add deterministic and fuzzy prompt-layer matching for supported style/substyle aliases, starting with `CHUKOVSKY_STYLE`.
2. Add regression tests for Chukovsky phrase variants and typo handling.
3. Strengthen Stage 2 prompt grounding for active truth/style layer semantics.
4. Add regression tests for `TRUTH` mode so fairy-tale markers cannot reach `approved_texts`.
5. Re-run the lead's broader manual prompt test matrix only after the two known defects are fixed.
