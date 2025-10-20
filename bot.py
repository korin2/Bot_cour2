import logging
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv
import os

# Загрузка переменных окружения из файла .env
load_dotenv()

# Включаем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Получение токена из переменной окружения
TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')

if not TOKEN:
    raise ValueError("Требуется переменная окружения TELEGRAM_BOT_TOKEN")

# Функция для получения курсов валют (используем exchangerate-api.com)
def get_exchange_rates():
    url = "https://api.exchangerate-api.com/v4/latest/USD"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Проверка на HTTP ошибки
        data = response.json()
        rates = data['rates']
        # Форматируем ответ, например, для EUR, GBP, RUB
        message = f"Курсы валют (на 1 USD):\n"
        for currency in ['EUR', 'GBP', 'RUB']:
            rate = rates.get(currency)
            if rate:
                message += f"{currency}: {rate:.4f}\n"
        return message
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка при запросе к API: {e}")
        return "Не удалось получить курсы валют. Попробуйте позже."
    except KeyError:
        logger.error("Ошибка: Неправильная структура данных от API.")
        return "Не удалось получить курсы валют. Попробуйте позже."

# Обработчик команды /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        'Привет! Я бот, который показывает курсы валют.\n'
        'Используйте команду /rates, чтобы получить актуальные курсы.'
    )

# Обработчик команды /rates
async def rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    rates_message = get_exchange_rates()
    await update.message.reply_text(rates_message)

def main() -> None:
    """Запуск бота."""
    # Создаем Application и передаем ему токен бота
    application = Application.builder().token(TOKEN).build()

    # Регистрируем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("rates", rates))

    # Запускаем бота в режиме long polling
    application.run_polling()

if __name__ == '__main__':
    main()
