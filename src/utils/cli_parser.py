import argparse
import re
from src.models.schemas import TruthMode, TextStyle, ImageStyle, WorkMode
from src.config.settings import settings

def parse_count(topic: str) -> int:
    # Простой поиск чисел в строке
    match = re.search(r'\d+', topic)
    if match:
        return int(match.group())
    return settings.DEFAULT_COUNT

def get_cli_parser():
    parser = argparse.ArgumentParser(
        description="DreamyDraw CLI Prototype"
    )

    parser.add_argument(
        "topic",
        nargs="?",
        help="Тема истории (например, 'лиса'). Не требуется при --session.",
    )
    
    parser.add_argument(
        "--truth", choices=[m.value for m in TruthMode],
        default=TruthMode.TRUTH.value, help="Режим правдивости"
    )
    
    parser.add_argument(
        "--text-style", choices=[s.value for s in TextStyle],
        default=TextStyle.GENTLE.value, help="Стиль текста"
    )
    
    parser.add_argument(
        "--image-style", choices=[s.value for s in ImageStyle],
        default=ImageStyle.CARTOON.value, help="Стиль картинки"
    )
    
    parser.add_argument(
        "--mode", choices=[m.value for m in WorkMode],
        default=WorkMode.FAST.value, help="Режим работы"
    )
    
    parser.add_argument(
        "--count", type=int, help="Количество иллюстраций (перекрывает значение из темы)"
    )
    
    parser.add_argument(
        "--session", help="ID существующей сессии для продолжения"
    )
    
    return parser
