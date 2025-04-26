#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import sys
import logging
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def check_and_fix_template(file_path):
    """Проверяет и исправляет шаблон, заменяя user.name на blogger_name"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Ищем все упоминания user.name в шаблоне
        patterns = [
            r'user\.name',  # Прямое упоминание в коде Python или шаблоне
            r'{{\s*user\.name\s*}}',  # В Jinja выражениях
            r'{%\s*if\s+user\.name\s*%}',  # В Jinja условиях
            r'{%\s*for.*?user\.name.*?%}'  # В Jinja циклах
        ]
        
        fixed = False
        fixed_content = content
        
        for pattern in patterns:
            if re.search(pattern, fixed_content):
                # Заменяем user.name на blogger_name в соответствующем контексте
                if pattern == r'user\.name':
                    fixed_content = re.sub(pattern, 'blogger_name', fixed_content)
                elif pattern == r'{{\s*user\.name\s*}}':
                    fixed_content = re.sub(pattern, '{{ blogger_name }}', fixed_content)
                elif pattern == r'{%\s*if\s+user\.name\s*%}':
                    fixed_content = re.sub(pattern, '{% if blogger_name %}', fixed_content)
                else:
                    # Для for циклов делаем простую замену, но это может потребовать ручной правки
                    fixed_content = re.sub(r'user\.name', 'blogger_name', fixed_content)
                
                fixed = True
                logger.info(f"Найдено и исправлено упоминание user.name в {file_path} для паттерна {pattern}")
        
        if fixed:
            # Сохраняем исправленный контент
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(fixed_content)
            logger.info(f"✅ Исправлен шаблон {file_path}")
            return True
        else:
            logger.info(f"✓ Шаблон {file_path} не требует исправлений")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке файла {file_path}: {str(e)}")
        return False

def main():
    """Основная функция для сканирования и исправления шаблонов"""
    try:
        # Определяем директорию шаблонов
        templates_dir = os.path.join(os.getcwd(), 'willway_blogers', 'templates')
        
        if not os.path.exists(templates_dir):
            logger.error(f"❌ Директория с шаблонами не найдена: {templates_dir}")
            return False
        
        logger.info(f"🔍 Сканирование шаблонов в директории: {templates_dir}")
        
        # Список всех HTML файлов в директории шаблонов
        html_files = list(Path(templates_dir).glob('*.html'))
        logger.info(f"📁 Найдено {len(html_files)} HTML файлов")
        
        fixed_count = 0
        
        # Проверяем и исправляем каждый шаблон
        for file_path in html_files:
            if check_and_fix_template(file_path):
                fixed_count += 1
        
        if fixed_count > 0:
            logger.info(f"✅ Исправлено {fixed_count} файлов")
        else:
            logger.info(f"✓ Все шаблоны в порядке, исправления не требуются")
        
        return True
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 