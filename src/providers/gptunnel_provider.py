import logging
import os
import time
from typing import List

import requests
from openai import OpenAI

from src.config.settings import settings
from src.providers.base import BaseLLMProvider, BaseImageProvider
from src.utils import langfuse_client

logger = logging.getLogger(__name__)

class GPTunnelLLMProvider(BaseLLMProvider):
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.GPTTUNNEL_API_KEY,
            base_url=settings.GPTTUNNEL_BASE_URL
        )
        self.model = settings.LLM_MODEL

    def generate_text(self, prompt: str, *, temperature: float | None = None) -> str:
        langfuse = langfuse_client.get_client()
        resolved_temperature = (
            float(temperature) if temperature is not None else float(settings.LLM_TEMPERATURE_DEFAULT)
        )

        # Если SDK выключен / не инициализирован — работаем без трейсинга
        if langfuse is None:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=resolved_temperature,
            )
            return response.choices[0].message.content

        if settings.LANGFUSE_CAPTURE_PROMPTS:
            input_payload = [{"role": "user", "content": prompt[:settings.LANGFUSE_PROMPT_PREVIEW_CHARS]}]
        else:
            input_payload = [{"role": "user", "content": f"<{len(prompt)} chars>"}]

        with langfuse.start_as_current_observation(
                as_type="generation",
                name="gptunnel.generate_text",
                model=self.model,
                input=input_payload,
                metadata={"provider": "gptunnel", "temperature": resolved_temperature},
        ) as gen:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=resolved_temperature,
                )
                result = response.choices[0].message.content

                usage = getattr(response, "usage", None)
                usage_details = None
                if usage is not None:
                    usage_details = {
                        "input": getattr(usage, "prompt_tokens", 0),
                        "output": getattr(usage, "completion_tokens", 0),
                        "total": getattr(usage, "total_tokens", 0),
                    }

                gen.update(
                    output=result,
                    usage_details=usage_details,
                )
                return result
            except Exception as exc:
                gen.update(level="ERROR", status_message=str(exc))
                raise

    def generate_questions(self, text: str) -> List[str]:
        return []

class GPTunnelMediaProvider(BaseImageProvider):
    """Провайдер для CreativeLab API (Media API) от GPTunnel"""
    def __init__(self):
        self.api_key = settings.GPTTUNNEL_API_KEY
        self.base_url = "https://gptunnel.ru/v1/media"
        self.model = settings.IMAGE_MODEL # Например, grok-imagine или gpt-image-1-high

    def generate_image(self, prompt: str, overlay_text: str, output_path: str) -> str:
        langfuse = langfuse_client.get_client()

        # Без обвязки если SDK не активен
        if langfuse is None:
            return self._generate_image_impl(prompt, overlay_text, output_path)

        if settings.LANGFUSE_CAPTURE_PROMPTS:
            input_payload = {
                "model": self.model,
                "prompt_preview": prompt[:settings.LANGFUSE_PROMPT_PREVIEW_CHARS],
                "overlay_preview": overlay_text[:settings.LANGFUSE_PROMPT_PREVIEW_CHARS],
                "output_path": output_path,
            }
        else:
            input_payload = {
                "model": self.model,
                "prompt_length": len(prompt),
                "overlay_length": len(overlay_text),
                "output_path": output_path,
            }

        with langfuse.start_as_current_observation(
                as_type="span",
                name="gptunnel.generate_image",
                input=input_payload,
                metadata={"provider": "gptunnel", "model": self.model, "host": self.base_url},
        ) as span:
            try:
                result_path = self._generate_image_impl(prompt, overlay_text, output_path)
                span.update(output={"output_path": result_path, "status": "done"})
                return result_path
            except Exception as exc:
                span.update(level="ERROR", status_message=str(exc), output={"status": "error"})
                raise

    def _generate_image_impl(self, prompt: str, overlay_text: str, output_path: str) -> str:
        """Реальная логика генерации изображения (без обвязки трейсинга)."""
        create_url = f"{self.base_url}/create"
        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "prompt": f"{prompt}. Please include this text on the image: {overlay_text}",
            "ar": settings.IMAGE_ASPECT_RATIO
        }

        logger.info("Отправка запроса в CreativeLab API (модель: %s)...", self.model)
        response = requests.post(create_url, headers=headers, json=payload)
        response.raise_for_status()

        task_data = response.json()
        task_id = task_data.get("id")

        if not task_id:
            raise ValueError(f"Не удалось получить task_id. Ответ: {task_data}")

        logger.info("Задача создана. ID: %s. Ожидание результата...", task_id)

        result_url = f"{self.base_url}/result"
        attempt = 0
        image_url = None

        while attempt < settings.MEDIA_POLL_MAX_ATTEMPTS:
            try:
                res = requests.post(
                    result_url,
                    headers=headers,
                    json={"task_id": task_id},
                    timeout=settings.HTTP_REQUEST_TIMEOUT_SECONDS
                )
                res.raise_for_status()
                res_data = res.json()

                status = res_data.get("status")
                if status == "done":
                    image_url = res_data.get("url")
                    break
                if status == "error" or status == "failed":
                    raise ValueError(f"Ошибка генерации на стороне сервера (статус: {status}): {res_data}")

                logger.debug("Статус: %s... ждем %s сек", status, settings.MEDIA_POLL_INTERVAL_SECONDS)
                time.sleep(settings.MEDIA_POLL_INTERVAL_SECONDS)
                attempt += 1
            except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
                logger.warning(
                    "Ошибка соединения при проверке статуса: %s. Пробую еще раз через %s сек...",
                    e,
                    settings.MEDIA_RETRY_INTERVAL_SECONDS,
                )
                time.sleep(settings.MEDIA_RETRY_INTERVAL_SECONDS)
                attempt += 1

        if not image_url:
            raise TimeoutError("Превышено время ожидания генерации изображения.")

        logger.info("Изображение готово! Скачивание...")

        img_res = requests.get(image_url)
        img_res.raise_for_status()

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'wb') as f:
            f.write(img_res.content)

        return output_path
