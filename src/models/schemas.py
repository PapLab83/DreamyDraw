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
    text: str = ""
    image_path: Optional[str] = None
    questions: List[str] = []
    is_confirmed: bool = False

class GenerationRequest(BaseModel):
    topic: str
    truth_mode: TruthMode = TruthMode.TRUTH
    text_style: TextStyle = TextStyle.GENTLE
    image_style: ImageStyle = ImageStyle.CARTOON
    work_mode: WorkMode = WorkMode.FAST
    count: int = settings.DEFAULT_COUNT

class SessionState(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    request: GenerationRequest
    stories: List[StoryItem] = []
    current_step: int = 0
    is_completed: bool = False
