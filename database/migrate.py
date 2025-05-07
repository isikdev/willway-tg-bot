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
    """
    Добавляет колонку commission_amount в таблицу blogger_referrals в базе данных willway_bloggers.db,
    если такая колонка еще не существует
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
        
        # Получаем информацию о колонках таблицы
        cursor.execute("PRAGMA table_info(blogger_referrals)")
        columns = [col[1] for col in cursor.fetchall()]
        
        # Проверяем, есть ли колонка commission_amount
        if 'commission_amount' not in columns:
            logger.info(f"Добавляем колонку commission_amount в таблицу blogger_referrals в базе {db_path}")
            
            # Добавляем колонку
            cursor.execute("ALTER TABLE blogger_referrals ADD COLUMN commission_amount REAL DEFAULT 0")
            
            # Проверяем, есть ли колонка converted
            if 'converted' not in columns:
                cursor.execute("ALTER TABLE blogger_referrals ADD COLUMN converted INTEGER DEFAULT 0")
                
            # Проверяем, есть ли колонка converted_at
            if 'converted_at' not in columns:
                cursor.execute("ALTER TABLE blogger_referrals ADD COLUMN converted_at TIMESTAMP")
                
            # Сохраняем изменения
            conn.commit()
            logger.info(f"Миграция базы данных {db_path} успешно выполнена")
        else:
            logger.info(f"Колонка commission_amount уже существует в таблице blogger_referrals")
        
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при миграции базы данных {db_path}: {str(e)}")
        return False

def migrate_bloggers_db():
    """Миграция базы данных блогеров"""
    logging.info("Начинаем миграцию базы данных блогеров")
    
    if not os.path.exists(BLOGGERS_DB_PATH):
        logging.warning(f"База данных {BLOGGERS_DB_PATH} не найдена. Миграция не требуется.")
        return

    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect(BLOGGERS_DB_PATH)
        c = conn.cursor()

        # Проверяем существование таблицы bloggers
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bloggers'")
        if not c.fetchone():
            c.execute('''
                CREATE TABLE bloggers (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    access_key TEXT UNIQUE,
                    referral_code TEXT UNIQUE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            logging.info("Создана таблица bloggers")

        # Проверяем существование таблицы blogger_referrals
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='blogger_referrals'")
        if not c.fetchone():
            c.execute('''
                CREATE TABLE blogger_referrals (
                    id INTEGER PRIMARY KEY,
                    blogger_id INTEGER,
                    user_id TEXT,
                    referral_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    converted INTEGER DEFAULT 0,
                    converted_at TIMESTAMP,
                    commission_amount REAL DEFAULT 0
                )
            ''')
            logging.info("Создана таблица blogger_referrals")
        else:
            # Проверяем и добавляем колонку user_id, если её нет
            c.execute("PRAGMA table_info(blogger_referrals)")
            columns = [column[1] for column in c.fetchall()]
            
            if 'user_id' not in columns:
                c.execute("ALTER TABLE blogger_referrals ADD COLUMN user_id TEXT")
                logging.info("Добавлена колонка user_id в таблицу blogger_referrals")
            
            # Проверяем и добавляем колонку source, если её нет
            if 'source' not in columns:
                c.execute("ALTER TABLE blogger_referrals ADD COLUMN source TEXT")
                logging.info("Добавлена колонка source в таблицу blogger_referrals")
            
            # Проверяем и добавляем колонку created_at, если её нет
            if 'created_at' not in columns:
                c.execute("ALTER TABLE blogger_referrals ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
                logging.info("Добавлена колонка created_at в таблицу blogger_referrals")
            
            # Проверяем и добавляем колонку converted, если её нет
            if 'converted' not in columns:
                c.execute("ALTER TABLE blogger_referrals ADD COLUMN converted INTEGER DEFAULT 0")
                logging.info("Добавлена колонка converted в таблицу blogger_referrals")
            
            # Проверяем и добавляем колонку converted_at, если её нет
            if 'converted_at' not in columns:
                c.execute("ALTER TABLE blogger_referrals ADD COLUMN converted_at TIMESTAMP")
                logging.info("Добавлена колонка converted_at в таблицу blogger_referrals")
            
            # Проверяем и добавляем колонку commission_amount, если её нет
            if 'commission_amount' not in columns:
                c.execute("ALTER TABLE blogger_referrals ADD COLUMN commission_amount REAL DEFAULT 0")
                logging.info("Добавлена колонка commission_amount в таблицу blogger_referrals")

        conn.commit()
        logging.info("Миграция базы данных блогеров успешно выполнена")
    except Exception as e:
        logging.error(f"Ошибка при миграции базы данных блогеров: {e}")
    finally:
        conn.close()

def add_cancel_columns_if_not_exist():
    """Добавляет колонки для отмены подписки, если их нет"""
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Проверяем, существуют ли колонки
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'cancel_reason' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN cancel_reason TEXT")
            logging.info("Добавлена колонка cancel_reason в таблицу users")
        
        if 'cancel_date' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN cancel_date TIMESTAMP")
            logging.info("Добавлена колонка cancel_date в таблицу users")
            
        if 'cancel_rate' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN cancel_rate INTEGER")
            logging.info("Добавлена колонка cancel_rate в таблицу users")
        
        conn.commit()
        conn.close()
        logging.info("Миграция колонок отмены подписок выполнена успешно")
    except Exception as e:
        logging.error(f"Ошибка при добавлении колонок для отмены подписки: {e}")

def migrate():
    """Запускает все миграции"""
    logging.info("Начинаем миграцию базы данных")
    add_cancel_columns_if_not_exist()
    migrate_bloggers_db()
    logging.info("Миграция базы данных завершена")

# Функция для запуска всех миграций
def run_migrations():
    """Запускает все необходимые миграции баз данных"""
    result = migrate_blogger_referrals()
    if result:
        logger.info("Миграция для системы блогеров успешно выполнена")
    
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