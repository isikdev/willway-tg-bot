#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import sqlite3
import logging
from datetime import datetime
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Добавляем корень проекта в пути для импорта
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Получаем путь к базе данных из переменных окружения
db_url = os.getenv('DATABASE_URL')
if not db_url:
    print("Ошибка: DATABASE_URL не найден в переменных окружения.")
    sys.exit(1)

# Для SQLite извлекаем путь из URL
if db_url.startswith('sqlite:///'):
    db_path = db_url.replace('sqlite:///', '')
    logger.info(f"Используется база данных: {db_path}")
    
    # Проверяем существование файла БД
    if not os.path.exists(db_path):
        print(f"Ошибка: Файл базы данных не найден по пути {db_path}")
        sys.exit(1)
            
    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect(db_path)
        logger.info("Соединение с базой данных установлено")
        cursor = conn.cursor()
        
        # Проверяем, существуют ли уже колонки
        cursor.execute("PRAGMA table_info(users)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Добавляем колонку subscription_choice_journey если её нет
        if 'subscription_choice_journey' not in columns:
            logger.info("Добавление колонки subscription_choice_journey...")
            cursor.execute("ALTER TABLE users ADD COLUMN subscription_choice_journey TEXT")
            logger.info("Колонка subscription_choice_journey добавлена.")
        else:
            logger.info("Колонка subscription_choice_journey уже существует.")
        
        # Добавляем колонку subscription_feedback если её нет
        if 'subscription_feedback' not in columns:
            logger.info("Добавление колонки subscription_feedback...")
            cursor.execute("ALTER TABLE users ADD COLUMN subscription_feedback TEXT")
            logger.info("Колонка subscription_feedback добавлена.")
        else:
            logger.info("Колонка subscription_feedback уже существует.")
        
        # Добавляем новые поля в таблицу users для сомнений при выборе подписки
        add_column_if_not_exists(conn, 'users', 'subscription_doubt_status', 'TEXT')
        add_column_if_not_exists(conn, 'users', 'subscription_doubt_response', 'TEXT')
        add_column_if_not_exists(conn, 'users', 'subscription_doubt_feedback', 'TEXT')
        
        # Добавляем поля для реферальной системы
        add_column_if_not_exists(conn, 'users', 'referral_code', 'TEXT')
        add_column_if_not_exists(conn, 'users', 'referred_by', 'TEXT')
        
        # Добавляем поля для блогер-реферальной системы
        add_column_if_not_exists(conn, 'users', 'blogger_ref_code', 'TEXT')
        
        # Сохраняем изменения
        conn.commit()
        logger.info("Миграции успешно применены")
        conn.close()
        
        logger.info("Миграция базы данных успешно завершена.")
    except Exception as e:
        logger.error(f"Ошибка при миграции базы данных: {e}")
        sys.exit(1)
else:
    print("Поддерживается только SQLite база данных.")
    sys.exit(1)

def add_column_if_not_exists(conn, table, column, column_type):
    """
    Добавляет колонку в таблицу, если она не существует
    """
    cursor = conn.cursor()
    try:
        # Проверяем, существует ли колонка
        cursor.execute(f"SELECT {column} FROM {table} LIMIT 1")
        logger.info(f"Колонка {column} уже существует.")
    except sqlite3.OperationalError:
        # Колонки нет, добавляем
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {column_type}")
        conn.commit()
        logger.info(f"Добавлена колонка {column} типа {column_type} в таблицу {table}.")
    except Exception as e:
        logger.error(f"Ошибка при проверке/добавлении колонки {column}: {e}")
        raise

def create_table_if_not_exists(conn, table_name, create_sql):
    """
    Создает таблицу, если она не существует
    """
    cursor = conn.cursor()
    try:
        # Проверяем, существует ли таблица
        cursor.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if cursor.fetchone() is None:
            # Таблицы нет, создаем
            cursor.execute(create_sql)
            conn.commit()
            logger.info(f"Создана таблица {table_name}.")
        else:
            logger.info(f"Таблица {table_name} уже существует.")
    except Exception as e:
        logger.error(f"Ошибка при создании таблицы {table_name}: {e}")
        raise

def migrate_database():
    """
    Выполняет миграцию базы данных - добавляет новые колонки и таблицы
    """
    logger.info(f"Используется база данных: {db_path}")
    
    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect(db_path)
        logger.info("Соединение с базой данных установлено")
        
        # Добавляем новые колонки для сомнений пользователя при выборе подписки
        add_column_if_not_exists(conn, 'users', 'subscription_doubt_status', 'TEXT')
        add_column_if_not_exists(conn, 'users', 'subscription_doubt_response', 'TEXT')
        add_column_if_not_exists(conn, 'users', 'subscription_doubt_feedback', 'TEXT')
        
        # Добавляем поля для реферальной системы
        add_column_if_not_exists(conn, 'users', 'referral_code', 'TEXT')
        add_column_if_not_exists(conn, 'users', 'referred_by', 'TEXT')
        
        # Добавляем поля для блогер-реферальной системы
        add_column_if_not_exists(conn, 'users', 'blogger_ref_code', 'TEXT')
        
        # Закрываем соединение
        conn.close()
        logger.info("Миграция базы данных успешно завершена")
        return True
    
    except Exception as e:
        logger.error(f"Ошибка при миграции базы данных: {e}")
        return False

if __name__ == "__main__":
    migrate_database() 