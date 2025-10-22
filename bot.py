import logging
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
from db import init_db, get_user_base_currency, set_user_base_currency, add_alert, update_user_info
import os
from datetime import datetime, date

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TOKEN:
    raise ValueError("Требуется переменная окружения TELEGRAM_BOT_TOKEN")

def get_exchange_rate(from_currency: str, to_currency: str) -> tuple[float | None, str]:
    """Получает курс обмена валют с использованием Frankfurter API"""
    # Используем только Frankfurter API
    url = f"https://api.frankfurter.app/latest?from={from_currency.upper()}&to={to_currency.upper()}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Получаем дату
        api_date = data.get('date', 'неизвестная дата')
        
        # Форматируем дату в понятный вид
        if api_date != 'неизвестная дата':
            try:
                # Преобразуем из YYYY-MM-DD в DD.MM.YYYY
                date_parts = api_date.split('-')
                if len(date_parts) == 3:
                    api_date = f"{date_parts[2]}.{date_parts[1]}.{date_parts[0]}"
            except:
                pass
        
        # Получаем курс
        rate = data['rates'].get(to_currency.upper())
        
        if rate is not None:
            logger.info(f"Курс {from_currency}/{to_currency} = {rate} получен с Frankfurter API")
            return rate, api_date
            
    except Exception as e:
        logger.error(f"Ошибка при получении курса с Frankfurter API: {e}")
        return None, 'неизвестная дата'

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

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    # Сохраняем информацию о пользователе в БД
    await update_user_info(user.id, user.first_name, user.username)
    
    # Создаем персонализированное приветствие
    if user.first_name:
        greeting = f"Привет, {user.first_name}!"
    else:
        greeting = "Привет!"
    
    # Главное меню без отдельных кнопок валют
    keyboard = [
        [InlineKeyboardButton("📊 Курсы ЦБ РФ", callback_data='cbr_rates')],
        [InlineKeyboardButton("🔄 Конвертер валют", callback_data='converter')],
        [InlineKeyboardButton("❓ Помощь", callback_data='help')],
        [InlineKeyboardButton("⚙️ Настройки", callback_data='settings')],
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

async def show_cbr_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает курсы валют от ЦБ РФ"""
    rates_data, cbr_date = get_cbr_rates()
    
    if not rates_data:
        error_msg = "❌ Не удалось получить курсы ЦБ РФ. Попробуйте позже."
        if update.callback_query:
            await update.callback_query.message.reply_text(error_msg)
        else:
            await update.message.reply_text(error_msg)
        return
    
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
    
    # Клавиатура с кнопкой "Назад"
    keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
    else:
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)

async def show_converter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает интерфейс конвертера валют"""
    message = (
        "🔄 <b>КОНВЕРТЕР ВАЛЮТ</b>\n\n"
        "Для конвертации используйте команду:\n"
        "<code>/convert 100 USD EUR</code>\n\n"
        "<b>Примеры:</b>\n"
        "• <code>/convert 1000 USD RUB</code> - 1000 долларов в рубли\n"
        "• <code>/convert 500 EUR USD</code> - 500 евро в доллары\n"
        "• <code>/convert 10000 JPY RUB</code> - 10000 иен в рубли\n\n"
        "💡 <i>Поддерживаются все основные мировые валюты</i>"
    )
    
    # Клавиатура с кнопкой "Назад"
    keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(message, parse_mode='HTML', reply_markup=reply_markup)
    else:
        await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)

