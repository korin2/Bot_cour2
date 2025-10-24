import requests
import xml.etree.ElementTree as ET
import json
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import logging
from config import CBR_API_BASE, COINGECKO_API_BASE, DEEPSEEK_API_BASE, DEEPSEEK_API_KEY, logger
from telegram.ext import ContextTypes

# =============================================================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С КУРСАМИ ВАЛЮТ ЦБ РФ
# =============================================================================

def get_currency_rates_for_date(date_req):
    """Получает курсы валют на определенную дату"""
    try:
        url = f"{CBR_API_BASE}scripts/XML_daily.asp"
        params = {'date_req': date_req}
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return None, None
        
        root = ET.fromstring(response.content)
        cbr_date = root.get('Date', '')
        
        rates = {}
        currency_codes = {
            'R01235': 'USD',  'R01239': 'EUR',  'R01035': 'GBP',  'R01820': 'JPY',
            'R01375': 'CNY',  'R01775': 'CHF',  'R01350': 'CAD',  'R01010': 'AUD',
            'R01700': 'TRY',  'R01335': 'KZT',
        }
        
        for valute in root.findall('Valute'):
            valute_id = valute.get('ID')
            if valute_id in currency_codes:
                currency_code = currency_codes[valute_id]
                name = valute.find('Name').text
                value = float(valute.find('Value').text.replace(',', '.'))
                nominal = int(valute.find('Nominal').text)
                
                if nominal > 1:
                    value = value / nominal
                
                rates[currency_code] = {
                    'value': value,
                    'name': name,
                    'nominal': nominal
                }
        
        return rates, cbr_date
        
    except Exception as e:
        logger.error(f"Ошибка при получении курсов на дату {date_req}: {e}")
        return None, None

def get_currency_rates_with_tomorrow():
    """Получает курсы валют на сегодня и завтра (если доступно)"""
    try:
        today = datetime.now()
        tomorrow = today + timedelta(days=1)
        
        # Форматируем даты для запроса
        date_today = today.strftime('%d/%m/%Y')
        date_tomorrow = tomorrow.strftime('%d/%m/%Y')
        
        # Получаем курсы на сегодня
        rates_today, date_today_str = get_currency_rates_for_date(date_today)
        if not rates_today:
            return {}, 'неизвестная дата', None, None
        
        # Пытаемся получить курсы на завтра
        rates_tomorrow, date_tomorrow_str = get_currency_rates_for_date(date_tomorrow)
        
        # Если курсы на завтра не доступны, возвращаем только сегодняшние
        if not rates_tomorrow:
            return rates_today, date_today_str, None, None
        
        # Рассчитываем изменения для завтрашних курсов
        changes = {}
        for currency, today_data in rates_today.items():
            if currency in rates_tomorrow:
                today_value = today_data['value']
                tomorrow_value = rates_tomorrow[currency]['value']
                change = tomorrow_value - today_value
                change_percent = (change / today_value) * 100 if today_value > 0 else 0
                
                changes[currency] = {
                    'change': change,
                    'change_percent': change_percent
                }
        
        return rates_today, date_today_str, rates_tomorrow, changes
        
    except Exception as e:
        logger.error(f"Ошибка при получении курсов с завтрашними данными: {e}")
        return {}, 'неизвестная дата', None, None

