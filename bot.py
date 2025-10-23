import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from db import init_db, add_alert, update_user_info, get_all_users
import os
from datetime import datetime
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("Требуется переменная окружения TELEGRAM_BOT_TOKEN")

# Глобальная переменная для хранения application и scheduler
application = None
scheduler = None

def get_cbr_rates() -> tuple[dict, str]:
    """Получает курсы валют от ЦБ РФ"""
    try:
        # API ЦБ РФ
        url = "https://www.cbr-xml-daily.ru/daily_json.js"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Получаем дату
        cbr_date = data.get('Date', '')
        if cbr_date:
            try:
                # Преобразуем дату из формата ISO в DD.MM.YYYY
                date_obj = datetime.fromisoformat(cbr_date.replace('Z', '+00:00'))
                cbr_date = date_obj.strftime('%d.%m.%Y')
            except:
                cbr_date = 'неизвестная дата'
        else:
            cbr_date = 'неизвестная дата'
        
        # Получаем курсы валют
        valutes = data.get('Valute', {})
        rates = {}
        
        # Основные валюты для отображения
        main_currencies = {
            'USD': 'Доллар США',
            'EUR': 'Евро',
            'GBP': 'Фунт стерлингов',
            'JPY': 'Японская иена',
            'CNY': 'Китайский юань',
            'CHF': 'Швейцарский франк',
            'CAD': 'Канадский доллар',
            'AUD': 'Австралийский доллар',
            'TRY': 'Турецкая лира',
            'KZT': 'Казахстанский тенге'
        }
        
        for currency, name in main_currencies.items():
            if currency in valutes:
                currency_data = valutes[currency]
                rates[currency] = {
                    'value': currency_data['Value'],
                    'name': name,
                    'previous': currency_data.get('Previous', currency_data['Value']),
                    'nominal': currency_data.get('Nominal', 1)
                }
        
        return rates, cbr_date
        
    except Exception as e:
        logger.error(f"Ошибка при получении курсов ЦБ РФ: {e}")
        return {}, 'неизвестная дата'

