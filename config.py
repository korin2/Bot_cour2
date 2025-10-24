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

# API URLs
CBR_API_BASE = "https://www.cbr.ru/"
COINGECKO_API_BASE = "https://api.coingecko.com/api/v3/"
DEEPSEEK_API_BASE = "https://api.deepseek.com/v1/"

# Поддерживаемые валюты
SUPPORTED_CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CHF', 'CAD', 'AUD', 'TRY', 'KZT']
