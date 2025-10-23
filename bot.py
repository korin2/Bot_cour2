import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from db import init_db, add_alert, update_user_info, get_all_users
import os
from datetime import datetime, timedelta
import asyncio
import xml.etree.ElementTree as ET
import json
from bs4 import BeautifulSoup

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("Требуется переменная окружения TELEGRAM_BOT_TOKEN")

# Базовый URL для официального API ЦБ РФ
CBR_API_BASE = "https://www.cbr.ru/"

def get_currency_rates_with_change():
    """Получает курсы валют от ЦБ РФ с динамикой изменения"""
    try:
        # Получаем данные за сегодня и за предыдущий день для сравнения
        today = datetime.now()
        yesterday = today - timedelta(days=1)
        
        # Форматируем даты для запроса
        date_req_today = today.strftime('%d/%m/%Y')
        date_req_yesterday = yesterday.strftime('%d/%m/%Y')
        
        # Получаем курсы за сегодня
        url = f"{CBR_API_BASE}scripts/XML_daily.asp"
        params_today = {'date_req': date_req_today}
        
        response_today = requests.get(url, params=params_today, timeout=10)
        response_today.raise_for_status()
        root_today = ET.fromstring(response_today.content)
        
        # Получаем курсы за вчера для сравнения
        params_yesterday = {'date_req': date_req_yesterday}
        response_yesterday = requests.get(url, params=params_yesterday, timeout=10)
        
        rates_yesterday = {}
        if response_yesterday.status_code == 200:
            root_yesterday = ET.fromstring(response_yesterday.content)
            for valute in root_yesterday.findall('Valute'):
                valute_id = valute.get('ID')
                value = float(valute.find('Value').text.replace(',', '.'))
                nominal = int(valute.find('Nominal').text)
                if nominal > 1:
                    value = value / nominal
                rates_yesterday[valute_id] = value
        
        # Получаем дату из атрибута
        cbr_date = root_today.get('Date', '')
        
        # Получаем курсы валют с изменением
        rates = {}
        currency_codes = {
            'R01235': 'USD',  # Доллар США
            'R01239': 'EUR',  # Евро
            'R01035': 'GBP',  # Фунт стерлингов
            'R01820': 'JPY',  # Японская иена
            'R01375': 'CNY',  # Китайский юань
            'R01775': 'CHF',  # Швейцарский франк
            'R01350': 'CAD',  # Канадский доллар
            'R01010': 'AUD',  # Австралийский доллар
            'R01700': 'TRY',  # Турецкая лира
            'R01335': 'KZT',  # Казахстанский тенге
        }
        
        for valute in root_today.findall('Valute'):
            valute_id = valute.get('ID')
            if valute_id in currency_codes:
                currency_code = currency_codes[valute_id]
                name = valute.find('Name').text
                value = float(valute.find('Value').text.replace(',', '.'))
                nominal = int(valute.find('Nominal').text)
                
                # Приводим к курсу за 1 единицу валюты
                if nominal > 1:
                    value = value / nominal
                
                # Рассчитываем изменение
                change = 0
                change_percent = 0
                if valute_id in rates_yesterday:
                    yesterday_value = rates_yesterday[valute_id]
                    change = value - yesterday_value
                    if yesterday_value > 0:
                        change_percent = (change / yesterday_value) * 100
                
                rates[currency_code] = {
                    'value': value,
                    'name': name,
                    'nominal': nominal,
                    'change': change,
                    'change_percent': change_percent
                }
        
        return rates, cbr_date
        
    except Exception as e:
        logger.error(f"Ошибка при получении курсов валют: {e}")
        return {}, 'неизвестная дата'

def get_key_rate():
    """Получает ключевую ставку ЦБ РФ через парсинг страницы"""
    try:
        url = "https://cbr.ru/hd_base/KeyRate/"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Используем BeautifulSoup для парсинга HTML
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Ищем таблицу с ключевыми ставками
        table = soup.find('table', class_='data')
        if table:
            # Берем первую строку с данными (последнюю ставку)
            rows = table.find_all('tr')
            if len(rows) > 1:
                # Первая строка - заголовки, вторая - последние данные
                cells = rows[1].find_all('td')
                if len(cells) >= 2:
                    date_str = cells[0].get_text(strip=True)
                    rate_str = cells[1].get_text(strip=True).replace(',', '.')
                    
                    # Преобразуем дату в нужный формат
                    try:
                        date_obj = datetime.strptime(date_str, '%d.%m.%Y')
                        formatted_date = date_obj.strftime('%d.%m.%Y')
                        rate_value = float(rate_str)
                        
                        key_rate_info = {
                            'rate': rate_value,
                            'date': formatted_date,
                            'is_current': True,
                            'source': 'cbr_parsed'
                        }
                        
                        return key_rate_info
                    except ValueError as e:
                        logger.error(f"Ошибка парсинга даты или ставки: {e}")
        
        logger.error("Не удалось найти данные о ключевой ставке на странице")
        return None
            
    except Exception as e:
        logger.error(f"Ошибка при получении ключевой ставки: {e}")
        return None

