from telegram import Update
from telegram.ext import ContextTypes, CallbackQueryHandler
import logging

from bot.config import logger
from bot.handlers.keyboards import get_main_menu_keyboard
from bot.handlers.currency import show_currency_rates
from bot.handlers.crypto import show_crypto_rates
from bot.handlers.key_rate import show_key_rate
from bot.handlers.ai_chat import show_ai_chat, show_ai_examples, show_ai_unavailable
from bot.handlers.alerts import my_alerts_command, clear_all_alerts_handler
from bot.handlers.commands import help_command

logger = logging.getLogger(__name__)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик callback'ов от inline-кнопок"""
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == 'help':
            await help_command(update, context)
        elif data == 'back_to_main':
            # Деактивируем режим ИИ при возврате в главное меню
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
        elif data == 'ai_unavailable':
            await show_ai_unavailable(update, context)
        elif data == 'ai_examples':
            await show_ai_examples(update, context)
        elif data == 'my_alerts':
            await my_alerts_command(update, context)
        elif data == 'clear_all_alerts':
            await clear_all_alerts_handler(update, context)
        elif data == 'create_alert':
            # Показываем инструкцию по созданию уведомления
            from telegram import InlineKeyboardMarkup, InlineKeyboardButton
            help_text = (
                "📝 <b>СОЗДАНИЕ УВЕДОМЛЕНИЯ</b>\n\n"
                "Используйте команду:\n"
                "<code>/alert ВАЛЮТА RUB ПОРОГ above/below</code>\n\n"
                "💡 <b>Примеры:</b>\n"
                "• <code>/alert USD RUB 80 above</code> - уведомить когда USD выше 80 руб.\n"
                "• <code>/alert EUR RUB 90 below</code> - уведомить когда EUR ниже 90 руб.\n\n"
                "💱 <b>Доступные валюты:</b>\n"
                "USD, EUR, GBP, JPY, CNY, CHF, CAD, AUD, TRY, KZT\n\n"
                "Нажмите на пример выше чтобы скопировать команду!"
            )
            
            keyboard = [
                [InlineKeyboardButton("🔙 Назад к уведомлениям", callback_data='my_alerts')],
                [InlineKeyboardButton("🔙 В главное меню", callback_data='back_to_main')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(help_text, parse_mode='HTML', reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка в обработчике кнопок: {e}")

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает главное меню"""
    try:
        user = update.effective_user
        greeting = f"Привет, {user.first_name}!" if user.first_name else "Привет!"
        
        # Проверяем доступность ИИ
        from bot.services.deepseek_api import ask_deepseek
        test_ai = await ask_deepseek("test")
        ai_available = not (test_ai.startswith("❌") or test_ai.startswith("⏰"))
        
        await update.effective_message.edit_text(
            f'{greeting} Я бот для отслеживания финансовых данных с универсальным ИИ помощником!\n\n'
            '🏛 <b>ОФИЦИАЛЬНЫЕ ДАННЫЕ ЦБ РФ + КРИПТОВАЛЮТЫ + УНИВЕРСАЛЬНЫЙ ИИ</b>\n\n'
            'Выберите раздел из меню ниже:',
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(ai_available)
        )
    except Exception as e:
        logger.error(f"Ошибка при показе главного меню: {e}")

def setup_callbacks(application):
    """Настройка обработчиков callback'ов"""
    application.add_handler(CallbackQueryHandler(button_handler))
