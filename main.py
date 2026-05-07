from src.utils.cli_parser import get_cli_parser, parse_count
from src.models.schemas import GenerationRequest, TruthMode, TextStyle, ImageStyle, WorkMode
from src.core.orchestrator import Orchestrator
from src.core.factory import ProviderFactory
from src.storage.json_storage import JSONStorage
from src.config.settings import settings

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

    # Запуск пайплайна
    while not session.is_completed:
        session = orchestrator.run_pipeline(session_id)
        
        if session.current_node == "failed":
            print("\n!!! Программа остановлена из-за ошибки.")
            break

        # Обработка обратной связи по ПЛАНУ
        if session.current_node == "plan_needs_refine":
            print("\n--- ОБРАТНАЯ СВЯЗЬ ПО ПЛАНУ ---")
            print("Критик нашел несоответствия в некоторых темах.")
            user_input = input("Ваш совет для ИИ (Enter, чтобы ИИ исправил сам по советам критика): ").strip()
            if user_input:
                session.user_feedback = user_input
                storage.save_session(session)
            continue # Возвращаемся в пайплайн для запуска step-plan-refine

        # Пакетное согласование ТЕКСТОВ
        unconfirmed = [s for s in session.stories if s.text and not s.is_confirmed]
        if session.request.work_mode == WorkMode.CHECK and unconfirmed:
            print("\n--- СОГЛАСОВАНИЕ ТЕКСТОВ СЕРИИ ---")
            for i, story in enumerate(session.stories):
                print(f"\n[История {i+1}/{len(session.stories)}]")
                print(f"Тема: {story.sub_topic}")
                print(f"Текст: {story.text}")
                print(f"Вопросы: {', '.join(story.questions)}")

            choice = input("\nПодтвердить ВСЕ тексты и начать отрисовку? (y - да / n - отмена / r - перегенерировать всё): ").lower()
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
