from database.models import init_db
from database.migrations import run_migrations
import logging

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def initialize_database():
    """Инициализирует все таблицы в базе данных"""
    try:
        # Создаем все таблицы из моделей
        init_db()
        logger.info("Все таблицы успешно созданы")
        
        # Запускаем миграции для обновления полей
        run_migrations()
        logger.info("Миграции успешно применены")
        
        return True
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        return False

if __name__ == "__main__":
    initialize_database()
    print("База данных инициализирована!") 