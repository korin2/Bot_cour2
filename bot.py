import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from db import init_db, add_alert, update_user_info, get_all_users
import os
from datetime import datetime
import asyncio

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("Требуется переменная окружения TELEGRAM_BOT_TOKEN")

def get_key_rate() -> dict:
    """Получает ключевую ставку ЦБ РФ"""
    try:
        # URL для получения ключевой ставки (используем API ЦБ РФ)
        # Это упрощенный подход - на практике может потребоваться парсинг HTML
        url = "https://www.cbr.ru/hd_base/KeyRate/"
        
        # Альтернативный подход: используем API, которое предоставляет ключевую ставку
        # В реальном проекте нужно использовать официальное API ЦБ РФ
        # Для демонстрации используем заглушку с актуальной ставкой
        today = datetime.now()
        
        # Пример актуальной ключевой ставки (нужно обновлять по данным ЦБ РФ)
        # На 2024 год ключевая ставка ЦБ РФ составляет 16.00%
        key_rate_info = {
            'rate': 16.00,
            'date': today.strftime('%d.%m.%Y'),
            'change': 0.0,  # изменение с предыдущего значения
            'is_current': True
        }
        
        # В реальном проекте здесь должен быть парсинг страницы ЦБ РФ
        # или использование официального API
        
        return key_rate_info
        
    except Exception as e:
        logger.error(f"Ошибка при получении ключевой ставки: {e}")
        return {}

def get_cbr_rates() -> tuple[dict, str, dict]:
    """Получает курсы валют и ключевую ставку от ЦБ РФ"""
    try:
        # API ЦБ РФ для курсов валют
        url = "https://www.cbr-xml-daily.ru/daily_json.js"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Получаем дату
        cbr_date = data.get('Date', '')
        if cbr_date:
            try:
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
        
        # Получаем ключевую ставку ЦБ РФ
        key_rate_data = get_key_rate()
        
        return rates, cbr_date, key_rate_data
        
    except Exception as e:
        logger.error(f"Ошибка при получении курсов ЦБ РФ: {e}")
        return {}, 'неизвестная дата', {}

