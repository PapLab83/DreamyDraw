from pathlib import Path

import pytest

from src.core.prompts.cultural_roots import (
    CulturalPromptRootError,
    resolve_cultural_prompt_root,
)

PROMPTS_ROOT = Path(__file__).resolve().parents[2] / "prompts"


def test_russian_folk_resolves_to_allowlisted_prompt_root():
    selected = resolve_cultural_prompt_root(PROMPTS_ROOT, "RUSSIAN_FOLK")

    assert selected == PROMPTS_ROOT / "cultural_contexts" / "russian_folk"


def test_unknown_context_is_rejected_before_registry_load():
    with pytest.raises(CulturalPromptRootError, match="Unsupported cultural context"):
        resolve_cultural_prompt_root(PROMPTS_ROOT, "UNKNOWN")
