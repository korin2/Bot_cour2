from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler
import logging

from bot.config import logger, SUPPORTED_CURRENCIES
from bot.handlers.keyboards import get_back_to_main_keyboard, get_alerts_keyboard
from bot.services.cbr_api import get_currency_rates_with_tomorrow
from bot.db import add_alert, get_user_alerts, clear_user_alerts, get_all_active_alerts, remove_alert  # Измененный импорт

logger = logging.getLogger(__name__)

# ... остальной код без изменений ...

async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Создание уведомления о курсе валюты"""
    try:
        args = context.args
        
        # Логируем аргументы для отладки
        logger.info(f"Команда /alert с аргументами: {args}")
        
        if len(args) != 4:
            keyboard = [
                [InlineKeyboardButton("📋 Мои уведомления", callback_data='my_alerts')],
                [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                "📝 <b>Использование:</b> /alert &lt;из&gt; &lt;в&gt; &lt;порог&gt; &lt;above|below&gt;\n\n"
                "💡 <b>Примеры:</b>\n"
                "• <code>/alert USD RUB 80 above</code> - уведомить когда USD выше 80 руб.\n"
                "• <code>/alert EUR RUB 90 below</code> - уведомить когда EUR ниже 90 руб.\n\n"
                "💱 <b>Доступные валюты:</b> {', '.join(SUPPORTED_CURRENCIES)}\n\n"
                "Нажмите на пример чтобы скопировать!",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return
        
        from_curr, to_curr = args[0].upper(), args[1].upper()
        
        # Проверяем поддерживаемые валюты
        if from_curr not in SUPPORTED_CURRENCIES:
            await update.message.reply_text(
                f"❌ Валюта <b>{from_curr}</b> не поддерживается.\n\n"
                f"💱 <b>Доступные валюты:</b> {', '.join(SUPPORTED_CURRENCIES)}",
                parse_mode='HTML',
                reply_markup=get_back_to_main_keyboard()
            )
            return
        
        # Проверяем, что целевая валюта - RUB
        if to_curr != 'RUB':
            await update.message.reply_text(
                "❌ В настоящее время поддерживаются только уведомления для пар с RUB.\n"
                "💡 Используйте: <code>/alert USD RUB 80 above</code>",
                parse_mode='HTML',
                reply_markup=get_back_to_main_keyboard()
            )
            return
        
        try:
            threshold = float(args[2])
            if threshold <= 0:
                raise ValueError("Порог должен быть положительным числом")
        except ValueError:
            await update.message.reply_text(
                "❌ Порог должен быть положительным числом.",
                reply_markup=get_back_to_main_keyboard()
            )
            return
        
        direction = args[3].lower()
        if direction not in ['above', 'below']:
            await update.message.reply_text(
                "❌ Направление должно быть 'above' или 'below'.",
                reply_markup=get_back_to_main_keyboard()
            )
            return
        
        user_id = update.effective_message.from_user.id
        
        # Логируем перед добавлением
        logger.info(f"Добавление уведомления: user_id={user_id}, {from_curr}/{to_curr} {threshold} {direction}")
        
        # Добавляем уведомление
        await add_alert(user_id, from_curr, to_curr, threshold, direction)
        
        # Получаем текущий курс для информации
        rates_today, _, _, _ = get_currency_rates_with_tomorrow()
        current_rate = "N/A"
        if rates_today and from_curr in rates_today:
            current_rate = f"{rates_today[from_curr]['value']:.2f}"
        
        keyboard = [
            [InlineKeyboardButton("📋 Мои уведомления", callback_data='my_alerts')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        success_message = (
            f"✅ <b>УВЕДОМЛЕНИЕ УСТАНОВЛЕНО!</b>\n\n"
            f"💱 <b>Пара:</b> {from_curr}/{to_curr}\n"
            f"🎯 <b>Порог:</b> {threshold} руб.\n"
            f"📊 <b>Условие:</b> курс <b>{'выше' if direction == 'above' else 'ниже'}</b> {threshold} руб.\n"
            f"💹 <b>Текущий курс:</b> {current_rate} руб.\n\n"
            f"💡 Уведомление будет проверяться каждые 30 минут\n"
            f"🔔 При срабатывании вы получите сообщение"
        )
        
        await update.message.reply_text(
            success_message,
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
    except Exception as e:
        logger.error(f"Ошибка в команде /alert: {e}")
        await update.message.reply_text(
            f"❌ Произошла ошибка при установке уведомления:\n<code>{str(e)}</code>",
            parse_mode='HTML',
            reply_markup=get_back_to_main_keyboard()
        )

async def my_alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает активные уведомления пользователя"""
    try:
        user_id = update.effective_user.id
        logger.info(f"Запрос уведомлений для пользователя {user_id}")
        
        alerts = await get_user_alerts(user_id)
        
        if not alerts:
            message = "📭 <b>У вас нет активных уведомлений.</b>\n\n"
            message += "💡 Используйте команду:\n"
            message += "<code>/alert USD RUB 80 above</code>\n"
            message += "чтобы создать уведомление, когда курс USD превысит 80 рублей"
            
            keyboard = [
                [InlineKeyboardButton("💱 Создать уведомление", callback_data='create_alert')],
                [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(
                    message, 
                    parse_mode='HTML', 
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    message, 
                    parse_mode='HTML', 
                    reply_markup=reply_markup
                )
            return
        
        message = "🔔 <b>ВАШИ АКТИВНЫЕ УВЕДОМЛЕНИЯ</b>\n\n"
        
        for i, alert in enumerate(alerts, 1):
            from_curr = alert['from_currency']
            to_curr = alert['to_currency']
            threshold = alert['threshold']
            direction = alert['direction']
            
            # Получаем текущий курс для сравнения
            rates_today, _, _, _ = get_currency_rates_with_tomorrow()
            current_rate = "N/A"
            if rates_today and from_curr in rates_today:
                current_rate = f"{rates_today[from_curr]['value']:.2f}"
            
            message += (
                f"{i}. <b>{from_curr} → {to_curr}</b>\n"
                f"   🎯 Порог: <b>{threshold} руб.</b>\n"
                f"   📊 Условие: курс <b>{'выше' if direction == 'above' else 'ниже'}</b> {threshold} руб.\n"
                f"   💱 Текущий курс: <b>{current_rate} руб.</b>\n"
            )
            
            # Добавляем индикатор выполнения
            if current_rate != "N/A":
                current_value = float(current_rate)
                threshold_value = float(threshold)
                if direction == 'above' and current_value >= threshold_value:
                    message += "   ✅ <b>УСЛОВИЕ ВЫПОЛНЕНО!</b>\n"
                elif direction == 'below' and current_value <= threshold_value:
                    message += "   ✅ <b>УСЛОВИЕ ВЫПОЛНЕНО!</b>\n"
                else:
                    progress = abs(current_value - threshold_value)
                    message += f"   📈 Осталось: <b>{progress:.2f} руб.</b>\n"
            
            message += "\n"
        
        message += "⏰ <i>Уведомления проверяются каждые 30 минут автоматически</i>\n"
        message += "💡 <i>При срабатывании уведомление автоматически удаляется</i>"
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                message, 
                parse_mode='HTML', 
                reply_markup=get_alerts_keyboard()
            )
        else:
            await update.message.reply_text(
                message, 
                parse_mode='HTML', 
                reply_markup=get_alerts_keyboard()
            )
        
    except Exception as e:
        logger.error(f"Ошибка в команде /myalerts: {e}")
        error_msg = (
            "❌ <b>Ошибка при получении уведомлений.</b>\n\n"
            "Попробуйте позже или используйте команду /debug_alerts для диагностики."
        )
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                error_msg, 
                parse_mode='HTML', 
                reply_markup=get_back_to_main_keyboard()
            )
        else:
            await update.message.reply_text(
                error_msg, 
                parse_mode='HTML', 
                reply_markup=get_back_to_main_keyboard()
            )