def format_currency_rates_message(rates_today: dict, date_today: str, 
                                rates_tomorrow: dict = None, changes: dict = None) -> str:
    """Форматирует сообщение с курсами валют на сегодня и завтра"""
    if not rates_today:
        return "❌ Не удалось получить курсы валют от ЦБ РФ."
    
    message = f"💱 <b>КУРСЫ ВАЛЮТ ЦБ РФ</b>\n"
    message += f"📅 <i>на {date_today}</i>\n\n"
    
    # Основные валюты (доллар, евро)
    main_currencies = ['USD', 'EUR']
    for currency in main_currencies:
        if currency in rates_today:
            data = rates_today[currency]
            
            message += f"💵 <b>{data['name']}</b> ({currency}):\n"
            message += f"   <b>{data['value']:.2f} руб.</b>\n"
            
            # Если есть данные на завтра, показываем прогноз
            if rates_tomorrow and currency in rates_tomorrow and currency in changes:
                tomorrow_data = rates_tomorrow[currency]
                change_info = changes[currency]
                change_icon = "📈" if change_info['change'] > 0 else "📉" if change_info['change'] < 0 else "➡️"
                
                message += f"   <i>Завтра: {tomorrow_data['value']:.2f} руб. {change_icon}</i>\n"
                message += f"   <i>Изменение: {change_info['change']:+.2f} руб. ({change_info['change_percent']:+.2f}%)</i>\n"
            
            message += "\n"
    
    # Другие валюты
    other_currencies = [curr for curr in rates_today.keys() if curr not in main_currencies]
    if other_currencies:
        message += "🌍 <b>Другие валюты:</b>\n"
        
        for currency in other_currencies:
            data = rates_today[currency]
            
            # Для JPY показываем за 100 единиц
            if currency == 'JPY':
                display_value = data['value'] * 100
                currency_text = f"   {data['name']} ({currency}): <b>{display_value:.2f} руб.</b>"
            else:
                currency_text = f"   {data['name']} ({currency}): <b>{data['value']:.2f} руб.</b>"
            
            # Добавляем индикатор изменения для завтра, если есть
            if rates_tomorrow and currency in rates_tomorrow and currency in changes:
                change_info = changes[currency]
                change_icon = "📈" if change_info['change'] > 0 else "📉" if change_info['change'] < 0 else "➡️"
                currency_text += f" {change_icon}"
            
            message += currency_text + "\n"
    
    # Информация о доступности завтрашних курсов
    if rates_tomorrow:
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y')
        message += f"\n📊 <i>Курсы на завтра ({tomorrow_date}) опубликованы ЦБ РФ</i>"
    else:
        message += f"\n💡 <i>Курсы на завтра будут опубликованы ЦБ РФ позже</i>"
    
    message += f"\n\n💡 <i>Официальные курсы ЦБ РФ с прогнозом на завтра</i>"
    return message

# =============================================================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С КЛЮЧЕВОЙ СТАВКОЙ ЦБ РФ
# =============================================================================

def get_key_rate():
    """Получает ключевую ставку ЦБ РФ с использованием нескольких методов"""
    
    # Сначала пробуем парсинг HTML с правильными заголовками
    key_rate_data = get_key_rate_html()
    if key_rate_data:
        return key_rate_data
    
    # Если не получилось, пробуем API
    logger.info("Парсинг HTML не удался, пробуем API...")
    key_rate_data = get_key_rate_api()
    if key_rate_data:
        return key_rate_data
    
    # Если оба метода не сработали, возвращаем демо-данные
    logger.warning("Не удалось получить актуальную ключевую ставку, используем демо-данные")
    return get_key_rate_demo()

def get_key_rate_html():
    """Парсинг ключевой ставки с сайта ЦБ РФ"""
    try:
        url = "https://cbr.ru/hd_base/KeyRate/"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.cbr.ru/',
            'Connection': 'keep-alive',
        }
        
        # Добавляем задержку чтобы не выглядеть как бот
        import time
        time.sleep(1)
        
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code == 403:
            logger.error("Доступ запрещен (403) при парсинге HTML")
            return None
        elif response.status_code != 200:
            logger.error(f"Ошибка HTTP {response.status_code} при парсинге HTML")
            return None
            
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Ищем таблицу с ключевыми ставками
        table = soup.find('table', class_='data')
        if table:
            rows = table.find_all('tr')
            for i in range(1, min(len(rows), 10)):  # Проверяем первые 10 строк
                cells = rows[i].find_all('td')
                if len(cells) >= 2:
                    date_str = cells[0].get_text(strip=True)
                    rate_str = cells[1].get_text(strip=True).replace(',', '.')
                    
                    try:
                        date_obj = datetime.strptime(date_str, '%d.%m.%Y')
                        # Проверяем что дата не в будущем
                        if date_obj <= datetime.now():
                            rate_value = float(rate_str)
                            
                            return {
                                'rate': rate_value,
                                'date': date_obj.strftime('%d.%m.%Y'),
                                'is_current': True,
                                'source': 'cbr_parsed'
                            }
                    except ValueError:
                        continue
        
        return None
            
    except Exception as e:
        logger.error(f"Ошибка при парсинге HTML ключевой ставки: {e}")
        return None

