# config.py
import os
from dotenv import load_dotenv

# Загружаем переменные из .env файла
load_dotenv()

class Config:
    """Конфигурация бота"""
    BOT_TOKEN = os.getenv('BOT_TOKEN')

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не найден в .env файле")

    # Настройки API для курсов валют
    EXCHANGE_API_URL = "https://api.exchangerate-api.com/v4/latest/{base_currency}"

    # Список поддерживаемых валют
    CURRENCIES = {
        'USD': {'name': 'Доллар США', 'symbol': '$'},
        'EUR': {'name': 'Евро', 'symbol': '€'},
        'RUB': {'name': 'Российский рубль', 'symbol': '₽'},
        'GBP': {'name': 'Фунт стерлингов', 'symbol': '£'},
        'JPY': {'name': 'Японская иена', 'symbol': '¥'},
        'CNY': {'name': 'Китайский юань', 'symbol': '¥'},
        'TRY': {'name': 'Турецкая лира', 'symbol': '₺'},
        'KZT': {'name': 'Казахстанский тенге', 'symbol': '₸'},
        'CHF': {'name': 'Швейцарский франк', 'symbol': '₣'},
        'CAD': {'name': 'Канадский доллар', 'symbol': 'C$'}
    }