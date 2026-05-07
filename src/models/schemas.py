from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field
import uuid

from src.config.settings import settings

class TruthMode(str, Enum):
    TRUTH = "Правда"
    MYTH = "Миф"
    FAIRY_TALE = "Сказка"

class TextStyle(str, Enum):
    GENTLE = "Ласковый"
    EDUCATIONAL = "Познавательный"
    PLAYFUL = "Игровой"

class ImageStyle(str, Enum):
    CARTOON = "Мультяшный"
    WATERCOLOR = "Акварельный"
    CLAY = "Пластилиновый"
    NIGHT = "Ночной/тихий"

class WorkMode(str, Enum):
    FAST = "fast"
    CHECK = "check"

class StoryItem(BaseModel):
    index: int
    sub_topic: str = ""  # Конкретный аспект из плана серии
    text: str = ""
    image_path: Optional[str] = None
    questions: List[str] = []
    is_confirmed: bool = False
    validation_notes: List[str] = []  # Замечания валидатора
    retry_count: int = 0  # Счетчик попыток исправления

class Idea(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    summary: str
    child_index: float = 0.0  # Скоринг безопасности/уместности
    normalized_weight: float = 0.0  # Вес для выборки
    is_selected: bool = False

class GenerationRequest(BaseModel):
    topic: str
    truth_mode: TruthMode = TruthMode.TRUTH
    text_style: TextStyle = TextStyle.EDUCATIONAL
    image_style: ImageStyle = ImageStyle.CARTOON
    work_mode: WorkMode = WorkMode.FAST
    count: int = settings.DEFAULT_COUNT

class SessionState(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request: GenerationRequest
    
    # План и контекст
    series_plan: List[str] = []  # Список подтем для каждого шага
    global_context: str = ""  # Описание героя и мира
    
    # Пул идей для текущего шага
    ideas_pool: List[Idea] = []
    
    # Результаты
    stories: List[StoryItem] = []
    current_step: int = 0
    is_completed: bool = False
    
    # Хранилище одобренных тем (чистовик) - словарь {index: {"theme": str, "content": str}}
    approved_plan_items: dict = {}
    
    # Полный текущий план с описаниями (черновик)
    full_plan_items: List[dict] = []
    
    # Статус текущего шага пайплайна
    current_node: str = "start"  # Имя текущего узла для восстановления
    user_feedback: Optional[str] = None  # Обратная связь от пользователя
    validator_feedback: str = "{}"  # Результаты последней валидации (JSON string)
    approved_indices: List[int] = []  # Список индексов одобренных тем
