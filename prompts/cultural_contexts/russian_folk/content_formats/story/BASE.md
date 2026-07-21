---
id: CONTENT_FORMAT_STORY
type: format
role: content_format
namespace: content_formats/story
name: История / рассказ
aliases:
  - story
  - stories
  - рассказ
  - рассказы
  - история
  - истории
  - сказка
applies_to:
  content_formats: [story]
  truth_modes: [TRUTH, FAIRY_TALE]
  utility_modes: [NARRATIVE, TEACHING]
  ages: ["3", "5"]
user_description: Короткая детская история с вопросами после текста.
short_description: Формат результата для коротких child-facing историй с темой, текстом, вопросами и служебными полями candidate text.
constraints:
  - Формат истории не выбирает truth_mode, utility_mode, возраст, стиль или subjects.
  - Candidate text должен поддерживать поля theme, text, questions, used_subjects, utility_points и expected_visual_idea.
  - Вопросы после истории должны соответствовать выбранному возрастному слою.
---

# Назначение слоя

Используй этот слой, когда результат должен быть короткой детской историей или рассказом. Слой задаёт форму результата и базовые ожидания к candidate text, но не решает, будет ли мир правдивым, сказочным.

Alias `сказка` в этом слое означает только пользовательский намёк на story-like формат. Если truth mode отдельно не выбран как `FAIRY_TALE`, формат не должен добавлять фактическое волшебство.

# Что добавить в результат

Candidate text должен поддерживать поля `theme`, `text`, `questions`, `used_subjects`, `utility_points` и `expected_visual_idea`.

`theme` кратко называет смысл истории. `text` содержит саму историю. `questions` содержат простые вопросы по тексту или мягкие вопросы на понимание. `used_subjects` фиксирует использованные обязательные и значимые subjects. `utility_points` кратко показывает, какие narrative или teaching задачи были раскрыты. `expected_visual_idea` описывает текстовую идею возможного визуального мотива, не превращаясь в инструкцию image generation.

История должна иметь понятное начало, одно центральное действие или маленькую цепочку действий и спокойное завершение. Длину, словарь, причинность и сложность вопросов уточняет age layer.

# Ограничения

Не меняй immutable normalized fields: `content_format`, `truth_mode`, `utility_mode`, `target_age`, `subjects`, `main_subject`, `required_subjects`, `character_profile` и hard details.

Не добавляй Stage 3, image generation, animation, visual validation или micro-cartoon logic. `expected_visual_idea` остаётся коротким текстовым описанием, полезным downstream, но не командой генерации картинки.

Не используй форматный слой для выбора стиля, подстиля, темы обучения, truth mode или возраста. Если пользователь просит "сказку", но resolved truth mode остаётся `TRUTH`, это должна быть история в реалистичном мире.

# Как сочетать с другими слоями

Truth mode определяет правила мира: что может быть реальным, сказочным. Utility layer определяет, нужна ли просто narrative value или явная teaching goal. Age layer уточняет длину фраз, словарь, причинную сложность и вопросы. Language layers определяют язык user-facing и final result частей. Style, substyle и entity layers добавляют тон и предметные детали, но не меняют output fields.

Generator использует этот слой как output contract. Validator проверяет наличие и соответствие полей, возрастную уместность вопросов и отсутствие решений, которые должен был принимать другой слой. Refiner исправляет форму результата, не меняя locked параметры запроса.

# Примеры допустимого поведения

Допустимо: написать короткий рассказ с одним понятным событием, двумя простыми вопросами после текста и `expected_visual_idea` вроде "ребёнок смотрит на ёжика у кустов".

Допустимо: сохранить мягкую сказочную интонацию в словах, если truth mode это разрешает или если это не превращает реалистичный мир в волшебный факт.

# Примеры недопустимого поведения

Недопустимо: из-за слова "сказка" автоматически добавить говорящих животных при `truth_mode = TRUTH`.

Недопустимо: заменить story output на список советов, image prompt, сценарий анимации или Stage 3 instructions.

Недопустимо: сделать вопросы слишком сложными для выбранного возраста или не связанными с `text`.
