# CONFIGURATION_CONSTANTS.md - Константы и конфигурация

Документ фиксирует целевое состояние конфигурации: все магические значения в активном Stage 1-2 контуре и prompt pipeline должны быть вынесены в именованные константы или настройки.

Status: current Release 2 configuration reference. References to removed legacy `main.py`, `PromptBuilder`, image polling or media constants below are historical cleanup context unless the value is still used by active provider compatibility code.

---

## 1. Цель

Сделать поведение DreamyDraw управляемым из одного места:

- числовые пороги не должны быть зашиты внутри методов;
- промпты не должны содержать несинхронизируемые продуктовые лимиты;
- значения из `.env`, `settings.py`, промптов и документации должны совпадать;
- смена порога или лимита не должна требовать поиска по проекту.

---

## 2. Правило размещения

| Тип значения | Где хранить | Пример |
|---|---|---|
| Переменные окружения и внешние настройки запуска | `src/config/settings.py` + `.env.example` | провайдеры, модели, директории, таймауты API |
| Бизнес-лимиты пайплайна | `src/config/settings.py` или `src/config/constants.py` | `IDEA_POOL_SIZE`, `MIN_CHILD_INDEX`, `MAX_VALIDATION_RETRIES` |
| Строковые имена состояний и решений | `src/config/constants.py` или Enum в моделях | `plan_needs_refine`, `REVISE`, `ALREADY_OK` |
| Значения, которые попадают в промпты | настройки + runtime composition через active prompt pipeline | возраст, число вопросов, число идей |
| Чисто локальные временные индексы цикла | оставить локально | `for i, item in enumerate(...)` |

Если значение влияет на поведение продукта, стоимость, качество, лимиты или UX, оно не должно быть локальным литералом.

---

## 3. Инвентаризация текущих магических значений

### Код

The legacy `main.py`, old `Orchestrator`, old `PromptBuilder` and old plan/text/image nodes referenced below were removed during Release 1 cleanup. Keep the table as reference input for a future shared/config cleanup pass.

| Значение | Где сейчас | Целевое имя | Назначение |
|---|---|---|---|
| `3` | `src/core/orchestrator.py`, `main.py` | `USER_ARBITRATION_THRESHOLD` | Сколько REJECTED-циклов валидатор/редактор проходят до вмешательства пользователя |
| `5` | `src/core/orchestrator.py` | `MAX_VALIDATION_RETRIES` | Абсолютная защита от бесконечного цикла валидации |
| `0.3` | `_step_idea_scoring` | `MIN_CHILD_INDEX` | Нижний порог детского индекса для идеи |
| `0.2` | `_step_score_normalize` | `SCORE_NORMALIZATION_EPSILON` | Смещение при нормализации весов |
| `0.7` | fallback идеи в `_step_idea_scoring` | `FALLBACK_IDEA_CHILD_INDEX` | Скор fallback-идеи |
| `0.5` | fallback при ошибке скоринга | `DEFAULT_IDEA_CHILD_INDEX` | Скор по умолчанию при сбое LLM |
| `100`, `80`, `60` | debug-preview и разделители в `orchestrator.py` | `DEBUG_CONTENT_PREVIEW_CHARS`, `DEBUG_TEXT_SEPARATOR_WIDTH` | Длина отладочных превью и ширина разделителей |
| `30` | `src/providers/gptunnel_provider.py` | `MEDIA_POLL_MAX_ATTEMPTS` | Максимум попыток опроса генерации картинки |
| `10` | `requests.post(..., timeout=10)` | `HTTP_REQUEST_TIMEOUT_SECONDS` | Таймаут HTTP-запроса |
| `25` | `time.sleep(25)` | `MEDIA_POLL_INTERVAL_SECONDS` | Интервал штатного polling картинки |
| `10` | `time.sleep(10)` в exception | `MEDIA_RETRY_INTERVAL_SECONDS` | Интервал повтора после сетевой ошибки |
| `"1:1"` | payload media provider | `IMAGE_ASPECT_RATIO` | Соотношение сторон картинки |
| `3` | `questions[:3]` в mock provider | `MAX_QUESTIONS` | Максимальное число вопросов |
| `"story_{i}.png"` | путь результата | `STORY_IMAGE_FILENAME_TEMPLATE` | Шаблон имени файла картинки |

### Промпты