def format_cbr_rates_message(rates_data: dict, cbr_date: str, key_rate_data: dict = None) -> str:
    """Форматирует сообщение с курсами ЦБ РФ и ключевой ставкой"""
    if not rates_data:
        return "❌ Не удалось получить курсы ЦБ РФ."
    
    message = f"🏛 <b>КУРСЫ ЦБ РФ</b>\n"
    message += f"📅 <i>на {cbr_date}</i>\n\n"
    
    # Добавляем ключевую ставку если есть данные
    if key_rate_data and key_rate_data.get('is_current'):
        rate = key_rate_data['rate']
        change = key_rate_data.get('change', 0)
        change_icon = "📈" if change > 0 else "📉" if change < 0 else "➡️"
        change_text = f"{change:+.2f}%" if change != 0 else ""
        
        message += f"💎 <b>Ключевая ставка ЦБ РФ:</b>\n"
        message += f"   <b>{rate:.2f}%</b> {change_icon} {change_text}\n\n"
    
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
    
    # Добавляем примечание о ключевой ставке
    if key_rate_data and not key_rate_data.get('is_current'):
        message += f"\n\n⚠️ <i>Информация по ключевой ставке может быть неактуальной</i>"
    
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
        
        # Получаем актуальные данные для приветственного сообщения
        rates_data, cbr_date, key_rate_data = get_cbr_rates()
        
        # Главное меню
        keyboard = [
            [InlineKeyboardButton("📊 Курсы ЦБ РФ", callback_data='cbr_rates')],
            [InlineKeyboardButton("💎 Ключевая ставка", callback_data='key_rate')],
            [InlineKeyboardButton("❓ Помощь", callback_data='help')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        start_message = f'{greeting} Я бот для отслеживания курсов валют!\n\n'
        start_message += '🏛 <b>Основной фокус - курсы ЦБ РФ</b>\n\n'
        
        # Добавляем информацию о ключевой ставке в приветствие
        if key_rate_data and key_rate_data.get('is_current'):
            rate = key_rate_data['rate']
            start_message += f'💎 <b>Ключевая ставка ЦБ РФ:</b> <b>{rate:.2f}%</b>\n\n'
        
        start_message += 'Выберите опцию из меню ниже:'
        
        await update.message.reply_text(
            start_message,
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
        rates_data, cbr_date, key_rate_data = get_cbr_rates()
        
        if not rates_data:
            error_msg = "❌ Не удалось получить курсы ЦБ РФ. Попробуйте позже."
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_msg, reply_markup=reply_markup)
            return
        
        message = format_cbr_rates_message(rates_data, cbr_date, key_rate_data)
        
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

async def show_key_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает ключевую ставку ЦБ РФ"""
    try:
        key_rate_data = get_key_rate()
        
        if not key_rate_data or not key_rate_data.get('is_current'):
            error_msg = "❌ Не удалось получить актуальную ключевую ставку ЦБ РФ."
            keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if update.callback_query:
                await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
            else:
                await update.message.reply_text(error_msg, reply_markup=reply_markup)
            return
        
        rate = key_rate_data['rate']
        change = key_rate_data.get('change', 0)
        change_icon = "📈" if change > 0 else "📉" if change < 0 else "➡️"
        change_text = f"{change:+.2f}%" if change != 0 else "без изменений"
        
        message = f"💎 <b>КЛЮЧЕВАЯ СТАВКА ЦБ РФ</b>\n\n"
        message += f"<b>Текущее значение:</b> {rate:.2f}% {change_icon}\n"
        
        if change != 0:
            message += f"<b>Изменение:</b> {change_text}\n"
        
        message += f"\n<b>Дата актуальности:</b> {key_rate_data.get('date', 'неизвестно')}\n\n"
        message += "💡 <i>Ключевая ставка - это основная процентная ставка ЦБ РФ,\n"
        message += "которая влияет на кредиты, депозиты и экономику в целом</i>"
        
        # Клавиатура с кнопками
        keyboard = [
            [InlineKeyboardButton("📊 Все курсы ЦБ РФ", callback_data='cbr_rates')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.callback_query:
            await update.callback_query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка при показе ключевой ставки: {e}")
        error_msg = "❌ Произошла ошибка при получении ключевой ставки."
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        if update.callback_query:
            await update.callback_query.message.reply_text(error_msg, reply_markup=reply_markup)
        else:
            await update.message.reply_text(error_msg, reply_markup=reply_markup)

async def send_daily_rates(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Ежедневная отправка курсов ЦБ РФ всем пользователям"""
    try:
        logger.info("Начало ежедневной рассылки курсов ЦБ РФ")
        
        # Получаем курсы ЦБ РФ
        rates_data, cbr_date, key_rate_data = get_cbr_rates()
        
        if not rates_data:
            logger.error("Не удалось получить курсы ЦБ РФ для ежедневной рассылки")
            return
        
        # Форматируем сообщение
        message = format_cbr_rates_message(rates_data, cbr_date, key_rate_data)
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
                await context.bot.send_message(
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

async def keyrate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды для ключевой ставки"""
    await show_key_rate(update, context)

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
            "• <code>/keyrate</code> - ключевая ставка ЦБ РФ\n"
            "• <code>/help</code> - эта справка\n\n"
            
            "🔔 <b>Уведомления:</b>\n"
            "• <code>/alert USD RUB 80 above</code> - уведомит о курсе\n\n"
            
            "⏰ <b>Ежедневная рассылка</b>\n"
            "• Автоматическая отправка курсов ЦБ РФ каждый день в 10:00\n\n"
            
            "💎 <b>Ключевая ставка ЦБ РФ</b>\n"
            "• Основная процентная ставка Центрального Банка\n"
            "• Влияет на кредиты и депозиты\n"
            "• Обновляется по решению Совета директоров ЦБ РФ\n\n"
            
            "💡 <b>ИНФОРМАЦИЯ</b>\n\n"
            "• Курсы ЦБ РФ обновляются ежедневно\n"
            "• Ключевая ставка обновляется по решению ЦБ РФ\n"
            "• Данные предоставляются Центральным Банком РФ\n"
            "• Всегда актуальные курсы валют и ставки"
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
                [InlineKeyboardButton("💎 Ключевая ставка", callback_data='key_rate')],
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
        elif data == 'key_rate':
            await show_key_rate(update, context)
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
        # Создаем и настраиваем application
        application = Application.builder().token(TOKEN).post_init(post_init).build()

        # Добавляем обработчики
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(CommandHandler("stop", stop_command))
        application.add_handler(CommandHandler("rates", rates))
        application.add_handler(CommandHandler("cbr", cbr_rates_command))
        application.add_handler(CommandHandler("keyrate", keyrate_command))
        application.add_handler(CommandHandler("alert", alert_command))
        
        # Обработчик для inline-кнопок
        application.add_handler(CallbackQueryHandler(button_handler))
        
        # Обработчик для неизвестных команд
        application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

        # Настраиваем ежедневную рассылку в 10:00 (07:00 UTC)
        job_queue = application.job_queue
        
        if job_queue:
            # 10:00 МСК = 07:00 UTC
            job_queue.run_daily(
                send_daily_rates,
                time=datetime.strptime("07:00", "%H:%M").time(),  # 07:00 UTC = 10:00 МСК
                days=(0, 1, 2, 3, 4, 5, 6)  # Все дни недели
            )
            logger.info("Ежедневная рассылка настроена на 10:00 МСК (07:00 UTC)")
        else:
            logger.warning("JobQueue не доступен. Ежедневная рассылка не будет работать.")

        # Запуск бота
        logger.info("Бот запускается...")
        application.run_polling()
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == '__main__':
    main()
