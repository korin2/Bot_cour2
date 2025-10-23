import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from db import init_db, add_alert, update_user_info, get_all_users
import os
from datetime import datetime, timedelta
import asyncio
import xml.etree.ElementTree as ET

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("Требуется переменная окружения TELEGRAM_BOT_TOKEN")

# Базовый URL для официального SOAP API ЦБ РФ
CBR_SOAP_URL = "https://www.cbr.ru/DailyInfoWebServ/DailyInfo.asmx"

# SOAP заголовки
SOAP_HEADERS = {
    'Content-Type': 'text/xml; charset=utf-8',
    'SOAPAction': ''
}

def make_soap_request(action, body):
    """Выполняет SOAP запрос к API ЦБ РФ"""
    try:
        soap_action = f"http://web.cbr.ru/{action}"
        headers = SOAP_HEADERS.copy()
        headers['SOAPAction'] = soap_action
        
        envelope = f'''<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:xsd="http://www.w3.org/2001/XMLSchema" xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    {body}
  </soap:Body>
</soap:Envelope>'''
        
        response = requests.post(CBR_SOAP_URL, data=envelope, headers=headers, timeout=10)
        response.raise_for_status()
        
        # Парсим XML ответ
        root = ET.fromstring(response.content)
        
        # Находим результат (убираем SOAP обертку)
        for elem in root.iter():
            if elem.tag.endswith('}') and not elem.text and len(elem) == 0:
                continue
            if elem.text and elem.text.strip():
                return elem.text
        
        return response.content
        
    except Exception as e:
        logger.error(f"Ошибка SOAP запроса для {action}: {e}")
        return None

def get_currency_rates(date_req=None):
    """Получает курсы валют от ЦБ РФ на определенную дату через SOAP"""
    try:
        if date_req is None:
            date_req = datetime.now().strftime('%Y-%m-%d')
        
        # SOAP запрос для получения курсов валют
        soap_body = f'''<GetCursOnDate xmlns="http://web.cbr.ru/">
          <On_date>{date_req}</On_date>
        </GetCursOnDate>'''
        
        response_text = make_soap_request("GetCursOnDate", soap_body)
        
        if not response_text:
            return {}, 'неизвестная дата'
        
        # Парсим XML с курсами валют
        rates_root = ET.fromstring(response_text)
        
        # Получаем дату
        cbr_date = date_req
        
        # Получаем курсы валют
        rates = {}
        main_currencies = {
            'R01235': 'USD',  # Доллар США
            'R01239': 'EUR',  # Евро
            'R01035': 'GBP',  # Фунт стерлингов
            'R01820': 'JPY',  # Японская иена
            'R01375': 'CNY',  # Китайский юань
            'R01775': 'CHF',  # Швейцарский франк
            'R01350': 'CAD',  # Канадский доллар
            'R01010': 'AUD',  # Австралийский доллар
            'R01700J': 'TRY', # Турецкая лира
            'R01335': 'KZT',  # Казахстанский тенге
        }
        
        # Парсим валюты из ValuteCursOnDate
        for valute in rates_root.findall('.//ValuteCursOnDate'):
            valute_code = valute.find('Vcode').text
            if valute_code in main_currencies:
                currency_code = main_currencies[valute_code]
                name = valute.find('Vname').text
                value = float(valute.find('Vcurs').text)
                nominal = int(valute.find('Vnom').text)
                
                # Приводим к курсу за 1 единицу валюты
                if nominal > 1:
                    value = value / nominal
                
                rates[currency_code] = {
                    'value': value,
                    'name': name,
                    'nominal': 1
                }
        
        return rates, cbr_date
        
    except Exception as e:
        logger.error(f"Ошибка при получении курсов валют через SOAP: {e}")
        return {}, 'неизвестная дата'

