import os
import sys
import logging
import sqlite3
from datetime import datetime

# Настраиваем логирование
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Добавляем путь к корневой директории проекта
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASE_DIR)

# Импортируем модели
try:
    from database.models import Base, PendingNotification, engine
    logger.info("Модели успешно импортированы")
except Exception as e:
    logger.error(f"Ошибка при импорте моделей: {str(e)}")
    sys.exit(1)

def create_pending_notifications_table():
    """Создает таблицу для хранения уведомлений, которые не были отправлены"""
    try:
        # Получаем путь к базе данных из строки подключения
        db_path = engine.url.database
        logger.info(f"Путь к базе данных: {db_path}")
        
        # Подключаемся к базе данных
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Проверяем, существует ли таблица
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='pending_notifications'")
        if cursor.fetchone():
            logger.info("Таблица pending_notifications уже существует")
        else:
            # Создаем таблицу
            cursor.execute('''
            CREATE TABLE pending_notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                message_type VARCHAR(50) NOT NULL,
                data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                sent BOOLEAN DEFAULT 0,
                sent_at TIMESTAMP,
                retries INTEGER DEFAULT 0
            )
            ''')
            
            # Создаем индекс для быстрого поиска по user_id
            cursor.execute('CREATE INDEX idx_pending_notifications_user_id ON pending_notifications(user_id)')
            
            conn.commit()
            logger.info("Таблица pending_notifications успешно создана")
        
        # Проверяем колонку reward_processed в таблице referral_uses
        cursor.execute("PRAGMA table_info(referral_uses)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]
        
        if 'reward_processed' not in column_names:
            logger.info("Добавление колонки reward_processed в таблицу referral_uses")
            cursor.execute("ALTER TABLE referral_uses ADD COLUMN reward_processed BOOLEAN DEFAULT 0")
            conn.commit()
            logger.info("Колонка reward_processed успешно добавлена")
        else:
            logger.info("Колонка reward_processed уже существует в таблице referral_uses")
        
        conn.close()
        logger.info("Обновление базы данных завершено успешно")
        
    except Exception as e:
        logger.error(f"Ошибка при создании таблицы: {str(e)}")
        return False
    
    return True

if __name__ == "__main__":
    logger.info("Начало процесса обновления базы данных...")
    if create_pending_notifications_table():
        logger.info("База данных успешно обновлена!")
    else:
        logger.error("Не удалось обновить базу данных.") 