# GOLDEN_SCENARIOS.md

# Golden Scenarios

Статус: рабочий список smoke/regression сценариев.

Golden scenarios не фиксируют точный финальный текст. Их задача — проверять нормализацию параметров, prompt lookup, fallback, composition, subject continuity, hard gates и validation behavior.

Со временем этот документ должен стать основой smoke/regression suite.

---

## 1. Формат сценария

```markdown
## GS-001. Правдивые истории про ёжика

Input:
Сделай 5 коротких натуралистичных историй про ёжика зимой в лесу для ребёнка 3 лет.

Expected normalized params:
- content_format = story
- truth_mode = TRUTH
- utility_mode = NARRATIVE
- target_age = 3
- output_count = 5
- main_subject = ёжик
- subjects includes HEDGEHOG
- setting.season = зима

Expected prompt lookup:
- CONTENT_FORMAT_STORY
- TRUTH_BASE
- AGE_3
- TRUTH_ANIMAL_HEDGEHOG
- NATURALISTIC or base factual style

Acceptance:
- no clarification required
- candidate texts do not repeat the same theme
- approved texts keep ёжик as main subject
- no fairy-tale behavior in TRUTH mode
```

---

## 2. Базовые сценарии

1. Правдивые истории про ёжика зимой для 3 лет.
2. Сказочные истории про лису для 5 лет.
3. Формулировка про миф в `raw_text` не переопределяет controlled `truth_mode`; MYTH layer не выбирается.
4. Поучительная правдивая история про мытьё рук после прогулки.
5. Поучительная сказка про переход через дорогу.
6. Поучительная история про незнакомца и конфету.
7. Запрос “попугай какаду” с fallback `PARROT` и unresolved detail `какаду`.
8. Запрос “лиса, заяц и белка зимой” с явной `subject_continuity_policy`.
9. Запрос “маленький бельчонок Тим” с `is_character = true` и `character_profile`.

---

## 3. Провокационные сценарии

Эти сценарии нужны, чтобы ловить поломки логики и слишком смелые fallback-решения.

1. Неподдерживаемый стиль как мягкое пожелание.
2. Неподдерживаемый стиль как жёсткое требование.
3. Противоречие `TRUTH` + фантастическая деталь.
4. Пустой или бессмысленный ввод.
5. Meta-запрос “расскажи о себе”.
6. Несколько subjects, один из которых пропадает во втором этапе.
7. Refiner меняет тему кандидата.
8. Refiner меняет `character_profile`.
9. Teaching topic про незнакомцев становится пугающим.
10. `TRUTH`-история превращает животное в говорящего героя.

---

## 4. Что проверять

Для каждого сценария желательно фиксировать:

* input;
* expected classification;
* expected normalized params;
* expected prompt lookup;
* expected clarification behavior;
* expected subject continuity;
* expected hard gates;
* expected validation behavior.

Точный текст результата фиксировать не нужно, если специально не создаётся snapshot-тест для конкретной версии prompt-базы.
