#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import sys
import logging
from pathlib import Path

# Настройка логирования с выводом в консоль
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def check_template(file_path):
    """Проверяет шаблон на наличие проблем с переменными user.name"""
    try:
        logger.info(f"🔍 Проверка файла: {file_path}")
        
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()
        
        # Ищем все упоминания user.name в шаблоне
        patterns = [
            r'user\.name',  # Прямое упоминание в коде Python или шаблоне
            r'{{\s*user\.name\s*}}',  # В Jinja выражениях
            r'{%\s*if\s+user\.name\s*%}',  # В Jinja условиях
            r'{%\s*for.*?user\.name.*?%}'  # В Jinja циклах
        ]
        
        found = False
        
        for pattern in patterns:
            matches = re.findall(pattern, content)
            if matches:
                found = True
                logger.warning(f"⚠️ Найдено {len(matches)} упоминаний для паттерна {pattern}")
                
                # Выводим контекст каждого найденного упоминания
                for match in re.finditer(pattern, content):
                    start_pos = max(0, match.start() - 30)
                    end_pos = min(len(content), match.end() + 30)
                    context = content[start_pos:end_pos]
                    logger.warning(f"Контекст: ...{context}...")
        
        # Проверяем, что blogger_name используется в шаблоне
        blogger_name_pattern = r'blogger_name'
        blogger_name_matches = re.findall(blogger_name_pattern, content)
        if blogger_name_matches:
            logger.info(f"✓ Найдено {len(blogger_name_matches)} упоминаний blogger_name")
        
        if found:
            logger.error(f"❌ Файл {file_path.name} содержит проблемные упоминания user.name")
            return True  # Возвращаем True, если найдены проблемы
        else:
            logger.info(f"✓ Файл {file_path.name} не содержит проблемных упоминаний user.name")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке файла {file_path}: {str(e)}")
        return False

def main():
    """Проверяет все шаблоны в директории templates"""
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
        
        problem_files = []
        
        # Проверяем каждый шаблон
        for file_path in html_files:
            if check_template(file_path):
                problem_files.append(file_path.name)
        
        if problem_files:
            logger.error(f"❌ Найдены проблемы в {len(problem_files)} файлах: {', '.join(problem_files)}")
            return False
        else:
            logger.info(f"✓ Все шаблоны проверены, проблем не обнаружено")
            return True
    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 