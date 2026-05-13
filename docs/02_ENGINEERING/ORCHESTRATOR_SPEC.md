# Спецификация оркестратора (DreamyDraw)

Технический контракт логики работы пайплайна. Описывает что делает оркестратор, в каком порядке, как обрабатывает циклы валидации и где может вмешаться пользователь.

Документ организован в двух слоях:
- **Логический слой** (разделы 1, 3, 4, 5, 9) — что делает пайплайн, без привязки к реализации.
- **Технический слой** (разделы 2, 6, 8) — как это собрано в коде на LangGraph.

---

## 1. Общий пайплайн

Оркестратор работает по принципу **Plan → Validate (with refinement loops) → Generate**.

Высокоуровневые фазы:

1. **Валидация входа** — проверка темы и совместимости с режимом.
2. **Планирование серии** — генерация пула идей и выбор финального плана.
3. **Контур валидации плана** — циклическая проверка плана с возможной редактурой и арбитражом пользователя.
4. **Генерация контента** — пакетная генерация текстов, согласование с пользователем, генерация иллюстраций.

Полный поток (упрощённо):

```
Тема + Конфигурация
        │
        ▼
[1] Safety Gate ──fail──▶ STOP
        │ pass
        ▼
[2] Config Match ──mismatch──▶ [USER: переключить режим?]
        │ pass                         │
        │ ◀──────────────── y ─────────┤
        │                              └── n ──▶ STOP
        ▼
[3] Series Planner (режимо-зависимый)
        │
        ▼
[4] Idea Scoring
        │
        ▼
[5] Score Normalize
        │
        ▼
[6] Idea Sampler ─────► план серии (N идей)
        │
        ▼
┌─────► [7] Plan Validator (режимо-зависимый)
│           │
│           ├─ APPROVED ─────────────────────┐
│           │                                │
│           └─ REJECTED                      │
│                │                           │
│                ▼                           │
│           [counter++]                      │
│                │                           │
│                ├─ counter < threshold      │
│                │   │                       │
│                │   ▼                       │
│                │  [8] Plan Reviewer        │
│                │   │                       │
│                │   ▼                       │
│                │  [9] Plan Refiner ────────┘ (если REVISE)
│                │                           │
│                └─ counter >= threshold     │
│                    │                       │
│                    ▼                       │
│                [USER ARBITRATION]          │
│                    │                       │
│                    ├─ "ок"/"хорошо" ───────│──▶ форсированное одобрение
│                    │                       │
│                    └─ комментарий ─────────│──▶ [8] → [9] → возврат в [7]
│                                            │
└────────────────────────────────────────────┘
                                             │
                                             ▼
                              [10] Text Generation (по каждой истории)
                                             │
                                             ▼
                              [11] User Confirmation (если режим check)
                                             │     │
                                             │     ├─ y ──▶ продолжить
                                             │     ├─ n ──▶ STOP
                                             │     └─ r ──▶ возврат в [10]
                                             ▼
                              [12] Image Generation
                                             │
                                             ▼
                                          DONE
```

В пайплайне есть **три точки взаимодействия с пользователем**:
- арбитраж конфигурации (если тема не сочетается с выбранным режимом),
- арбитраж плана (если валидатор не может сойтись с редактором),
- подтверждение текстов (только в режиме `check`).

Подробнее — в разделе 4.

---

## 2. Граф пайплайна

Оркестратор реализован как **LangGraph-граф**. Каждый шаг логики из раздела 1 — это отдельная нода. Переходы между нодами заданы рёбрами (включая условные `add_conditional_edges`), а не `if/elif` в коде. Точки взаимодействия с пользователем реализованы через `interrupt()`.

### 2.1 Ноды графа

| Идентификатор ноды | Логический шаг | Тип |
|---|---|---|
| `NODE_SAFETY_GATE` | [1] Safety Gate | 🤖 LLM |
| `NODE_CONFIG_MATCH` | [2] Config Match | 🤖 LLM |
| `NODE_CONFIG_ARBITRATION` | пользовательский арбитраж конфига | 🙋 Interrupt |
| `NODE_SERIES_PLANNER` | [3] Series Planner | 🤖 LLM |
| `NODE_IDEA_SCORING` | [4] Idea Scoring | 🤖 LLM |
| `NODE_SCORE_NORMALIZE` | [5] Score Normalize | ⚙️ Детерминированный |
| `NODE_IDEA_SAMPLER` | [6] Idea Sampler | ⚙️ Детерминированный |
| `NODE_PLAN_VALIDATOR` | [7] Plan Validator | 🤖 LLM |
| `NODE_PLAN_REVIEWER` | [8] Plan Reviewer | 🤖 LLM |
| `NODE_PLAN_REFINER` | [9] Plan Refiner | 🤖 LLM |
| `NODE_PLAN_ARBITRATION` | пользовательский арбитраж плана | 🙋 Interrupt |
| `NODE_TEXT_GENERATION` | [10] Text Generation | 🤖 LLM |
| `NODE_USER_CONFIRMATION` | [11] User Confirmation (HITL) | 🙋 Interrupt |
| `NODE_IMAGE_GENERATION` | [12] Image Generation | 🤖 Image Model |

