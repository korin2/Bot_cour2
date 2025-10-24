import logging
from telegram.ext import ContextTypes
from datetime import datetime
from services import check_alerts, send_daily_rates
from config import logger

def setup_jobs(application):
    """Настройка фоновых задач"""
    job_queue = application.job_queue
    
    if job_queue:
        # Ежедневная рассылка в 10:00 (07:00 UTC)
        job_queue.run_daily(
            send_daily_rates,
            time=datetime.strptime("07:00", "%H:%M").time(),
            days=(0, 1, 2, 3, 4, 5, 6)
        )
        
        # Проверка уведомлений каждые 30 минут
        job_queue.run_repeating(check_alerts, interval=1800, first=10)
        
        logger.info("Фоновые задачи настроены")
    else:
        logger.warning("JobQueue не доступен")
