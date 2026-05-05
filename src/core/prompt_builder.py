import yaml
import os
from src.models.schemas import GenerationRequest, TruthMode, TextStyle

class PromptBuilder:
    def __init__(self, prompts_dir: str = "src/prompts"):
        self.prompts_dir = prompts_dir
        self.data = self._load_all_prompts()

    def _load_all_prompts(self):
        # Для простоты прототипа читаем все из одного файла system.yaml, 
        # но архитектура позволяет читать из нескольких
        path = os.path.join(self.prompts_dir, "system.yaml")
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
        return {}

    def build_text_prompt(self, request: GenerationRequest) -> str:
        base_data = self.data.get("base_instruction", {})
        system = base_data.get("system", "")
        format_instr = base_data.get("format", "")
        constraints = base_data.get("constraints", "")
        
        # Режим правдивости
        truth_key = self._map_truth_mode(request.truth_mode)
        truth_instr = self.data.get(truth_key, "")
        
        # Стиль текста
        style_key = self._map_text_style(request.text_style)
        style_instr = self.data.get(style_key, "")
        
        prompt = (
            f"{system}\n"
            f"РЕЖИМ: {truth_instr}\n"
            f"СТИЛЬ: {style_instr}\n"
            f"ОГРАНИЧЕНИЯ: {constraints}\n"
            f"ФОРМАТ: {format_instr}\n"
            f"ТЕМА: {request.topic}"
        )
        return prompt

    def build_image_prompt(self, story_text: str, image_style: str) -> str:
        base = self.data.get("image_base", "")
        return base.format(image_style=image_style, story_text=story_text)

    def _map_truth_mode(self, mode: TruthMode) -> str:
        mapping = {
            TruthMode.TRUTH: "truth",
            TruthMode.MYTH: "myth",
            TruthMode.FAIRY_TALE: "fairy_tale"
        }
        return mapping.get(mode, "truth")

    def _map_text_style(self, style: TextStyle) -> str:
        mapping = {
            TextStyle.GENTLE: "gentle",
            TextStyle.EDUCATIONAL: "educational",
            TextStyle.PLAYFUL: "playful"
        }
        return mapping.get(style, "gentle")
