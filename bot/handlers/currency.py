from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
import logging

from bot.config import logger
from bot.handlers.keyboards import get_back_to_main_keyboard
from bot.services.cbr_api import get_currency_rates_with_tomorrow
from bot.utils.formatters import format_currency_display

logger = logging.getLogger(__name__)

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
        from datetime import datetime, timedelta
        tomorrow_date = (datetime.now() + timedelta(days=1)).strftime('%d.%m.%Y')
        message += f"\n📊 <i>Курсы на завтра ({tomorrow_date}) опубликованы ЦБ РФ</i>"
    else:
        message += f"\n💡 <i>Курсы на завтра будут опубликованы ЦБ РФ позже</i>"
    
    message += f"\n\n💡 <i>Официальные курсы ЦБ РФ с прогнозом на завтра</i>"
    return message

async def show_currency_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает курсы валют на сегодня и завтра"""
    try:
        rates_today, date_today, rates_tomorrow, changes = get_currency_rates_with_tomorrow()
        
        if not rates_today:
            error_msg = "❌ Не удалось получить курсы валют от ЦБ РФ. Попробуйте позже."
            await update.effective_message.reply_text(
                error_msg,
                reply_markup=get_back_to_main_keyboard()
            )
            return
        
        message = format_currency_rates_message(rates_today, date_today, rates_tomorrow, changes)
        
        await update.effective_message.edit_text(
            message, 
            parse_mode='HTML', 
            reply_markup=get_back_to_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка при показе курсов валют: {e}")
        error_msg = "❌ Произошла ошибка при получении курсов валют от ЦБ РФ."
        await update.effective_message.reply_text(
            error_msg,
            reply_markup=get_back_to_main_keyboard()
        )

async def rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /rates"""
    await show_currency_rates(update, context)

async def currency_rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /currency"""
    await show_currency_rates(update, context)

def setup_currency_handlers(application):
    """Настройка обработчиков валют"""
    application.add_handler(CommandHandler("rates", rates_command))
    application.add_handler(CommandHandler("currency", currency_rates_command))
