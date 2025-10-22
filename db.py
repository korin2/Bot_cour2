import asyncpg
import os

DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("Требуется переменная окружения DATABASE_URL")

async def init_db():
    """Инициализация базы данных и создание таблиц"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                first_name TEXT,
                username TEXT
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
        print("Таблицы созданы успешно")
    except Exception as e:
        print(f"Ошибка при создании таблиц: {e}")
        raise

async def update_user_info(user_id: int, first_name: str, username: str = None):
    """Обновление информации о пользователе"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute('''
            INSERT INTO users (user_id, first_name, username)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id)
            DO UPDATE SET first_name = $2, username = $3
        ''', user_id, first_name, username)
        await conn.close()
    except Exception as e:
        print(f"Ошибка при обновлении информации о пользователе: {e}")
        raise

async def add_alert(user_id: int, from_curr: str, to_curr: str, threshold: float, direction: str):
    """Добавление уведомления"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        await conn.execute('''
            INSERT INTO alerts (user_id, from_currency, to_currency, threshold, direction)
            VALUES ($1, $2, $3, $4, $5)
        ''', user_id, from_curr, to_curr, threshold, direction)
        await conn.close()
    except Exception as e:
        print(f"Ошибка при добавлении уведомления: {e}")
        raise

async def get_all_alerts():
    """Получение всех уведомлений"""
    try:
        conn = await asyncpg.connect(DATABASE_URL)
        alerts = await conn.fetch('SELECT * FROM alerts')
        await conn.close()
        return alerts
    except Exception as e:
        print(f"Ошибка при получении уведомлений: {e}")
        return []
