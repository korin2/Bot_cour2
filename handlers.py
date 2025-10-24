import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import logger
from services import get_currency_rates_with_tomorrow, format_currency_rates_message, get_key_rate, format_key_rate_message
from services import get_crypto_rates, get_crypto_rates_fallback, format_crypto_rates_message, ask_deepseek
from utils import split_long_message, create_back_button
from db import get_user_alerts, clear_user_alerts, remove_alert, add_alert, update_user_info

# Основные команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    try:
        user = update.effective_user
        await update_user_info(user.id, user.first_name, user.username)
        
        greeting = f"Привет, {user.first_name}!" if user.first_name else "Привет!"
        
        # Проверяем доступность ИИ
        test_ai = await ask_deepseek("test", context)
        ai_available = not (test_ai.startswith("❌") or test_ai.startswith("⏰"))
        
        keyboard = [
            [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
            [InlineKeyboardButton("₿ Криптовалюты", callback_data='crypto_rates')],
            [InlineKeyboardButton("💎 Ключевая ставка", callback_data='key_rate')],
        ]
        
        if ai_available:
            keyboard.append([InlineKeyboardButton("🤖 Универсальный ИИ", callback_data='ai_chat')])
        else:
            keyboard.append([InlineKeyboardButton("❌ ИИ временно недоступен", callback_data='ai_unavailable')])
            
        keyboard.extend([
            [InlineKeyboardButton("🔔 Мои уведомления", callback_data='my_alerts')],
            [InlineKeyboardButton("❓ Помощь", callback_data='help')],
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        start_message = f'{greeting} Я бот для отслеживания финансовых данных!\n\nВыберите раздел:'
        await update.message.reply_text(start_message, parse_mode='HTML', reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Ошибка в команде /start: {e}")
        await update.message.reply_text("❌ Произошла ошибка при запуске бота.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    help_text = """
📚 **Доступные команды:**

/start - Главное меню
/rates - Курсы валют ЦБ РФ
/crypto - Курсы криптовалют  
/keyrate - Ключевая ставка ЦБ РФ
/ai - Чат с ИИ помощником
/myalerts - Мои уведомления
/alert - Создать уведомление
/help - Эта справка

💡 **Пример уведомления:**
/alert USD RUB 80 above - уведомит когда USD превысит 80 руб.
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

# Обработчики callback-кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на inline-кнопки"""
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == 'help':
            await help_command(update, context)
        elif data == 'back_to_main':
            context.user_data['ai_mode'] = False
            await show_main_menu(update, context)
        elif data == 'currency_rates':
            await show_currency_rates(update, context)
        elif data == 'crypto_rates':
            await show_crypto_rates(update, context)
        elif data == 'key_rate':
            await show_key_rate(update, context)
        elif data == 'ai_chat':
            await show_ai_chat(update, context)
        # ... остальные обработчики кнопок

    except Exception as e:
        logger.error(f"Ошибка в обработчике кнопок: {e}")

# Функции отображения данных
async def show_currency_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает курсы валют"""
    try:
        rates_today, date_today, rates_tomorrow, changes = get_currency_rates_with_tomorrow()
        
        if not rates_today:
            await update.effective_message.reply_text(
                "❌ Не удалось получить курсы валют.", 
                reply_markup=create_back_button()
            )
            return
        
        message = format_currency_rates_message(rates_today, date_today, rates_tomorrow, changes)
        await update.effective_message.reply_text(message, parse_mode='HTML', reply_markup=create_back_button())
        
    except Exception as e:
        logger.error(f"Ошибка при показе курсов валют: {e}")
        await update.effective_message.reply_text("❌ Ошибка при получении данных.")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает главное меню"""
    # ... реализация функции
    pass

# ... остальные обработчики из оригинального bot.py
