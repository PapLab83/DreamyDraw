"""
DreamyDraw CLI — точка входа.

Главный цикл:
    1. start (или resume) сессии
    2. orch.run_pipeline(...) → PipelineResult
    3. если result.is_waiting_user → спросить пользователя → resume_value
    4. повторять, пока не is_done
    5. напечатать результат
"""

import logging
from typing import Optional

from src.config import constants
from src.config.settings import settings
from src.core.factory import ProviderFactory
from src.core.orchestrator import Orchestrator
from src.core.pipeline_result import PipelineResult
from src.models.schemas import (
    GenerationRequest,
    ImageStyle,
    SessionState,
    TextStyle,
    TruthMode,
    WorkMode,
)
from src.storage.json_storage import JSONStorage
from src.utils.cli_parser import get_cli_parser, parse_count
from src.utils.langfuse_client import flush as flush_langfuse, init_langfuse
from src.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Interrupt handlers — каждый возвращает значение для Command(resume=...)
# или None, если пользователь решил прервать пайплайн.
# ---------------------------------------------------------------------------

def handle_config_arbitration(payload: dict, session: SessionState, orch: Orchestrator) -> Optional[str]:
    """
    config_arbitration: спросить, переключить ли режим на предложенный.
    Возвращает 'y' для переключения или 'n' для отмены.
    """
    separator = "=" * constants.DEBUG_TEXT_SEPARATOR_WIDTH
    print("\n" + separator)
    print("[!] КОНФИГ НЕ СОВПАДАЕТ С ТЕМОЙ")
    print(separator)
    print(f"Причина:          {payload.get('reason', '')}")
    print(f"Текущий режим:    {payload.get('current_mode', '')}")
    print(f"Предложенный:     {payload.get('suggested_mode', '')}")
    print()
    choice = input("Переключить режим и продолжить? (y/n): ").strip().lower()
    return choice or "n"


def handle_plan_arbitration(payload: dict, session: SessionState, orch: Orchestrator) -> Optional[str]:
    """
    plan_arbitration: показать проблемные темы, попросить комментарий
    или форсированное одобрение.
    """
    separator = "=" * constants.DEBUG_TEXT_SEPARATOR_WIDTH
    print("\n" + separator)
    print(f"[!] АРБИТРАЖ ПОЛЬЗОВАТЕЛЯ")
    print(
        f"Валидатор отклонил план уже {payload.get('validation_cycles', '?')} раз(а)."
    )
    print(
        f"Порог автоматических циклов ({payload.get('threshold', '?')}) достигнут."
    )
    print("Спор между валидатором и редактором требует вашего вмешательства.")
    print(separator)

    problems = payload.get("problems", [])
    if problems:
        print("\n--- ПОСЛЕДНИЕ ЗАМЕЧАНИЯ ПО ПРОБЛЕМНЫМ ТЕМАМ ---")
        for p in problems:
            idx = p.get("index", "?")
            print(
                f"\n[Тема {idx + 1 if isinstance(idx, int) else idx}] "
                f"(всего версий в истории: {p.get('history_size', 0)})"
            )
            if p.get("current_theme") or p.get("current_content"):
                print(f"  Текущая версия (от редактора):")
                print(f"    Название: {p.get('current_theme')}")
                print(f"    Сюжет:    {p.get('current_content')}")
            if p.get("last_validator_note"):
                print(f"  Последнее замечание валидатора:")
                print(f"    {p.get('last_validator_note')}")
        print("-----------------------------------------------\n")
    else:
        print("(не удалось определить проблемные темы)")

    print("Варианты:")
    print("  [Enter] — дать свободный комментарий ИИ для следующей итерации")
    print("  'ок' / 'хорошо' / 'хватит' — принудительно одобрить текущий вариант")
    print()
    user_input = input("Ваш ответ: ").strip()
    return user_input  # пустая строка тоже валидна — нода поймёт


