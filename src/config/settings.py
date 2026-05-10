from pydantic_settings import BaseSettings, SettingsConfigDict
from src.config import constants

class Settings(BaseSettings):
    # Провайдеры (mock или openai/dalle)
    LLM_PROVIDER: str = "gptunnel" # gptunnel
    IMAGE_PROVIDER: str = "gptunnel" # gptunnel
    
    # GPTunnel / OpenAI настройки
    GPTTUNNEL_API_KEY: str = ""
    GPTTUNNEL_BASE_URL: str = "https://gptunnel.ru/v1"
    
    LLM_MODEL: str = "gpt-4o" # gpt-4o, gpt-4o-mini
    IMAGE_MODEL: str = "nano-banana-2" # dall-e-3, nano-banana, nano-banana-2
    
    # Дефолтные значения
    DEFAULT_COUNT: int = constants.DEFAULT_COUNT
    MAX_COUNT: int = constants.MAX_COUNT

    # Продуктовые лимиты
    TARGET_AGE_MIN: int = constants.TARGET_AGE_MIN
    TARGET_AGE_MAX: int = constants.TARGET_AGE_MAX
    STORY_SENTENCES_MIN: int = constants.STORY_SENTENCES_MIN
    STORY_SENTENCES_MAX: int = constants.STORY_SENTENCES_MAX
    MIN_QUESTIONS: int = constants.MIN_QUESTIONS
    MAX_QUESTIONS: int = constants.MAX_QUESTIONS

    # Пороги пайплайна
    USER_ARBITRATION_THRESHOLD: int = constants.USER_ARBITRATION_THRESHOLD
    MAX_VALIDATION_RETRIES: int = constants.MAX_VALIDATION_RETRIES
    MIN_CHILD_INDEX: float = constants.MIN_CHILD_INDEX
    DEFAULT_IDEA_CHILD_INDEX: float = constants.DEFAULT_IDEA_CHILD_INDEX
    FALLBACK_IDEA_CHILD_INDEX: float = constants.FALLBACK_IDEA_CHILD_INDEX
    SCORE_NORMALIZATION_EPSILON: float = constants.SCORE_NORMALIZATION_EPSILON

    # Настройки провайдеров
    HTTP_REQUEST_TIMEOUT_SECONDS: int = constants.HTTP_REQUEST_TIMEOUT_SECONDS
    MEDIA_POLL_MAX_ATTEMPTS: int = constants.MEDIA_POLL_MAX_ATTEMPTS
    MEDIA_POLL_INTERVAL_SECONDS: int = constants.MEDIA_POLL_INTERVAL_SECONDS
    MEDIA_RETRY_INTERVAL_SECONDS: int = constants.MEDIA_RETRY_INTERVAL_SECONDS
    IMAGE_ASPECT_RATIO: str = constants.IMAGE_ASPECT_RATIO

    # Настройки LangFuse
    LANGFUSE_PUBLIC_KEY: str = ""
    LANGFUSE_SECRET_KEY: str = ""
    LANGFUSE_HOST: str = constants.LANGFUSE_HOST
    LANGFUSE_ENABLED: bool = constants.LANGFUSE_ENABLED
    LANGFUSE_PROJECT_NAME: str = constants.LANGFUSE_PROJECT_NAME
    LANGFUSE_ENV: str = constants.LANGFUSE_ENV
    LANGFUSE_SAMPLE_RATE: float = constants.LANGFUSE_SAMPLE_RATE
    LANGFUSE_CAPTURE_PROMPTS: bool = constants.LANGFUSE_CAPTURE_PROMPTS
    LANGFUSE_PROMPT_PREVIEW_CHARS: int = constants.LANGFUSE_PROMPT_PREVIEW_CHARS

    # Логирование
    LOG_LEVEL: str = constants.LOG_LEVEL
    LOG_TO_FILE: bool = constants.LOG_TO_FILE
    LOG_FILE_PATH: str = constants.LOG_FILE_PATH
    LOG_FORMAT_COLORED: bool = constants.LOG_FORMAT_COLORED
    
    # Пути
    OUTPUT_DIR: str = "output"
    PROMPTS_DIR: str = "docs/03_PROMPTS"
    MOCKS_DIR: str = "assets/mocks"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

settings = Settings()
