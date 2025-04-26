#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для одновременного запуска двух сервисов:
1. Админ-сервис (web_admin)
2. Сервис блогеров (web_bloggers)
"""

import os
import sys
import subprocess
import time
import threading
import logging
import signal
import atexit
from pathlib import Path
import importlib.util

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Глобальные переменные для процессов
admin_process = None
bloggers_process = None
processes = []

def signal_handler(sig, frame):
    """Обработчик сигналов для корректного завершения"""
    logger.info(f"Получен сигнал {sig}. Завершаем все процессы...")
    terminate_all()
    sys.exit(0)

def terminate_all():
    """Завершает все запущенные процессы"""
    global processes, admin_process, bloggers_process
    
    for process in processes:
        if process and process.poll() is None:
            logger.info(f"Завершаю процесс: {process.args}")
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning(f"Таймаут при завершении процесса {process.args}. Принудительное завершение.")
                process.kill()
            except Exception as e:
                logger.error(f"Ошибка при завершении процесса: {str(e)}")
    
    processes = []
    admin_process = None
    bloggers_process = None
    logger.info("Все процессы завершены")

def run_command(command, env=None, cwd=None):
    """Запускает команду и возвращает процесс"""
    logger.info(f"Запуск команды: {command}")
    
    # Объединяем текущее окружение с дополнительными переменными
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    
    # Запускаем процесс
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=full_env,
            cwd=cwd,
            bufsize=1,
            universal_newlines=True
        )
        processes.append(process)
        return process
    except Exception as e:
        logger.error(f"Ошибка при запуске команды '{command}': {str(e)}")
        return None

def log_output(process, service_name):
    """Выводит и логирует вывод процесса"""
    for line in iter(process.stdout.readline, ""):
        if line:
            logger.info(f"[{service_name}] {line.strip()}")
    
    if process.poll() is not None:
        logger.warning(f"Процесс {service_name} завершился с кодом: {process.returncode}")

def run_service(command, service_name, env=None, cwd=None):
    """Запускает сервис и настраивает логирование его вывода"""
    process = run_command(command, env, cwd)
    
    if not process:
        logger.error(f"Не удалось запустить сервис {service_name}")
        return None
    
    # Запускаем поток для логирования вывода
    thread = threading.Thread(target=log_output, args=(process, service_name), daemon=True)
    thread.start()
    
    logger.info(f"Сервис {service_name} запущен, PID: {process.pid}")
    return process

def check_process(process, service_name):
    """Проверяет состояние процесса и перезапускает его при необходимости"""
    global admin_process, bloggers_process
    
    if not process or process.poll() is not None:
        logger.warning(f"Сервис {service_name} не работает, перезапускаем...")
        
        if service_name == "admin":
            admin_process = start_admin_service()
            return admin_process
        elif service_name == "bloggers":
            bloggers_process = start_bloggers_service()
            return bloggers_process
    
    return process

def fix_database():
    """Запускает скрипт для исправления и настройки базы данных"""
    logger.info("Проверяем и исправляем базу данных...")
    
    # Проверяем наличие прямого скрипта исправления БД
    db_fix_script = Path("direct_fix_tables.py")
    if db_fix_script.exists():
        logger.info(f"Запуск скрипта исправления таблиц: {db_fix_script}")
        try:
            result = subprocess.run(
                [sys.executable, str(db_fix_script)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )
            logger.info(f"Результат исправления таблиц БД: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"❌ Ошибка при исправлении таблиц БД: {e.stdout}")
            return False
        except Exception as e:
            logger.error(f"❌ Ошибка при запуске скрипта исправления таблиц БД: {str(e)}")
            return False
    
    # Запускаем скрипт исправления ключей блогеров
    blogger_key_script = Path("fix_blogger_key.py")
    if not blogger_key_script.exists():
        logger.error(f"Скрипт исправления ключей блогеров не найден: {blogger_key_script}")
        return False
    
    logger.info(f"Запуск скрипта исправления ключей блогеров: {blogger_key_script}")
    try:
        result = subprocess.run(
            [sys.executable, str(blogger_key_script)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )
        logger.info(f"Результат исправления ключей блогеров: {result.stdout}")
        logger.info("✅ База данных успешно настроена")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Ошибка при исправлении ключей блогеров: {e.stdout}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске скрипта исправления ключей блогеров: {str(e)}")
        return False

def setup_database():
    """Настраивает базу данных перед запуском сервисов"""
    # Сначала запускаем исправление базы данных
    if not fix_database():
        logger.warning("⚠️ Не удалось исправить базу данных. Попытка стандартной настройки.")
    
    # Запускаем стандартную настройку базы данных через Flask-Migrate
    logger.info("Настраиваем базу данных...")
    
    # Настраиваем переменные окружения для Flask
    flask_env = {
        "FLASK_APP": "web_admin.app:app"
    }
    
    # Создаем миграции, если они еще не созданы
    run_command("flask db init", env=flask_env)
    run_command("flask db migrate", env=flask_env)
    
    # Обновляем базу данных
    migrate_process = run_command("flask db upgrade", env=flask_env)
    if migrate_process:
        migrate_process.wait()
        logger.info("База данных настроена")
        return True
    else:
        logger.error("Не удалось настроить базу данных")
        return False

def start_admin_service():
    """Запускает сервис администратора"""
    logger.info("Запуск admin сервиса...")
    
    # Настройка переменных окружения для admin сервиса
    admin_env = {
        "FLASK_APP": "web_admin.app:app",
        "FLASK_ENV": "development",
        "FLASK_DEBUG": "1"
    }
    
    # Запускаем сервис на порту 5000
    command = "flask run --host=0.0.0.0 --port=5000"
    return run_service(command, "admin", env=admin_env)

def start_bloggers_service():
    """Запускает сервис блогеров"""
    logger.info("Запуск bloggers сервиса...")
    
    # Настройка переменных окружения для bloggers сервиса
    bloggers_env = {
        "FLASK_APP": "web_bloggers.app:app",
        "FLASK_ENV": "development",
        "FLASK_DEBUG": "1"
    }
    
    # Запускаем сервис на порту 5001
    command = "flask run --host=0.0.0.0 --port=5001"
    return run_service(command, "bloggers", env=bloggers_env)

def main():
    """Основная функция для запуска всех сервисов"""
    global admin_process, bloggers_process
    
    # Регистрируем обработчики сигналов для корректного завершения
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(terminate_all)
    
    logger.info("===== Запуск всех сервисов =====")
    
    # Настраиваем базу данных
    if not setup_database():
        logger.error("Не удалось настроить базу данных. Завершение...")
        sys.exit(1)
    
    # Запускаем сервисы
    admin_process = start_admin_service()
    time.sleep(2)  # Небольшая задержка между запусками
    bloggers_process = start_bloggers_service()
    
    if not admin_process or not bloggers_process:
        logger.error("Не удалось запустить все сервисы. Завершение...")
        terminate_all()
        sys.exit(1)
    
    logger.info("✅ Все сервисы запущены")
    logger.info("📊 Админ-панель доступна по адресу: http://localhost:5000")
    logger.info("🖥️ Панель блогеров доступна по адресу: http://localhost:5001")
    
    # Мониторинг процессов
    try:
        while True:
            admin_process = check_process(admin_process, "admin")
            bloggers_process = check_process(bloggers_process, "bloggers")
            time.sleep(5)
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания. Завершаем...")
    finally:
        terminate_all()

if __name__ == "__main__":
    main() 