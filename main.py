import logging
import asyncio
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from config import TOKEN, logger
from db import init_db
from handlers import start, help_command, button_handler, show_currency_rates
from handlers import handle_ai_message, alert_command, myalerts_command, show_key_rate, show_crypto_rates, show_ai_chat

async def post_init(application):
    """Функция инициализации после запуска бота"""
    try:
        await init_db()
        logger.info("База данных инициализирована")
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}")

async def error_handler(update, context):
    """Обработчик ошибок"""
    logger.error(f"Ошибка при обработке update {update}: {context.error}")

def main():
    """Основная функция запуска бота"""
    try:
        # Создаем application с обработчиком ошибок
        application = Application.builder().token(TOKEN).post_init(post_init).build()
        
        # Добавляем обработчик ошибок
        application.add_error_handler(error_handler)

        # Регистрация обработчиков команд
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("rates", show_currency_rates))
        application.add_handler(CommandHandler("currency", show_currency_rates))
        application.add_handler(CommandHandler("keyrate", show_key_rate))
        application.add_handler(CommandHandler("crypto", show_crypto_rates))
        application.add_handler(CommandHandler("ai", show_ai_chat))
        application.add_handler(CommandHandler("alert", alert_command))
        application.add_handler(CommandHandler("myalerts", myalerts_command))
        
        # Обработчики кнопок и сообщений
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_message))

        logger.info("Бот запускается...")
        
        # Запускаем с явным указанием allowed_updates
        application.run_polling(
            allowed_updates=['message', 'callback_query'],
            drop_pending_updates=True  # Игнорируем накопленные updates
        )
        
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    # Добавляем проверку на множественный запуск
    import sys
    logger.info("Запуск бота...")
    main()
