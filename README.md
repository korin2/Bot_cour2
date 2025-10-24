bot/
├── __init__.py
├── main.py              # Точка входа
├── config.py            # Конфигурация и константы
├── handlers/            # Обработчики
│   ├── __init__.py
│   ├── commands.py      # Основные команды
│   ├── currency.py      # Курсы валют
│   ├── crypto.py        # Криптовалюты
│   ├── ai_chat.py       # ИИ функционал
│   ├── alerts.py        # Уведомления
│   └── keyboards.py     # Клавиатуры
├── services/            # Сервисы
│   ├── __init__.py
│   ├── cbr_api.py       # API ЦБ РФ
│   ├── coingecko_api.py # API CoinGecko
│   └── deepseek_api.py  # API DeepSeek
├── utils/               # Утилиты
│   ├── __init__.py
│   ├── formatters.py    # Форматирование сообщений
│   └── helpers.py       # Вспомогательные функции
└── jobs/               # Фоновые задачи
    ├── __init__.py
    ├── alerts.py        # Проверка уведомлений
    └── daily_rates.py   # Ежедневная рассылка
