from telegram import Update
from telegram.ext import ContextTypes, MessageHandler, filters
import logging

from bot.config import logger
from bot.handlers.keyboards import get_back_to_main_keyboard
from bot.services.cbr_api import get_currency_rates_with_tomorrow, get_key_rate
from bot.services.coingecko_api import get_crypto_rates, get_crypto_rates_fallback

logger = logging.getLogger(__name__)

async def handle_financial_questions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает финансовые вопросы без ИИ API"""
    try:
        user_message = update.message.text.lower()
        
        # Простые ответы на частые вопросы
        responses = {
            'курс доллара': await get_simple_currency_response('USD'),
            'курс евро': await get_simple_currency_response('EUR'),
            'ключевая ставка': await get_simple_key_rate_response(),
            'биткоин': await get_simple_crypto_response('BTC'),
            'эфириум': await get_simple_crypto_response('ETH'),
            'криптовалюты': "Для просмотра курсов криптовалют используйте команду /crypto или нажмите '₿ Криптовалюты' в меню",
            'помощь': "Используйте /help для просмотра всех команд или меню для навигации",
        }
        
        response = None
        for key, value in responses.items():
            if key in user_message:
                response = value
                break
        
        if response:
            await update.message.reply_text(response, parse_mode='HTML')
        else:
            await update.message.reply_text(
                "🤖 <b>Финансовый помощник</b>\n\n"
                "К сожалению, функция ИИ временно недоступна.\n\n"
                "Вы можете:\n"
                "• 💱 Посмотреть курсы валют\n"
                "• ₿ Узнать курсы криптовалют\n"
                "• 💎 Проверить ключевую ставку\n"
                "• 🔔 Настроить уведомления\n\n"
                "Используйте меню для навигации!",
                parse_mode='HTML'
            )
            
    except Exception as e:
        logger.error(f"Ошибка в обработчике финансовых вопросов: {e}")

async def get_simple_currency_response(currency: str) -> str:
    """Возвращает простой ответ о курсе валюты"""
    try:
        rates_today, date_today, _, _ = get_currency_rates_with_tomorrow()
        if rates_today and currency in rates_today:
            rate = rates_today[currency]['value']
            name = rates_today[currency]['name']
            return f"💱 <b>{name}</b>\nТекущий курс: <b>{rate:.2f} руб.</b>\n\nДата: {date_today}"
        return "❌ Не удалось получить курс валюты"
    except Exception as e:
        logger.error(f"Ошибка при получении курса {currency}: {e}")
        return "❌ Ошибка при получении данных"

async def get_simple_key_rate_response() -> str:
    """Возвращает простой ответ о ключевой ставке"""
    try:
        key_rate_data = get_key_rate()
        if key_rate_data:
            rate = key_rate_data['rate']
            date = key_rate_data.get('date', 'неизвестно')
            return f"💎 <b>Ключевая ставка ЦБ РФ</b>\nТекущее значение: <b>{rate:.2f}%</b>\n\nДата: {date}"
        return "❌ Не удалось получить ключевую ставку"
    except Exception as e:
        logger.error(f"Ошибка при получении ключевой ставки: {e}")
        return "❌ Ошибка при получении данных"

async def get_simple_crypto_response(crypto: str) -> str:
    """Возвращает простой ответ о криптовалюте"""
    try:
        crypto_rates = get_crypto_rates() or get_crypto_rates_fallback()
        if crypto_rates:
            if crypto == 'BTC' and 'bitcoin' in crypto_rates:
                btc = crypto_rates['bitcoin']
                return f"₿ <b>Bitcoin (BTC)</b>\nКурс: <b>{btc['price_rub']:,.0f} руб.</b>\nИзменение 24ч: {btc['change_24h']:+.2f}%"
            elif crypto == 'ETH' and 'ethereum' in crypto_rates:
                eth = crypto_rates['ethereum']
                return f"🔷 <b>Ethereum (ETH)</b>\nКурс: <b>{eth['price_rub']:,.0f} руб.</b>\nИзменение 24ч: {eth['change_24h']:+.2f}%"
        return f"Для полной информации о {crypto} используйте команду /crypto"
    except Exception as e:
        logger.error(f"Ошибка при получении данных {crypto}: {e}")
        return "❌ Ошибка при получении данных"

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик неизвестных команд"""
    try:
        await update.message.reply_text(
            "❌ Неизвестная команда. Используйте /help для просмотра доступных команд.",
            reply_markup=get_back_to_main_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в обработчике неизвестных команд: {e}")

def setup_messages(application):
    """Настройка обработчиков сообщений"""
    # Обработчик для финансовых вопросов (fallback)
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, 
        handle_financial_questions
    ))
    
    # Обработчик для неизвестных команд
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
