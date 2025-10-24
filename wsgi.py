"""
WSGI точка входа (для совместимости)
"""
from bot.main import setup_application

application = setup_application()
