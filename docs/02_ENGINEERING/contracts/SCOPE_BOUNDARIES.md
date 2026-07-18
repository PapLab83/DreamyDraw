# SCOPE_BOUNDARIES.md

# Scope Boundaries

Статус: рабочие границы MVP-контуров.

Документ фиксирует, что не входит в первый MVP-контур prompt contracts и не должно блокировать подготовку seed prompts, PromptRegistry, PromptComposer и второго этапа генерации текстов.

Продуктовый MVP DreamyDraw по-прежнему предполагает визуальный результат. В этом документе граница уже: contracts и text pipeline доводятся до `approved_texts`, а baseline image generation рассматривается как downstream stage с отдельной детализацией.

---

## 1. Не входит в MVP контрактов

В первый контракт и seed scope не входят:

* полная база персонажей и объектов;
* все возрастные градации `3`, `3.5`, `4`, `4.5`, `5`;
* полноценный режим `ENGLISH`;
* картинки-загадки;
* серия картинок по одному рассказу;
* петлевые и маятниковые анимации;
* короткие микро-мультики;
* личный кабинет и долгосрочная история пользователя;
* vector search по prompt-базе;
* отдельный агент для каждого score component;
* сложный пользовательский арбитраж при нехватке approved texts.

---

## 2. Почему это вынесено отдельно

Эти направления важны для продукта, но они не должны перегружать стартовую реализацию prompt lookup и text pipeline.

Контракты должны оставаться совместимыми с будущими форматами, но MVP-проверка должна сфокусироваться на:

* нормализации параметров;
* prompt file contract;
* metadata lookup;
* execution lookup;
* prompt composition;
* candidate generation;
* scoring;
* validation/refinement;
* approved texts.

---

## 3. Где отслеживать будущие направления

Будущие форматы и продуктовые расширения должны жить в:

* `docs/01_PRODUCT/PRODUCT_VISION.md`;
* `docs/02_ENGINEERING/ROADMAP.md`;
* `docs/02_ENGINEERING/implementation/RELEASE_2_BACKLOG.md`;
* отдельных draft-документах по визуальному этапу и новым форматам.

Если идея начинает влиять на поля `normalized_request` или `prompt_context`, её нужно вернуть в контрактные документы.