Любая нода имеет сигнатуру `(GraphState) -> GraphState`. Это позволяет нодам быть автономными и пригодными для отдельного юнит-тестирования.

### 2.2 Рёбра

Линейные рёбра:
- `START → safety_gate`
- `series_planner → idea_scoring → score_normalize → idea_sampler`
- `image_generation → END`

Условные рёбра (routing-функции в `src/core/graph/routing.py`):

| Из ноды | Routing-функция | Возможные таргеты |
|---|---|---|
| `safety_gate` | `route_after_safety` | `config_match`, `END` |
| `config_match` | `route_after_config_match` | `series_planner`, `config_arbitration`, `END` |
| `config_arbitration` | `route_after_config_arbitration` | `series_planner`, `END` |
| `idea_sampler` | `_route_after_sampler` | `plan_validator`, `END` |
| `plan_validator` | `route_after_validator` | `text_generation`, `plan_reviewer`, `plan_arbitration`, `END` |
| `plan_reviewer` | `route_after_reviewer` | `plan_refiner`, `END` |
| `plan_refiner` | `route_after_refiner` | `plan_validator`, `END` |
| `plan_arbitration` | `route_after_arbitration` | `text_generation`, `plan_reviewer` |
| `text_generation` | `route_after_text_generation` | `user_confirmation`, `image_generation` |
| `user_confirmation` | `route_after_user_confirmation` | `image_generation`, `text_generation`, `END` |

### 2.3 Поле `current_node`

`SessionState.current_node` сохранён в схеме и используется как **информационный маркер прогресса**:
- отображение в CLI (что происходит сейчас, на чём прервалась сессия),
- восстановление контекста при `--session <id>`,
- инвариант: значение `"failed"` означает терминальную ошибку (см. раздел 9).

**Переходы между нодами определяет граф**, а не значение `current_node`.

### 2.4 Сборка графа

Граф собирается один раз в `Orchestrator.__init__` через `build_graph(...)`. Все зависимости (`llm`, `image`, `storage`, `prompt_builder`) инжектируются в ноды через фабрики `make_<node>(...)`, которые возвращают замыкания с подшитыми зависимостями. Это гарантирует, что:
- ноды не таскают глобальный контекст,
- их можно подменять моками в тестах,
- каждая нода видна в Langfuse как отдельный span благодаря `@observe`.

---

## 3. Описание узлов пайплайна

### Фаза I. Валидация входа

#### [1] Safety Gate
- **Нода:** `NODE_SAFETY_GATE` (`make_safety_gate`)
- **Тип:** 🤖 LLM
- **Промпт:** `text/SAFETY_GATE.md`
- **Цель:** Отсечь темы с насилием, взрослым контентом, опасными сценариями.
- **Вход:** `topic`.
- **Выход:** при неудаче — `current_node = "failed"` → переход в `END`.
- **DoD:** Тема признана безопасной для детской аудитории.

#### [2] Config Match
- **Нода:** `NODE_CONFIG_MATCH` (`make_config_match`)
- **Тип:** 🤖 LLM
- **Промпт:** `text/CONFIG_MATCH.md`
- **Цель:** Проверить совместимость темы и выбранного `truth_mode`.
- **Логика:** Если несовместимо — граф уходит в ноду `config_arbitration` (interrupt с предложенным режимом). Если совместимо — переход к планировщику.
- **DoD:** Конфигурация признана логически верной либо явно подтверждена пользователем.

#### [2a] Config Arbitration (HITL)
- **Нода:** `NODE_CONFIG_ARBITRATION` (`make_config_arbitration`)
- **Тип:** 🙋 Interrupt
- **Цель:** Спросить пользователя, переключить ли `truth_mode` на предложенный валидатором.
- **Payload interrupt:** `{type: "config_arbitration", reason, current_mode, suggested_mode}`.
- **Resume value:** `"y"` (переключить и продолжить) / `"n"` (отменить).
- **DoD:** Пользователь либо подтвердил смену режима, либо отменил сессию.

### Фаза II. Планирование серии

#### [3] Series Planner
- **Нода:** `NODE_SERIES_PLANNER` (`make_series_planner`)
- **Тип:** 🤖 LLM
- **Промпт (режимо-зависимый):**
  - `text/planners/SERIES_PLANNER_TRUTH.md`
  - `text/planners/SERIES_PLANNER_MYTH.md`
  - `text/planners/SERIES_PLANNER_FAIRY_TALE.md`
- **Цель:** Сгенерировать пул идей в правильном жанровом регистре + `global_context` (описание персонажа).
- **Выход:** `session.ideas_pool` (`List[Idea]`), `session.global_context`.
- **DoD:** Пул из валидных идей в нужном режиме готов к скорингу.

