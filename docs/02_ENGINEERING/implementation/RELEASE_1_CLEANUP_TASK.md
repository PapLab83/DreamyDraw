# Release 1 Cleanup Task

Status: approved with lead notes; execute in phases.
Audience: developer taking over Release 1 cleanup.

## Контекст продукта

DreamyDraw — генератор детского познавательно-развлекательного контента. Продуктовая идея: по короткому запросу взрослого создавать понятные, интересные и безопасные материалы для детей, сначала в формате коротких текстовых историй, а в дальнейшем — с иллюстрациями и более сложными сценариями.

Release 1 ограничен Stage 1-2 text-only MVP: система интерпретирует пользовательский запрос, собирает prompt layers, генерирует и проверяет текстовые варианты, а затем возвращает результат в `approved_texts`.

В этом релизе важно не расширять продукт, а закрыть текущий MVP как стабильную и понятную основу для следующих релизов.

## Обращение к разработчику

Привет!

Задача Release 1 — **не развивать prompt-архитектуру и не начинать новые продуктовые улучшения**, а аккуратно закрыть текущий Stage 1-2 text-only MVP как понятный, чистый и передаваемый релиз.

MVP уже доведен до рабочего состояния: CLI запускается, `mock` остается default executor, `llm` executor подключается опционально, Stage 1-2 доводят результат до `approved_texts`. Теперь нужно убрать шум вокруг реализации: синхронизировать документацию, удалить legacy/устаревшие артефакты, явно зафиксировать границы релиза и прогнать финальные проверки после чистки.

## Контекст проекта

DreamyDraw сейчас имеет два контура:

| Контур | Статус |
|--------|--------|
| Stage 1-2 MVP | Целевой контур релиза: text-only CLI до `approved_texts` |
| Legacy pipeline | Deprecated; использовать только для audit/cleanup, не как образец |

Фактический scope Release 1:

- Stage 1-2 text-only CLI;
- `mock` executor по умолчанию;
- `llm` executor только по явному флагу;
- автоматические тесты не ходят к реальному LLM provider;
- image generation, animation, Stage 3 и интерактивный CLI не входят в релиз.

## Главная цель

Подготовить Release 1 к передаче и приемке:

```text
актуальные docs + чистый repo + явно зафиксированные ограничения + green regression
```

## Фазы Работы

1. **Inventory и dependency audit.** Зафиксировать списки документов и проверить legacy imports/tests перед удалением.
2. **Doc sync + Release 2 backlog.** Синхронизировать актуальные Release 1 docs и создать `RELEASE_2_BACKLOG.md`.
3. **Legacy cleanup.** Удалять legacy code/docs/tests только после dependency audit.
4. **Regression/smoke.** Прогнать focused checks, full pytest и default CLI smoke.

Legacy code deletion is allowed only after dependency audit. Be especially careful with `providers/*`, `src/core/factory.py`, `src/utils/cli_parser.py`, `src/models/schemas.py` and shared test fixtures.

## Что читать перед работой

Обязательно:

- `docs/02_ENGINEERING/implementation/STAGE_1_2_MVP_RUNBOOK.md`
- `docs/02_ENGINEERING/implementation/STAGE_1_2_MVP_ACCEPTANCE_CHECKLIST.md`
- `docs/02_ENGINEERING/implementation/WAVE_11_FINAL.md`
- `docs/02_ENGINEERING/implementation/WAVE_11_FOLLOW_UP_DEVELOPMENT_TASKS.md`
- `docs/02_ENGINEERING/implementation/MVP_FOLLOW_UP_MASTER_PLAN.md`
- `docs/02_ENGINEERING/implementation/RELEASE_2_BACKLOG.md`
- `docs/02_ENGINEERING/implementation/WAVE_0_LEGACY_POLICY.md`

По коду:

- `scripts/run_stage1_2_mvp.py`
- `src/core/stage1_2_orchestrator.py`
- `src/core/nodes/stage1.py`
- `src/core/nodes/stage2.py`
- `src/core/stage2_llm_executor.py`
- `src/core/prompts/`
- `tests/integration/test_stage1_2_*.py`

## Задачи Release 1

### 1. Подчистить и синхронизировать документацию

Нужно привести документы к фактическому состоянию Release 1.

Зафиксировать в документации:

- Stage 1-2 text-only MVP является целевым контуром;
- `mock` executor — default;
- `llm` executor — опциональный ручной/конфигурируемый режим;
- автоматические тесты не должны вызывать реального провайдера;
- image/animation/Stage 3 не входят в релиз;
- prompt-архитектура, semantic resolver и качество стилей переносятся в Release 2.

Убрать или пометить как устаревшие противоречивые `done/planned` хвосты, если они сбивают разработчика с текущего scope.

