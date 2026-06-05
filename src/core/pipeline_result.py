"""Public pipeline call result for legacy and Stage 1-2 orchestrators."""

from dataclasses import dataclass
from typing import Optional

from src.models.schemas import CompletionStatus, SessionState

TERMINAL_COMPLETION_STATUSES = {
    CompletionStatus.COMPLETED_ENOUGH.value,
    CompletionStatus.COMPLETED_WITH_SHORTAGE.value,
    CompletionStatus.COMPLETED_WITH_SHORTAGE_USER_ACCEPTED.value,
    CompletionStatus.STOPPED_UNRESOLVED_REQUEST.value,
    CompletionStatus.STOPPED_BY_USER.value,
    CompletionStatus.FAILED.value,
}


@dataclass
class PipelineResult:
    session: SessionState
    interrupt: Optional[dict] = None

    @property
    def is_done(self) -> bool:
        """Граф завершился (успешно или с ошибкой), interrupt не ожидается."""
        if self.is_waiting_user:
            return False
        return bool(self.session.is_completed) or _status_value(self.session.completion_status) in TERMINAL_COMPLETION_STATUSES

    @property
    def is_waiting_user(self) -> bool:
        """Граф остановился на interrupt — нужен ввод пользователя."""
        if self.interrupt is not None:
            return True
        pending = self.session.pending_interrupt
        return bool(pending and pending.status == "waiting")

    @property
    def interrupt_type(self) -> Optional[str]:
        """Тип interrupt-точки, если граф остановлен."""
        if self.interrupt is not None:
            return self.interrupt.get("type")
        pending = self.session.pending_interrupt
        if pending and pending.status == "waiting":
            return pending.type
        return None


def _status_value(status) -> str:
    return getattr(status, "value", status)
