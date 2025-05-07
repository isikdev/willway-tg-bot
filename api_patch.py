import logging
import os
import sqlite3
import sys
from database.models import Blogger, BloggerReferral, User, get_session
from datetime import datetime
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from typing import Optional, Dict, Any, Union

# Добавляем корневую директорию в путь для импорта
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

# Теперь можем импортировать config
from config import BLOGGERS_DB_PATH, DATABASE_PATH

logger = logging.getLogger(__name__)

def get_blogger_session():
    """
    Создает сессию для работы с базой данных блогеров.
    Пытается использовать специальную БД для блогеров, если она указана.
    """
    # Проверяем наличие отдельной БД для блогеров
    blogger_db_path = os.getenv("BLOGGER_DATABASE_URL")
    
    if blogger_db_path:
        try:
            engine = create_engine(blogger_db_path)
            Session = sessionmaker(bind=engine)
            return Session()
        except Exception as e:
            logger.error(f"[BLOGGER_DB] Ошибка при подключении к БД блогеров: {str(e)}")
    
    # Если отдельной БД нет или произошла ошибка, используем основную БД
    return get_session()

def track_referral_click(blogger_key: str, user_id: Union[int, str], username: Optional[str] = None):
    """
    Отслеживает клик по реферальной ссылке блогера.
    
    Args:
        blogger_key (str): Ключ или реферальный код блогера.
        user_id (int|str): ID пользователя, который кликнул по ссылке.
        username (str, optional): Имя пользователя, если доступно.
    
    Returns:
        tuple: (success, result)
            success (bool): Успешно ли обработан клик
            result (str): Сообщение о результате операции
    """
    logging.info(f"Отслеживание клика по реферальной ссылке: {blogger_key}, пользователь: {user_id}, username: {username}")
    
    try:
        # Удаляем префикс и пробелы, если они есть
        if blogger_key.startswith('blogger_'):
            blogger_key = blogger_key[8:]
        elif blogger_key.startswith('ref_'):
            blogger_key = blogger_key[4:]  # Убираем префикс "ref_"
        blogger_key = blogger_key.strip()
        
        logging.info(f"Очищенный ключ блогера: {blogger_key}")
        
        # Подготавливаем ключи для поиска
        key_variants = [f"blogger_{blogger_key}", f"ref_{blogger_key}", blogger_key]
        
        # Сначала ищем в основной базе данных
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Проверяем существование таблицы blogger_referral_codes
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='blogger_referral_codes'")
        if cursor.fetchone():
            # Таблица существует, ищем блогера
            placeholders = ', '.join(['?'] * len(key_variants))
            cursor.execute(f"SELECT blogger_id FROM blogger_referral_codes WHERE code IN ({placeholders})", key_variants)
            result = cursor.fetchone()
            
            if result:
                blogger_id = result[0]
                logging.info(f"Найден блогер в database.db с ID: {blogger_id}")
            else:
                blogger_id = None
                logging.info("Блогер не найден в database.db")
        else:
            blogger_id = None
            logging.info("Таблица blogger_referral_codes не существует в database.db")
        
        conn.close()
        
        # Если не нашли в основной базе, проверяем в базе блогеров
        if blogger_id is None and os.path.exists(BLOGGERS_DB_PATH):
            conn = sqlite3.connect(BLOGGERS_DB_PATH)
            cursor = conn.cursor()
            
            # Проверяем структуру таблицы bloggers
            cursor.execute("PRAGMA table_info(bloggers)")
            columns = [col[1] for col in cursor.fetchall()]
            has_referral_code = 'referral_code' in columns
            
            # Ищем по ключу, учитывая наличие колонки referral_code
            placeholders = ', '.join(['?'] * len(key_variants))
            if has_referral_code:
                query = f"SELECT id FROM bloggers WHERE access_key IN ({placeholders}) OR referral_code IN ({placeholders})"
                cursor.execute(query, key_variants + key_variants)
            else:
                query = f"SELECT id FROM bloggers WHERE access_key IN ({placeholders})"
                cursor.execute(query, key_variants)
            
            result = cursor.fetchone()
            
            if result:
                blogger_id = result[0]
                logging.info(f"Найден блогер в willway_bloggers.db с ID: {blogger_id}")
            else:
                logging.warning(f"Блогер не найден ни в одной из баз данных с ключом: {blogger_key}")
                conn.close()
                return False, "Блогер не найден"
                
            # Проверяем структуру таблицы blogger_referrals
            cursor.execute("PRAGMA table_info(blogger_referrals)")
            columns = [col[1] for col in cursor.fetchall()]
            logging.info(f"Колонки в таблице blogger_referrals: {columns}")
            
            # Определяем, какие колонки доступны
            has_source = 'source' in columns
            has_user_id = 'user_id' in columns
            has_created_at = 'created_at' in columns
            has_referral_date = 'referral_date' in columns
            
            # Формируем значение для source
            source_value = username if username else str(user_id)
            
            # Формируем запрос на вставку записи с учетом доступных колонок
            insert_columns = ["blogger_id"]
            insert_values = [blogger_id]
            
            if has_source:
                insert_columns.append("source")
                insert_values.append(source_value)
            
            if has_user_id:
                insert_columns.append("user_id")
                insert_values.append(str(user_id))
            
            # Добавляем дату, если есть соответствующая колонка
            current_time = datetime.now()
            if has_created_at:
                insert_columns.append("created_at")
                insert_values.append(current_time)
            elif has_referral_date:
                insert_columns.append("referral_date")
                insert_values.append(current_time)
            
            # Формируем и выполняем запрос
            columns_str = ", ".join(insert_columns)
            placeholders = ", ".join(["?"] * len(insert_values))
            
            query = f"INSERT INTO blogger_referrals ({columns_str}) VALUES ({placeholders})"
            logging.info(f"SQL запрос на вставку: {query}")
            logging.info(f"Значения для вставки: {insert_values}")
            
            cursor.execute(query, insert_values)
            conn.commit()
            conn.close()
            
            logging.info(f"Клик по реферальной ссылке блогера успешно отслежен. Блогер ID: {blogger_id}, Пользователь: {user_id}")
            return True, "Успешно зарегистрирован переход"
    except Exception as e:
        logging.error(f"Ошибка при отслеживании клика по реферальной ссылке: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return False, f"Ошибка при отслеживании клика: {str(e)}"

    return False, "Реферальный код не обработан"

def register_conversion(user_id: Union[int, str], amount: float, username: Optional[str] = None) -> bool:
    """
    Регистрирует конверсию (покупку) пользователя, пришедшего по реферальной ссылке блогера.
    Блогеру начисляется 20% от суммы покупки.
    
    Args:
        user_id (int|str): ID пользователя, совершившего покупку.
        amount (float): Сумма покупки.
        username (str, optional): Имя пользователя, если доступно.
        
    Returns:
        bool: True если конверсия успешно зарегистрирована, False в противном случае.
    """
    logging.info(f"Регистрация конверсии: пользователь {user_id}, сумма {amount}, username: {username}")
    
    try:
        # Вычисляем комиссию блогера (20% от суммы покупки)
        commission = round(amount * 0.2, 2)
        logging.info(f"Комиссия блогера: {commission} (20% от {amount})")
        
        # Преобразуем user_id в строку для поиска
        user_id_str = str(user_id)
        source_value = username if username else user_id_str
        
        # Ищем запись в базе willway_bloggers.db
        if os.path.exists(BLOGGERS_DB_PATH):
            conn = sqlite3.connect(BLOGGERS_DB_PATH)
            cursor = conn.cursor()
            
            # Проверяем структуру таблицы
            cursor.execute("PRAGMA table_info(blogger_referrals)")
            columns = [col[1] for col in cursor.fetchall()]
            logging.info(f"Колонки в таблице blogger_referrals: {columns}")
            
            # Определяем, какие колонки доступны
            has_source = 'source' in columns
            has_user_id = 'user_id' in columns
            has_converted = 'converted' in columns
            has_converted_at = 'converted_at' in columns
            has_commission = 'commission_amount' in columns
            
            # Формируем условие поиска в зависимости от доступных колонок
            search_conditions = []
            search_params = []
            
            if has_user_id:
                search_conditions.append("user_id = ?")
                search_params.append(user_id_str)
            
            if has_source:
                if username:
                    search_conditions.append("source = ?")
                    search_params.append(username)
                search_conditions.append("source = ?")
                search_params.append(user_id_str)
            
            if not search_conditions:
                logging.error("Не удалось найти подходящие колонки для поиска реферала")
                conn.close()
            return False
        
            # Формируем запрос для поиска
            search_query = " OR ".join(search_conditions)
            cursor.execute(f"SELECT id, blogger_id FROM blogger_referrals WHERE {search_query} ORDER BY id DESC LIMIT 1", 
                          search_params)
            
            result = cursor.fetchone()
            
            if result:
                referral_id, blogger_id = result
                logging.info(f"Найдена запись о реферале: ID {referral_id}, блогер ID {blogger_id}")
                
                # Обновляем запись о реферале
                update_fields = []
                update_values = []
                
                if has_converted:
                    update_fields.append("converted = ?")
                    update_values.append(1)
                
                if has_converted_at:
                    update_fields.append("converted_at = ?")
                    update_values.append(datetime.now())
                
                if has_commission:
                    update_fields.append("commission_amount = ?")
                    update_values.append(commission)
                
                if update_fields:
                    update_query = f"UPDATE blogger_referrals SET {', '.join(update_fields)} WHERE id = ?"
                    update_values.append(referral_id)
                    
                    logging.info(f"SQL запрос на обновление: {update_query}")
                    logging.info(f"Значения для обновления: {update_values}")
                    
                    cursor.execute(update_query, update_values)
                    conn.commit()
                    conn.close()
                    
                    logging.info(f"Конверсия успешно зарегистрирована. Блогер ID: {blogger_id}, комиссия: {commission}")
                    return True
                else:
                    logging.warning("Нет колонок для обновления при конверсии")
                    conn.close()
                    return False
            else:
                logging.warning(f"Запись о реферале не найдена для пользователя {user_id} / {username}")
                conn.close()
        
        # Если не нашли в willway_bloggers.db или её нет, проверяем в основной базе
        conn = sqlite3.connect(DATABASE_PATH)
        cursor = conn.cursor()
        
        # Проверяем существование таблицы user_referrals
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_referrals'")
        if cursor.fetchone():
            # Ищем реферальный код для пользователя
            cursor.execute("SELECT blogger_code FROM user_referrals WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", 
                          (user_id_str,))
            result = cursor.fetchone()
            
            if result:
                blogger_code = result[0]
                logging.info(f"Найден реферальный код блогера в database.db: {blogger_code}")
                
                # Ищем ID блогера по реферальному коду
                cursor.execute("SELECT blogger_id FROM blogger_referral_codes WHERE code = ?", (blogger_code,))
                blogger_result = cursor.fetchone()
                
                if blogger_result:
                    blogger_id = blogger_result[0]
                    
                    # Обновляем статистику блогера, добавляя конверсию
                    # Если у нас есть таблица для статистики блогеров
                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='blogger_statistics'")
                    if cursor.fetchone():
                        # Проверяем наличие записи для этого блогера
                        today = datetime.now().strftime("%Y-%m-%d")
                        cursor.execute("SELECT id FROM blogger_statistics WHERE blogger_id = ? AND date = ?", 
                                      (blogger_id, today))
                        stat_result = cursor.fetchone()
                        
                        if stat_result:
                            # Обновляем существующую запись
                            cursor.execute("UPDATE blogger_statistics SET conversions = conversions + 1, earnings = earnings + ? WHERE id = ?", 
                                          (commission, stat_result[0]))
                        else:
                            # Создаем новую запись
                            cursor.execute("INSERT INTO blogger_statistics (blogger_id, date, conversions, earnings) VALUES (?, ?, 1, ?)", 
                                          (blogger_id, today, commission))
                    
                    conn.commit()
                    
                    logging.info(f"Конверсия успешно зарегистрирована в database.db. Блогер ID: {blogger_id}, комиссия: {commission}")
                    conn.close()
                    return True
                else:
                    logging.warning(f"Блогер не найден по коду {blogger_code} в database.db")
            else:
                logging.warning(f"Реферальный код не найден для пользователя {user_id} в database.db")
        else:
            logging.warning("Таблица user_referrals не существует в database.db")
        
        conn.close()
        return False
    except Exception as e:
        logging.error(f"Ошибка при регистрации конверсии: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        return False 