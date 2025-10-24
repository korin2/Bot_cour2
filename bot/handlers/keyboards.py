from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def get_main_menu_keyboard(ai_available: bool = True):
    """Возвращает главное меню"""
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
        [InlineKeyboardButton("❓ Помощь", callback_data='help')],
    ])
    
    return InlineKeyboardMarkup(keyboard)

def get_back_to_main_keyboard():
    """Клавиатура с кнопкой 'Назад в меню'"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
    ])

def get_ai_keyboard():
    """Клавиатура для ИИ чата"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💡 Примеры вопросов", callback_data='ai_examples')],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
    ])

def get_alerts_keyboard():
    """Клавиатура для управления уведомлениями"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🗑 Очистить все", callback_data='clear_all_alerts')],
        [InlineKeyboardButton("💱 Создать ещё", callback_data='create_alert')],
        [InlineKeyboardButton("🔙 Назад в меню", callback_data='back_to_main')]
    ])
