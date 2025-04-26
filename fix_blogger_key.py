#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для исправления проблем с ключами блогеров в базе данных.
Проверяет наличие нужных таблиц и данных в них, исправляет некорректные ключи.
"""

import os
import logging
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Импортируем модели и функции
from willway_blogers.database.models import Base, Blogger, generate_access_key

def fix_blogger_keys():
    logger.info("===== Запуск исправления ключей блогеров =====")
    
    # Получаем путь к базе данных
    db_path = os.path.join(os.path.dirname(__file__), 'willway_bloggers.db')
    database_url = f"sqlite:///{db_path}"
    
    logger.info(f"Подключаемся к базе данных: {database_url}")
    
    try:
        # Создаем движок
        engine = create_engine(database_url)
        
        # Проверяем существование таблицы
        inspector = inspect(engine)
        if 'bloggers' not in inspector.get_table_names():
            logger.info("Таблица 'bloggers' не существует. Создаем...")
            Base.metadata.create_all(engine)
            logger.info("Таблица успешно создана")
        
        # Создаем сессию
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Проверяем количество блогеров
        blogger_count = session.query(Blogger).count()
        
        if blogger_count == 0:
            logger.info("Таблица пуста. Создаем тестового блогера...")
            test_blogger = Blogger(
                name="Тестовый Блогер",
                telegram_id="123456789",
                email="test@example.com",
                access_key=generate_access_key()
            )
            session.add(test_blogger)
            session.commit()
            logger.info("Тестовый блогер создан успешно")
        
        # Проверяем и исправляем ключи
        bloggers = session.query(Blogger).all()
        fixed_count = 0
        
        for blogger in bloggers:
            if not blogger.access_key or len(blogger.access_key) != 10:
                blogger.access_key = generate_access_key()
                fixed_count += 1
        
        if fixed_count > 0:
            session.commit()
            logger.info(f"Исправлено {fixed_count} ключей блогеров")
        else:
            logger.info("Все ключи блогеров в порядке")
        
        logger.info("✅ Исправление ключей блогеров завершено успешно")
        return True
        
    except SQLAlchemyError as e:
        logger.error(f"Ошибка базы данных: {str(e)}")
        logger.error("❌ Не удалось исправить ключи блогеров")
        return False
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {str(e)}")
        logger.error("❌ Не удалось исправить ключи блогеров")
        return False

if __name__ == "__main__":
    fix_blogger_keys() 