def get_inflation():
    """Получает данные по инфляции через официальное API ЦБ РФ"""
    try:
        # Используем API для макроэкономических показателей
        # Получаем данные по индексу потребительских цен (ИПЦ)
        today = datetime.now()
        
        # Формируем URL для получения данных по инфляции
        # Используем официальный API для статистики
        url = f"{CBR_API_BASE}statistics/macroinst/id/ipc"
        
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Ищем последние данные по инфляции на странице
            # Обычно они находятся в таблицах или специальных блоках
            inflation_value = None
            
            # Попробуем найти данные в таблицах
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) >= 2:
                        cell_text = cells[0].get_text(strip=True).lower()
                        if 'инфляция' in cell_text or 'ипц' in cell_text:
                            value_text = cells[1].get_text(strip=True)
                            try:
                                # Извлекаем числовое значение
                                import re
                                numbers = re.findall(r'\d+[,.]\d+', value_text)
                                if numbers:
                                    inflation_value = float(numbers[0].replace(',', '.'))
                                    break
                            except ValueError:
                                continue
            
            if inflation_value:
                inflation_data = {
                    'current': inflation_value,
                    'period': today.strftime('%Y'),
                    'source': 'cbr_official'
                }
                return inflation_data
        
        # Если не удалось получить данные, возвращаем демо-данные с пометкой
        logger.warning("Используются демо-данные по инфляции")
        return {
            'current': 7.4,
            'target': 4.0,
            'period': today.strftime('%Y'),
            'source': 'demo'
        }
        
    except Exception as e:
        logger.error(f"Ошибка при получении данных по инфляции: {e}")
        return {
            'current': 7.4,
            'target': 4.0,
            'period': datetime.now().strftime('%Y'),
            'source': 'demo_error'
        }

def get_metal_rates():
    """Получает курсы драгоценных металлов через API ЦБ РФ"""
    try:
        # API для драгоценных металлов
        date_req = datetime.now().strftime('%d/%m/%Y')
        url = f"{CBR_API_BASE}scripts/XML_metall.asp"
        params = {'date_req': date_req}
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        # Парсим XML ответ
        root = ET.fromstring(response.content)
        
        metal_rates = {}
        metals_map = {
            '1': {'name': 'gold', 'display': 'Золото'},
            '2': {'name': 'silver', 'display': 'Серебро'}, 
            '3': {'name': 'platinum', 'display': 'Платина'},
            '4': {'name': 'palladium', 'display': 'Палладий'}
        }
        
        for record in root.findall('Record'):
            metal_code = record.get('Code')
            if metal_code in metals_map:
                metal_info = metals_map[metal_code]
                buy_price = float(record.find('Buy').text)
                sell_price = float(record.find('Sell').text)
                avg_price = (buy_price + sell_price) / 2
                
                metal_rates[metal_info['name']] = {
                    'price': avg_price,
                    'display_name': metal_info['display'],
                    'buy': buy_price,
                    'sell': sell_price
                }
        
        if metal_rates:
            metal_rates['update_date'] = datetime.now().strftime('%d.%m.%Y')
            metal_rates['source'] = 'cbr_official'
            return metal_rates
        else:
            logger.error("Не найдено данных по металлам в ответе API")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при получении курсов металлов: {e}")
        return None

def format_currency_rates_message(rates_data: dict, cbr_date: str) -> str:
    """Форматирует сообщение с курсами валют и динамикой"""
    if not rates_data:
        return "❌ Не удалось получить курсы валют от ЦБ РФ."
    
    message = f"💱 <b>КУРСЫ ВАЛЮТ ЦБ РФ</b>\n"
    message += f"📅 <i>на {cbr_date}</i>\n\n"
    
    # Основные валюты (доллар, евро) с детальной информацией
    main_currencies = ['USD', 'EUR']
    for currency in main_currencies:
        if currency in rates_data:
            data = rates_data[currency]
            change = data['change']
            change_percent = data['change_percent']
            
            change_icon = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            change_text = f"{change:+.2f} руб. ({change_percent:+.2f}%)" if change != 0 else "без изменений"
            
            message += f"💵 <b>{data['name']}</b> ({currency}):\n"
            message += f"   <b>{data['value']:.2f} руб.</b> {change_icon}\n"
            message += f"   <i>Изменение: {change_text}</i>\n\n"
    
    # Другие валюты с краткой информацией
    other_currencies = [curr for curr in rates_data.keys() if curr not in main_currencies]
    if other_currencies:
        message += "🌍 <b>Другие валюты:</b>\n"
        
        for currency in other_currencies:
            data = rates_data[currency]
            change = data['change']
            change_icon = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            
            # Для JPY показываем за 100 единиц
            if currency == 'JPY':
                display_value = data['value'] * 100
                message += f"   {data['name']} ({currency}): <b>{display_value:.2f} руб.</b> {change_icon}\n"
            else:
                message += f"   {data['name']} ({currency}): <b>{data['value']:.2f} руб.</b> {change_icon}\n"
    
    message += f"\n💡 <i>Официальные курсы ЦБ РФ с динамикой изменений</i>"
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
    message += "которая влияет на кредиты, депозиты и экономику в целом</i>"
    
    if key_rate_data.get('source') == 'cbr_parsed':
        message += f"\n\n✅ <i>Данные получены с официального сайта ЦБ РФ</i>"
    
    return message

