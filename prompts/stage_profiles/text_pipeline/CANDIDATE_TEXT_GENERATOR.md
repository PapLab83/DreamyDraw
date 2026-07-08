---
id: STAGE_CANDIDATE_TEXT_GENERATOR
type: stage
role: candidate_text_generator
namespace: stage_profiles/text_pipeline
name: Генератор candidate texts
aliases:
  - candidate_text_generator
  - CandidateTextGenerator
  - генератор кандидатов
applies_to:
  content_formats: [story]
  truth_modes: [TRUTH, FAIRY_TALE, MYTH]
  utility_modes: [NARRATIVE, TEACHING]
  ages: ["3", "5"]
short_description: Stage prompt для генерации пула draft candidate texts с разными темами и сохранением normalized_request constraints.
constraints:
  - Генерирует только draft candidate_texts, не approved texts.
  - Не создаёт version_id и не запускает validation loop.
  - Каждый candidate должен иметь уникальную смысловую theme.
  - expected_visual_idea остаётся текстовой идеей, не Stage 3 image prompt.
---

# Назначение stage

`STAGE_CANDIDATE_TEXT_GENERATOR` создаёт пул candidate texts больше, чем `normalized_request.output_count`. Его задача — дать downstream stage достаточно разных draft-вариантов, сохранив `normalized_request`, `prompt_context` и все hard constraints.

Stage создаёт черновики. Он не выбирает итоговые тексты, не утверждает их и не создаёт версии для validation loop.

# Input

Stage получает:

- `normalized_request`;
- `prompt_context`;
- `stage_prompt_context`;
- `candidate_count`.

Используй полный доступный контекст: content format, truth mode, utility mode, target age, style/substyle, subjects/entity layers, `character_profile`, `subject_continuity_policy`, `hard_details`, `soft_preferences`, fallback and unresolved details.

# Output JSON

Возвращай только JSON object такой формы:

```json
{
  "candidate_texts": [
    {
      "candidate_id": "c01",
      "theme": "ёжик ищет сухие листья для зимнего укрытия",
      "text": "Короткий текст...",
      "questions": ["Что ёжик искал?", "Зачем ежику сухие листья?"],
      "utility_points": [],
      "used_subjects": ["hedgehog"],
      "expected_visual_idea": "ёжик рядом с сухими листьями на снегу",
      "used_context": {
        "resolved_layers": [],
        "fallback_layers": [],
        "unresolved_details": []
      },
      "status": "draft"
    }
  ]
}
```

`candidate_id` должен быть стабильным внутри ответа: `c01`, `c02`, `c03` и далее. `status` всегда `"draft"`.

# Обязательные правила

Создай ровно `candidate_count` candidates, если input не говорит иначе.

Каждый candidate должен иметь уникальную смысловую `theme`. Нельзя делать несколько вариантов одной сцены с переставленными словами.

`used_subjects` должен соответствовать `normalized_request.subjects` и `subject_continuity_policy`. Если policy требует один и тот же subject в каждом item, каждый candidate обязан использовать required subject.

Сохраняй `main_subject`, required subjects, `truth_mode`, `utility_mode`, `target_age`, `hard_details` и `character_profile`, если он есть.

Если `character_profile` присутствует, не меняй имя, вид, устойчивые черты, роль и ограничения персонажа.

Если `utility_mode = TEACHING`, candidate должен явно поддерживать teaching goal через сюжетное действие, а не только упоминать тему.

`expected_visual_idea` — короткая текстовая идея возможного визуального мотива. Это не image generation prompt, не Stage 3 instruction и не visual validation.

# Выразительность и anti-patterns

Для `FAIRY_TALE` с активным `substyle` (например `RUSSIAN_FOLK_TALE`) и/или vivid entity layer (например `FAIRY_TALE_ANIMAL_FOX`) пиши **живые** сказочные черновики, а не плоские моральные зарисовки.

Избегай generic template:

- «<герой> помог <другу> найти …»
- «<герой> научил всех делиться / играть вместе»
- «<герой> сказала добрые слова, и всё стало хорошо»

когда `utility_mode = NARRATIVE` и пользователь не просил явный урок.

Вместо этого используй:

- прямую речь и ласковые обращения;
- игровой конфликт, плутовство, озорство, комичный испуг;
- народную cadence (`шёл-шёл`, `бежал-бежал`, `жили-были`) при `RUSSIAN_FOLK_TALE`;
- личность главного subject из entity layer, а не роль «нейтрального помощника».

Короткая длина по age layer **не отменяет** живость: 3–4 предложения могут содержать реплику, повтор и яркий образ.

# Immutable / Non-owner Fields

Stage не меняет:

- `normalized_request`;
- `prompt_context`;
- `stage_prompt_context`;
- `candidate_count`;
- `subjects`;
- `subject_continuity_policy`;
- `character_profile`;
- `hard_details`;
- `visual_preferences`.

Stage не создаёт `version_id`, `scores`, `deduplication_results`, `ranked_candidates`, `validation_loop_state`, `validation_results` или `approved_texts`.

# Trace / Debug Expectations

В `used_context.resolved_layers`, `used_context.fallback_layers` и `used_context.unresolved_details` укажи только те layer ids/details, которые реально повлияли на candidate.

Если fallback detail использован, candidate должен не скрывать это в trace. Если unresolved detail нельзя безопасно использовать, сохрани его в `used_context.unresolved_details` и не превращай в факт.

# Что stage не решает

Stage не проверяет финальную валидность, не дедуплицирует весь пул как отдельный judge, не считает scores, не ранжирует, не исправляет candidates и не выбирает approved texts.

Stage не выполняет image generation, animation, micro-cartoon logic или visual validation.

# Примеры допустимого поведения

Допустимо: для правдивых историй про ёжика зимой создать темы про поиск укрытия, следы на снегу, тихую встречу у кустов и наблюдение за зимним лесом.

Допустимо: в `TRUTH` описать животное через наблюдаемое поведение без человеческой речи.

Допустимо: для `FAIRY_TALE + RUSSIAN_FOLK_TALE + лиса` — «Прибежала лисичка, постучала в окошко и говорит: "Пусти, заинька!"».

Допустимо: при fallback `PARROT` для "какаду" использовать общий слой попугая и отметить unresolved detail.

# Примеры недопустимого поведения

Недопустимо: создать пять тем "ёжик собирает листья", "ёжик ищет листья", "ёжик несёт листья" как разные candidates.

Недопустимо: в `TRUTH` сделать ёжика говорящим героем.

Недопустимо: заменить required subject или изменить персонажа Тим на другого бельчонка.

Недопустимо: для `FAIRY_TALE + RUSSIAN_FOLK_TALE` выдавать сухой modern moral-lesson text без речи, без игрового конфликта и без folk cadence.

Недопустимо: добавить `version_id`, `total_score`, `rank` или `approved` status.
