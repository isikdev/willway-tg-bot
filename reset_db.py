#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Сброс и инициализация базы данных
"""

import os
import sys
import logging
from database.models import init_db

# Настраиваем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def reset_database():
    """Удаление старой базы данных и создание новой"""
    db_path = "health_bot.db"
    
    # Проверяем, существует ли файл базы данных
    if os.path.exists(db_path):
        try:
            # Пытаемся удалить файл базы данных
            os.remove(db_path)
            logger.info(f"База данных успешно удалена: {db_path}")
        except Exception as e:
            logger.error(f"Ошибка при удалении базы данных: {e}")
            logger.error("Возможно, файл используется другим процессом. Остановите бота перед сбросом базы.")
            sys.exit(1)
    
    # Инициализируем новую базу данных
    try:
        init_db()
        logger.info("Новая база данных успешно создана")
    except Exception as e:
        logger.error(f"Ошибка при создании новой базы данных: {e}")
        sys.exit(1)
    
    logger.info("База данных успешно сброшена и инициализирована")

if __name__ == "__main__":
    reset_database() 