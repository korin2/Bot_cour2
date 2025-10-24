import requests
import xml.etree.ElementTree as ET
import json
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import logging
import re
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

def get_meeting_dates():
    """Парсит даты заседаний Совета директоров ЦБ РФ по ключевой ставке"""
    try:
        urls = [
            "https://cbr.ru/dkp/cal_mp/",  # Основная страница
        ]
        
        meeting_dates = []
        
        for url in urls:
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Referer': 'https://www.cbr.ru/',
                }
                
                logger.info(f"Пытаемся получить данные с {url}")
                response = requests.get(url, headers=headers, timeout=20)
                
                if response.status_code != 200:
                    logger.warning(f"Не удалось загрузить страницу {url}, статус: {response.status_code}")
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                logger.info(f"Страница загружена, ищем данные...")
                
                # Метод 1: Ищем в таблицах
                tables = soup.find_all('table')
                logger.info(f"Найдено таблиц: {len(tables)}")
                
                for i, table in enumerate(tables):
                    rows = table.find_all('tr')
                    for row in rows:
                        cells = row.find_all(['td', 'th'])
                        row_text = ' '.join([cell.get_text(strip=True) for cell in cells])
                        
                        # Ищем строки с заседаниями
                        if any(keyword in row_text.lower() for keyword in [
                            'заседание совета директоров', 
                            'ключевая ставка',
                            'совет директоров цб',
                            'заседание цб'
                        ]):
                            # Пытаемся извлечь дату
                            date_match = re.search(r'(\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4})', row_text)
                            if date_match:
                                date_text = date_match.group(1)
                                parsed_date = parse_russian_date(date_text)
                                if parsed_date and parsed_date > datetime.now():
                                    meeting_dates.append({
                                        'date_obj': parsed_date,
                                        'date_str': date_text,
                                        'formatted_date': parsed_date.strftime('%d.%m.%Y')
                                    })
                                    logger.info(f"Найдено заседание: {date_text}")
                
                # Метод 2: Ищем по всему тексту страницы
                page_text = soup.get_text()
                date_pattern = r'(\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+\d{4})'
                dates = re.findall(date_pattern, page_text)
                
                # Фильтруем только будущие даты
                for date_text in dates:
                    parsed_date = parse_russian_date(date_text)
                    if parsed_date and parsed_date > datetime.now():
                        # Проверяем контекст - ищем упоминания о заседаниях рядом с датой
                        context_start = max(0, page_text.find(date_text) - 100)
                        context_end = min(len(page_text), page_text.find(date_text) + 100)
                        context = page_text[context_start:context_end].lower()
                        
                        if any(keyword in context for keyword in [
                            'заседание', 'совет директоров', 'цб', 'банк россии', 'ключевая'
                        ]):
                            meeting_dates.append({
                                'date_obj': parsed_date,
                                'date_str': date_text,
                                'formatted_date': parsed_date.strftime('%d.%m.%Y')
                            })
                            logger.info(f"Найдено заседание (по контексту): {date_text}")
                
            except Exception as e:
                logger.error(f"Ошибка при парсинге {url}: {e}")
                continue
        
        # Если не нашли данные через парсинг, используем запасной вариант
        if not meeting_dates:
            logger.info("Не удалось найти данные через парсинг, используем запасные данные")
            return get_fallback_meeting_dates()
        
        # Сортируем по дате и убираем дубликаты
        unique_dates = {}
        for meeting in meeting_dates:
            date_key = meeting['formatted_date']
            if date_key not in unique_dates:
                unique_dates[date_key] = meeting
        
        sorted_meetings = sorted(unique_dates.values(), key=lambda x: x['date_obj'])
        
        # Ограничиваем количество выводимых дат (ближайшие 6)
        return sorted_meetings[:6]
        
    except Exception as e:
        logger.error(f"Общая ошибка при получении дат заседаний: {e}")
        return get_fallback_meeting_dates()

