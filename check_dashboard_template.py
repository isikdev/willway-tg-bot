#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import sys
import logging

# Настройка логирования с выводом в консоль
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def check_dashboard_template():
    """Проверяет dashboard.html на наличие проблем с переменными"""
    try:
        # Путь к файлу dashboard.html
        dashboard_path = os.path.join(os.getcwd(), 'willway_blogers', 'templates', 'dashboard.html')
        
        if not os.path.exists(dashboard_path):
            logger.error(f"❌ Файл не найден: {dashboard_path}")
            return False
        
        logger.info(f"🔍 Проверка файла: {dashboard_path}")
        
        with open(dashboard_path, 'r', encoding='utf-8') as file:
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
                    start_pos = max(0, match.start() - 50)
                    end_pos = min(len(content), match.end() + 50)
                    context = content[start_pos:end_pos]
                    logger.warning(f"Контекст: ...{context}...")
        
        # Проверяем, что blogger_name используется правильно
        blogger_name_patterns = [
            r'blogger_name',
            r'{{\s*blogger_name\s*}}',
            r'{%\s*if\s+blogger_name\s*%}'
        ]
        
        for pattern in blogger_name_patterns:
            matches = re.findall(pattern, content)
            if matches:
                logger.info(f"✓ Найдено {len(matches)} правильных упоминаний blogger_name для паттерна {pattern}")
        
        if not found:
            logger.info(f"✓ Файл dashboard.html не содержит проблемных упоминаний user.name")
            return True
        else:
            logger.error(f"❌ Файл dashboard.html содержит проблемные упоминания user.name")
            return False
    except Exception as e:
        logger.error(f"❌ Ошибка при проверке файла: {str(e)}", exc_info=True)
        return False

if __name__ == "__main__":
    success = check_dashboard_template()
    sys.exit(0 if success else 1) 