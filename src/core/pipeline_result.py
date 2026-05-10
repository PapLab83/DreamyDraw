"""
PipelineResult — результат вызова Orchestrator.run_pipeline().

Содержит:
    - session: текущее состояние сессии
    - interrupt: данные interrupt, если граф остановился (None если завершился/упал)

interrupt: dict с обязательными ключами:
    - type: 'config_arbitration' | 'plan_arbitration' | 'user_confirmation'
    - все остальные поля специфичны для типа (см. сами ноды)
"""

from dataclasses import dataclass
from typing import Optional

from src.models.schemas import SessionState


@dataclass
class PipelineResult:
    session: SessionState
    interrupt: Optional[dict] = None

    @property
    def is_done(self) -> bool:
        """Граф завершился (успешно или с ошибкой), interrupt не ожидается."""
        return self.interrupt is None

    @property
    def is_waiting_user(self) -> bool:
        """Граф остановился на interrupt — нужен ввод пользователя."""
        return self.interrupt is not None

    @property
    def interrupt_type(self) -> Optional[str]:
        """Тип interrupt-точки, если граф остановлен."""
        if self.interrupt is None:
            return None
        return self.interrupt.get("type")