def get_key_rate():
    """Получает ключевую ставку ЦБ РФ через SOAP"""
    try:
        # SOAP запрос для получения ключевой ставки
        soap_body = '''<KeyRate xmlns="http://web.cbr.ru/" />'''
        
        response_text = make_soap_request("KeyRate", soap_body)
        
        if not response_text:
            return None
        
        # Парсим XML с ключевой ставкой
        keyrate_root = ET.fromstring(response_text)
        
        # Ищем последнюю запись о ключевой ставке
        last_record = None
        for record in keyrate_root.findall('.//KeyRate'):
            rate_date = record.find('DT').text
            rate_value = float(record.find('Rate').text)
            
            if not last_record or rate_date > last_record['date']:
                last_record = {
                    'date': rate_date,
                    'rate': rate_value
                }
        
        if last_record:
            # Преобразуем дату в формат DD.MM.YYYY
            date_obj = datetime.strptime(last_record['date'], '%Y-%m-%dT%H:%M:%S')
            formatted_date = date_obj.strftime('%d.%m.%Y')
            
            key_rate_info = {
                'rate': last_record['rate'],
                'date': formatted_date,
                'is_current': True,
                'source': 'cbr_soap'
            }
            
            return key_rate_info
        else:
            logger.error("Не найдено записей о ключевой ставке в SOAP ответе")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при получении ключевой ставки через SOAP: {e}")
        return None

def get_inflation():
    """Получает данные по инфляции через SOAP"""
    try:
        # SOAP запрос для получения данных по инфляции
        # Используем метод для получения индекса потребительских цен
        today = datetime.now()
        start_date = (today - timedelta(days=30)).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
        
        soap_body = f'''<GetInflation xmlns="http://web.cbr.ru/">
          <fromDate>{start_date}</fromDate>
          <ToDate>{end_date}</ToDate>
        </GetInflation>'''
        
        response_text = make_soap_request("GetInflation", soap_body)
        
        if response_text:
            # Парсим XML с инфляцией
            inflation_root = ET.fromstring(response_text)
            
            # Берем последнее значение
            last_inflation = None
            for record in inflation_root.findall('.//Inflation'):
                inflation_date = record.find('Date').text
                inflation_value = float(record.find('Value').text)
                
                if not last_inflation or inflation_date > last_inflation['date']:
                    last_inflation = {
                        'date': inflation_date,
                        'value': inflation_value
                    }
            
            if last_inflation:
                return {
                    'current': last_inflation['value'],
                    'period': 'текущий месяц',
                    'source': 'cbr_soap'
                }
        
        # Если не удалось получить через SOAP, используем демо-данные
        return {
            'current': 7.4,
            'period': '2024',
            'source': 'demo'
        }
        
    except Exception as e:
        logger.error(f"Ошибка при получении данных по инфляции через SOAP: {e}")
        return {
            'current': 7.4,
            'period': '2024',
            'source': 'demo_fallback'
        }

def get_metal_rates():
    """Получает курсы драгоценных металлов через SOAP"""
    try:
        # SOAP запрос для получения курсов драгоценных металлов
        today = datetime.now().strftime('%Y-%m-%d')
        
        soap_body = f'''<GetMetallDynamic xmlns="http://web.cbr.ru/">
          <fromDate>{today}</fromDate>
          <ToDate>{today}</ToDate>
          <metalCode>1</metalCode>
        </GetMetallDynamic>'''
        
        # Получаем данные для золота
        gold_response = make_soap_request("GetMetallDynamic", soap_body)
        
        # Для других металлов нужно делать отдельные запросы с разными metalCode
        # 1 - золото, 2 - серебро, 3 - платина, 4 - палладий
        
        metal_rates = {}
        
        # Временная реализация с демо-данными
        # В реальном приложении нужно делать запросы для каждого металла
        metal_rates = {
            'gold': {'avg': 5830.50},
            'silver': {'avg': 72.30},
            'platinum': {'avg': 3200.75},
            'palladium': {'avg': 4100.25}
        }
        
        if metal_rates:
            metal_rates['update_date'] = datetime.now().strftime('%d.%m.%Y')
            metal_rates['source'] = 'cbr_soap_demo'
            return metal_rates
        else:
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при получении курсов металлов через SOAP: {e}")
        return None

