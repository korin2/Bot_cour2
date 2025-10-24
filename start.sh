#!/bin/bash

set -e  # Выход при ошибке

echo "Запуск Telegram Finance Bot..."

# Активируем виртуальное окружение (если используется)
if [ -d "venv" ]; then
    source venv/bin/activate
    echo "Виртуальное окружение активировано"
fi

# Устанавливаем зависимости
echo "Установка зависимостей..."
pip install -r requirements.txt

# Создаем необходимые директории
mkdir -p logs

# Проверяем переменные окружения
if [ -z "$TELEGRAM_BOT_TOKEN" ]; then
    echo "Ошибка: TELEGRAM_BOT_TOKEN не установлен"
    exit 1
fi

if [ -z "$DATABASE_URL" ]; then
    echo "Ошибка: DATABASE_URL не установлен"
    exit 1
fi

echo "Переменные окружения проверены успешно"

# Запускаем бота
echo "Запуск бота..."
exec python bot/main.py
