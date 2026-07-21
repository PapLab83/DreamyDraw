---
id: ENTITY_ROAD
type: entity
namespace: entities/environment/safety
name: Дорога
aliases:
  - дорога
  - улица
  - проезжая часть
  - переход
  - пешеходный переход
  - road
applies_to:
  content_formats: [story]
  truth_modes: [TRUTH, FAIRY_TALE]
  utility_modes: [NARRATIVE, TEACHING]
  ages: ["3", "5"]
user_description: "Дорога как environment safety entity для историй про спокойное поведение рядом с машинами."
short_description: "Environment safety entity: дорога для машин, у края нужно остановиться, быть рядом со взрослым и следовать road safety layer."
constraints:
  - Не показывать перебегание дороги или игру на дороге как успешное поведение.
  - Не делать road safety пугающим, графичным или shame-based.
  - Не дублировать полный road safety utility topic.
  - Не использовать сказочность для отмены правил дороги.
good_for:
  - road safety support entity
  - setting near crossing, street or sidewalk
  - teaching stories with caring adult and traffic light
bad_for:
  - accident scene
  - unsafe shortcut
safety_notes:
  - safe action must stay clear and calm
---

# Назначение слоя

Используй этот слой, когда в истории нужна дорога, улица, переход или место рядом с машинами. Это environment safety entity, а не полный road safety utility topic.

# Что добавить в результат

Покажи дорогу как место, где важно остановиться, быть рядом со знакомым заботящимся взрослым, смотреть на переход или светофор и не играть на проезжей части.

В `FAIRY_TALE` дорога может быть "широкой рекой для машин" или сказочной дорожкой с правилами, но safe action остаётся земным и понятным.

# Ограничения

Не показывай unsafe advice как удачный исход: нельзя перебегать, играть на дороге, идти на красный, вырываться от взрослого или следовать за сказочным персонажем через дорогу без правил.

Не добавляй аварии, graphic danger, realistic terror или shame.

# Как сочетать с другими слоями

`UTILITY_TOPIC_ROAD_SAFETY` задаёт teaching goal. `ENTITY_TRAFFIC_LIGHT` может уточнить signal object. `ENTITY_CARING_ADULT` помогает показать safe support.

Validator должен считать unsafe road advice critical issue.

# Примеры сочетания со слоями

`TRUTH + TEACHING`: "У края дороги ребёнок остановился и взял папу за руку".

`FAIRY_TALE + road safety`: "Сказочная дорога шумела, как река, и зайчонок ждал зелёный свет рядом с мамой".


# Примеры недопустимого поведения

Недопустимо: "Герой быстро перебежал дорогу и успел, значит, так можно".

Недопустимо: делать сцену аварии ради обучения.

Недопустимо: сказочный помощник отменяет необходимость ждать и смотреть.
