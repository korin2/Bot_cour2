import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from telegram.ext import JobQueue  # <-- Добавили импорт
from db import init_db, get_user_base_currency, set_user_base_currency, add_alert, get_all_alerts
# from dotenv import load_dotenv  # <-- УБРАТЬ
import os
from typing import Optional  # <-- Добавлено

# load_dotenv()  # <-- УБРАТЬ

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("Требуется переменная окружения TELEGRAM_BOT_TOKEN")

def get_exchange_rate(from_currency: str, to_currency: str) -> Optional[float]:
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
    keyboard = [
        [InlineKeyboardButton("Евро (EUR)", callback_data='rate_EUR')],
        [InlineKeyboardButton("Фунт (GBP)", callback_data='rate_GBP')],
        [InlineKeyboardButton("Рубль (RUB)", callback_data='rate_RUB')],
        [InlineKeyboardButton("Настройки", callback_data='settings')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        'Привет! Выберите валюту или воспользуйтесь командами:\n'
        '/rates — курсы к вашей базовой валюте\n'
        '/rate <из> <в> — например, /rate EUR RUB\n'
        '/convert <сумма> <из> <в> — например, /convert 100 USD RUB\n'
        '/setbase <валюта> — установить базовую валюту',
        reply_markup=reply_markup
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        'Доступные команды:\n'
        '/start — главное меню\n'
        '/help — это сообщение\n'
        '/rates — курсы к вашей базовой валюте\n'
        '/rate <из> <в> — например, /rate EUR RUB\n'
        '/convert <сумма> <из> <в> — например, /convert 100 USD RUB\n'
        '/setbase <валюта> — установить базовую валюту\n'
        '/alert <из> <в> <порог> <above|below> — установить уведомление'
    )

async def rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user_id = update.effective_message.from_user.id
    base_currency = await get_user_base_currency(user_id)
    url = f"https://api.exchangerate-api.com/v4/latest/{base_currency}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        rates = data['rates']
        message = f"Курсы относительно {base_currency}:\n"
        for curr, rate in list(rates.items())[:5]:  # первые 5
            message += f"{curr}: {rate:.4f}\n"
        await update.message.reply_text(message)
    except Exception as e:
        await update.message.reply_text("Не удалось получить курсы валют.")

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

# Фоновая задача для проверки уведомлений
async def check_alerts(context: ContextTypes.DEFAULT_TYPE):
    alerts = await get_all_alerts()
    for alert in alerts:
        rate = get_exchange_rate(alert['from_currency'], alert['to_currency'])
        if rate is None:
            continue
        if (alert['direction'] == 'above' and rate > alert['threshold']) or \
           (alert['direction'] == 'below' и rate < alert['threshold']):
            try:
                await context.bot.send_message(chat_id=alert['user_id'], text=f"🔔 Уведомление: {alert['from_currency']}/{alert['to_currency']} = {rate:.4f}")
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления пользователю {alert['user_id']}: {e}")

# Задача для инициализации БД
async def init_db_job(context: ContextTypes.DEFAULT_TYPE):
    await init_db()

def main() -> None:
    # Создаём JobQueue вручную
    job_queue = JobQueue()
    # Передаём её в Application.builder()
    application = Application.builder().token(TOKEN).job_queue(job_queue).build()

    # Добавляем задачу инициализации БД, которая выполнится один раз
    application.job_queue.run_once(init_db_job, when=0.1)

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rates", rates))
    application.add_handler(CommandHandler("rate", rate_command))
    application.add_handler(CommandHandler("convert", convert_command))
    application.add_handler(CommandHandler("setbase", setbase_command))
    application.add_handler(CommandHandler("alert", alert_command))

    # Добавляем задачу проверки уведомлений (раз в 10 минут)
    application.job_queue.run_repeating(check_alerts, interval=600, first=10)

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()  # <-- Просто запускаем main, без asyncio.run()
