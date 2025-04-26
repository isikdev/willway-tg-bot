#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
import argparse
import logging
from dotenv import load_dotenv
import shutil

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

def run_bloggers_app(host='0.0.0.0', port=5002, debug=False):
    """Запускает приложение для блогеров на указанном хосте и порту"""
    try:
        # Добавляем корневую директорию в путь поиска модулей
        root_dir = os.path.abspath(os.path.dirname(__file__))
        sys.path.insert(0, root_dir)
        
        # Копируем api_bridge.py в корневую директорию, если его там нет
        source_api_bridge = os.path.join(root_dir, 'willway_blogers', 'api_bridge.py')
        dest_api_bridge = os.path.join(root_dir, 'api_bridge.py')
        
        if os.path.exists(source_api_bridge) and not os.path.exists(dest_api_bridge):
            logger.info(f"Копирование api_bridge.py в корневую директорию")
            shutil.copy2(source_api_bridge, dest_api_bridge)
            logger.info(f"✅ Файл api_bridge.py скопирован")
        
        # Копируем api_patch.py в корневую директорию, если его там нет
        source_api_patch = os.path.join(root_dir, 'willway_blogers', 'api_patch.py')
        dest_api_patch = os.path.join(root_dir, 'api_patch.py')
        
        if os.path.exists(source_api_patch) and not os.path.exists(dest_api_patch):
            logger.info(f"Копирование api_patch.py в корневую директорию")
            shutil.copy2(source_api_patch, dest_api_patch)
            logger.info(f"✅ Файл api_patch.py скопирован")
        
        # Проверяем существование директории willway_blogers
        bloggers_dir = os.path.join(os.path.dirname(__file__), 'willway_blogers')
        if not os.path.exists(bloggers_dir):
            logger.error(f"❌ Директория {bloggers_dir} не найдена")
            logger.info("ℹ️ Запустите fix_database.py --blogers для создания необходимых файлов")
            return False
        
        # Проверяем наличие необходимых файлов
        app_file = os.path.join(bloggers_dir, 'app.py')
        if not os.path.exists(app_file):
            logger.error(f"❌ Файл {app_file} не найден")
            logger.info("ℹ️ Запустите fix_database.py --blogers для создания необходимых файлов")
            return False
        
        # Устанавливаем переменные окружения для реферальных ссылок
        os.environ['BOT_USERNAME'] = os.getenv('BOT_USERNAME', 'willway_super_bot')
        logger.info(f"ℹ️ Используется бот @{os.environ.get('BOT_USERNAME')} для реферальных ссылок")
        
        # Сначала запускаем исправление таблиц
        logger.info("===== Исправление таблиц перед запуском =====")
        from direct_fix_tables import main as fix_tables
        fix_tables()
        
        # Импортируем приложение блогеров
        from willway_blogers.app import app
        
        # Применяем патч для исправления реферальных ссылок
        try:
            from api_patch import patch_api_functions
            patch_api_functions()
            logger.info(f"✅ Применен патч для реферальных ссылок, используется бот @{os.environ.get('BOT_USERNAME')}")
        except Exception as e:
            logger.error(f"❌ Ошибка при применении патча: {str(e)}")
        
        # Запускаем сервер блогеров
        logger.info(f"✅ Запуск сервера блогеров на http://{host}:{port}")
        app.run(host=host, port=port, debug=debug)
        
        return True
    except ImportError as e:
        logger.error(f"❌ Ошибка импорта: {str(e)}")
        logger.info("ℹ️ Убедитесь, что все зависимости установлены: pip install -r requirements.txt")
        return False
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {str(e)}")
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Запуск сервера для блогеров')
    parser.add_argument('--host', default='0.0.0.0', help='Хост для запуска сервера (по умолчанию: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=5002, help='Порт для запуска сервера (по умолчанию: 5002)')
    parser.add_argument('--debug', action='store_true', help='Запуск в режиме отладки')
    parser.add_argument('--bot', default=None, help='Имя бота для реферальных ссылок (по умолчанию: willway_super_bot)')
    
    args = parser.parse_args()
    
    # Устанавливаем имя бота из аргументов командной строки, если оно предоставлено
    if args.bot:
        os.environ['BOT_USERNAME'] = args.bot
    
    success = run_bloggers_app(host=args.host, port=args.port, debug=args.debug)
    sys.exit(0 if success else 1) 