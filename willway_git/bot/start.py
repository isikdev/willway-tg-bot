#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import logging
import subprocess

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def restart_bot():
    """Перезапускает бота через systemd"""
    try:
        logger.info("Попытка перезапуска бота через systemd...")
        result = subprocess.run(["systemctl", "restart", "willway-bot"], 
                               capture_output=True, text=True, check=True)
        logger.info(f"Результат перезапуска: {result.stdout}")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Ошибка при перезапуске бота: {e.stderr}")
        return False

def main():
    """Основная функция запуска скрипта"""
    logger.info("Запуск скрипта перезапуска бота...")
    
    if restart_bot():
        logger.info("Бот успешно перезапущен")
        print("Бот успешно перезапущен! Проверьте логи для подтверждения.")
    else:
        logger.error("Не удалось перезапустить бота")
        print("Не удалось перезапустить бота. Проверьте логи для деталей.")

if __name__ == "__main__":
    main() 