async def clear_all_alerts_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Очищает все уведомления пользователя"""
    try:
        query = update.callback_query
        await query.answer()
        
        user_id = query.from_user.id
        alerts = await get_user_alerts(user_id)
        
        if not alerts:
            await query.edit_message_text("❌ У вас нет активных уведомлений для удаления.")
            return
        
        # Удаляем все уведомления пользователя
        await clear_user_alerts(user_id)
        
        await query.edit_message_text(
            "✅ <b>Все ваши уведомления удалены.</b>",
            parse_mode='HTML',
            reply_markup=get_back_to_main_keyboard()
        )
        
    except Exception as e:
        logger.error(f"Ошибка при очистке уведомлений: {e}")
        await update.callback_query.edit_message_text("❌ Ошибка при удалении уведомлений.")

async def debug_alerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отладочная команда для проверки уведомлений"""
    try:
        user_id = update.effective_user.id
        logger.info(f"Отладочная проверка уведомлений для user_id: {user_id}")
        
        # Прямой запрос к базе для отладки
        import asyncpg
        import os
        conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
        
        # Проверяем существование таблицы
        table_exists = await conn.fetchval(
            "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'alerts')"
        )
        logger.info(f"Таблица alerts существует: {table_exists}")
        
        # Проверяем все уведомления пользователя
        alerts = await conn.fetch(
            "SELECT * FROM alerts WHERE user_id = $1 ORDER BY id DESC",
            user_id
        )
        
        # Проверяем структуру таблицы
        table_structure = await conn.fetch(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'alerts'"
        )
        
        await conn.close()
        
        # Формируем отладочное сообщение
        message = f"🔧 <b>ОТЛАДКА УВЕДОМЛЕНИЙ</b>\n\n"
        message += f"<b>User ID:</b> {user_id}\n"
        message += f"<b>Таблица существует:</b> {table_exists}\n\n"
        
        message += "<b>Структура таблицы alerts:</b>\n"
        for col in table_structure:
            message += f"  {col['column_name']} ({col['data_type']})\n"
        
        message += f"\n<b>Найдено уведомлений:</b> {len(alerts)}\n\n"
        
        for i, alert in enumerate(alerts, 1):
            message += f"<b>Уведомление {i}:</b>\n"
            for key, value in alert.items():
                message += f"  {key}: {value}\n"
            message += "\n"
        
        if not alerts:
            message += "❌ Уведомлений не найдено в базе данных\n"
            message += "💡 Проверьте:\n"
            message += "1. Команда /alert выполнена корректно\n"
            message += "2. База данных подключена\n"
            message += "3. Таблица alerts создана\n"
        
        await update.message.reply_text(message, parse_mode='HTML')
        
    except Exception as e:
        logger.error(f"Ошибка в отладочной команде: {e}")
        await update.message.reply_text(f"❌ Ошибка отладки: {str(e)}")

async def myalerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /myalerts"""
    await my_alerts_command(update, context)

def setup_alerts_handlers(application):
    """Настройка обработчиков уведомлений"""
    application.add_handler(CommandHandler("alert", alert_command))
    application.add_handler(CommandHandler("myalerts", myalerts_command))
    application.add_handler(CommandHandler("debug_alerts", debug_alerts_command))