async def cbr_rates_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды для курсов ЦБ РФ"""
    await show_cbr_rates(update, context)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await show_help(update, context)

async def show_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    greeting = f", {user.first_name}!" if user.first_name else "!"
    
    help_text = (
        f"Привет{greeting} Я бот для отслеживания курсов валют!\n\n"
        
        "🏛 <b>ОСНОВНОЙ ФОКУС - КУРСЫ ЦБ РФ</b>\n\n"
        
        "💱 <b>Основные команды:</b>\n"
        "• <code>/start</code> - главное меню и курсы ЦБ РФ\n"
        "• <code>/cbr</code> - актуальные курсы ЦБ РФ\n"
        "• <code>/rates</code> - тоже курсы ЦБ РФ\n"
        "• <code>/convert 100 USD EUR</code> - конвертация валют\n"
        "• <code>/help</code> - эта справка\n\n"
        
        "🔄 <b>Конвертация валют:</b>\n"
        "• <code>/convert 100 USD EUR</code> - конвертирует сумму\n"
        "• <code>/convert 500 EUR RUB</code> - евро в рубли\n"
        "• <code>/convert 10000 JPY USD</code> - иены в доллары\n\n"
        
        "⚙️ <b>Настройки:</b>\n"
        "• <code>/setbase EUR</code> - устанавливает базовую валюту\n\n"
        
        "🔔 <b>Уведомления:</b>\n"
        "• <code>/alert USD RUB 80 above</code> - уведомит о курсе\n\n"
        
        "💡 <b>ИНФОРМАЦИЯ</b>\n\n"
        "• Курсы ЦБ РФ обновляются ежедневно\n"
        "• Данные предоставляются Центральным Банком РФ\n"
        "• Конвертация использует актуальные рыночные курсы"
    )
    
    # Клавиатура с кнопкой "Назад"
    keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
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
    await show_cbr_rates(update, context)

async def rate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) != 2:
        await update.message.reply_text("Используйте: /rate <из> <в>")
        return
    from_curr, to_curr = args
    rate, api_date = get_exchange_rate(from_curr, to_curr)
    if rate is not None:
        await update.message.reply_text(f"💱 <b>Курс на {api_date}:</b>\n1 {from_curr.upper()} = <b>{rate:.4f}</b> {to_curr.upper()}", parse_mode='HTML')
    else:
        await update.message.reply_text("❌ Не удалось получить курс.")

async def convert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) != 3:
        await update.message.reply_text("Используйте: /convert <сумма> <из> <в>")
        return
    try:
        amount = float(args[0])
    except ValueError:
        await update.message.reply_text("❌ Сумма должна быть числом.")
        return
    from_curr, to_curr = args[1], args[2]
    rate, api_date = get_exchange_rate(from_curr, to_curr)
    if rate is not None:
        result = amount * rate
        await update.message.reply_text(
            f"💱 <b>Конвертация по курсу на {api_date}:</b>\n\n"
            f"{amount} {from_curr.upper()} = <b>{result:.4f}</b> {to_curr.upper()}\n\n"
            f"<i>Курс: 1 {from_curr.upper()} = {rate:.4f} {to_curr.upper()}</i>", 
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text("❌ Не удалось выполнить конвертацию.")

async def setbase_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) != 1:
        await update.message.reply_text("Используйте: /setbase <валюта>")
        return
    currency = args[0].upper()
    user_id = update.effective_message.from_user.id
    await set_user_base_currency(user_id, currency)
    await update.message.reply_text(f"✅ Базовая валюта установлена: {currency}")

async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if len(args) != 4:
        await update.message.reply_text("Используйте: /alert <из> <в> <порог> <above|below>")
        return
    from_curr, to_curr = args[0], args[1]
    try:
        threshold = float(args[2])
    except ValueError:
        await update.message.reply_text("❌ Порог должен быть числом.")
        return
    direction = args[3].lower()
    if direction not in ['above', 'below']:
        await update.message.reply_text("❌ Направление должно быть 'above' или 'below'.")
        return
    user_id = update.effective_message.from_user.id
    await add_alert(user_id, from_curr, to_curr, threshold, direction)
    await update.message.reply_text(f"🔔 Уведомление установлено: {from_curr}/{to_curr} {'>' if direction == 'above' else '<'} {threshold}")

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
            [InlineKeyboardButton("📊 Курсы ЦБ РФ", callback_data='cbr_rates')],
            [InlineKeyboardButton("🔄 Конвертер валют", callback_data='converter')],
            [InlineKeyboardButton("❓ Помощь", callback_data='help')],
            [InlineKeyboardButton("⚙️ Настройки", callback_data='settings')],
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
    elif data == 'converter':
        await show_converter(update, context)
    elif data == 'settings':
        user_id = query.from_user.id
        base_currency = await get_user_base_currency(user_id)
        
        # Клавиатура с кнопкой "Назад"
        keyboard = [[InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await query.edit_message_text(
            f"⚙️ <b>Текущие настройки:</b>\n\n"
            f"• Базовая валюта: <b>{base_currency}</b>\n\n"
            "Используйте /setbase <валюта> для изменения базовой валюты.",
            parse_mode='HTML',
            reply_markup=reply_markup
        )

async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("❌ Неизвестная команда. Используйте /help для просмотра доступных команд.")

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
    application.add_handler(CommandHandler("cbr", cbr_rates_command))
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
