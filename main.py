from src.utils.cli_parser import get_cli_parser, parse_count
from src.models.schemas import GenerationRequest, TruthMode, TextStyle, ImageStyle, WorkMode
from src.core.orchestrator import Orchestrator
from src.providers.llm_mock import LLMMockProvider
from src.providers.image_mock import ImageMockProvider
from src.storage.json_storage import JSONStorage

def main():
    parser = get_cli_parser()
    args = parser.parse_args()

    # Инициализация
    storage = JSONStorage()
    llm = LLMMockProvider()
    image = ImageMockProvider()
    orchestrator = Orchestrator(llm, image, storage)

    if args.session:
        session_id = args.session
        session = storage.get_session(session_id)
        if not session:
            print(f"Сессия {session_id} не найдена.")
            return
    else:
        # Создание новой сессии
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
        
        current_idx = session.current_step
        if current_idx < len(session.stories):
            story = session.stories[current_idx]
            
            # Если мы в режиме check и текст готов, но не подтвержден
            if session.request.work_mode == WorkMode.CHECK and not story.is_confirmed:
                print(f"\n[История {current_idx + 1}/{session.request.count}]")
                print(f"Текст: {story.text}")
                print(f"Вопросы: {', '.join(story.questions)}")
                
                choice = input("\nПодтвердить текст? (y/n/r - regenerate): ").lower()
                if choice == 'y':
                    orchestrator.confirm_story(session_id, current_idx)
                elif choice == 'r':
                    # Логика регенерации (в прототипе просто сбросим текст)
                    story.text = ""
                    storage.save_session(session)
                else:
                    print("Остановка по требованию пользователя.")
                    break
        
        if session.is_completed:
            print(f"\n--- Генерация завершена! ---")
            print(f"Результаты в папке: output/{session_id}")
            break

if __name__ == "__main__":
    main()