def handle_user_confirmation(payload: dict, session: SessionState, orch: Orchestrator) -> Optional[str]:
    """
    user_confirmation (CHECK-режим): показать все сгенерированные тексты,
    попросить y/n/r.
    """
    print("\n--- СОГЛАСОВАНИЕ ТЕКСТОВ СЕРИИ ---")
    stories = payload.get("stories", [])
    for s in stories:
        idx = s.get("index", "?")
        idx_print = idx + 1 if isinstance(idx, int) else idx
        print(f"\n[История {idx_print}/{len(stories)}]")
        print(f"Тема: {s.get('sub_topic', '')}")
        print(f"Текст: {s.get('text', '')}")
        questions = s.get("questions") or []
        print(f"Вопросы: {', '.join(questions)}")

    print()
    choice = input(
        "Подтвердить ВСЕ тексты и начать отрисовку? "
        "(y - да / n - отмена / r - перегенерировать всё): "
    ).strip().lower()
    return choice or "n"


# Реестр обработчиков по типу interrupt.
# Добавление новой interrupt-ноды = одна запись здесь.
INTERRUPT_HANDLERS = {
    "config_arbitration": handle_config_arbitration,
    "plan_arbitration": handle_plan_arbitration,
    "user_confirmation": handle_user_confirmation,
}


# ---------------------------------------------------------------------------
# Главный цикл
# ---------------------------------------------------------------------------

def run_loop(orch: Orchestrator, session_id: str) -> SessionState:
    """
    Запускает граф и обрабатывает interrupts до завершения.
    Возвращает финальное состояние сессии.
    """
    resume_value: Optional[str] = None

    while True:
        result: PipelineResult = orch.run_pipeline(session_id, resume_value=resume_value)

        if result.is_done:
            return result.session

        # Граф остановился — обрабатываем interrupt
        interrupt_type = result.interrupt_type or "unknown"
        handler = INTERRUPT_HANDLERS.get(interrupt_type)

        if handler is None:
            logger.error(
                "Неизвестный interrupt type: %s. Останавливаемся.", interrupt_type
            )
            return result.session

        resume_value = handler(result.interrupt, result.session, orch)


# ---------------------------------------------------------------------------
# Вывод финального результата
# ---------------------------------------------------------------------------

def print_final(session: SessionState) -> None:
    if session.current_node == "failed":
        print("\n!!! Программа остановлена из-за ошибки.")
        return

    if session.is_completed:
        print(f"\n--- Генерация завершена! ---")
        print(f"Результаты в папке: {settings.OUTPUT_DIR}/{session.session_id}")
        return

    # Промежуточное состояние — сессия не завершена, но и не failed
    # (например, пользователь отменил подтверждение текстов).
    print(f"\n--- Генерация прервана пользователем ---")
    print(f"Текущее состояние: {session.current_node}")
    print(f"Сессия сохранена: {settings.OUTPUT_DIR}/{session.session_id}")
    print(f"Можно продолжить: python main.py --session {session.session_id}")


# ---------------------------------------------------------------------------
# Точка входа
# ---------------------------------------------------------------------------

def main():
    setup_logging(
        level=settings.LOG_LEVEL,
        to_file=settings.LOG_TO_FILE,
        file_path=settings.LOG_FILE_PATH,
        colored=settings.LOG_FORMAT_COLORED,
    )
    init_langfuse(settings)

    parser = get_cli_parser()
    args = parser.parse_args()

    storage = JSONStorage(base_dir=settings.OUTPUT_DIR)
    llm = ProviderFactory.get_llm_provider(settings.LLM_PROVIDER)
    image = ProviderFactory.get_image_provider(settings.IMAGE_PROVIDER)
    orchestrator = Orchestrator(llm, image, storage)

    # Создаём новую сессию или восстанавливаем
    if args.session:
        session = storage.get_session(args.session)
        if not session:
            print(f"Сессия {args.session} не найдена.")
            return
        session_id = args.session
        print(f"--- Восстановлена сессия: {session_id} ---")
    else:
        count = args.count if args.count else parse_count(args.topic)
        request = GenerationRequest(
            topic=args.topic,
            truth_mode=TruthMode(args.truth),
            text_style=TextStyle(args.text_style),
            image_style=ImageStyle(args.image_style),
            work_mode=WorkMode(args.mode),
            count=count,
        )
        session = orchestrator.start_session(request)
        session_id = session.session_id
        print(f"--- Новая сессия начата: {session_id} ---")

    try:
        final_session = run_loop(orchestrator, session_id)
        print_final(final_session)
    finally:
        flush_langfuse()


if __name__ == "__main__":
    main()