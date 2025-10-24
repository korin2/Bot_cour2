import logging
import signal
import asyncio
import sys
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters
from config import TOKEN, logger
from db import init_db
from handlers import start, help_command, button_handler, show_currency_rates
from handlers import handle_ai_message, alert_command, myalerts_command, show_key_rate, show_crypto_rates, show_ai_chat

class BotManager:
    def __init__(self):
        self.application = None
        self.is_running = False

    async def post_init(self, application):
        """Функция инициализации после запуска бота"""
        try:
            await init_db()
            logger.info("База данных инициализирована")
        except Exception as e:
            logger.error(f"Ошибка при инициализации БД: {e}")

    async def shutdown(self, signal=None):
        """Корректное завершение работы бота"""
        if self.is_running:
            logger.info("Получен сигнал завершения...")
            self.is_running = False
            if self.application:
                await self.application.stop()
                await self.application.shutdown()
            logger.info("Бот остановлен")
            sys.exit(0)

    def setup_signal_handlers(self):
        """Настройка обработчиков сигналов"""
        for sig in [signal.SIGTERM, signal.SIGINT]:
            signal.signal(sig, lambda s, f: asyncio.create_task(self.shutdown()))

    async def run(self):
        """Основная функция запуска бота"""
        try:
            self.setup_signal_handlers()
            
            self.application = Application.builder().token(TOKEN).post_init(self.post_init).build()
            self.is_running = True

            # Регистрация обработчиков команд
            self.application.add_handler(CommandHandler("start", start))
            self.application.add_handler(CommandHandler("help", help_command))
            self.application.add_handler(CommandHandler("rates", show_currency_rates))
            self.application.add_handler(CommandHandler("currency", show_currency_rates))
            self.application.add_handler(CommandHandler("keyrate", show_key_rate))
            self.application.add_handler(CommandHandler("crypto", show_crypto_rates))
            self.application.add_handler(CommandHandler("ai", show_ai_chat))
            self.application.add_handler(CommandHandler("alert", alert_command))
            self.application.add_handler(CommandHandler("myalerts", myalerts_command))
            
            # Обработчики кнопок и сообщений
            self.application.add_handler(CallbackQueryHandler(button_handler))
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_message))

            logger.info("Бот запускается...")
            await self.application.run_polling()
            
        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}")
            await self.shutdown()

def main():
    """Точка входа"""
    bot_manager = BotManager()
    
    try:
        # Запускаем бота
        asyncio.run(bot_manager.run())
    except KeyboardInterrupt:
        logger.info("Получен сигнал KeyboardInterrupt")
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}")
    finally:
        # Гарантируем завершение
        asyncio.run(bot_manager.shutdown())

if __name__ == '__main__':
    main()
