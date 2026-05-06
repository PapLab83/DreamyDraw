from typing import Dict, Type
from src.providers.base import BaseLLMProvider, BaseImageProvider
from src.providers.llm_mock import LLMMockProvider
from src.providers.image_mock import ImageMockProvider
from src.providers.gptunnel_provider import GPTunnelLLMProvider, GPTunnelMediaProvider

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

# Выполняем регистрацию провайдеров
ProviderFactory.register_llm("mock", LLMMockProvider)
ProviderFactory.register_llm("gptunnel", GPTunnelLLMProvider)

ProviderFactory.register_image("mock", ImageMockProvider)
ProviderFactory.register_image("gptunnel", GPTunnelMediaProvider)
