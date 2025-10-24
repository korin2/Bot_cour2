import os
import sys
import logging

# Добавляем корневую директорию в путь для импортов
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram.ext import Application

from bot.config import TOKEN, logger
from bot.handlers.commands import setup_commands
from bot.handlers.callbacks import setup_callbacks
from bot.handlers.messages import setup_messages
from bot.handlers.currency import setup_currency_handlers
from bot.handlers.crypto import setup_crypto_handlers
from bot.handlers.key_rate import setup_key_rate_handlers
from bot.handlers.ai_chat import setup_ai_handlers
from bot.handlers.alerts import setup_alerts_handlers
from bot.jobs.alerts import setup_jobs
from db import init_db

async def post_init(application: Application) -> None:
    """Функция, выполняемая после инициализации бота"""
    try:
        await init_db()
        logger.info("БД инициализирована успешно")
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}")

def setup_application():
    """Настройка и создание application"""
    application = Application.builder().token(TOKEN).post_init(post_init).build()

    # Настройка обработчиков
    setup_commands(application)
    setup_currency_handlers(application)
    setup_crypto_handlers(application)
    setup_key_rate_handlers(application)
    setup_ai_handlers(application)
    setup_alerts_handlers(application)
    setup_callbacks(application)
    setup_messages(application)
    
    # Настройка фоновых задач
    setup_jobs(application)
    
    return application

def main() -> None:
    """Основная функция для запуска бота"""
    try:
        application = setup_application()
        
        # Запуск бота
        logger.info("Бот запускается...")
        application.run_polling()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
