from src.utils.cli_parser import get_cli_parser, parse_count
from src.models.schemas import GenerationRequest, TruthMode, TextStyle, ImageStyle, WorkMode
from src.core.orchestrator import Orchestrator, USER_ARBITRATION_THRESHOLD
from src.core.factory import ProviderFactory
from src.storage.json_storage import JSONStorage
from src.config.settings import settings


def _print_revision_history(session, problem_indices):
    """Выводит ТОЛЬКО последние замечания по проблемным темам."""
    print("\n--- ПОСЛЕДНИЕ ЗАМЕЧАНИЯ ПО ПРОБЛЕМНЫМ ТЕМАМ ---")
    for idx in problem_indices:
        history = session.revision_history.get(str(idx), [])
        if not history:
            print(f"\n[Тема {idx + 1}] История пуста.")
            continue

        # Берём последнюю запись от валидатора и последнюю от редактора (если есть)
        last_validator = next((r for r in reversed(history) if r.get("source") == "validator"), None)
        last_refiner = next((r for r in reversed(history) if r.get("source") == "refiner"), None)

        print(f"\n[Тема {idx + 1}] (всего версий в истории: {len(history)})")

        if last_refiner:
            print(f"  Текущая версия (от редактора):")
            print(f"    Название: {last_refiner.get('theme')}")
            print(f"    Сюжет:    {last_refiner.get('content')}")

        if last_validator:
            print(f"  Последнее замечание валидатора:")
            print(f"    {last_validator.get('note')}")
    print("-----------------------------------------------\n")


def main():
    parser = get_cli_parser()
    args = parser.parse_args()

    storage = JSONStorage(base_dir=settings.OUTPUT_DIR)
    llm = ProviderFactory.get_llm_provider(settings.LLM_PROVIDER)
    image = ProviderFactory.get_image_provider(settings.IMAGE_PROVIDER)
    orchestrator = Orchestrator(llm, image, storage)

    if args.session:
        session_id = args.session
        session = storage.get_session(session_id)
        if not session:
            print(f"Сессия {session_id} не найдена.")
            return
    else:
        count = args.count if args.count else parse_count(args.topic)
        request = GenerationRequest(
            topic=args.topic,
            truth_mode=TruthMode(args.truth),
            text_style=TextStyle(args.text_style),
            image_style=ImageStyle(args.image_style),
            work_mode=WorkMode(args.mode),
            count=count
        )
        session = orchestrator.start_session(request)
        session_id = session.session_id
        print(f"--- Новая сессия начата: {session_id} ---")

    while not session.is_completed:
        session = orchestrator.run_pipeline(session_id)

        if session.current_node == "failed":
            print("\n!!! Программа остановлена из-за ошибки.")
            break

        # Арбитраж пользователя — после 3+ REJECTED
        if session.current_node == "plan_needs_user_arbitration":
            print("\n" + "=" * 60)
            print(f"[!] АРБИТРАЖ ПОЛЬЗОВАТЕЛЯ")
            print(f"Валидатор отклонил план уже {session.validation_cycles} раз(а).")
            print(f"Порог автоматических циклов ({USER_ARBITRATION_THRESHOLD}) достигнут.")
            print("Спор между валидатором и редактором требует вашего вмешательства.")
            print("=" * 60)

            # Определяем проблемные темы из последнего фидбека валидатора
            try:
                import json as _json
                vf = _json.loads(getattr(session, "validator_feedback", "{}") or "{}")
                problem_indices = vf.get("invalid_indices", [])
            except Exception:
                problem_indices = []

            if problem_indices:
                _print_revision_history(session, problem_indices)
            else:
                print("(не удалось определить проблемные темы из фидбека валидатора)")

            print("Варианты:")
            print("  [Enter] — дать свободный комментарий ИИ для следующей итерации")
            print("  'ок' / 'хорошо' / 'хватит' — принудительно одобрить текущий вариант")
            print()
            user_input = input("Ваш ответ: ").strip()

            if user_input.lower() in ["хватит", "достаточно", "больше не", "ок", "хорошо"]:
                print("[USER] Принудительное одобрение текущего варианта.")
                # Помечаем все проблемные темы как одобренные принудительно
                for idx in problem_indices:
                    if idx < len(session.full_plan_items):
                        session.approved_plan_items[str(idx)] = session.full_plan_items[idx]
                        if idx not in session.approved_indices:
                            session.approved_indices.append(idx)
                # Сбрасываем счетчик — пользователь закрыл вопрос
                print(f"[CYCLE] validation_cycles reset → 0 (форсированное одобрение пользователем)")
                session.validation_cycles = 0
                session.current_node = "plan_approved"
                session.user_feedback = None
                storage.save_session(session)
            else:
                # Пользователь дал комментарий — отправляем в рефайн
                if user_input:
                    session.user_feedback = user_input
                    print(f"[USER] Комментарий передан ревьюеру/редактору.")
                else:
                    print(f"[USER] Без комментария — ревьюер и редактор будут работать сами.")
                # Узел уже plan_needs_user_arbitration — пайплайн вызовет _step_plan_refine
                storage.save_session(session)
            continue

        unconfirmed = [s for s in session.stories if s.text and not s.is_confirmed]
        if session.request.work_mode == WorkMode.CHECK and unconfirmed:
            print("\n--- СОГЛАСОВАНИЕ ТЕКСТОВ СЕРИИ ---")
            for i, story in enumerate(session.stories):
                print(f"\n[История {i + 1}/{len(session.stories)}]")
                print(f"Тема: {story.sub_topic}")
                print(f"Текст: {story.text}")
                print(f"Вопросы: {', '.join(story.questions)}")

            choice = input(
                "\nПодтвердить ВСЕ тексты и начать отрисовку? (y - да / n - отмена / r - перегенерировать всё): ").lower()
            if choice == 'y':
                for story in session.stories:
                    orchestrator.confirm_story(session_id, story.index)
            elif choice == 'r':
                for story in session.stories:
                    story.text = ""
                storage.save_session(session)
            else:
                print("Остановка по требованию пользователя.")
                return
            continue

        if session.is_completed:
            print(f"\n--- Генерация завершена! ---")
            print(f"Результаты в папке: output/{session_id}")
            break


if __name__ == "__main__":
    main()