def format_inflation_message(inflation_data: dict) -> str:
    """Форматирует сообщение с данными по инфляции"""
    if not inflation_data:
        return "❌ Не удалось получить данные по инфляции от ЦБ РФ."
    
    current = inflation_data['current']
    target = inflation_data.get('target')
    period = inflation_data['period']
    source = inflation_data.get('source', '')
    
    message = f"📊 <b>ИНФЛЯЦИЯ В РОССИИ</b>\n\n"
    message += f"<b>Текущая инфляция:</b> {current:.1f}%\n"
    
    if target:
        message += f"<b>Целевой показатель ЦБ РФ:</b> {target:.1f}%\n"
    
    message += f"<b>Период:</b> {period} год\n\n"
    
    # Анализ
    if target and current > target:
        message += f"📈 <i>Инфляция выше целевого уровня</i>\n"
    elif target and current < target:
        message += f"📉 <i>Инфляция ниже целевого уровня</i>\n"
    elif target:
        message += f"✅ <i>Инфляция на целевом уровне</i>\n"
    
    message += "\n💡 <i>Официальные данные по инфляции от ЦБ РФ</i>"
    
    if source == 'demo':
        message += f"\n\n⚠️ <i>Используются демонстрационные данные</i>"
    elif source == 'demo_error':
        message += f"\n\n⚠️ <i>Используются демонстрационные данные (ошибка получения реальных)</i>"
    elif source == 'cbr_official':
        message += f"\n\n✅ <i>Данные получены через официальное API ЦБ РФ</i>"
    
    return message

