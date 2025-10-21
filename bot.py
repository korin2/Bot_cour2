import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters, CallbackQueryHandler
from db import init_db, get_user_base_currency, set_user_base_currency, add_alert, get_all_alerts, update_user_info
import os
import asyncio

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("Требуется переменная окружения TELEGRAM_BOT_TOKEN")

def get_exchange_rate(from_currency: str, to_currency: str) -> float | None:
    url = f"https://api.exchangerate-api.com/v4/latest/{from_currency.upper()}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        rate = data['rates'].get(to_currency.upper())
        return rate
    except Exception as e:
        logger.error(f"Ошибка при получении курса {from_currency}/{to_currency}: {e}")
        return None

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
    
    # Проверяем, является ли update сообщением или callback query
    if update.message:
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
    elif update.callback_query:
        await update.callback_query.edit_message_text(
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
    
    # Останавливаем бота
    await context.application.stop()

async def rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    user_id = user.id
    base_currency = await get_user_base_currency(user_id)
    
    greeting = f", {user.first_name}!" if user.first_name else "!"
    
    url = f"https://api.exchangerate-api.com/v4/latest/{base_currency}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        rates = data['rates']
        message = f"Привет{greeting} Курсы относительно {base_currency}:\n"
        for curr, rate in list(rates.items())[:5]:  # первые 5
            message += f"{curr}: {rate:.4f}\n"
        await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text(f"Привет{greeting} Не удалось получить курсы валют.")

async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Используйте: /rate <из> <в>")
        return
    from_curr, to_curr = args
    rate = get_exchange_rate(from_curr, to_curr)
    if rate is not None:
        await update.message.reply_text(f"1 {from_curr.upper()} = {rate:.4f} {to_curr.upper()}")
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
    rate = get_exchange_rate(from_curr, to_curr)
    if rate is not None:
        result = amount * rate
        await update.message.reply_text(f"{amount} {from_curr.upper()} = {result:.4f} {to_curr.upper()}")
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
        await start(update, context)
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
        rate = get_exchange_rate(base_currency, currency)
        
        # Клавиатура с кнопкой "Назад"
        keyboard = [[InlineKeyboardButton("Назад", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if rate is not None:
            await query.edit_message_text(
                f"1 {base_currency} = {rate:.4f} {currency}\n\n"
                "Используйте /rates для просмотра всех курсов или /convert для конвертации сумм.",
                reply_markup=reply_markup
            )
        else:
            await query.edit_message_text(
                "Не удалось получить курс. Попробуйте позже.",
                reply_markup=reply_markup
            )

def main() -> None:
    # Создаем и настраиваем application
    application = Application.builder().token(TOKEN).build()

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

    # Инициализируем БД и запускаем бота
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        # Инициализация БД
        loop.run_until_complete(init_db())
        print("БД инициализирована успешно")
        
        # Запуск бота
        print("Бот запускается...")
        application.run_polling()
    except KeyboardInterrupt:
        logger.info("Бот остановлен пользователем")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
    finally:
        loop.close()

if __name__ == '__main__':
    main()