#### [4] Idea Scoring
- **Нода:** `NODE_IDEA_SCORING` (`make_idea_scoring`)
- **Тип:** 🤖 LLM
- **Промпт:** `text/IDEA_SCORING.md` (режимо-нейтральный, оценивает безопасность для возраста 3-5).
- **Цель:** Каждой идее присвоить `child_index` ∈ [0, 1].
- **Доп. логика:** идеи с `child_index < MIN_CHILD_INDEX` отсеиваются. Если пул пуст — fallback "Прогулка в лесу" со скором `FALLBACK_IDEA_CHILD_INDEX`.
- **DoD:** Все идеи имеют скор; пул непустой (за счёт fallback).

#### [5] Score Normalize
- **Нода:** `NODE_SCORE_NORMALIZE` (`make_score_normalize`)
- **Тип:** ⚙️ Детерминированный
- **Алгоритм:** Линейная нормализация со смещением `SCORE_NORMALIZATION_EPSILON` (см. раздел 7).
- **Цель:** Получить веса для взвешенной выборки.
- **DoD:** У каждой идеи `normalized_weight`, сумма весов = 1.

#### [6] Idea Sampler
- **Нода:** `NODE_IDEA_SAMPLER` (`make_idea_sampler`)
- **Тип:** ⚙️ Детерминированный
- **Алгоритм:** Взвешенная случайная выборка без повторений (`random.choices` + удаление выбранной + ренормализация).
- **Цель:** Выбрать `count` уникальных идей из пула.
- **Выход:** `session.series_plan` (список названий тем), `session.full_plan_items` (список объектов `{theme, content}`), инициализация `session.revision_history`.
- **DoD:** Финальный план из N идей готов к валидации.

### Фаза III. Контур валидации плана

#### [7] Plan Validator
- **Нода:** `NODE_PLAN_VALIDATOR` (`make_plan_validator`)
- **Тип:** 🤖 LLM
- **Промпт (режимо-зависимый):**
  - `text/validators/PLAN_VALIDATOR_TRUTH.md`
  - `text/validators/PLAN_VALIDATOR_MYTH.md`
  - `text/validators/PLAN_VALIDATOR_FAIRY_TALE.md`
- **Цель:** Проверить каждую тему на соответствие правилам режима ("красные флаги").
- **Логика:**
  - Темы из `approved_indices` пропускает (статус `ALREADY_APPROVED_BY_YOU`).
  - Для отклонённых — записывает `validator_feedback` с `invalid_indices`, `reasons`, `suggestions`.
  - При `APPROVED` всех тем — граф уходит в `text_generation`, **счётчик `validation_cycles` сбрасывается в 0**.
  - При `REJECTED` — **инкремент `validation_cycles += 1`**, переход в `plan_reviewer` (если < `USER_ARBITRATION_THRESHOLD`) или в `plan_arbitration` (если ≥ порога).
- **DoD:** Все темы либо одобрены, либо помечены как требующие правки с указанием причины.

#### [8] Plan Reviewer
- **Нода:** `NODE_PLAN_REVIEWER` (`make_plan_reviewer`)
- **Тип:** 🤖 LLM
- **Промпт:** `text/PLAN_REVIEWER.md` (режимо-нейтральный).
- **Цель:** По каждой теме принять одно из решений:
  - `REVISE` — отправить на доработку редактору.
  - `KEEP_ORIGINAL` — оставить оригинал (только при явном требовании автора).
  - `ALREADY_OK` — тема не была отклонена и не требует изменений.
- **Доп. логика:**
  - При **пустом ответе** ревьюера — fallback `_build_fallback_decisions` (отклонённые → REVISE, остальные → ALREADY_OK).
  - **Страховка:** если ревьюер выбрал `KEEP_ORIGINAL` для отклонённой темы при пустом `user_comment` — принудительная замена на `REVISE`.
- **DoD:** Каждой теме присвоено решение.

#### [9] Plan Refiner
- **Нода:** `NODE_PLAN_REFINER` (`make_plan_refiner`)
- **Тип:** 🤖 LLM
- **Промпт (режимо-зависимый):**
  - `text/refiners/PLAN_REFINER_TRUTH.md`
  - `text/refiners/PLAN_REFINER_MYTH.md`
  - `text/refiners/PLAN_REFINER_FAIRY_TALE.md`
- **Цель:** Аккуратно довести `validator_suggestion` до финального вида (без отсебятины).
- **Принцип:** Редактор — НЕ автор. Берёт рекомендацию валидатора как основу, делает минимальные правки (опечатки, имя героя в серии). Запрещено добавлять новые предложения, эмоциональные обобщения, мораль.
- **Логика:** Запускается только для тем с решением `REVISE`. При пустом ответе → `current_node = "failed"`, граф уходит в `END`. После успешной правки — возврат в `plan_validator`.
- **DoD:** Все темы с решением `REVISE` обновлены в `full_plan_items`.

#### [9a] Plan Arbitration (HITL)
- **Нода:** `NODE_PLAN_ARBITRATION` (`make_plan_arbitration`)
- **Тип:** 🙋 Interrupt
- **Цель:** Показать пользователю проблемные темы и попросить либо свободный комментарий, либо форсированное одобрение.
- **Payload interrupt:** `{type: "plan_arbitration", validation_cycles, threshold, problems: [{index, current_theme, current_content, last_validator_note, history_size}]}`.
- **Resume value:**
  - `"ок"` / `"хорошо"` / `"хватит"` — форсированное одобрение текущего плана, переход в `text_generation`, счётчик сбрасывается.
  - Любой другой текст — сохраняется в `session.user_feedback` и граф уходит в `plan_reviewer` для нового цикла.
