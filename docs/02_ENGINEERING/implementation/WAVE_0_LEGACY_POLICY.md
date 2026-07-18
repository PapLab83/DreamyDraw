# Wave 0 Legacy Policy

Status: active for Wave 1 planning.

This note fixes the repository boundary before the clean-slate Stage 1-2 implementation.

## Decisions

1. Legacy source files stay in place during Wave 0.
2. The new active graph must not import or register legacy nodes.
3. Physical backup or movement of legacy source files is deferred until after the Stage 1 runnable smoke checkpoint.
4. Public compatibility APIs may remain temporarily, but old orchestration fields must become adapter input only in later waves.
5. `image_style` may be preserved as downstream `visual_preferences`, but it must not trigger image generation in Stage 1-2.
6. The source of truth for `completion_status` values is `docs/02_ENGINEERING/orchestration/03_STATE_AND_RECOVERY.md`.
7. `current_node` is a debug/progress marker, not the primary recovery router.

## Legacy Reference Surface

Treat the current `PromptBuilder`, planning/validation/content/safety nodes, `fast/check` semantics, and image generation path as legacy/reference material only. They may inform migration adapters or compatibility behavior, but they are not the foundation for the new Stage 1-2 graph.

The current MVP implementation boundary ends at `SessionState.approved_texts`. Stage 3, image prompt execution, image generation, animation, visual validation, and visual pipeline behavior remain out of scope for the Stage 1-2 implementation waves.
