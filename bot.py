import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from db import init_db, add_alert, update_user_info, get_all_users, get_user_alerts, remove_alert, get_all_active_alerts, clear_user_alerts
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

def get_key_rate():
    """Получает ключевую ставку ЦБ РФ через парсинг страницы"""
    try:
        url = "https://cbr.ru/hd_base/KeyRate/"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Ищем таблицу с ключевыми ставками
        table = soup.find('table', class_='data')
        if table:
            rows = table.find_all('tr')
            if len(rows) > 1:
                cells = rows[1].find_all('td')
                if len(cells) >= 2:
                    date_str = cells[0].get_text(strip=True)
                    rate_str = cells[1].get_text(strip=True).replace(',', '.')
                    
                    try:
                        date_obj = datetime.strptime(date_str, '%d.%m.%Y')
                        formatted_date = date_obj.strftime('%d.%m.%Y')
                        rate_value = float(rate_str)
                        
                        return {
                            'rate': rate_value,
                            'date': formatted_date,
                            'is_current': True,
                            'source': 'cbr_parsed'
                        }
                    except ValueError as e:
                        logger.error(f"Ошибка парсинга даты или ставки: {e}")
        
        logger.error("Не удалось найти данные о ключевой ставке на странице")
        return None
            
    except Exception as e:
        logger.error(f"Ошибка при получении ключевой ставки: {e}")
        return None

def get_inflation():
    """Получает данные по инфляции"""
    try:
        today = datetime.now()
        
        # Демо-данные по инфляции (в реальном приложении можно добавить парсинг)
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
        date_req = datetime.now().strftime('%d/%m/%Y')
        url = f"{CBR_API_BASE}scripts/XML_metall.asp"
        params = {'date_req': date_req}
        
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        
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

