from typing import Dict, Type
from src.providers.base import BaseLLMProvider, BaseImageProvider
from src.providers.llm_mock import LLMMockProvider
from src.providers.image_mock import ImageMockProvider

# Здесь в будущем будут импорты реальных провайдеров
# from src.providers.openai_provider import OpenAIProvider

class ProviderFactory:
    # Реестр LLM провайдеров
    _llm_registry: Dict[str, Type[BaseLLMProvider]] = {
        "mock": LLMMockProvider,
        # "openai": OpenAIProvider,
    }

    # Реестр Image провайдеров
    _image_registry: Dict[str, Type[BaseImageProvider]] = {
        "mock": ImageMockProvider,
        # "dalle": DalleProvider,
    }

    @classmethod
    def get_llm_provider(cls, provider_type: str = "mock") -> BaseLLMProvider:
        provider_class = cls._llm_registry.get(provider_type)
        if not provider_class:
            raise ValueError(f"Unknown LLM provider type: {provider_type}. Available: {list(cls._llm_registry.keys())}")
        return provider_class()

    @classmethod
    def get_image_provider(cls, provider_type: str = "mock") -> BaseImageProvider:
        provider_class = cls._image_registry.get(provider_type)
        if not provider_class:
            raise ValueError(f"Unknown Image provider type: {provider_type}. Available: {list(cls._image_registry.keys())}")
        return provider_class()

    @classmethod
    def register_llm(cls, name: str, provider_class: Type[BaseLLMProvider]):
        """Позволяет регистрировать новых провайдеров без изменения кода фабрики"""
        cls._llm_registry[name] = provider_class

    @classmethod
    def register_image(cls, name: str, provider_class: Type[BaseImageProvider]):
        cls._image_registry[name] = provider_class