- **DoD:** Пользователь либо принудительно одобрил план, либо дал комментарий для следующей итерации.

### Фаза IV. Генерация контента

#### [10] Text Generation
- **Нода:** `NODE_TEXT_GENERATION` (`make_text_generation`)
- **Тип:** 🤖 LLM
- **Промпт:** `text/TEXT_BASE_PROMPT.md` + `truth_modes/{TRUTH|MYTH|FAIRY_TALE}.md` + `styles/{GENTLE|EDUCATIONAL|PLAYFUL}.md`.
- **Цель:** Сгенерировать полный текст истории + 2-3 вопроса по тексту.
- **Вход:** одобренный сюжет из `approved_plan_items[i]`.
- **Выход:** `story.text`, `story.questions` для каждой истории.
- **Дальнейший роут:** в режиме `check` — в `user_confirmation`, в режиме `fast` — сразу в `image_generation`.
- **DoD:** Все истории имеют текст и вопросы.

#### [11] User Confirmation (только в режиме `check`)
- **Нода:** `NODE_USER_CONFIRMATION` (`make_user_confirmation`)
- **Тип:** 🙋 Interrupt
- **Цель:** Пользователь подтверждает все тексты пакетно перед генерацией картинок.
- **Payload interrupt:** `{type: "user_confirmation", stories: [{index, sub_topic, text, questions}]}`.
- **Resume value:**
  - `"y"` — подтвердить → переход в `image_generation`. Все `StoryItem.is_confirmed = True`.
  - `"r"` — перегенерировать всё → возврат в `text_generation`.
  - `"n"` (или любое другое) — отмена → `current_node = "failed"`, переход в `END`.
- **DoD:** Все тексты подтверждены либо сессия завершена.

#### [12] Image Generation
- **Нода:** `NODE_IMAGE_GENERATION` (`make_image_generation`)
- **Тип:** 🤖 Image Model
- **Промпт:** `image/IMAGE_BASE_PROMPT.md` + `image/styles/{CARTOON|WATERCOLOR|CLAY|NIGHT}.md`.
- **Цель:** Сгенерировать иллюстрацию для каждой истории.
- **Логика:** Синхронный вызов провайдера, сохранение в `output/<session_id>/story_{i}.png`.
- **DoD:** `session.is_completed = True`.

---

## 4. Циклы валидации и арбитраж пользователя

Ключевой механизм качества плана. Реализует контролируемый цикл "проверить → исправить → проверить" с защитой от бесконечной петли.

### Счётчик `validation_cycles`

- **Хранение:** `SessionState.validation_cycles: int`.
- **Семантика:** считает количество **REJECTED**-результатов от валидатора.
- **Инкремент:** в ноде `plan_validator` при статусе REJECTED.
- **Сброс в 0:** при полном одобрении плана (переход в `text_generation`) и при форсированном одобрении через арбитраж.
- **Назначение сброса:** валидатор будет переиспользоваться на других этапах (валидация текстов, картинок) — счётчик каждого этапа должен начинаться с нуля.

### Пороги и поведение

| `validation_cycles` после инкремента | Поведение |
|---|---|
| от 1 до `USER_ARBITRATION_THRESHOLD - 1` | Граф уходит в `plan_reviewer` → `plan_refiner` → обратно в `plan_validator`. Авторежим: ревьюер и редактор работают самостоятельно, без участия пользователя. |
| `USER_ARBITRATION_THRESHOLD` и выше | Граф уходит в `plan_arbitration` (interrupt). Пользователь видит проблемные темы и может вмешаться. |
| > `MAX_VALIDATION_RETRIES` | Принудительный переход в `END` через `current_node = "failed"`. Защита от бесконечной петли. |

### Арбитраж пользователя

Когда `validation_cycles >= USER_ARBITRATION_THRESHOLD`, граф останавливается на `plan_arbitration`. Пользователю показываются:
- Текущая версия проблемных тем (от редактора).
- Последнее замечание валидатора по каждой теме.
- Размер истории правок по каждой теме.

Пользователь может:
- Ввести **свободный комментарий** → сохраняется в `session.user_feedback`, граф уходит в `plan_reviewer` для нового цикла.
- Ввести **`ок` / `хорошо` / `хватит`** → форсированное одобрение текущей версии без валидации, счётчик сбрасывается, граф уходит в `text_generation`.

### История правок

Все изменения тем сохраняются в `SessionState.revision_history: dict[str(idx), list[record]]`.
Каждая запись содержит:
- `source` — `planner`, `validator`, `reviewer:accept_suggestion`, `reviewer:keep_original`, `refiner`.
- `theme`, `content` — версия на момент записи.
- `note` — пояснение.

