from datetime import datetime

def format_currency_display(currency_data, show_changes=False, change_info=None):
    """Форматирует отображение данных о валюте"""
    if not currency_data:
        return ""
    
    name = currency_data.get('name', 'N/A')
    symbol = currency_data.get('symbol', '')
    value = currency_data.get('value', currency_data.get('price_rub', 0))
    change = currency_data.get('change_24h', 0)
    
    # Для JPY показываем за 100 единиц
    if symbol == 'JPY':
        display_value = value * 100
        value_text = f"{display_value:.2f}"
    else:
        value_text = f"{value:.2f}"
    
    result = f"<b>{name}</b> ({symbol}): <b>{value_text} руб.</b>"
    
    if show_changes and change_info:
        change_icon = "📈" if change_info['change'] > 0 else "📉" if change_info['change'] < 0 else "➡️"
        result += f" {change_icon}"
    
    return result

def format_percentage_change(change):
    """Форматирует процентное изменение"""
    if change is None:
        return "N/A"
    
    change_icon = "📈" if change > 0 else "📉" if change < 0 else "➡️"
    return f"{change_icon} {change:+.2f}%"
