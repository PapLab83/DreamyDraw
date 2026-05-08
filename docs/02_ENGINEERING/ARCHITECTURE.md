# ARCHITECTURE.md - DreamyDraw

## 1. Общая архитектура
Система строится по принципу **слоистой архитектуры (Layered Architecture)** с использованием **Dependency Injection** и **State Management**.

### Основные компоненты:
1.  **Entry Points (CLI):** `main.py` — взаимодействие с пользователем, парсинг аргументов, запуск оркестратора.
2.  **Orchestrator (Core):** `src/core/orchestrator.py` — управляет жизненным циклом генерации. Реализует сложный пайплайн с обратной связью (Reviewer/Refiner).
3.  **Domain Models (Pydantic):** `src/models/schemas.py` — типизированные структуры данных: `SessionState`, `StoryItem`, `Idea`.
4.  **Providers (Adapters):** `src/providers/` — интерфейсы и реализации для LLM (GPT) и Image Generation API.
5.  **Storage Layer:** `src/storage/json_storage.py` — работа с JSON-файлами сессий. Каждая сессия сохраняется в `output/<session_id>/state.json`.

## 2. Диаграмма потока данных (Пайплайн планирования)
Процесс формирования плана серии (Series Planning) значительно усложнен для повышения качества:

```text
User Request -> [Safety Gate] -> [Config Match]
      |
[Series Planner] -> Генерирует 10 идей (Idea Pool)
      |
[Idea Scoring] -> Присвоение "Детского индекса" (0-1) каждой идее
      |
[Score Normalize] -> Линейная нормализация + Epsilon (живучесть)
      |
[Idea Sampler] -> Взвешенная случайная выборка N идей
      |
[Plan Validator] <---------------------------+
      | (Rejected)                            |
      V                                       |
[Plan Reviewer] (Анализ решения пользователя) |
      | (Revise/Accept/Keep)                  |
      V                                       |
[Plan Refiner] (Точечное исправление темы) ---+
      | (Approved)
      V
[Approved Plan Items] (Зона доверия / Чистовик)
      |
[Story Content Gen] -> Написание литературных текстов
```

## 3. Зона доверия (Approved Plan Items)
Для предотвращения "галлюцинаций" и случайных изменений уже согласованного контента введена **Зона доверия**:
- Одобренные пользователем или валидатором (100 баллов) темы переносятся в `approved_plan_items`.
- При редактировании других тем через `Plan Refiner`, темы из зоны доверия **не передаются** в LLM-редактор, что физически исключает их порчу.

## 4. Математика отбора (Idea Sampling)
- **Санитарный фильтр:** Идеи со скором < 0.3 отсекаются сразу.
- **Взвешенная рулетка:** Шансы выбора пропорциональны их качеству, но сглажены константой `epsilon=0.2` для сохранения разнообразия.

## 5. Механизмы надежности
- **Persistence:** Полное состояние сессии (`SessionState`) сохраняется после каждого шага. Это позволяет возобновлять процесс после ввода пользователя.
- **Atomic Updates:** Код оркестратора гарантирует, что данные между `Series Planner`, `Validator` и `Refiner` синхронизируются через `full_plan_items` и `approved_plan_items`.
