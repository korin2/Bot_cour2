import logging
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters

from bot.config import TOKEN
from bot.handlers.commands import setup_commands
from bot.handlers.callbacks import setup_callbacks
from bot.handlers.messages import setup_messages
from bot.jobs.alerts import setup_jobs
from database.db import init_db

logger = logging.getLogger(__name__)

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
        application = Application.builder().token(TOKEN).post_init(post_init).build()

        # Настройка обработчиков
        setup_commands(application)
        setup_callbacks(application)
        setup_messages(application)
        
        # Настройка фоновых задач
        setup_jobs(application)

        # Запуск бота
        logger.info("Бот запускается...")
        application.run_polling()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    main()
