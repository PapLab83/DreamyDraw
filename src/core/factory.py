from typing import Dict, Type

from src.config.settings import settings
from src.core.stage2_llm_executor import LLMStage2TextExecutor
from src.core.stage2_mock_executor import MockStage2TextExecutor
from src.providers.base import BaseLLMProvider, BaseImageProvider
from src.providers.gptunnel_provider import GPTunnelLLMProvider, GPTunnelMediaProvider
from src.providers.image_mock import ImageMockProvider
from src.providers.llm_mock import LLMMockProvider


class ProviderFactory:
    # Инициализируем словари явно
    _llm_registry: Dict[str, Type[BaseLLMProvider]] = {}
    _image_registry: Dict[str, Type[BaseImageProvider]] = {}

    @classmethod
    def get_llm_provider(cls, provider_type: str = "mock") -> BaseLLMProvider:
        p_type = str(provider_type).strip().lower()
        provider_class = cls._llm_registry.get(p_type)
        if not provider_class:
            raise ValueError(f"Unknown LLM provider type: {p_type}. Available: {list(cls._llm_registry.keys())}")
        return provider_class()

    @classmethod
    def get_image_provider(cls, provider_type: str = "mock") -> BaseImageProvider:
        p_type = str(provider_type).strip().lower()
        provider_class = cls._image_registry.get(p_type)
        if not provider_class:
            raise ValueError(f"Unknown Image provider type: {p_type}. Available: {list(cls._image_registry.keys())}")
        return provider_class()

    @classmethod
    def register_llm(cls, name: str, provider_class: Type[BaseLLMProvider]):
        cls._llm_registry[name] = provider_class

    @classmethod
    def register_image(cls, name: str, provider_class: Type[BaseImageProvider]):
        cls._image_registry[name] = provider_class


def build_stage2_text_executor(
    *,
    executor_type: str = "mock",
    provider_name: str | None = None,
    llm_provider: BaseLLMProvider | None = None,
    model_name: str | None = None,
    debug_artifact_dir: str | None = None,
    debug_to_stderr: bool = False,
):
    e_type = str(executor_type).strip().lower()
    if e_type == "mock":
        return MockStage2TextExecutor()
    if e_type != "llm":
        raise ValueError(f"Unknown Stage 2 executor type: {e_type}")
    provider = llm_provider or ProviderFactory.get_llm_provider(provider_name or settings.LLM_PROVIDER)
    effective_model = model_name or settings.LLM_MODEL
    if hasattr(provider, "model"):
        setattr(provider, "model", effective_model)
    return LLMStage2TextExecutor(
        provider,
        model_name=effective_model,
        debug_artifact_dir=debug_artifact_dir,
        debug_to_stderr=debug_to_stderr,
    )


def validate_llm_provider_config(provider_name: str | None = None) -> None:
    p_name = str(provider_name or settings.LLM_PROVIDER).strip().lower()
    if p_name == "gptunnel":
        if not settings.GPTTUNNEL_API_KEY:
            raise ValueError("GPTTUNNEL_API_KEY is required when --executor llm uses provider gptunnel.")
        if not settings.GPTTUNNEL_BASE_URL:
            raise ValueError("GPTTUNNEL_BASE_URL is required when --executor llm uses provider gptunnel.")
    if p_name not in ProviderFactory._llm_registry:
        raise ValueError(f"Unknown LLM provider type: {p_name}. Available: {list(ProviderFactory._llm_registry.keys())}")

# Выполняем регистрацию провайдеров
ProviderFactory.register_llm("mock", LLMMockProvider)
ProviderFactory.register_llm("gptunnel", GPTunnelLLMProvider)

ProviderFactory.register_image("mock", ImageMockProvider)
ProviderFactory.register_image("gptunnel", GPTunnelMediaProvider)
