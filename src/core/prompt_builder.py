import os
import re
from src.models.schemas import GenerationRequest, TruthMode, TextStyle
from src.config.settings import settings

class PromptBuilder:
    def __init__(self, prompts_dir: str = None):
        # Если путь не передан, берем его из настроек. 
        # Если в настройках путь не поменялся, используем новый стандартный путь.
        self.prompts_dir = prompts_dir or settings.PROMPTS_DIR
        if self.prompts_dir == "src/prompts":
            self.prompts_dir = "docs/03_PROMPTS"

    def _extract_prompt_block(self, file_path: str) -> str:
        """Извлекает текст из блока ## PROMPT_BLOCK в Markdown файле"""
        if not os.path.exists(file_path):
            print(f"DEBUG: File not found: {file_path}")
            return ""
            
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        # Ищем заголовок ## PROMPT_BLOCK и следующий за ним блок кода
        # Учитываем возможность разного количества решеток и пробелов
        pattern = r"## PROMPT_BLOCK\s*\n+```[a-z]*\n+(.*?)\n+```"
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        
        if match:
            return match.group(1).strip()
        
        print(f"DEBUG: PROMPT_BLOCK not found in {file_path}")
        return ""

    def build_text_prompt(self, request: GenerationRequest) -> str:
        # 1. Базовая инструкция
        base_path = os.path.join(self.prompts_dir, "base", "BASE_INSTRUCTION.md")
        base_instr = self._extract_prompt_block(base_path)
        
        # 2. Режим правдивости
        truth_file = self._map_truth_mode_file(request.truth_mode)
        truth_path = os.path.join(self.prompts_dir, "truth_modes", truth_file)
        truth_instr = self._extract_prompt_block(truth_path)
        
        # 3. Стиль текста
        style_file = self._map_text_style_file(request.text_style)
        style_path = os.path.join(self.prompts_dir, "text_styles", style_file)
        style_instr = self._extract_prompt_block(style_path)
        
        # Сборка финального промпта
        prompt_parts = []
        if base_instr: prompt_parts.append(base_instr)
        if truth_instr: prompt_parts.append(truth_instr)
        if style_instr: prompt_parts.append(style_instr)
        
        prompt_parts.append(f"ТЕМА ПОЛЬЗОВАТЕЛЯ: {request.topic}")
        
        return "\n\n".join(prompt_parts)

    def build_image_prompt(self, story_text: str, image_style: str) -> str:
        # Пока используем упрощенную логику для картинок, 
        # так как файл IMAGE_BASE_PROMPT.md еще может быть не заполнен
        image_base_path = os.path.join(self.prompts_dir, "image", "IMAGE_BASE_PROMPT.md")
        template = self._extract_prompt_block(image_base_path)
        
        if not template:
            # Фолбэк на базовый промпт, если файл пустой
            return f"Create a child-friendly illustration for this story. Style: {image_style}. Story: {story_text}"
            
        return template.format(image_style=image_style, story_text=story_text)

    def _map_truth_mode_file(self, mode: TruthMode) -> str:
        mapping = {
            TruthMode.TRUTH: "TRUTH.md",
            TruthMode.MYTH: "MYTH.md",
            TruthMode.FAIRY_TALE: "FAIRY_TALE.md"
        }
        return mapping.get(mode, "TRUTH.md")

    def _map_text_style_file(self, style: TextStyle) -> str:
        mapping = {
            TextStyle.GENTLE: "GENTLE.md",
            TextStyle.EDUCATIONAL: "EDUCATIONAL.md",
            TextStyle.PLAYFUL: "PLAYFUL.md"
        }
        return mapping.get(style, "GENTLE.md")
