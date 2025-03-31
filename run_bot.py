#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Точка входа для запуска бота
"""

import os
import logging
import sys
from env_var import setup_env

# Устанавливаем переменные окружения
setup_env()

# Настраиваем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)

logger = logging.getLogger(__name__)

def check_environment():
    """Проверяет наличие всех необходимых переменных окружения"""
    required_vars = [
        "TELEGRAM_TOKEN",
        "DATABASE_URL",
        "OPENAI_API_KEY",
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Отсутствуют следующие переменные окружения: {', '.join(missing_vars)}")
        return False
        
    logger.info("Все необходимые переменные окружения найдены")
    return True

def main():
    """Основная функция для запуска бота"""
    logger.info("Запуск бота WillWay")
    
    # Проверяем переменные окружения
    if not check_environment():
        logger.error("Невозможно запустить бота из-за отсутствия переменных окружения")
        return
    
    # Импортируем функцию main из модуля handlers
    try:
        from bot.handlers import main as run_bot
        
        # Запускаем бота
        run_bot()
    except ImportError as e:
        logger.error(f"Ошибка импорта модуля handlers: {e}")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")

if __name__ == "__main__":
    main()
