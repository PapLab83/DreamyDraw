import requests
import os
import time
from typing import List
from src.providers.base import BaseLLMProvider, BaseImageProvider
from src.config.settings import settings
from openai import OpenAI

class GPTunnelLLMProvider(BaseLLMProvider):
    def __init__(self):
        self.client = OpenAI(
            api_key=settings.GPTTUNNEL_API_KEY,
            base_url=settings.GPTTUNNEL_BASE_URL
        )
        self.model = settings.LLM_MODEL

    def generate_text(self, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7
        )
        return response.choices[0].message.content

    def generate_questions(self, text: str) -> List[str]:
        return []

class GPTunnelMediaProvider(BaseImageProvider):
    """Провайдер для CreativeLab API (Media API) от GPTunnel"""
    def __init__(self):
        self.api_key = settings.GPTTUNNEL_API_KEY
        self.base_url = "https://gptunnel.ru/v1/media"
        self.model = settings.IMAGE_MODEL # Например, grok-imagine или gpt-image-1-high

    def generate_image(self, prompt: str, overlay_text: str, output_path: str) -> str:
        # 1. Создание задачи (Асинхронно)
        create_url = f"{self.base_url}/create"
        headers = {
            "Authorization": self.api_key,
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "prompt": f"{prompt}. Please include this text on the image: {overlay_text}",
            "ar": "1:1"
        }

        print(f"Отправка запроса в CreativeLab API (модель: {self.model})...")
        response = requests.post(create_url, headers=headers, json=payload)
        response.raise_for_status()
        
        task_data = response.json()
        task_id = task_data.get("id")
        
        if not task_id:
            raise ValueError(f"Не удалось получить task_id. Ответ: {task_data}")

        print(f"Задача создана. ID: {task_id}. Ожидание результата...")

        # 2. Опрос результата (Polling)
        result_url = f"{self.base_url}/result"
        max_attempts = 30
        attempt = 0
        image_url = None

        while attempt < max_attempts:
            res = requests.post(result_url, headers=headers, json={"task_id": task_id})
            res.raise_for_status()
            res_data = res.json()
            
            status = res_data.get("status")
            if status == "done":
                image_url = res_data.get("url")
                break
            elif status == "error":
                raise ValueError(f"Ошибка генерации на стороне сервера: {res_data}")
            
            print(f"Статус: {status}... ждем 5 сек")
            time.sleep(5)
            attempt += 1

        if not image_url:
            raise TimeoutError("Превышено время ожидания генерации изображения.")

        print(f"Изображение готово! Скачивание...")

        # 3. Скачивание
        img_res = requests.get(image_url)
        img_res.raise_for_status()
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        # Сохраняем как есть (может быть webp), но расширение в output_path должно соответствовать
        # Для простоты сохраняем в файл, путь к которому передал оркестратор
        with open(output_path, 'wb') as f:
            f.write(img_res.content)
            
        return output_path