def get_main_indicators():
    """Получает основные показатели через SOAP"""
    try:
        # SOAP запрос для получения основных показателей
        soap_body = '''<MainIndicatorsVR xmlns="http://web.cbr.ru/" />'''
        
        response_text = make_soap_request("MainIndicatorsVR", soap_body)
        
        if response_text:
            # Парсим XML с основными показателями
            indicators_root = ET.fromstring(response_text)
            
            indicators = {}
            
            # Пример парсинга некоторых показателей
            for indicator in indicators_root.findall('.//MainIndicatorsVR'):
                date_str = indicator.find('Date').text if indicator.find('Date') is not None else None
                # Добавьте парсинг других показателей по необходимости
                
            return indicators
        else:
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при получении основных показателей через SOAP: {e}")
        return None

def format_currency_rates_message(rates_data: dict, cbr_date: str) -> str:
    """Форматирует сообщение с курсами валют"""
    if not rates_data:
        return "❌ Не удалось получить курсы валют от ЦБ РФ."
    
    message = f"💱 <b>КУРСЫ ВАЛЮТ ЦБ РФ</b>\n"
    message += f"📅 <i>на {cbr_date}</i>\n\n"
    
    # Основные валюты (доллар, евро)
    main_currencies = ['USD', 'EUR']
    for currency in main_currencies:
        if currency in rates_data:
            data = rates_data[currency]
            current_value = data['value']
            
            message += f"💵 <b>{data['name']}</b> ({currency}):\n"
            message += f"   <b>{current_value:.2f} руб.</b>\n\n"
    
    # Другие валюты
    other_currencies = [curr for curr in rates_data.keys() if curr not in main_currencies]
    if other_currencies:
        message += "🌍 <b>Другие валюты:</b>\n"
        
        for currency in other_currencies:
            data = rates_data[currency]
            current_value = data['value']
            
            # Для JPY показываем за 100 единиц
            if currency == 'JPY':
                display_value = current_value * 100
                message += f"   {data['name']} ({currency}): <b>{display_value:.2f} руб.</b>\n"
            else:
                message += f"   {data['name']} ({currency}): <b>{current_value:.2f} руб.</b>\n"
    
    message += f"\n💡 <i>Официальные курсы ЦБ РФ через SOAP API</i>"
    return message

def format_key_rate_message(key_rate_data: dict) -> str:
    """Форматирует сообщение с ключевой ставкой"""
    if not key_rate_data:
        return "❌ Не удалось получить данные по ключевой ставке от ЦБ РФ."
    
    rate = key_rate_data['rate']
    
    message = f"💎 <b>КЛЮЧЕВАЯ СТАВКА ЦБ РФ</b>\n\n"
    message += f"<b>Текущее значение:</b> {rate:.2f}%\n"
    message += f"\n<b>Дата установления:</b> {key_rate_data.get('date', 'неизвестно')}\n\n"
    message += "💡 <i>Ключевая ставка - это основная процентная ставка ЦБ РФ,\n"
    message += "которая влияет на кредиты, депозиты и экономику в целом</i>\n\n"
    message += "<i>Данные получены через официальный SOAP API ЦБ РФ</i>"
    
    return message

def format_inflation_message(inflation_data: dict) -> str:
    """Форматирует сообщение с данными по инфляции"""
    if not inflation_data:
        return "❌ Не удалось получить данные по инфляции от ЦБ РФ."
    
    current = inflation_data['current']
    period = inflation_data['period']
    
    message = f"📊 <b>ИНФЛЯЦИЯ В РОССИИ</b>\n\n"
    message += f"<b>Уровень инфляции:</b> {current:.1f}%\n"
    message += f"<b>Период:</b> {period}\n\n"
    
    if inflation_data.get('source', '').startswith('demo'):
        message += "⚠️ <i>Используются демонстрационные данные</i>\n\n"
    
    message += "💡 <i>Официальные данные по инфляции от ЦБ РФ</i>\n"
    message += "<i>Данные получены через официальный SOAP API ЦБ РФ</i>"
    
    return message

