import os
import sys
import sqlite3
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def fix_first_interaction_time():
    logger.info("Исправление колонки first_interaction_time...")
    try:
        conn = sqlite3.connect('health_bot.db')
        cursor = conn.cursor()
        
        cursor.execute("PRAGMA table_info(users)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'first_interaction_time' not in columns:
            cursor.execute("ALTER TABLE users ADD COLUMN first_interaction_time DATETIME")
            logger.info("Колонка first_interaction_time добавлена")
            
            cursor.execute("UPDATE users SET first_interaction_time = registration_date")
            logger.info("Установлены значения для first_interaction_time из поля registration_date")
            
            conn.commit()
            logger.info("Миграция успешно завершена")
        else:
            logger.info("Колонка first_interaction_time уже существует")
            
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Ошибка при исправлении миграции: {str(e)}")
        return False

if __name__ == "__main__":
    fix_first_interaction_time()
