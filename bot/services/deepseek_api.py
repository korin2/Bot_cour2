import requests
import logging

from bot.config import DEEPSEEK_API_KEY, DEEPSEEK_API_BASE

logger = logging.getLogger(__name__)

async def ask_deepseek(prompt: str) -> str:
    """Отправляет запрос к API DeepSeek и возвращает ответ"""
    if not DEEPSEEK_API_KEY:
        return "❌ Функционал ИИ временно недоступен. Отсутствует API ключ."
    
    try:
        url = f"{DEEPSEEK_API_BASE}chat/completions"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}'
        }
        
        system_message = """Ты - универсальный ИИ помощник в телеграм боте. Ты помогаешь пользователям с любыми вопросами."""
        
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2000,
            "stream": False
        }
        
        logger.info(f"Отправка запроса к DeepSeek API: {prompt[:100]}...")
        
        response = requests.post(url, headers=headers, json=data, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            answer = result['choices'][0]['message']['content']
            logger.info("Успешно получен ответ от DeepSeek API")
            return answer
        elif response.status_code == 402:
            logger.error("Недостаточно средств на счету DeepSeek API")
            return "❌ Функционал ИИ временно недоступен. Недостаточно средств на API аккаунте."
        elif response.status_code == 401:
            logger.error("Неверный API ключ DeepSeek")
            return "❌ Ошибка аутентификации API. Проверьте API ключ."
        elif response.status_code == 429:
            logger.error("Превышен лимит запросов к DeepSeek API")
            return "⏰ Превышен лимит запросов. Попробуйте позже."
        else:
            error_msg = f"Ошибка API DeepSeek: {response.status_code} - {response.text}"
            logger.error(error_msg)
            return f"❌ Временная ошибка сервиса ИИ. Попробуйте позже."
            
    except requests.exceptions.Timeout:
        logger.error("Таймаут при запросе к DeepSeek API")
        return "⏰ ИИ не успел обработать запрос. Попробуйте позже."
    except requests.exceptions.RequestException as e:
        logger.error(f"Сетевая ошибка при запросе к DeepSeek API: {e}")
        return "❌ Произошла сетевая ошибка. Проверьте подключение к интернету."
    except Exception as e:
        logger.error(f"Неожиданная ошибка при работе с DeepSeek API: {e}")
        return "❌ Произошла непредвиденная ошибка. Попробуйте позже."
