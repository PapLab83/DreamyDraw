# Implementation Readiness

## Implementation Order

Recommended implementation order:

1. Replace old `SessionState` orchestration fields with new models.
2. Implement `PromptRegistry`.
3. Implement `PromptComposer`.
4. Implement Stage 1 nodes and routing.
5. Implement CLI/API interrupt handlers for Stage 1.
6. Implement Stage 2 candidate generation.
7. Implement deduplication/scoring/ranking.
8. Implement validation/refinement loop.
9. Implement `ApprovedTextSelector` and shortage object.
10. Connect seed prompt layers.
11. Add golden scenario tests.
12. Only after Stage 1-2 are stable, write separate Stage 3 visual pipeline spec.

---

## Golden Scenario Acceptance

At minimum, implementation must pass scenarios for:

- правдивые истории про ёжика зимой для 3 лет;
- сказочные истории про лису для 5 лет;
- мифологическая мягкая история про солнце или ветер;
- поучительная история про мытьё рук;
- поучительная сказка про переход через дорогу;
- поучительная история про незнакомца и конфету;
- провокационный safety case про незнакомца/конфету, где teaching goal не должен превращаться в небезопасный совет;
- fallback `PARROT` for `какаду` with unresolved detail;
- multiple subjects with explicit `subject_continuity_policy`;
- character request with `character_profile`;
- empty/meaningless input;
- contradiction `TRUTH` + fantastic hard detail;
- unsupported hard style requirement;
- refiner must not change theme/main subject/character profile;
- selector must use validated candidate versions;
- accepted draft создаёт item в `validated_candidate_versions` даже без refinement;
- validator/refiner uses `validation_loop_state`, чтобы revised versions проверялись вместо stale drafts;
- validator/refiner stage prompt contexts являются dynamic per candidate/version/attempt;
- execution lookup missing source ведёт в reresolve/clarify/stop и не делает silent layer swap;
- interrupt restart сохраняет `completion_status = waiting_user` и `pending_interrupt`;
- recovered interrupt resume не увеличивает clarification attempts дважды;
- HITL fallback approved text маркируется `hitl_fallback_accepted`;
- `retry_generation` очищает active `shortage.fallback_acceptance_policy`.

Acceptance is behavioral, not snapshot text equality.

---

## Completion Criteria

The orchestrator implementation is complete when:

- active graph starts at Stage 1 analysis;
- all Stage 1 nodes persist state;
- all clarification branches route back to analysis/classification;
- `normalized_request` is separate from process metadata;
- `PromptRegistry` validates metadata and stable ids;
- resolved layer `type` uses `PROMPT_FILE_CONTRACT.md` enum and orchestration-specific meaning is stored in `role`;
- metadata lookup returns utility mode/topic and audience/result language candidates when applicable;
- `candidate_layer_resolution` is the owner for applying lookup-derived normalized field updates;
- `PromptComposer` creates stage-specific contexts;
- `PromptComposer` includes utility mode, utility topic when applicable, audience language and result language layers;
- teaching topics are represented in `normalized_request.utility_topic` and resolved prompt layers when registry match exists;
- Stage 2 generates candidate pool with default count 20;
- duplicate themes are filtered or marked;
- hard gates can exclude candidates before approval;
- validation/refinement loop respects per-candidate counters;
- `ranker` initializes `validation_loop_state` idempotently before first validator entry;
- validation/refinement loop uses `validation_loop_state` для active candidate/version/source;
- `candidate_validator` validates revised versions from `refined_candidate_versions` after refiner output;
- refiner preserves immutable fields;
- selector читает normal approved text content из `validated_candidate_versions`, а не из `candidate_texts` или `ranked_candidates`;
- selector may prepare `safe_fallback_candidates` when shortage occurs;
- selector может включить HITL fallback только из `safe_fallback_candidates` плюс explicit `shortage.fallback_acceptance_policy`, when interactive shortage HITL is enabled;
- shortage fallback resume payload includes accepted safe fallback ids and known-issues acknowledgement when interactive shortage HITL is enabled and applicable;
- selector не превращает HITL fallback union в `completed_enough` или `shortage.status = "enough"`;
- selector не возвращает пользователя в shortage interrupt повторно после `accept_fewer` или durable `shortage.fallback_acceptance_policy`;
- accepted draft создаёт объект `validated_candidate_versions`;
- execution lookup failure никогда не делает silent prompt layer swap;
- interrupt nodes сохраняют `completion_status = waiting_user` и `pending_interrupt`;
- final output is `approved_texts`;
- selector always writes `shortage`, including `shortage.status = "enough"` on successful full output;
- shortage is explicit when output count is not met;
- execution lookup returns status envelope and never behaves as a plain layer-list lookup;
- no image/animation node is part of current graph;
- `stage_status` distinguishes not started, completed-empty result and failed stages for recovery;
- `retry_generation` resets Stage 2 `stage_status` entries, hashes and timestamps;
- `retry_generation` removes dynamic Stage 2 `stage_prompt_context.entries` and invalid stale static entries;
- Stage 1 recovery does not proceed to prompt context preparation until final parameter validation has passed;
- JSONStorage can restore meaningful progress, including non-interrupt Stage 2 progress without restarting from Stage 1;
- Langfuse traces contain enough debug refs to inspect approved text decisions.