def get_key_rate_api():
    """Получает ключевую ставку через API ЦБ РФ"""
    try:
        # Альтернативный URL для ключевой ставки
        url = "https://www.cbr.ru/hd_base/KeyRate/?UniDbQuery.Posted=True&UniDbQuery.From=01.01.2020&UniDbQuery.To=31.12.2025"
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            table = soup.find('table', class_='data')
            
            if table:
                rows = table.find_all('tr')
                for i in range(1, min(len(rows), 5)):  # Первые 5 строк
                    cells = rows[i].find_all('td')
                    if len(cells) >= 2:
                        date_str = cells[0].get_text(strip=True)
                        rate_str = cells[1].get_text(strip=True).replace(',', '.')
                        
                        try:
                            date_obj = datetime.strptime(date_str, '%d.%m.%Y')
                            if date_obj <= datetime.now():
                                rate_value = float(rate_str)
                                
                                return {
                                    'rate': rate_value,
                                    'date': date_str,
                                    'is_current': True,
                                    'source': 'cbr_api'
                                }
                        except ValueError:
                            continue
        return None
            
    except Exception as e:
        logger.error(f"Ошибка при получении ключевой ставки через API: {e}")
        return None

def get_key_rate_demo():
    """Возвращает демо-данные ключевой ставки"""
    return {
        'rate': 16.0,  # Примерное значение
        'date': datetime.now().strftime('%d.%m.%Y'),
        'is_current': True,
        'source': 'demo'
    }

def format_key_rate_message(key_rate_data: dict) -> str:
    """Форматирует сообщение с ключевой ставкой"""
    if not key_rate_data:
        return "❌ Не удалось получить данные по ключевой ставке от ЦБ РФ."
    
    rate = key_rate_data['rate']
    source = key_rate_data.get('source', 'unknown')
    
    message = f"💎 <b>КЛЮЧЕВАЯ СТАВКА ЦБ РФ</b>\n\n"
    message += f"<b>Текущее значение:</b> {rate:.2f}%\n"
    message += f"\n<b>Дата установления:</b> {key_rate_data.get('date', 'неизвестно')}\n\n"
    message += "💡 <i>Ключевая ставка - это основная процентная ставка ЦБ РФ,\n"
    message += "которая влияет на кредиты, депозиты и экономику в целом</i>"
    
    # Добавляем информацию об источнике данных
    if source == 'cbr_parsed':
        message += f"\n\n✅ <i>Данные получены с официального сайта ЦБ РФ</i>"
    elif source == 'cbr_api':
        message += f"\n\n✅ <i>Данные получены через API ЦБ РФ</i>"
    elif source == 'demo':
        message += f"\n\n⚠️ <i>Используются демонстрационные данные (ошибка получения реальных)</i>"
    
    return message

# =============================================================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С КРИПТОВАЛЮТАМИ
# =============================================================================