Используется в арбитраже для показа пользователю и для отладки (полная история сохраняется в JSON-сессии).

---

## 5. Режимная архитектура

Три режима правдивости (`TruthMode`): `Правда` / `Миф` / `Сказка`.

Промпты разделены по режимам в трёх ключевых точках пайплайна:

| Узел | Файлы |
|---|---|
| Series Planner | `planners/SERIES_PLANNER_{TRUTH,MYTH,FAIRY_TALE}.md` |
| Plan Validator | `validators/PLAN_VALIDATOR_{TRUTH,MYTH,FAIRY_TALE}.md` |
| Plan Refiner | `refiners/PLAN_REFINER_{TRUTH,MYTH,FAIRY_TALE}.md` |

**Режимо-нейтральные** промпты (один файл на все режимы):
- `SAFETY_GATE.md`, `CONFIG_MATCH.md`
- `IDEA_SCORING.md`
- `PLAN_REVIEWER.md`

**Текстовая генерация** использует другую модель подмешивания: один общий `TEXT_BASE_PROMPT.md` + один из `truth_modes/{TRUTH|MYTH|FAIRY_TALE}.md` + стиль текста.

Маппинг значения режима → суффикс файла реализован в `PromptBuilder._map_truth_mode_to_suffix`:
- `Правда` → `TRUTH`
- `Миф` → `MYTH`
- `Сказка` → `FAIRY_TALE`

---

## 6. Состояние сессии и состояние графа

### 6.1 `SessionState` — продуктовая модель

Хранится в `SessionState` (см. `src/models/schemas.py`). Это **источник правды** для логики оркестратора. Каждая нода читает и мутирует именно этот объект.

#### Ключевые поля для оркестрации

| Поле | Тип | Назначение |
|---|---|---|
| `current_node` | str | Информационный маркер текущего шага (см. §2.3) |
| `series_plan` | List[str] | Список названий тем |
| `full_plan_items` | List[dict] | Полный план с `theme` и `content` |
| `approved_plan_items` | dict | Чистовик одобренных тем по индексу |
| `approved_indices` | List[int] | Индексы тем, прошедших валидацию |
| `global_context` | str | Описание персонажа и мира серии |
| `ideas_pool` | List[Idea] | Пул идей до сэмплинга |
| `validation_cycles` | int | Счётчик REJECTED-циклов |
| `validator_feedback` | str (JSON) | Последний фидбек валидатора |
| `user_feedback` | Optional[str] | Комментарий пользователя для рефайна |
| `revision_history` | dict | История всех правок по темам |
| `stories` | List[StoryItem] | Готовые истории |
| `is_completed` | bool | Флаг завершения всей генерации |

### 6.2 `GraphState` — обёртка для LangGraph

Минимальный `TypedDict`, который ходит между нодами LangGraph:

```python
class GraphState(TypedDict, total=False):
    session: SessionState        # источник правды
    user_input: Optional[Any]    # значение от Command(resume=...)
```

`user_input` заполняется снаружи при возобновлении после interrupt и обнуляется нодой после прочтения. Никакой бизнес-логики в `GraphState` нет — это просто транспорт.

Преобразования:
- `to_graph_state(session)` — вход в граф,
- `from_graph_state(state)` — извлечение сессии после завершения.

### 6.3 `PipelineResult` — результат `run_pipeline`

```python
@dataclass
class PipelineResult:
    session: SessionState
    interrupt: Optional[dict] = None

    is_done: bool          # interrupt is None — граф завершился
    is_waiting_user: bool  # interrupt is not None — ждём ввода
    interrupt_type: Optional[str]  # 'config_arbitration' | 'plan_arbitration' | 'user_confirmation'
```

CLI крутит цикл `run_pipeline → handler → run_pipeline` до тех пор, пока `is_done == True`.

### 6.4 Персистентность: два слоя

| Слой | Что хранит | Технология |
|---|---|---|
| In-process | Состояние LangGraph между interrupt и resume в рамках одного процесса | `MemorySaver` (checkpointer) |
| Долгосрочный | `SessionState` целиком, после каждого шага | `JSONStorage` → диск |

**Источник правды между запусками — JSONStorage.** Каждая нода сама сохраняет сессию через `storage.save_session(session)` после своих изменений. При вызове `run_pipeline` оркестратор предпочитает читать сессию из JSONStorage, а не из финального state графа — это надёжнее на случай прерывания.

`MemorySaver` нужен только для механики interrupt/resume в рамках одного процесса. Восстановление сессии между процессами (`--session <id>`) работает за счёт того, что каждая нода читает `session.current_node` и LangGraph переходит на нужное место графа.

### 6.5 Observability

Корневой span каждого запуска `run_pipeline` создаётся через `start_root_span("orchestrator.run_pipeline")`. Все ноды графа помечены `@observe(name=...)` и автоматически попадают в один Langfuse trace благодаря OpenTelemetry-контексту. На корневой span навешиваются:
- `session_id`, `user_id`, теги (`truth_mode`, `work_mode`, `image_style`),
- input (topic, resume-флаг),
- финальный output (`current_node`, `is_completed`, `validation_cycles`, `waiting_user`).

