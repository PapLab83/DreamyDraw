from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPT_PATH = Path(__file__).resolve()
OUTPUT_DIR = SCRIPT_PATH.parent
PROJECT_ROOT = SCRIPT_PATH.parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.graph.state import to_graph_state  # noqa: E402
from src.core.nodes.stage2 import candidate_text_generator  # noqa: E402
from src.core.stage1_runner import Stage1Runner  # noqa: E402
from src.core.stage2_llm_executor import LLMStage2TextExecutor  # noqa: E402
from src.providers.base import BaseLLMProvider  # noqa: E402


PROMPTS_ROOT = PROJECT_ROOT / "prompts"
SELECTED_PROMPT_ROOT = PROMPTS_ROOT / "cultural_contexts" / "russian_folk"
MODEL_NAME = "wave14-local-capture"
DIAGNOSTIC_VERSION = "wave14-v1"
CONTROLLED_CONFIG = {
    "output_count": 2,
    "target_age": "3",
    "truth_mode": "FAIRY_TALE",
    "cultural_context": "RUSSIAN_FOLK",
    "utility_mode": "NARRATIVE",
}
EXACT_PROMPT_START = "<!-- EXACT_GENERATOR_PROMPT_START -->"
EXACT_PROMPT_END = "<!-- EXACT_GENERATOR_PROMPT_END -->"


@dataclass(frozen=True)
class DiagnosticCase:
    key: str
    filename: str
    title: str
    raw_text: str
    required_layer: str | None = None
    forbidden_layers: tuple[str, ...] = ()
    exact_filename: str | None = None


CASES = (
    DiagnosticCase(
        key="01",
        filename="01_FAIRY_FOX_BASE.md",
        title="Case 1 — base fairy-tale fox",
        raw_text="Короткие истории про лисичку.",
        forbidden_layers=("RUSSIAN_FOLK_TALE", "CHUKOVSKY_STYLE"),
    ),
    DiagnosticCase(
        key="02",
        filename="02_FAIRY_FOX_RUSSIAN_FOLK.md",
        title="Case 2 — fairy-tale fox in Russian folk manner",
        raw_text="Короткие истории про лисичку в русской народной манере.",
        required_layer="RUSSIAN_FOLK_TALE",
        forbidden_layers=("CHUKOVSKY_STYLE",),
        exact_filename="02_FAIRY_FOX_RUSSIAN_FOLK_EXACT_PROMPT.md",
    ),
    DiagnosticCase(
        key="03",
        filename="03_FAIRY_FOX_CHUKOVSKY.md",
        title="Case 3 — fairy-tale fox with CHUKOVSKY_STYLE",
        raw_text="Короткие истории про лисичку в стиле Чуковского.",
        required_layer="CHUKOVSKY_STYLE",
    ),
)


class LocalCaptureProvider(BaseLLMProvider):
    """In-memory provider boundary: captures input and performs no external I/O."""

    def __init__(self) -> None:
        self.prompts: list[str] = []
        self.temperatures: list[float | None] = []

    def generate_text(self, prompt: str, *, temperature: float | None = None) -> str:
        self.prompts.append(prompt)
        self.temperatures.append(temperature)
        return json.dumps({"candidates": []}, ensure_ascii=False)

    def generate_questions(self, text: str) -> list[str]:
        raise AssertionError("Generator prompt diagnostics must not request questions separately")


class CapturingGeneratorExecutor(LLMStage2TextExecutor):
    def __init__(self, provider: LocalCaptureProvider) -> None:
        super().__init__(provider, model_name=MODEL_NAME, max_retries=0)
        self.generator_runtime_contexts: list[dict[str, Any]] = []
        self.generator_candidate_counts: list[int] = []

    def generate_candidates(
        self,
        runtime_context: dict[str, Any],
        count: int,
    ) -> list[dict[str, Any]]:
        self.generator_runtime_contexts.append(deepcopy(runtime_context))
        self.generator_candidate_counts.append(count)
        return super().generate_candidates(runtime_context, count)


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Wave 14 generator prompt diagnostics.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Directory for the generated Markdown cases.",
    )
    parser.add_argument(
        "--case",
        choices=("all", "01", "02", "03"),
        default="all",
        help="Generate all cases or one selected case.",
    )
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)

    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat()
    summaries: list[dict[str, Any]] = []
    selected_cases = CASES if args.case == "all" else tuple(case for case in CASES if case.key == args.case)
    with tempfile.TemporaryDirectory(prefix="dreamydraw-wave14-") as temp_dir:
        for index, case in enumerate(selected_cases, start=1):
            summary = _export_case(
                case,
                output_path=args.output_dir / case.filename,
                storage_dir=Path(temp_dir) / f"case-{index}",
                generated_at=generated_at,
            )
            summaries.append(summary)

    print(json.dumps({"external_llm_calls": 0, "cases": summaries}, ensure_ascii=False, indent=2))
    return 0


