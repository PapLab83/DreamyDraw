# MODULES.md - Модули и интерфейсы

## 1. Core / Orchestrator
- `Orchestrator`: Главный класс, управляющий пайплайном.
    - `run(request: GenerationRequest) -> List[Story]`
    - `confirm_text(session_id: str, index: int)`
    - `regenerate_text(session_id: str, index: int)`

## 2. Providers (Интерфейсы)
### LLM Provider
- `BaseLLMProvider`:
    - `generate_text(prompt: str) -> str`
    - `generate_questions(text: str) -> List[str]`
### Image Provider
- `BaseImageProvider`:
    - `generate_image(prompt: str, overlay_text: str) -> str (path_or_url)`

## 3. Storage (JSON Storage)
- `JSONStorage`: Класс для работы с файлами.
    - `save_session(session: SessionState)`
    - `get_session(session_id: str) -> SessionState`
    - `get_cache(key: str) -> Optional[Result]`
    - `save_cache(key: str, data: Result)`

## 4. Models (Pydantic)
- `GenerationRequest`: Тема, режимы, стили, количество.
- `Story`: Текст, путь к картинке, список вопросов.
- `SessionState`: Промежуточные данные, статус (pending/completed).

## 5. Configuration
- `Config`: Загрузка из `.env` и `config.yaml`.
- `PromptsRegistry`: Хранение шаблонов промптов.

## 6. Файловая структура (рекомендуемая)
```text
dreamydraw/
├── assets/
│   └── mocks/            # Мок-данные (картинки, тексты)
├── docs/                 # Документация
├── output/               # Результаты генерации (JSON + JPG)
├── src/
│   ├── core/
│   │   ├── orchestrator.py  # Логика пайплайна
│   │   └── pipeline.py      # Шаги процесса
│   ├── models/
│   │   └── schemas.py       # Pydantic модели
│   ├── providers/
│   │   ├── base.py          # Базовые интерфейсы
│   │   ├── llm_mock.py      # Мок LLM
│   │   └── image_mock.py    # Мок генератора картинок
│   ├── storage/
│   │   ├── json_storage.py  # Работа с файлами и блокировками
│   │   └── cache.py         # Логика кеширования
│   ├── utils/
│   │   ├── cli_parser.py    # Парсинг аргументов
│   │   └── logger.py        # Логирование
│   └── config.py            # Загрузка настроек
├── .env.example
├── main.py                  # Точка входа (CLI)
└── requirements.txt
```
