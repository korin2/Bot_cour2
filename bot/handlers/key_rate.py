from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
import logging

from bot.config import logger
from bot.handlers.keyboards import get_back_to_main_keyboard
from bot.services.cbr_api import get_key_rate

logger = logging.getLogger(__name__)

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

async def show_key_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает ключевую ставку ЦБ РФ"""
    try:
        key_rate_data = get_key_rate()
        
        if not key_rate_data:
            error_msg = "❌ Не удалось получить ключевую ставку ЦБ РФ."
            
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.message.reply_text(
                    error_msg,
                    reply_markup=get_back_to_main_keyboard()
                )
            else:
                await update.message.reply_text(
                    error_msg,
                    reply_markup=get_back_to_main_keyboard()
                )
            return
        
        message = format_key_rate_message(key_rate_data)
        
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                message, 
                parse_mode='HTML', 
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                message, 
                parse_mode='HTML', 
                reply_markup=reply_markup
            )
            
    except Exception as e:
        logger.error(f"Ошибка при показе ключевой ставки: {e}")
        error_msg = "❌ Произошла ошибка при получении ключевой ставки от ЦБ РФ."
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.reply_text(
                error_msg,
                reply_markup=get_back_to_main_keyboard()
            )
        else:
            await update.message.reply_text(
                error_msg,
                reply_markup=get_back_to_main_keyboard()
            )

async def keyrate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /keyrate"""
    await show_key_rate(update, context)

def setup_key_rate_handlers(application):
    """Настройка обработчиков ключевой ставки"""
    application.add_handler(CommandHandler("keyrate", keyrate_command))