def format_cbr_rates_message(rates_data: dict, cbr_date: str) -> str:
    """Форматирует сообщение с курсами ЦБ РФ"""
    if not rates_data:
        return "❌ Не удалось получить курсы ЦБ РФ."
    
    message = f"🏛 <b>КУРСЫ ЦБ РФ</b>\n"
    message += f"📅 <i>на {cbr_date}</i>\n\n"
    
    # Основные валюты (доллар, евро)
    main_currencies = ['USD', 'EUR']
    for currency in main_currencies:
        if currency in rates_data:
            data = rates_data[currency]
            current_value = data['value']
            previous_value = data['previous']
            change = current_value - previous_value
            change_percent = (change / previous_value) * 100 if previous_value else 0
            
            change_icon = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            change_text = f"{change:+.2f} руб. ({change_percent:+.2f}%)"
            
            message += f"💵 <b>{data['name']}</b> ({currency}):\n"
            message += f"   <b>{current_value:.2f} руб.</b> {change_icon} {change_text}\n\n"
    
    # Другие валюты
    other_currencies = [curr for curr in rates_data.keys() if curr not in main_currencies]
    if other_currencies:
        message += "🌍 <b>Другие валюты:</b>\n"
        
        for currency in other_currencies:
            data = rates_data[currency]
            current_value = data['value']
            previous_value = data['previous']
            change = current_value - previous_value
            
            change_icon = "📈" if change > 0 else "📉" if change < 0 else "➡️"
            
            # Для JPY делим на 100, так как курс указан за 100 единиц
            if currency == 'JPY':
                display_value = current_value / 100
                message += f"   {data['name']} ({currency}): <b>{display_value:.4f} руб.</b> {change_icon}\n"
            else:
                message += f"   {data['name']} ({currency}): <b>{current_value:.4f} руб.</b> {change_icon}\n"
    
    message += f"\n💡 <i>Курсы обновляются ежедневно</i>"
    return message

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = update.effective_user
        
        # Сохраняем информацию о пользователе в БД
        await update_user_info(user.id, user.first_name, user.username)
        
        # Создаем персонализированное приветствие
        if user.first_name:
            greeting = f"Привет, {user.first_name}!"
        else:
            greeting = "Привет!"
        
        # Главное меню
        keyboard = [
            [InlineKeyboardButton("📊 Курсы ЦБ РФ", callback_data='cbr_rates')],
            [InlineKeyboardButton("❓ Помощь", callback_data='help')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f'{greeting} Я бот для отслеживания курсов валют!\n\n'
            '🏛 <b>Основной фокус - курсы ЦБ РФ</b>\n\n'
            'Выберите опцию из меню ниже:',
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        
        # Показываем курсы ЦБ РФ сразу после старта
        await show_cbr_rates(update, context)
    except Exception as e:
        logger.error(f"Ошибка в команде /start: {e}")
        await update.message.reply_text("❌ Произошла ошибка при запуске бота. Пожалуйста, попробуйте еще раз.")

async def show_cbr_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает курсы валют от ЦБ РФ"""
    try:
        rates_data, cbr_date = get_cbr_rates()
        
        if not rates_data:
            error_msg = "❌ Не удалось получить курсы ЦБ РФ. Попробуйте позже."
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_msg, reply_markup=reply_markup)
            return
        
        message = format_cbr_rates_message(rates_data, cbr_date)
        
        # Клавиатура с кнопкой "Назад"
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка при показе курсов ЦБ РФ: {e}")
        error_msg = "❌ Произошла ошибка при получении курсов ЦБ РФ."
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
        else:
            await update.message.reply_text(error_msg, reply_markup=reply_markup)

async def send_daily_rates():
    """Ежедневная отправка курсов ЦБ РФ всем пользователям"""
    try:
        if application is None:
            logger.error("Application не инициализирована для ежедневной рассылки")
            return
            
        logger.info("Начало ежедневной рассылки курсов ЦБ РФ")
        
        # Получаем курсы ЦБ РФ
        rates_data, cbr_date = get_cbr_rates()
        
        if not rates_data:
            logger.error("Не удалось получить курсы ЦБ РФ для ежедневной рассылки")
            return
        
        # Форматируем сообщение
        message = format_cbr_rates_message(rates_data, cbr_date)
        message = f"🌅 <b>Ежедневное обновление курсов ЦБ РФ</b>\n\n{message}"
        
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
                await application.bot.send_message(
                    chat_id=user['user_id'],
                    text=message,
                    parse_mode='HTML'
                )
                success_count += 1
                # Небольшая задержка чтобы не превысить лимиты Telegram
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.warning(f"Не удалось отправить сообщение пользователю {user['user_id']}: {e}")
        
        logger.info(f"Ежедневная рассылка завершена. Успешно отправлено: {success_count}/{len(users)}")
        
    except Exception as e:
        logger.error(f"Ошибка в ежедневной рассылке: {e}")

async def cbr_rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды для курсов ЦБ РФ"""
    await show_cbr_rates(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_help(update, context)

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = update.effective_user
        greeting = f", {user.first_name}!" if user.first_name else "!"
        
        help_text = (
            f"Привет{greeting} Я бот для отслеживания курсов валют!\n\n"
            
            "🏛 <b>ОСНОВНОЙ ФОКУС - КУРСЫ ЦБ РФ</b>\n\n"
            
            "💱 <b>Основные команды:</b>\n"
            "• <code>/start</code> - главное меню и курсы ЦБ РФ\n"
            "• <code>/cbr</code> - актуальные курсы ЦБ РФ\n"
            "• <code>/rates</code> - тоже курсы ЦБ РФ\n"
            "• <code>/help</code> - эта справка\n\n"
            
            "🔔 <b>Уведомления:</b>\n"
            "• <code>/alert USD RUB 80 above</code> - уведомит о курсе\n\n"
            
            "⏰ <b>Ежедневная рассылка</b>\n"
            "• Автоматическая отправка курсов ЦБ РФ каждый день в 10:00\n\n"
            
            "💡 <b>ИНФОРМАЦИЯ</b>\n\n"
            "• Курсы ЦБ РФ обновляются ежедневно\n"
            "• Данные предоставляются Центральным Банком РФ\n"
            "• Всегда актуальные курсы валют"
        )
        
        # Клавиатура с кнопкой "Назад"
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(help_text, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=reply_markup)
    except Exception as e:
        logger.error(f"Ошибка при показе справки: {e}")

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        user = update.effective_user
        greeting = f", {user.first_name}!" if user.first_name else "!"
        
        # Клавиатура с кнопкой "Назад"
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"До свидания{greeting} Бот остановлен.\n"
            "Для возобновления работы отправьте /start",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка в команде /stop: {e}")

async def rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_cbr_rates(update, context)

async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        args = context.args
        if len(args) != 4:
            # Клавиатура с кнопкой "Назад"
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "Используйте: /alert <из> <в> <порог> <above|below>\n\n"
                "Пример: /alert USD RUB 80 above",
                reply_markup=reply_markup
            )
            return
        
        from_curr, to_curr = args[0], args[1]
        try:
            threshold = float(args[2])
        except ValueError:
            # Клавиатура с кнопкой "Назад"
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("❌ Порог должен быть числом.", reply_markup=reply_markup)
            return
        
        direction = args[3].lower()
        if direction not in ['above', 'below']:
            # Клавиатура с кнопкой "Назад"
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text("❌ Направление должно быть 'above' или 'below'.", reply_markup=reply_markup)
            return
        
        user_id = update.effective_message.from_user.id
        await add_alert(user_id, from_curr, to_curr, threshold, direction)
        
        # Клавиатура с кнопкой "Назад"
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            f"🔔 Уведомление установлено: {from_curr}/{to_curr} {'>' if direction == 'above' else '<'} {threshold}",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка в команде /alert: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == 'help':
            await show_help(update, context)
        elif data == 'back_to_main':
            user = query.from_user
            
            # Создаем персонализированное приветствие
            if user.first_name:
                greeting = f"Привет, {user.first_name}!"
            else:
                greeting = "Привет!"
            
            keyboard = [
                [InlineKeyboardButton("📊 Курсы ЦБ РФ", callback_data='cbr_rates')],
                [InlineKeyboardButton("❓ Помощь", callback_data='help')],
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await query.edit_message_text(
                f'{greeting} Я бот для отслеживания курсов валют!\n\n'
                '🏛 <b>Основной фокус - курсы ЦБ РФ</b>\n\n'
                'Выберите опцию из меню ниже:',
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        elif data == 'cbr_rates':
            await show_cbr_rates(update, context)
    except Exception as e:
        logger.error(f"Ошибка в обработчике кнопок: {e}")

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Клавиатура с кнопкой "Назад"
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "❌ Неизвестная команда. Используйте /help для просмотра доступных команд.",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка в обработчике неизвестных команд: {e}")

async def setup_scheduler():
    """Настройка планировщика для ежедневной рассылки"""
    global scheduler
    scheduler = AsyncIOScheduler()
    # 10:00 МСК = 07:00 UTC
    scheduler.add_job(
        send_daily_rates,
        trigger=CronTrigger(hour=7, minute=0, timezone='UTC'),
        id='daily_rates'
    )
    scheduler.start()
    logger.info("Ежедневная рассылка настроена на 10:00 МСК (07:00 UTC)")

async def post_init(application_instance: Application) -> None:
    """Функция, выполняемая после инициализации бота"""
    global application
    application = application_instance
    
    try:
        await init_db()
        logger.info("БД инициализирована успешно")
        
        # Настраиваем планировщик после инициализации БД
        await setup_scheduler()
    except Exception as e:
        logger.error(f"Ошибка при инициализации БД: {e}")

async def main() -> None:
    """Основная асинхронная функция для запуска бота"""
    try:
        # Создаем и настраиваем application
        app = Application.builder().token(TOKEN).post_init(post_init).build()

        # Добавляем обработчики
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("help", help_command))
        app.add_handler(CommandHandler("stop", stop_command))
        app.add_handler(CommandHandler("rates", rates))
        app.add_handler(CommandHandler("cbr", cbr_rates_command))
        app.add_handler(CommandHandler("alert", alert_command))
        
        # Обработчик для inline-кнопок
        app.add_handler(CallbackQueryHandler(button_handler))
        
        # Обработчик для неизвестных команд
        app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

        # Запуск бота
        logger.info("Бот запускается...")
        await app.run_polling()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        # Останавливаем планировщик при завершении работы бота
        if scheduler and scheduler.running:
            scheduler.shutdown()

if __name__ == '__main__':
    # Запускаем основную асинхронную функцию
    asyncio.run(main())
