import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Провайдеры (mock или openai/dalle)
    LLM_PROVIDER: str = "mock"
    IMAGE_PROVIDER: str = "mock"
    
    # GPTunnel / OpenAI настройки
    GPTTUNNEL_API_KEY: str = ""
    GPTTUNNEL_BASE_URL: str = "https://gptunnel.ru/v1"
    
    LLM_MODEL: str = "gpt-4o-mini"
    IMAGE_MODEL: str = "nano-banana" # dall-e-3, nano-banana
    
    # Дефолтные значения
    DEFAULT_COUNT: int = 1
    
    # Пути
    OUTPUT_DIR: str = "output"
    PROMPTS_DIR: str = "docs/03_PROMPTS"
    MOCKS_DIR: str = "assets/mocks"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
