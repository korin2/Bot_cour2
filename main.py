import logging
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

def main():
    """Основная функция запуска бота"""
    try:
        application = Application.builder().token(TOKEN).post_init(post_init).build()

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
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    main()