### 2. Удалить legacy-код, компоненты и prompt-файлы

Удалять только то, что точно:

- не используется Stage 1-2 MVP;
- не является нужной основой для Release 2;
- уже описано как deprecated/legacy;
- не требуется текущими тестами.

Если есть сомнение, не удалять молча: зафиксировать как candidate for cleanup и вынести на lead review.

### 3. Зафиксировать ограничения Release 1 и перенос задач в Release 2

Release 1 не должен превращаться в работу над качеством prompt-графа.

Нужно явно записать, что в Release 1 не делаем:

- не перепроектируем animal prompts;
- не выравниваем других животных под текущую лису;
- не делаем лису эталоном будущей prompt-структуры;
- не выносим русско-народный стиль в отдельный component;
- не начинаем полноценный semantic resolver;
- не проводим глубокую диагностику итогового prompt, если ее результат нельзя использовать в Release 1;
- не меняем продуктовую логику возрастной адаптации и познавательных направлений.

Эти темы должны быть оформлены как вход в Release 2.

### 4. Провести финальную smoke/regression-проверку после чистки

После удаления legacy и doc sync нужно подтвердить, что текущий MVP не сломан.

Минимальный набор проверок:

```bash
venv/bin/pytest tests/unit/test_stage2_llm_executor.py tests/integration/test_stage1_2_llm_executor_cli.py -q
venv/bin/pytest tests/integration/test_stage1_2_mvp_smoke.py tests/integration/test_stage1_2_cli.py -q
venv/bin/pytest tests/integration/test_stage1_2_golden_scenarios.py tests/integration/test_stage1_2_negative_scenarios.py -q
venv/bin/pytest -q
```

CLI smoke:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай 2 сказки про лису для 5 лет." --count 2
```

LLM smoke можно выполнять только вручную и только при наличии `.env`/provider config:

```bash
venv/bin/python scripts/run_stage1_2_mvp.py "Сделай 2 сказки про лису для 5 лет." --count 2 --executor llm
```

## Non-goals

В Release 1 запрещено расширять задачу до:

- semantic resolver;
- нового алгоритма parameter extraction;
- RapidFuzz/LLM-tail унификации для всех параметров;
- переписывания animal prompts;
- выноса русско-народного style/substyle layer;
- настройки Chukovsky style quality;
- новой схемы `base content generation -> child adaptation`;
- добавления новых животных, объектов, субстилей;
- сюжетного банка, randomizer, seeded diversity;
- image/animation/Stage 3.

## Ожидаемый результат

К концу Release 1 должно быть:

- документация совпадает с фактическим состоянием Stage 1-2 MVP;
- legacy/устаревшие файлы удалены или явно помечены как deferred cleanup;
- границы Release 1 и переносы в Release 2 зафиксированы;
- автоматические тесты проходят без реального LLM provider;
- CLI smoke в default `mock` режиме работает;
- ручной `llm` smoke, если выполнялся, описан отдельно с session id и результатом;
- нет изменений, которые начинают новую prompt-архитектуру в рамках Release 1.

## Acceptance criteria

- [ ] Scope Release 1 явно записан в актуальных docs.
- [ ] Release 2 items отделены от Release 1 cleanup.
- [ ] Legacy cleanup выполнен только по согласованному списку.
- [ ] Не изменялась структура animal prompts ради выравнивания под текущую лису.
- [ ] Не добавлялись image/animation/Stage 3 paths.
- [ ] Automated tests не вызывают реального LLM provider.
- [ ] Финальный `venv/bin/pytest -q` green или все failures объяснены.
- [ ] Default CLI smoke возвращает рабочий Stage 1-2 результат.

## Release 2 handoff

Темы, которые не нужно чинить в Release 1, но нужно передать в Release 2:

1. Стандартизировать получение параметров: rules/regex, aliases, normalization, RapidFuzz, narrow LLM tail, clarification.
2. Описать и реализовать полноценный semantic resolver.
3. Посмотреть итоговый prompt, который реально приходит LLM.
4. Пересобрать prompt-компоненты: animal отдельно, style/substyle отдельно.
5. На примере лисы убрать русско-народную специфику из animal component и вынести ее в отдельный style/substyle component.
6. Упростить generation prompt, если диагностика покажет перегруз.
7. Исследовать схему: базовый содержательно точный материал -> детская адаптация -> scorer/validator/post-check.
8. Приоритизировать познавательные направления: животные, городская инфраструктура, энергетика, водоснабжение, история Земли.
9. Настроить Stage 2 quality: temperature, models, validator strictness, scorer, truth/fairy enforcement, length/safety.
10. Расширить стили, объекты и разнообразие через substyles, randomizer, plot bank/seeded subset.
