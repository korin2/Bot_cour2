import os
import logging

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токены и API ключи
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("Требуется переменная окружения TELEGRAM_BOT_TOKEN")

DEEPSEEK_API_KEY = os.getenv('TG_BOT_APIDEEPSEEK')

# API ключ погоды
WEATHER_API_KEY = os.getenv('API_weather')
if not WEATHER_API_KEY:
    logger.warning("API ключ погоды не найден, будут использоваться демо-данные")

# API URLs
CBR_API_BASE = "https://www.cbr.ru/"
COINGECKO_API_BASE = "https://api.coingecko.com/api/v3/"
DEEPSEEK_API_BASE = "https://api.deepseek.com/v1/"
OPENWEATHER_API_BASE = "http://api.openweathermap.org/data/2.5/"

# Поддерживаемые валюты
SUPPORTED_CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CHF', 'CAD', 'AUD', 'TRY', 'KZT']

# Настройки погоды
WEATHER_CITY = "Moscow"