def get_crypto_rates():
    """Получает курсы криптовалют через CoinGecko API"""
    try:
        # Основные криптовалюты для отслеживания
        crypto_ids = [
            'bitcoin', 'ethereum', 'binancecoin', 'ripple', 'cardano',
            'solana', 'polkadot', 'dogecoin', 'tron', 'litecoin'
        ]
        
        url = f"{COINGECKO_API_BASE}simple/price"
        params = {
            'ids': ','.join(crypto_ids),
            'vs_currencies': 'rub,usd',
            'include_24hr_change': 'true',
            'include_last_updated_at': 'true'
        }
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json'
        }
        
        logger.info(f"Запрос к CoinGecko API: {url}")
        logger.info(f"Параметры: {params}")
        
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"Ошибка CoinGecko API: {response.status_code}")
            logger.error(f"Текст ответа: {response.text}")
            return None
            
        data = response.json()
        logger.info(f"Получены данные от CoinGecko: {type(data)}")
        
        # Проверяем структуру ответа
        if not isinstance(data, dict):
            logger.error(f"Неправильный формат ответа: ожидался dict, получен {type(data)}")
            return None
            
        # Маппинг названий криптовалют
        crypto_names = {
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
        
        crypto_rates = {}
        valid_count = 0
        
        for crypto_id, info in crypto_names.items():
            if crypto_id in data:
                crypto_data = data[crypto_id]
                
                # Проверяем что crypto_data - словарь
                if not isinstance(crypto_data, dict):
                    logger.warning(f"Данные для {crypto_id} не словарь: {type(crypto_data)}")
                    continue
                
                # Получаем цены с проверкой
                price_rub = crypto_data.get('rub')
                price_usd = crypto_data.get('usd')
                
                # Получаем изменение цены (может быть под разными ключами)
                change_24h = crypto_data.get('rub_24h_change') or crypto_data.get('usd_24h_change') or 0
                
                # Проверяем что цены есть и они числа
                if price_rub is None or price_usd is None:
                    logger.warning(f"Отсутствуют цены для {crypto_id}: RUB={price_rub}, USD={price_usd}")
                    continue
                
                try:
                    price_rub = float(price_rub)
                    price_usd = float(price_usd)
                    change_24h = float(change_24h) if change_24h is not None else 0
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
    except json.JSONDecodeError as e:
        logger.error(f"Ошибка парсинга JSON от CoinGecko: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении курсов криптовалют: {e}")
        return None

def get_crypto_rates_fallback():
    """Резервная функция для получения курсов криптовалют (демо-данные)"""
    try:
        # Демо-данные на случай недоступности API
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
            },
            'ripple': {
                'name': 'XRP',
                'symbol': 'XRP',
                'price_rub': 60.0,
                'price_usd': 0.65,
                'change_24h': 0.8,
                'last_updated': datetime.now().timestamp()
            },
            'cardano': {
                'name': 'Cardano',
                'symbol': 'ADA',
                'price_rub': 45.0,
                'price_usd': 0.48,
                'change_24h': -1.2,
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

def format_crypto_rates_message(crypto_rates: dict) -> str:
    """Форматирует сообщение с курсами криптовалют"""
    if not crypto_rates:
        return "❌ Не удалось получить курсы криптовалют от CoinGecko API."
    
    message = f"₿ <b>КУРСЫ КРИПТОВАЛЮТ</b>\n\n"
    
    # Основные криптовалюты (первые 5)
    main_cryptos = ['bitcoin', 'ethereum', 'binancecoin', 'ripple', 'cardano']
    
    for crypto_id in main_cryptos:
        if crypto_id in crypto_rates:
            data = crypto_rates[crypto_id]
            
            # Безопасное получение данных
            name = data.get('name', 'N/A')
            symbol = data.get('symbol', 'N/A')
            price_rub = data.get('price_rub', 0)
            price_usd = data.get('price_usd', 0)
            change_24h = data.get('change_24h', 0)
            
            # Проверяем типы данных
            try:
                price_rub = float(price_rub)
                price_usd = float(price_usd)
                change_24h = float(change_24h)
            except (TypeError, ValueError):
                continue
            
            change_icon = "📈" if change_24h > 0 else "📉" if change_24h < 0 else "➡️"
            
            message += (
                f"<b>{name} ({symbol})</b>\n"
                f"   💰 <b>{price_rub:,.0f} руб.</b>\n"
                f"   💵 {price_usd:,.2f} $\n"
                f"   {change_icon} <i>{change_24h:+.2f}% (24ч)</i>\n\n"
            )
    
    # Остальные криптовалюты
    other_cryptos = [crypto_id for crypto_id in crypto_rates.keys() 
                    if crypto_id not in main_cryptos and crypto_id not in ['update_time', 'source']]
    
    if other_cryptos:
        message += "🔹 <b>Другие криптовалюты:</b>\n"
        
        for crypto_id in other_cryptos:
            data = crypto_rates[crypto_id]
            symbol = data.get('symbol', 'N/A')
            price_rub = data.get('price_rub', 0)
            change_24h = data.get('change_24h', 0)
            
            try:
                price_rub = float(price_rub)
                change_24h = float(change_24h)
            except (TypeError, ValueError):
                continue
            
            change_icon = "📈" if change_24h > 0 else "📉" if change_24h < 0 else "➡️"
            
            message += (
                f"   <b>{symbol}</b>: {price_rub:,.0f} руб. {change_icon}\n"
            )
    
    message += f"\n<i>Обновлено: {crypto_rates.get('update_time', 'неизвестно')}</i>\n\n"
    message += "💡 <i>Данные предоставлены CoinGecko API</i>"
    
    if crypto_rates.get('source') == 'coingecko':
        message += f"\n\n✅ <i>Официальные данные CoinGecko</i>"
    
    return message

# =============================================================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ИИ DEEPSEEK
# =============================================================================

async def ask_deepseek(prompt: str, context: ContextTypes.DEFAULT_TYPE = None) -> str:
    """Отправляет запрос к API DeepSeek и возвращает ответ"""
    if not DEEPSEEK_API_KEY:
        return "❌ Функционал ИИ временно недоступен. Отсутствует API ключ."
    
    try:
        url = f"{DEEPSEEK_API_BASE}chat/completions"
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}'
        }
        
        # УНИВЕРСАЛЬНЫЙ ПРОМПТ ДЛЯ ЛЮБЫХ ВОПРОСОВ
        system_message = """Ты - универсальный ИИ помощник в телеграм боте. Ты помогаешь пользователям с любыми вопросами, включая:

- 💰 Финансы: курсы валют, инвестиции, криптовалюты
- 📊 Технологии: программирование, IT, разработка
- 🎓 Образование: обучение, науки, исследования
- 🎨 Творчество: искусство, музыка, литература
- 🏥 Здоровье: медицина, спорт, образ жизни
- 🌍 Путешествия: страны, культура, языки
- 🔧 Советы: решение проблем, рекомендации
- 💬 Общение: поддержка, мотивация

Отвечай подробно, информативно и помогающе. Будь дружелюбным и поддерживающим собеседником."""
        
        data = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7,
            "max_tokens": 2000,  # Увеличим лимит токенов для более подробных ответов
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
            return "❌ Функционал ИИ временно недоступен. Недостаточно средств на API аккаунте. Обратитесь к администратору."
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

