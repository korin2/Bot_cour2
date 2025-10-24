import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import logger, DEEPSEEK_API_KEY
from services import (
    get_currency_rates_with_tomorrow, format_currency_rates_message, 
    get_key_rate, format_key_rate_message, get_crypto_rates, 
    get_crypto_rates_fallback, format_crypto_rates_message, ask_deepseek
)
from utils import split_long_message, create_back_button
from db import get_user_alerts, clear_user_alerts, remove_alert, add_alert, update_user_info

# Основные команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start"""
    try:
        user = update.effective_user
        await update_user_info(user.id, user.first_name, user.username)
        
        greeting = f"Привет, {user.first_name}!" if user.first_name else "Привет!"
        
        # Проверяем доступность ИИ
        test_ai = await ask_deepseek("test", context)
        ai_available = not (test_ai.startswith("❌") or test_ai.startswith("⏰"))
        
        keyboard = [
            [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
            [InlineKeyboardButton("₿ Криптовалюты", callback_data='crypto_rates')],
            [InlineKeyboardButton("💎 Ключевая ставка", callback_data='key_rate')],
        ]
        
        if ai_available:
            keyboard.append([InlineKeyboardButton("🤖 Универсальный ИИ", callback_data='ai_chat')])
        else:
            keyboard.append([InlineKeyboardButton("❌ ИИ временно недоступен", callback_data='ai_unavailable')])
            
        keyboard.extend([
            [InlineKeyboardButton("🔔 Мои уведомления", callback_data='my_alerts')],
            [InlineKeyboardButton("🔧 Прочие функции", callback_data='other_functions')],
            [InlineKeyboardButton("❓ Помощь", callback_data='help')],
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        start_message = f'{greeting} Я бот для отслеживания финансовых данных!\n\nВыберите раздел:'
        await update.message.reply_text(start_message, parse_mode='HTML', reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Ошибка в команде /start: {e}")
        await update.message.reply_text("❌ Произошла ошибка при запуске бота.")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /help"""
    help_text = """
📚 **Доступные команды:**

/start - Главное меню
/rates - Курсы валют ЦБ РФ
/crypto - Курсы криптовалют  
/keyrate - Ключевая ставка ЦБ РФ
/ai - Чат с ИИ помощником
/myalerts - Мои уведомления
/alert - Создать уведомление
/help - Эта справка

💡 **Пример уведомления:**
/alert USD RUB 80 above - уведомит когда USD превысит 80 руб.
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def show_currency_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает курсы валют"""
    try:
        rates_today, date_today, rates_tomorrow, changes = get_currency_rates_with_tomorrow()
        
        if not rates_today:
            await update.effective_message.reply_text(
                "❌ Не удалось получить курсы валют.", 
                reply_markup=create_back_button()
            )
            return
        
        message = format_currency_rates_message(rates_today, date_today, rates_tomorrow, changes)
        await update.effective_message.reply_text(message, parse_mode='HTML', reply_markup=create_back_button())
        
    except Exception as e:
        logger.error(f"Ошибка при показе курсов валют: {e}")
        await update.effective_message.reply_text("❌ Ошибка при получении данных.")

async def show_key_rate(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает ключевую ставку"""
    try:
        key_rate_data = get_key_rate()
        
        if not key_rate_data:
            await update.effective_message.reply_text(
                "❌ Не удалось получить ключевую ставку.",
                reply_markup=create_back_button()
            )
            return
        
        message = format_key_rate_message(key_rate_data)
        
        keyboard = [
            [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.effective_message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Ошибка при показе ключевой ставки: {e}")
        await update.effective_message.reply_text("❌ Ошибка при получении данных.")

async def show_crypto_rates(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает курсы криптовалют"""
    try:
        # Показываем сообщение о загрузке
        loading_message = "🔄 <b>Загружаем курсы криптовалют...</b>"
        await update.effective_message.reply_text(loading_message, parse_mode='HTML', reply_markup=create_back_button())
        
        # Получаем данные
        crypto_rates = get_crypto_rates()
        
        # Если не удалось получить данные, используем fallback
        if not crypto_rates:
            logger.warning("Не удалось получить данные от CoinGecko, используем fallback")
            crypto_rates = get_crypto_rates_fallback()
        
        if not crypto_rates:
            error_msg = "❌ <b>Не удалось получить курсы криптовалют.</b>"
            await update.effective_message.reply_text(error_msg, parse_mode='HTML', reply_markup=create_back_button())
            return
        
        message_text = format_crypto_rates_message(crypto_rates)
        
        # Добавляем предупреждение если используем демо-данные
        if crypto_rates.get('source') == 'demo_fallback':
            message_text += "\n\n⚠️ <i>Используются демонстрационные данные (CoinGecko API недоступен)</i>"
        
        # Клавиатура с кнопками
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data='crypto_rates')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.effective_message.reply_text(message_text, parse_mode='HTML', reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Ошибка при показе курсов криптовалют: {e}")
        await update.effective_message.reply_text("❌ Ошибка при получении данных.", reply_markup=create_back_button())

async def show_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает интерфейс чата с ИИ"""
    try:
        if not DEEPSEEK_API_KEY:
            error_msg = "❌ <b>Функционал ИИ временно недоступен</b>"
            await update.effective_message.reply_text(error_msg, parse_mode='HTML', reply_markup=create_back_button())
            return
        
        # Активируем режим ИИ для пользователя
        context.user_data['ai_mode'] = True
        
        welcome_message = (
            "🤖 <b>УНИВЕРСАЛЬНЫЙ ИИ ПОМОЩНИК</b>\n\n"
            "Задайте мне любой вопрос по любой теме!\n\n"
            "🎯 <b>Основные направления:</b>\n"
            "• 💰 Финансы и инвестиции\n"
            "• 📊 Технологии и программирование\n"
            "• 🎓 Образование и наука\n"
            "• 🎨 Творчество и искусство\n"
            "• 🏥 Здоровье и спорт\n"
            "• 🌍 Путешествия и культура\n"
            "• 🔧 Советы и решение проблем\n"
            "• 💬 Общение и поддержка\n\n"
            "Просто напишите ваш вопрос в чат!\n\n"
            "<i>Для выхода из режима ИИ используйте кнопку 'Назад в меню'</i>"
        )
        
        keyboard = [
            [InlineKeyboardButton("💡 Примеры вопросов", callback_data='ai_examples')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.effective_message.reply_text(welcome_message, parse_mode='HTML', reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка при показе чата с ИИ: {e}")
        await update.effective_message.reply_text("❌ Ошибка при запуске ИИ помощника.", reply_markup=create_back_button())

async def show_other_functions(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает меню прочих функций"""
    try:
        message = (
            "🔧 <b>ПРОЧИЕ ФУНКЦИИ</b>\n\n"
            "Выберите дополнительную функцию:\n\n"
            
            "📊 <b>Аналитика:</b>\n"
            "• Статистика использования бота\n"
            "• Графики изменения курсов\n"
            "• Исторические данные\n\n"
            
            "⚙️ <b>Настройки:</b>\n"
            "• Настройка уведомлений\n"
            "• Выбор языка\n"
            "• Часовой пояс\n\n"
            
            "🔍 <b>Дополнительно:</b>\n"
            "• Информация о боте\n"
            "• Связь с разработчиком\n"
            "• Отзывы и предложения\n\n"
            
            "💡 <i>Эти функции находятся в разработке и будут добавлены в будущих обновлениях</i>"
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
            [InlineKeyboardButton("⚙️ Настройки", callback_data='settings')],
            [InlineKeyboardButton("ℹ️ О боте", callback_data='about')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if update.message:
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.effective_message.edit_text(message, parse_mode='HTML', reply_markup=reply_markup)
            
    except Exception as e:
        logger.error(f"Ошибка при показе прочих функций: {e}")
        await update.effective_message.reply_text("❌ Ошибка при загрузке функций.", reply_markup=create_back_button())

async def show_bot_stats(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает статистику бота"""
    try:
        from db import get_all_users, get_all_alerts
        
        users = await get_all_users()
        alerts = await get_all_alerts()
        
        total_users = len(users)
        total_alerts = len(alerts)
        active_alerts = len([alert for alert in alerts if alert.get('is_active', True)])
        
        message = (
            "📊 <b>СТАТИСТИКА БОТА</b>\n\n"
            f"👥 <b>Всего пользователей:</b> {total_users}\n"
            f"🔔 <b>Всего уведомлений:</b> {total_alerts}\n"
            f"🟢 <b>Активных уведомлений:</b> {active_alerts}\n"
            f"🔴 <b>Выполненных уведомлений:</b> {total_alerts - active_alerts}\n\n"
            
            "📈 <b>Популярные валюты для уведомлений:</b>\n"
        )
        
        # Анализируем популярные валюты
        currency_stats = {}
        for alert in alerts:
            currency = alert['from_currency']
            currency_stats[currency] = currency_stats.get(currency, 0) + 1
        
        if currency_stats:
            sorted_currencies = sorted(currency_stats.items(), key=lambda x: x[1], reverse=True)
            for currency, count in sorted_currencies[:5]:  # Топ-5 валют
                message += f"   • {currency}: {count} уведомлений\n"
        else:
            message += "   <i>Нет данных</i>\n"
        
        message += "\n💡 <i>Статистика обновляется в реальном времени</i>"
        
        keyboard = [
            [InlineKeyboardButton("🔄 Обновить", callback_data='stats')],
            [InlineKeyboardButton("🔧 Прочие функции", callback_data='other_functions')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.effective_message.edit_text(message, parse_mode='HTML', reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Ошибка при показе статистики: {e}")
        await update.effective_message.edit_text(
            "❌ Ошибка при загрузке статистики.",
            reply_markup=create_back_button()
        )

async def show_bot_about(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает информацию о боте"""
    try:
        message = (
            "ℹ️ <b>ИНФОРМАЦИЯ О БОТЕ</b>\n\n"
            
            "🤖 <b>Финансовый бот с ИИ помощником</b>\n\n"
            
            "📚 <b>Основные возможности:</b>\n"
            "• 💱 Курсы валют ЦБ РФ с прогнозом\n"
            "• ₿ Криптовалюты через CoinGecko API\n"
            "• 💎 Ключевая ставка ЦБ РФ\n"
            "• 🤖 Универсальный ИИ помощник\n"
            "• 🔔 Умные уведомления\n"
            "• 🌅 Ежедневная рассылка\n\n"
            
            "🛠 <b>Технологии:</b>\n"
            "• Python 3.8+\n"
            "• PostgreSQL\n"
            "• python-telegram-bot\n"
            "• DeepSeek AI API\n"
            "• CoinGecko API\n"
            "• ЦБ РФ API\n\n"
            
            "📞 <b>Поддержка:</b>\n"
            "• Для связи с разработчиком используйте команду /feedback\n"
            "• Сообщения об ошибках: /bugreport\n\n"
            
            "💡 <b>Версия:</b> 1.0.0\n"
            "🔄 <b>Последнее обновление:</b> Октябрь 2024\n\n"
            
            "⭐ <i>Бот постоянно развивается и улучшается!</i>"
        )
        
        keyboard = [
            [InlineKeyboardButton("📊 Статистика", callback_data='stats')],
            [InlineKeyboardButton("🔧 Прочие функции", callback_data='other_functions')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.effective_message.edit_text(message, parse_mode='HTML', reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Ошибка при показе информации о боте: {e}")
        await update.effective_message.edit_text(
            "❌ Ошибка при загрузке информации.",
            reply_markup=create_back_button()
        )

async def show_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает настройки"""
    try:
        message = (
            "⚙️ <b>НАСТРОЙКИ</b>\n\n"
            
            "🔔 <b>Уведомления:</b>\n"
            "• Ежедневная рассылка: <b>Включено</b>\n"
            "• Проверка уведомлений: <b>Каждые 30 минут</b>\n\n"
            
            "🌍 <b>Региональные настройки:</b>\n"
            "• Часовой пояс: <b>Москва (UTC+3)</b>\n"
            "• Язык: <b>Русский</b>\n\n"
            
            "📊 <b>Отображение:</b>\n"
            "• Формат чисел: <b>С разделителями</b>\n"
            "• Валюта по умолчанию: <b>RUB</b>\n\n"
            
            "💡 <i>Настройки будут доступны для изменения в будущих обновлениях</i>"
        )
        
        keyboard = [
            [InlineKeyboardButton("🔧 Прочие функции", callback_data='other_functions')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.effective_message.edit_text(message, parse_mode='HTML', reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Ошибка при показе настроек: {e}")
        await update.effective_message.edit_text(
            "❌ Ошибка при загрузке настроек.",
            reply_markup=create_back_button()
        )

async def handle_ai_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает текстовые сообщения для ИИ"""
    try:
        user_id = update.effective_user.id
        user_message = update.message.text
        
        # Проверяем, не является ли сообщение командой
        if user_message.startswith('/'):
            return
            
        # Проверяем, активирован ли режим ИИ для пользователя
        if context.user_data.get('ai_mode') != True:
            return
            
        # Показываем индикатор набора сообщения
        await update.message.chat.send_action(action="typing")
        
        # Отправляем запрос к DeepSeek
        ai_response = await ask_deepseek(user_message, context)
        
        # Разбиваем длинные сообщения на части
        message_parts = await split_long_message(ai_response)
        
        # Отправляем первую часть с клавиатурой
        first_part = message_parts[0]
        if len(message_parts) > 1:
            first_part += f"\n\n📄 <i>Часть 1 из {len(message_parts)}</i>"
        
        await update.message.reply_text(
            f"🤖 <b>ИИ Ассистент:</b>\n\n{first_part}",
            parse_mode='HTML',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Новый вопрос", callback_data='ai_chat')],
                [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
            ])
        )
        
        # Отправляем остальные части
        for i, part in enumerate(message_parts[1:], 2):
            part_text = part
            if i < len(message_parts):
                part_text += f"\n\n📄 <i>Часть {i} из {len(message_parts)}</i>"
            
            await update.message.reply_text(
                part_text,
                parse_mode='HTML'
            )
        
    except Exception as e:
        logger.error(f"Ошибка в обработчике ИИ сообщений: {e}")
        await update.message.reply_text(
            "❌ Произошла ошибка при обработке вашего запроса.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
            ])
        )

async def alert_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Создание уведомления о курсе валюты"""
    try:
        args = context.args
        
        if len(args) != 4:
            await update.message.reply_text(
                "📝 <b>Использование:</b> /alert &lt;из&gt; &lt;в&gt; &lt;порог&gt; &lt;above|below&gt;\n\n"
                "💡 <b>Примеры:</b>\n"
                "• <code>/alert USD RUB 80 above</code> - уведомить когда USD выше 80 руб.\n"
                "• <code>/alert EUR RUB 90 below</code> - уведомить когда EUR ниже 90 руб.",
                parse_mode='HTML',
                reply_markup=create_back_button()
            )
            return
        
        from_curr, to_curr = args[0].upper(), args[1].upper()
        
        # Проверяем поддерживаемые валюты
        supported_currencies = ['USD', 'EUR', 'GBP', 'JPY', 'CNY', 'CHF', 'CAD', 'AUD', 'TRY', 'KZT']
        if from_curr not in supported_currencies:
            await update.message.reply_text(
                f"❌ Валюта <b>{from_curr}</b> не поддерживается.\n\n"
                f"💱 <b>Доступные валюты:</b> {', '.join(supported_currencies)}",
                parse_mode='HTML',
                reply_markup=create_back_button()
            )
            return
        
        # Проверяем, что целевая валюта - RUB
        if to_curr != 'RUB':
            await update.message.reply_text(
                "❌ В настоящее время поддерживаются только уведомления для пар с RUB.\n"
                "💡 Используйте: <code>/alert USD RUB 80 above</code>",
                parse_mode='HTML',
                reply_markup=create_back_button()
            )
            return
        
        try:
            threshold = float(args[2])
            if threshold <= 0:
                raise ValueError("Порог должен быть положительным числом")
        except ValueError:
            await update.message.reply_text(
                "❌ Порог должен быть положительным числом.",
                reply_markup=create_back_button()
            )
            return
        
        direction = args[3].lower()
        if direction not in ['above', 'below']:
            await update.message.reply_text(
                "❌ Направление должно быть 'above' или 'below'.",
                reply_markup=create_back_button()
            )
            return
        
        user_id = update.effective_message.from_user.id
        
        # Добавляем уведомление
        await add_alert(user_id, from_curr, to_curr, threshold, direction)
        
        # Получаем текущий курс для информации
        rates_today, _, _, _ = get_currency_rates_with_tomorrow()
        current_rate = "N/A"
        if rates_today and from_curr in rates_today:
            current_rate = f"{rates_today[from_curr]['value']:.2f}"
        
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
            reply_markup=create_back_button()
        )
        
    except Exception as e:
        logger.error(f"Ошибка в команде /alert: {e}")
        await update.message.reply_text(
            f"❌ Произошла ошибка при установке уведомления:\n<code>{str(e)}</code>",
            parse_mode='HTML',
            reply_markup=create_back_button()
        )

async def myalerts_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает активные уведомления пользователя"""
    try:
        user_id = update.effective_user.id
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
            
            # Используем правильный метод для отправки сообщения
            if update.message:
                await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
            else:
                await update.effective_message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
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
                f"   💱 Текущий курс: <b>{current_rate} руб.</b>\n\n"
            )
        
        message += "⏰ <i>Уведомления проверяются каждые 30 минут автоматически</i>\n"
        message += "💡 <i>При срабатывании уведомление автоматически удаляется</i>"
        
        keyboard = [
            [InlineKeyboardButton("🗑 Очистить все", callback_data='clear_all_alerts')],
            [InlineKeyboardButton("💱 Создать ещё", callback_data='create_alert')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Используем правильный метод для отправки сообщения
        if update.message:
            await update.message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
        else:
            await update.effective_message.reply_text(message, parse_mode='HTML', reply_markup=reply_markup)
        
    except Exception as e:
        logger.error(f"Ошибка в команде /myalerts: {e}")
        error_message = "❌ <b>Ошибка при получении уведомлений.</b>"
        
        # Используем правильный метод для отправки сообщения об ошибке
        if update.message:
            await update.message.reply_text(error_message, parse_mode='HTML', reply_markup=create_back_button())
        else:
            await update.effective_message.reply_text(error_message, parse_mode='HTML', reply_markup=create_back_button())

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает главное меню"""
    try:
        user = update.effective_user
        greeting = f"Привет, {user.first_name}!" if user.first_name else "Привет!"
        
        # Проверяем доступность ИИ
        test_ai = await ask_deepseek("test", context)
        ai_available = not (test_ai.startswith("❌") or test_ai.startswith("⏰"))
        
        keyboard = [
            [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
            [InlineKeyboardButton("₿ Криптовалюты", callback_data='crypto_rates')],
            [InlineKeyboardButton("💎 Ключевая ставка", callback_data='key_rate')],
        ]
        
        if ai_available:
            keyboard.append([InlineKeyboardButton("🤖 Универсальный ИИ", callback_data='ai_chat')])
        else:
            keyboard.append([InlineKeyboardButton("❌ ИИ временно недоступен", callback_data='ai_unavailable')])
            
        keyboard.extend([
            [InlineKeyboardButton("🔔 Мои уведомления", callback_data='my_alerts')],
            [InlineKeyboardButton("🔧 Прочие функции", callback_data='other_functions')],
            [InlineKeyboardButton("❓ Помощь", callback_data='help')],
        ])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.effective_message.edit_text(
            f'{greeting} Я бот для отслеживания финансовых данных!\n\nВыберите раздел:',
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Ошибка при показе главного меню: {e}")

# Обработчики callback-кнопок
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик нажатий на inline-кнопки"""
    try:
        query = update.callback_query
        await query.answer()
        
        data = query.data
        
        if data == 'help':
            await help_command(update, context)
        elif data == 'back_to_main':
            context.user_data['ai_mode'] = False
            await show_main_menu(update, context)
        elif data == 'currency_rates':
            await show_currency_rates(update, context)
        elif data == 'crypto_rates':
            await show_crypto_rates(update, context)
        elif data == 'key_rate':
            await show_key_rate(update, context)
        elif data == 'ai_chat':
            await show_ai_chat(update, context)
        elif data == 'my_alerts':
            await myalerts_command(update, context)
        elif data == 'other_functions':
            await show_other_functions(update, context)
        elif data == 'stats':
            await show_bot_stats(update, context)
        elif data == 'about':
            await show_bot_about(update, context)
        elif data == 'settings':
            await show_settings(update, context)
        elif data == 'clear_all_alerts':
            user_id = update.effective_user.id
            await clear_user_alerts(user_id)
            await query.edit_message_text(
                "✅ Все уведомления очищены",
                reply_markup=create_back_button()
            )
        elif data == 'create_alert':
            await query.edit_message_text(
                "📝 <b>Создание уведомления</b>\n\n"
                "Используйте команду:\n"
                "<code>/alert USD RUB 80 above</code>\n\n"
                "💡 <b>Примеры:</b>\n"
                "• <code>/alert USD RUB 85 above</code> - уведомит когда USD выше 85 руб.\n"
                "• <code>/alert EUR RUB 90 below</code> - уведомит когда EUR ниже 90 руб.",
                parse_mode='HTML',
                reply_markup=create_back_button()
            )
        elif data == 'ai_examples':
            examples_text = (
                "💡 <b>ПРИМЕРЫ ВОПРОСОВ ДЛЯ ИИ:</b>\n\n"
                "💰 <b>Финансы:</b>\n"
                "• Как начать инвестировать с маленькой суммой?\n"
                "• Каков прогноз курса доллара на месяц?\n"
                "• В чем разница между акциями и облигациями?\n\n"
                "📊 <b>Технологии:</b>\n"
                "• Объясни что такое блокчейн простыми словами\n"
                "• Как создать телеграм бота на Python?\n"
                "• Какие языки программирования учить в 2024?\n\n"
                "🎓 <b>Образование:</b>\n"
                "• Как эффективно учиться новому?\n"
                "• Объясни теорию относительности Эйнштейна\n"
                "• Какие навыки будут востребованы в будущем?\n\n"
                "🎨 <b>Творчество:</b>\n"
                "• Придумай идею для стартапа в IT\n"
                "• Напиши короткое стихотворение о технологии\n"
                "• Какие тренды в дизайне сейчас популярны?\n\n"
                "🏥 <b>Здоровье:</b>\n"
                "• Как поддерживать здоровый образ жизни?\n"
                "• Какие упражнения делать при сидячей работе?\n"
                "• Как бороться со стрессом на работе?\n\n"
                "🌍 <b>Путешествия:</b>\n"
                "• Куда поехать отдыхать с ограниченным бюджетом?\n"
                "• Какие документы нужны для поездки в Европу?\n"
                "• Как путешествовать экологично?\n\n"
                "💬 <b>Просто поговорить:</b>\n"
                "• Расскажи интересный факт о космосе\n"
                "• Что думаешь об искусственном интеллекте?\n"
                "• Давай обсудим будущее технологий"
            )
            await query.edit_message_text(
                examples_text,
                parse_mode='HTML',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🤖 Задать вопрос", callback_data='ai_chat')],
                    [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
                ])
            )
        else:
            await query.edit_message_text(
                "🔄 <b>Функция в разработке</b>",
                parse_mode='HTML',
                reply_markup=create_back_button()
            )

    except Exception as e:
        logger.error(f"Ошибка в обработчике кнопок: {e}")