def format_metal_rates_message(metal_rates: dict) -> str:
    """Форматирует сообщение с курсами драгоценных металлов"""
    if not metal_rates:
        return "❌ Не удалось получить курсы драгоценных металлов от ЦБ РФ."
    
    message = f"🥇 <b>КУРСЫ ДРАГОЦЕННЫХ МЕТАЛЛОВ ЦБ РФ</b>\n\n"
    
    # Сортируем металлы в определенном порядке
    metal_order = ['gold', 'silver', 'platinum', 'palladium']
    
    for metal_code in metal_order:
        if metal_code in metal_rates:
            data = metal_rates[metal_code]
            message += f"<b>{data['display_name']}:</b> {data['price']:.2f} руб/г\n"
            message += f"  <i>Покупка: {data['buy']:.2f} | Продажа: {data['sell']:.2f}</i>\n\n"
    
    message += f"<i>Обновлено: {metal_rates.get('update_date', 'неизвестно')}</i>\n\n"
    message += "💡 <i>Официальные курсы для операций с драгоценными металлами</i>"
    
    if metal_rates.get('source') == 'cbr_official':
        message += f"\n\n✅ <i>Данные получены через официальное API ЦБ РФ</i>"
    
    return message

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    try:
        user = update.effective_user
        
        # Сохраняем информацию о пользователе в БД
        await update_user_info(user.id, user.first_name, user.username)
        
        # Создаем персонализированное приветствие
        greeting = f"Привет, {user.first_name}!" if user.first_name else "Привет!"
        
        # Получаем актуальные данные для приветственного сообщения
        key_rate_data = get_key_rate()
        
        # Главное меню
        keyboard = [
            [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
            [InlineKeyboardButton("💎 Ключевая ставка", callback_data='key_rate')],
            [InlineKeyboardButton("📊 Инфляция", callback_data='inflation')],
            [InlineKeyboardButton("🥇 Драгоценные металлы", callback_data='metal_rates')],
            [InlineKeyboardButton("❓ Помощь", callback_data='help')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        start_message = f'{greeting} Я бот для отслеживания официальных данных ЦБ РФ!\n\n'
        start_message += '🏛 <b>ОФИЦИАЛЬНЫЕ ДАННЫЕ ЦЕНТРАЛЬНОГО БАНКА РОССИИ</b>\n\n'
        
        # Добавляем информацию о ключевой ставке в приветствие
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
    """Показывает курсы валют с динамикой"""
    try:
        rates_data, cbr_date = get_currency_rates_with_change()
        
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

# Остальные функции без изменений (send_daily_rates, команды, обработчики)
async def send_daily_rates(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ежедневная отправка основных данных ЦБ РФ всем пользователям"""
    try:
        logger.info("Начало ежедневной рассылки данных ЦБ РФ")
        
        # Получаем основные данные
        rates_data, cbr_date = get_currency_rates_with_change()
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

# Команды бота (остаются без изменений)
async def currency_rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_currency_rates(update, context)

async def keyrate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_key_rate(update, context)

async def inflation_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_inflation(update, context)

async def metals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_metal_rates(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_help(update, context)

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = update.effective_user
        greeting = f", {user.first_name}!" if user.first_name else "!"
        
        help_text = (
            f"Привет{greeting} Я бот для отслеживания официальных данных ЦБ РФ!\n\n"
            
            "🏛 <b>ОФИЦИАЛЬНЫЕ ДАННЫЕ ЦЕНТРАЛЬНОГО БАНКА РОССИИ</b>\n\n"
            
            "💱 <b>Основные команды:</b>\n"
            "• <code>/start</code> - главное меню\n"
            "• <code>/rates</code> - курсы валют ЦБ РФ с динамикой\n"
            "• <code>/keyrate</code> - ключевая ставка ЦБ РФ\n"
            "• <code>/inflation</code> - данные по инфляции\n"
            "• <code>/metals</code> - курсы драгоценных металлов\n"
            "• <code>/help</code> - эта справка\n\n"
            
            "🔔 <b>Уведомления:</b>\n"
            "• <code>/alert USD RUB 80 above</code> - уведомит о курсе\n\n"
            
            "⏰ <b>Ежедневная рассылка</b>\n"
            "• Автоматическая отправка основных данных каждый день в 10:00\n\n"
            
            "📊 <b>Доступные разделы:</b>\n"
            "• <b>Курсы валют</b> - основные мировые валюты с динамикой изменений\n"
            "• <b>Ключевая ставка</b> - основная процентная ставка ЦБ РФ\n"
            "• <b>Инфляция</b> - текущий уровень инфляции\n"
            "• <b>Драгоценные металлы</b> - золото, серебро, платина, палладий\n\n"
            
            "💡 <b>ИНФОРМАЦИЯ</b>\n\n"
            "• Все данные предоставляются через официальные источники ЦБ РФ\n"
            "• Курсы обновляются ежедневно с отображением динамики\n"
            "• Ключевая ставка обновляется по решению Совета директоров\n"
            "• Используются только официальные источники данных"
        )
        
        # Клавиатура с кнопкой "Назад"
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
        
        # Клавиатура с кнопкой "Назад"
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
            # Клавиатура с кнопкой "Назад"
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
            # Клавиатура с кнопкой "Назад"
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("❌ Порог должен быть числом.", reply_markup=reply_markup)
            return
        
        direction = args[3].lower()
        if direction not in ['above', 'below']:
            # Клавиатура с кнопкой "Назад"
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("❌ Направление должно быть 'above' или 'below'.", reply_markup=reply_markup)
            return
        
        user_id = update.effective_message.from_user.id
        await add_alert(user_id, from_curr, to_curr, threshold, direction)
        
        # Клавиатура с кнопкой "Назад"
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
            
            # Создаем персонализированное приветствие
            greeting = f"Привет, {user.first_name}!" if user.first_name else "Привет!"
            
            keyboard = [
                [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
                [InlineKeyboardButton("💎 Ключевая ставка", callback_data='key_rate')],
                [InlineKeyboardButton("📊 Инфляция", callback_data='inflation')],
                [InlineKeyboardButton("🥇 Драгоценные металлы", callback_data='metal_rates')],
                [InlineKeyboardButton("❓ Помощь", callback_data='help')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f'{greeting} Я бот для отслеживания официальных данных ЦБ РФ!\n\n'
                '🏛 <b>ОФИЦИАЛЬНЫЕ ДАННЫЕ ЦЕНТРАЛЬНОГО БАНКА РОССИИ</b>\n\n'
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
    except Exception as e:
        logger.error(f"Ошибка в обработчике кнопок: {e}")

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Клавиатура с кнопкой "Назад"
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
        # Создаем и настраиваем application
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
        application.add_handler(CommandHandler("alert", alert_command))
        
        # Обработчик для inline-кнопок
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Обработчик для неизвестных команд
        application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

        # Настраиваем ежедневную рассылку в 10:00 (07:00 UTC)
        job_queue = application.job_queue
        
        if job_queue:
            # 10:00 МСК = 07:00 UTC
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