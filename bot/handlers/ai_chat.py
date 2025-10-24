from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, CommandHandler, MessageHandler, filters
import logging

from bot.config import logger, DEEPSEEK_API_KEY
from bot.handlers.keyboards import get_ai_keyboard, get_back_to_main_keyboard
from bot.services.deepseek_api import ask_deepseek
from bot.utils.helpers import split_long_message

logger = logging.getLogger(__name__)

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
        ai_response = await ask_deepseek(user_message)
        
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
            reply_markup=get_back_to_main_keyboard()
        )

async def show_ai_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает интерфейс чата с ИИ"""
    try:
        if not DEEPSEEK_API_KEY:
            error_msg = (
                "❌ <b>Функционал ИИ временно недоступен</b>\n\n"
                "Отсутствует API ключ DeepSeek. Обратитесь к администратору."
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
            return
        
        # Тестируем подключение к API
        test_response = await ask_deepseek("Тестовое сообщение")
        if test_response.startswith("❌") or test_response.startswith("⏰"):
            # Если тест не прошел, показываем ошибку
            error_msg = (
                "❌ <b>Функционал ИИ временно недоступен</b>\n\n"
                f"{test_response}\n\n"
                "Попробуйте использовать другие функции бота."
            )
            keyboard = [
                [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
                [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            if hasattr(update, 'callback_query') and update.callback_query:
                await update.callback_query.edit_message_text(
                    error_msg, 
                    parse_mode='HTML', 
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    error_msg, 
                    parse_mode='HTML', 
                    reply_markup=reply_markup
                )
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
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                welcome_message, 
                parse_mode='HTML', 
                reply_markup=get_ai_keyboard()
            )
        else:
            await update.message.reply_text(
                welcome_message, 
                parse_mode='HTML', 
                reply_markup=get_ai_keyboard()
            )
            
    except Exception as e:
        logger.error(f"Ошибка при показе чата с ИИ: {e}")
        error_msg = "❌ Произошла ошибка при запуске ИИ помощника."
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.message.reply_text(
                error_msg,
                reply_markup=get_back_to_main_keyboard()
            )
        else:
            await update.message.reply_text(
                error_msg,
                reply_markup=get_back_to_main_keyboard()
            )

async def show_ai_examples(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает примеры вопросов для ИИ"""
    try:
        examples_text = (
            "💡 <b>ПРИМЕРЫ ВОПРОСОВ ДЛЯ ИИ</b>\n\n"
            
            "<b>💰 Финансы и инвестиции:</b>\n"
            "• Каков прогноз курса доллара на ближайшую неделю?\n"
            "• Во что инвестировать сбережения?\n"
            "• Как работает криптовалюта?\n\n"
            
            "<b>📊 Технологии:</b>\n"
            "• Как выучить Python с нуля?\n"
            "• В чем разница между AI и ML?\n"
            "• Как создать свой сайт?\n\n"
            
            "<b>🎓 Образование:</b>\n"
            "• Как эффективно учиться?\n"
            "• Какие книги по саморазвитию посоветуешь?\n"
            "• Как подготовиться к экзаменам?\n\n"
            
            "<b>🎨 Творчество:</b>\n"
            "• Как научиться рисовать?\n"
            "• Посоветуй хорошие фильмы\n"
            "• Как написать интересный рассказ?\n\n"
            
            "<b>🏥 Здоровье:</b>\n"
            "• Как начать заниматься спортом?\n"
            "• Какие продукты полезны для здоровья?\n"
            "• Как бороться со стрессом?\n\n"
            
            "<b>🌍 Путешествия:</b>\n"
            "• Куда поехать отдыхать в декабре?\n"
            "• Что посмотреть в Париже?\n"
            "• Как подготовиться к путешествию?\n\n"
            
            "<b>🔧 Советы:</b>\n"
            "• Как улучшить продуктивность?\n"
            "• Как наладить отношения с коллегами?\n"
            "• Как выбрать подарок?\n\n"
            
            "<b>💬 Разное:</b>\n"
            "• Расскажи интересный факт\n"
            "• Придумай шутку\n"
            "• Объясни теорию относительности\n\n"
            
            "<i>Напишите любой из этих вопросов или свой собственный!</i>"
        )
        
        keyboard = [
            [InlineKeyboardButton("🤖 Задать вопрос", callback_data='ai_chat')],
            [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        if hasattr(update, 'callback_query') and update.callback_query:
            await update.callback_query.edit_message_text(
                examples_text, 
                parse_mode='HTML', 
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                examples_text, 
                parse_mode='HTML', 
                reply_markup=reply_markup
            )
            
    except Exception as e:
        logger.error(f"Ошибка при показе примеров ИИ: {e}")

async def show_ai_unavailable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Показывает сообщение о недоступности ИИ"""
    try:
        message = (
            "❌ <b>ИИ ПОМОЩНИК ВРЕМЕННО НЕДОСТУПЕН</b>\n\n"
            "В настоящее время функционал ИИ недоступен по техническим причинам.\n\n"
            "Возможные причины:\n"
            "• Недостаточно средств на API аккаунте\n"
            "• Временные проблемы с сервисом DeepSeek\n"
            "• Превышены лимиты запросов\n\n"
            "Вы можете использовать другие функции бота."
        )
        
        keyboard = [
            [InlineKeyboardButton("💱 Курсы валют", callback_data='currency_rates')],
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
            
    except Exception as e:
        logger.error(f"Ошибка при показе сообщения о недоступности ИИ: {e}")

async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /ai"""
    await show_ai_chat(update, context)

def setup_ai_handlers(application):
    """Настройка обработчиков ИИ"""
    application.add_handler(CommandHandler("ai", ai_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_ai_message))
