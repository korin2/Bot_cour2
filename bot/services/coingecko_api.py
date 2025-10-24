import requests
import logging
from datetime import datetime

from bot.config import COINGECKO_API_BASE, CRYPTO_IDS, CRYPTO_NAMES
from bot.utils.helpers import safe_float_convert

logger = logging.getLogger(__name__)

def get_crypto_rates():
    """Получает курсы криптовалют через CoinGecko API"""
    try:
        url = f"{COINGECKO_API_BASE}simple/price"
        params = {
            'ids': ','.join(CRYPTO_IDS),
            'vs_currencies': 'rub,usd',
            'include_24hr_change': 'true',
            'include_last_updated_at': 'true'
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        logger.info(f"Запрос к CoinGecko API: {url}")
        
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"Ошибка CoinGecko API: {response.status_code}")
            return None
            
        data = response.json()
        logger.info(f"Получены данные от CoinGecko: {type(data)}")
        
        if not isinstance(data, dict):
            logger.error(f"Неправильный формат ответа: ожидался dict, получен {type(data)}")
            return None
            
        crypto_rates = {}
        valid_count = 0
        
        for crypto_id, info in CRYPTO_NAMES.items():
            if crypto_id in data:
                crypto_data = data[crypto_id]
                
                if not isinstance(crypto_data, dict):
                    logger.warning(f"Данные для {crypto_id} не словарь: {type(crypto_data)}")
                    continue
                
                price_rub = crypto_data.get('rub')
                price_usd = crypto_data.get('usd')
                change_24h = crypto_data.get('rub_24h_change') or crypto_data.get('usd_24h_change') or 0
                
                if price_rub is None or price_usd is None:
                    logger.warning(f"Отсутствуют цены для {crypto_id}: RUB={price_rub}, USD={price_usd}")
                    continue
                
                try:
                    price_rub = safe_float_convert(price_rub)
                    price_usd = safe_float_convert(price_usd)
                    change_24h = safe_float_convert(change_24h)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Ошибка преобразования данных для {crypto_id}: {e}")
                    continue
                
                crypto_rates[crypto_id] = {
                    'name': info['name'],
                    'symbol': info['symbol'],
                    'price_rub': price_rub,
                    'price_usd': price_usd,
                    'change_24h': change_24h,
                    'last_updated': crypto_data.get('last_updated_at', 0)
                }
                valid_count += 1
            else:
                logger.warning(f"Криптовалюта {crypto_id} не найдена в ответе API")
        
        logger.info(f"Успешно обработано {valid_count} криптовалют")
        
        if crypto_rates:
            crypto_rates['update_time'] = datetime.now().strftime('%d.%m.%Y %H:%M')
            crypto_rates['source'] = 'coingecko'
            return crypto_rates
        else:
            logger.error("Не найдено валидных данных по криптовалютам в ответе API")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Сетевая ошибка при получении курсов криптовалют: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении курсов криптовалют: {e}")
        return None

def get_crypto_rates_fallback():
    """Резервная функция для получения курсов криптовалют (демо-данные)"""
    try:
        crypto_rates = {
            'bitcoin': {
                'name': 'Bitcoin',
                'symbol': 'BTC',
                'price_rub': 4500000.0,
                'price_usd': 50000.0,
                'change_24h': 2.5,
                'last_updated': datetime.now().timestamp()
            },
            'ethereum': {
                'name': 'Ethereum', 
                'symbol': 'ETH',
                'price_rub': 300000.0,
                'price_usd': 3300.0,
                'change_24h': 1.2,
                'last_updated': datetime.now().timestamp()
            },
            'binancecoin': {
                'name': 'Binance Coin',
                'symbol': 'BNB', 
                'price_rub': 35000.0,
                'price_usd': 380.0,
                'change_24h': -0.5,
                'last_updated': datetime.now().timestamp()
            }
        }
        
        crypto_rates['update_time'] = datetime.now().strftime('%d.%m.%Y %H:%M')
        crypto_rates['source'] = 'demo_fallback'
        
        logger.info("Используются демо-данные криптовалют")
        return crypto_rates
        
    except Exception as e:
        logger.error(f"Ошибка в fallback функции криптовалют: {e}")
        return None
