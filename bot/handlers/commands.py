from telegram import Update
from telegram.ext import ContextTypes, CommandHandler
import logging
import os
import sys

# Добавляем корневую директорию в путь для импортов
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from bot.config import logger
from bot.handlers.keyboards import get_main_menu_keyboard
from bot.services.deepseek_api import ask_deepseek
from bot.services.cbr_api import get_key_rate
from db import update_user_info

logger = logging.getLogger(__name__)

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
        
        # Проверяем доступность ИИ
        test_ai = await ask_deepseek("test")
        ai_available = not (test_ai.startswith("❌") or test_ai.startswith("⏰"))
        
        start_message = f'{greeting} Я бот для отслеживания финансовых данных с универсальным ИИ помощником!\n\n'
        start_message += '🏛 <b>ОФИЦИАЛЬНЫЕ ДАННЫЕ ЦБ РФ + КРИПТОВАЛЮТЫ + УНИВЕРСАЛЬНЫЙ ИИ</b>\n\n'
        
        # Добавляем информацию о ключевой ставке в приветствие
        if key_rate_data and key_rate_data.get('is_current'):
            rate = key_rate_data['rate']
            start_message += f'💎 <b>Ключевая ставка ЦБ РФ:</b> <b>{rate:.2f}%</b>\n\n'
        
        if not ai_available:
            start_message += '⚠️ <i>ИИ помощник временно недоступен</i>\n\n'
            
        start_message += 'Выберите раздел из меню ниже:'
        
        await update.message.reply_text(
            start_message,
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard(ai_available)
        )
        
    except Exception as e:
        logger.error(f"Ошибка в команде /start: {e}")
        await update.message.reply_text("❌ Произошла ошибка при запуске бота. Пожалуйста, попробуйте еще раз.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    try:
        user = update.effective_user
        greeting = f", {user.first_name}!" if user.first_name else "!"
        
        help_text = (
            f"Привет{greeting} Я бот для отслеживания финансовых данных с универсальным ИИ помощником!\n\n"
            
            "🏛 <b>ОФИЦИАЛЬНЫЕ ДАННЫЕ ЦБ РФ + КРИПТОВАЛЮТЫ + УНИВЕРСАЛЬНЫЙ ИИ</b>\n\n"
            
            "💱 <b>Основные команды:</b>\n"
            "• <code>/start</code> - главное меню\n"
            "• <code>/rates</code> - курсы валют ЦБ РФ с прогнозом на завтра\n"
            "• <code>/crypto</code> - курсы криптовалют\n"
            "• <code>/keyrate</code> - ключевая ставка ЦБ РФ\n"
            "• <code>/ai</code> - Универсальный ИИ помощник\n"
            "• <code>/myalerts</code> - мои активные уведомления\n"
            "• <code>/debug_alerts</code> - отладка уведомлений\n"
            "• <code>/help</code> - эта справка\n\n"
            
            "🔔 <b>Уведомления:</b>\n"
            "• <code>/alert USD RUB 80 above</code> - уведомит когда USD выше 80 руб.\n"
            "• <code>/alert EUR RUB 90 below</code> - уведомит когда EUR ниже 90 руб.\n\n"
            
            "🤖 <b>Универсальный ИИ Помощник:</b>\n"
            "• Отвечает на вопросы по любым темам\n"
            "• Помогает с финансами, технологиями, образованием\n"
            "• Дает советы по творчеству, здоровью, путешествиям\n"
            "• Общается на любые темы\n\n"
            
            "⏰ <b>Автоматические уведомления</b>\n"
            "• Проверка условий каждые 30 минут\n"
            "• Автоматическое удаление после срабатывания\n\n"
            
            "💡 <b>ИНФОРМАЦИЯ</b>\n\n"
            "• Данные по ЦБ РФ предоставляются через официальные источники\n"
            "• Курсы криптовалют предоставляются CoinGecko API\n"
            "• ИИ помощник работает на основе DeepSeek AI\n"
            "• Курсы на завтра показываются только после публикации ЦБ РФ\n"
            "• Используются только проверенные источники данных"
        )
        
        await update.message.reply_text(
            help_text,
            parse_mode='HTML',
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в команде /help: {e}")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /stop"""
    try:
        user = update.effective_user
        greeting = f", {user.first_name}!" if user.first_name else "!"
        
        await update.message.reply_text(
            f"До свидания{greeting} Бот остановлен.\n"
            "Для возобновления работы отправьте /start",
            reply_markup=get_main_menu_keyboard()
        )
    except Exception as e:
        logger.error(f"Ошибка в команде /stop: {e}")

def setup_commands(application):
    """Настройка обработчиков команд"""
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stop", stop_command))
