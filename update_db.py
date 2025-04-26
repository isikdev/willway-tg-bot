import os
import sys
import logging
import sqlite3
from datetime import datetime

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

def check_column_exists(conn, table_name, column_name):
    """Проверяет, существует ли колонка в таблице"""
    cursor = conn.cursor()
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    return any(col[1] == column_name for col in columns)

def add_column_if_not_exists(conn, table_name, column_name, column_type, default_value=None):
    """Добавляет колонку в таблицу, если она не существует"""
    try:
        if not check_column_exists(conn, table_name, column_name):
            default_clause = f"DEFAULT {default_value}" if default_value is not None else ""
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type} {default_clause}")
            logger.info(f"✅ Добавлена колонка {column_name} в таблицу {table_name}")
            return True
        else:
            logger.info(f"✓ Колонка {column_name} уже существует в таблице {table_name}")
            return False
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка при добавлении колонки {column_name} в таблицу {table_name}: {str(e)}")
        return False

def update_payment_table(conn):
    """Обновляет таблицу payments"""
    logger.info("===== Обновление таблицы payments =====")
    
    # Добавляем поле subscription_type
    add_column_if_not_exists(conn, "payments", "subscription_type", "TEXT", None)
    conn.commit()

def update_referral_uses_table(conn):
    """Обновляет таблицу referral_uses"""
    logger.info("===== Обновление таблицы referral_uses =====")
    
    # Проверяем существование таблицы
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='referral_uses'")
    if not cursor.fetchone():
        logger.error("❌ Таблица referral_uses не существует в базе данных")
        return False
    
    # Добавляем необходимые столбцы
    columns_to_add = [
        ("user_id", "INTEGER", None),
        ("referrer_id", "INTEGER", None),
        ("subscription_purchased", "BOOLEAN", "0"),
        ("purchase_date", "TIMESTAMP", None),
        ("status", "TEXT", None)
    ]
    
    for column_name, column_type, default_value in columns_to_add:
        add_column_if_not_exists(conn, "referral_uses", column_name, column_type, default_value)
    
    conn.commit()
    return True

def check_db_path():
    """Проверяет и возвращает путь к файлу базы данных"""
    # Проверяем переменную окружения
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        logger.error("❌ Переменная окружения DATABASE_URL не установлена")
        sys.exit(1)
    
    # Извлекаем путь к файлу из URL
    if db_url.startswith("sqlite:///"):
        db_path = db_url[10:]  # убираем префикс sqlite:///
        if os.path.exists(db_path):
            logger.info(f"✅ Найден файл базы данных: {db_path}")
            return db_path
        else:
            logger.error(f"❌ Файл базы данных не найден по пути: {db_path}")
            sys.exit(1)
    else:
        logger.error(f"❌ Неподдерживаемый URL базы данных: {db_url}")
        sys.exit(1)

def main():
    """Главная функция обновления базы данных"""
    logger.info("🚀 Запуск обновления базы данных...")
    
    # Проверяем и получаем путь к БД
    db_path = check_db_path()
    
    # Подключаемся к базе данных
    try:
        conn = sqlite3.connect(db_path)
        logger.info(f"✅ Успешное подключение к базе данных: {db_path}")
        
        # Обновляем таблицы
        update_payment_table(conn)
        update_referral_uses_table(conn)
        
        logger.info("🎉 Обновление базы данных успешно завершено!")
    except sqlite3.Error as e:
        logger.error(f"❌ Ошибка при подключении к базе данных: {str(e)}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()
            logger.info("✅ Соединение с базой данных закрыто")

if __name__ == "__main__":
    main() 