def _export_case(
    case: DiagnosticCase,
    *,
    output_path: Path,
    storage_dir: Path,
    generated_at: str,
) -> dict[str, Any]:
    runner = Stage1Runner(
        storage_dir=storage_dir,
        prompts_root=PROMPTS_ROOT,
        cultural_context="RUSSIAN_FOLK",
    )
    stage1 = runner.start(case.raw_text, current_config=CONTROLLED_CONFIG)
    if not stage1.is_stage1_ready:
        raise RuntimeError(f"Stage 1 did not reach prompt-ready state for {case.filename}")

    provider = LocalCaptureProvider()
    executor = CapturingGeneratorExecutor(provider)
    candidate_text_generator(
        to_graph_state(stage1.session),
        runner.registry,
        runner.composer,
        executor,
        candidate_count=None,
    )

    if len(provider.prompts) != 1 or len(executor.generator_runtime_contexts) != 1:
        raise RuntimeError(f"Expected exactly one captured generator call for {case.filename}")

    prompt = provider.prompts[0]
    runtime_context = executor.generator_runtime_contexts[0]
    candidate_count = executor.generator_candidate_counts[0]
    wrapper, payload = _split_exact_prompt(prompt)
    ordered_layer_ids = list(payload["prompt_context"]["ordered_layer_ids"])
    _verify_case_layers(case, ordered_layer_ids)

    prompt_hash = _sha256(prompt)
    markdown = _render_case(
        case=case,
        session=stage1.session,
        registry=runner.registry,
        runtime_context=runtime_context,
        wrapper=wrapper,
        payload=payload,
        prompt=prompt,
        prompt_hash=prompt_hash,
        candidate_count=candidate_count,
        temperature=provider.temperatures[0],
        generated_at=generated_at,
    )
    output_path.write_text(markdown, encoding="utf-8")
    if case.exact_filename:
        exact_path = output_path.with_name(case.exact_filename)
        exact_path.write_bytes(prompt.encode("utf-8"))
        _verify_exact_file(exact_path, prompt, prompt_hash)
    else:
        exact_path = None
        _verify_written_export(output_path, prompt, prompt_hash)

    return {
        "file": output_path.name,
        "exact_file": exact_path.name if exact_path else None,
        "prompt_chars": len(prompt),
        "prompt_bytes_utf8": len(prompt.encode("utf-8")),
        "sha256": prompt_hash,
        "ordered_layer_ids": ordered_layer_ids,
    }


