from setuptools import setup, find_packages

setup(
    name="telegram-finance-bot",
    version="1.0.0",
    packages=find_packages(),
    install_requires=[
        "python-telegram-bot==21.0",
        "requests",
        "python-dotenv",
        "asyncpg",
        "beautifulsoup4",
        "lxml",
    ],
    python_requires=">=3.8",
)