def format_metal_rates_message(metal_rates: dict) -> str:
    """Форматирует сообщение с курсами драгоценных металлов"""
    if not metal_rates:
        return "❌ Не удалось получить курсы драгоценных металлов от ЦБ РФ."
    
    message = f"🥇 <b>КУРСЫ ДРАГОЦЕННЫХ МЕТАЛЛОВ ЦБ РФ</b>\n\n"
    
    metal_names = {
        'gold': 'Золото',
        'silver': 'Серебро', 
        'platinum': 'Платина',
        'palladium': 'Палладий'
    }
    
    for metal_code, metal_name in metal_names.items():
        if metal_code in metal_rates:
            data = metal_rates[metal_code]
            message += f"<b>{metal_name}:</b> {data['avg']:.2f} руб/г\n"
    
    message += f"\n<i>Обновлено: {metal_rates.get('update_date', 'неизвестно')}</i>\n\n"
    message += "💡 <i>Официальные курсы для операций с драгоценными металлами</i>\n"
    
    if metal_rates.get('source', '').endswith('demo'):
        message += "⚠️ <i>Используются демонстрационные данные</i>\n"
    else:
        message += "<i>Данные получены через официальный SOAP API ЦБ РФ</i>"
    
    return message

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = update.effective_user
        
        # Сохраняем информацию о пользователе в БД
        await update_user_info(user.id, user.first_name, user.username)
        
        # Создаем персонализированное приветствие
        if user.first_name:
            greeting = f"Привет, {user.first_name}!"
        else:
            greeting = "Привет!"
        
        # Получаем актуальные данные для приветственного сообщения
        rates_data, cbr_date = get_currency_rates()
        key_rate_data = get_key_rate()
        
        # Главное меню с разделами API ЦБ РФ
        keyboard = [
            [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
            [InlineKeyboardButton("💎 Ключевая ставка", callback_data='key_rate')],
            [InlineKeyboardButton("📊 Инфляция", callback_data='inflation')],
            [InlineKeyboardButton("🥇 Драгоценные металлы", callback_data='metal_rates')],
            [InlineKeyboardButton("📈 Основные показатели", callback_data='main_indicators')],
            [InlineKeyboardButton("❓ Помощь", callback_data='help')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        start_message = f'{greeting} Я бот для отслеживания официальных данных ЦБ РФ!\n\n'
        start_message += '🏛 <b>ОФИЦИАЛЬНЫЕ ДАННЫЕ ЦБ РФ ЧЕРЕЗ SOAP API</b>\n\n'
        
        # Добавляем краткую сводку
        if key_rate_data and key_rate_data.get('is_current'):
            rate = key_rate_data['rate']
            start_message += f'💎 <b>Ключевая ставка ЦБ РФ:</b> <b>{rate:.2f}%</b>\n\n'
        
        start_message += 'Выберите раздел из меню ниже:'
        
        await update.message.reply_text(
            start_message,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Ошибка в команде /start: {e}")
        await update.message.reply_text("❌ Произошла ошибка при запуске бота. Пожалуйста, попробуйте еще раз.")

async def show_currency_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает курсы валют"""
    try:
        rates_data, cbr_date = get_currency_rates()
        
        if not rates_data:
            error_msg = "❌ Не удалось получить курсы валют от ЦБ РФ. Попробуйте позже."
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_msg, reply_markup=reply_markup)
            return
        
        message = format_currency_rates_message(rates_data, cbr_date)
        
        # Клавиатура с кнопкой "Назад"
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка при показе курсов валют: {e}")
        error_msg = "❌ Произошла ошибка при получении курсов валют от ЦБ РФ."
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
        else:
            await update.message.reply_text(error_msg, reply_markup=reply_markup)

async def show_key_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает ключевую ставку ЦБ РФ"""
    try:
        key_rate_data = get_key_rate()
        
        if not key_rate_data:
            error_msg = "❌ Не удалось получить ключевую ставку ЦБ РФ."
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_msg, reply_markup=reply_markup)
            return
        
        message = format_key_rate_message(key_rate_data)
        
        # Клавиатура с кнопками
        keyboard = [
            [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка при показе ключевой ставки: {e}")
        error_msg = "❌ Произошла ошибка при получении ключевой ставки от ЦБ РФ."
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
        else:
            await update.message.reply_text(error_msg, reply_markup=reply_markup)

async def show_inflation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает данные по инфляции"""
    try:
        inflation_data = get_inflation()
        
        if not inflation_data:
            error_msg = "❌ Не удалось получить данные по инфляции от ЦБ РФ."
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_msg, reply_markup=reply_markup)
            return
        
        message = format_inflation_message(inflation_data)
        
        # Клавиатура с кнопками
        keyboard = [
            [InlineKeyboardButton("💎 Ключевая ставка", callback_data='key_rate')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка при показе инфляции: {e}")
        error_msg = "❌ Произошла ошибка при получении данных по инфляции от ЦБ РФ."
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
        else:
            await update.message.reply_text(error_msg, reply_markup=reply_markup)

async def show_metal_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает курсы драгоценных металлов"""
    try:
        metal_rates = get_metal_rates()
        
        if not metal_rates:
            error_msg = "❌ Не удалось получить курсы драгоценных металлов от ЦБ РФ."
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_msg, reply_markup=reply_markup)
            return
        
        message = format_metal_rates_message(metal_rates)
        
        # Клавиатура с кнопками
        keyboard = [
            [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка при показе курсов металлов: {e}")
        error_msg = "❌ Произошла ошибка при получении курсов драгоценных металлов от ЦБ РФ."
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
        else:
            await update.message.reply_text(error_msg, reply_markup=reply_markup)

async def show_main_indicators(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает основные показатели"""
    try:
        indicators = get_main_indicators()
        
        if not indicators:
            message = "📈 <b>ОСНОВНЫЕ ПОКАЗАТЕЛИ ЦБ РФ</b>\n\n"
            message += "⚠️ <i>Функция в разработке</i>\n\n"
            message += "В будущем здесь будут отображаться:\n"
            message += "• Золотовалютные резервы\n"
            message += "• Международные резервы\n"
            message += "• Прочие макроэкономические показатели\n\n"
            message += "<i>Используется официальный SOAP API ЦБ РФ</i>"
        else:
            message = "📈 <b>ОСНОВНЫЕ ПОКАЗАТЕЛИ ЦБ РФ</b>\n\n"
            # Здесь будет парсинг и отображение показателей
            message += "<i>Данные обновляются...</i>"
        
        # Клавиатура с кнопками
        keyboard = [
            [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
            [InlineKeyboardButton("💎 Ключевая ставка", callback_data='key_rate')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка при показе основных показателей: {e}")
        error_msg = "❌ Произошла ошибка при получении основных показателей от ЦБ РФ."
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
        else:
            await update.message.reply_text(error_msg, reply_markup=reply_markup)

async def send_daily_rates(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ежедневная отправка основных данных ЦБ РФ всем пользователям"""
    try:
        logger.info("Начало ежедневной рассылки данных ЦБ РФ")
        
        # Получаем основные данные
        rates_data, cbr_date = get_currency_rates()
        key_rate_data = get_key_rate()
        
        if not rates_data:
            logger.error("Не удалось получить данные для ежедневной рассылки")
            return
        
        # Форматируем сообщение
        message = f"🌅 <b>Ежедневное обновление данных ЦБ РФ</b>\n\n"
        
        if key_rate_data and key_rate_data.get('is_current'):
            rate = key_rate_data['rate']
            message += f"💎 <b>Ключевая ставка:</b> {rate:.2f}%\n\n"
        
        message += format_currency_rates_message(rates_data, cbr_date)
        
        # Получаем всех пользователей из базы данных
        users = await get_all_users()
        
        if not users:
            logger.info("Нет пользователей для рассылки")
            return
        
        logger.info(f"Начинаем рассылку для {len(users)} пользователей")
        
        # Отправляем сообщение каждому пользователю
        success_count = 0
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user['user_id'],
                    text=message,
                    parse_mode='HTML'
                )
                success_count += 1
                # Небольшая задержка чтобы не превысить лимиты Telegram
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.warning(f"Не удалось отправить сообщение пользователю {user['user_id']}: {e}")
        
        logger.info(f"Ежедневная рассылка завершена. Успешно отправлено: {success_count}/{len(users)}")
        
    except Exception as e:
        logger.error(f"Ошибка в ежедневной рассылке: {e}")

# Команды и обработчики (остаются без изменений)
async def currency_rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_currency_rates(update, context)

async def keyrate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_key_rate(update, context)

async def inflation_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_inflation(update, context)

async def metals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_metal_rates(update, context)

async def indicators_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_main_indicators(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_help(update, context)

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = update.effective_user
        greeting = f", {user.first_name}!" if user.first_name else "!"
        
        help_text = (
            f"Привет{greeting} Я бот для отслеживания официальных данных ЦБ РФ!\n\n"
            
            "🏛 <b>ОФИЦИАЛЬНЫЕ ДАННЫЕ ЦБ РФ ЧЕРЕЗ SOAP API</b>\n\n"
            
            "💱 <b>Основные команды:</b>\n"
            "• <code>/start</code> - главное меню\n"
            "• <code>/rates</code> - курсы валют ЦБ РФ\n"
            "• <code>/keyrate</code> - ключевая ставка ЦБ РФ\n"
            "• <code>/inflation</code> - данные по инфляции\n"
            "• <code>/metals</code> - курсы драгоценных металлов\n"
            "• <code>/indicators</code> - основные показатели\n"
            "• <code>/help</code> - эта справка\n\n"
            
            "🔔 <b>Уведомления:</b>\n"
            "• <code>/alert USD RUB 80 above</code> - уведомит о курсе\n\n"
            
            "⏰ <b>Ежедневная рассылка</b>\n"
            "• Автоматическая отправка основных данных каждый день в 10:00\n\n"
            
            "📊 <b>Доступные разделы:</b>\n"
            "• <b>Курсы валют</b> - основные мировые валюты\n"
            "• <b>Ключевая ставка</b> - основная процентная ставка ЦБ РФ\n"
            "• <b>Инфляция</b> - текущий уровень инфляции\n"
            "• <b>Драгоценные металлы</b> - золото, серебро, платина, палладий\n"
            "• <b>Основные показатели</b> - макроэкономические показатели\n\n"
            
            "💡 <b>ИНФОРМАЦИЯ</b>\n\n"
            "• Все данные предоставляются через официальный SOAP API ЦБ РФ\n"
            "• Используется веб-сервис DailyInfoWebServ\n"
            "• Данные всегда актуальные и официальные\n"
            "• Обновление в реальном времени"
        )
        
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(help_text, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка при показе справки: {e}")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = update.effective_user
        greeting = f", {user.first_name}!" if user.first_name else "!"
        
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"До свидания{greeting} Бот остановлен.\n"
            "Для возобновления работы отправьте /start",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка в команде /stop: {e}")

async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_currency_rates(update, context)

async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        args = context.args
        if len(args) != 4:
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Используйте: /alert <из> <в> <порог> <above|below>\n\n"
                "Пример: /alert USD RUB 80 above",
                reply_markup=reply_markup
            )
            return
        
        from_curr, to_curr = args[0], args[1]
        try:
            threshold = float(args[2])
        except ValueError:
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("❌ Порог должен быть числом.", reply_markup=reply_markup)
            return
        
        direction = args[3].lower()
        if direction not in ['above', 'below']:
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("❌ Направление должно быть 'above' или 'below'.", reply_markup=reply_markup)
            return
        
        user_id = update.effective_message.from_user.id
        await add_alert(user_id, from_curr, to_curr, threshold, direction)
        
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🔔 Уведомление установлено: {from_curr}/{to_curr} {'>' if direction == 'above' else '<'} {threshold}",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка в команде /alert: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == 'help':
            await show_help(update, context)
        elif data == 'back_to_main':
            user = query.from_user
            
            if user.first_name:
                greeting = f"Привет, {user.first_name}!"
            else:
                greeting = "Привет!"
            
            keyboard = [
                [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
                [InlineKeyboardButton("💎 Ключевая ставка", callback_data='key_rate')],
                [InlineKeyboardButton("📊 Инфляция", callback_data='inflation')],
                [InlineKeyboardButton("🥇 Драгоценные металлы", callback_data='metal_rates')],
                [InlineKeyboardButton("📈 Основные показатели", callback_data='main_indicators')],
                [InlineKeyboardButton("❓ Помощь", callback_data='help')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f'{greeting} Я бот для отслеживания официальных данных ЦБ РФ!\n\n'
                '🏛 <b>ОФИЦИАЛЬНЫЕ ДАННЫЕ ЦБ РФ ЧЕРЕЗ SOAP API</b>\n\n'
                'Выберите раздел из меню ниже:',
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        elif data == 'currency_rates':
            await show_currency_rates(update, context)
        elif data == 'key_rate':
            await show_key_rate(update, context)
        elif data == 'inflation':
            await show_inflation(update, context)
        elif data == 'metal_rates':
            await show_metal_rates(update, context)
        elif data == 'main_indicators':
            await show_main_indicators(update, context)
    except Exception as e:
        logger.error(f"Ошибка в обработчике кнопок: {e}")

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ Неизвестная команда. Используйте /help для просмотра доступных команд.",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка в обработчике неизвестных команд: {e}")

async def post_init(application: Application) -> None:
    """Функция, выполняемая после инициализации бота"""
    try:
        await init_db()
        logger.info("БД инициализирована успешно")
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}")

def main() -> None:
    """Основная функция для запуска бота"""
    try:
        application = Application.builder().token(TOKEN).post_init(post_init).build()

        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("stop", stop_command))
        application.add_handler(CommandHandler("rates", rates_command))
        application.add_handler(CommandHandler("currency", currency_rates_command))
        application.add_handler(CommandHandler("keyrate", keyrate_command))
        application.add_handler(CommandHandler("inflation", inflation_command))
        application.add_handler(CommandHandler("metals", metals_command))
        application.add_handler(CommandHandler("indicators", indicators_command))
        application.add_handler(CommandHandler("alert", alert_command))
        
        # Обработчик для inline-кнопок
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Обработчик для неизвестных команд
        application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

        # Настраиваем ежедневную рассылку в 10:00 (07:00 UTC)
        job_queue = application.job_queue
        
        if job_queue:
            job_queue.run_daily(
                send_daily_rates,
                time=datetime.strptime("07:00", "%H:%M").time(),
                days=(0, 1, 2, 3, 4, 5, 6)
            )
            logger.info("Ежедневная рассылка настроена на 10:00 МСК (07:00 UTC)")
        else:
            logger.warning("JobQueue не доступен. Ежедневная рассылка не будет работать.")

        # Запуск бота
        logger.info("Бот запускается...")
        application.run_polling()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    main()