# Добавьте в конец services.py
async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет активные уведомления и отправляет уведомления при срабатывании"""
    try:
        from db import get_all_active_alerts, deactivate_alert
        
        alerts = await get_all_active_alerts()
        if not alerts:
            return
        
        rates_today, _, _, _ = get_currency_rates_with_tomorrow()
        if not rates_today:
            return
        
        for alert in alerts:
            user_id = alert['user_id']
            from_curr = alert['from_currency']
            threshold = alert['threshold']
            direction = alert['direction']
            alert_id = alert['id']
            
            if from_curr in rates_today:
                current_rate = rates_today[from_curr]['value']
                triggered = False
                
                if direction == 'above' and current_rate >= threshold:
                    triggered = True
                elif direction == 'below' and current_rate <= threshold:
                    triggered = True
                
                if triggered:
                    message = (
                        f"🔔 <b>УВЕДОМЛЕНИЕ СРАБОТАЛО!</b>\n\n"
                        f"💱 <b>Пара:</b> {from_curr}/RUB\n"
                        f"🎯 <b>Порог:</b> {threshold} руб.\n"
                        f"💹 <b>Текущий курс:</b> {current_rate:.2f} руб.\n"
                        f"📊 <b>Условие:</b> курс <b>{'выше' if direction == 'above' else 'ниже'}</b> {threshold} руб.\n\n"
                        f"✅ <i>Уведомление выполнено и удалено.</i>"
                    )
                    
                    await context.bot.send_message(
                        chat_id=user_id, 
                        text=message, 
                        parse_mode='HTML'
                    )
                    await deactivate_alert(alert_id)
                    
    except Exception as e:
        logger.error(f"Ошибка при проверке уведомлений: {e}")

async def send_daily_rates(context: ContextTypes.DEFAULT_TYPE):
    """Ежедневная рассылка основных финансовых данных"""
    try:
        from db import get_all_users
        
        users = await get_all_users()
        if not users:
            return
        
        # Формируем сводное сообщение
        message = "🌅 <b>ЕЖЕДНЕВНАЯ ФИНАНСОВАЯ СВОДКА</b>\n\n"
        
        # Добавляем курсы валют
        rates_today, date_today, _, _ = get_currency_rates_with_tomorrow()
        if rates_today:
            message += "💱 <b>Основные курсы ЦБ РФ:</b>\n"
            for currency in ['USD', 'EUR']:
                if currency in rates_today:
                    rate = rates_today[currency]['value']
                    message += f"   {currency}: <b>{rate:.2f} руб.</b>\n"
            message += "\n"
        
        # Добавляем ключевую ставку
        key_rate_data = get_key_rate()
        if key_rate_data:
            message += f"💎 <b>Ключевая ставка:</b> {key_rate_data['rate']:.2f}%\n\n"
        
        message += "💡 Используйте команды бота для подробной информации"
        
        # Отправляем всем пользователям
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user['user_id'],
                    text=message,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Ошибка отправки рассылки пользователю {user['user_id']}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка при ежедневной рассылке: {e}")

async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет активные уведомления и отправляет уведомления при срабатывании"""
    try:
        from db import get_all_active_alerts, deactivate_alert
        
        alerts = await get_all_active_alerts()
        if not alerts:
            return
        
        rates_today, _, _, _ = get_currency_rates_with_tomorrow()
        if not rates_today:
            return
        
        for alert in alerts:
            user_id = alert['user_id']
            from_curr = alert['from_currency']
            threshold = alert['threshold']
            direction = alert['direction']
            alert_id = alert['id']
            
            if from_curr in rates_today:
                current_rate = rates_today[from_curr]['value']
                triggered = False
                
                if direction == 'above' and current_rate >= threshold:
                    triggered = True
                elif direction == 'below' and current_rate <= threshold:
                    triggered = True
                
                if triggered:
                    message = (
                        f"🔔 <b>УВЕДОМЛЕНИЕ СРАБОТАЛО!</b>\n\n"
                        f"💱 <b>Пара:</b> {from_curr}/RUB\n"
                        f"🎯 <b>Порог:</b> {threshold} руб.\n"
                        f"💹 <b>Текущий курс:</b> {current_rate:.2f} руб.\n"
                        f"📊 <b>Условие:</b> курс <b>{'выше' if direction == 'above' else 'ниже'}</b> {threshold} руб.\n\n"
                        f"✅ <i>Уведомление выполнено и удалено.</i>"
                    )
                    
                    await context.bot.send_message(
                        chat_id=user_id, 
                        text=message, 
                        parse_mode='HTML'
                    )
                    await deactivate_alert(alert_id)
                    
    except Exception as e:
        logger.error(f"Ошибка при проверке уведомлений: {e}")

