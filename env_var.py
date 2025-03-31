#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для настройки переменных окружения
"""

import os
from dotenv import load_dotenv

def setup_env():
    """Настраивает переменные окружения для бота"""
    # Загружаем переменные из .env файла
    load_dotenv()
    
    # Копируем BOT_TOKEN в TELEGRAM_TOKEN, если он существует
    if os.getenv('BOT_TOKEN') and not os.getenv('TELEGRAM_TOKEN'):
        os.environ['TELEGRAM_TOKEN'] = os.getenv('BOT_TOKEN')
        print("Установлена переменная TELEGRAM_TOKEN из BOT_TOKEN")
    
    # Проверяем наличие всех необходимых переменных
    required_vars = [
        "TELEGRAM_TOKEN",
        "DATABASE_URL",
        "OPENAI_API_KEY",
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        print(f"ВНИМАНИЕ: Отсутствуют следующие переменные окружения: {', '.join(missing_vars)}")
    else:
        print("Все необходимые переменные окружения найдены")

if __name__ == "__main__":
    setup_env() 