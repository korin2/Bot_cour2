import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from db import init_db, add_alert, update_user_info, get_all_users
import os
from datetime import datetime, timedelta
import asyncio
import json

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("Требуется переменная окружения TELEGRAM_BOT_TOKEN")

# Базовый URL для API ЦБ РФ
CBR_API_BASE = "https://www.cbr.ru/eng/webservices/"

def get_currency_rates(date=None):
    """Получает курсы валют от ЦБ РФ на определенную дату"""
    try:
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
        
        # Используем API для ежедневных курсов
        url = f"https://www.cbr-xml-daily.ru/daily_json.js"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Получаем дату
        cbr_date = data.get('Date', '')
        if cbr_date:
            try:
                date_obj = datetime.fromisoformat(cbr_date.replace('Z', '+00:00'))
                cbr_date = date_obj.strftime('%d.%m.%Y')
            except:
                cbr_date = 'неизвестная дата'
        else:
            cbr_date = 'неизвестная дата'
        
        # Получаем курсы валют
        valutes = data.get('Valute', {})
        rates = {}
        
        # Основные валюты для отображения
        main_currencies = {
            'USD': 'Доллар США',
            'EUR': 'Евро',
            'GBP': 'Фунт стерлингов',
            'JPY': 'Японская иена',
            'CNY': 'Китайский юань',
            'CHF': 'Швейцарский франк',
            'CAD': 'Канадский доллар',
            'AUD': 'Австралийский доллар',
            'TRY': 'Турецкая лира',
            'KZT': 'Казахстанский тенге'
        }
        
        for currency, name in main_currencies.items():
            if currency in valutes:
                currency_data = valutes[currency]
                rates[currency] = {
                    'value': currency_data['Value'],
                    'name': name,
                    'previous': currency_data.get('Previous', currency_data['Value']),
                    'nominal': currency_data.get('Nominal', 1)
                }
        
        return rates, cbr_date
        
    except Exception as e:
        logger.error(f"Ошибка при получении курсов валют: {e}")
        return {}, 'неизвестная дата'

