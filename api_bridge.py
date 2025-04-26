#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
API мост для прямого доступа к API админки
"""

import requests
import logging
import os
from dotenv import load_dotenv
import re
import random
import datetime

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logger = logging.getLogger(__name__)

# URL API для проверки доступа блогеров
API_URL = os.getenv("API_URL", "http://45.141.78.243:5001/api")
API_KEY = os.getenv("API_KEY", "")
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "5"))
BOT_USERNAME = os.getenv("BOT_USERNAME", "willway_super_bot")  # Имя бота для реферальных ссылок

def check_api_status():
    """Проверяет доступность API админки"""
    try:
        response = requests.get(
            f"{API_URL}/ping",
            timeout=API_TIMEOUT
        )
        return response.status_code == 200, response.json() if response.status_code == 200 else {"error": "API недоступен"}
    except Exception as e:
        logger.error(f"Ошибка при проверке статуса API: {str(e)}")
        return False, {"error": str(e)}

def verify_blogger_key(access_key):
    """Проверка ключа доступа блогера"""
    try:
        response = requests.post(
            f"{API_URL}/blogger/verify-key", 
            json={"key": access_key},
            timeout=API_TIMEOUT
        )
        
        if response.status_code == 200:
            return response.json()
        
        # Обработка ошибок
        error_message = "Неизвестная ошибка при проверке ключа"
        try:
            error_data = response.json()
            error_message = error_data.get("error", error_message)
        except:
            pass
        
        logger.error(f"Ошибка API ({response.status_code}): {error_message}")
        return {"success": False, "error": f"Ошибка API: {error_message}"}
    except requests.RequestException as e:
        logger.error(f"Ошибка соединения с API: {str(e)}")
        return {"success": False, "error": f"Ошибка соединения с сервером: {str(e)}"}

def get_blogger_stats(blogger_id, access_key):
    """Получение статистики блогера"""
    if not blogger_id or not access_key:
        logger.error("Отсутствуют ID блогера или ключ доступа")
        return {
            "success": False, 
            "error": "Отсутствуют ID блогера или ключ доступа"
        }
        
    try:
        # Проверяем доступность API
        api_status, _ = check_api_status()
        if not api_status:
            logger.warning("API недоступен, возвращаем тестовые данные")
            # Возвращаем тестовые данные, чтобы интерфейс мог функционировать
            mock_stats = generate_mock_stats(blogger_id, access_key)
            return mock_stats
            
        response = requests.get(
            f"{API_URL}/blogger/stats",
            params={
                "id": blogger_id,
                "key": access_key
            },
            timeout=API_TIMEOUT
        )
        
        if response.status_code == 200:
            try:
                result = response.json()
                # Исправляем реферальную ссылку, если она присутствует
                if result.get("success") and "referral_link" in result:
                    result["referral_link"] = fix_referral_link(result["referral_link"])
                return result
            except ValueError as e:
                logger.error(f"Ошибка декодирования JSON: {str(e)}")
                return {"success": False, "error": f"Ошибка формата данных: {str(e)}"}
        
        logger.error(f"Ошибка API при получении статистики: код {response.status_code}")
        try:
            error_data = response.json()
            error_message = error_data.get("error", f"Ошибка API: код {response.status_code}")
        except:
            error_message = f"Ошибка API: код {response.status_code}"
            
        return {"success": False, "error": error_message}
        
    except requests.ConnectionError as e:
        logger.error(f"Ошибка соединения с API: {str(e)}")
        # Возвращаем тестовые данные при ошибке соединения
        logger.warning("Соединение с API невозможно, возвращаем тестовые данные")
        mock_stats = generate_mock_stats(blogger_id, access_key)
        return mock_stats
    except requests.Timeout as e:
        logger.error(f"Таймаут соединения с API: {str(e)}")
        return {"success": False, "error": f"Таймаут соединения с сервером: {str(e)}"}
    except Exception as e:
        logger.error(f"Неизвестная ошибка при получении статистики: {str(e)}", exc_info=True)
        return {"success": False, "error": f"Ошибка соединения с сервером: {str(e)}"}

def generate_mock_stats(blogger_id, access_key):
    """Генерирует тестовые данные для статистики блогера"""
    # Генерируем реферальную ссылку
    ref_code = f"ref_{access_key[-8:]}" if access_key else f"ref_test{blogger_id}"
    referral_link = f"https://t.me/{BOT_USERNAME}?start={ref_code}"
    
    # Базовые статистические данные
    clicks = random.randint(10, 500)
    conversions = int(clicks * random.uniform(0.05, 0.2))
    earnings = conversions * random.randint(200, 1000)
    
    # Генерируем транзакции
    transactions = []
    for i in range(min(10, conversions)):
        date = (datetime.datetime.now() - datetime.timedelta(days=random.randint(1, 30))).strftime("%d.%m.%Y")
        transactions.append({
            "date": date,
            "referral_id": f"user_{random.randint(1000, 9999)}",
            "referral_name": f"User_{random.randint(100, 999)}",
            "action": "Регистрация и оплата",
            "amount": random.randint(200, 1000),
            "status": random.choices(["completed", "pending", "rejected"], weights=[0.8, 0.15, 0.05])[0]
        })
    
    # Сортируем транзакции по дате (новые сверху)
    transactions.sort(key=lambda x: datetime.datetime.strptime(x["date"], "%d.%m.%Y"), reverse=True)
    
    return {
        "success": True,
        "blogger_id": blogger_id,
        "referral_link": referral_link,
        "total_referrals": clicks,
        "total_conversions": conversions,
        "total_earnings": earnings,
        "monthly_earnings": int(earnings * 0.7),  # 70% от общего дохода
        "active_referrals": int(conversions * 0.8),  # 80% активных
        "conversion_rate": round((conversions / clicks) * 100 if clicks else 0, 1),
        "transactions": transactions,
        "clicks": clicks,
        "unique_visitors": int(clicks * 0.8),
        "registrations": conversions,
        "_mock": True  # Флаг, что это тестовые данные
    }

def get_blogger_referrals(blogger_id, access_key, offset=0, limit=10):
    """Получение списка рефералов блогера"""
    if not blogger_id or not access_key:
        logger.error("Отсутствуют ID блогера или ключ доступа")
        return {
            "success": False, 
            "error": "Отсутствуют ID блогера или ключ доступа"
        }
        
    try:
        # Проверяем доступность API
        api_status, _ = check_api_status()
        if not api_status:
            logger.warning("API недоступен, возвращаем тестовые данные для рефералов")
            return generate_mock_referrals(blogger_id, access_key, offset, limit)
            
        response = requests.get(
            f"{API_URL}/blogger/referrals",
            params={
                "id": blogger_id,
                "key": access_key,
                "offset": offset,
                "limit": limit
            },
            timeout=API_TIMEOUT
        )
        
        if response.status_code == 200:
            try:
                return response.json()
            except ValueError as e:
                logger.error(f"Ошибка декодирования JSON: {str(e)}")
                return {"success": False, "error": f"Ошибка формата данных: {str(e)}"}
        
        logger.error(f"Ошибка API при получении рефералов: код {response.status_code}")
        try:
            error_data = response.json()
            error_message = error_data.get("error", f"Ошибка API: код {response.status_code}")
        except:
            error_message = f"Ошибка API: код {response.status_code}"
            
        return {"success": False, "error": error_message}
        
    except requests.ConnectionError as e:
        logger.error(f"Ошибка соединения с API: {str(e)}")
        logger.warning("Соединение с API невозможно, возвращаем тестовые данные")
        return generate_mock_referrals(blogger_id, access_key, offset, limit)
    except requests.Timeout as e:
        logger.error(f"Таймаут соединения с API: {str(e)}")
        return {"success": False, "error": f"Таймаут соединения с сервером: {str(e)}"}
    except Exception as e:
        logger.error(f"Неизвестная ошибка при получении рефералов: {str(e)}", exc_info=True)
        return {"success": False, "error": f"Ошибка соединения с сервером: {str(e)}"}

def get_referral_link(blogger_id, access_key):
    """Получение реферальной ссылки блогера"""
    if not blogger_id or not access_key:
        logger.error("Отсутствуют ID блогера или ключ доступа")
        return {
            "success": False, 
            "error": "Отсутствуют ID блогера или ключ доступа"
        }
        
    try:
        # Проверяем доступность API
        api_status, _ = check_api_status()
        if not api_status:
            logger.warning("API недоступен, генерируем тестовую реферальную ссылку")
            return generate_mock_referral_link(blogger_id, access_key)
            
        response = requests.get(
            f"{API_URL}/blogger/referral-link",
            params={
                "id": blogger_id,
                "key": access_key
            },
            timeout=API_TIMEOUT
        )
        
        if response.status_code == 200:
            try:
                result = response.json()
                # Исправляем реферальную ссылку
                if result.get("success") and "referral_link" in result:
                    result["referral_link"] = fix_referral_link(result["referral_link"])
                return result
            except ValueError as e:
                logger.error(f"Ошибка декодирования JSON: {str(e)}")
                return {"success": False, "error": f"Ошибка формата данных: {str(e)}"}
        
        logger.error(f"Ошибка API при получении реферальной ссылки: код {response.status_code}")
        try:
            error_data = response.json()
            error_message = error_data.get("error", f"Ошибка API: код {response.status_code}")
        except:
            error_message = f"Ошибка API: код {response.status_code}"
            
        return {"success": False, "error": error_message}
        
    except requests.ConnectionError as e:
        logger.error(f"Ошибка соединения с API: {str(e)}")
        logger.warning("Соединение с API невозможно, генерируем тестовую ссылку")
        return generate_mock_referral_link(blogger_id, access_key)
    except requests.Timeout as e:
        logger.error(f"Таймаут соединения с API: {str(e)}")
        return {"success": False, "error": f"Таймаут соединения с сервером: {str(e)}"}
    except Exception as e:
        logger.error(f"Неизвестная ошибка при получении реферальной ссылки: {str(e)}", exc_info=True)
        return {"success": False, "error": f"Ошибка соединения с сервером: {str(e)}"}

def generate_mock_referrals(blogger_id, access_key, offset=0, limit=10):
    """Генерирует тестовый список рефералов"""
    # Генерируем базовый набор рефералов
    total_referrals = random.randint(50, 200)
    referrals = []
    
    # Проверяем валидность параметров пагинации
    offset = max(0, offset)
    limit = min(50, max(1, limit))
    
    # Определяем последние элементы для текущей страницы
    end_index = min(offset + limit, total_referrals)
    
    # Если запрос за пределами возможных рефералов, возвращаем пустой список
    if offset >= total_referrals:
        return {
            "success": True,
            "referrals": [],
            "total": total_referrals,
            "offset": offset,
            "limit": limit,
            "_mock": True
        }
    
    # Генерируем рефералов для текущей страницы
    for i in range(offset, end_index):
        date = (datetime.datetime.now() - datetime.timedelta(days=random.randint(1, 90))).strftime("%d.%m.%Y")
        converted = random.random() < 0.2  # 20% вероятность конверсии
        commission = random.randint(200, 1000) if converted else 0
        
        referrals.append({
            "id": f"user_{random.randint(1000, 9999)}",
            "source": random.choice(["Telegram", "WhatsApp", "VK", "Instagram", "Facebook", "Личная рекомендация"]),
            "created_at": date,
            "converted": converted,
            "commission_amount": commission,
            "status": "active" if random.random() < 0.9 else "inactive"
        })
    
    # Сортируем рефералов по дате (новые сверху)
    referrals.sort(key=lambda x: datetime.datetime.strptime(x["created_at"], "%d.%m.%Y"), reverse=True)
    
    return {
        "success": True,
        "referrals": referrals,
        "total": total_referrals,
        "offset": offset,
        "limit": limit,
        "_mock": True
    }

def generate_mock_referral_link(blogger_id, access_key):
    """Генерирует тестовую реферальную ссылку"""
    ref_code = f"ref_{access_key[-8:]}" if access_key else f"ref_test{blogger_id}"
    referral_link = f"https://t.me/{BOT_USERNAME}?start={ref_code}"
    
    clicks = random.randint(10, 500)  # random уже импортирован в generate_mock_stats
    unique_visitors = int(clicks * 0.8)
    conversions = int(clicks * random.uniform(0.05, 0.2))
    
    return {
        "success": True,
        "referral_link": referral_link,
        "clicks": clicks,
        "unique_visitors": unique_visitors,
        "conversions": conversions,
        "_mock": True
    }

def get_earnings(blogger_id, access_key):
    """Получение информации о заработке блогера"""
    if not blogger_id or not access_key:
        logger.error("Отсутствуют ID блогера или ключ доступа")
        return {
            "success": False, 
            "error": "Отсутствуют ID блогера или ключ доступа"
        }
        
    try:
        # Проверяем доступность API
        api_status, _ = check_api_status()
        if not api_status:
            logger.warning("API недоступен, генерируем тестовые данные о заработке")
            return generate_mock_earnings(blogger_id, access_key)
            
        response = requests.get(
            f"{API_URL}/blogger/earnings",
            params={
                "id": blogger_id,
                "key": access_key
            },
            timeout=API_TIMEOUT
        )
        
        if response.status_code == 200:
            try:
                return response.json()
            except ValueError as e:
                logger.error(f"Ошибка декодирования JSON: {str(e)}")
                return {"success": False, "error": f"Ошибка формата данных: {str(e)}"}
        
        logger.error(f"Ошибка API при получении данных о заработке: код {response.status_code}")
        try:
            error_data = response.json()
            error_message = error_data.get("error", f"Ошибка API: код {response.status_code}")
        except:
            error_message = f"Ошибка API: код {response.status_code}"
            
        return {"success": False, "error": error_message}
        
    except requests.ConnectionError as e:
        logger.error(f"Ошибка соединения с API: {str(e)}")
        logger.warning("Соединение с API невозможно, генерируем тестовые данные о заработке")
        return generate_mock_earnings(blogger_id, access_key)
    except requests.Timeout as e:
        logger.error(f"Таймаут соединения с API: {str(e)}")
        return {"success": False, "error": f"Таймаут соединения с сервером: {str(e)}"}
    except Exception as e:
        logger.error(f"Неизвестная ошибка при получении данных о заработке: {str(e)}", exc_info=True)
        return {"success": False, "error": f"Ошибка соединения с сервером: {str(e)}"}

def generate_mock_earnings(blogger_id, access_key):
    """Генерирует тестовые данные о заработке блогера"""
    total_earnings = random.randint(5000, 50000)
    
    # Генерируем месячные данные (за последние 6 месяцев)
    now = datetime.datetime.now()
    monthly_data = []
    
    for i in range(6):
        month_date = now - datetime.timedelta(days=30*i)
        month_str = month_date.strftime("%m.%Y")
        monthly_data.append({
            "month": month_str,
            "earnings": random.randint(int(total_earnings/10), int(total_earnings/3)),
            "referrals": random.randint(5, 50),
            "conversions": random.randint(1, 15)
        })
    
    # Генерируем данные о балансе
    balance = {
        "available": random.randint(1000, 5000),
        "pending": random.randint(500, 3000),
        "total": 0  # Будет вычислено
    }
    balance["total"] = balance["available"] + balance["pending"]
    
    # Генерируем историю выплат
    payments_history = []
    for i in range(random.randint(1, 5)):
        payment_date = now - datetime.timedelta(days=random.randint(30, 180))
        payments_history.append({
            "date": payment_date.strftime("%d.%m.%Y"),
            "amount": random.randint(1000, 10000),
            "method": random.choice(["Банковская карта", "WebMoney", "QIWI", "Яндекс.Деньги"]),
            "status": "completed"
        })
    
    return {
        "success": True,
        "total_earnings": total_earnings,
        "monthly_data": monthly_data,
        "balance": balance,
        "payments_history": payments_history,
        "_mock": True
    }

def fix_referral_link(link):
    """Исправляет реферальную ссылку, заменяя имя бота"""
    if not link:
        return link
    
    # Извлекаем ref_code из ссылки
    match = re.search(r'start=([^&]+)', link)
    if match:
        ref_code = match.group(1)
        return f"https://t.me/{BOT_USERNAME}?start={ref_code}"
    
    return link

# Тестовая функция
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        test_key = sys.argv[1]
        print(f"Тестирование ключа: {test_key}")
        result = verify_blogger_key(test_key)
        
        if result.get("success"):
            blogger_id = result["blogger_id"]
            print(f"Успешная аутентификация! ID блогера: {blogger_id}")
            
            # Получаем статистику
            stats = get_blogger_stats(blogger_id, test_key)
            if stats.get("success"):
                print(f"Всего переходов: {stats['total_referrals']}")
                print(f"Всего конверсий: {stats['total_conversions']}")
                print(f"Заработано: {stats['total_earnings']} ₽")
            else:
                print(f"Ошибка при получении статистики: {stats.get('error')}")
        else:
            print(f"Ошибка аутентификации: {result.get('error')}")
    else:
        # Просто проверяем статус
        status, info = check_api_status()
        if status:
            print("✅ API доступен")
        else:
            print(f"❌ API недоступен: {info}")
