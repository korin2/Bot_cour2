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

def get_currency_rates(date_req=None):
    """Получает курсы валют от ЦБ РФ на определенную дату"""
    try:
        if date_req is None:
            date_req = datetime.now().strftime('%d/%m/%Y')
        
        # Официальное API ЦБ РФ для ежедневных курсов валют
        url = "https://www.cbr.ru/scripts/XML_daily.asp"
        params = {
            'date_req': date_req
        }
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
        # Парсим XML ответ
        root = ET.fromstring(response.content)
        
        # Получаем дату из атрибута
        cbr_date = root.get('Date', '')
        
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
            'R01700': 'TRY',  # Турецкая лира
            'R01335': 'KZT',  # Казахстанский тенге
        }
        
        for valute in root.findall('Valute'):
            valute_id = valute.get('ID')
            if valute_id in main_currencies:
                currency_code = main_currencies[valute_id]
                name = valute.find('Name').text
                value = float(valute.find('Value').text.replace(',', '.'))
                nominal = int(valute.find('Nominal').text)
                
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
        logger.error(f"Ошибка при получении курсов валют: {e}")
        return {}, 'неизвестная дата'

def get_key_rate():
    """Получает ключевую ставку ЦБ РФ"""
    try:
        # API для ключевой ставки ЦБ РФ
        url = "https://www.cbr.ru/scripts/XML_keyRate.asp"
        
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # Парсим XML ответ
        root = ET.fromstring(response.content)
        
        # Ищем все записи о ключевой ставке
        records = root.findall('Record')
        if records:
            # Берем самую последнюю запись (первую в списке)
            last_record = records[0]
            rate_date = last_record.get('Date')
            rate_value = float(last_record.find('Rate').text)
            
            # Преобразуем дату в формат DD.MM.YYYY
            date_obj = datetime.strptime(rate_date, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d.%m.%Y')
            
            key_rate_info = {
                'rate': rate_value,
                'date': formatted_date,
                'is_current': True,
                'source': 'cbr_official'
            }
            
            return key_rate_info
        else:
            logger.error("Не найдено записей о ключевой ставке в ответе API")
            return None
            
    except Exception as e:
        logger.error(f"Ошибка при получении ключевой ставки: {e}")
        return None

def get_inflation():
    """Получает данные по инфляции"""
    try:
        # Демо-данные для инфляции
        today = datetime.now()
        current_year = today.year
        
        inflation_data = {
            'current': 7.4,
            'period': f'{current_year}',
            'source': 'demo'
        }
        
        return inflation_data
        
    except Exception as e:
        logger.error(f"Ошибка при получении данных по инфляции: {e}")
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
    
    message += f"\n💡 <i>Официальные курсы ЦБ РФ обновляются ежедневно</i>"
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
    
    return message

def format_inflation_message(inflation_data: dict) -> str:
    """Форматирует сообщение с данными по инфляции"""
    if not inflation_data:
        return "❌ Не удалось получить данные по инфляции."
    
    current = inflation_data['current']
    period = inflation_data['period']
    
    message = f"📊 <b>ИНФЛЯЦИЯ В РОССИИ</b>\n\n"
    message += f"<b>Уровень инфляции:</b> {current:.1f}%\n"
    message += f"<b>Период:</b> {period}\n\n"
    
    if inflation_data.get('source') == 'demo':
        message += "⚠️ <i>Используются демонстрационные данные</i>\n\n"
    
    message += "💡 <i>Данные по инфляции</i>"
    
    return message

def format_metal_rates_message(metal_rates: dict) -> str:
    """Форматирует сообщение с курсами драгоценных металлов"""
    if not metal_rates:
        return "❌ Не удалось получить курсы драгоценных металлов."
    
    message = f"🥇 <b>КУРСЫ ДРАГОЦЕННЫХ МЕТАЛЛОВ</b>\n\n"
    
    metal_names = {
        'gold': 'Золото',
        'silver': 'Серебро', 
        'platinum': 'Платина',
        'palladium': 'Палладий'
    }
    
    for metal_code, metal_name in metal_names.items():
        if metal_code in metal_rates:
            data = metal_rates[metal_code]
            message += f"<b>{metal_name}:</b> {data:.2f} руб/г\n"
    
    message += f"\n<i>Обновлено: {metal_rates.get('update_date', 'неизвестно')}</i>\n\n"
    message += "💡 <i>Курсы драгоценных металлов</i>"
    
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
        
        # Главное меню
        keyboard = [
            [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
            [InlineKeyboardButton("💎 Ключевая ставка", callback_data='key_rate')],
            [InlineKeyboardButton("📊 Инфляция", callback_data='inflation')],
            [InlineKeyboardButton("🥇 Драгоценные металлы", callback_data='metal_rates')],
            [InlineKeyboardButton("❓ Помощь", callback_data='help')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        start_message = f'{greeting} Я бот для отслеживания финансовых данных!\n\n'
        start_message += '🏛 <b>ОСНОВНЫЕ ДАННЫЕ ЦБ РФ</b>\n\n'
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
    """Ежедневная отправка основных данных всем пользователям"""
    try:
        logger.info("Начало ежедневной рассылки данных")
        
        # Получаем основные данные
        rates_data, cbr_date = get_currency_rates()
        key_rate_data = get_key_rate()
        
        if not rates_data:
            logger.error("Не удалось получить данные для ежедневной рассылки")
            return
        
        # Форматируем сообщение
        message = f"🌅 <b>Ежедневное обновление данных</b>\n\n"
        
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

# Команды
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
            f"Привет{greeting} Я бот для отслеживания финансовых данных!\n\n"
            
            "🏛 <b>ОСНОВНЫЕ ДАННЫЕ ЦБ РФ</b>\n\n"
            
            "💱 <b>Основные команды:</b>\n"
            "• <code>/start</code> - главное меню\n"
            "• <code>/rates</code> - курсы валют ЦБ РФ\n"
            "• <code>/keyrate</code> - ключевая ставка ЦБ РФ\n"
            "• <code>/inflation</code> - данные по инфляции\n"
            "• <code>/metals</code> - курсы драгоценных металлов\n"
            "• <code>/help</code> - эта справка\n\n"
            
            "🔔 <b>Уведомления:</b>\n"
            "• <code>/alert USD RUB 80 above</code> - уведомит о курсе\n\n"
            
            "⏰ <b>Ежедневная рассылка</b>\n"
            "• Автоматическая отправка основных данных каждый день в 10:00\n\n"
            
            "📊 <b>Доступные разделы:</b>\n"
            "• <b>Курсы валют</b> - основные мировые валюты\n"
            "• <b>Ключевая ставка</b> - основная процентная ставка ЦБ РФ\n"
            "• <b>Инфляция</b> - текущий уровень инфляции\n"
            "• <b>Драгоценные металлы</b> - золото, серебро, платина, палладий\n\n"
            
            "💡 <b>ИНФОРМАЦИЯ</b>\n\n"
            "• Курсы валют и ключевая ставка - официальные данные ЦБ РФ\n"
            "• Инфляция и металлы - демонстрационные данные\n"
            "• Курсы обновляются ежедневно\n"
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
                [InlineKeyboardButton("🥇 Драгоценные металлы", callback_data='metal_rates')],
                [InlineKeyboardButton("❓ Помощь", callback_data='help')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f'{greeting} Я бот для отслеживания финансовых данных!\n\n'
                '🏛 <b>ОСНОВНЫЕ ДАННЫЕ ЦБ РФ</b>\n\n'
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