---

## 7. Конфигурация и константы

Все поведенческие значения оркестратора должны задаваться через `settings.py` или `constants.py`, а не локальными литералами в методах.

Базовый набор констант для оркестратора:

| Константа | Назначение |
|---|---|
| `IDEA_POOL_SIZE` | Размер пула идей, который просит `Series Planner` |
| `MIN_CHILD_INDEX` | Минимальный `child_index` для прохождения фильтра |
| `DEFAULT_IDEA_CHILD_INDEX` | Скор по умолчанию при ошибке скоринга |
| `FALLBACK_IDEA_CHILD_INDEX` | Скор fallback-идеи, если весь пул отсеян |
| `SCORE_NORMALIZATION_EPSILON` | Смещение для линейной нормализации весов |
| `USER_ARBITRATION_THRESHOLD` | Порог REJECTED-циклов до подключения пользователя |
| `MAX_VALIDATION_RETRIES` | Абсолютный лимит циклов, защита от петли |
| `DEBUG_CONTENT_PREVIEW_CHARS` | Длина превью контента в отладочном выводе |

Подробная инвентаризация магических значений по коду, промптам и провайдерам находится в `docs/02_ENGINEERING/CONFIGURATION_CONSTANTS.md`.

---

## 8. Технический долг и точки расширения

### Известный технический долг

1. **Парсинг JSON через копипасту.** Частично вынесен в `parse_llm_json`, но местами ещё встречается `response_raw.replace("```json", "").replace("```", "").strip()`. Доводим до единого хелпера.
2. **Изменяемые дефолты в Pydantic-моделях** (`dict = {}`, `List[dict] = []`). Не критично в pydantic v2, но архитектурно неаккуратно.
3. **`StoryItem.retry_count`** оставлен в схеме, но больше не используется как раньше (заменён на `validation_cycles` уровня сессии).
4. **`current_node` как строка.** Поле осталось от старой стейтмашины, сейчас выполняет роль информационного маркера прогресса. Стоит формализовать множество допустимых значений (например, `Literal` или enum), чтобы не плодить «магические» строки.
5. **Дублирование логики "если failed — иди в END"** в нескольких routing-функциях. Можно вынести в общий хелпер.

### Запланированные расширения

1. **Валидация и редактура текстов** (после генерации, перед согласованием с пользователем). Будет использовать тот же паттерн `validator → reviewer → refiner`, что и для плана, и добавится как поднабор нод между `text_generation` и `user_confirmation`. Потребует новых промптов: `TEXT_VALIDATOR_*.md`, `TEXT_REFINER_*.md`. Логика арбитража и счётчик переиспользуются.
2. **Асинхронная генерация картинок.** `asyncio.gather` для пакетной отрисовки. Делается после стабилизации текущей логики.
3. **JSON-база знаний** для подмешивания фактов о популярных темах (лягушки, ёжики, белки и т.п.) в промпты валидатора и редактора. Альтернатива классическому RAG для предсказуемой предметной области.
4. **Видео-провайдер** рядом с image-провайдером.
5. **Загрузка фото ребёнка** как референса персонажа. Большая отдельная фича с юридическими и техническими нюансами.
6. **Долгосрочный checkpointer.** Сейчас `MemorySaver` живёт в рамках процесса — между запусками `--session <id>` сессия восстанавливается из `JSONStorage`. Для более точной паузы внутри сложных interrupt-сценариев между процессами можно подключить персистентный checkpointer (SQLite/Postgres).  

---

## 9. Соглашения и инварианты

Список инвариантов, которые должны соблюдаться в любой момент:

1. **`approved_indices` ⊆ ключи `approved_plan_items`** — если индекс одобрен, для него есть данные в чистовике.
2. **`validation_cycles >= 0`** всегда. Сброс в 0 — только при `plan_approved` или форсированном одобрении в арбитраже.
3. **`validation_cycles <= MAX_VALIDATION_RETRIES`** иначе сессия идёт в `failed`.
4. **`session.user_feedback` обнуляется** после использования (в конце цикла рефайна).
5. **`current_node == "failed"`** — терминальное состояние, граф уходит в `END`, переходов из него нет.
6. **`session.is_completed == True`** — флаг ставится только после успешной генерации картинок.
7. **`session.full_plan_items[i]` всегда актуален** для всех `i in range(len(series_plan))`.
8. **`GraphState["user_input"]` обнуляется** нодой после прочтения, чтобы не «протекал» в следующие итерации.


## 11. Целевое представление пайплайна

Раздел описывает **планируемую эволюцию графа** в сторону продуктового видения, изложенного в `PRODUCT_VISION.md`. Здесь — только техническая сторона: какие ноды добавляются, как меняются существующие, как организована файловая иерархия промптов.

Продуктовый смысл изменений (зачем нужны режим полезности, подстили, персонажи) — см. `PRODUCT_VISION.md`.

### 11.1 Новые ноды-обогатители

Между **Idea Sampler** и **Plan Validator** (или параллельно с Series Planner — финальное место определяется при разработке) появляется блок нод, обогащающих контекст генерации деталями из запроса пользователя.

