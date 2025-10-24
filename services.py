import requests
import xml.etree.ElementTree as ET
import json
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import logging
from config import CBR_API_BASE, COINGECKO_API_BASE, DEEPSEEK_API_BASE, DEEPSEEK_API_KEY

logger = logging.getLogger(__name__)

# Импорт функций из оригинального bot.py
# (перенесите сюда все функции работы с API из оригинального файла)
# get_currency_rates_for_date, get_currency_rates_with_tomorrow, 
# get_key_rate, get_crypto_rates, ask_deepseek и т.д.

def get_currency_rates_for_date(date_req):
    """Получает курсы валют на определенную дату"""
    try:
        url = f"{CBR_API_BASE}scripts/XML_daily.asp"
        params = {'date_req': date_req}
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code != 200:
            return None, None
        
        root = ET.fromstring(response.content)
        cbr_date = root.get('Date', '')
        
        rates = {}
        currency_codes = {
            'R01235': 'USD',  'R01239': 'EUR',  'R01035': 'GBP',  'R01820': 'JPY',
            'R01375': 'CNY',  'R01775': 'CHF',  'R01350': 'CAD',  'R01010': 'AUD',
            'R01700': 'TRY',  'R01335': 'KZT',
        }
        
        for valute in root.findall('Valute'):
            valute_id = valute.get('ID')
            if valute_id in currency_codes:
                currency_code = currency_codes[valute_id]
                name = valute.find('Name').text
                value = float(valute.find('Value').text.replace(',', '.'))
                nominal = int(valute.find('Nominal').text)
                
                if nominal > 1:
                    value = value / nominal
                
                rates[currency_code] = {
                    'value': value,
                    'name': name,
                    'nominal': nominal
                }
        
        return rates, cbr_date
        
    except Exception as e:
        logger.error(f"Ошибка при получении курсов на дату {date_req}: {e}")
        return None, None

# ... (остальные функции API из оригинального bot.py)
