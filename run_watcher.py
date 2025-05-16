#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для запуска системы мониторинга конфигурации блогер-бота
Основной бот теперь самостоятельно отслеживает изменения в своей конфигурации
"""

import os
import sys
import logging
import signal
import time
import threading

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('watcher.log')
    ]
)

logger = logging.getLogger(__name__)

def run_watcher():
    """Запускает систему мониторинга конфигурации блогер-бота"""
    try:
        logger.info("Запуск системы мониторинга конфигурации блогер-бота WILLWAY")
        
        # Определяем интерпретатор Python
        python_executable = sys.executable
        if not python_executable:
            python_executable = 'python'  # Или python3, в зависимости от системы
        
        # Запускаем процесс мониторинга только для блогер-бота
        import subprocess
        watcher_process = subprocess.Popen(
            [python_executable, 'bot_config_watcher.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        logger.info(f"Система мониторинга блогер-бота запущена, PID: {watcher_process.pid}")
        
        # Обрабатываем вывод от watcher
        for line in iter(watcher_process.stdout.readline, ''):
            if line:
                print(f"[BLOGGER-BOT WATCHER] | {line.strip()}")
        
        # Ожидаем завершение процесса
        watcher_process.wait()
        exit_code = watcher_process.returncode
        logger.info(f"Система мониторинга блогер-бота завершила работу с кодом: {exit_code}")
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал завершения работы системы мониторинга блогер-бота")
        try:
            if watcher_process and watcher_process.poll() is None:
                watcher_process.send_signal(signal.SIGTERM)
                time.sleep(1)
                if watcher_process.poll() is None:
                    watcher_process.kill()
        except Exception as e:
            logger.error(f"Ошибка при остановке процесса мониторинга блогер-бота: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка при запуске системы мониторинга блогер-бота: {e}")

if __name__ == "__main__":
    run_watcher() 