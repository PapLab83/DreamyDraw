# Observability

## Observability

Every node should be traced as a separate Langfuse span.

Root trace metadata:

- `session_id`;
- user id if available;
- raw input;
- normalized summary;
- final status;
- current node;
- shortage status.

Stage 1 span metadata:

- classification;
- confidence summary;
- clarification reason;
- clarification attempts;
- selected option id/freeform marker;
- resolved layer ids;
- fallback layer ids;
- unresolved details;
- final validation status;
- preview hash/text summary.

Stage 2 span metadata:

- candidate count requested/generated;
- duplicate count;
- hard gate failure counts;
- score component summaries;
- ranked candidate ids;
- validation attempts;
- refinement attempts;
- approved count;
- shortage reason.

Prompt trace metadata:

- layer ids;
- source paths;
- prompt hashes;
- stage context hash;
- model/provider;
- token and cost metadata if available.

Approved text `trace_refs`:

```json
{
  "trace_id": "...",
  "generator_span_id": "...",
  "scorer_span_id": "...",
  "validator_span_ids": [],
  "refiner_span_ids": [],
  "prompt_context_hash": "...",
  "candidate_id": "c01",
  "version_id": "c01_v1"
}
```

---
