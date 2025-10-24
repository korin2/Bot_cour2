import os
import logging

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Токены и ключи
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
DEEPSEEK_API_KEY = os.getenv('TG_BOT_APIDEEPSEEK')
DATABASE_URL = os.getenv('DATABASE_URL')

# Проверка обязательных переменных
if not TOKEN:
    raise ValueError("Требуется переменная окружения TELEGRAM_BOT_TOKEN")

if not DATABASE_URL:
    raise ValueError("Требуется переменная окружения DATABASE_URL")

# API URLs
CBR_API_BASE = "https://www.cbr.ru/"
COINGECKO_API_BASE = "https://api.coingecko.com/api/v3/"
DEEPSEEK_API_BASE = "https://api.deepseek.com/v1/"

# Константы
MAX_MESSAGE_LENGTH = 4096
ALERT_CHECK_INTERVAL = 1800  # 30 минут
DAILY_RATES_TIME = "07:00"   # 10:00 МСК = 07:00 UTC

# Поддерживаемые валюты
SUPPORTED_CURRENCIES = ['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CHF', 'CAD', 'AUD', 'TRY', 'KZT']

# Коды валют ЦБ РФ
CBR_CURRENCY_CODES = {
    'R01235': 'USD', 'R01239': 'EUR', 'R01035': 'GBP', 'R01820': 'JPY',
    'R01375': 'CNY', 'R01775': 'CHF', 'R01350': 'CAD', 'R01010': 'AUD',
    'R01700': 'TRY', 'R01335': 'KZT',
}

# Основные криптовалюты
CRYPTO_IDS = [
    'bitcoin', 'ethereum', 'binancecoin', 'ripple', 'cardano',
    'solana', 'polkadot', 'dogecoin', 'tron', 'litecoin'
]

CRYPTO_NAMES = {
    'bitcoin': {'name': 'Bitcoin', 'symbol': 'BTC'},
    'ethereum': {'name': 'Ethereum', 'symbol': 'ETH'},
    'binancecoin': {'name': 'Binance Coin', 'symbol': 'BNB'},
    'ripple': {'name': 'XRP', 'symbol': 'XRP'},
    'cardano': {'name': 'Cardano', 'symbol': 'ADA'},
    'solana': {'name': 'Solana', 'symbol': 'SOL'},
    'polkadot': {'name': 'Polkadot', 'symbol': 'DOT'},
    'dogecoin': {'name': 'Dogecoin', 'symbol': 'DOGE'},
    'tron': {'name': 'TRON', 'symbol': 'TRX'},
    'litecoin': {'name': 'Litecoin', 'symbol': 'LTC'}
}
