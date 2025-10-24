import logging

logger = logging.getLogger(__name__)

async def split_long_message(text: str, max_length: int = 4096) -> list:
    """Разбивает длинное сообщение на части для Telegram"""
    if len(text) <= max_length:
        return [text]
    
    parts = []
    while text:
        if len(text) <= max_length:
            parts.append(text)
            break
        
        # Ищем последний перенос строки в пределах лимита
        split_pos = text.rfind('\n', 0, max_length)
        if split_pos == -1:
            split_pos = text.rfind('.', 0, max_length)
        if split_pos == -1:
            split_pos = text.rfind(' ', 0, max_length)
        if split_pos == -1:
            split_pos = max_length
        
        parts.append(text[:split_pos + 1])
        text = text[split_pos + 1:]
    
    return parts

def safe_float_convert(value, default=0.0):
    """Безопасное преобразование в float"""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
