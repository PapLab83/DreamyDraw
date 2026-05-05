import shutil
import os
from src.providers.base import BaseImageProvider

class ImageMockProvider(BaseImageProvider):
    def __init__(self, mock_image: str = "assets/mocks/fox_story.png"):
        self.mock_image = mock_image

    def generate_image(self, prompt: str, overlay_text: str, output_path: str) -> str:
        if os.path.exists(self.mock_image):
            shutil.copy(self.mock_image, output_path)
            return output_path
        # Если мок-файла нет, создаем пустой файл для теста
        with open(output_path, "w") as f:
            f.write("mock image data")
        return output_path
