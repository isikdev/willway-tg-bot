#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для запуска системы мониторинга и управления всеми ботами
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

def run_bots_watcher():
    """Запускает систему мониторинга и управления ботами"""
    try:
        logger.info("Запуск системы мониторинга и управления ботами WILLWAY")
        
        # Определяем интерпретатор Python
        python_executable = sys.executable
        if not python_executable:
            python_executable = 'python'  # Или python3, в зависимости от системы
        
        # Запускаем процесс мониторинга
        watcher_process = subprocess.Popen(
            [python_executable, 'bot_config_watcher.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True
        )
        
        logger.info(f"Система мониторинга запущена, PID: {watcher_process.pid}")
        
        # Создаем поток для вывода логов системы мониторинга
        watcher_thread = threading.Thread(
            target=stream_output,
            args=(watcher_process.stdout, "[WATCHER]"),
            daemon=True
        )
        watcher_thread.start()
        
        # Прямой доступ к логам основного бота
        bot_log_path = 'bot.log'
        if os.path.exists(bot_log_path):
            # Начальное чтение лога
            with open(bot_log_path, 'r') as f:
                # Переходим в конец файла
                f.seek(0, 2)
                bot_log_position = f.tell()
        else:
            bot_log_position = 0
        
        # Основной цикл для отслеживания логов
        while watcher_process.poll() is None:
            time.sleep(0.5)
            
            # Проверяем и выводим логи основного бота
            if os.path.exists(bot_log_path):
                with open(bot_log_path, 'r') as f:
                    f.seek(bot_log_position)
                    bot_log_content = f.read()
                    bot_log_position = f.tell()
                    
                    if bot_log_content:
                        for line in bot_log_content.splitlines():
                            if line:
                                print(f"[MAIN BOT] | {line}")
        
        # Ожидаем завершения процесса мониторинга
        watcher_process.wait()
        exit_code = watcher_process.returncode
        logger.info(f"Система мониторинга завершила работу с кодом: {exit_code}")
        
    except KeyboardInterrupt:
        logger.info("Получен сигнал завершения работы")
        try:
            if watcher_process and watcher_process.poll() is None:
                watcher_process.send_signal(signal.SIGTERM)
                time.sleep(1)
                if watcher_process.poll() is None:
                    watcher_process.kill()
        except Exception as e:
            logger.error(f"Ошибка при остановке процесса: {e}")
            
    except Exception as e:
        logger.error(f"Ошибка при запуске системы мониторинга: {e}")

if __name__ == "__main__":
    run_bots_watcher() 