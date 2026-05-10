"""
Orchestrator — тонкий фасад над LangGraph.

Публичный API сохранён:
    - start_session(request)
    - run_pipeline(session_id, resume_value=None)
    - confirm_story(session_id, index)

Внутри:
    - Граф собирается один раз в __init__ через build_graph().
    - Checkpointer — MemorySaver (in-process, для interrupt/resume).
    - Долгосрочная персистентность — через JSONStorage (как раньше).
    - При restore сессии (--session <id>) граф продолжается с правильной ноды
      благодаря тому, что каждая нода читает session.current_node.
"""

import logging
import os
from typing import Any, Optional

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command

from src.core.graph.builder import build_graph
from src.core.graph.state import GraphState, to_graph_state
from src.core.pipeline_result import PipelineResult
from src.core.prompt_builder import PromptBuilder
from src.models.schemas import GenerationRequest, SessionState, StoryItem
from src.providers.base import BaseImageProvider, BaseLLMProvider
from src.storage.json_storage import JSONStorage
from src.utils.langfuse_client import (
    log_trace_url,
    update_current_trace,
)

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(
        self,
        llm_provider: BaseLLMProvider,
        image_provider: BaseImageProvider,
        storage: JSONStorage,
        prompt_builder: Optional[PromptBuilder] = None,
    ):
        self.llm = llm_provider
        self.image = image_provider
        self.storage = storage
        self.prompt_builder = prompt_builder or PromptBuilder()

        # Один checkpointer на весь жизненный цикл оркестратора.
        # Хранит состояние interrupt в рамках одного процесса.
        self._checkpointer = MemorySaver()

        # Граф собирается один раз — зависимости запечатываются в closure нод.
        self.graph = build_graph(
            llm=self.llm,
            image=self.image,
            storage=self.storage,
            prompt_builder=self.prompt_builder,
            checkpointer=self._checkpointer,
        )

    # --- Публичный API ---------------------------------------------------

    def start_session(self, request: GenerationRequest) -> SessionState:
        """Создаёт новую сессию и подготавливает контейнеры для историй."""
        session = SessionState(request=request)
        for i in range(request.count):
            session.stories.append(StoryItem(index=i))

        os.makedirs(
            os.path.join(self.storage.base_dir, session.session_id), exist_ok=True
        )
        self.storage.save_session(session)
        return session

    def run_pipeline(
        self,
        session_id: str,
        resume_value: Optional[Any] = None,
    ) -> PipelineResult:
        """
        Запускает (или возобновляет) граф для сессии.

        Args:
            session_id: ID сессии в JSONStorage
            resume_value: если граф ранее остановился на interrupt — значение
                          передаётся в нод-ожидание (например, ответ пользователя).
                          При первом вызове = None.

        Returns:
            PipelineResult с актуальным состоянием:
            - is_done=True: граф завершился (успех или failed)
            - is_waiting_user=True: граф ждёт ввода (interrupt в виде dict)
        """
        session = self.storage.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session.is_completed:
            logger.info("Session %s already completed", session_id)
            return PipelineResult(session=session)

        config = {"configurable": {"thread_id": session_id}}

        # Метаданные трейса (один раз на каждый invoke/resume)
        self._update_trace_metadata(session)

        # Решаем: первый запуск или resume после interrupt
        if resume_value is not None:
            logger.debug(
                "Orchestrator.run_pipeline: resume thread=%s value=%r",
                session_id,
                str(resume_value)[:120],
            )
            graph_input: Any = Command(resume=resume_value)
        else:
            # Первый запуск — проверяем, есть ли уже состояние в checkpointer.
            # Если нет (например, новый процесс) — кладём session из JSONStorage.
            graph_input = to_graph_state(session)

        try:
            final_state = self.graph.invoke(graph_input, config=config)
        except Exception:
            logger.exception("Orchestrator: graph.invoke failed")
            raise

        # Проверяем: граф остановился на interrupt или завершился?
        interrupt_data = self._extract_interrupt(config)

        # Актуальная сессия — берём ИЗ JSONStorage, т.к. ноды сами туда сохраняют
        # после каждого шага. Это надёжнее, чем доверять final_state, который
        # может быть промежуточным при interrupt.
        actual_session = self.storage.get_session(session_id) or final_state["session"]

        # Обновим итог трейса
        update_current_trace(
            output={
                "current_node": actual_session.current_node,
                "is_completed": actual_session.is_completed,
                "validation_cycles": actual_session.validation_cycles,
                "waiting_user": interrupt_data is not None,
            }
        )

        return PipelineResult(session=actual_session, interrupt=interrupt_data)

    def confirm_story(self, session_id: str, index: int) -> SessionState:
        """
        Backward-compatible helper (для скриптов отладки).
        В новом флоу подтверждение делается через interrupt в user_confirmation,
        но метод оставляем для совместимости.
        """
        session = self.storage.get_session(session_id)
        if session and 0 <= index < len(session.stories):
            session.stories[index].is_confirmed = True
            self.storage.save_session(session)
        return session

    # --- Внутренние утилиты ---------------------------------------------

    def _update_trace_metadata(self, session: SessionState) -> None:
        """Обогащает текущий трейс метаданными сессии."""
        update_current_trace(
            session_id=session.session_id,
            user_id="cli",
            tags=[
                f"truth_mode:{session.request.truth_mode.value}",
                f"work_mode:{session.request.work_mode.value}",
                f"image_style:{session.request.image_style.value}",
            ],
            input={
                "session_id": session.session_id,
                "topic": session.request.topic,
            },
            metadata={
                "truth_mode": session.request.truth_mode.value,
                "text_style": session.request.text_style.value,
                "image_style": session.request.image_style.value,
                "work_mode": session.request.work_mode.value,
                "count": session.request.count,
                "current_node": session.current_node,
            },
        )
        log_trace_url()

    def _extract_interrupt(self, config: dict) -> Optional[dict]:
        """
        После invoke смотрим в state graph: если есть pending interrupt —
        возвращаем его payload. Иначе None.

        В langgraph 0.2.x interrupt хранится в snapshot.tasks[*].interrupts.
        """
        try:
            snapshot = self.graph.get_state(config)
        except Exception as exc:
            logger.debug("Failed to get graph state: %s", exc)
            return None

        if not snapshot:
            return None

        # snapshot.tasks — список PregelTask. У каждой может быть interrupts.
        tasks = getattr(snapshot, "tasks", None) or []
        for task in tasks:
            interrupts = getattr(task, "interrupts", None) or []
            if interrupts:
                # Берём первый interrupt — у нас одновременно может быть только один HITL
                first = interrupts[0]
                payload = getattr(first, "value", None)
                if isinstance(payload, dict):
                    return payload
                # На всякий случай fallback
                return {"type": "unknown", "value": payload}

        return None