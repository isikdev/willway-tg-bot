#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для запуска бота для блогеров
Запуск осуществляется отдельно от основного бота для оптимизации производительности
"""

import os
import sys
import logging
import signal
import time
from env_var import setup_env
from dotenv import load_dotenv

# Устанавливаем переменные окружения
setup_env()

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('blogger_bot_standalone.log')
    ]
)

logger = logging.getLogger(__name__)

# Загрузка переменных окружения
load_dotenv()

def run_blogger_bot():
    """Запуск бота для блогеров в отдельном процессе"""
    try:
        logger.info("Запуск бота для блогеров WILLWAY")
        
        # Определяем интерпретатор Python
        python_executable = sys.executable
        if not python_executable:
            python_executable = 'python'  # Или python3, в зависимости от системы
        
        # Запускаем бот для блогеров
        import subprocess
        blogger_bot_process = subprocess.Popen(
            [python_executable, 'run_blogger_bot.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        logger.info(f"Бот для блогеров запущен, PID: {blogger_bot_process.pid}")
        
        # Обрабатываем вывод от бота
        for line in iter(blogger_bot_process.stdout.readline, ''):
            if line:
                print(f"[BLOGGER BOT] | {line.strip()}")
        
        # Ожидаем завершение процесса
        blogger_bot_process.wait()
        exit_code = blogger_bot_process.returncode
        logger.info(f"Бот для блогеров завершил работу с кодом: {exit_code}")
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал завершения работы бота для блогеров")
        try:
            if blogger_bot_process and blogger_bot_process.poll() is None:
                blogger_bot_process.send_signal(signal.SIGTERM)
                time.sleep(1)
                if blogger_bot_process.poll() is None:
                    blogger_bot_process.kill()
        except Exception as e:
            logger.error(f"Ошибка при остановке процесса бота для блогеров: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка при запуске бота для блогеров: {e}")

if __name__ == "__main__":
    run_blogger_bot() 