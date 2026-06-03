---
id: LANGUAGE_RU_RESULT
type: language
role: result_language
namespace: languages/ru/result
name: Русский язык результата
aliases:
  - русский
  - на русском
  - ru
  - Russian
applies_to:
  content_formats: [story]
  truth_modes: [TRUTH, FAIRY_TALE, MYTH]
  utility_modes: [NARRATIVE, TEACHING]
  ages: ["3", "5"]
user_description: Финальный результат истории и вопросов должен быть на русском языке.
short_description: Result language слой для русского final generated text: story text, questions and child-facing result fields.
constraints:
  - Final `text` и `questions` должны быть на русском.
  - Не добавлять случайный английский в child-facing result.
  - Result language не меняет audience_language, truth_mode, utility_mode, content_format, subjects или age.
---

# Назначение слоя

Используй этот слой, когда final generated result должен быть на русском языке. Слой управляет языком полей результата, особенно `text` и `questions`.

# Что добавить в результат

Пиши финальную историю (`text`) и вопросы (`questions`) на русском. Русский должен быть естественным, детским по тону и согласованным с age layer.

Если contract field names отображаются или упоминаются как технические имена, они остаются на английском. Содержимое child-facing полей должно быть русским.

# Ограничения

Не добавляй случайные английские слова, вопросы или объяснения в child-facing result, если будущий explicit scope не разрешает bilingual или English output.

Не меняй `audience_language`: пользовательские формулировки контролирует отдельный слой `LANGUAGE_RU_AUDIENCE`. Не меняй truth mode, utility mode, age, style, subjects, hard details или output structure.

# Как сочетать с другими слоями

Content format определяет, какие поля должны быть в candidate text. Truth, utility, age, style и entity layers определяют смысл и сложность. Этот слой применяет русский язык к final generated text.

Generator пишет `text` и `questions` по-русски. Validator проверяет, что child-facing content не содержит случайного английского и не противоречит age language. Refiner переводит случайные английские фразы на русский, не меняя immutable fields и смысл.

# Примеры допустимого поведения

Допустимо: `questions` содержит "Что герой сделал после прогулки?".

Допустимо: техническое имя поля `expected_visual_idea` остаётся английским, а его значение написано по-русски.

# Примеры недопустимого поведения

Недопустимо: финальный вопрос "Why did the fox stop?" без явного bilingual scope.

Недопустимо: менять resolved result language из-за style или user-facing phrasing.

Недопустимо: использовать русский результат как повод изменить truth mode или teaching goal.
