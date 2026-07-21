from __future__ import annotations

from pathlib import Path

CULTURAL_CONTEXT_DIRECTORIES = {
    "RUSSIAN_FOLK": "russian_folk",
}


class CulturalPromptRootError(ValueError):
    pass


def resolve_cultural_prompt_root(
    prompts_root: str | Path,
    cultural_context: str,
) -> Path:
    context = str(cultural_context).strip().upper()
    directory = CULTURAL_CONTEXT_DIRECTORIES.get(context)
    if directory is None:
        raise CulturalPromptRootError(f"Unsupported cultural context: {cultural_context}")

    base_root = Path(prompts_root)
    if base_root.name == directory and base_root.parent.name == "cultural_contexts":
        selected_root = base_root
    else:
        selected_root = base_root / "cultural_contexts" / directory

    if not selected_root.is_dir():
        raise CulturalPromptRootError(
            f"Prompt root for {context} does not exist: {selected_root}"
        )
    return selected_root
