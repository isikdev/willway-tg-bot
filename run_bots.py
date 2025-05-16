#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для запуска системы управления всеми ботами
Запускает основной бот и блогер-бот независимо друг от друга
"""

import os
import sys
import logging
import subprocess
import signal
import time
import threading

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bots_manager.log')
    ]
)

logger = logging.getLogger(__name__)

def stream_output(stream, prefix):
    """Читает вывод процесса и выводит его в консоль с префиксом"""
    for line in iter(stream.readline, ''):
        if line:
            print(f"{prefix} | {line.strip()}")

def run_bots_manager():
    """Запускает систему управления ботами"""
    try:
        logger.info("Запуск системы управления ботами WILLWAY")
        
        # Определяем интерпретатор Python
        python_executable = sys.executable
        if not python_executable:
            python_executable = 'python'  # Или python3, в зависимости от системы
        
        # Запускаем основной бот напрямую (теперь он сам отслеживает свои изменения)
        main_bot_process = subprocess.Popen(
            [python_executable, 'run_bot.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        logger.info(f"Основной бот запущен, PID: {main_bot_process.pid}")
        
        # Создаем поток для вывода логов основного бота
        main_bot_thread = threading.Thread(
            target=stream_output,
            args=(main_bot_process.stdout, "[MAIN BOT]"),
            daemon=True
        )
        main_bot_thread.start()
        
        # Запускаем процесс мониторинга для блогер-бота
        blogger_watcher_process = subprocess.Popen(
            [python_executable, 'run_watcher.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        logger.info(f"Система мониторинга блогер-бота запущена, PID: {blogger_watcher_process.pid}")
        
        # Создаем поток для вывода логов блогер-бота
        blogger_thread = threading.Thread(
            target=stream_output,
            args=(blogger_watcher_process.stdout, "[BLOGGER BOT]"),
            daemon=True
        )
        blogger_thread.start()
        
        # Основной цикл для проверки работоспособности процессов
        while True:
            time.sleep(5)
            
            # Проверяем основной бот
            if main_bot_process.poll() is not None:
                exit_code = main_bot_process.returncode
                logger.warning(f"Основной бот неожиданно завершился с кодом {exit_code}, перезапускаем...")
                # Перезапускаем
                main_bot_process = subprocess.Popen(
                    [python_executable, 'run_bot.py'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True
                )
                logger.info(f"Основной бот перезапущен, новый PID: {main_bot_process.pid}")
                
                # Обновляем поток для логов
                main_bot_thread = threading.Thread(
                    target=stream_output,
                    args=(main_bot_process.stdout, "[MAIN BOT]"),
                    daemon=True
                )
                main_bot_thread.start()
            
            # Проверяем блогер-бот
            if blogger_watcher_process.poll() is not None:
                exit_code = blogger_watcher_process.returncode
                logger.warning(f"Система мониторинга блогер-бота неожиданно завершилась с кодом {exit_code}, перезапускаем...")
                # Перезапускаем
                blogger_watcher_process = subprocess.Popen(
                    [python_executable, 'run_watcher.py'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    universal_newlines=True
                )
                logger.info(f"Система мониторинга блогер-бота перезапущена, новый PID: {blogger_watcher_process.pid}")
                
                # Обновляем поток для логов
                blogger_thread = threading.Thread(
                    target=stream_output,
                    args=(blogger_watcher_process.stdout, "[BLOGGER BOT]"),
                    daemon=True
                )
                blogger_thread.start()
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал завершения работы системы управления ботами")
        try:
            # Останавливаем основной бот
            if main_bot_process and main_bot_process.poll() is None:
                logger.info(f"Остановка основного бота (PID: {main_bot_process.pid})...")
                main_bot_process.send_signal(signal.SIGTERM)
                time.sleep(2)
                if main_bot_process.poll() is None:
                    logger.warning("Основной бот не ответил на SIGTERM, принудительно завершаем...")
                    main_bot_process.kill()
            
            # Останавливаем блогер-бот
            if blogger_watcher_process and blogger_watcher_process.poll() is None:
                logger.info(f"Остановка системы мониторинга блогер-бота (PID: {blogger_watcher_process.pid})...")
                blogger_watcher_process.send_signal(signal.SIGTERM)
                time.sleep(2)
                if blogger_watcher_process.poll() is None:
                    logger.warning("Система мониторинга блогер-бота не ответила на SIGTERM, принудительно завершаем...")
                    blogger_watcher_process.kill()
        except Exception as e:
            logger.error(f"Ошибка при остановке процессов: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка в системе управления ботами: {e}")

if __name__ == "__main__":
    run_bots_manager() 