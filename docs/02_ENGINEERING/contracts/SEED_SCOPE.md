# SEED_SCOPE.md

# Minimal Seed Prompt Scope

Статус: рабочий scope для первых прогонов.

Этот документ временно фиксирует минимальный набор prompt layers, достаточный для проверки lookup, composition и второго этапа генерации текстов. После появления реальных seed prompts документ может стать чеклистом покрытия.

---

## 1. Цель seed scope

Seed prompts нужны не для полного покрытия будущей базы знаний, а для проверки контракта:

* lookup умеет находить слои;
* fallback работает предсказуемо;
* composition собирает stage context;
* generator/scorer/validator/refiner получают достаточно информации;
* golden scenarios проходят без ручной подгонки под каждый запрос.

---

## 2. MVP-покрытие режимов

```text
truth_modes/
  TRUTH
  FAIRY_TALE
```

Для каждого режима нужен:

* `BASE.md`;
* минимум один базовый style layer;
* минимум один stage profile для text generation;
* минимум один validator/refiner layer или общий слой, применимый к режиму.

---

## 3. MVP-покрытие utility

```text
utility/
  NARRATIVE
  TEACHING
```

Для `TEACHING` нужны seed topics:

* `HAND_WASHING_AFTER_WALK`;
* `ROAD_SAFETY`;
* `STRANGERS_AND_CANDY`.

Тема `STRANGERS_AND_CANDY` должна быть отмечена как sensitive teaching topic: формулировки должны быть осторожными, без запугивания, с акцентом на обращение к знакомому взрослому.

---

## 4. MVP-покрытие возраста

```text
ages/
  3
  5
```

Различия:

* длина фраз;
* сложность причинно-следственных связей;
* допустимая абстрактность;
* формат вопросов после текста.

---

## 5. MVP-покрытие subjects

Минимальный набор:

```text
animals:
  HEDGEHOG
  FOX
  SQUIRREL
  PARROT

people/professions:
  DOCTOR
  CHILD

objects/safety:
  TRAFFIC_LIGHT
  ROAD
  SOAP
```

`PARROT` нужен как пример fallback для запроса “какаду”: точного слоя может не быть, но общий слой попугая есть.

---

## 6. MVP-покрытие named/custom character

Нужен хотя бы один сценарий, где пользователь задаёт персонажа не из базы:

```text
маленький бельчонок Тим
```

Ожидание:

* `subjects` фиксирует бельчонка;
* `is_character = true`;
* `character_profile` фиксирует имя и traits;
* lookup может использовать общий слой `SQUIRREL`;
* имя `Тим` и конкретные черты идут в `hard_details` / `character_profile`, а не требуют отдельного prompt layer.

---

## 7. Когда этот документ можно упростить

После создания реальных seed prompt files этот документ можно превратить в короткий чеклист покрытия или перенести его содержание в roadmap. Полностью удалять его до появления smoke/golden прогонов не стоит: он объясняет, зачем выбран именно такой минимальный набор.