| Нода | Тип | Назначение |
|---|---|---|
| `NODE_STYLE_DETECTOR` | 🤖 LLM | Анализирует `topic` пользователя, выделяет упоминания подстилей («русско-народная», «Чуковский», «мифы Греции») |
| `NODE_CHARACTER_DETECTOR` | 🤖 LLM | Анализирует `topic`, выделяет упоминания персонажей и значимых деталей (блоха, зима, приключения) |
| `NODE_PROMPT_ENRICHER` | ⚙️ Детерминированный | Берёт результаты детекторов, ищет совпадения в базе знаний (см. §11.3), подмешивает найденные слои к базовому промпту |

**Принцип работы:**
- Детекторы заполняют новые поля в `SessionState`: `detected_substyle`, `detected_characters`, `detected_details`.
- Енричер на основе этих полей собирает финальный промпт.
- Если совпадений в базе нет — енричер сохраняет упоминание детали в контексте, но подмешивает только базовый слой.

**Принцип «мягкой деградации**: ни одна из этих нод не может перевести сессию в `failed`. Их отсутствие или ошибка означает, что генерация проходит на базовых промптах.

### 11.2 Расширение арбитража конфигурации

Сейчас нода `config_arbitration` срабатывает только при несоответствии `truth_mode` и темы.

**Целевое поведение:** срабатывает при несоответствии **любого** из четырёх измерений настроек контексту запроса:

- `truth_mode` (как сейчас)
- `utility_mode` (новое измерение, см. §11.4)
- `text_style` / подстиль (новое)
- возрастная градация (новое, см. §11.5)

**Структура payload interrupt** расширяется:

```python
{
    "type": "config_arbitration",
    "mismatches": [
        {"setting": "truth_mode", "current": "Правда", "suggested": "Сказка", "reason": "..."},
        {"setting": "substyle", "current": None, "suggested": "Чуковский", "reason": "..."},
        # ...
    ]
}
```

**Resume value** также расширяется — пользователь может частично принять предложения (например, поменять только `truth_mode`, но оставить остальное).

### 11.3 База знаний промптов (файловая иерархия)

База знаний — **обычная файловая структура**. Никаких векторных БД на старте, никакого RAG. Это даёт:
- Предсказуемость (что положили — то и нашлось).
- Прозрачность для отладки.
- Простоту добавления нового контента — просто положить файл в нужную папку.

**Планируемая структура:**

```
docs/03_PROMPTS/
├── text/
│   ├── styles/
│   │   ├── TRUTH/
│   │   │   ├── BASE.md
│   │   │   ├── ENCYCLOPEDIC.md
│   │   │   ├── NATURALISTIC.md
│   │   │   └── ...
│   │   ├── MYTH/
│   │   │   ├── BASE.md
│   │   │   ├── GREEK.md
│   │   │   ├── ROMAN.md
│   │   │   └── ...
│   │   └── FAIRY_TALE/
│   │       ├── BASE.md
│   │       ├── RUSSIAN_FOLK.md
│   │       ├── SCANDINAVIAN.md
│   │       ├── CHUKOVSKY.md
│   │       └── ...
│   │
│   ├── characters/
│   │   ├── TRUTH/
│   │   │   ├── animals/{FOX, HEDGEHOG, FROG, ...}.md
│   │   │   └── humans/...
│   │   ├── MYTH/
│   │   │   ├── gods/{ZEUS, ATHENA, ...}.md
│   │   │   └── heroes/{HERCULES, ...}.md
│   │   └── FAIRY_TALE/
│   │       ├── russian_folk/{KOLOBOK, IVAN, ...}.md
│   │       ├── chukovsky/{MUKHA_TSOKOTUKHA, BARMALEY, ...}.md
│   │       └── ...
│   │
│   ├── utility/
│   │   ├── TEACHING/{POTTY, ROAD, CLEANING, ...}.md
│   │   ├── NARRATIVE/BASE.md
│   │   └── ENGLISH/{LEVEL_1, LEVEL_2, ...}.md
│   │
│   └── ages/
│       ├── AGE_3.md
│       ├── AGE_3_5.md
│       ├── AGE_4.md
│       ├── AGE_4_5.md
│       └── AGE_5.md
│
└── image/  (как сейчас)
```

**Логика поиска (упрощённо):**

```python
def find_substyle(truth_mode: str, detected_substyle: str | None) -> str:
    base_path = f"text/styles/{truth_mode}/BASE.md"
    if detected_substyle is None:
        return load(base_path)
    
    candidate = f"text/styles/{truth_mode}/{detected_substyle}.md"
    if exists(candidate):
        return load(base_path) + load(candidate)
    
    # Mатчер: ищет ближайшее по семантике (можно через LLM, можно через простое сравнение строк на старте)
    nearest = find_nearest(truth_mode, detected_substyle)
    if nearest:
        return load(base_path) + load(nearest)
    
    return load(base_path)  # мягкая деградация
```

