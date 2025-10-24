from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
import logging

from bot.config import logger
from bot.handlers.keyboards import get_back_to_main_keyboard
from bot.services.coingecko_api import get_crypto_rates, get_crypto_rates_fallback
from bot.utils.formatters import format_percentage_change

logger = logging.getLogger(__name__)

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
            
            name = data.get('name', 'N/A')
            symbol = data.get('symbol', 'N/A')
            price_rub = data.get('price_rub', 0)
            price_usd = data.get('price_usd', 0)
            change_24h = data.get('change_24h', 0)
            
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
            
            change_icon = "📈" if change_24h > 0 else "📉" if change_24h < 0 else "➡️"
            
            message += (
                f"   <b>{symbol}</b>: {price_rub:,.0f} руб. {change_icon}\n"
            )
    
    message += f"\n<i>Обновлено: {crypto_rates.get('update_time', 'неизвестно')}</i>\n\n"
    message += "💡 <i>Данные предоставлены CoinGecko API</i>"
    
    if crypto_rates.get('source') == 'coingecko':
        message += f"\n\n✅ <i>Официальные данные CoinGecko</i>"
    
    return message

async def show_crypto_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает курсы криптовалют"""
    try:
        # Показываем сообщение о загрузке
        loading_message = "🔄 <b>Загружаем курсы криптовалют...</b>"
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                loading_message, 
                parse_mode='HTML', 
                reply_markup=get_back_to_main_keyboard()
            )
        else:
            message = await update.message.reply_text(
                loading_message, 
                parse_mode='HTML', 
                reply_markup=get_back_to_main_keyboard()
            )
        
        # Получаем данные
        crypto_rates = get_crypto_rates()
        
        # Если не удалось получить данные, используем fallback
        if not crypto_rates:
            logger.warning("Не удалось получить данные от CoinGecko, используем fallback")
            crypto_rates = get_crypto_rates_fallback()
        
        if not crypto_rates:
            error_msg = (
                "❌ <b>Не удалось получить курсы криптовалют.</b>\n\n"
                "Возможные причины:\n"
                "• Проблемы с подключением к CoinGecko API\n"
                "• Превышены лимиты запросов\n"
                "• Временные технические работы\n\n"
                "Попробуйте позже."
            )
            
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(
                    error_msg, 
                    parse_mode='HTML', 
                    reply_markup=get_back_to_main_keyboard()
                )
            else:
                await message.edit_text(
                    error_msg, 
                    parse_mode='HTML', 
                    reply_markup=get_back_to_main_keyboard()
                )
            return
        
        message_text = format_crypto_rates_message(crypto_rates)
        
        # Добавляем предупреждение если используем демо-данные
        if crypto_rates.get('source') == 'demo_fallback':
            message_text += "\n\n⚠️ <i>Используются демонстрационные данные (CoinGecko API недоступен)</i>"
        
        from telegram import InlineKeyboardMarkup, InlineKeyboardButton
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data='crypto_rates')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                message_text, 
                parse_mode='HTML', 
                reply_markup=reply_markup
            )
        else:
            await message.edit_text(
                message_text, 
                parse_mode='HTML', 
                reply_markup=reply_markup
            )
            
    except Exception as e:
        logger.error(f"Ошибка при показе курсов криптовалют: {e}")
        error_msg = "❌ Произошла ошибка при получении курсов криптовалют."
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                error_msg,
                reply_markup=get_back_to_main_keyboard()
            )
        else:
            await update.message.reply_text(
                error_msg,
                reply_markup=get_back_to_main_keyboard()
            )

async def crypto_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /crypto"""
    await show_crypto_rates(update, context)

def setup_crypto_handlers(application):
    """Настройка обработчиков криптовалют"""
    application.add_handler(CommandHandler("crypto", crypto_command))
