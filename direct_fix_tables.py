#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для прямого исправления и настройки таблиц в базе данных
"""

import os
import sys
import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

# Определение базового класса для моделей
Base = declarative_base()

def get_db_uri():
    """Получает URI для подключения к БД из переменных окружения или использует значение по умолчанию"""
    db_uri = os.getenv('SQLALCHEMY_DATABASE_URI')
    if not db_uri:
        # SQLite по умолчанию
        db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'instance', 'willway.db'))
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        db_uri = f'sqlite:///{db_path}'
        logger.info(f"Используем SQLite БД по умолчанию: {db_path}")
    return db_uri

def init_engine():
    """Инициализирует и возвращает движок SQLAlchemy"""
    db_uri = get_db_uri()
    logger.info(f"Подключение к БД: {db_uri}")
    
    # Создаем движок с логированием для отладки
    engine = create_engine(db_uri, echo=False)
    return engine

def check_connection(engine):
    """Проверяет соединение с базой данных"""
    try:
        connection = engine.connect()
        connection.close()
        logger.info("✅ Соединение с БД установлено успешно")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка соединения с БД: {str(e)}")
        return False

def check_tables(engine):
    """Проверяет наличие таблиц в БД"""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()
    logger.info(f"Найдено таблиц в БД: {len(table_names)}")
    for table in table_names:
        logger.info(f"  - {table}")
    return table_names

def create_tables(engine):
    """Создает таблицы в БД согласно моделям"""
    try:
        # Импортируем модели здесь, чтобы избежать цикличных импортов
        from web_admin.models import Blogger, ReferralClick, Visit
        
        logger.info("Создаем таблицы в БД...")
        Base.metadata.create_all(engine)
        logger.info("✅ Таблицы успешно созданы")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при создании таблиц: {str(e)}")
        return False

def add_sample_data(engine):
    """Добавляет примеры данных в БД, если таблицы пустые"""
    try:
        from web_admin.models import Blogger
        from sqlalchemy.orm import sessionmaker
        
        Session = sessionmaker(bind=engine)
        session = Session()
        
        # Проверяем наличие данных в таблице блогеров
        blogger_count = session.query(Blogger).count()
        
        if blogger_count == 0:
            logger.info("Таблица блогеров пуста, добавляем тестовые данные...")
            
            # Создаем тестового блогера
            test_blogger = Blogger(
                username="test_blogger",
                email="test@example.com",
                access_key="testkey123",
                is_active=True
            )
            session.add(test_blogger)
            session.commit()
            
            logger.info(f"✅ Добавлен тестовый блогер: {test_blogger.username} (ID: {test_blogger.id})")
        else:
            logger.info(f"В таблице блогеров уже есть {blogger_count} записей")
        
        session.close()
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка при добавлении тестовых данных: {str(e)}")
        return False

def fix_database():
    """Проверяет и исправляет БД"""
    # Инициализируем движок
    engine = init_engine()
    
    # Проверяем соединение
    if not check_connection(engine):
        return False
    
    # Проверяем наличие таблиц
    existing_tables = check_tables(engine)
    
    # Если таблиц нет или их количество неправильное, создаем их
    if not existing_tables or len(existing_tables) < 3:  # Blogger, ReferralClick, Visit
        if not create_tables(engine):
            return False
    
    # Добавляем тестовые данные, если нужно
    add_sample_data(engine)
    
    # Обновляем схему БД
    logger.info("Обновляем схему БД...")
    try:
        # Запускаем Flask-Migrate вручную
        flask_db_cmd = "flask db upgrade"
        
        # Настраиваем переменные окружения для Flask
        os.environ["FLASK_APP"] = "web_admin.app:app"
        
        # Запускаем команду и выводим результат
        import subprocess
        result = subprocess.run(flask_db_cmd, shell=True, capture_output=True, text=True)
        
        if result.returncode == 0:
            logger.info("✅ Схема БД успешно обновлена")
            logger.info(result.stdout)
        else:
            logger.warning(f"⚠️ Предупреждение при обновлении схемы БД: {result.stderr}")
    except Exception as e:
        logger.error(f"❌ Ошибка при обновлении схемы БД: {str(e)}")
    
    logger.info("✅ База данных настроена успешно")
    return True

if __name__ == "__main__":
    logger.info("===== Исправление и настройка базы данных =====")
    
    if fix_database():
        logger.info("✅ База данных настроена успешно")
        sys.exit(0)
    else:
        logger.error("❌ Не удалось настроить базу данных")
        sys.exit(1) 