def _render_case(
    *,
    case: DiagnosticCase,
    session: Any,
    registry: Any,
    runtime_context: dict[str, Any],
    wrapper: str,
    payload: dict[str, Any],
    prompt: str,
    prompt_hash: str,
    candidate_count: int,
    temperature: float | None,
    generated_at: str,
) -> str:
    if case.exact_filename:
        return _render_human_case(
            case=case,
            session=session,
            registry=registry,
            runtime_context=runtime_context,
            wrapper=wrapper,
            payload=payload,
            prompt=prompt,
            prompt_hash=prompt_hash,
            candidate_count=candidate_count,
            temperature=temperature,
            generated_at=generated_at,
        )

    normalized = session.normalized_request.model_dump(mode="json")
    generator_summary = payload["normalized_request_summary"]
    fallback_ids = payload["prompt_context"]["fallback_layer_ids"]
    unresolved = payload["prompt_context"]["unresolved_details"]
    ordered_refs = runtime_context["ordered_layer_refs"]
    fallback_refs = runtime_context["fallback_layer_refs"]
    bodies = payload.get("layer_grounding", {}).get("bodies", {})
    metadata_constraints = payload.get("layer_grounding", {}).get("metadata_constraints", {})

    map_rows = _component_map_rows(wrapper, payload, ordered_refs)
    lines = [
        f"# {case.title}",
        "",
        "> Temporary Wave 14 diagnostic artifact. Do not use as a prompt asset or source of truth.",
        "",
        "## A. Input",
        "",
        f"- Raw text: `{case.raw_text}`",
        f"- Controlled parameters: `{_compact_json(CONTROLLED_CONFIG)}`",
        f"- Model name embedded in prompt: `{MODEL_NAME}`",
        f"- Candidate count passed to executor: `{candidate_count}`",
        f"- Capture temperature: `{temperature}`",
        f"- Cultural prompt root: `{SELECTED_PROMPT_ROOT.relative_to(PROJECT_ROOT).as_posix()}/`",
        "- External LLM calls: `0` (local in-memory capture provider)",
        "",
        "## B. Normalized request",
        "",
        "### Full normalized request",
        "",
        _fenced(_compact_json(normalized), "json"),
        "",
        "### Generator-facing normalized summary",
        "",
        _fenced(_compact_json(generator_summary), "json"),
        "",
        "## C. Resolved prompt context",
        "",
        f"- Ordered layer IDs: `{_compact_json(payload['prompt_context']['ordered_layer_ids'])}`",
        f"- Fallback layer IDs: `{_compact_json(fallback_ids)}`",
        f"- Unresolved details: `{_compact_json(unresolved)}`",
        f"- Hard details: `{_compact_json(payload['stage_context']['hard_details'])}`",
        f"- Soft preferences: `{_compact_json(payload['stage_context']['soft_preferences'])}`",
        f"- Stage context hash: `{payload['prompt_context']['stage_context_hash']}`",
        f"- Registry hash: `{registry.registry_hash}`",
        "",
        "### Layer sources and selection reasons",
        "",
        "| # | Layer ID | Source | Why selected | Raw body size | Summary |",
        "|---:|---|---|---|---:|---|",
    ]
    for index, ref in enumerate(ordered_refs, start=1):
        layer_id = ref["id"]
        body = bodies[layer_id]
        source = f"prompts/cultural_contexts/russian_folk/{ref['source']}"
        reason = ref.get("reason") or _default_layer_reason(ref)
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    _cell(layer_id),
                    _cell(source),
                    _cell(reason),
                    _cell(_size(body)),
                    _cell(ref.get("short_description") or ""),
                ]
            )
            + " |"
        )
    if fallback_refs:
        lines.extend(["", "Fallback refs:", "", _fenced(_compact_json(fallback_refs), "json")])

    lines.extend(
        [
            "",
            "## D. Component map",
            "",
            "Sizes below are UTF-8 sizes of the exact compact JSON value used in the final payload; the wrapper size is measured as raw text.",
            "",
            "| # | Part | Source | Purpose | Size |",
            "|---:|---|---|---|---:|",
        ]
    )
    for index, row in enumerate(map_rows, start=1):
        lines.append(
            f"| {index} | {_cell(row['part'])} | {_cell(row['source'])} | "
            f"{_cell(row['purpose'])} | {_cell(row['size'])} |"
        )

    lines.extend(["", "## E. Full prompt parts", ""])
    lines.extend(_render_full_parts(wrapper, payload, ordered_refs, bodies, metadata_constraints))
    lines.extend(
        [
            "",
            "## F. Exact final prompt",
            "",
            f"- Total size: `{_size(prompt)}`",
            f"- Stable SHA-256: `{prompt_hash}`",
            f"- Ordered layer IDs: `{_compact_json(payload['prompt_context']['ordered_layer_ids'])}`",
            f"- Diagnostic timestamp: `{generated_at}`",
            f"- Diagnostic version: `{DIAGNOSTIC_VERSION}`",
            "- Capture boundary: argument passed to `LocalCaptureProvider.generate_text()` by `LLMStage2TextExecutor`.",
            "- Verification: exporter re-extracts this fenced block after writing and compares exact text plus SHA-256 to the captured provider argument.",
            "",
            _exact_prompt_block(prompt),
            "",
            "## Замечания prompt engineers",
            "",
            "_Заполняется на следующем этапе._",
            "",
        ]
    )
    return "\n".join(lines)


