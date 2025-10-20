import asyncpg
import os
from typing import Optional

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("Требуется переменная окружения DATABASE_URL")

print(f"Подключаюсь к: {DATABASE_URL}")  # <-- Добавим это для отладки

async def init_db():
    print("Инициализация БД...")
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            base_currency TEXT DEFAULT 'USD',
            timezone TEXT DEFAULT 'UTC'
        );
    ''')
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS alerts (
            id SERIAL PRIMARY KEY,
            user_id BIGINT NOT NULL,
            from_currency TEXT NOT NULL,
            to_currency TEXT NOT NULL,
            threshold DECIMAL NOT NULL,
            direction TEXT NOT NULL CHECK (direction IN ('above', 'below')),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
        );
    ''')
    await conn.close()
    print("БД инициализирована.")

async def get_user_base_currency(user_id: int) -> str:
    conn = await asyncpg.connect(DATABASE_URL)
    currency = await conn.fetchval('SELECT base_currency FROM users WHERE user_id = $1', user_id)
    await conn.close()
    return currency or 'USD'

async def set_user_base_currency(user_id: int, currency: str):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        INSERT INTO users (user_id, base_currency)
        VALUES ($1, $2)
        ON CONFLICT (user_id)
        DO UPDATE SET base_currency = $2
    ''', user_id, currency)
    await conn.close()

async def add_alert(user_id: int, from_curr: str, to_curr: str, threshold: float, direction: str):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        INSERT INTO alerts (user_id, from_currency, to_currency, threshold, direction)
        VALUES ($1, $2, $3, $4, $5)
    ''', user_id, from_curr, to_curr, threshold, direction)
    await conn.close()

async def get_all_alerts():
    conn = await asyncpg.connect(DATABASE_URL)
    alerts = await conn.fetch('SELECT * FROM alerts')
    await conn.close()
    return alerts
