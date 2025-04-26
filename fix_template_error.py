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
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def fix_template_variable(file_path):
    """Исправляет переменную user.name на blogger_name в шаблоне"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Ищем все вхождения user.name и заменяем их на blogger_name
        pattern = r'user\.name'
        if re.search(pattern, content):
            fixed_content = re.sub(pattern, 'blogger_name', content)
            
            # Сохраняем изменения
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(fixed_content)
            
            logger.info(f"✅ Исправлена переменная user.name в файле {file_path}")
            return True
        else:
            logger.info(f"✓ Файл {file_path} не требует исправления")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке файла {file_path}: {str(e)}")
        return False

def fix_dashboard_template(file_path):
    """Проверяет и исправляет конкретные проблемы в шаблоне dashboard.html"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Проверяем, что переменная blogger_name используется правильно
        # Возможная проблема: многострочное выражение для вывода переменной
        pattern = r'{{\s*[\r\n\s]*blogger_name\s*[\r\n\s]*}}'
        if re.search(pattern, content):
            fixed_content = re.sub(pattern, '{{ blogger_name }}', content)
            
            # Сохраняем изменения
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(fixed_content)
            
            logger.info(f"✅ Исправлен многострочный вывод переменной blogger_name в файле {file_path}")
            return True
        else:
            logger.info(f"✓ Файл {file_path} не требует исправления многострочных выражений")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка при обработке файла {file_path}: {str(e)}")
        return False

def main():
    """Основная функция для сканирования и исправления шаблонов"""
    try:
        # Определяем корневую директорию проекта
        root_dir = os.path.abspath(os.path.dirname(__file__))
        templates_dir = os.path.join(root_dir, 'willway_blogers', 'templates')
        
        if not os.path.exists(templates_dir):
            logger.error(f"❌ Директория с шаблонами не найдена: {templates_dir}")
            return False
        
        logger.info(f"🔍 Сканирование шаблонов в директории: {templates_dir}")
        
        # Список всех HTML файлов в директории шаблонов
        html_files = list(Path(templates_dir).glob('*.html'))
        logger.info(f"📁 Найдено {len(html_files)} HTML файлов")
        
        fixed_count = 0
        
        # Исправляем переменные во всех шаблонах
        for file_path in html_files:
            if fix_template_variable(file_path):
                fixed_count += 1
        
        # Дополнительная проверка dashboard.html на многострочные выражения
        dashboard_path = os.path.join(templates_dir, 'dashboard.html')
        if os.path.exists(dashboard_path):
            if fix_dashboard_template(dashboard_path):
                logger.info(f"🔧 Дополнительные исправления в dashboard.html выполнены")
        
        if fixed_count > 0:
            logger.info(f"✅ Исправлено {fixed_count} файлов с ошибками")
        else:
            logger.info(f"✓ Ошибок в шаблонах не обнаружено")
        
        return True
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 