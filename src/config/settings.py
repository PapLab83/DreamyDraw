import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Провайдеры (mock или реальные)
    LLM_PROVIDER: str = "mock"
    IMAGE_PROVIDER: str = "mock"
    
    # API Ключи (будут в .env)
    OPENAI_API_KEY: str = ""
    
    # Пути
    OUTPUT_DIR: str = "output"
    PROMPTS_DIR: str = "src/prompts"
    MOCKS_DIR: str = "assets/mocks"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
