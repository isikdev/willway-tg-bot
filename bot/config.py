#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Модуль для работы с конфигурацией бота
"""

import os
import json
import logging

# Настройка логирования
logger = logging.getLogger(__name__)

def get_bot_config():
    """Получает конфигурацию бота из файла"""
    logger.info("Попытка чтения конфигурации бота")
    # Путь к файлу конфигурации (относительно корневой директории проекта)
    BOT_CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'bot_config.json')
    
    logger.info(f"Путь к файлу конфигурации: {BOT_CONFIG_FILE}")
    logger.info(f"Файл существует: {os.path.exists(BOT_CONFIG_FILE)}")
    
    config = {
        "trainer_username": "telegram",
        "manager_username": "telegram",
        "cancel_subscription_url": "https://willway.pro/cancelmembers"
    }
    
    try:
        with open(BOT_CONFIG_FILE, 'r', encoding='utf-8') as f:
            loaded_config = json.load(f)
            config.update(loaded_config)
            logger.info(f"Конфигурация загружена: {config.keys()}")
            
            # Проверка и обработка путей изображений
            if 'description_pic_url' in config and config['description_pic_url']:
                path = config['description_pic_url']
                logger.info(f"Найден путь изображения описания: {path}")
                
                # Преобразуем относительный путь в абсолютный
                if path.startswith('/'):
                    # Если путь начинается с /, убираем его
                    path = path[1:]
                
                # Преобразуем в абсолютный путь
                abs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
                logger.info(f"Абсолютный путь изображения описания: {abs_path}")
                
                # Проверяем существование файла
                if os.path.exists(abs_path):
                    logger.info("Файл изображения описания существует")
                    config['description_pic_absolute_path'] = abs_path
                else:
                    logger.warning(f"Файл изображения описания не существует: {abs_path}")
            
            if 'botpic_url' in config and config['botpic_url']:
                path = config['botpic_url']
                logger.info(f"Найден путь изображения бота: {path}")
                
                # Преобразуем относительный путь в абсолютный
                if path.startswith('/'):
                    # Если путь начинается с /, убираем его
                    path = path[1:]
                
                # Преобразуем в абсолютный путь
                abs_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), path)
                logger.info(f"Абсолютный путь изображения бота: {abs_path}")
                
                # Проверяем существование файла
                if os.path.exists(abs_path):
                    logger.info("Файл изображения бота существует")
                    config['botpic_absolute_path'] = abs_path
                else:
                    logger.warning(f"Файл изображения бота не существует: {abs_path}")
                
    except Exception as e:
        logger.error(f"Ошибка при чтении конфигурации бота: {e}")
    
    return config 