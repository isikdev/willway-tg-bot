#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Скрипт для мониторинга изменений в bot_config.json и автоматического перезапуска бота
"""

import os
import time
import json
import hashlib
import logging
import subprocess
import signal
import sys

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

class ConfigWatcher:
    """Класс для мониторинга изменений конфигурационного файла и управления ботом"""
    
    def __init__(self, config_path, bot_script_path):
        """
        Инициализация мониторинга
        
        Args:
            config_path: Путь к файлу конфигурации
            bot_script_path: Путь к скрипту запуска бота
        """
        self.config_path = config_path
        self.bot_script_path = bot_script_path
        self.last_hash = self.get_file_hash()
        self.bot_process = None
        
    def get_file_hash(self):
        """Вычисляет хеш-сумму файла конфигурации"""
        try:
            with open(self.config_path, 'rb') as f:
                content = f.read()
                return hashlib.md5(content).hexdigest()
        except Exception as e:
            logger.error(f"Ошибка при вычислении хеш-суммы файла {self.config_path}: {e}")
            return None
    
    def check_config_changed(self):
        """Проверяет, изменился ли файл конфигурации"""
        current_hash = self.get_file_hash()
        if current_hash is None:
            return False
        
        if self.last_hash != current_hash:
            logger.info(f"Обнаружены изменения в конфигурационном файле {self.config_path}")
            self.last_hash = current_hash
            return True
        
        return False
    
    def validate_json(self):
        """Проверяет валидность JSON файла конфигурации"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                json.load(f)
            return True
        except json.JSONDecodeError as e:
            logger.error(f"Некорректный JSON в файле {self.config_path}: {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка при чтении файла {self.config_path}: {e}")
            return False
    
    def start_bot(self):
        """Запускает процесс бота"""
        try:
            # Проверяем валидность JSON перед запуском
            if not self.validate_json():
                logger.error("Бот не будет запущен из-за ошибок в конфигурационном файле")
                return False
            
            # Запускаем бота в новом процессе
            logger.info(f"Запуск бота: {self.bot_script_path}")
            
            # Определяем интерпретатор Python для запуска
            python_executable = sys.executable
            if not python_executable:
                python_executable = 'python'  # Или python3, в зависимости от системы
            
            # Запускаем процесс
            self.bot_process = subprocess.Popen(
                [python_executable, self.bot_script_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True
            )
            
            logger.info(f"Бот запущен, PID: {self.bot_process.pid}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при запуске бота: {e}")
            return False
    
    def stop_bot(self):
        """Останавливает процесс бота"""
        if self.bot_process and self.bot_process.poll() is None:
            try:
                logger.info(f"Остановка бота (PID: {self.bot_process.pid})...")
                
                # Сначала пытаемся завершить процесс корректно через SIGTERM
                self.bot_process.send_signal(signal.SIGTERM)
                
                # Ждем завершения процесса с тайм-аутом
                timeout = 5  # секунд
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if self.bot_process.poll() is not None:
                        logger.info("Бот успешно остановлен")
                        return True
                    time.sleep(0.1)
                
                # Если процесс не завершился, принудительно завершаем
                logger.warning(f"Бот не ответил на SIGTERM, принудительно завершаем процесс")
                self.bot_process.kill()
                return True
            except Exception as e:
                logger.error(f"Ошибка при остановке бота: {e}")
                return False
        else:
            logger.info("Бот уже остановлен или не был запущен")
            return True
    
    def restart_bot(self):
        """Перезапускает бота"""
        logger.info("Перезапуск бота...")
        self.stop_bot()
        # Небольшая пауза для корректного освобождения ресурсов
        time.sleep(2)
        return self.start_bot()
    
    def run(self, check_interval=10):
        """
        Запускает цикл мониторинга
        
        Args:
            check_interval: Интервал проверки изменений в секундах
        """
        logger.info(f"Запуск мониторинга конфигурационного файла {self.config_path}")
        
        # Запускаем бота при старте мониторинга
        self.start_bot()
        
        try:
            while True:
                time.sleep(check_interval)
                
                # Проверяем, не завершился ли бот неожиданно
                if self.bot_process and self.bot_process.poll() is not None:
                    exit_code = self.bot_process.poll()
                    logger.warning(f"Бот неожиданно завершился с кодом {exit_code}, перезапускаем...")
                    self.start_bot()
                    continue
                
                # Проверяем изменения в конфигурации
                if self.check_config_changed():
                    logger.info("Конфигурация изменилась, перезапускаем бота...")
                    self.restart_bot()
        
        except KeyboardInterrupt:
            logger.info("Получен сигнал завершения работы")
            self.stop_bot()
        
        except Exception as e:
            logger.error(f"Ошибка в цикле мониторинга: {e}")
            self.stop_bot()
            raise
        
        finally:
            logger.info("Мониторинг завершен")

def main():
    """Основная функция для запуска мониторинга"""
    # Определяем пути к файлам
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, 'bot_config.json')
    bot_script_path = os.path.join(base_dir, 'run_bot.py')
    
    # Проверяем существование файлов
    if not os.path.exists(config_path):
        logger.error(f"Файл конфигурации не найден: {config_path}")
        return
    
    if not os.path.exists(bot_script_path):
        logger.error(f"Скрипт запуска бота не найден: {bot_script_path}")
        return
    
    # Запускаем мониторинг
    watcher = ConfigWatcher(config_path, bot_script_path)
    watcher.run()

if __name__ == "__main__":
    main() 