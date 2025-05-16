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

# Добавляем импорты для отслеживания изменений в файле конфигурации
import time
import json
import hashlib
import signal
import requests
import atexit
from datetime import datetime

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

def get_file_hash(file_path):
    """Вычисляет хеш-сумму файла для отслеживания изменений"""
    if not os.path.exists(file_path):
        return None
    
    try:
        with open(file_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        return file_hash
    except Exception as e:
        logger.error(f"Ошибка при вычислении хеш-суммы файла {file_path}: {e}")
        return None

def validate_json(file_path):
    """Проверяет, является ли файл валидным JSON"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            json.load(f)
        return True
    except json.JSONDecodeError as e:
        logger.error(f"Файл {file_path} содержит невалидный JSON: {e}")
        return False
    except Exception as e:
        logger.error(f"Ошибка при проверке файла {file_path}: {e}")
        return False

# Глобальная переменная для хранения последнего содержимого файла, чтобы определить автоматические изменения
last_file_content = None

def check_config_changed(file_path, last_hash):
    """Проверяет, изменился ли файл конфигурации"""
    global last_file_content, initial_hash
    
    current_hash = get_file_hash(file_path)
    
    if current_hash is None:
        return False
    
    if last_hash is None:
        # При первом запуске сохраняем содержимое файла
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                last_file_content = f.read()
        except Exception:
            pass
        return False  # Избегаем перезапуска при первоначальной загрузке
    
    changed = current_hash != last_hash
    
    if changed:
        # Читаем содержимое файла для анализа изменений
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                current_content = f.read()
                
            # Проверяем существенные изменения, игнорируя автоматические
            if last_file_content:
                # Загружаем JSON для сравнения
                import json
                try:
                    prev_config = json.loads(last_file_content)
                    current_config = json.loads(current_content)
                    
                    # Поля, которые могут меняться автоматически
                    auto_update_fields = ['description_pic_absolute_path', 'intro_video_file_id']
                    
                    # Копируем конфиги без автоматических полей для сравнения
                    prev_important = {k: v for k, v in prev_config.items() if k not in auto_update_fields}
                    current_important = {k: v for k, v in current_config.items() if k not in auto_update_fields}
                    
                    # Если существенные поля не изменились, игнорируем обновление
                    if prev_important == current_important:
                        logger.info(f"Игнорируем автоматическое изменение в файле {file_path}")
                        initial_hash = current_hash  # Обновляем хеш без перезапуска
                        last_file_content = current_content  # Обновляем сохраненное содержимое
                        return False
                    
                    logger.info(f"Обнаружены существенные изменения в конфигурации в файле {file_path}")
                    last_file_content = current_content
                except json.JSONDecodeError:
                    # Если не удается распарсить JSON, считаем, что есть изменения
                    logger.warning(f"Не удалось проанализировать JSON в файле {file_path}, считаем что файл изменился")
            else:
                last_file_content = current_content
                
            # Проверяем валидность JSON
            if not validate_json(file_path):
                logger.error(f"Файл {file_path} содержит некорректный JSON, изменения не будут применены")
                return False
        except Exception as e:
            logger.error(f"Ошибка при анализе изменений в файле: {e}")
            return False
    
    return changed

def restart_bot():
    """Перезапускает бота"""
    logger.info("Перезапуск бота из-за изменений в конфигурации...")
    
    # Закрываем все текущие соединения и освобождаем ресурсы
    cleanup()
    
    # Перезапускаем процесс
    os.execv(sys.executable, [sys.executable] + sys.argv)

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
        
        # Перед запуском бота удаляем webhook, чтобы избежать конфликтов
        try:
            # Получаем токен бота
            token = os.getenv("TELEGRAM_TOKEN")
            if token:
                import requests
                
                # Сначала проверим наличие активного webhook
                webhook_info_url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
                webhook_info_response = requests.get(webhook_info_url)
                
                if webhook_info_response.status_code == 200:
                    webhook_info = webhook_info_response.json()
                    if webhook_info.get("ok", False):
                        webhook_url = webhook_info.get("result", {}).get("url", "")
                        if webhook_url:
                            logger.info(f"Обнаружен активный webhook: {webhook_url}")
                        else:
                            logger.info("Webhook не установлен, можно запускать бота")
                
                # Удаляем вебхук
                logger.info("Выполняется удаление webhook перед запуском бота...")
                webhook_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
                response = requests.get(webhook_url)
                if response.status_code == 200 and response.json().get("ok"):
                    logger.info("Webhook успешно удален перед запуском бота")
                else:
                    logger.warning(f"Ошибка при удалении webhook: {response.text}")
                
                # Добавляем еще одну попытку удаления webhook с параметром drop_pending_updates
                webhook_url = f"https://api.telegram.org/bot{token}/deleteWebhook?drop_pending_updates=true"
                response = requests.get(webhook_url)
                if response.status_code == 200 and response.json().get("ok"):
                    logger.info("Webhook успешно удален с параметром drop_pending_updates")
                else:
                    logger.warning(f"Ошибка при удалении webhook с drop_pending_updates: {response.text}")
                    
                # Добавляем небольшую паузу, чтобы Telegram успел обработать запрос
                logger.info("Ожидание 3 секунды после удаления webhook...")
                time.sleep(3)
        except Exception as e:
            logger.error(f"Ошибка при попытке удалить webhook: {e}")
        
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

# Глобальные переменные для хранения потоков
flask_thread = None
bot_thread = None
stop_flag = False

def cleanup():
    """Функция для корректного завершения работы бота"""
    global stop_flag
    stop_flag = True
    logger.info("Выполняется корректное завершение работы бота...")
    
    # Останавливаем шедулер (если запущен)
    try:
        from telegram.ext import updater
        if hasattr(updater, 'job_queue') and updater.job_queue:
            updater.job_queue.stop()
    except Exception as e:
        logger.error(f"Ошибка при остановке шедулера: {e}")
    
    # Останавливаем webhook (если используется)
    try:
        from telegram.ext import updater
        if hasattr(updater, 'bot') and updater.bot:
            updater.bot.delete_webhook()
    except Exception as e:
        logger.error(f"Ошибка при удалении webhook: {e}")
    
    logger.info("Бот успешно завершил работу")

def signal_handler(signum, frame):
    """Обработчик сигналов для корректного завершения работы"""
    sig_name = signal.Signals(signum).name
    logger.info(f"Получен сигнал {sig_name}, завершаем работу бота...")
    cleanup()
    sys.exit(0)

# Регистрируем обработчик сигналов
signal.signal(signal.SIGTERM, signal_handler)
signal.signal(signal.SIGINT, signal_handler)

# Регистрируем функцию cleanup для вызова при завершении программы
atexit.register(cleanup)

def main():
    """Основная функция для запуска бота и веб-сервера"""
    global flask_thread, bot_thread, stop_flag, initial_hash, last_file_content
    
    logger.info("Запуск бота WillWay")
    
    # Проверяем переменные окружения
    if not check_environment():
        logger.error("Невозможно запустить бота из-за отсутствия переменных окружения")
        return
    
    # Путь к файлу конфигурации
    config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bot_config.json')
    logger.info(f"Путь к файлу конфигурации: {config_file}")
    
    # Получаем начальный хеш файла
    initial_hash = get_file_hash(config_file)
    logger.info(f"Начальный хеш конфигурации: {initial_hash}")
    
    # Считываем начальное содержимое файла
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            last_file_content = f.read()
    except Exception as e:
        logger.error(f"Ошибка при чтении начального содержимого файла: {e}")
    
    # Запускаем Flask сервер в отдельном потоке
    flask_thread = threading.Thread(target=run_flask_server)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Запускаем Telegram бота в основном потоке, чтобы обработчики сигналов работали правильно
    t = threading.Thread(target=lambda: monitor_config_changes(config_file, initial_hash))
    t.daemon = True
    t.start()
    
    # Запускаем бота в основном потоке
    run_telegram_bot()

def monitor_config_changes(config_file, initial_hash):
    """Отдельная функция для мониторинга изменений в конфигурации"""
    global stop_flag
    try:
        current_hash = initial_hash
        while not stop_flag:
            time.sleep(10)  # Проверяем каждые 10 секунд
            
            # Проверяем изменения в конфигурации
            if check_config_changed(config_file, current_hash):
                logger.info("Обнаружены изменения в конфигурационном файле, перезапускаем бота...")
                restart_bot()
                return  # Выходим из цикла, так как бот перезапущен
            
            # Обновляем текущий хеш для следующей проверки
            current_hash = get_file_hash(config_file)
            
    except Exception as e:
        logger.error(f"Ошибка в цикле мониторинга: {e}")
    except KeyboardInterrupt:
        logger.info("Получен сигнал завершения работы в мониторе конфигурации")
        stop_flag = True

if __name__ == "__main__":
    main()