async def send_daily_rates(context: ContextTypes.DEFAULT_TYPE):
    """Ежедневная рассылка основных финансовых данных"""
    try:
        from db import get_all_users
        
        users = await get_all_users()
        if not users:
            return
        
        # Формируем сводное сообщение
        message = "🌅 <b>ЕЖЕДНЕВНАЯ ФИНАНСОВАЯ СВОДКА</b>\n\n"
        
        # Добавляем курсы валют
        rates_today, date_today, _, _ = get_currency_rates_with_tomorrow()
        if rates_today:
            message += "💱 <b>Основные курсы ЦБ РФ:</b>\n"
            for currency in ['USD', 'EUR']:
                if currency in rates_today:
                    rate = rates_today[currency]['value']
                    message += f"   {currency}: <b>{rate:.2f} руб.</b>\n"
            message += "\n"
        
        # Добавляем ключевую ставку
        key_rate_data = get_key_rate()
        if key_rate_data:
            message += f"💎 <b>Ключевая ставка:</b> {key_rate_data['rate']:.2f}%\n\n"
        
        message += "💡 Используйте команды бота для подробной информации"
        
        # Отправляем всем пользователям
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user['user_id'],
                    text=message,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Ошибка отправки рассылки пользователю {user['user_id']}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка при ежедневной рассылке: {e}")

async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    """Проверяет активные уведомления и отправляет уведомления при срабатывании"""
    try:
        from db import get_all_active_alerts, deactivate_alert
        
        alerts = await get_all_active_alerts()
        if not alerts:
            return
        
        rates_today, _, _, _ = get_currency_rates_with_tomorrow()
        if not rates_today:
            return
        
        for alert in alerts:
            user_id = alert['user_id']
            from_curr = alert['from_currency']
            threshold = alert['threshold']
            direction = alert['direction']
            alert_id = alert['id']
            
            if from_curr in rates_today:
                current_rate = rates_today[from_curr]['value']
                triggered = False
                
                if direction == 'above' and current_rate >= threshold:
                    triggered = True
                elif direction == 'below' and current_rate <= threshold:
                    triggered = True
                
                if triggered:
                    message = (
                        f"🔔 <b>УВЕДОМЛЕНИЕ СРАБОТАЛО!</b>\n\n"
                        f"💱 <b>Пара:</b> {from_curr}/RUB\n"
                        f"🎯 <b>Порог:</b> {threshold} руб.\n"
                        f"💹 <b>Текущий курс:</b> {current_rate:.2f} руб.\n"
                        f"📊 <b>Условие:</b> курс <b>{'выше' if direction == 'above' else 'ниже'}</b> {threshold} руб.\n\n"
                        f"✅ <i>Уведомление выполнено и удалено.</i>"
                    )
                    
                    await context.bot.send_message(
                        chat_id=user_id, 
                        text=message, 
                        parse_mode='HTML'
                    )
                    await deactivate_alert(alert_id)
                    
    except Exception as e:
        logger.error(f"Ошибка при проверке уведомлений: {e}")

