import os
import requests
from dotenv import load_dotenv

def get_models():
    load_dotenv()
    api_key = os.getenv('GPTTUNNEL_API_KEY')
    base_url = 'https://gptunnel.ru/v1/models'
    headers = {'Authorization': f'Bearer {api_key}'}
    try:
        response = requests.get(base_url, headers=headers)
        data = response.json()
        print("Список доступных моделей:")
        for model in data.get('data', []):
            print(f"- {model['id']} ({model.get('title', 'N/A')})")
    except Exception as e:
        print(f"Ошибка при получении моделей: {e}")

if __name__ == '__main__':
    get_models()
