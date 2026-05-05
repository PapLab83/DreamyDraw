import pytest
from src.core.prompt_builder import PromptBuilder
from src.models.schemas import GenerationRequest, TruthMode, TextStyle

def test_prompt_building():
    builder = PromptBuilder()
    request = GenerationRequest(
        topic="белка",
        truth_mode=TruthMode.FAIRY_TALE,
        text_style=TextStyle.PLAYFUL
    )
    prompt = builder.build_text_prompt(request)
    
    assert "белка" in prompt
    assert "РЕЖИМ:" in prompt
    assert "ФОРМАТ:" in prompt
    # Проверка, что подставился именно текст из fairy_tale, а не truth
    assert "фантастическую" in prompt 
