# Добавьте эту функцию в db.py
async def update_user_info(user_id: int, first_name: str, username: str = None):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute('''
        INSERT INTO users (user_id, first_name, username, base_currency)
        VALUES ($1, $2, $3, 'USD')
        ON CONFLICT (user_id)
        DO UPDATE SET first_name = $2, username = $3
    ''', user_id, first_name, username)
    await conn.close()