def _render_human_case(
    *,
    case: DiagnosticCase,
    session: Any,
    registry: Any,
    runtime_context: dict[str, Any],
    wrapper: str,
    payload: dict[str, Any],
    prompt: str,
    prompt_hash: str,
    candidate_count: int,
    temperature: float | None,
    generated_at: str,
) -> str:
    ordered_refs = runtime_context["ordered_layer_refs"]
    bodies = payload["layer_grounding"].get("bodies", {})
    exact_filename = case.exact_filename or ""
    lines = [
        "# Кейс 02 — сказочная лиса в русской народной манере",
        "",
        "> Временный диагностический материал Wave 14. Это не prompt asset и не source of truth.",
        "",
        "## 1. Как собирается prompt",
        "",
        "Prompt строится фактическим runtime-путём `Stage 1 → PromptComposer → candidate_text_generator → LLMStage2TextExecutor`. Сначала executor добавляет общую инструкцию для JSON-only ответа, затем присоединяет один JSON payload со всеми данными генерации.",
        "",
        "Короткая схема:",
        "",
        "```text",
        "обёртка executor",
        "→ задача генератора и Python suffixes",
        "→ normalized request и age length policy",
        "→ stage inputs и prompt context",
        "→ metadata constraints активных layers",
        "→ полные тела активных layers",
        "→ stage context",
        "→ обязательная форма JSON-ответа",
        "```",
        "",
        "В разделе 4 эти значения показаны по частям для удобства чтения. Звёздочки и русские названия частей добавлены только в диагностический документ и не входят в prompt. Полная строка без разделителей сохранена отдельно byte-for-byte.",
        "",
        "## 2. Краткое описание частей",
        "",
        "| Часть | Что содержит | Зачем нужна |",
        "|---|---|---|",
        "| Обёртка executor | Общие правила роли Stage 2 и JSON-only ответа | Задаёт формат взаимодействия с LLM |",
        "| Этап и модель | Имя runtime stage и диагностическое имя модели | Идентифицирует текущий вызов |",
        "| Задача генератора | Требование создать пул candidates плюс ограничения длины и выразительности | Формулирует конкретную работу генератора |",
        "| Нормализованный запрос | Канонические параметры, subject, style и continuity policy | Передаёт интерпретированный пользовательский запрос |",
        "| Политика длины | Возраст, диапазон предложений и сложность | Ограничивает длину и синтаксис истории |",
        "| Входные данные этапа | Generator-facing данные текущего stage | Передаёт runtime-сводку входов |",
        "| Контекст prompt | Ordered layers, fallbacks, unresolved details и context hash | Фиксирует выбранный prompt context |",
        "| Метаданные и ограничения | Краткие описания, constraints и hashes каждого layer | Даёт структурированные ограничения без потери provenance |",
        "| Тела layers | Полный Markdown активных prompt assets | Передаёт содержательные инструкции каждого слоя |",
        "| Контекст этапа | Body policy, stage instructions, context blocks, hard/soft details | Описывает режим и доступные блоки текущего stage |",
        "| Форма JSON-ответа | Обязательная структура объекта `candidates` | Фиксирует контракт ответа |",
        "",
        "## 3. Параметры и выбранные layers",
        "",
        f"- Исходный текст: `{case.raw_text}`",
        f"- Управляемые параметры: `{_compact_json(CONTROLLED_CONFIG)}`",
        f"- Сводка для генератора: `{_compact_json(payload['normalized_request_summary'])}`",
        f"- Количество кандидатов: `{candidate_count}`",
        f"- Имя модели: `{MODEL_NAME}`",
        f"- Температура: `{temperature}`",
        f"- Корень культурной prompt-базы: `{SELECTED_PROMPT_ROOT.relative_to(PROJECT_ROOT).as_posix()}/`",
        f"- Порядок layer IDs: `{_compact_json(payload['prompt_context']['ordered_layer_ids'])}`",
        f"- Резервные layers: `{_compact_json(payload['prompt_context']['fallback_layer_ids'])}`",
        f"- Неразрешённые детали: `{_compact_json(payload['prompt_context']['unresolved_details'])}`",
        f"- Обязательные детали: `{_compact_json(payload['stage_context']['hard_details'])}`",
        f"- Мягкие предпочтения: `{_compact_json(payload['stage_context']['soft_preferences'])}`",
        "",
        "### Активные layers",
        "",
        "| Layer ID | Источник | Почему выбран | Краткое назначение |",
        "|---|---|---|---|",
    ]
    for ref in ordered_refs:
        lines.append(
            f"| {_cell(ref['id'])} | {_cell(ref['source'])} | "
            f"{_cell(ref.get('reason') or _default_layer_reason(ref))} | "
            f"{_cell(ref.get('short_description') or '')} |"
        )

    lines.extend(
        [
            "",
            "### Техническая идентификация",
            "",
            f"- Файл точного prompt: [`{exact_filename}`]({exact_filename})",
            f"- Размер точного prompt: `{_size(prompt)}`",
            f"- SHA-256: `{prompt_hash}`",
            f"- Stage context hash: `{payload['prompt_context']['stage_context_hash']}`",
            f"- Registry hash: `{registry.registry_hash}`",
            f"- Диагностическая версия: `{DIAGNOSTIC_VERSION}`",
            f"- Дата экспорта: `{generated_at}`",
            "- Внешние LLM-вызовы: `0`.",
            "",
            "## 4. Оригинальный prompt по частям",
            "",
            "> Разделители и названия частей ниже добавлены только для навигации. Порядок соответствует фактическому порядку полей в compact JSON с `sort_keys=True`. Строковые значения показаны в декодированном виде для чтения, поэтому это не byte slices; byte-exact строка находится в отдельном файле.",
            "",
        ]
    )
    lines.extend(_render_separated_parts(wrapper, payload, ordered_refs, bodies))
    lines.extend(
        [
            "",
            "## Замечания prompt engineers",
            "",
            "_Заполняется на следующем этапе._",
            "",
        ]
    )
    return "\n".join(lines)


