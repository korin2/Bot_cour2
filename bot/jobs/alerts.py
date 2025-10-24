import logging
import os
import sys

# Добавляем корневую директорию в путь для импортов
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime
from telegram.ext import ContextTypes

from bot.config import logger, ALERT_CHECK_INTERVAL, DAILY_RATES_TIME
from bot.services.cbr_api import get_currency_rates_with_tomorrow
from db import get_all_active_alerts, remove_alert, get_all_users

logger = logging.getLogger(__name__)

async def check_alerts(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Проверка условий уведомлений"""
    try:
        logger.info("Начало проверки уведомлений")
        
        # Получаем текущие курсы валют
        rates_today, date_today, _, _ = get_currency_rates_with_tomorrow()
        
        if not rates_today:
            logger.error("Не удалось получить курсы для проверки уведомлений")
            return
        
        # Получаем все активные уведомления
        alerts = await get_all_active_alerts()
        
        if not alerts:
            logger.info("Нет активных уведомлений для проверки")
            return
        
        triggered_alerts = []
        
        for alert in alerts:
            try:
                from_curr = alert['from_currency'].upper()
                to_curr = alert['to_currency'].upper()
                threshold = float(alert['threshold'])
                direction = alert['direction']
                
                # Проверяем доступность валюты
                if from_curr not in rates_today:
                    logger.warning(f"Валюта {from_curr} не найдена в курсах для алерта {alert['id']}")
                    continue
                
                current_rate = rates_today[from_curr]['value']
                
                # Проверяем условие уведомления
                condition_met = False
                if direction == 'above':
                    condition_met = current_rate >= threshold
                elif direction == 'below':
                    condition_met = current_rate <= threshold
                
                if condition_met:
                    triggered_alerts.append((alert, current_rate))
                    
            except Exception as e:
                logger.error(f"Ошибка при проверке алерта {alert.get('id', 'unknown')}: {e}")
        
        # Отправляем уведомления и удаляем сработавшие алерты
        for alert, current_rate in triggered_alerts:
            try:
                user_id = alert['user_id']
                from_curr = alert['from_currency']
                to_curr = alert['to_currency']
                threshold = alert['threshold']
                direction = alert['direction']
                
                # Форматируем сообщение
                message = (
                    f"🔔 <b>СРАБОТАЛО УВЕДОМЛЕНИЕ!</b>\n\n"
                    f"💱 <b>{from_curr} → {to_curr}</b>\n"
                    f"📈 <b>Текущий курс:</b> {current_rate:.2f} руб.\n"
                    f"🎯 <b>Установленный порог:</b> {threshold} руб.\n"
                    f"📊 <b>Условие:</b> курс {'выше' if direction == 'above' else 'ниже'} {threshold} руб.\n\n"
                    f"<i>Уведомление удалено из системы</i>"
                )
                
                await context.bot.send_message(
                    chat_id=user_id,
                    text=message,
                    parse_mode='HTML'
                )
                
                # Удаляем сработавшее уведомление
                await remove_alert(alert['id'])
                logger.info(f"Отправлено уведомление пользователю {user_id} для {from_curr}")
                
            except Exception as e:
                logger.error(f"Ошибка при отправке уведомления для алерта {alert['id']}: {e}")
        
        logger.info(f"Проверка уведомлений завершена. Сработало: {len(triggered_alerts)}")
        
    except Exception as e:
        logger.error(f"Ошибка в функции проверки уведомлений: {e}")

async def send_daily_rates(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ежедневная отправка основных данных ЦБ РФ всем пользователям"""
    try:
        logger.info("Начало ежедневной рассылки данных ЦБ РФ")
        
        # Получаем основные данные
        rates_today, date_today, rates_tomorrow, changes = get_currency_rates_with_tomorrow()
        from bot.services.cbr_api import get_key_rate
        key_rate_data = get_key_rate()
        
        if not rates_today:
            logger.error("Не удалось получить данные для ежедневной рассылки")
            return
        
        # Форматируем сообщение
        message = f"🌅 <b>Ежедневное обновление данных ЦБ РФ</b>\n\n"
        
        if key_rate_data and key_rate_data.get('is_current'):
            rate = key_rate_data['rate']
            message += f"💎 <b>Ключевая ставка:</b> {rate:.2f}%\n\n"
        
        from bot.handlers.currency import format_currency_rates_message
        message += format_currency_rates_message(rates_today, date_today, rates_tomorrow, changes)
        
        # Получаем всех пользователей из базы данных
        users = await get_all_users()
        
        if not users:
            logger.info("Нет пользователей для рассылки")
            return
        
        logger.info(f"Начинаем рассылку для {len(users)} пользователей")
        
        # Отправляем сообщение каждому пользователю
        success_count = 0
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user['user_id'],
                    text=message,
                    parse_mode='HTML'
                )
                success_count += 1
                # Небольшая задержка чтобы не превысить лимиты Telegram
                import asyncio
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.warning(f"Не удалось отправить сообщение пользователю {user['user_id']}: {e}")
        
        logger.info(f"Ежедневная рассылка завершена. Успешно отправлено: {success_count}/{len(users)}")
        
    except Exception as e:
        logger.error(f"Ошибка в ежедневной рассылке: {e}")

def setup_jobs(application):
    """Настройка фоновых задач"""
    job_queue = application.job_queue
    
    if job_queue:
        # 10:00 МСК = 07:00 UTC
        from datetime import datetime
        job_queue.run_daily(
            send_daily_rates,
            time=datetime.strptime(DAILY_RATES_TIME, "%H:%M").time(),
            days=(0, 1, 2, 3, 4, 5, 6)
        )
        logger.info("Ежедневная рассылка настроена на 10:00 МСК (07:00 UTC)")
        
        # Проверка уведомлений каждые 30 минут
        job_queue.run_repeating(
            check_alerts, 
            interval=ALERT_CHECK_INTERVAL,
            first=10
        )
        logger.info("Проверка уведомлений настроена на каждые 30 минут")
    else:
        logger.warning("JobQueue не доступен. Ежедневная рассылка и проверка уведомлений не будут работать.")