**В будущем**, если иерархия разрастётся, поиск может переехать на векторное хранилище (FAISS/Chroma) — но интерфейс `find_*` останется тем же.

### 11.4 Новое измерение настроек: `utility_mode`

В `GenerationRequest` добавляется обязательное поле `utility_mode: UtilityMode`:

```python
class UtilityMode(str, Enum):
    TEACHING = "Поучительный"
    NARRATIVE = "Повествовательный"
    ENGLISH = "Английский"
```

**Влияние на пайплайн:**

- **Series Planner** учитывает `utility_mode` при генерации идей:
  - `TEACHING` → идеи строятся вокруг полезного навыка.
  - `NARRATIVE` → идеи свободные, без цели «научить».
  - `ENGLISH` → идеи привязаны к словарным темам (animals, family, colors).
- **Plan Validator** получает соответствующий профиль валидации.
- **Text Generation** подмешивает слой `utility/{MODE}/*.md`.

Маппинг режим → промпт-файл аналогичен текущему `_map_truth_mode_to_suffix` в `PromptBuilder`.

**Режим `ENGLISH` требует доп. проработки** — возможно потребует отдельной ветки графа (свои промпты, своя валидация, возможно своя градация уровней вместо возрастной).

### 11.5 Возрастные градации

В `GenerationRequest` добавляется обязательное поле `age: AgeLevel`:

```python
class AgeLevel(str, Enum):
    AGE_3 = "3"
    AGE_3_5 = "3.5"
    AGE_4 = "4"
    AGE_4_5 = "4.5"
    AGE_5 = "5"
```

**Влияние на пайплайн:**

- В **Text Generation** подмешивается слой `ages/AGE_{X}.md` — он влияет на длину фраз, словарь, сложность сюжета.
- **Idea Scoring**: возрастной фильтр становится точнее. То, что подходит для 3 лет, может быть слишком простым для 5, и наоборот. `MIN_CHILD_INDEX` может стать функцией от возраста.

### 11.6 Обновлённый поток (с учётом новых нод)

Принципиальная схема пайплайна после внедрения целевого представления:

```
Тема + Конфигурация (4 измерения + возраст)
        │
        ▼
[1] Safety Gate
        │
        ▼
[2] Config Match  ──mismatch──▶ [Config Arbitration (расширенный)]
        │                              │
        ▼                              │
[2.5] Style Detector       ◀───────────┘
        │
        ▼
[2.6] Character Detector
        │
        ▼
[3] Series Planner (truth + utility + style)
        │
        ▼
[4] Idea Scoring (с учётом возраста)
        │
        ▼
[5] Score Normalize
        │
        ▼
[6] Idea Sampler
        │
        ▼
[6.5] Prompt Enricher (подмешивает подстили, персонажей, детали)
        │
        ▼
[7..12] далее как сейчас
```

> 💡 Точное место Style/Character Detector (до Series Planner или после Idea Sampler) определяется на этапе разработки. Возможно, детектирование происходит **один раз сразу после Safety Gate**, а результаты используются всеми последующими нодами через поля `SessionState`.

### 11.7 Влияние на `SessionState`

Новые поля, которые потребуется добавить:

| Поле | Тип | Назначение |
|---|---|---|
| `detected_substyle` | Optional[str] | Что детектор стиля выделил из запроса |
| `detected_characters` | List[str] | Персонажи, выделенные из запроса |
| `detected_details` | List[str] | Прочие значимые детали (сезон, жанр, мотив) |
| `enriched_prompt_layers` | dict | Какие конкретно файлы из базы знаний были подмешаны (для отладки и Langfuse) |

Возрастная градация и `utility_mode` живут в `GenerationRequest`, как и текущие настройки.

### 11.8 Расширяемость и обратная совместимость

**Принципы расширения:**

1. **Новые подстили / персонажи / темы — без изменений кода.** Достаточно положить новый `.md` файл в соответствующую папку.
2. **Новые измерения настроек — через расширение `GenerationRequest` и `config_arbitration`.** Код графа меняется минимально.
3. **Старые сессии должны грузиться.** При добавлении новых полей в `SessionState` они должны иметь дефолты (Pydantic), чтобы JSON-сессии, созданные до изменений, не ломали загрузку.

### 11.9 Технический план перехода

Эволюция к целевому представлению — **итеративная**, не одним коммитом. Приоритеты:

1. **`utility_mode` как третье обязательное измерение.** Минимальное изменение — расширить `GenerationRequest`, добавить три новых базовых промпта, прокинуть через PromptBuilder.
2. **Возрастные градации.** Аналогично — расширение `GenerationRequest` и добавление пяти возрастных промптов.
3. **Style Detector + Prompt Enricher для подстилей.** Сначала на одном-двух подстилях (например, «русско-народная» и «Чуковский»).
4. **Character Detector + расширение базы знаний персонажами.**
5. **Расширение `config_arbitration` на все измерения.**
6. **Режим `ENGLISH`** — отдельной фазой, требует продуктовой проработки.

Каждый шаг можно выкатывать независимо. Граф LangGraph остаётся обратно совместимым: новые ноды добавляются, старые не ломаются.
