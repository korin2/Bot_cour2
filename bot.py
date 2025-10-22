import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from db import init_db, get_user_base_currency, set_user_base_currency, add_alert, update_user_info
import os
from datetime import datetime

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("Требуется переменная окружения TELEGRAM_BOT_TOKEN")

def get_exchange_rate(from_currency: str, to_currency: str) -> tuple[float | None, str]:
    """Получает курс обмена валют с использованием надежного API"""
    # Основное API - Frankfurter (бесплатное и надежное)
    url = f"https://api.frankfurter.app/latest?from={from_currency.upper()}&to={to_currency.upper()}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Получаем дату
        date = data.get('date', 'неизвестная дата')
        
        # Форматируем дату в понятный вид
        if date != 'неизвестная дата':
            try:
                # Преобразуем из YYYY-MM-DD в DD.MM.YYYY
                date_parts = date.split('-')
                if len(date_parts) == 3:
                    date = f"{date_parts[2]}.{date_parts[1]}.{date_parts[0]}"
            except:
                pass
        
        # Получаем курс
        rate = data['rates'].get(to_currency.upper())
        
        if rate is not None:
            logger.info(f"Курс {from_currency}/{to_currency} = {rate} получен с Frankfurter API")
            return rate, date
            
    except Exception as e:
        logger.warning(f"Ошибка при получении курса с Frankfurter API: {e}")
    
    # Резервное API - ExchangeRate-API
    try:
        url_fallback = f"https://api.exchangerate-api.com/v4/latest/{from_currency.upper()}"
        response = requests.get(url_fallback, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Получаем дату
        date = data.get('time_last_updated', 'неизвестная дата')
        if date != 'неизвестная дата':
            try:
                date = datetime.fromtimestamp(date).strftime('%d.%m.%Y')
            except:
                pass
        
        # Получаем курс
        rate = data['rates'].get(to_currency.upper())
        
        if rate is not None:
            logger.info(f"Курс {from_currency}/{to_currency} = {rate} получен с резервного API")
            return rate, date
            
    except Exception as e:
        logger.warning(f"Ошибка при получении курса с резервного API: {e}")
    
    logger.error(f"Не удалось получить курс {from_currency}/{to_currency} ни с одного API")
    return None, 'неизвестная дата'

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    # Сохраняем информацию о пользователе в БД
    await update_user_info(user.id, user.first_name, user.username)
    
    # Создаем персонализированное приветствие
    if user.first_name:
        greeting = f"Привет, {user.first_name}!"
    else:
        greeting = "Привет!"
    
    keyboard = [
        [InlineKeyboardButton("Евро (EUR)", callback_data='rate_EUR')],
        [InlineKeyboardButton("Фунт (GBP)", callback_data='rate_GBP')],
        [InlineKeyboardButton("Рубль (RUB)", callback_data='rate_RUB')],
        [InlineKeyboardButton("Помощь", callback_data='help')],
        [InlineKeyboardButton("Настройки", callback_data='settings')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f'{greeting} Я бот для отслеживания курсов валют!\n\n'
        'Выберите валюту или воспользуйтесь командами:\n'
        '/rates — курсы к вашей базовой валюте\n'
        '/rate <из> <в> — например, /rate EUR RUB\n'
        '/convert <сумма> <из> <в> — например, /convert 100 USD RUB\n'
        '/setbase <валюта> — установить базовую валюту\n'
        '/stop — остановить бота',
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_help(update, context)

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    greeting = f", {user.first_name}!" if user.first_name else "!"
    
    help_text = (
        f"Привет{greeting} Я бот для отслеживания курсов валют!\n\n"
        "📊 <b>Основные функции:</b>\n"
        "• Просмотр актуальных курсов валют\n"
        "• Конвертация любых сумм\n"
        "• Установка уведомлений об изменении курсов\n"
        "• Настройка базовой валюты\n\n"
        "🔄 <b>Доступные команды:</b>\n"
        "/start — главное меню\n"
        "/help — эта справка\n"
        "/rates — курсы к вашей базовой валюте\n"
        "/rate <из> <в> — курс между двумя валютами\n"
        "/convert <сумма> <из> <в> — конвертация суммы\n"
        "/setbase <валюта> — установить базовую валюту\n"
        "/alert <из> <в> <порог> <above|below> — установить уведомление\n"
        "/stop — остановить бота\n\n"
        "💡 <b>Примеры использования:</b>\n"
        "<code>/rate EUR USD</code> — курс евро к доллару\n"
        "<code>/convert 100 USD RUB</code> — конвертация 100 долларов в рубли\n"
        "<code>/setbase EUR</code> — установить евро как базовую валюту\n"
        "<code>/alert USD RUB 80 above</code> — уведомить, когда курс доллара к рублю превысит 80\n\n"
        "📈 <b>Поддерживаемые валюты:</b>\n"
        "USD, EUR, GBP, RUB, JPY, CNY, CHF и многие другие!"
    )
    
    # Клавиатура с кнопкой "Назад"
    keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(help_text, parse_mode='HTML', reply_markup=reply_markup)
    else:
        await update.message.reply_text(help_text, parse_mode='HTML', reply_markup=reply_markup)

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    greeting = f", {user.first_name}!" if user.first_name else "!"
    
    await update.message.reply_text(
        f"До свидания{greeting} Бот остановлен.\n"
        "Для возобновления работы отправьте /start"
    )

async def rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    base_currency = await get_user_base_currency(user_id)
    
    greeting = f", {user.first_name}!" if user.first_name else "!"
    
    # Используем Frankfurter API для получения курсов
    # Получаем курсы для популярных валют относительно базовой
    popular_currencies = ['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'RUB', 'CHF', 'CAD', 'AUD']
    target_currencies = [curr for curr in popular_currencies if curr != base_currency]
    
    if not target_currencies:
        await update.message.reply_text(f"Привет{greeting} Базовая валюта {base_currency} совпадает со всеми популярными валютами.")
        return
    
    # Формируем запрос к API
    symbols = ','.join(target_currencies)
    url = f"https://api.frankfurter.app/latest?from={base_currency}&to={symbols}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Получаем дату
        date = data.get('date', 'неизвестная дата')
        if date != 'неизвестная дата':
            try:
                date_parts = date.split('-')
                if len(date_parts) == 3:
                    date = f"{date_parts[2]}.{date_parts[1]}.{date_parts[0]}"
            except:
                pass
        
        rates_data = data['rates']
        
        message = f"Привет{greeting} Курсы валют на {date} относительно {base_currency}:\n\n"
        for curr, rate in rates_data.items():
            message += f"{curr}: {rate:.4f}\n"
            
        await update.message.reply_text(message)
        
    except Exception as e:
        logger.error(f"Ошибка при получении курсов валют: {e}")
        # Пробуем альтернативное API
        try:
            url_fallback = f"https://api.exchangerate-api.com/v4/latest/{base_currency}"
            response = requests.get(url_fallback, timeout=10)
            response.raise_for_status()
            data = response.json()
            rates_data = data['rates']
            
            # Пытаемся получить дату из альтернативного API
            date = data.get('time_last_updated', 'неизвестная дата')
            if date != 'неизвестная дата':
                try:
                    date = datetime.fromtimestamp(date).strftime('%d.%m.%Y')
                except:
                    pass
            
            message = f"Привет{greeting} Курсы валют на {date} относительно {base_currency}:\n\n"
            for curr in ['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'RUB']:
                if curr != base_currency and curr in rates_data:
                    rate = rates_data[curr]
                    message += f"{curr}: {rate:.4f}\n"
                    
            await update.message.reply_text(message)
            
        except Exception as e2:
            logger.error(f"Ошибка при получении курсов с резервного API: {e2}")
            await update.message.reply_text(
                f"Привет{greeting} К сожалению, не удалось получить актуальные курсы валют. "
                "Пожалуйста, попробуйте позже или используйте команду /rate для получения конкретного курса."
            )

async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Используйте: /rate <из> <в>")
        return
    from_curr, to_curr = args
    rate, date = get_exchange_rate(from_curr, to_curr)
    if rate is not None:
        await update.message.reply_text(f"Курс на {date}:\n1 {from_curr.upper()} = {rate:.4f} {to_curr.upper()}")
    else:
        await update.message.reply_text("Не удалось получить курс.")

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) != 3:
        await update.message.reply_text("Используйте: /convert <сумма> <из> <в>")
        return
    try:
        amount = float(args[0])
    except ValueError:
        await update.message.reply_text("Сумма должна быть числом.")
        return
    from_curr, to_curr = args[1], args[2]
    rate, date = get_exchange_rate(from_curr, to_curr)
    if rate is not None:
        result = amount * rate
        await update.message.reply_text(f"Курс на {date}:\n{amount} {from_curr.upper()} = {result:.4f} {to_curr.upper()}")
    else:
        await update.message.reply_text("Не удалось выполнить конвертацию.")

async def setbase_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("Используйте: /setbase <валюта>")
        return
    currency = args[0].upper()
    user_id = update.effective_message.from_user.id
    await set_user_base_currency(user_id, currency)
    await update.message.reply_text(f"Базовая валюта установлена: {currency}")

async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) != 4:
        await update.message.reply_text("Используйте: /alert <из> <в> <порог> <above|below>")
        return
    from_curr, to_curr = args[0], args[1]
    try:
        threshold = float(args[2])
    except ValueError:
        await update.message.reply_text("Порог должен быть числом.")
        return
    direction = args[3].lower()
    if direction not in ['above', 'below']:
        await update.message.reply_text("Направление должно быть 'above' или 'below'.")
        return
    user_id = update.effective_message.from_user.id
    await add_alert(user_id, from_curr, to_curr, threshold, direction)
    await update.message.reply_text(f"Уведомление установлено: {from_curr}/{to_curr} {'>' if direction == 'above' else '<'} {threshold}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
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
            [InlineKeyboardButton("Евро (EUR)", callback_data='rate_EUR')],
            [InlineKeyboardButton("Фунт (GBP)", callback_data='rate_GBP')],
            [InlineKeyboardButton("Рубль (RUB)", callback_data='rate_RUB')],
            [InlineKeyboardButton("Помощь", callback_data='help')],
            [InlineKeyboardButton("Настройки", callback_data='settings')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f'{greeting} Я бот для отслеживания курсов валют!\n\n'
            'Выберите валюту или воспользуйтесь командами:\n'
            '/rates — курсы к вашей базовой валюте\n'
            '/rate <из> <в> — например, /rate EUR RUB\n'
            '/convert <сумма> <из> <в> — например, /convert 100 USD RUB\n'
            '/setbase <валюта> — установить базовую валюту\n'
            '/stop — остановить бота',
            reply_markup=reply_markup
        )
    elif data == 'settings':
        user_id = query.from_user.id
        base_currency = await get_user_base_currency(user_id)
        
        # Клавиатура с кнопкой "Назад"
        keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"Текущие настройки:\n"
            f"• Базовая валюта: {base_currency}\n\n"
            "Используйте /setbase <валюта> для изменения базовой валюты.",
            reply_markup=reply_markup
        )
    elif data.startswith('rate_'):
        currency = data.split('_')[1]
        user_id = query.from_user.id
        base_currency = await get_user_base_currency(user_id)
        rate, date = get_exchange_rate(base_currency, currency)
        
        # Клавиатура с кнопкой "Назад"
        keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if rate is not None:
            await query.edit_message_text(
                f"Курс на {date}:\n1 {base_currency} = {rate:.4f} {currency}\n\n"
                "Используйте /rates для просмотра всех курсов или /convert для конвертации сумм.",
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text(
                "Не удалось получить курс. Попробуйте позже.",
                reply_markup=reply_markup
            )

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Неизвестная команда. Используйте /help для просмотра доступных команд.")

async def post_init(application: Application) -> None:
    """Функция, выполняемая после инициализации бота"""
    await init_db()
    print("БД инициализирована успешно")

def main() -> None:
    # Создаем и настраиваем application
    application = Application.builder().token(TOKEN).post_init(post_init).build()

    # Добавляем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("stop", stop_command))
    application.add_handler(CommandHandler("rates", rates))
    application.add_handler(CommandHandler("rate", rate_command))
    application.add_handler(CommandHandler("convert", convert_command))
    application.add_handler(CommandHandler("setbase", setbase_command))
    application.add_handler(CommandHandler("alert", alert_command))
    
    # Обработчик для inline-кнопок
    application.add_handler(CallbackQueryHandler(button_handler))
    
    # Обработчик для неизвестных команд
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # Запуск бота
    print("Бот запускается...")
    application.run_polling()

if __name__ == '__main__':
    main()
