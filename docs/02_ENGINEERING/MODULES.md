# MODULES.md - Модули и интерфейсы

## 1. Core / Orchestrator (`src/core/orchestrator.py`)
Центральный узел системы, реализующий бизнес-логику пайплайна.

- **Основные методы:**
    - `run_pipeline(session_id: str)`: Запуск или возобновление процесса генерации.
    - `_step_series_planner`: Генерация настраиваемого пула идей.
    - `_step_idea_scoring`: Оценка идей по "Детскому индексу".
    - `_step_idea_sampler`: Взвешенный отбор N уникальных идей.
    - `_step_plan_validator`: Проверка идей Критиком.
    - `_step_plan_refine`: Цикл Reviewer -> Refiner для исправления тем.
    - `_pipeline_content_generation`: Генерация финальных рассказов на базе одобренного плана.

## 2. Prompt Builder (`src/core/prompt_builder.py`)
Динамическая сборка промптов из шаблонов в `docs/03_PROMPTS/`.
- Поддерживает инъекцию контекста (approved items, user comments, validator feedback).

## 3. Providers (`src/providers/`)
- `BaseLLMProvider`: Интерфейс для текстовых моделей.
- `BaseImageProvider`: Интерфейс для генерации изображений.
- `LLMMockProvider`: Мок-провайдер для тестирования логики без затрат на API.

## 4. Models (`src/models/schemas.py`)
- `Idea`: Структура для хранения варианта сюжета со скорингом.
- `StoryItem`: Окончательная история (текст, вопросы, картинка).
- `SessionState`: Полный снимок состояния сессии, включая "Зону доверия" (`approved_plan_items`).

## 5. Storage (`src/storage/json_storage.py`)
- `JSONStorage`: Сохранение и загрузка `SessionState`. Использует структуру `output/<session_id>/state.json`.

## 6. Configuration (`src/config/settings.py`)
- `Settings`: Настройки из `.env` (API ключи, модели, лимиты).
- Все поведенческие лимиты и пороги должны быть доступны по имени через `settings.py` или `constants.py`: размер пула идей, пороги валидации, пороги скоринга, лимиты вопросов, возрастные рамки, polling/timeout провайдеров.
- Детальная схема вынесения магических значений описана в `docs/02_ENGINEERING/CONFIGURATION_CONSTANTS.md`.

## 7. Файловая структура (Актуальная)
```text
dreamydraw/
├── docs/                 # Документация и Системные промпты
│   └── 03_PROMPTS/       # Шаблоны промптов (Planner, Validator, и др.)
├── output/               # Результаты сессий (JSON + JPG)
├── src/
│   ├── core/
│   │   ├── orchestrator.py  # Главный оркестратор
│   │   ├── factory.py       # Фабрика провайдеров
│   │   └── prompt_builder.py # Сборщик промптов
│   ├── models/
│   │   └── schemas.py       # Pydantic модели
│   ├── providers/
│   │   ├── base.py          # Базовые классы
│   │   └── gptunnel.py      # Реализация для GPTunnel
│   ├── storage/
│   │   └── json_storage.py  # Хранилище сессий
│   └── config/
│       └── settings.py      # Настройки проекта
├── main.py                  # Точка входа
└── requirements.txt
```
