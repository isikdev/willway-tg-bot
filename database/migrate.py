import os
import sys
import logging
from datetime import datetime

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Добавляем путь к корневой директории проекта
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy import create_engine, Column, Boolean, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import sqlalchemy as sa
from dotenv import load_dotenv

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

if __name__ == "__main__":
    try:
        migrate_add_welcome_message_sent()
        migrate_database()
        print("Все миграции успешно выполнены!")
    except Exception as e:
        print(f"Ошибка при выполнении миграции: {e}")
    finally:
        connection.close() 