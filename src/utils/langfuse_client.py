"""
Langfuse v4 SDK интеграция.

В v4 SDK работает через OpenTelemetry-контекст. Иерархия трейс/спан
строится автоматически из вложенности вызовов (через @observe или with).
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_CLIENT: Optional[Any] = None  # экземпляр Langfuse
_ENABLED: bool = False


def init_langfuse(settings_obj: Any) -> None:
    """Инициализация Langfuse SDK. Вызывается один раз в main.py."""
    global _CLIENT, _ENABLED

    if not settings_obj.LANGFUSE_ENABLED:
        logger.info("LangFuse disabled via config.")
        _ENABLED = False
        return

    if not settings_obj.LANGFUSE_PUBLIC_KEY or not settings_obj.LANGFUSE_SECRET_KEY:
        logger.warning("LangFuse disabled: missing LANGFUSE_PUBLIC_KEY or LANGFUSE_SECRET_KEY.")
        _ENABLED = False
        return

    try:
        from langfuse import Langfuse  # type: ignore

        _CLIENT = Langfuse(
            public_key=settings_obj.LANGFUSE_PUBLIC_KEY,
            secret_key=settings_obj.LANGFUSE_SECRET_KEY,
            host=settings_obj.LANGFUSE_HOST,
            environment=settings_obj.LANGFUSE_ENV,
        )
        _ENABLED = True
        logger.info(
            "LangFuse client initialized (host=%s, project=%s, env=%s).",
            settings_obj.LANGFUSE_HOST,
            settings_obj.LANGFUSE_PROJECT_NAME,
            settings_obj.LANGFUSE_ENV,
        )
    except Exception as exc:
        _ENABLED = False
        logger.warning("LangFuse init failed, fallback to NoOp: %s", exc)


def is_enabled() -> bool:
    return _ENABLED and _CLIENT is not None


def get_client() -> Optional[Any]:
    """Возвращает экземпляр Langfuse SDK или None если не инициализирован."""
    return _CLIENT if is_enabled() else None


def update_current_trace(**kwargs: Any) -> None:
    """
    Обновить метаданные текущего трейса (session_id, user_id, tags, metadata, input, output).
    В v4 это делается через активный observation, поэтому используем get_current_span.
    Безопасно: если SDK выключен или нет активного контекста — ничего не делает.
    """
    if not is_enabled():
        return
    try:
        # В v4 update_current_trace доступен на активном observation/span
        span = _CLIENT.get_current_span() if hasattr(_CLIENT, "get_current_span") else None
        if span is not None and hasattr(span, "update_trace"):
            span.update_trace(**kwargs)
        else:
            # Fallback: пробуем напрямую (для совместимости с разными версиями SDK)
            if hasattr(_CLIENT, "update_current_trace"):
                _CLIENT.update_current_trace(**kwargs)
    except Exception as exc:
        logger.debug("LangFuse update_current_trace failed: %s", exc)


def log_trace_url() -> None:
    """Залогировать URL текущего трейса для удобства дебага."""
    if not is_enabled():
        return
    try:
        url = _CLIENT.get_trace_url()
        if url:
            logger.info("LangFuse trace URL: %s", url)
    except Exception as exc:
        logger.debug("LangFuse get_trace_url failed: %s", exc)


def score_current_trace(name: str, value: float, comment: Optional[str] = None) -> None:
    """Поставить score на текущий трейс."""
    if not is_enabled():
        return
    try:
        span = _CLIENT.get_current_span() if hasattr(_CLIENT, "get_current_span") else None
        if span is not None and hasattr(span, "score_trace"):
            span.score_trace(name=name, value=value, comment=comment)
        elif hasattr(_CLIENT, "score_current_trace"):
            _CLIENT.score_current_trace(name=name, value=value, comment=comment)
    except Exception as exc:
        logger.debug("LangFuse score_current_trace failed: %s", exc)


def flush() -> None:
    """Принудительно отправить все буферизованные события. Вызвать перед выходом из приложения."""
    if not is_enabled():
        return
    try:
        _CLIENT.flush()
    except Exception as exc:
        logger.debug("LangFuse flush failed: %s", exc)