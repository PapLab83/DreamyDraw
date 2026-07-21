---
id: ENTITY_TRAFFIC_LIGHT
type: entity
namespace: entities/objects/safety
name: Светофор
aliases:
  - светофор
  - зелёный свет
  - зеленый свет
  - красный свет
  - traffic light
applies_to:
  content_formats: [story]
  truth_modes: [TRUTH, FAIRY_TALE]
  utility_modes: [NARRATIVE, TEACHING]
  ages: ["3", "5"]
user_description: "Светофор как safety object для историй про дорогу и ожидание разрешающего сигнала."
short_description: "Safety object entity: светофор помогает дождаться разрешающего сигнала; fairy-tale style не отменяет road safety."
constraints:
  - Не показывать переход на красный как успешное действие.
  - Не делать светофор магическим объектом, который отменяет взрослого и правила.
  - Не дублировать полный road safety utility topic.
  - Не добавлять graphic road danger.
good_for:
  - road safety support entity
  - teaching stories about waiting
  - fairy-tale object that still preserves safe action
bad_for:
  - unsafe shortcut
  - frightening road scene
safety_notes:
  - green signal alone may not replace caring adult when age/utility requires adult support
---

# Назначение слоя

Используй этот слой, когда в истории нужен светофор, красный или зелёный сигнал. Это safety object entity, а не полный road safety utility topic.

# Что добавить в результат

Покажи ясное действие: герой остановился, посмотрел на светофор, дождался разрешающего зелёного сигнала и пошёл по переходу рядом со взрослым, если это требуется utility/age layer.

В `FAIRY_TALE` светофор может подмигнуть, заговорить или светить как фонарик, но правило остаётся понятным.

# Ограничения

Не показывай переход на красный или перебегание как удачный исход. Не делай зелёный свет единственным условием, если story context требует взрослого рядом.

Не добавляй аварии, угрозы, graphic danger или fearmongering.

Именованных/reference персонажей из примеров используй только если пользователь сам запросил такого персонажа, reference label или совместимый сказочный стиль. Без такого запроса заменяй их на generic ребёнка, взрослого или сказочного героя.

# Как сочетать с другими слоями

`ENTITY_ROAD` задаёт environment context. `UTILITY_TOPIC_ROAD_SAFETY` задаёт teaching goal. `ENTITY_CARING_ADULT` может быть required safety support.

Validator должен считать unsafe signal behavior critical issue.

# Примеры сочетания со слоями

`TRUTH + TEACHING`: "Светофор переключился на зелёный. Мама взяла ребёнка за руку, и они вместе пошли по пешеходному переходу".

`FAIRY_TALE + TEACHING`: "Зайчонок увидел, как на светофоре загорелся зелёный огонёк. Он крепче взял папу за лапу, и они вместе перешли дорогу".

`NARRATIVE + waiting`: "Красный свет ещё горел. Дядя Стёпа стоял рядом с детьми и смотрел, как по дороге едут машины".

# Примеры недопустимого поведения

Недопустимо: "Светофор был красным, но герой побежал, потому что машин не было".

Недопустимо: "Волшебный светофор разрешил детям играть на дороге".

Недопустимо: использовать страшную аварию как главный teaching device.
