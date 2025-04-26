#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
API патч для интеграции с ботом и отслеживания реферальных переходов
"""

import os
import logging
import requests
from dotenv import load_dotenv
import re
from functools import wraps

# Настройка логирования
logger = logging.getLogger(__name__)

# Загружаем переменные окружения
load_dotenv()

# Конфигурация бота
BOT_USERNAME = os.getenv("BOT_USERNAME", "willway_super_bot")
API_URL = os.getenv("API_URL", "http://45.141.78.243:5001/api")
API_KEY = os.getenv("API_KEY", "")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "5"))

def register_referral_link(blogger_id, access_key, ref_code=None):
    """Регистрирует реферальную ссылку в системе бота"""
    if not ref_code:
        ref_code = f"ref_{access_key[-8:]}" if access_key else f"ref_test{blogger_id}"
    
    try:
        response = requests.post(
            f"{API_URL}/bot/register-referral",
            json={
                "blogger_id": blogger_id,
                "key": access_key,
                "ref_code": ref_code,
                "bot_username": BOT_USERNAME
            },
            timeout=API_TIMEOUT
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Реферальная ссылка зарегистрирована: {result}")
            return True, result
        else:
            logger.error(f"Ошибка при регистрации реферальной ссылки: {response.status_code}")
            return False, {"error": f"Ошибка сервера: {response.status_code}"}
    except Exception as e:
        logger.error(f"Исключение при регистрации реферальной ссылки: {str(e)}")
        return False, {"error": str(e)}

def track_referral_click(ref_code, user_id=None, username=None, ip=None):
    """Отслеживает клик по реферальной ссылке"""
    try:
        data = {
            "ref_code": ref_code,
            "api_key": API_KEY
        }
        
        if user_id:
            data["user_id"] = user_id
        if username:
            data["username"] = username
        if ip:
            data["ip"] = ip
            
        response = requests.post(
            f"{API_URL}/bot/track-click",
            json=data,
            timeout=API_TIMEOUT
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Клик по реферальной ссылке отслежен: {result}")
            return True, result
        else:
            logger.error(f"Ошибка при отслеживании клика: {response.status_code}")
            return False, {"error": f"Ошибка сервера: {response.status_code}"}
    except Exception as e:
        logger.error(f"Исключение при отслеживании клика: {str(e)}")
        return False, {"error": str(e)}

def track_conversion(ref_code, user_id, amount, purchase_id=None):
    """Отслеживает конверсию (покупка после перехода по реферальной ссылке)"""
    try:
        data = {
            "ref_code": ref_code,
            "user_id": user_id,
            "amount": amount,
            "api_key": API_KEY
        }
        
        if purchase_id:
            data["purchase_id"] = purchase_id
            
        response = requests.post(
            f"{API_URL}/bot/track-conversion",
            json=data,
            timeout=API_TIMEOUT
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Конверсия отслежена: {result}")
            return True, result
        else:
            logger.error(f"Ошибка при отслеживании конверсии: {response.status_code}")
            return False, {"error": f"Ошибка сервера: {response.status_code}"}
    except Exception as e:
        logger.error(f"Исключение при отслеживании конверсии: {str(e)}")
        return False, {"error": str(e)}

def get_blogger_by_ref_code(ref_code):
    """Получает информацию о блогере по реферальному коду"""
    try:
        response = requests.get(
            f"{API_URL}/bot/ref-info",
            params={
                "ref_code": ref_code,
                "api_key": API_KEY
            },
            timeout=API_TIMEOUT
        )
        
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Получена информация о блогере по реф-коду: {result}")
            return True, result
        else:
            logger.error(f"Ошибка при получении информации о блогере: {response.status_code}")
            return False, {"error": f"Ошибка сервера: {response.status_code}"}
    except Exception as e:
        logger.error(f"Исключение при получении информации о блогере: {str(e)}")
        return False, {"error": str(e)}

def monkey_patch_functions(module_object):
    """Заменяет функции в указанном модуле на улучшенные версии"""
    original_get_referral_link = module_object.get_referral_link
    
    @wraps(original_get_referral_link)
    def patched_get_referral_link(blogger_id, access_key):
        """Улучшенная версия функции получения реферальной ссылки"""
        # Получаем ссылку обычным способом
        result = original_get_referral_link(blogger_id, access_key)
        
        # Если ссылка получена успешно, регистрируем её в боте
        if result.get("success"):
            # Извлекаем ref_code из ссылки
            ref_link = result.get("referral_link", "")
            match = re.search(r'start=([^&]+)', ref_link)
            
            if match:
                ref_code = match.group(1)
                # Регистрируем ссылку
                success, bot_result = register_referral_link(blogger_id, access_key, ref_code)
                
                if success:
                    logger.info(f"Реферальная ссылка успешно зарегистрирована в боте")
                    # Обновляем данные в результате
                    result["bot_registered"] = True
                    if "message" in bot_result:
                        result["bot_message"] = bot_result["message"]
                else:
                    logger.warning(f"Не удалось зарегистрировать ссылку в боте: {bot_result.get('error')}")
                    result["bot_registered"] = False
                    result["bot_error"] = bot_result.get("error", "Неизвестная ошибка")
        
        return result
    
    # Заменяем функцию на улучшенную версию
    module_object.get_referral_link = patched_get_referral_link
    
    # Заменяем функцию исправления реферальной ссылки
    original_fix_link = module_object.fix_referral_link
    
    @wraps(original_fix_link)
    def patched_fix_referral_link(link):
        """Улучшенная версия функции исправления реферальной ссылки"""
        if not link:
            return link
        
        # Извлекаем ref_code из ссылки
        match = re.search(r'start=([^&]+)', link)
        if match:
            ref_code = match.group(1)
            return f"https://t.me/{BOT_USERNAME}?start={ref_code}"
        
        return link
    
    # Заменяем функцию на улучшенную версию
    module_object.fix_referral_link = patched_fix_referral_link
    
    logger.info(f"✅ Функции API успешно заменены на улучшенные версии")
    return True

def patch_api_functions():
    """Применяет патчи для всех необходимых модулей"""
    try:
        # Импортируем api_bridge для патчинга
        import api_bridge
        monkey_patch_functions(api_bridge)
        
        logger.info("✅ API патч успешно применен")
        return True
    except ImportError as e:
        logger.error(f"❌ Не удалось импортировать модуль: {str(e)}")
        return False
    except Exception as e:
        logger.error(f"❌ Ошибка при применении патча: {str(e)}")
        return False

# Если файл запущен напрямую, применяем патч
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    patch_api_functions() 