import logging
from telegram.ext import ContextTypes
from datetime import datetime
from services import check_alerts, send_daily_rates, send_daily_weather
from config import logger

def setup_jobs(application):
    """Настройка фоновых задач"""
    job_queue = application.job_queue
    
    if job_queue:
        # Ежедневная рассылка курсов валют в 10:00 (07:00 UTC)
        job_queue.run_daily(
            send_daily_rates,
            time=datetime.strptime("07:00", "%H:%M").time(),
            days=(0, 1, 2, 3, 4, 5, 6),
            name="daily_rates"
        )
        
        # Ежедневная рассылка погоды в 08:00 (05:00 UTC)
        job_queue.run_daily(
            send_daily_weather,
            time=datetime.strptime("05:00", "%H:%M").time(),
            days=(0, 1, 2, 3, 4, 5, 6),
            name="daily_weather"
        )
        
        # Проверка уведомлений каждые 30 минут
        job_queue.run_repeating(check_alerts, interval=1800, first=10, name="check_alerts")
        
        logger.info("Фоновые задачи настроены")
    else:
        logger.warning("JobQueue не доступен")
