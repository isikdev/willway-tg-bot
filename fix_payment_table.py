#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
import sqlite3
import sys

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_path():
    """Получает путь к базе данных"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Проверяем альтернативные базы данных
    alt_db_paths = [
        os.path.join(script_dir, 'health_bot.db'),
        os.path.join(script_dir, 'willway.db'),
        os.path.join(script_dir, 'willway_bloggers.db')
    ]
    
    for alt_path in alt_db_paths:
        if os.path.exists(alt_path):
            logger.info(f"✅ База данных найдена: {alt_path}")
            return alt_path
    
    logger.error(f"❌ База данных не найдена ни в одном из возможных мест")
    return None

def check_column_exists(conn, table_name, column_name):
    """Проверяет, существует ли колонка в таблице"""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return any(col[1] == column_name for col in columns)

def add_column_if_not_exists(conn, table_name, column_name, column_type, default_value=None):
    """Добавляет колонку, если она не существует"""
    if not check_column_exists(conn, table_name, column_name):
        cursor = conn.cursor()
        try:
            # Создаем SQL запрос с дефолтным значением, если оно указано
            sql = f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"
            if default_value is not None:
                if isinstance(default_value, str):
                    sql += f" DEFAULT '{default_value}'"
                else:
                    sql += f" DEFAULT {default_value}"
            
            cursor.execute(sql)
            logger.info(f"✅ Колонка {column_name} успешно добавлена в таблицу {table_name}")
            return True
        except sqlite3.Error as e:
            logger.error(f"❌ Ошибка при добавлении колонки {column_name}: {str(e)}")
            return False
    else:
        logger.info(f"ℹ️ Колонка {column_name} уже существует в таблице {table_name}")
        return False

def fix_payment_table(conn):
    """Исправляет таблицу payments"""
    logger.info("===== Исправление таблицы payments =====")
    
    # Список колонок, которые нужно добавить
    columns_to_add = [
        ("currency", "TEXT", "RUB"),
        ("created_at", "TIMESTAMP", "CURRENT_TIMESTAMP"),
        ("paid_at", "TIMESTAMP", None),
        ("status", "TEXT", "'pending'")
    ]
    
    for column_name, column_type, default_value in columns_to_add:
        add_column_if_not_exists(conn, "payments", column_name, column_type, default_value)

def main():
    """Основная функция"""
    db_path = get_db_path()
    if not db_path:
        logger.error("❌ Невозможно исправить базу данных: файл не найден")
        return False
    
    logger.info(f"🔧 Исправление базы данных по пути: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        
        # Исправляем таблицу payments
        fix_payment_table(conn)
        
        conn.commit()
        conn.close()
        
        logger.info("✅ База данных успешно обновлена")
        return True
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка при исправлении базы данных: {str(e)}")
        return False

if __name__ == "__main__":
    sys.exit(0 if main() else 1) 