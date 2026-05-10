"""
Ноды фазы генерации контента: text_generation, user_confirmation, image_generation.

Поток:
    text_generation → [CHECK: user_confirmation (interrupt)] → image_generation → END

В CHECK-режиме user_confirmation:
    - 'y' → подтверждение всех → image_generation
    - 'r' → чистим тексты → возврат в text_generation
    - 'n' → cancel → END (failed)
"""

import logging
import os
from typing import Callable

from langfuse import observe
from langgraph.types import interrupt

from src.config import constants
from src.core.graph.state import GraphState
from src.core.prompt_builder import PromptBuilder
from src.models.schemas import WorkMode
from src.providers.base import BaseImageProvider, BaseLLMProvider
from src.storage.json_storage import JSONStorage

logger = logging.getLogger(__name__)


# --- Фабрика: text_generation -------------------------------------------------

def make_text_generation(
    llm: BaseLLMProvider,
    storage: JSONStorage,
    prompt_builder: PromptBuilder,
) -> Callable[[GraphState], GraphState]:
    """
    LLM-нода: генерирует текст и вопросы для каждой истории, у которой
    text ещё пустой. Идёт по всем story в session.stories.
    """

    @observe(name="text_generation")
    def text_generation(state: GraphState) -> GraphState:
        session = state["session"]
        request = session.request
        logger.info(
            "[STEP] text-generation | Генерация текстов для %s историй",
            request.count,
        )

        for i in range(request.count):
            story = session.stories[i]

            if story.text:
                logger.debug("  [SKIP] История %s: текст уже есть", i + 1)
                continue

            # Определяем тему и сюжет для этой истории
            current_topic, current_content = _resolve_story_topic(session, i)

            if current_topic:
                story.sub_topic = current_topic
            else:
                current_topic = story.sub_topic if story.sub_topic else request.topic

            # Формируем промпт
            temp_request = request.model_copy(update={"topic": current_topic})
            prompt = prompt_builder.build_text_prompt(
                temp_request, session.global_context
            )

            if current_content:
                logger.debug(
                    "[DEBUG] История %s: Используется одобренный сюжет", i + 1
                )
                logger.debug("Входящий сюжет: %s", current_content)
                prompt += f"\n\nИСПОЛЬЗУЙ СЛЕДУЮЩИЙ СЮЖЕТ (ОДОБРЕНО): {current_content}"

            # Вызываем LLM
            raw_response = llm.generate_text(prompt)
            story.text, story.questions = _parse_llm_response(raw_response)

            logger.info("  [OK] История %s: текст сгенерирован", i + 1)
            storage.save_session(session)

        session.current_node = "texts_generated"
        storage.save_session(session)
        return {"session": session}

    return text_generation


# --- Фабрика: user_confirmation (interrupt) -----------------------------------

def make_user_confirmation(
    storage: JSONStorage,
) -> Callable[[GraphState], GraphState]:
    """
    Interrupt-нода: показывает пользователю сгенерированные тексты
    и просит подтверждение. Работает только в CHECK-режиме.
    В FAST-режиме маршрутизация эту ноду минует (см. route_after_text_generation).

    Через Command(resume=<value>):
        'y' / 'yes' / 'д' / 'да' → все is_confirmed=True → image_generation
        'r' / 'regenerate'        → чистим тексты → возврат в text_generation
        иначе ('n', 'cancel', ...) → cancel → END
    """

    @observe(name="user_confirmation")
    def user_confirmation(state: GraphState) -> GraphState:
        session = state["session"]

        # Готовим payload для UI/CLI
        stories_summary = []
        for i, story in enumerate(session.stories):
            stories_summary.append(
                {
                    "index": i,
                    "sub_topic": story.sub_topic,
                    "text": story.text,
                    "questions": story.questions,
                }
            )

        user_input = interrupt(
            {
                "type": "user_confirmation",
                "stories": stories_summary,
            }
        )

        choice = (user_input or "").strip().lower()

        if choice in ("y", "yes", "д", "да"):
            for story in session.stories:
                story.is_confirmed = True
            logger.info("[USER] Все тексты подтверждены, переходим к картинкам")
            session.current_node = "texts_confirmed"

        elif choice in ("r", "regenerate", "перегенерировать"):
            for story in session.stories:
                story.text = ""
                story.questions = []
                story.is_confirmed = False
            logger.info("[USER] Перегенерация всех текстов")
            session.current_node = "texts_generated"  # routing вернёт нас обратно

        else:
            logger.info("[USER] Отмена генерации по требованию пользователя")
            session.current_node = "failed"

        storage.save_session(session)
        return {"session": session}

    return user_confirmation


# --- Фабрика: image_generation ------------------------------------------------

def make_image_generation(
    image: BaseImageProvider,
    storage: JSONStorage,
    prompt_builder: PromptBuilder,
) -> Callable[[GraphState], GraphState]:
    """
    Нода генерации картинок. Синхронный цикл по всем историям.
    После завершения — session.is_completed = True.
    """

    @observe(name="image_generation")
    def image_generation(state: GraphState) -> GraphState:
        session = state["session"]
        request = session.request
        logger.info(
            "[STEP] image-generation | Генерация %s картинок", request.count
        )

        for i in range(request.count):
            story = session.stories[i]
            if story.image_path:
                logger.debug("  [SKIP] История %s: картинка уже есть", i + 1)
                continue

            image_filename = constants.STORY_IMAGE_FILENAME_TEMPLATE.format(index=i)
            image_path = os.path.join(
                storage.base_dir, session.session_id, image_filename
            )
            prompt = prompt_builder.build_image_prompt(
                story.text, request.image_style.value
            )

            story.image_path = image.generate_image(prompt, story.text, image_path)
            logger.info("  [OK] История %s: картинка сохранена", i + 1)
            storage.save_session(session)

        session.is_completed = True
        session.current_node = "completed"
        storage.save_session(session)
        logger.info("[STEP] image-generation | Все картинки готовы ✓")
        return {"session": session}

    return image_generation


# --- Внутренние утилиты -------------------------------------------------------

def _resolve_story_topic(session, i: int) -> tuple[str, str]:
    """
    Определяет тему и сюжет для истории i.
    Приоритет: approved_plan_items > full_plan_items.
    Возвращает (topic, content).
    """
    if str(i) in session.approved_plan_items:
        item = session.approved_plan_items[str(i)]
        return item.get("theme", ""), item.get("content", "")
    if i < len(session.full_plan_items):
        item = session.full_plan_items[i]
        return item.get("theme", ""), item.get("content", "")
    return "", ""


def _parse_llm_response(text: str) -> tuple[str, list]:
    """
    Парсер ответа LLM для текстовой генерации.
    Разделяет ответ на блок 'История' и блок 'Вопросы'.
    Идентичен оригинальному Orchestrator._parse_llm_response.
    """
    story_part, questions = "", []
    q_start = text.find("Вопросы:")
    if q_start != -1:
        story_part = (
            text[:q_start]
            .replace("История:", "")
            .replace("Текст истории:", "")
            .strip()
        )
        q_list = text[q_start:].replace("Вопросы:", "").strip().split("\n")
        questions = [
            q.strip(constants.QUESTION_NUMBERING_STRIP_CHARS)
            for q in q_list
            if q.strip()
        ]
    else:
        story_part = (
            text.replace("История:", "").replace("Текст истории:", "").strip()
        )
    return story_part, questions