def _render_separated_parts(
    wrapper: str,
    payload: dict[str, Any],
    ordered_refs: list[dict[str, Any]],
    bodies: dict[str, str],
) -> list[str]:
    lines: list[str] = []
    lines.extend(_star_part("ЧАСТЬ 1 — ОБЁРТКА EXECUTOR", wrapper, "text"))

    # Exact JSON is serialized with sort_keys=True. Within layer_grounding,
    # bodies appears before metadata_constraints, and body ids are alphabetical.
    refs_by_id = {ref["id"]: ref for ref in ordered_refs}
    next_index = 2
    for layer_id, body in bodies.items():
        source = refs_by_id[layer_id]["source"]
        lines.extend(
            _star_part(
                f"ЧАСТЬ {next_index} — layer_grounding.bodies.{layer_id} ({source})",
                body,
                "markdown",
            )
        )
        next_index += 1

    serialized_parts: list[tuple[str, Any, str]] = [
        (
            "layer_grounding.metadata_constraints — МЕТАДАННЫЕ И ОГРАНИЧЕНИЯ LAYERS",
            payload["layer_grounding"].get("metadata_constraints", {}),
            "json",
        ),
        ("length_policy — ПОЛИТИКА ДЛИНЫ", payload["length_policy"], "json"),
        ("model_name — ИМЯ МОДЕЛИ", payload["model_name"], "json"),
        (
            "normalized_request_summary — СВОДКА НОРМАЛИЗОВАННОГО ЗАПРОСА",
            payload["normalized_request_summary"],
            "json",
        ),
        ("prompt_context — КОНТЕКСТ PROMPT", payload["prompt_context"], "json"),
        (
            "required_output_shape — ТРЕБУЕМАЯ ФОРМА JSON-ОТВЕТА",
            payload["required_output_shape"],
            "json",
        ),
        ("stage — ЭТАП", payload["stage"], "json"),
        ("stage_context — КОНТЕКСТ ЭТАПА", payload["stage_context"], "json"),
        ("stage_inputs — ВХОДНЫЕ ДАННЫЕ ЭТАПА", payload["stage_inputs"], "json"),
        (
            "task — ЗАДАЧА ГЕНЕРАТОРА И ДОБАВЛЕННЫЕ PYTHON-ОГРАНИЧЕНИЯ",
            payload["task"],
            "text",
        ),
    ]
    for title, value, language in serialized_parts:
        content = value if language == "text" else _compact_json(value)
        lines.extend(_star_part(f"ЧАСТЬ {next_index} — {title}", content, language))
        next_index += 1
    return lines


def _star_part(title: str, content: str, language: str) -> list[str]:
    divider = "*" * 80
    return [divider, title, divider, "", _fenced(content, language), ""]