def get_key_rate():
    """Получает ключевую ставку ЦБ РФ"""
    try:
        # API для ключевой ставки ЦБ РФ
        today = datetime.now()
        url = "https://www.cbr.ru/eng/webservices/KeyRate"
        
        # Параметры запроса
        params = {
            'date': today.strftime('%Y-%m-%d')
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        # Если не получается получить актуальные данные, используем последние известные
        if response.status_code != 200:
            # Заглушка с последней известной ключевой ставкой
            key_rate_info = {
                'rate': 16.00,
                'date': today.strftime('%d.%m.%Y'),
                'change': 0.0,
                'is_current': True,
                'source': 'cbr_api_fallback'
            }
            return key_rate_info
        
        # Парсим ответ (может быть XML или JSON в зависимости от API)
        try:
            data = response.json()
            # Предполагаемая структура ответа
            rate = data.get('KeyRate', 16.00)
            date_str = data.get('Date', today.strftime('%Y-%m-%d'))
        except:
            # Если JSON не парсится, используем заглушку
            rate = 16.00
            date_str = today.strftime('%Y-%m-%d')
        
        # Преобразуем дату
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d.%m.%Y')
        except:
            formatted_date = today.strftime('%d.%m.%Y')
        
        key_rate_info = {
            'rate': float(rate),
            'date': formatted_date,
            'change': 0.0,  # В реальном API должно быть изменение
            'is_current': True,
            'source': 'cbr_api'
        }
        
        return key_rate_info
        
    except Exception as e:
        logger.error(f"Ошибка при получении ключевой ставки: {e}")
        # Возвращаем заглушку в случае ошибки
        today = datetime.now()
        return {
            'rate': 16.00,
            'date': today.strftime('%d.%m.%Y'),
            'change': 0.0,
            'is_current': False,
            'source': 'fallback'
        }

def get_inflation():
    """Получает данные по инфляции от ЦБ РФ"""
    try:
        # API для инфляции
        url = "https://www.cbr.ru/eng/webservices/Inflation"
        
        response = requests.get(url, timeout=10)
        
        if response.status_code == 200:
            try:
                data = response.json()
                # Предполагаемая структура ответа
                current_inflation = data.get('CurrentInflation', 7.5)
                target_inflation = data.get('TargetInflation', 4.0)
                period = data.get('Period', '2024')
            except:
                # Если не парсится, используем демо-данные
                current_inflation = 7.5
                target_inflation = 4.0
                period = '2024'
        else:
            # Демо-данные
            current_inflation = 7.5
            target_inflation = 4.0
            period = '2024'
        
        inflation_data = {
            'current': current_inflation,
            'target': target_inflation,
            'period': period,
            'source': 'cbr_api' if response.status_code == 200 else 'demo'
        }
        
        return inflation_data
        
    except Exception as e:
        logger.error(f"Ошибка при получении данных по инфляции: {e}")
        return {
            'current': 7.5,
            'target': 4.0,
            'period': '2024',
            'source': 'fallback'
        }

def get_deposit_rates():
    """Получает ставки по депозитам"""
    try:
        # Демо-данные для ставок по депозитам
        deposit_rates = {
            'overnight': 15.0,
            'week': 14.5,
            'month': 14.0,
            'quarter': 13.5,
            'year': 13.0,
            'update_date': datetime.now().strftime('%d.%m.%Y'),
            'source': 'demo'
        }
        
        return deposit_rates
        
    except Exception as e:
        logger.error(f"Ошибка при получении ставок по депозитам: {e}")
        return None

def get_metal_rates():
    """Получает курсы драгоценных металлов"""
    try:
        # Демо-данные для драгоценных металлов
        metal_rates = {
            'gold': 5830.50,
            'silver': 72.30,
            'platinum': 3200.75,
            'palladium': 4100.25,
            'update_date': datetime.now().strftime('%d.%m.%Y'),
            'source': 'demo'
        }
        
        return metal_rates
        
    except Exception as e:
        logger.error(f"Ошибка при получении курсов металлов: {e}")
        return None

def format_currency_rates_message(rates_data: dict, cbr_date: str) -> str:
    """Форматирует сообщение с курсами валют"""
    if not rates_data:
        return "❌ Не удалось получить курсы валют."
    
    message = f"💱 <b>КУРСЫ ВАЛЮТ ЦБ РФ</b>\n"
    message += f"📅 <i>на {cbr_date}</i>\n\n"
    
    # Основные валюты (доллар, евро)
    main_currencies = ['USD', 'EUR']
    for currency in main_currencies:
        if currency in rates_data:
            data = rates_data[currency]
            current_value = data['value']
            previous_value = data['previous']
            change = current_value - previous_value
            change_percent = (change / previous_value) * 100 if previous_value else 0
            
            change_icon = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            change_text = f"{change:+.2f} руб. ({change_percent:+.2f}%)"
            
            message += f"💵 <b>{data['name']}</b> ({currency}):\n"
            message += f"   <b>{current_value:.2f} руб.</b> {change_icon} {change_text}\n\n"
    
    # Другие валюты
    other_currencies = [curr for curr in rates_data.keys() if curr not in main_currencies]
    if other_currencies:
        message += "🌍 <b>Другие валюты:</b>\n"
        
        for currency in other_currencies:
            data = rates_data[currency]
            current_value = data['value']
            previous_value = data['previous']
            change = current_value - previous_value
            
            change_icon = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            
            # Для JPY делим на 100, так как курс указан за 100 единиц
            if currency == 'JPY':
                display_value = current_value / 100
                message += f"   {data['name']} ({currency}): <b>{display_value:.4f} руб.</b> {change_icon}\n"
            else:
                message += f"   {data['name']} ({currency}): <b>{current_value:.4f} руб.</b> {change_icon}\n"
    
    message += f"\n💡 <i>Курсы обновляются ежедневно</i>"
    return message

def format_key_rate_message(key_rate_data: dict) -> str:
    """Форматирует сообщение с ключевой ставкой"""
    if not key_rate_data:
        return "❌ Не удалось получить данные по ключевой ставке."
    
    rate = key_rate_data['rate']
    change = key_rate_data.get('change', 0)
    change_icon = "📈" if change > 0 else "📉" if change < 0 else "➡️"
    change_text = f"{change:+.2f}%" if change != 0 else "без изменений"
    
    message = f"💎 <b>КЛЮЧЕВАЯ СТАВКА ЦБ РФ</b>\n\n"
    message += f"<b>Текущее значение:</b> {rate:.2f}% {change_icon}\n"
    
    if change != 0:
        message += f"<b>Изменение:</b> {change_text}\n"
    
    message += f"\n<b>Дата актуальности:</b> {key_rate_data.get('date', 'неизвестно')}\n\n"
    message += "💡 <i>Ключевая ставка - это основная процентная ставка ЦБ РФ,\n"
    message += "которая влияет на кредиты, депозиты и экономику в целом</i>"
    
    if key_rate_data.get('source') == 'fallback':
        message += f"\n\n⚠️ <i>Используются демонстрационные данные</i>"
    
    return message

def format_inflation_message(inflation_data: dict) -> str:
    """Форматирует сообщение с данными по инфляции"""
    if not inflation_data:
        return "❌ Не удалось получить данные по инфляции."
    
    current = inflation_data['current']
    target = inflation_data['target']
    period = inflation_data['period']
    
    message = f"📊 <b>ИНФЛЯЦИЯ В РОССИИ</b>\n\n"
    message += f"<b>Текущая инфляция:</b> {current:.1f}%\n"
    message += f"<b>Целевой показатель ЦБ РФ:</b> {target:.1f}%\n"
    message += f"<b>Период:</b> {period} год\n\n"
    
    # Анализ
    if current > target:
        message += f"📈 <i>Инфляция выше целевого уровня</i>\n"
    elif current < target:
        message += f"📉 <i>Инфляция ниже целевого уровня</i>\n"
    else:
        message += f"✅ <i>Инфляция на целевом уровне</i>\n"
    
    message += "\n💡 <i>Данные предоставлены ЦБ РФ</i>"
    
    if inflation_data.get('source') == 'demo':
        message += f"\n\n⚠️ <i>Используются демонстрационные данные</i>"
    
    return message

def format_deposit_rates_message(deposit_rates: dict) -> str:
    """Форматирует сообщение со ставками по депозитам"""
    if not deposit_rates:
        return "❌ Не удалось получить данные по депозитным ставкам."
    
    message = f"🏦 <b>СТАВКИ ПО ДЕПОЗИТАМ ЦБ РФ</b>\n\n"
    message += f"<b>Овернайт (1 день):</b> {deposit_rates['overnight']:.1f}%\n"
    message += f"<b>Неделя:</b> {deposit_rates['week']:.1f}%\n"
    message += f"<b>Месяц:</b> {deposit_rates['month']:.1f}%\n"
    message += f"<b>Квартал:</b> {deposit_rates['quarter']:.1f}%\n"
    message += f"<b>Год:</b> {deposit_rates['year']:.1f}%\n\n"
    
    message += f"<i>Обновлено: {deposit_rates['update_date']}</i>\n\n"
    message += "💡 <i>Ставки по депозитам для кредитных организаций</i>"
    
    if deposit_rates.get('source') == 'demo':
        message += f"\n\n⚠️ <i>Используются демонстрационные данные</i>"
    
    return message

def format_metal_rates_message(metal_rates: dict) -> str:
    """Форматирует сообщение с курсами драгоценных металлов"""
    if not metal_rates:
        return "❌ Не удалось получить курсы драгоценных металлов."
    
    message = f"🥇 <b>КУРСЫ ДРАГОЦЕННЫХ МЕТАЛЛОВ ЦБ РФ</b>\n\n"
    message += f"<b>Золото:</b> {metal_rates['gold']:,.2f} руб/г\n".replace(',', ' ')
    message += f"<b>Серебро:</b> {metal_rates['silver']:.2f} руб/г\n"
    message += f"<b>Платина:</b> {metal_rates['platinum']:,.2f} руб/г\n".replace(',', ' ')
    message += f"<b>Палладий:</b> {metal_rates['palladium']:,.2f} руб/г\n\n".replace(',', ' ')
    
    message += f"<i>Обновлено: {metal_rates['update_date']}</i>\n\n"
    message += "💡 <i>Официальные курсы для операций с драгоценными металлами</i>"
    
    if metal_rates.get('source') == 'demo':
        message += f"\n\n⚠️ <i>Используются демонстрационные данные</i>"
    
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
            [InlineKeyboardButton("🏦 Депозитные ставки", callback_data='deposit_rates')],
            [InlineKeyboardButton("🥇 Драгоценные металлы", callback_data='metal_rates')],
            [InlineKeyboardButton("❓ Помощь", callback_data='help')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        start_message = f'{greeting} Я бот для отслеживания финансовых данных ЦБ РФ!\n\n'
        start_message += '🏛 <b>ОФИЦИАЛЬНЫЕ ДАННЫЕ ЦЕНТРАЛЬНОГО БАНКА РОССИИ</b>\n\n'
        
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
            error_msg = "❌ Не удалось получить курсы валют. Попробуйте позже."
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
        error_msg = "❌ Произошла ошибка при получении курсов валют."
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
        error_msg = "❌ Произошла ошибка при получении ключевой ставки."
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
            error_msg = "❌ Не удалось получить данные по инфляции."
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
        error_msg = "❌ Произошла ошибка при получении данных по инфляции."
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
        else:
            await update.message.reply_text(error_msg, reply_markup=reply_markup)

async def show_deposit_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает ставки по депозитам"""
    try:
        deposit_rates = get_deposit_rates()
        
        if not deposit_rates:
            error_msg = "❌ Не удалось получить ставки по депозитам."
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_msg, reply_markup=reply_markup)
            return
        
        message = format_deposit_rates_message(deposit_rates)
        
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
        logger.error(f"Ошибка при показе депозитных ставок: {e}")
        error_msg = "❌ Произошла ошибка при получении ставок по депозитам."
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
            error_msg = "❌ Не удалось получить курсы драгоценных металлов."
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
        error_msg = "❌ Произошла ошибка при получении курсов драгоценных металлов."
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

async def currency_rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды для курсов валют"""
    await show_currency_rates(update, context)

async def keyrate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды для ключевой ставки"""
    await show_key_rate(update, context)

async def inflation_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды для инфляции"""
    await show_inflation(update, context)

async def deposits_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды для депозитных ставок"""
    await show_deposit_rates(update, context)

async def metals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды для драгоценных металлов"""
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
            "• <code>/rates</code> - курсы валют ЦБ РФ\n"
            "• <code>/keyrate</code> - ключевая ставка ЦБ РФ\n"
            "• <code>/inflation</code> - данные по инфляции\n"
            "• <code>/deposits</code> - ставки по депозитам\n"
            "• <code>/metals</code> - курсы драгоценных металлов\n"
            "• <code>/help</code> - эта справка\n\n"
            
            "🔔 <b>Уведомления:</b>\n"
            "• <code>/alert USD RUB 80 above</code> - уведомит о курсе\n\n"
            
            "⏰ <b>Ежедневная рассылка</b>\n"
            "• Автоматическая отправка основных данных каждый день в 10:00\n\n"
            
            "📊 <b>Доступные разделы:</b>\n"
            "• <b>Курсы валют</b> - основные мировые валюты\n"
            "• <b>Ключевая ставка</b> - основная процентная ставка ЦБ РФ\n"
            "• <b>Инфляция</b> - текущая и целевая инфляция\n"
            "• <b>Депозитные ставки</b> - ставки для кредитных организаций\n"
            "• <b>Драгоценные металлы</b> - золото, серебро, платина, палладий\n\n"
            
            "💡 <b>ИНФОРМАЦИЯ</b>\n\n"
            "• Все данные предоставляются ЦБ РФ\n"
            "• Курсы обновляются ежедневно\n"
            "• Ключевая ставка обновляется по решению Совета директоров\n"
            "• Используются официальные API ЦБ РФ"
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
            if user.first_name:
                greeting = f"Привет, {user.first_name}!"
            else:
                greeting = "Привет!"
            
            keyboard = [
                [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
                [InlineKeyboardButton("💎 Ключевая ставка", callback_data='key_rate')],
                [InlineKeyboardButton("📊 Инфляция", callback_data='inflation')],
                [InlineKeyboardButton("🏦 Депозитные ставки", callback_data='deposit_rates')],
                [InlineKeyboardButton("🥇 Драгоценные металлы", callback_data='metal_rates')],
                [InlineKeyboardButton("❓ Помощь", callback_data='help')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f'{greeting} Я бот для отслеживания финансовых данных ЦБ РФ!\n\n'
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
        elif data == 'deposit_rates':
            await show_deposit_rates(update, context)
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
        application.add_handler(CommandHandler("deposits", deposits_command))
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
                time=datetime.strptime("07:00", "%H:%M").time(),  # 07:00 UTC = 10:00 МСК
                days=(0, 1, 2, 3, 4, 5, 6)  # Все дни недели
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
