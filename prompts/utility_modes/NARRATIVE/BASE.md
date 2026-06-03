---
id: UTILITY_NARRATIVE_BASE
type: utility
role: utility_mode
namespace: utility_modes/NARRATIVE
name: История без явной обучающей цели
aliases:
  - просто историю
  - без поучения
  - на ночь
  - интересную историю
  - narrative
applies_to:
  content_formats: [story]
  truth_modes: [TRUTH, FAIRY_TALE, MYTH]
  utility_modes: [NARRATIVE]
  ages: ["3", "5"]
user_description: Режим для обычной интересной или спокойной истории без обязательного урока.
short_description: "Utility mode для narrative value: история должна быть цельной, интересной и age-safe без explicit teaching hard goal."
constraints:
  - Не добавлять явную мораль или учебную цель, если utility_mode = NARRATIVE.
  - Не удалять мягкий смысл истории, но не превращать его в поучение.
  - Style, truth mode, age и required subjects остаются приоритетными constraints.
---

# Назначение слоя

Используй этот слой, когда пользователь просит просто историю, рассказ на ночь или интересный сюжет без явного обучения.

`NARRATIVE` означает, что `utility_goal` не становится отдельным teaching hard gate.

# Что добавить в результат

Добавляй narrative value: понятное событие, мягкий интерес, маленький выбор, уютное завершение, эмоциональную цельность. История может чему-то мягко подводить, но не должна звучать как урок.

# Ограничения

Не вставляй назидательные выводы, прямые инструкции или список правил без запроса. Не подменяй story format советами.

`NARRATIVE` не отменяет `truth_mode`, age safety, hard details, required subjects, `character_profile` или style/substyle constraints.

# Как сочетать с другими слоями

Generator строит цельную историю без explicit teaching goal. Validator/refiner могут отмечать чрезмерное поучение как utility mismatch. Если есть soft preference вроде "на ночь", стиль можно сделать спокойнее, но не менять resolved layers.

# Примеры допустимого поведения

Допустимо: история о том, как ребёнок увидел следы на снегу и спокойно вернулся домой.

# Примеры недопустимого поведения

Недопустимо: заканчивать историю длинной моралью "поэтому каждый ребёнок обязан...".