def _component_map_rows(
    wrapper: str,
    payload: dict[str, Any],
    ordered_refs: list[dict[str, Any]],
) -> list[dict[str, str]]:
    rows = [
        _map_row("Executor wrapper", "LLMStage2TextExecutor._build_prompt", "JSON-only executor and response envelope rules", wrapper, raw=True),
        _map_row("Stage and model envelope", "LLMStage2TextExecutor._build_prompt", "Identifies stage and diagnostic model", {"stage": payload["stage"], "model_name": payload["model_name"]}),
        _map_row("Generator task + Python suffixes", "generate_candidates + length/expressiveness/truth policies", "Exact candidate-generation instruction", payload["task"]),
        _map_row("Normalized request summary", "PromptComposer._normalized_request_summary", "Generator-facing normalized state", payload["normalized_request_summary"]),
        _map_row("Length policy", "stage2_length_policy.length_policy_payload", "Age-specific sentence and complexity limits", payload["length_policy"]),
        _map_row("Stage inputs", "stage2_llm_executor._stage_inputs", "Generator inputs serialized for this call", payload["stage_inputs"]),
        _map_row("Prompt context", "LLMStage2TextExecutor._build_prompt", "Ordered/fallback layers, unresolved details and context hash", payload["prompt_context"]),
        _map_row("Layer metadata constraints", "PromptComposer + PromptRegistry metadata", "Descriptions, constraints and hashes for active layers", payload["layer_grounding"].get("metadata_constraints", {})),
    ]
    bodies = payload["layer_grounding"].get("bodies", {})
    refs_by_id = {ref["id"]: ref for ref in ordered_refs}
    for layer_id, body in bodies.items():
        ref = refs_by_id[layer_id]
        rows.append(
            _map_row(
                f"Layer body: {layer_id}",
                f"prompts/cultural_contexts/russian_folk/{ref['source']}",
                ref.get("short_description") or "Active prompt layer body",
                body,
            )
        )
    rows.extend(
        [
            _map_row("Stage instructions", "PromptComposer._stage_instructions", "Stage profile and output contract label", payload["stage_context"]["stage_instructions"]),
            _map_row("Context blocks", "PromptComposer._context_blocks", "Declares available runtime context groups", payload["stage_context"]["context_blocks"]),
            _map_row("Hard details", "NormalizedRequest.hard_details", "Mandatory free-form details", payload["stage_context"]["hard_details"]),
            _map_row("Soft preferences", "NormalizedRequest.soft_preferences", "Non-mandatory free-form preferences", payload["stage_context"]["soft_preferences"]),
            _map_row("Body policy", "Stage 2 candidate_text_generator", "Controls runtime inclusion of layer bodies", payload["stage_context"]["body_policy"]),
            _map_row("Required JSON output shape", "LLMStage2TextExecutor.generate_candidates", "Exact response object contract", payload["required_output_shape"]),
        ]
    )
    return rows


def _render_full_parts(
    wrapper: str,
    payload: dict[str, Any],
    ordered_refs: list[dict[str, Any]],
    bodies: dict[str, str],
    metadata_constraints: dict[str, Any],
) -> list[str]:
    sections: list[tuple[str, Any, str]] = [
        ("Executor wrapper", wrapper, "text"),
        ("Stage and model envelope", {"stage": payload["stage"], "model_name": payload["model_name"]}, "json"),
        ("Generator task including runtime suffixes", payload["task"], "text"),
        ("Normalized request summary", payload["normalized_request_summary"], "json"),
        ("Length policy", payload["length_policy"], "json"),
        ("Stage inputs", payload["stage_inputs"], "json"),
        ("Prompt context", payload["prompt_context"], "json"),
        ("Layer metadata constraints", metadata_constraints, "json"),
        ("Stage instructions", payload["stage_context"]["stage_instructions"], "json"),
        ("Context blocks", payload["stage_context"]["context_blocks"], "json"),
        ("Hard details", payload["stage_context"]["hard_details"], "json"),
        ("Soft preferences", payload["stage_context"]["soft_preferences"], "json"),
        ("Body policy", payload["stage_context"]["body_policy"], "text"),
        ("Required JSON output shape", payload["required_output_shape"], "json"),
    ]
    lines: list[str] = []
    for title, value, language in sections:
        content = value if isinstance(value, str) else _compact_json(value)
        lines.extend([f"### {title}", "", _fenced(content, language), ""])

    refs_by_id = {ref["id"]: ref for ref in ordered_refs}
    lines.extend(["### Complete active layer bodies", ""])
    for layer_id, body in bodies.items():
        ref = refs_by_id[layer_id]
        lines.extend(
            [
                f"#### {layer_id}",
                "",
                f"- Source: `prompts/cultural_contexts/russian_folk/{ref['source']}`",
                f"- Selection reason: `{ref.get('reason') or _default_layer_reason(ref)}`",
                f"- Purpose: {ref.get('short_description') or 'Active prompt layer body'}",
                f"Raw size: `{_size(body)}`",
                "",
                _fenced(body, "markdown"),
                "",
            ]
        )
    return lines


