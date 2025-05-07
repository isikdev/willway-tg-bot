#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Точка входа для запуска бота
"""

import os
import logging
import sys
import threading
from flask import Flask
from env_var import setup_env
from dotenv import load_dotenv
from bot.handlers import main
from database.migrate import add_cancellation_columns, migrate, migrate_blogger_referrals

# Устанавливаем переменные окружения
setup_env()

# Устанавливаем имя бота из настроек, если не указано явно
if not os.getenv("TELEGRAM_BOT_USERNAME"):
    from bot.handlers import get_bot_config
    try:
        config = get_bot_config()
        bot_username = config.get("bot_name", "willway_bot")
        os.environ["TELEGRAM_BOT_USERNAME"] = bot_username
        print(f"Установлена переменная TELEGRAM_BOT_USERNAME = {bot_username}")
    except Exception as e:
        print(f"Ошибка при установке имени бота: {str(e)}")
        os.environ["TELEGRAM_BOT_USERNAME"] = "willway_bot"

# Настраиваем логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log')
    ]
)

logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

# Проверка наличия всех необходимых переменных окружения
required_env_vars = [
    "TELEGRAM_TOKEN",
    "DATABASE_URL"
]

missing_vars = [var for var in required_env_vars if not os.getenv(var)]

if missing_vars:
    logger.error(f"Отсутствуют следующие переменные окружения: {', '.join(missing_vars)}")
    sys.exit(1)
else:
    logger.info("Все необходимые переменные окружения найдены")

# Выполнение миграций базы данных
try:
    add_cancellation_columns()
    logger.info("Миграция базы данных для добавления колонок отмены подписки выполнена")
except Exception as e:
    logger.error(f"Ошибка при выполнении миграции базы данных: {e}")

# Миграция базы данных
if migrate():
    logger.info("Миграция базы данных для добавления колонок отмены подписки выполнена")
else:
    logger.warning("Ошибка при миграции базы данных")

# Выполняем миграцию для базы данных блогеров
if migrate_blogger_referrals():
    logger.info("Миграция базы данных блогеров для добавления колонок комиссий выполнена")
else:
    logger.warning("Ошибка при миграции базы данных блогеров")

def check_environment():
    """Проверяет наличие всех необходимых переменных окружения"""
    required_vars = [
        "TELEGRAM_TOKEN",
        "DATABASE_URL",
        "OPENAI_API_KEY",
    ]
    
    missing_vars = [var for var in required_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Отсутствуют следующие переменные окружения: {', '.join(missing_vars)}")
        return False
        
    logger.info("Все необходимые переменные окружения найдены")
    return True

def run_flask_server():
    """Запускает Flask сервер для обработки вебхуков и запросов от Tilda"""
    try:
        from web import create_app
        
        app = create_app()
        
        # Явно устанавливаем настройки базы данных
        app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        # Получаем настройки из переменных окружения
        host = os.getenv("FLASK_HOST", "0.0.0.0")
        port = int(os.getenv("FLASK_PORT", 5000))
        
        logger.info(f"Запуск Flask сервера на {host}:{port}")
        app.run(host=host, port=port, threaded=True)
    except Exception as e:
        logger.error(f"Ошибка при запуске Flask сервера: {e}")

def run_telegram_bot():
    """Запускает Telegram бота"""
    try:
        # Сначала проверяем версию python-telegram-bot
        import telegram
        version = telegram.__version__
        logger.info(f"Используется python-telegram-bot версии {version}")
        
        try:
            # Создаем фиктивные классы для совместимости
            import sys
            from database.models import Payment
            
            # Создаем фиктивные классы, которые могут использоваться в коде,
            # но которых нет в моделях
            class PaymentRecord:
                pass
                
            class PaymentHistory:
                pass
                
            class PaymentEvent:
                pass
                
            # Добавляем их в модуль database.models
            import database.models
            database.models.PaymentRecord = PaymentRecord
            database.models.PaymentHistory = PaymentHistory
            database.models.PaymentEvent = PaymentEvent
            
            # Пробуем импортировать код бота с парсингом ParseMode из telegram (для v13.x)
            from bot.handlers import main as run_bot
            run_bot()
        except ImportError as e:
            if "cannot import name 'ParseMode' from 'telegram.constants'" in str(e):
                logger.info("Пробуем исправить импорт ParseMode...")
                # Патчим импорт ParseMode
                import sys
                from telegram import ParseMode
                sys.modules['telegram.constants'] = type('FakeModule', (), {'ParseMode': ParseMode})
                # Пробуем снова импортировать
                from bot.handlers import main as run_bot
                run_bot()
            else:
                raise e
    except ImportError as e:
        logger.error(f"Ошибка импорта модуля handlers: {e}")
    except Exception as e:
        logger.error(f"Ошибка при запуске бота: {e}")
        logger.exception(e)

def main():
    """Основная функция для запуска бота и веб-сервера"""
    logger.info("Запуск бота WillWay")
    
    # Проверяем переменные окружения
    if not check_environment():
        logger.error("Невозможно запустить бота из-за отсутствия переменных окружения")
        return
    
    # Запускаем Flask сервер в отдельном потоке
    flask_thread = threading.Thread(target=run_flask_server)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Запускаем Telegram бота в основном потоке
    run_telegram_bot()

if __name__ == "__main__":
    main()