async def send_daily_rates(context: ContextTypes.DEFAULT_TYPE):
    """Ежедневная рассылка основных финансовых данных"""
    try:
        from db import get_all_users
        
        users = await get_all_users()
        if not users:
            return
        
        # Формируем сводное сообщение
        message = "🌅 <b>ЕЖЕДНЕВНАЯ ФИНАНСОВАЯ СВОДКА</b>\n\n"
        
        # Добавляем курсы валют
        rates_today, date_today, _, _ = get_currency_rates_with_tomorrow()
        if rates_today:
            message += "💱 <b>Основные курсы ЦБ РФ:</b>\n"
            for currency in ['USD', 'EUR']:
                if currency in rates_today:
                    rate = rates_today[currency]['value']
                    message += f"   {currency}: <b>{rate:.2f} руб.</b>\n"
            message += "\n"
        
        # Добавляем ключевую ставку
        key_rate_data = get_key_rate()
        if key_rate_data:
            message += f"💎 <b>Ключевая ставка:</b> {key_rate_data['rate']:.2f}%\n\n"
        
        message += "💡 Используйте команды бота для подробной информации"
        
        # Отправляем всем пользователям
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user['user_id'],
                    text=message,
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.error(f"Ошибка отправки рассылки пользователю {user['user_id']}: {e}")
                
    except Exception as e:
        logger.error(f"Ошибка при ежедневной рассылке: {e}")


# =============================================================================
# ФУНКЦИИ ДЛЯ РАБОТЫ С ПОГОДОЙ
# =============================================================================

def get_weather_moscow():
    """Получает текущую погоду в Москве через OpenWeatherMap API"""
    try:
        from config import WEATHER_API_KEY
        
        # Если API ключ не установлен, используем демо-данные
        if not WEATHER_API_KEY or WEATHER_API_KEY == 'demo_key_12345':
            logger.warning("API ключ погоды не настроен, используем демо-данные")
            return get_weather_demo()
        
        CITY = "Moscow"
        URL = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
        
        logger.info(f"Запрос погоды для города: {CITY}")
        response = requests.get(URL, timeout=10)
        
        if response.status_code == 401:
            logger.error("Невалидный API ключ OpenWeatherMap")
            return get_weather_demo()
        elif response.status_code == 429:
            logger.error("Превышен лимит запросов к API погоды")
            return get_weather_demo()
        elif response.status_code != 200:
            logger.error(f"Ошибка API погоды: {response.status_code} - {response.text}")
            return get_weather_demo()
            
        data = response.json()
        
        weather_info = {
            'city': data['name'],
            'temperature': round(data['main']['temp']),
            'feels_like': round(data['main']['feels_like']),
            'description': data['weather'][0]['description'].capitalize(),
            'humidity': data['main']['humidity'],
            'pressure': data['main']['pressure'],
            'wind_speed': data['wind']['speed'],
            'icon': data['weather'][0]['icon'],
            'source': 'openweathermap'
        }
        
        logger.info(f"Погода получена: {weather_info['temperature']}°C, {weather_info['description']}")
        return weather_info
        
    except requests.exceptions.Timeout:
        logger.error("Таймаут при запросе погоды")
        return get_weather_demo()
    except requests.exceptions.RequestException as e:
        logger.error(f"Сетевая ошибка при получении погоды: {e}")
        return get_weather_demo()
    except Exception as e:
        logger.error(f"Неожиданная ошибка при получении погоды: {e}")
        return get_weather_demo()

