import os
import sys
import logging
import asyncio
import signal
from telegram.ext import Application

# Добавляем корневую директорию в путь для импортов
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
from bot.db import init_db

class BotRunner:
    def __init__(self):
        self.application = None
        self.shutdown_event = asyncio.Event()

    async def post_init(self, application: Application) -> None:
        """Функция, выполняемая после инициализации бота"""
        try:
            await init_db()
            logger.info("БД инициализирована успешно")
        except Exception as e:
            logger.error(f"Ошибка при инициализации БД: {e}")

    def setup_application(self):
        """Настройка и создание application"""
        self.application = Application.builder().token(TOKEN).post_init(self.post_init).build()

        # Настройка обработчиков
        setup_commands(self.application)
        setup_currency_handlers(self.application)
        setup_crypto_handlers(self.application)
        setup_key_rate_handlers(self.application)
        setup_ai_handlers(self.application)
        setup_alerts_handlers(self.application)
        setup_callbacks(self.application)
        setup_messages(self.application)
        
        # Настройка фоновых задач
        setup_jobs(self.application)
        
        return self.application

    async def shutdown(self, signal=None):
        """Graceful shutdown"""
        if signal:
            logger.info(f"Получен сигнал {signal.name}")
        
        logger.info("Остановка бота...")
        
        if self.application:
            if self.application.updater and self.application.updater.running:
                self.application.updater.stop()
            
            if self.application.job_queue and self.application.job_queue.running:
                self.application.job_queue.stop()
            
            if self.application.running:
                await self.application.stop()
            
            await self.application.shutdown()
        
        self.shutdown_event.set()

    async def main_async(self) -> None:
        """Асинхронная основная функция для запуска бота"""
        try:
            # Настройка обработчиков сигналов (только на Unix-системах)
            if os.name != 'nt':  # Не Windows
                loop = asyncio.get_running_loop()
                for sig in [signal.SIGTERM, signal.SIGINT]:
                    loop.add_signal_handler(
                        sig, 
                        lambda s=sig: asyncio.create_task(self.shutdown(s))
                    )
            
            # Настройка приложения
            self.setup_application()
            
            # Запуск бота
            logger.info("Бот запускается...")
            await self.application.initialize()
            await self.application.start()
            
            # Запуск polling с обработкой конфликтов
            await self.application.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=['message', 'callback_query'],
                timeout=10,
                pool_timeout=10,
                connect_timeout=10,
                read_timeout=10
            )
            
            logger.info("Бот успешно запущен и готов к работе!")
            
            # Ожидание события shutdown
            await self.shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}")
            await self.shutdown()
            raise

def main() -> None:
    """Основная функция для запуска бота"""
    runner = BotRunner()
    
    try:
        asyncio.run(runner.main_async())
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
