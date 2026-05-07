import os
import re
from src.models.schemas import GenerationRequest, TruthMode, TextStyle
from src.config.settings import settings

class PromptBuilder:
    def __init__(self, prompts_dir: str = None):
        self.prompts_dir = prompts_dir or settings.PROMPTS_DIR
        if self.prompts_dir == "src/prompts":
            self.prompts_dir = "docs/03_PROMPTS"

    def _extract_prompt_block(self, file_path: str) -> str:
        if not os.path.exists(file_path):
            return ""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        pattern = r"## PROMPT_BLOCK\s*\n+```[a-z]*\n+(.*?)\n+```"
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return ""

    def build_safety_prompt(self, topic: str) -> str:
        path = os.path.join(self.prompts_dir, "text", "SAFETY_GATE.md")
        instr = self._extract_prompt_block(path)
        return f"{instr}\n\nТЕМА ДЛЯ ПРОВЕРКИ: {topic}"

    def build_config_match_prompt(self, topic: str, truth_mode: str) -> str:
        path = os.path.join(self.prompts_dir, "text", "CONFIG_MATCH.md")
        instr = self._extract_prompt_block(path)
        return f"{instr}\n\nТЕМА: {topic}\nВЫБРАННЫЙ РЕЖИМ: {truth_mode}"

    def build_series_plan_prompt(self, topic: str, count: int) -> str:
        path = os.path.join(self.prompts_dir, "text", "SERIES_PLANNER.md")
        instr = self._extract_prompt_block(path)
        instr = instr.replace("{topic}", topic).replace("{count}", str(count)).replace("{correction_block}", "")
        return instr

    def build_plan_validator_prompt(self, full_plan_json: str, context: str, truth_mode: str) -> str:
        path = os.path.join(self.prompts_dir, "text", "PLAN_VALIDATOR.md")
        instr = self._extract_prompt_block(path)
        truth_path = os.path.join(self.prompts_dir, "text", "truth_modes", f"{self._map_truth_mode_file_by_val(truth_mode)}.md")
        truth_rules = self._extract_prompt_block(truth_path)
        instr = instr.replace("{truth_mode}", truth_mode).replace("{truth_mode_rules}", truth_rules)
        return f"{instr}\n\nПЛАН ДЛЯ ПРОВЕРКИ (JSON):\n{full_plan_json}\n\nГЛОБАЛЬНЫЙ КОНТЕКСТ:\n{context}"

    def build_plan_refine_prompt(self, current_plan_json: str, validator_feedback_json: str, truth_mode: str) -> str:
        path = os.path.join(self.prompts_dir, "text", "PLAN_REFINER.md")
        instr = self._extract_prompt_block(path)
        instr = instr.replace("{truth_mode}", truth_mode)
        return f"{instr}\n\nТЕКУЩИЙ ПЛАН (JSON):\n{current_plan_json}\n\nЗАМЕЧАНИЯ ВАЛИДАТОРА И РЕШЕНИЯ (JSON):\n{validator_feedback_json}"

    def build_plan_reviewer_prompt(self, current_plan_json: str, validator_feedback_json: str, user_comment: str) -> str:
        path = os.path.join(self.prompts_dir, "text", "PLAN_REVIEWER.md")
        instr = self._extract_prompt_block(path)
        return f"{instr}\n\nТЕКУЩИЙ ПЛАН (JSON):\n{current_plan_json}\n\nЗАМЕЧАНИЯ КРИТИКА (JSON):\n{validator_feedback_json}\n\nКОММЕНТАРИЙ АВТОРА:\n{user_comment}"

    def _map_truth_mode_file_by_val(self, mode_val: str) -> str:
        if mode_val == "Правда": return "TRUTH"
        if mode_val == "Миф": return "MYTH"
        if mode_val == "Сказка": return "FAIRY_TALE"
        return "TRUTH"

    def build_text_prompt(self, request: GenerationRequest, global_context: str = "") -> str:
        base_path = os.path.join(self.prompts_dir, "text", "TEXT_BASE_PROMPT.md")
        base_instr = self._extract_prompt_block(base_path)
        truth_file = self._map_truth_mode_file(request.truth_mode)
        truth_path = os.path.join(self.prompts_dir, "text", "truth_modes", truth_file)
        truth_instr = self._extract_prompt_block(truth_path)
        style_file = self._map_text_style_file(request.text_style)
        style_path = os.path.join(self.prompts_dir, "text", "styles", style_file)
        style_instr = self._extract_prompt_block(style_path)
        prompt_parts = []
        if global_context: prompt_parts.append(f"ОБЩИЙ КОНТЕКСТ СЕРИИ: {global_context}")
        if base_instr: prompt_parts.append(base_instr)
        if truth_instr: prompt_parts.append(truth_instr)
        if style_instr: prompt_parts.append(style_instr)
        prompt_parts.append(f"ТЕМА ЭТОЙ ИСТОРИИ: {request.topic}")
        return "\n\n".join(prompt_parts)

    def build_image_prompt(self, story_text: str, image_style: str) -> str:
        base_path = os.path.join(self.prompts_dir, "image", "IMAGE_BASE_PROMPT.md")
        base_template = self._extract_prompt_block(base_path)
        style_file = f"{self._map_image_style_name(image_style)}.md"
        style_path = os.path.join(self.prompts_dir, "image", "styles", style_file)
        style_instr = self._extract_prompt_block(style_path)
        if not base_template:
            return f"Create a child-friendly illustration. Style: {image_style}. Story: {story_text}"
        final_parts = [
            base_template,
            f"ВИЗУАЛЬНЫЙ СТИЛЬ: {image_style}",
            f"ДЕТАЛИ СТИЛЯ: {style_instr}" if style_instr else "",
            f"СЮЖЕТ ДЛЯ ОТРИСОВКИ: {story_text}"
        ]
        return "\n\n".join([p for p in final_parts if p])

    def _map_truth_mode_file(self, mode: TruthMode) -> str:
        mapping = {TruthMode.TRUTH: "TRUTH.md", TruthMode.MYTH: "MYTH.md", TruthMode.FAIRY_TALE: "FAIRY_TALE.md"}
        return mapping.get(mode, "TRUTH.md")

    def _map_text_style_file(self, style: TextStyle) -> str:
        mapping = {TextStyle.GENTLE: "GENTLE.md", TextStyle.EDUCATIONAL: "EDUCATIONAL.md", TextStyle.PLAYFUL: "PLAYFUL.md"}
        return mapping.get(style, "EDUCATIONAL.md")

    def _map_image_style_name(self, style_val: str) -> str:
        from src.models.schemas import ImageStyle
        mapping = {
            ImageStyle.CARTOON.value: "CARTOON",
            ImageStyle.WATERCOLOR.value: "WATERCOLOR",
            ImageStyle.CLAY.value: "CLAY",
            ImageStyle.NIGHT.value: "NIGHT"
        }
        return mapping.get(style_val, "CARTOON")
