import os
import sys
import logging
from datetime import datetime
import sqlite3

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Добавляем корневую директорию в путь для импорта
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine, Column, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import sqlalchemy as sa
from dotenv import load_dotenv

# Теперь можем импортировать config
from config import BLOGGERS_DB_PATH, DATABASE_PATH

# Импортируем модуль миграций
from database.migrations import run_migrations
from database.models import init_db, get_session, User, ReferralCode, ReferralUse

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///health_bot.db")

# Создаем соединение с БД
engine = create_engine(DATABASE_URL)
connection = engine.connect()

# Функция для создания соединения с базой данных SQLite
def create_connection():
    """Создает соединение с базой данных"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        return conn
    except sqlite3.Error as e:
        logger.error(f"Ошибка при подключении к базе данных: {e}")
        return None

def migrate_add_welcome_message_sent():
    """Добавляет поле welcome_message_sent в таблицу users"""
    print("Начинаем миграцию: добавление поля welcome_message_sent в таблицу users")
    
    # Проверяем, существует ли уже колонка
    inspector = sa.inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('users')]
    
    if 'welcome_message_sent' not in columns:
        print("Добавляем колонку welcome_message_sent...")
        
        # Выполняем ALTER TABLE
        if 'sqlite' in DATABASE_URL:
            # SQLite не поддерживает простое добавление колонки с значением по умолчанию
            # Поэтому используем более сложный подход
            connection.execute(sa.text(
                "ALTER TABLE users ADD COLUMN welcome_message_sent BOOLEAN"
            ))
            connection.execute(sa.text(
                "UPDATE users SET welcome_message_sent = 0"
            ))
        else:
            # PostgreSQL/MySQL поддерживают значение по умолчанию
            connection.execute(sa.text(
                "ALTER TABLE users ADD COLUMN welcome_message_sent BOOLEAN DEFAULT FALSE"
            ))
        
        print("Колонка welcome_message_sent успешно добавлена!")
    else:
        print("Колонка welcome_message_sent уже существует. Пропускаем.")
    
    print("Миграция завершена.")

def migrate_database():
    logger.info("Начало миграции базы данных...")
    try:
        # Запускаем миграции через модуль миграций
        result = run_migrations()
        if result:
            logger.info("Миграция успешно завершена.")
        else:
            logger.error("Ошибка при выполнении миграций.")
            return False
        
        # Инициализируем таблицы, которые могли отсутствовать
        init_db()
        logger.info("Инициализация базы данных успешно завершена.")
        
        # Проверяем, созданы ли таблицы для реферальной системы
        session = get_session()
        try:
            # Проверяем наличие таблицы ReferralCode
            session.query(ReferralCode).first()
            logger.info("Таблица ReferralCode успешно создана.")
            
            # Проверяем наличие таблицы ReferralUse
            session.query(ReferralUse).first()
            logger.info("Таблица ReferralUse успешно создана.")
            
            # Генерируем реферальные коды для существующих пользователей, если их нет
            users = session.query(User).all()
            codes_generated = 0
            
            for user in users:
                # Проверяем, есть ли у пользователя реферальный код
                existing_code = session.query(ReferralCode).filter(
                    ReferralCode.user_id == user.user_id
                ).first()
                
                if not existing_code:
                    # Генерируем случайный код
                    import random
                    import string
                    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
                    
                    # Создаем запись в базе
                    ref_code = ReferralCode(
                        user_id=user.user_id,
                        code=code,
                        is_active=True,
                        created_at=datetime.now()
                    )
                    session.add(ref_code)
                    codes_generated += 1
            
            if codes_generated > 0:
                session.commit()
                logger.info(f"Сгенерировано {codes_generated} реферальных кодов для существующих пользователей.")
            
            return True
        except Exception as e:
            logger.error(f"Ошибка при проверке таблиц реферальной системы: {str(e)}")
            return False
        finally:
            session.close()
    
    except Exception as e:
        logger.error(f"Ошибка при миграции базы данных: {str(e)}")
        return False

def add_cancellation_columns():
    """
    Добавляет колонки для отмены подписки в таблицу users
    """
    session = get_session()
    try:
        # Проверяем, существуют ли уже колонки
        result = session.execute(text("PRAGMA table_info(users)"))
        columns = [row[1] for row in result]
        
        # Добавляем колонки, если их нет
        if 'cancellation_reason_1' not in columns:
            session.execute(text("ALTER TABLE users ADD COLUMN cancellation_reason_1 TEXT"))
            logger.info("Добавлена колонка cancellation_reason_1")
        
        if 'cancellation_reason_2' not in columns:
            session.execute(text("ALTER TABLE users ADD COLUMN cancellation_reason_2 TEXT"))
            logger.info("Добавлена колонка cancellation_reason_2")
        
        if 'cancellation_date' not in columns:
            session.execute(text("ALTER TABLE users ADD COLUMN cancellation_date DATETIME"))
            logger.info("Добавлена колонка cancellation_date")
        
        session.commit()
        logger.info("Миграция успешно выполнена")
        return True
    except Exception as e:
        session.rollback()
        logger.error(f"Ошибка при миграции базы данных: {e}")
        return False
    finally:
        session.close()

def migrate_blogger_referrals():
    """Добавляет колонку commission_amount в таблицу blogger_referrals, если её нет"""
    connection = create_connection()
    if not connection:
        return False
    
    try:
        # Проверяем наличие колонки commission_amount
        cursor = connection.cursor()
        cursor.execute("PRAGMA table_info(blogger_referrals);")
        columns = cursor.fetchall()
        
        column_names = [column[1] for column in columns]
        
        # Добавляем колонку commission_amount, если её нет
        if 'commission_amount' not in column_names:
            cursor.execute("ALTER TABLE blogger_referrals ADD COLUMN commission_amount REAL DEFAULT 0;")
            connection.commit()
            logger.info("Миграция: добавлена колонка commission_amount в таблицу blogger_referrals")
        
        connection.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при миграции таблицы blogger_referrals: {e}")
        if connection:
            connection.close()
        return False

def migrate_health_assistant_flag():
    """Добавляет колонку health_assistant_first_time в таблицу users, если её нет"""
    connection = create_connection()
    if not connection:
        return False
    
    try:
        # Проверяем наличие колонки health_assistant_first_time
        cursor = connection.cursor()
        cursor.execute("PRAGMA table_info(users);")
        columns = cursor.fetchall()
        
        column_names = [column[1] for column in columns]
        
        # Добавляем колонку health_assistant_first_time, если её нет
        if 'health_assistant_first_time' not in column_names:
            cursor.execute("ALTER TABLE users ADD COLUMN health_assistant_first_time BOOLEAN DEFAULT 1;")
            connection.commit()
            logger.info("Миграция: добавлена колонка health_assistant_first_time в таблицу users")
        
        connection.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при миграции таблицы users для health_assistant_first_time: {e}")
        if connection:
            connection.close()
        return False

def migrate():
    """Выполняет все необходимые миграции базы данных"""
    # Выполняем миграции по порядку
    success = True
    
    # Миграция для добавления колонок для отмены подписки
    if not add_cancellation_columns():
        logger.error("Не удалось добавить колонки для отмены подписки")
        success = False
    
    # Миграция для добавления колонки для blogger_referrals
    if not migrate_blogger_referrals():
        logger.error("Не удалось добавить колонку commission_amount в таблицу blogger_referrals")
        success = False
        
    # Миграция для добавления колонки health_assistant_first_time
    if not migrate_health_assistant_flag():
        logger.error("Не удалось добавить колонку health_assistant_first_time в таблицу users")
        success = False
    
    return success
    
def migrate_blogger_access_key():
    """
    Изменяет длину поля access_key в таблице bloggers для совместимости с кодом
    """
    try:
        # Путь к базе данных
        db_path = 'willway_bloggers.db'
        
        # Проверяем существование файла базы данных
        if not os.path.exists(db_path):
            logger.warning(f"База данных {db_path} не найдена. Миграция не требуется.")
            return
            
        # Подключаемся к базе данных
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Создаем временную таблицу с новой структурой
        cursor.execute('''
            CREATE TABLE bloggers_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                telegram_id TEXT,
                email TEXT,
                access_key TEXT UNIQUE NOT NULL,
                join_date TIMESTAMP,
                total_earned REAL DEFAULT 0.0,
                total_referrals INTEGER DEFAULT 0,
                total_conversions INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
        # Копируем данные из старой таблицы в новую
        cursor.execute('''
            INSERT INTO bloggers_new (id, name, telegram_id, email, access_key, join_date, total_earned, total_referrals, total_conversions, is_active)
            SELECT id, name, telegram_id, email, access_key, join_date, total_earned, total_referrals, total_conversions, is_active FROM bloggers
        ''')
        
        # Удаляем старую таблицу и переименовываем новую
        cursor.execute("DROP TABLE bloggers")
        cursor.execute("ALTER TABLE bloggers_new RENAME TO bloggers")
        
        conn.commit()
        logger.info("Успешно изменена длина поля access_key в таблице bloggers")
        
    except Exception as e:
        logger.error(f"Ошибка при изменении длины поля access_key: {str(e)}")
        if conn:
            conn.rollback()
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    try:
        migrate_add_welcome_message_sent()
        migrate_database()
        add_cancellation_columns()
        migrate()
        migrate_blogger_access_key()
        print("Все миграции успешно выполнены!")
    except Exception as e:
        print(f"Ошибка при выполнении миграции: {e}")
    finally:
        connection.close() 