async def check_alerts(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверка условий уведомлений"""
    try:
        logger.info("Начало проверки уведомлений")
        
        # Получаем текущие курсы валют
        rates_today, date_today, _, _ = get_currency_rates_with_tomorrow()
        
        if not rates_today:
            logger.error("Не удалось получить курсы для проверки уведомлений")
            return
        
        # Получаем все активные уведомления
        alerts = await get_all_active_alerts()
        
        if not alerts:
            logger.info("Нет активных уведомлений для проверки")
            return
        
        triggered_alerts = []
        
        for alert in alerts:
            try:
                from_curr = alert['from_currency'].upper()
                to_curr = alert['to_currency'].upper()
                threshold = float(alert['threshold'])
                direction = alert['direction']
                
                # Проверяем доступность валюты
                if from_curr not in rates_today:
                    logger.warning(f"Валюта {from_curr} не найдена в курсах для алерта {alert['id']}")
                    continue
                
                current_rate = rates_today[from_curr]['value']
                
                # Проверяем условие уведомления
                condition_met = False
                if direction == 'above':
                    condition_met = current_rate >= threshold
                elif direction == 'below':
                    condition_met = current_rate <= threshold
                
                if condition_met:
                    triggered_alerts.append((alert, current_rate))
                    
            except Exception as e:
                logger.error(f"Ошибка при проверке алерта {alert.get('id', 'unknown')}: {e}")
        
        # Отправляем уведомления и удаляем сработавшие алерты
        for alert, current_rate in triggered_alerts:
            try:
                user_id = alert['user_id']
                from_curr = alert['from_currency']
                to_curr = alert['to_currency']
                threshold = alert['threshold']
                direction = alert['direction']
                
                # Форматируем сообщение
                message = (
                    f"🔔 <b>СРАБОТАЛО УВЕДОМЛЕНИЕ!</b>\n\n"
                    f"💱 <b>{from_curr} → {to_curr}</b>\n"
                    f"📈 <b>Текущий курс:</b> {current_rate:.2f} руб.\n"
                    f"🎯 <b>Установленный порог:</b> {threshold} руб.\n"
                    f"📊 <b>Условие:</b> курс {'выше' if direction == 'above' else 'ниже'} {threshold} руб.\n\n"
                    f"<i>Уведомление удалено из системы</i>"
                )
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='HTML'
                )
                
                # Удаляем сработавшее уведомление
                await remove_alert(alert['id'])
                logger.info(f"Отправлено уведомление пользователю {user_id} для {from_curr}")
                
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления для алерта {alert['id']}: {e}")
        
        logger.info(f"Проверка уведомлений завершена. Сработало: {len(triggered_alerts)}")
        
    except Exception as e:
        logger.error(f"Ошибка в функции проверки уведомлений: {e}")

async def my_alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает активные уведомления пользователя"""
    try:
        user_id = update.effective_user.id
        alerts = await get_user_alerts(user_id)
        
        if not alerts:
            message = "📭 <b>У вас нет активных уведомлений.</b>\n\n💡 Используйте /alert для создания нового уведомления."
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
            else:
                await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
            return
        
        message = "🔔 <b>ВАШИ АКТИВНЫЕ УВЕДОМЛЕНИЯ</b>\n\n"
        
        for i, alert in enumerate(alerts, 1):
            from_curr = alert['from_currency']
            to_curr = alert['to_currency']
            threshold = alert['threshold']
            direction = alert['direction']
            created_at = alert['created_at'].strftime('%d.%m.%Y %H:%M') if alert.get('created_at') else 'неизвестно'
            
            message += (
                f"{i}. <b>{from_curr}/{to_curr}</b>\n"
                f"   🎯 Порог: {threshold} руб.\n"
                f"   📊 Условие: курс {'выше' if direction == 'above' else 'ниже'}\n"
                f"   📅 Создано: {created_at}\n\n"
            )
        
        message += "⏰ <i>Уведомления проверяются каждые 30 минут</i>"
        
        keyboard = [
            [InlineKeyboardButton("🗑 Очистить все", callback_data='clear_all_alerts')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Ошибка в команде /myalerts: {e}")
        error_msg = "❌ Ошибка при получении уведомлений."
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg, reply_markup=reply_markup)
        else:
            await update.message.reply_text(error_msg, reply_markup=reply_markup)

async def clear_all_alerts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очищает все уведомления пользователя"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        alerts = await get_user_alerts(user_id)
        
        if not alerts:
            await query.edit_message_text("❌ У вас нет активных уведомлений для удаления.")
            return
        
        # Удаляем все уведомления пользователя
        await clear_user_alerts(user_id)
        
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            "✅ <b>Все ваши уведомления удалены.</b>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Ошибка при очистке уведомлений: {e}")
        await update.callback_query.edit_message_text("❌ Ошибка при удалении уведомлений.")

async def show_currency_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает курсы валют на сегодня и завтра"""
    try:
        rates_today, date_today, rates_tomorrow, changes = get_currency_rates_with_tomorrow()
        
        if not rates_today:
            error_msg = "❌ Не удалось получить курсы валют от ЦБ РФ. Попробуйте позже."
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_msg, reply_markup=reply_markup)
            return
        
        message = format_currency_rates_message(rates_today, date_today, rates_tomorrow, changes)
        
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

async def send_daily_rates(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ежедневная отправка основных данных ЦБ РФ всем пользователям"""
    try:
        logger.info("Начало ежедневной рассылки данных ЦБ РФ")
        
        # Получаем основные данные
        rates_today, date_today, rates_tomorrow, changes = get_currency_rates_with_tomorrow()
        key_rate_data = get_key_rate()
        
        if not rates_today:
            logger.error("Не удалось получить данные для ежедневной рассылки")
            return
        
        # Форматируем сообщение
        message = f"🌅 <b>Ежедневное обновление данных ЦБ РФ</b>\n\n"
        
        if key_rate_data and key_rate_data.get('is_current'):
            rate = key_rate_data['rate']
            message += f"💎 <b>Ключевая ставка:</b> {rate:.2f}%\n\n"
        
        message += format_currency_rates_message(rates_today, date_today, rates_tomorrow, changes)
        
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
            [InlineKeyboardButton("🔔 Мои уведомления", callback_data='my_alerts')],
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
            "• <code>/rates</code> - курсы валют ЦБ РФ с прогнозом на завтра\n"
            "• <code>/keyrate</code> - ключевая ставка ЦБ РФ\n"
            "• <code>/inflation</code> - данные по инфляции\n"
            "• <code>/metals</code> - курсы драгоценных металлов\n"
            "• <code>/myalerts</code> - мои активные уведомления\n"
            "• <code>/help</code> - эта справка\n\n"
            
            "🔔 <b>Уведомления:</b>\n"
            "• <code>/alert USD RUB 80 above</code> - уведомит когда USD выше 80 руб.\n"
            "• <code>/alert EUR RUB 90 below</code> - уведомит когда EUR ниже 90 руб.\n\n"
            
            "⏰ <b>Автоматические уведомления</b>\n"
            "• Проверка условий каждые 30 минут\n"
            "• Автоматическое удаление после срабатывания\n\n"
            
            "🌅 <b>Ежедневная рассылка</b>\n"
            "• Автоматическая отправка основных данных каждый день в 10:00\n\n"
            
            "📊 <b>Доступные разделы:</b>\n"
            "• <b>Курсы валют</b> - основные мировые валюты с прогнозом на завтра\n"
            "• <b>Ключевая ставка</b> - основная процентная ставка ЦБ РФ\n"
            "• <b>Инфляция</b> - текущий уровень инфляции\n"
            "• <b>Драгоценные металлы</b> - золото, серебро, платина, палладий\n\n"
            
            "💡 <b>ИНФОРМАЦИЯ</b>\n\n"
            "• Все данные предоставляются через официальные источники ЦБ РФ\n"
            "• Курсы на завтра показываются только после публикации ЦБ РФ\n"
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
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "📝 <b>Использование:</b> /alert &lt;из&gt; &lt;в&gt; &lt;порог&gt; &lt;above|below&gt;\n\n"
                "💡 <b>Примеры:</b>\n"
                "• <code>/alert USD RUB 80 above</code> - уведомить когда USD выше 80 руб.\n"
                "• <code>/alert EUR RUB 90 below</code> - уведомить когда EUR ниже 90 руб.\n\n"
                "💱 <b>Доступные валюты:</b> USD, EUR, GBP, JPY, CNY, CHF, CAD, AUD, TRY, KZT",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return
        
        from_curr, to_curr = args[0].upper(), args[1].upper()
        
        # Проверяем поддерживаемые валюты
        supported_currencies = ['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CHF', 'CAD', 'AUD', 'TRY', 'KZT']
        if from_curr not in supported_currencies:
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"❌ Валюта {from_curr} не поддерживается.\n\n"
                f"💱 <b>Доступные валюты:</b> {', '.join(supported_currencies)}",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return
        
        # Проверяем, что целевая валюта - RUB
        if to_curr != 'RUB':
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "❌ В настоящее время поддерживаются только уведомления для пар с RUB.\n"
                "💡 Используйте: /alert USD RUB 80 above",
                reply_markup=reply_markup
            )
            return
        
        try:
            threshold = float(args[2])
            if threshold <= 0:
                raise ValueError("Порог должен быть положительным числом")
        except ValueError:
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "❌ Порог должен быть положительным числом.",
                reply_markup=reply_markup
            )
            return
        
        direction = args[3].lower()
        if direction not in ['above', 'below']:
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "❌ Направление должно быть 'above' или 'below'.",
                reply_markup=reply_markup
            )
            return
        
        user_id = update.effective_message.from_user.id
        await add_alert(user_id, from_curr, to_curr, threshold, direction)
        
        keyboard = [
            [InlineKeyboardButton("📋 Мои уведомления", callback_data='my_alerts')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"✅ <b>УВЕДОМЛЕНИЕ УСТАНОВЛЕНО!</b>\n\n"
            f"💱 <b>Пара:</b> {from_curr}/{to_curr}\n"
            f"🎯 <b>Порог:</b> {threshold} руб.\n"
            f"📊 <b>Условие:</b> курс {'выше' if direction == 'above' else 'ниже'} {threshold} руб.\n\n"
            f"💡 Уведомление будет проверяться каждые 30 минут",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка в команде /alert: {e}")
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "❌ Произошла ошибка при установке уведомления.",
            reply_markup=reply_markup
        )

async def myalerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await my_alerts_command(update, context)

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
                [InlineKeyboardButton("🔔 Мои уведомления", callback_data='my_alerts')],
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
        elif data == 'my_alerts':
            await my_alerts_command(update, context)
        elif data == 'clear_all_alerts':
            await clear_all_alerts_handler(update, context)
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
        application.add_handler(CommandHandler("myalerts", myalerts_command))
        
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
            
            # Проверка уведомлений каждые 30 минут
            job_queue.run_repeating(
                check_alerts, 
                interval=1800,  # 30 минут в секундах
                first=10        # Первая проверка через 10 секунд после запуска
            )
            logger.info("Проверка уведомлений настроена на каждые 30 минут")
        else:
            logger.warning("JobQueue не доступен. Ежедневная рассылка и проверка уведомлений не будут работать.")

        # Запуск бота
        logger.info("Бот запускается...")
        application.run_polling()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    main()