def _map_row(part: str, source: str, purpose: str, value: Any, *, raw: bool = False) -> dict[str, str]:
    serialized = value if raw and isinstance(value, str) else _compact_json(value)
    return {
        "part": part,
        "source": source,
        "purpose": purpose,
        "size": _size(serialized),
    }


def _default_layer_reason(ref: dict[str, Any]) -> str:
    if ref.get("role") == "candidate_text_generator":
        return "stage role=candidate_text_generator"
    return f"active {ref.get('type') or 'prompt'} layer selected by Stage 1"


def _verify_case_layers(case: DiagnosticCase, ordered_layer_ids: list[str]) -> None:
    if case.required_layer and case.required_layer not in ordered_layer_ids:
        raise RuntimeError(f"{case.filename} did not resolve required layer {case.required_layer}")
    unexpected = sorted(set(case.forbidden_layers) & set(ordered_layer_ids))
    if unexpected:
        raise RuntimeError(f"{case.filename} unexpectedly resolved layers: {unexpected}")


def _split_exact_prompt(prompt: str) -> tuple[str, dict[str, Any]]:
    payload_start = prompt.find("{")
    if payload_start < 0:
        raise RuntimeError("Captured prompt has no JSON payload")
    wrapper = prompt[:payload_start]
    payload_text = prompt[payload_start:]
    payload = json.loads(payload_text)
    if wrapper + json.dumps(payload, ensure_ascii=False, sort_keys=True) != prompt:
        raise RuntimeError("Captured prompt is not the expected wrapper + canonical JSON payload")
    return wrapper, payload


def _exact_prompt_block(prompt: str) -> str:
    fence = _fence_for(prompt)
    return f"{EXACT_PROMPT_START}\n{fence}text\n{prompt}\n{fence}\n{EXACT_PROMPT_END}"


def _verify_written_export(path: Path, prompt: str, prompt_hash: str) -> None:
    markdown = path.read_text(encoding="utf-8")
    marker_start = markdown.index(EXACT_PROMPT_START) + len(EXACT_PROMPT_START) + 1
    opening_end = markdown.index("\n", marker_start)
    opening = markdown[marker_start:opening_end]
    if not opening.endswith("text"):
        raise RuntimeError(f"Malformed exact prompt fence in {path}")
    fence = opening[:-4]
    content_start = opening_end + 1
    closing = f"\n{fence}\n{EXACT_PROMPT_END}"
    content_end = markdown.index(closing, content_start)
    embedded_prompt = markdown[content_start:content_end]
    if embedded_prompt != prompt:
        raise RuntimeError(f"Embedded prompt differs from provider capture in {path}")
    if _sha256(embedded_prompt) != prompt_hash:
        raise RuntimeError(f"Embedded prompt hash differs from recorded capture hash in {path}")


def _verify_exact_file(path: Path, prompt: str, prompt_hash: str) -> None:
    expected = prompt.encode("utf-8")
    actual = path.read_bytes()
    if actual != expected:
        raise RuntimeError(f"Exact prompt file differs byte-for-byte from provider capture: {path}")
    if hashlib.sha256(actual).hexdigest() != prompt_hash:
        raise RuntimeError(f"Exact prompt file hash differs from provider capture: {path}")


def _fenced(content: str, language: str) -> str:
    fence = _fence_for(content)
    return f"{fence}{language}\n{content}\n{fence}"


def _fence_for(content: str) -> str:
    longest = max((len(match.group(0)) for match in re.finditer(r"`+", content)), default=0)
    return "`" * max(4, longest + 1)


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _size(value: str) -> str:
    return f"{len(value)} chars / {len(value.encode('utf-8'))} bytes"


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _cell(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


if __name__ == "__main__":
    raise SystemExit(main())