| Значение | Где встречается | Целевое имя | Назначение |
|---|---|---|---|
| `10 идей` | `text/planners/SERIES_PLANNER_*.md` | `IDEA_POOL_SIZE` | Размер пула идей |
| `3-5` / `3–5 лет` | почти все текстовые промпты | `TARGET_AGE_MIN`, `TARGET_AGE_MAX` | Возрастная аудитория |
| `3-5 предложений` | `TEXT_BASE_PROMPT.md` | `STORY_SENTENCES_MIN`, `STORY_SENTENCES_MAX` (legacy global) | Длина истории |
| per-age 3–4 / 3–5 | `src/core/stage2_length_policy.py` | `AGE_STORY_LENGTH_POLICIES` | Enforcement по `target_age` (§3.4) |
| `2-3 вопроса` | `TEXT_BASE_PROMPT.md`, режимные промпты | `MIN_QUESTIONS`, `MAX_QUESTIONS` | Количество вопросов |
| `2-3 персонажа`, `3-4 персонажа` | валидаторы и режимные промпты | `MAX_MAIN_CHARACTERS`, `MAX_SCENE_CHARACTERS` | Ограничение сложности сцены |
| `15-30 секунд` | `TEXT_BASE_PROMPT.md` | `READING_TIME_MIN_SECONDS`, `READING_TIME_MAX_SECONDS` | Целевая длительность чтения |

Продуктовые значения в промптах допустимы только как подставленные параметры. Иначе промпты и код начинают жить разными правилами.

---

## 4. Целевая структура `Settings`

Минимальный набор настроек после рефакторинга:

```python
class Settings(BaseSettings):
    DEFAULT_COUNT: int = 3
    MAX_COUNT: int = 10
    DEFAULT_TARGET_AGE: str = "5"
    DEFAULT_TRUTH_MODE: str = "TRUTH"
    DEFAULT_CULTURAL_CONTEXT: str = "RUSSIAN_FOLK"
    DEFAULT_UTILITY_MODE: str = "NARRATIVE"

    TARGET_AGE_MIN: int = 3
    TARGET_AGE_MAX: int = 5
    STORY_SENTENCES_MIN: int = 3
    STORY_SENTENCES_MAX: int = 5
    MIN_QUESTIONS: int = 2
    MAX_QUESTIONS: int = 3

    IDEA_POOL_SIZE: int = 10
    MIN_CHILD_INDEX: float = 0.3
    DEFAULT_IDEA_CHILD_INDEX: float = 0.5
    FALLBACK_IDEA_CHILD_INDEX: float = 0.7
    SCORE_NORMALIZATION_EPSILON: float = 0.2

    USER_ARBITRATION_THRESHOLD: int = 3
    MAX_VALIDATION_RETRIES: int = 5

    HTTP_REQUEST_TIMEOUT_SECONDS: int = 10
    MEDIA_POLL_MAX_ATTEMPTS: int = 30
    MEDIA_POLL_INTERVAL_SECONDS: int = 25
    MEDIA_RETRY_INTERVAL_SECONDS: int = 10
    IMAGE_ASPECT_RATIO: str = "1:1"
```

Если часть значений не должна меняться через `.env`, её можно оставить в `src/config/constants.py`, но использовать по имени.

---

## 5. Промпты после рефакторинга

В активном Release 1 контуре значения должны попадать в prompt context через `PromptRegistry` / `PromptComposer` и stage-specific runtime context. Legacy `PromptBuilder` был удален вместе со старым runtime-пайплайном и не является целевым механизмом.

Пример целевого подхода:

```text
Основная аудитория текста - ребенок {target_age_min}-{target_age_max} лет.
Сгенерируй {idea_pool_size} уникальных идей.
После истории нужно задать {min_questions}-{max_questions} вопроса.
```

Для обратной совместимости можно сначала поддержать оба формата:

- существующие `{topic}`, `{truth_mode}`;
- новые `{idea_pool_size}`, `{target_age_min}`, `{target_age_max}`, `{min_questions}`, `{max_questions}`.

---

## 6. DoD рефакторинга

Рефакторинг считается завершенным, когда:

1. В `src/` нет поведенческих числовых литералов без имени, кроме локальных индексов, булевых значений и очевидных нейтральных значений `0`/`1`.
2. Active CLI and orchestration code do not depend on hidden local magic values; общие значения берутся из `settings` или `constants`.
3. `.env.example` содержит все настройки, которые допускается менять без правки кода.
4. Промпты получают продуктовые лимиты через active prompt/runtime context.
5. `REQUIREMENTS.md`, `ORCHESTRATOR_SPEC.md` и этот документ описывают одни и те же лимиты.
6. Есть тесты на `parse_count`, пороги валидации, фильтр `child_index`, нормализацию весов и подстановку параметров в промпты.

---

## 7. Риски

- Простая замена чисел в промптах может изменить качество LLM-ответов. После подстановки параметров нужны тестовые прогоны на типовых темах.
- `DEFAULT_COUNT` приведён к документированному значению `3`. Если продуктово нужен другой дефолт, менять его нужно только через `constants.py` / `.env`.
- В промптах есть числа, которые являются примерами или пунктами списков. Их не нужно выносить в конфиг.
