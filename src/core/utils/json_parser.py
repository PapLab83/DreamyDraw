"""
Унифицированный парсер JSON-ответов от LLM.

Закрывает тех. долг п.5 из ORCHESTRATOR_SPEC.md: устраняет дубль
response_raw.replace("```json", "").replace("```", "").strip() + json.loads
по всему оркестратору (~10 мест).
"""

import json
import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


class LLMJsonParseError(ValueError):
    """Ошибка парсинга JSON-ответа от LLM."""
    pass


def parse_llm_json(
    raw_response: str,
    *,
    default: Optional[Any] = None,
    context: str = "",
) -> Any:
    """
    Распарсить JSON-ответ от LLM, устойчиво к markdown-обёрткам.

    Поддерживает:
    - чистый JSON: '{"x": 1}'
    - markdown code fence: '```json\n{"x": 1}\n```'
    - markdown без языка: '```\n{"x": 1}\n```'
    - JSON с префиксом/суффиксом текста (берёт первый валидный {} или []-блок)

    Args:
        raw_response: сырой ответ от LLM
        default: значение, возвращаемое при ошибке. Если None — поднимается LLMJsonParseError
        context: метка для логирования (имя ноды/шага)

    Returns:
        Распарсенный объект (dict / list / etc.)

    Raises:
        LLMJsonParseError: если парсинг не удался и default не задан
    """
    if not raw_response or not raw_response.strip():
        msg = f"[{context}] Пустой ответ от LLM"
        if default is not None:
            logger.warning(msg)
            return default
        raise LLMJsonParseError(msg)

    cleaned = _strip_code_fence(raw_response).strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    extracted = _extract_first_json_block(cleaned)
    if extracted is not None:
        try:
            return json.loads(extracted)
        except json.JSONDecodeError:
            pass

    msg = f"[{context}] Не удалось распарсить JSON. Ответ (первые 200 символов): {raw_response[:200]!r}"
    if default is not None:
        logger.warning(msg)
        return default
    raise LLMJsonParseError(msg)


def _strip_code_fence(text: str) -> str:
    """Убирает markdown code fence ```json ... ``` или ``` ... ```."""
    pattern = r"^```(?:json|JSON)?\s*\n?(.*?)\n?```\s*$"
    match = re.match(pattern, text.strip(), re.DOTALL)
    if match:
        return match.group(1)
    return text.replace("```json", "").replace("```JSON", "").replace("```", "")


def _extract_first_json_block(text: str) -> Optional[str]:
    """
    Извлекает первый сбалансированный JSON-блок (объект или массив) из текста.
    Полезно когда LLM добавляет текст до/после JSON.
    """
    for open_char, close_char in [("{", "}"), ("[", "]")]:
        start = text.find(open_char)
        if start == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"' and not escape:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == open_char:
                depth += 1
            elif ch == close_char:
                depth -= 1
                if depth == 0:
                    return text[start : i + 1]
    return None