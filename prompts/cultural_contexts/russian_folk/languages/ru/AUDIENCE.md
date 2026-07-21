---
id: LANGUAGE_RU_AUDIENCE
type: language
role: audience_language
namespace: languages/ru/audience
name: Русский язык аудитории
aliases:
  - русский
  - на русском
  - ru
  - Russian
applies_to:
  content_formats: [story]
  truth_modes: [TRUTH, FAIRY_TALE]
  utility_modes: [NARRATIVE, TEACHING]
  ages: ["3", "5"]
user_description: Русские user-facing формулировки для объяснений, preview и child-facing framing.
short_description: Audience language слой для русских пользовательских и детских формулировок в prompt context.
constraints:
  - User-facing wording должно быть на русском, если нет будущего явного scope для другого языка.
  - Формулировки для ребёнка должны учитывать age layer и не смешивать случайный английский.
  - Audience language не меняет result_language, truth_mode, utility_mode или content_format.
---

# Назначение слоя

Используй этот слой, когда аудитория и пользовательские формулировки должны быть русскими. Слой управляет тем, как система формулирует объяснения, preview, уточнения и child-facing framing в prompt context.

# Что добавить в результат

Используй естественный русский язык для user-facing и child-facing формулировок. Если текст обращён к ребёнку или описывает будущий результат для ребёнка, учитывай выбранный age layer: для 3 лет проще и мягче, для 5 лет чуть богаче и яснее.

Термины stage/output fields, если они упоминаются как contract names, сохраняй на английском: `theme`, `text`, `questions`, `used_subjects`, `utility_points`, `expected_visual_idea`.

# Ограничения

Не добавляй случайный английский в формулировки для ребёнка. Не смешивай языки без явного будущего scope или hard detail.

Не меняй `result_language`: если final result тоже русский, это фиксирует отдельный слой `LANGUAGE_RU_RESULT`. Не меняй truth mode, utility mode, age, subjects или output contract.

# Как сочетать с другими слоями

Composition должна сохранять различимость `audience_language` и `result_language`, даже если оба слоя про русский. Age layer уточняет простоту обращений. Utility и truth mode определяют смысл, а этот слой только делает русскую подачу понятной и согласованной.

Generator использует этот слой для русской framing-подачи, если она попадает в prompt context. Validator и refiner проверяют отсутствие случайного английского в child-facing частях и соответствие возрастному тону.

# Примеры допустимого поведения

Допустимо: "Коротко объясни ребёнку, что герой сделал после прогулки".

Допустимо: сохранить `questions` как имя поля, но сами вопросы писать по-русски, если это final child-facing content.

# Примеры недопустимого поведения

Недопустимо: случайно вставлять "What did the hero do?" в детские вопросы.

Недопустимо: использовать audience language слой как основание для изменения truth mode или content format.

Недопустимо: склеивать audience/result roles так, что trace перестаёт показывать оба языковых решения.
