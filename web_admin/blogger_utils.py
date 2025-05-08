import sqlite3
import os
from datetime import datetime, timedelta

def get_blogger_db_connection():
    """
    Создает подключение к базе данных блогеров
    """
    blogger_db_path = os.path.join(os.getcwd(), 'willway_bloggers.db')
    conn = sqlite3.connect(blogger_db_path)
    conn.row_factory = sqlite3.Row
    return conn

def check_blogger_table():
    """
    Проверяет наличие таблицы блогеров и создает ее при необходимости
    """
    conn = get_blogger_db_connection()
    cursor = conn.cursor()
    
    # Проверяем существование таблицы
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='bloggers'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bloggers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                telegram_id TEXT,
                email TEXT,
                access_key TEXT UNIQUE NOT NULL,
                registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_earned REAL DEFAULT 0,
                total_referrals INTEGER DEFAULT 0,
                total_conversions INTEGER DEFAULT 0,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        
    # Проверяем наличие таблицы реферралов
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='blogger_referrals'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blogger_referrals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                blogger_id INTEGER NOT NULL,
                user_id TEXT,
                source TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                converted BOOLEAN DEFAULT 0,
                converted_at TIMESTAMP,
                conversion_date TIMESTAMP,
                commission REAL DEFAULT 0,
                commission_amount REAL DEFAULT 0,
                status TEXT DEFAULT 'pending',
                FOREIGN KEY (blogger_id) REFERENCES bloggers (id)
            )
        ''')
        
    conn.commit()
    conn.close()

def get_blogger_by_key(access_key):
    """
    Получает данные блогера по ключу доступа
    """
    if not access_key:
        return None
        
    conn = get_blogger_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM bloggers WHERE access_key = ? AND is_active = 1", (access_key,))
    blogger = cursor.fetchone()
    
    conn.close()
    return blogger

def get_all_bloggers():
    """
    Получает список всех блогеров
    """
    conn = get_blogger_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM bloggers ORDER BY registration_date DESC")
    bloggers = cursor.fetchall()
    
    conn.close()
    return bloggers

def get_blogger_stats(blogger_id):
    """
    Получает статистику блогера: количество реферралов, конверсий и заработок
    """
    conn = get_blogger_db_connection()
    cursor = conn.cursor()
    
    # Проверяем структуру таблицы blogger_referrals
    cursor.execute("PRAGMA table_info(blogger_referrals)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Общее количество реферральных переходов
    cursor.execute("SELECT COUNT(*) FROM blogger_referrals WHERE blogger_id = ?", (blogger_id,))
    total_referrals = cursor.fetchone()[0] or 0
    
    # Общее количество конверсий
    if 'converted' in columns:
        cursor.execute("SELECT COUNT(*) FROM blogger_referrals WHERE blogger_id = ? AND converted = 1", (blogger_id,))
    else:
        # Если колонки converted нет, считаем что конверсий 0
        cursor.execute("SELECT 0")
    total_conversions = cursor.fetchone()[0] or 0
    
    # Общий заработок
    if 'commission_amount' in columns:
        cursor.execute("SELECT SUM(commission_amount) FROM blogger_referrals WHERE blogger_id = ?", (blogger_id,))
    else:
        cursor.execute("SELECT 0")
    total_earned = cursor.fetchone()[0] or 0
    
    conn.close()
    return {
        'total_referrals': total_referrals,
        'total_conversions': total_conversions,
        'total_earned': total_earned
    }

def update_blogger_stats(blogger_id):
    """
    Обновляет статистику блогера в таблице bloggers
    """
    stats = get_blogger_stats(blogger_id)
    
    conn = get_blogger_db_connection()
    cursor = conn.cursor()
    
    # Проверяем структуру таблицы bloggers
    cursor.execute("PRAGMA table_info(bloggers)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Формируем запрос в зависимости от структуры таблицы
    update_fields = []
    update_values = []
    
    if 'total_referrals' in columns:
        update_fields.append("total_referrals = ?")
        update_values.append(stats['total_referrals'])
    
    if 'total_conversions' in columns:
        update_fields.append("total_conversions = ?")
        update_values.append(stats['total_conversions'])
    
    if 'total_earned' in columns:
        update_fields.append("total_earned = ?")
        update_values.append(stats['total_earned'])
    
    # Если есть поля для обновления
    if update_fields:
        update_query = f"UPDATE bloggers SET {', '.join(update_fields)} WHERE id = ?"
        update_values.append(blogger_id)
        cursor.execute(update_query, tuple(update_values))
    else:
        # Если нужных колонок нет, добавляем их
        try:
            missing_columns = []
            if 'total_referrals' not in columns:
                missing_columns.append("ADD COLUMN total_referrals INTEGER DEFAULT 0")
            if 'total_conversions' not in columns:
                missing_columns.append("ADD COLUMN total_conversions INTEGER DEFAULT 0")
            if 'total_earned' not in columns:
                missing_columns.append("ADD COLUMN total_earned REAL DEFAULT 0")
                
            for alter_query in missing_columns:
                cursor.execute(f"ALTER TABLE bloggers {alter_query}")
                
            # Теперь обновляем значения
            cursor.execute("""
                UPDATE bloggers 
                SET total_referrals = ?, total_conversions = ?, total_earned = ? 
                WHERE id = ?
            """, (
                stats['total_referrals'],
                stats['total_conversions'],
                stats['total_earned'],
                blogger_id
            ))
        except Exception as e:
            print(f"Ошибка при добавлении колонок в таблицу bloggers: {str(e)}")
    
    conn.commit()
    conn.close()
    
    return stats

def get_blogger_referrals(blogger_id, limit=10):
    """
    Получает последние реферральные переходы блогера
    """
    conn = get_blogger_db_connection()
    cursor = conn.cursor()
    
    # Проверяем структуру таблицы
    cursor.execute("PRAGMA table_info(blogger_referrals)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Проверяем наличие колонки created_at
    if 'created_at' not in columns:
        try:
            # Добавляем колонку created_at, если её нет
            cursor.execute("ALTER TABLE blogger_referrals ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
            conn.commit()
        except Exception as e:
            print(f"Ошибка при добавлении колонки created_at: {str(e)}")
    
    # Формируем запрос с учетом доступных колонок
    if 'created_at' in columns:
        order_by = "ORDER BY created_at DESC"
    else:
        # Если колонки created_at нет и её не удалось добавить, используем id для сортировки
        order_by = "ORDER BY id DESC"
    
    cursor.execute(f"""
        SELECT * FROM blogger_referrals 
        WHERE blogger_id = ? 
        {order_by} LIMIT ?
    """, (blogger_id, limit))
    
    referrals = cursor.fetchall()
    conn.close()
    
    return referrals

def record_referral(blogger_id, user_id="", source="direct"):
    """
    Записывает реферальный переход
    """
    if not blogger_id:
        return None
        
    conn = get_blogger_db_connection()
    cursor = conn.cursor()
    
    # Проверяем структуру таблицы
    cursor.execute("PRAGMA table_info(blogger_referrals)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Формируем SQL запрос в зависимости от структуры таблицы
    fields = ["blogger_id", "user_id", "source"]
    values = [blogger_id, user_id, source]
    
    # Если есть колонка created_at, добавляем текущую дату
    if 'created_at' in columns:
        fields.append("created_at")
        values.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    
    # Формируем запрос
    placeholders = ", ".join(["?" for _ in fields])
    fields_str = ", ".join(fields)
    
    cursor.execute(
        f"INSERT INTO blogger_referrals ({fields_str}) VALUES ({placeholders})",
        tuple(values)
    )
    
    referral_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    # Обновляем статистику блогера
    update_blogger_stats(blogger_id)
    
    return referral_id

def mark_conversion(user_id, commission_amount=0):
    """
    Отмечает конверсию пользователя для реферальной программы
    
    Вызывайте эту функцию после успешной регистрации/оплаты пользователя
    
    Параметры:
    - user_id: ID пользователя
    - commission_amount: сумма комиссионных для блогера
    """
    if not user_id:
        return False
    
    conn = get_blogger_db_connection()
    cursor = conn.cursor()
    
    # Проверяем структуру таблицы
    cursor.execute("PRAGMA table_info(blogger_referrals)")
    columns = [column[1] for column in cursor.fetchall()]
    
    # Проверяем наличие необходимых колонок
    required_columns = ['converted', 'converted_at', 'conversion_date', 'commission_amount', 'status']
    missing_columns = []
    
    for column in required_columns:
        if column not in columns:
            missing_columns.append(column)
    
    # Если есть отсутствующие колонки, добавляем их
    if missing_columns:
        for column in missing_columns:
            try:
                if column in ['converted', 'status']:
                    cursor.execute(f"ALTER TABLE blogger_referrals ADD COLUMN {column} TEXT")
                elif column in ['commission_amount']:
                    cursor.execute(f"ALTER TABLE blogger_referrals ADD COLUMN {column} REAL DEFAULT 0")
                else:
                    cursor.execute(f"ALTER TABLE blogger_referrals ADD COLUMN {column} TEXT")
            except Exception as e:
                print(f"Ошибка при добавлении колонки {column}: {str(e)}")
                pass
    
    # Находим последний реферальный переход для данного пользователя
    cursor.execute("""
        SELECT * FROM blogger_referrals 
        WHERE user_id = ? AND converted = 0 
        ORDER BY created_at DESC LIMIT 1
    """, (user_id,))
    
    referral = cursor.fetchone()
    
    if referral:
        # Отмечаем конверсию
        update_fields = []
        update_params = []
        
        if 'converted' in columns:
            update_fields.append("converted = 1")
        
        if 'converted_at' in columns:
            update_fields.append("converted_at = ?")
            update_params.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        
        if 'conversion_date' in columns:
            update_fields.append("conversion_date = ?")
            update_params.append(datetime.now().strftime("%Y-%m-%d"))
        
        if 'commission_amount' in columns:
            update_fields.append("commission_amount = ?")
            update_params.append(commission_amount)
        
        if 'status' in columns:
            update_fields.append("status = 'completed'")
        
        if update_fields:
            update_query = f"UPDATE blogger_referrals SET {', '.join(update_fields)} WHERE id = ?"
            update_params.append(referral['id'])
            
            cursor.execute(update_query, tuple(update_params))
            conn.commit()
            
            # Обновляем статистику блогера
            update_blogger_stats(referral['blogger_id'])
            result = True
        else:
            result = False
    else:
        result = False
    
    conn.close()
    return result

def toggle_blogger_status(blogger_id, activate=True):
    """
    Изменяет статус блогера (активный/неактивный)
    """
    conn = get_blogger_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("UPDATE bloggers SET is_active = ? WHERE id = ?", (1 if activate else 0, blogger_id))
    
    conn.commit()
    conn.close()
    
    return True

def get_total_stats():
    """
    Получает общую статистику по всем блогерам
    """
    conn = get_blogger_db_connection()
    cursor = conn.cursor()
    
    try:
        # Проверяем структуру таблицы blogger_referrals
        cursor.execute("PRAGMA table_info(blogger_referrals)")
        columns = [column[1] for column in cursor.fetchall()]
        
        # Общее количество реферральных переходов
        cursor.execute("SELECT COUNT(*) FROM blogger_referrals")
        total_referrals = cursor.fetchone()[0] or 0
        
        # Общее количество конверсий
        if 'converted' in columns:
            cursor.execute("SELECT COUNT(*) FROM blogger_referrals WHERE converted = 1")
            total_conversions = cursor.fetchone()[0] or 0
        else:
            total_conversions = 0
        
        # Общий заработок
        if 'commission_amount' in columns:
            cursor.execute("SELECT SUM(commission_amount) FROM blogger_referrals")
            total_earnings = cursor.fetchone()[0] or 0
        else:
            total_earnings = 0
        
        # Если нет данных в таблице blogger_referrals, 
        # попробуем суммировать статистику из таблицы bloggers
        if total_referrals == 0:
            cursor.execute("PRAGMA table_info(bloggers)")
            blogger_columns = [column[1] for column in cursor.fetchall()]
            
            if 'total_referrals' in blogger_columns:
                cursor.execute("SELECT SUM(total_referrals) FROM bloggers")
                total_referrals = cursor.fetchone()[0] or 0
            
            if 'total_conversions' in blogger_columns:
                cursor.execute("SELECT SUM(total_conversions) FROM bloggers")
                total_conversions = cursor.fetchone()[0] or 0
            
            if 'total_earned' in blogger_columns:
                cursor.execute("SELECT SUM(total_earned) FROM bloggers")
                total_earnings = cursor.fetchone()[0] or 0
        
        # Логируем результаты для отладки
        print(f"Статистика: переходы={total_referrals}, конверсии={total_conversions}, заработок={total_earnings}")
        
        return {
            'total_referrals': total_referrals,
            'total_conversions': total_conversions,
            'total_earnings': total_earnings
        }
    except Exception as e:
        print(f"Ошибка при получении общей статистики: {str(e)}")
        return {
            'total_referrals': 0,
            'total_conversions': 0,
            'total_earnings': 0
        }
    finally:
        conn.close()

def process_referral_reward(user_id, referrer_id=None):

    import logging
    import sqlite3
    from datetime import datetime, timedelta
    from database.models import get_session, User, ReferralUse
    
    logging.info(f"[REFERRAL_BONUS] Начало обработки бонуса для реферера пользователя {user_id} (тип: {type(user_id).__name__}), referrer_id={referrer_id} (тип: {type(referrer_id).__name__ if referrer_id else 'None'})")
    
    try:
        session = get_session()
        
        # Получаем более детальную информацию о пользователе
        user_obj = session.query(User).filter(User.id == user_id).first()
        if user_obj:
            logging.info(f"[REFERRAL_BONUS] Найден пользователь по user.id: user_id={user_obj.user_id}, username={user_obj.username}")
        else:
            # Если не нашли по id записи, пробуем найти по telegram id
            user_tg = session.query(User).filter(User.user_id == user_id).first()
            if user_tg:
                logging.info(f"[REFERRAL_BONUS] Найден пользователь по user.user_id: id={user_tg.id}, username={user_tg.username}")
                user_id = user_tg.id  # Используем id записи для дальнейшего поиска
                logging.info(f"[REFERRAL_BONUS] Используем id записи: {user_id}")
            else:
                logging.warning(f"[REFERRAL_BONUS] Пользователь не найден ни по id={user_id}, ни по user_id={user_id}")
        
        # Если referrer_id не указан, ищем его в базе
        if not referrer_id:
            # Проверяем запись использования реферальной ссылки для этого пользователя
            logging.info(f"[REFERRAL_BONUS] Поиск реферера для пользователя {user_id}")
            
            # Выводим все записи ReferralUse для отладки
            all_refs = session.query(ReferralUse).all()
            logging.info(f"[REFERRAL_BONUS] Всего записей ReferralUse: {len(all_refs)}")
            for ref in all_refs:
                logging.info(f"[REFERRAL_BONUS] ReferralUse: id={ref.id}, user_id={ref.user_id}, referrer_id={ref.referrer_id}, subscription_purchased={getattr(ref, 'subscription_purchased', False)}")
            
            # Пытаемся найти запись с подтвержденной покупкой
            referral = session.query(ReferralUse).filter(
                ReferralUse.user_id == user_id,
                ReferralUse.subscription_purchased == True
            ).first()
            
            logging.info(f"[REFERRAL_BONUS] Результат поиска по user_id={user_id} и subscription_purchased=True: {referral}")
            
            if not referral and isinstance(user_id, int):
                # Если не найдено, проверяем по полю referred_id (для обратной совместимости)
                logging.info(f"[REFERRAL_BONUS] Поиск по referred_id для пользователя {user_id}")
                user = session.query(User).filter(User.id == user_id).first()
                if user:
                    referral = session.query(ReferralUse).filter(
                        ReferralUse.referred_id == user.user_id,
                        ReferralUse.subscription_purchased == True
                    ).first()
                    logging.info(f"[REFERRAL_BONUS] Результат поиска по referred_id={user.user_id} и subscription_purchased=True: {referral}")
            
            # Если всё еще не нашли с subscription_purchased=True, 
            # пробуем искать без этого фильтра и обновим статус
            if not referral:
                logging.info(f"[REFERRAL_BONUS] Не найдена запись с subscription_purchased=True, ищем без фильтра")
                referral = session.query(ReferralUse).filter(
                    ReferralUse.user_id == user_id
                ).first()
                
                if referral:
                    logging.info(f"[REFERRAL_BONUS] Найдена запись без фильтра: ID={referral.id}, обновляем статус покупки")
                    referral.subscription_purchased = True
                    referral.purchase_date = datetime.now()
                    session.commit()
                    logging.info(f"[REFERRAL_BONUS] Обновлен статус покупки для записи ID={referral.id}")
            
            if referral and referral.referrer_id:
                referrer_id = referral.referrer_id
                logging.info(f"[REFERRAL_BONUS] Найден реферер с ID {referrer_id} для пользователя {user_id}")
            else:
                logging.warning(f"[REFERRAL_BONUS] Не найден реферер для пользователя {user_id}")
                
                # Дополнительная логика для старых записей
                all_referrals = session.query(ReferralUse).filter(
                    ReferralUse.user_id == user_id
                ).all()
                
                if all_referrals:
                    for ref in all_referrals:
                        logging.info(f"[REFERRAL_BONUS] Найдена запись: ID={ref.id}, referrer_id={ref.referrer_id}, subscription_purchased={ref.subscription_purchased}, reward_processed={getattr(ref, 'reward_processed', None)}")
                
                session.close()
                return False
        
        # Получаем пользователя-реферера
        referrer = session.query(User).filter(User.id == referrer_id).first()
        
        if not referrer:
            # Если не найден по ID, ищем по user_id (для обратной совместимости)
            logging.info(f"[REFERRAL_BONUS] Поиск реферера по user_id {referrer_id}")
            referrer = session.query(User).filter(User.user_id == referrer_id).first()
            
        if not referrer:
            logging.warning(f"[REFERRAL_BONUS] Реферер с ID {referrer_id} не найден в базе данных")
            session.close()
            return False
        
        logging.info(f"[REFERRAL_BONUS] Начисляем бонус для реферера {referrer_id} (username: {referrer.username})")
        
        # Начисляем бонус - 30 дней подписки
        if referrer.subscription_expires and referrer.subscription_expires > datetime.now():
            # Если подписка активна, продлеваем её на 30 дней
            old_expiry = referrer.subscription_expires
            referrer.subscription_expires = referrer.subscription_expires + timedelta(days=30)
            logging.info(f"[REFERRAL_BONUS] Продлеваем подписку с {old_expiry} до {referrer.subscription_expires}")
        else:
            # Если подписки нет или истекла, устанавливаем на 30 дней от текущей даты
            referrer.subscription_expires = datetime.now() + timedelta(days=30)
            logging.info(f"[REFERRAL_BONUS] Устанавливаем новую подписку до {referrer.subscription_expires}")
        
        # Активируем подписку
        referrer.is_subscribed = True
        
        # Если тип подписки не указан, устанавливаем monthly
        if not referrer.subscription_type:
            referrer.subscription_type = "monthly"
        
        # Отмечаем, что бонус обработан в записи использования реферальной ссылки
        referral = session.query(ReferralUse).filter(
            ReferralUse.referrer_id == referrer_id,
            ReferralUse.user_id == user_id,
            ReferralUse.subscription_purchased == True,
            (ReferralUse.reward_processed == False) | (ReferralUse.reward_processed == None)
        ).first()
        
        if not referral:
            # Пробуем найти по referred_id
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                logging.info(f"[REFERRAL_BONUS] Ищем запись по referred_id={user.user_id}")
                referral = session.query(ReferralUse).filter(
                    ReferralUse.referrer_id == referrer_id,
                    ReferralUse.referred_id == user.user_id,
                    ReferralUse.subscription_purchased == True,
                    (ReferralUse.reward_processed == False) | (ReferralUse.reward_processed == None)
                ).first()
                logging.info(f"[REFERRAL_BONUS] Результат поиска по referred_id: {referral}")
        
        if referral:
            try:
                # Проверяем, есть ли атрибут reward_processed
                try:
                    if hasattr(referral, 'reward_processed'):
                        referral.reward_processed = True 
                        logging.info(f"[REFERRAL_BONUS] Поле reward_processed установлено в True")
                    else:
                        # Если атрибута нет, добавляем его через SQLAlchemy DDL
                        from sqlalchemy import text
                        logging.info(f"[REFERRAL_BONUS] Поле reward_processed отсутствует, добавляем его")
                        session.execute(text("ALTER TABLE referral_use ADD COLUMN IF NOT EXISTS reward_processed BOOLEAN DEFAULT FALSE"))
                        session.commit()
                        
                        # После добавления колонки пытаемся установить значение
                        session.execute(
                            text("UPDATE referral_use SET reward_processed = :value WHERE id = :id"),
                            {"value": True, "id": referral.id}
                        )
                        session.commit()
                        logging.info(f"[REFERRAL_BONUS] Добавлена колонка reward_processed и установлено значение для записи ID={referral.id}")
                except Exception as column_error:
                    logging.error(f"[REFERRAL_BONUS] Ошибка при работе с колонкой reward_processed: {str(column_error)}")
                    import traceback
                    logging.error(traceback.format_exc())
                
                logging.info(f"[REFERRAL_BONUS] Отмечаем бонус как обработанный для записи ID={referral.id}")
            except Exception as e:
                logging.error(f"[REFERRAL_BONUS] Ошибка при отметке обработки бонуса: {str(e)}")
                import traceback
                logging.error(traceback.format_exc())
        else:
            logging.warning(f"[REFERRAL_BONUS] Не найдена запись реферала для отметки бонуса")
        
        session.commit()
        
        logging.info(f"[REFERRAL_BONUS] Успешно начислен бонус рефереру {referrer_id}, подписка продлена до {referrer.subscription_expires}")
        
        # Получаем имя пользователя, купившего подписку
        user = session.query(User).filter(User.id == user_id).first()
        username = user.username if user and user.username else f"id{user_id}"
        
        session.close()
        
        # Отправляем уведомление рефереру
        try:
            from web.payment_routes import send_referral_bonus_notification
            logging.info(f"[REFERRAL_BONUS] Отправляем уведомление пользователю {referrer.user_id} (username: {referrer.username}) о бонусе от {username}")
            notification_result = send_referral_bonus_notification(referrer.user_id, username)
            logging.info(f"[REFERRAL_BONUS] Результат отправки уведомления: {notification_result}")
        except Exception as e:
            logging.error(f"[REFERRAL_BONUS] Ошибка при отправке уведомления: {str(e)}")
            import traceback
            logging.error(f"[REFERRAL_BONUS] Трассировка ошибки при отправке уведомления:\n{traceback.format_exc()}")
            # Попробуем прямой вызов бота
            try:
                from telegram import Bot
                import os
                token = os.getenv("TELEGRAM_TOKEN")
                if token:
                    bot = Bot(token=token)
                    message = (
                        f"🎁 *Поздравляем!* Вы получили бонусный месяц подписки!\n\n"
                        f"Ваш друг *{username}* только что оплатил подписку по вашей реферальной ссылке.\n\n"
                        f"Срок действия вашей подписки был продлен на 30 дней.\n"
                        f"Текущая дата окончания подписки: *{referrer.subscription_expires.strftime('%d.%m.%Y')}*\n\n"
                        f"Продолжайте приглашать друзей и получать бонусные месяцы!"
                    )
                    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                    keyboard = InlineKeyboardMarkup([
                        [InlineKeyboardButton(text="Пригласить еще друзей", callback_data="invite_friend")],
                        [InlineKeyboardButton(text="Управление подпиской", callback_data="subscription_management")]
                    ])
                    logging.info(f"[REFERRAL_BONUS] Альтернативная отправка уведомления пользователю {referrer.user_id}")
                    bot.send_message(
                        chat_id=referrer.user_id,
                        text=message,
                        parse_mode="Markdown",
                        reply_markup=keyboard
                    )
                    logging.info(f"[REFERRAL_BONUS] Альтернативное уведомление успешно отправлено")
                else:
                    logging.error("[REFERRAL_BONUS] Невозможно получить токен бота для альтернативной отправки")
            except Exception as alt_e:
                logging.error(f"[REFERRAL_BONUS] Ошибка при альтернативной отправке уведомления: {str(alt_e)}")
                import traceback
                logging.error(f"[REFERRAL_BONUS] Трассировка ошибки при альтернативной отправке:\n{traceback.format_exc()}")
        
        return True
    
    except Exception as e:
        logging.error(f"[REFERRAL_BONUS] Ошибка при обработке бонуса для реферера: {str(e)}")
        import traceback
        logging.error(traceback.format_exc())
        if 'session' in locals():
            session.close()
        return False 