def get_fallback_meeting_dates():
    """Запасные данные о заседаниях ЦБ РФ"""
    try:
        # Стандартные даты заседаний ЦБ РФ (примерные)
        current_year = datetime.now().year
        next_year = current_year + 1
        
        # Типичные даты заседаний (примерные, основанные на исторических данных)
        typical_dates = [
            f"15 января {current_year} года",
            f"12 февраля {current_year} года", 
            f"15 марта {current_year} года",
            f{26} апреля {current_year} года",
            f"14 июня {current_year} года",
            f"26 июля {current_year} года",
            f{13} сентября {current_year} года",
            f"25 октября {current_year} года",
            f"13 декабря {current_year} года",
            f"14 февраля {next_year} года",
            f"18 апреля {next_year} года",
            f"13 июня {next_year} года"
        ]
        
        meeting_dates = []
        for date_text in typical_dates:
            parsed_date = parse_russian_date(date_text)
            if parsed_date and parsed_date > datetime.now():
                meeting_dates.append({
                    'date_obj': parsed_date,
                    'date_str': date_text,
                    'formatted_date': parsed_date.strftime('%d.%m.%Y')
                })
        
        # Сортируем и берем ближайшие 6
        sorted_meetings = sorted(meeting_dates, key=lambda x: x['date_obj'])
        return sorted_meetings[:6]
        
    except Exception as e:
        logger.error(f"Ошибка в запасных данных: {e}")
        return []

def parse_russian_date(date_text):
    """Парсит русскую дату в объект datetime"""
    try:
        # Словарь для преобразования месяцев
        months = {
            'января': 1, 'февраля': 2, 'марта': 3, 'апреля': 4,
            'мая': 5, 'июня': 6, 'июля': 7, 'августа': 8,
            'сентября': 9, 'октября': 10, 'ноября': 11, 'декабря': 12
        }
        
        # Убираем "года" и лишние пробелы
        date_text = date_text.replace('года', '').strip()
        
        # Разбиваем на части
        parts = date_text.split()
        if len(parts) >= 3:
            day = int(parts[0])
            month_str = parts[1].lower()
            year = int(parts[2])
            
            if month_str in months:
                month = months[month_str]
                return datetime(year, month, day)
        
        return None
        
    except Exception as e:
        logger.error(f"Ошибка парсинга даты '{date_text}': {e}")
        return None

def get_key_rate_with_meetings():
    """Получает ключевую ставку и даты заседаний"""
    try:
        key_rate_data = get_key_rate()
        meeting_dates = get_meeting_dates()
        
        return {
            'key_rate': key_rate_data,
            'meetings': meeting_dates
        }
    except Exception as e:
        logger.error(f"Ошибка в get_key_rate_with_meetings: {e}")
        return {
            'key_rate': get_key_rate(),
            'meetings': []
        }

def format_key_rate_message(key_rate_data: dict, meeting_dates: list = None) -> str:
    """Форматирует сообщение с ключевой ставкой и датами заседаний"""
    if not key_rate_data:
        return "❌ Не удалось получить данные по ключевой ставке от ЦБ РФ."
    
    rate = key_rate_data['rate']
    source = key_rate_data.get('source', 'unknown')
    
    message = f"💎 <b>КЛЮЧЕВАЯ СТАВКА ЦБ РФ</b>\n\n"
    message += f"<b>Текущее значение:</b> {rate:.2f}%\n"
    message += f"<b>Дата установления:</b> {key_rate_data.get('date', 'неизвестно')}\n\n"
    
    # Добавляем информацию о заседаниях
    if meeting_dates:
        message += "<b>Следующие заседания ЦБ РФ:</b>\n"
        for i, meeting in enumerate(meeting_dates, 1):
            message += f"• {meeting['date_str']}\n"
        message += "\n"
    else:
        message += "<i>Информация о датах заседаний временно недоступна</i>\n\n"
    
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
        
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
        if response.status_code != 200:
            logger.error(f"Ошибка CoinGecko API: {response.status_code}")
            return None
            
        data = response.json()
        
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
    
    # Основные криптовалюты
    main_cryptos = ['bitcoin', 'ethereum', 'binancecoin']
    
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
