---
id: FAIRY_TALE_ANIMAL_SQUIRREL
type: entity
namespace: truth_modes/FAIRY_TALE/characters/animals
name: Белка как сказочный персонаж
aliases:
  - белка
  - белочка
  - бельчонок
  - сказочная белка
  - говорящая белка
  - squirrel
  - fairy tale squirrel
applies_to:
  content_formats: [story]
  truth_modes: [FAIRY_TALE]
  utility_modes: [NARRATIVE, TEACHING]
  ages: ["3", "5"]
user_description: "Сказочная белка для детских историй: может говорить, быть ловкой, заботливой, запасливой или любопытной героиней."
short_description: "Белка-персонаж для FAIRY_TALE: речь, характер, ловкость, запасы и уютное дерево разрешены в пределах age, safety, utility и character_profile."
constraints:
  - Разрешать речь и характер белки только внутри FAIRY_TALE.
  - Не создавать Tim-specific prompt file; Тим остаётся в normalized `character_profile`.
  - Не использовать сказочность для unsafe advice или нарушения teaching goal.
  - Если задан `character_profile`, не менять имя, stable traits и required subject.
good_for:
  - сказочный лесной герой
  - custom squirrel character вроде маленького бельчонка Тима
  - teaching stories про порядок, заботу, сон или просьбу о помощи
bad_for:
  - правдивая история без speaking animals
  - Tim-specific species prompt
safety_notes:
  - character_profile and utility layers win over playful squirrel behavior
---

# Назначение слоя

Используй этот слой, когда subject запроса — белка в `truth_mode = FAIRY_TALE`. Белка может быть героиней, помощницей, ребёнком-персонажем, лесной соседкой или маленьким другом, если это не конфликтует с age layer, safety и utility goal.

Если пользователь просит `маленького бельчонка Тима`, этот слой может быть species/entity layer, но Тим не получает отдельный prompt file. Имя, stable traits и continuity фиксируются в `character_profile`, `hard_details` и `subject_continuity_policy`.

# Что добавить в результат

Белка может говорить короткими фразами, быть быстрой, заботливой, запасливой, любопытной, смешливой или немного суетливой. Сохраняй узнаваемые признаки: пушистый хвост, ветки, дупло, орешки, шишки, прыжки, маленькие лапки.

Для teaching stories белка может показывать бытовые действия: складывать игрушки, делиться запасами, просить помощи, не торопиться на дороге, чистить зубки перед сном или беречь чужие вещи.

# Ограничения

Не позволяй сказочной белке отменять `utility_goal`, safety constraints, `hard_details` или `character_profile`. Если герой — Тим, refiner не должен менять его имя, stable traits или required subject.

Не делай белку generic talking child без animal identity. Даже в сказке её действия и образы должны оставаться беличьими.

# Как сочетать с другими слоями

`FAIRY_TALE_BASE` разрешает speaking animals и мягкое волшебство. Style layer может добавить народную или другую сказочную манеру. Age layer ограничивает длину речи. Utility layer сильнее шутки, волшебства и характера.

Validator должен проверять continuity: named squirrel character остаётся тем же персонажем во всех items.

# Примеры сочетания со слоями

`FAIRY_TALE + NARRATIVE`: "Белочка Сима прыгнула на ветку и сказала: 'Сегодня облака похожи на мягкие орешки'".

`FAIRY_TALE + TEACHING + cleanup`: "Бельчонок Тим разложил кубики по коробкам и спрятал машинку на нижнюю полку, чтобы утром быстро её найти".

`FAIRY_TALE + TEACHING + sharing`: "Белочка положила два орешка себе и один другу: 'Так запас становится добрее'".

`FAIRY_TALE + character_profile`: "Если героя зовут Тим, он остаётся Тимом: маленьким бельчонком с теми же stable traits".

# Примеры недопустимого поведения

Недопустимо: менять Тима на безымянную белку, если `character_profile.name = Тим`.

Недопустимо: в teaching story показать, что белка хитрит и получает награду.

Недопустимо: использовать сказочность, чтобы ребёнок нарушал safety rule.