def get_weather_demo():
    """Демо-данные погоды на случай недоступности API"""
    import random
    from datetime import datetime
    
    # Сезонные температуры для реалистичности
    current_month = datetime.now().month
    if current_month in [12, 1, 2]:  # Зима
        temp_range = (-15, -2)
    elif current_month in [3, 4, 5]:  # Весна
        temp_range = (0, 15)
    elif current_month in [6, 7, 8]:  # Лето
        temp_range = (15, 30)
    else:  # Осень
        temp_range = (5, 18)
    
    descriptions = [
        "ясно", "переменная облачность", "облачно с прояснениями", 
        "небольшой дождь", "пасмурно", "снег", "небольшая облачность"
    ]
    
    weather_data = {
        'city': 'Москва',
        'temperature': random.randint(temp_range[0], temp_range[1]),
        'feels_like': 0,
        'description': random.choice(descriptions),
        'humidity': random.randint(40, 90),
        'pressure': random.randint(740, 780),
        'wind_speed': round(random.uniform(1, 8), 1),
        'icon': '02d',
        'source': 'demo'
    }
    
    # Делаем "ощущается как" реалистичным
    weather_data['feels_like'] = weather_data['temperature'] + random.randint(-3, 2)
    
    return weather_data

def format_weather_message(weather_data):
    """Форматирует сообщение с погодой"""
    if not weather_data:
        return "❌ Не удалось получить данные о погоде."
    
    # Эмодзи для разных типов погоды
    weather_emojis = {
        'ясно': '☀️',
        'переменная облачность': '⛅',
        'облачно с прояснениями': '🌤️',
        'небольшой дождь': '🌦️',
        'пасмурно': '☁️',
        'снег': '❄️',
        'небольшая облачность': '🌤️'
    }
    
    description_lower = weather_data['description'].lower()
    emoji = '🌡️'
    for key, value in weather_emojis.items():
        if key in description_lower:
            emoji = value
            break
    
    message = (
        f"{emoji} <b>ПОГОДА В {weather_data['city'].upper()}</b>\n\n"
        f"🌡️ <b>Температура:</b> {weather_data['temperature']}°C\n"
        f"🤔 <b>Ощущается как:</b> {weather_data['feels_like']}°C\n"
        f"📝 <b>Описание:</b> {weather_data['description']}\n"
        f"💧 <b>Влажность:</b> {weather_data['humidity']}%\n"
        f"📊 <b>Давление:</b> {weather_data['pressure']} мм рт.ст.\n"
        f"💨 <b>Ветер:</b> {weather_data['wind_speed']} м/с\n\n"
    )
    
    # Добавляем рекомендации по одежде
    temp = weather_data['temperature']
    if temp >= 20:
        recommendation = "👕 Легкая одежда, можно в футболке"
    elif temp >= 15:
        recommendation = "👚 Длинный рукав или легкая кофта"
    elif temp >= 10:
        recommendation = "🧥 Легкая куртка или кофта"
    elif temp >= 0:
        recommendation = "🧥 Теплая куртка, шапка"
    else:
        recommendation = "🧣 Зимняя куртка, шапка, шарф, перчатки"
    
    message += f"👗 <b>Рекомендация:</b> {recommendation}\n\n"
    
    if weather_data['source'] == 'demo':
        message += "⚠️ <i>Используются демонстрационные данные (API ключ не настроен или недоступен)</i>\n"
        message += "💡 <i>Для реальных данных настройте API ключ OpenWeatherMap</i>\n"
    else:
        message += "✅ <i>Актуальные данные от OpenWeatherMap</i>\n"
    
    message += f"🕒 <i>Обновлено: {datetime.now().strftime('%d.%m.%Y %H:%M')}</i>"
    
    return message

async def send_daily_weather(context: ContextTypes.DEFAULT_TYPE):
    """Ежедневная рассылка погоды"""
    try:
        from db import get_all_users
        
        users = await get_all_users()
        if not users:
            return
        
        # Получаем погоду
        weather_data = get_weather_moscow()
        message = format_weather_message(weather_data)
        
        # Добавляем заголовок для рассылки
        full_message = f"🌅 <b>ЕЖЕДНЕВНАЯ РАССЫЛКА ПОГОДЫ</b>\n\n{message}"
        
        # Отправляем всем пользователям
        success_count = 0
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user['user_id'],
                    text=full_message,
                    parse_mode='HTML'
                )
                success_count += 1
            except Exception as e:
                logger.error(f"Ошибка отправки погоды пользователю {user['user_id']}: {e}")
        
        logger.info(f"Ежедневная рассылка погоды отправлена {success_count} пользователям")
                
    except Exception as e:
        logger.error(f"Ошибка при ежедневной рассылке погоды: {e}")
