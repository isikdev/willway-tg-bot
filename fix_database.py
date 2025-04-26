#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging
import os
import sqlite3
import sys
import argparse

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def get_db_path():
    """Получает путь к базе данных"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, 'database', 'willway.db')
    
    if not os.path.exists(db_path):
        logger.error(f"❌ База данных не найдена по пути: {db_path}")
        
        # Проверяем альтернативные базы данных
        alt_db_paths = [
            os.path.join(script_dir, 'willway.db'),
            os.path.join(script_dir, 'health_bot.db'),
            os.path.join(script_dir, 'willway_bloggers.db')
        ]
        
        for alt_path in alt_db_paths:
            if os.path.exists(alt_path):
                logger.info(f"✅ База данных найдена: {alt_path}")
                return alt_path
        
        logger.error(f"❌ База данных не найдена ни в одном из возможных мест")
        return None
    
    return db_path

def check_column_exists(conn, table_name, column_name):
    """Проверяет, существует ли колонка в таблице"""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return any(col[1] == column_name for col in columns)

def add_column_if_not_exists(conn, table_name, column_name, column_type):
    """Добавляет колонку, если она не существует"""
    if not check_column_exists(conn, table_name, column_name):
        cursor = conn.cursor()
        try:
            cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
            logger.info(f"✅ Колонка {column_name} успешно добавлена в таблицу {table_name}")
            return True
        except sqlite3.Error as e:
            logger.error(f"❌ Ошибка при добавлении колонки {column_name}: {str(e)}")
            return False
    else:
        logger.info(f"ℹ️ Колонка {column_name} уже существует в таблице {table_name}")
        return False

def fix_users_table(conn):
    """Исправляет таблицу users"""
    logger.info("===== Исправление таблицы users =====")
    
    # Список колонок, которые нужно добавить
    columns_to_add = [
        ("first_name", "TEXT"),
        ("last_name", "TEXT"),
        ("chat_id", "INTEGER"),
        ("registered_at", "TIMESTAMP"),
        ("payment_status", "TEXT"),
        ("welcome_message_sent", "BOOLEAN DEFAULT 0"),
        ("referrer_id", "INTEGER"),
        ("referral_source", "TEXT"),
        ("blogger_ref_code", "TEXT")
    ]
    
    changes_made = False
    for column_name, column_type in columns_to_add:
        if add_column_if_not_exists(conn, "users", column_name, column_type):
            changes_made = True
    
    if changes_made:
        logger.info("✅ Таблица users успешно обновлена")
    else:
        logger.info("ℹ️ Таблица users уже содержит все необходимые колонки")

def create_bloggers_table(conn):
    """Создает таблицу для блогеров, если она не существует"""
    logger.info("===== Создание таблицы bloggers =====")
    
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS bloggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            telegram_username TEXT,
            email TEXT,
            access_key TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1,
            commission_rate REAL DEFAULT 0.1,
            total_referrals INTEGER DEFAULT 0,
            total_earnings REAL DEFAULT 0,
            paid_amount REAL DEFAULT 0,
            pending_amount REAL DEFAULT 0
        )
        """)
        logger.info("✅ Таблица bloggers успешно создана или уже существует")
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка при создании таблицы bloggers: {str(e)}")

def create_blogger_payments_table(conn):
    """Создает таблицу для выплат блогерам, если она не существует"""
    logger.info("===== Создание таблицы blogger_payments =====")
    
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS blogger_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blogger_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP,
            notes TEXT,
            FOREIGN KEY (blogger_id) REFERENCES bloggers (id)
        )
        """)
        logger.info("✅ Таблица blogger_payments успешно создана или уже существует")
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка при создании таблицы blogger_payments: {str(e)}")

def create_blogger_stats_table(conn):
    """Создает таблицу для статистики блогеров, если она не существует"""
    logger.info("===== Создание таблицы blogger_stats =====")
    
    cursor = conn.cursor()
    try:
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS blogger_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            blogger_id INTEGER NOT NULL,
            date DATE NOT NULL,
            clicks INTEGER DEFAULT 0,
            registrations INTEGER DEFAULT 0,
            payments INTEGER DEFAULT 0,
            earnings REAL DEFAULT 0,
            FOREIGN KEY (blogger_id) REFERENCES bloggers (id),
            UNIQUE(blogger_id, date)
        )
        """)
        logger.info("✅ Таблица blogger_stats успешно создана или уже существует")
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка при создании таблицы blogger_stats: {str(e)}")

def fix_database():
    """Основная функция для исправления базы данных"""
    db_path = get_db_path()
    if not db_path:
        logger.error("❌ Невозможно исправить базу данных: файл не найден")
        return False
    
    logger.info(f"🔧 Исправление базы данных по пути: {db_path}")
    
    try:
        conn = sqlite3.connect(db_path)
        
        # Исправляем таблицу users
        fix_users_table(conn)
        
        # Создаем таблицы для блогеров
        create_bloggers_table(conn)
        create_blogger_payments_table(conn)
        create_blogger_stats_table(conn)
        
        conn.commit()
        conn.close()
        
        logger.info("✅ База данных успешно обновлена")
        return True
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка при исправлении базы данных: {str(e)}")
        return False

def create_blogers_files():
    """Создает необходимые файлы для системы блогеров"""
    logger.info("===== Создание файлов для системы блогеров =====")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    blogers_dir = os.path.join(script_dir, 'willway_blogers')
    
    # Создаем директорию willway_blogers, если она не существует
    if not os.path.exists(blogers_dir):
        os.makedirs(blogers_dir)
        logger.info(f"✅ Создана директория {blogers_dir}")
        
        # Создаем поддиректории
        os.makedirs(os.path.join(blogers_dir, 'templates'), exist_ok=True)
        os.makedirs(os.path.join(blogers_dir, 'static'), exist_ok=True)
        logger.info(f"✅ Созданы поддиректории templates и static")
    
    return True

def main():
    """Основная функция"""
    parser = argparse.ArgumentParser(description='Исправление базы данных и создание файлов для блогеров')
    parser.add_argument('--blogers', action='store_true', help='Создать файлы для системы блогеров')
    args = parser.parse_args()
    
    success = fix_database()
    
    if args.blogers:
        create_blogers_files()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main()) 