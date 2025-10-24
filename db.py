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
                f"   📊 Условие: курс <b>{'выше' if direction == 'above' else 'нише'}</b> {threshold} руб.\n"
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
