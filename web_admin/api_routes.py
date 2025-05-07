from flask import Blueprint, request, jsonify, current_app
from database.models import Blogger, BloggerReferral, User, Payment, BloggerPayment, get_session, generate_access_key
from database.db import db
from sqlalchemy import func, desc
from datetime import datetime, timedelta
import secrets
import re
from functools import wraps
import sqlite3
import os
import json
import time
import traceback

api_bp = Blueprint('api', __name__)

# Определяем путь к БД блогеров
BLOGGERS_DB_PATH = os.path.join(os.getcwd(), 'willway_bloggers.db')

# Вспомогательная функция для получения соединения с базой данных блогеров
def get_bloggers_db_connection():
    """Устанавливает соединение с БД блогеров"""
    try:
        # Используем прямой путь к файлу willway_bloggers.db
        db_path = os.path.join(os.getcwd(), 'willway_bloggers.db')
        print(f"Попытка подключения к БД: {db_path}")
        
        # Проверяем, существует ли файл базы данных
        db_exists = os.path.exists(db_path)
        if not db_exists:
            print("ОШИБКА: База данных не найдена")
            # Создаем базу данных и таблицы
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Создаем таблицу bloggers
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bloggers (
                    id INTEGER PRIMARY KEY,
                    name TEXT,
                    telegram_id TEXT,
                    access_key TEXT UNIQUE,
                    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Создаем таблицу blogger_referrals
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS blogger_referrals (
                    id INTEGER PRIMARY KEY,
                    blogger_id INTEGER,
                    user_id INTEGER,
                    date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    purchase_price REAL DEFAULT 0,
                    conversion_date TIMESTAMP,
                    commission REAL DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    FOREIGN KEY (blogger_id) REFERENCES bloggers (id)
                )
            ''')
            
            conn.commit()
            print("База данных и таблицы созданы")
            return conn
        
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Проверяем наличие необходимых таблиц
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND (name='bloggers' OR name='blogger_referrals')")
        tables = cursor.fetchall()
        table_names = [table['name'] for table in tables]
        
        if 'bloggers' not in table_names or 'blogger_referrals' not in table_names:
            print("ОШИБКА: В базе данных отсутствуют необходимые таблицы")
            # Создаем отсутствующие таблицы
            if 'bloggers' not in table_names:
                cursor.execute('''
                    CREATE TABLE bloggers (
                        id INTEGER PRIMARY KEY,
                        name TEXT,
                        telegram_id TEXT,
                        access_key TEXT UNIQUE,
                        registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
            
            if 'blogger_referrals' not in table_names:
                cursor.execute('''
                    CREATE TABLE blogger_referrals (
                        id INTEGER PRIMARY KEY,
                        blogger_id INTEGER,
                        user_id INTEGER,
                        date_added TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        purchase_price REAL DEFAULT 0,
                        conversion_date TIMESTAMP,
                        commission REAL DEFAULT 0,
                        status TEXT DEFAULT 'pending',
                        FOREIGN KEY (blogger_id) REFERENCES bloggers (id)
                    )
                ''')
            
            conn.commit()
            print("Отсутствующие таблицы созданы")
        
        print("Подключение к БД успешно установлено")
        return conn
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА при подключении к БД: {str(e)}")
        # Если мы не можем подключиться к БД, генерируем исключение
        raise ConnectionError(f"Не удалось подключиться к базе данных: {str(e)}")

# Вспомогательная функция для проверки блогера по ключу доступа
def verify_blogger_by_key(access_key, blogger_id=None):
    """
    Проверяет существование блогера по ключу доступа и, опционально, по ID.
    Возвращает данные блогера или None, если блогер не найден.
    """
    print(f"Проверка блогера: key={access_key}, id={blogger_id}")
    
    try:
        conn = get_bloggers_db_connection()
        cursor = conn.cursor()
        
        if blogger_id:
            # Если указан ID блогера, проверяем совпадение и ID, и ключа
            cursor.execute(
                "SELECT * FROM bloggers WHERE access_key = ? AND id = ?", 
                (access_key, blogger_id)
            )
        else:
            # Иначе проверяем только по ключу
            cursor.execute("SELECT * FROM bloggers WHERE access_key = ?", (access_key,))
        
        blogger = cursor.fetchone()
        conn.close()
        
        if blogger:
            blogger_dict = dict(blogger)
            print(f"Блогер найден: id={blogger_dict.get('id')}")
            return blogger_dict  # Преобразуем Row в dict
        
        print(f"Блогер не найден для ключа {access_key}")
        return None
    except Exception as e:
        print(f"Ошибка при проверке блогера: {str(e)}")
        if 'conn' in locals():
            conn.close()
    return None

# Декоратор для проверки авторизации
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        from flask import session, redirect, url_for
        if 'logged_in' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@api_bp.route('/blogger/verify-key', methods=['POST'])
def verify_blogger_key():
    data = request.get_json()
    
    if not data or 'key' not in data:
        return jsonify({"success": False, "error": "Не указан ключ доступа"}), 400
    
    access_key = data['key']
    
    db_session = get_session()
    try:
        blogger = db_session.query(Blogger).filter_by(access_key=access_key).first()
        
        if not blogger:
            return jsonify({"success": False, "error": "Неверный ключ доступа"}), 401
        
        return jsonify({
            "success": True,
            "blogger_id": blogger.id,
            "blogger_name": blogger.name,
            "access_key": blogger.access_key
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Ошибка базы данных: {str(e)}"}), 500
    finally:
        db_session.close()

@api_bp.route('/blogger/stats', methods=['GET'])
def get_blogger_stats():
    """
    Получение статистики блогера (количество рефералов, конверсий, заработок).
    Параметры:
    - key или id: ключ доступа или идентификатор блогера
    """
    try:
        print(f"Получен запрос статистики блогера: ID={request.args.get('id')}, key={request.args.get('key')}, nocache={request.args.get('nocache')}")
        # Получаем ключ из параметров запроса
        access_key = request.args.get('key') or request.args.get('id')
        
        if not access_key:
            print("Ошибка: отсутствует ключ доступа")
            return jsonify({
                'status': 'error',
                'message': 'Отсутствует ключ доступа'
            }), 400
        
        # Получаем данные блогера по ключу
        blogger = verify_blogger_by_key(access_key)
        
        if not blogger:
            print(f"Ошибка: блогер не найден по ключу {access_key}")
            return jsonify({
                'status': 'error',
                'message': 'Неверный ключ доступа'
            }), 401
        
        blogger_id = blogger['id']
        print(f"Получение статистики для блогера {blogger_id}")
        
        # Подключаемся к БД
        conn = get_bloggers_db_connection()
        cursor = conn.cursor()
        
        # Получаем количество рефералов
        cursor.execute(
            "SELECT COUNT(*) as total FROM blogger_referrals WHERE blogger_id = ?", 
            (blogger_id,)
        )
        total_referrals = cursor.fetchone()['total']
        print(f"Всего рефералов: {total_referrals}")
        
        # Получаем количество конверсий
        cursor.execute(
            "SELECT COUNT(*) as total FROM blogger_referrals WHERE blogger_id = ? AND (converted = 1 OR status = 'converted')", 
            (blogger_id,)
        )
        total_conversions = cursor.fetchone()['total']
        print(f"Всего конверсий: {total_conversions}")
        
        # Получаем данные для графика рефералов по дням (за последние 30 дней)
        thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        
        cursor.execute("""
            SELECT date(created_at) as day, COUNT(*) as count 
            FROM blogger_referrals 
            WHERE blogger_id = ? AND date(created_at) >= ? 
            GROUP BY day 
            ORDER BY day
        """, (blogger_id, thirty_days_ago))
        
        daily_referrals = cursor.fetchall()
        referrals_chart_data = {
            'labels': [row['day'] for row in daily_referrals],
            'data': [row['count'] for row in daily_referrals]
        }
        print(f"Данные для графика рефералов: {len(daily_referrals)} дней")
        
        # Получаем данные для графика конверсий по дням (за последние 30 дней)
        cursor.execute("""
            SELECT date(conversion_date) as day, COUNT(*) as count 
            FROM blogger_referrals 
            WHERE blogger_id = ? AND (converted = 1 OR status = 'converted') AND date(conversion_date) >= ? 
            GROUP BY day 
            ORDER BY day
        """, (blogger_id, thirty_days_ago))
        
        daily_conversions = cursor.fetchall()
        conversions_chart_data = {
            'labels': [row['day'] for row in daily_conversions],
            'data': [row['count'] for row in daily_conversions]
        }
        print(f"Данные для графика конверсий: {len(daily_conversions)} дней")
            
        # Получаем данные для графика заработка по дням (за последние 30 дней)
        cursor.execute("""
            SELECT date(conversion_date) as day, SUM(commission) as amount 
            FROM blogger_referrals 
            WHERE blogger_id = ? AND (converted = 1 OR status = 'converted') AND date(conversion_date) >= ? 
            GROUP BY day 
            ORDER BY day
        """, (blogger_id, thirty_days_ago))
        
        daily_earnings = cursor.fetchall()
        earnings_chart_data = {
            'labels': [row['day'] for row in daily_earnings],
            'data': [row['amount'] for row in daily_earnings]
        }
        print(f"Данные для графика заработка: {len(daily_earnings)} дней")
        
        # Получаем общий заработок
        cursor.execute(
            "SELECT SUM(commission) as total FROM blogger_referrals WHERE blogger_id = ? AND (converted = 1 OR status = 'converted')", 
            (blogger_id,)
        )
        total_earnings = cursor.fetchone()['total'] or 0
        print(f"Общий заработок: {total_earnings}")
        
        # Формируем реферальную ссылку
        bot_username = current_app.config.get('TELEGRAM_BOT_USERNAME', 'willwayapp_bot')
        referral_link = f"https://t.me/{bot_username}?start=ref_{blogger['access_key']}"
        
        conn.close()
        
        return jsonify({
            'status': 'success',
            'data': {
                'name': blogger['name'],
                'blogger_id': blogger['id'],
                'join_date': blogger.get('join_date') or blogger.get('created_at'),
                'total_referrals': total_referrals,
                'total_conversions': total_conversions,
                'total_earnings': total_earnings,
                'referral_link': referral_link,  # Добавляем реферальную ссылку в ответ
                'referrals_chart': referrals_chart_data,
                'conversions_chart': conversions_chart_data,
                'earnings_chart': earnings_chart_data
            }
        })
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА в get_blogger_stats: {str(e)}")
        traceback.print_exc()  # Печатаем полный стек ошибки
        return jsonify({
            'status': 'error',
            'message': f'Внутренняя ошибка сервера: {str(e)}'
        }), 500

@api_bp.route('/blogger/referrals', methods=['GET'])
def get_blogger_referrals():
    """
    Получение списка рефералов блогера.
    Параметры:
    - key или id: ключ доступа или идентификатор блогера
    - page: номер страницы (по умолчанию 1)
    - per_page: количество записей на страницу (по умолчанию 20)
    """
    try:
        # Получаем ключ из параметров запроса
        access_key = request.args.get('key') or request.args.get('id')
        
        if not access_key:
            print("Ошибка: отсутствует ключ доступа")
            return jsonify({
                'status': 'error',
                'message': 'Отсутствует ключ доступа'
            }), 400
    
        # Получаем данные блогера по ключу
        blogger = verify_blogger_by_key(access_key)
        
        if not blogger:
            print(f"Ошибка: блогер не найден по ключу {access_key}")
            return jsonify({
                'status': 'error',
                'message': 'Неверный ключ доступа'
            }), 401
        
        blogger_id = blogger['id']
        
        # Пагинация
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 20))
        
        print(f"Получение списка рефералов для блогера {blogger_id}, страница {page}, записей на страницу {per_page}")
        
        # Подключаемся к БД
        conn = get_bloggers_db_connection()
        cursor = conn.cursor()
        
        # Получаем общее количество рефералов
        cursor.execute(
            "SELECT COUNT(*) as total FROM blogger_referrals WHERE blogger_id = ?", 
            (blogger_id,)
        )
        total_referrals = cursor.fetchone()['total']
        print(f"Всего рефералов: {total_referrals}")
        
        # Рассчитываем смещение для пагинации
        offset = (page - 1) * per_page
        
        # Получаем список рефералов с пагинацией
        cursor.execute("""
            SELECT * FROM blogger_referrals 
            WHERE blogger_id = ? 
            ORDER BY created_at DESC 
            LIMIT ? OFFSET ?
        """, (blogger_id, per_page, offset))
        
        referrals_data = cursor.fetchall()
        print(f"Получено {len(referrals_data)} записей")
        
        # Преобразуем данные для JSON
        referrals = []
        for referral in referrals_data:
            referral_dict = dict(referral)
            
            # Преобразуем даты в строки для JSON
            if 'created_at' in referral_dict and referral_dict['created_at']:
                referral_dict['date_added'] = str(referral_dict['created_at'])
                
            if 'conversion_date' in referral_dict and referral_dict['conversion_date']:
                referral_dict['conversion_date'] = str(referral_dict['conversion_date'])
                
            referrals.append(referral_dict)
        
        conn.close()
        
        # Рассчитываем метаданные пагинации
        total_pages = (total_referrals + per_page - 1) // per_page  # Округление вверх
        has_next = page < total_pages
        has_prev = page > 1
        
        return jsonify({
            'status': 'success',
            'data': {
                'referrals': referrals,
                'meta': {
                    'total': total_referrals,
                    'page': page,
                    'per_page': per_page,
                    'total_pages': total_pages,
                    'has_next': has_next,
                    'has_prev': has_prev
                }
            }
        })
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА в get_blogger_referrals: {str(e)}")
        traceback.print_exc()  # Печатаем полный стек ошибки
        return jsonify({
            'status': 'error',
            'message': f'Внутренняя ошибка сервера: {str(e)}'
        }), 500

@api_bp.route('/blogger/generate-key', methods=['POST'])
def generate_blogger_key():
    """Генерация нового ключа доступа для блогера (только для администраторов)"""
    data = request.get_json()
    
    if not data or 'admin_key' not in data or 'blogger_id' not in data:
        return jsonify({"success": False, "error": "Недостаточно данных"}), 400
    
    admin_key = data['admin_key']
    blogger_id = data['blogger_id']
    
    # Проверка ключа администратора
    if admin_key != current_app.config.get('ADMIN_API_KEY'):
        return jsonify({"success": False, "error": "Нет доступа"}), 401
    
    db_session = get_session()
    try:
        # Поиск блогера
        blogger = db_session.query(Blogger).get(blogger_id)
        if not blogger:
            return jsonify({"success": False, "error": "Блогер не найден"}), 404
        
        # Генерация нового ключа доступа
        new_key = secrets.token_hex(16)
        blogger.access_key = new_key
        
        db_session.commit()
        return jsonify({
            "success": True,
            "blogger_id": blogger.id,
            "new_key": new_key
        })
    except Exception as e:
        db_session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        db_session.close()

# API для блогеров
@api_bp.route('/bloggers', methods=['GET'])
@login_required
def get_bloggers():
    """Получение списка всех блогеров"""
    try:
        db_session = get_session()
        bloggers = db_session.query(Blogger).all()
        
        bloggers_data = []
        for blogger in bloggers:
            referrals_count = db_session.query(BloggerReferral).filter(
                BloggerReferral.blogger_id == blogger.id
            ).count()
            
            converted_count = db_session.query(BloggerReferral).filter(
                BloggerReferral.blogger_id == blogger.id,
                BloggerReferral.converted == True
            ).count()
            
            earnings = db_session.query(func.sum(BloggerPayment.amount)).filter(
                BloggerPayment.blogger_id == blogger.id,
                BloggerPayment.status == 'paid'
            ).scalar() or 0
            
            bloggers_data.append({
                'id': blogger.id,
                'name': blogger.name,
                'telegram_id': blogger.telegram_id or '',
                'email': blogger.email or '',
                'access_key': blogger.access_key,
                'created_at': blogger.created_at.strftime("%d.%m.%Y %H:%M") if blogger.created_at else '',
                'is_active': blogger.is_active,
                'referrals_count': referrals_count,
                'converted_count': converted_count,
                'earnings': float(earnings)
            })
        
        db_session.close()
        return jsonify({'success': True, 'bloggers': bloggers_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/bloggers', methods=['POST'])
@login_required
def add_blogger():
    """Добавление нового блогера"""
    try:
        name = request.form.get('name')
        email = request.form.get('email')
        username = request.form.get('username')  # Используем username вместо telegram_id
        
        if not name:
            return jsonify({'success': False, 'error': 'Имя блогера обязательно'}), 400
        
        # Генерируем уникальный ключ доступа
        access_key = generate_access_key()
        
        # Создаем запись о блогере
        blogger = Blogger(
            name=name,
            email=email,
            telegram_id=username,  # Сохраняем username в поле telegram_id
            access_key=access_key,
            is_active=True
        )
        
        db_session = get_session()
        db_session.add(blogger)
        db_session.commit()
        
        # Получаем данные нового блогера
        blogger_data = {
            'id': blogger.id,
            'name': blogger.name,
            'telegram_id': blogger.telegram_id or '',
            'email': blogger.email or '',
            'access_key': blogger.access_key,
            'created_at': blogger.created_at.strftime("%d.%m.%Y %H:%M") if blogger.created_at else '',
            'is_active': blogger.is_active
        }
        
        db_session.close()
        return jsonify({'success': True, 'blogger': blogger_data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/bloggers/stats', methods=['GET'])
@login_required
def get_bloggers_stats():
    """Получение общей статистики по блогерам"""
    try:
        db_session = get_session()
        
        # Общее количество блогеров
        total_bloggers = db_session.query(Blogger).count()
        
        # Общее количество рефералов от блогеров
        total_referrals = db_session.query(BloggerReferral).count()
        
        # Количество успешных конверсий
        converted_referrals = db_session.query(BloggerReferral).filter(
            BloggerReferral.converted == True
        ).count()
        
        # Общая сумма выплат блогерам
        total_earnings = db_session.query(func.sum(BloggerPayment.amount)).filter(
            BloggerPayment.status == 'paid'
        ).scalar() or 0
        
        # Конверсия
        conversion_rate = 0
        if total_referrals > 0:
            conversion_rate = (converted_referrals / total_referrals) * 100
        
        stats = {
            'total_bloggers': total_bloggers,
            'total_referrals': total_referrals,
            'converted_referrals': converted_referrals,
            'total_earnings': float(total_earnings),
            'conversion_rate': round(conversion_rate, 2)
        }
        
        db_session.close()
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/bloggers/<int:blogger_id>', methods=['DELETE'])
@login_required
def delete_blogger(blogger_id):
    """Удаление блогера"""
    try:
        db_session = get_session()
        blogger = db_session.query(Blogger).filter(Blogger.id == blogger_id).first()
        
        if not blogger:
            db_session.close()
            return jsonify({'success': False, 'error': 'Блогер не найден'}), 404
        
        # Удаляем связанные записи
        db_session.query(BloggerReferral).filter(BloggerReferral.blogger_id == blogger_id).delete()
        db_session.query(BloggerPayment).filter(BloggerPayment.blogger_id == blogger_id).delete()
        
        # Удаляем блогера
        db_session.delete(blogger)
        db_session.commit()
        
        db_session.close()
        return jsonify({'success': True})
    except Exception as e:
        db_session.rollback()
        db_session.close()
        return jsonify({'success': False, 'error': str(e)}), 500

@api_bp.route('/bloggers/<int:blogger_id>/stats', methods=['GET'])
@login_required
def get_detailed_blogger_stats(blogger_id):
    """Получение детальной статистики блогера за период"""
    try:
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        
        db_session = get_session()
        blogger = db_session.query(Blogger).get(blogger_id)
        
        if not blogger:
            db_session.close()
            return jsonify({"success": False, "error": "Блогер не найден"}), 404
        
        # Преобразуем строки в даты, если они предоставлены
        query_filter = [BloggerReferral.blogger_id == blogger_id]
        if start_date:
            try:
                start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
                query_filter.append(BloggerReferral.created_at >= start_datetime)
            except ValueError:
                pass
            
        if end_date:
            try:
                end_datetime = datetime.strptime(end_date, '%Y-%m-%d')
                end_datetime = datetime.combine(end_datetime.date(), datetime.max.time())  # Конец дня
                query_filter.append(BloggerReferral.created_at <= end_datetime)
            except ValueError:
                pass
        
        # Базовые метрики
        total_clicks = db_session.query(BloggerReferral).filter(*query_filter).count()
        
        # Конверсии
        conversion_filter = query_filter.copy()
        conversion_filter.append(BloggerReferral.converted == True)
        total_conversions = db_session.query(BloggerReferral).filter(*conversion_filter).count()
        
        # Комиссионные
        total_earnings = db_session.query(func.sum(BloggerReferral.commission_amount))\
            .filter(*conversion_filter).scalar() or 0
            
        # Реферальная ссылка
        bot_username = current_app.config.get('TELEGRAM_BOT_USERNAME', 'willwayapp_bot')
        referral_link = f"https://t.me/{bot_username}?start=ref_{blogger.access_key}"
            
        # Конверсия в процентах
        conversion_rate = 0
        if total_clicks > 0:
            conversion_rate = (total_conversions / total_clicks) * 100
            
        # Данные по дням, если указан период
        daily_data = []
        if start_date and end_date:
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d')
                end_dt = datetime.strptime(end_date, '%Y-%m-%d')
                current_date = start_dt
                
                while current_date <= end_dt:
                    day_start = datetime.combine(current_date.date(), datetime.min.time())
                    day_end = datetime.combine(current_date.date(), datetime.max.time())
                    
                    # Количество переходов за день
                    day_clicks = db_session.query(BloggerReferral).filter(
                        BloggerReferral.blogger_id == blogger_id,
                        BloggerReferral.created_at >= day_start,
                        BloggerReferral.created_at <= day_end
                    ).count()
                    
                    # Количество конверсий за день
                    day_conversions = db_session.query(BloggerReferral).filter(
                        BloggerReferral.blogger_id == blogger_id,
                        BloggerReferral.converted == True,
                        BloggerReferral.created_at >= day_start,
                        BloggerReferral.created_at <= day_end
                    ).count()
                    
                    # Получаем заработок за день
                    day_earnings = db_session.query(func.sum(BloggerReferral.commission_amount)).filter(
                        BloggerReferral.blogger_id == blogger_id,
                        BloggerReferral.converted == True,
                        BloggerReferral.created_at >= day_start,
                        BloggerReferral.created_at <= day_end
                    ).scalar() or 0
                    
                    daily_data.append({
                        "date": current_date.strftime("%Y-%m-%d"),
                        "clicks": day_clicks,
                        "conversions": day_conversions,
                        "earnings": float(day_earnings)
                    })
                    
                    current_date += timedelta(days=1)
            except ValueError:
                pass
        
        db_session.close()
        
        return jsonify({
            "success": True,
            "blogger": {
                "id": blogger.id,
                "name": blogger.name,
                "join_date": blogger.join_date.strftime("%Y-%m-%d"),
                "is_active": blogger.is_active
            },
            "stats": {
                "total_clicks": total_clicks,
                "total_conversions": total_conversions,
                "total_earnings": float(total_earnings),
                "conversion_rate": round(conversion_rate, 2),
                "referral_link": referral_link
            },
            "daily_data": daily_data
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@api_bp.route('/blogger/referral-link', methods=['GET'])
def get_blogger_referral_link():
    """Получение реферальной ссылки блогера"""
    blogger_id = request.args.get('id') or request.args.get('blogger_id')
    access_key = request.args.get('key') or request.args.get('access_key')
    
    if not blogger_id or not access_key:
        return jsonify({"success": False, "error": "Не указаны параметры id и key или blogger_id и access_key"}), 400
    
    db_session = get_session()
    try:
        # Проверка ключа доступа
        blogger = db_session.query(Blogger).filter_by(id=blogger_id, access_key=access_key).first()
        if not blogger:
            return jsonify({"success": False, "error": "Нет доступа"}), 401
        
        # Формируем реферальную ссылку
        bot_username = current_app.config.get('TELEGRAM_BOT_USERNAME', 'willwayapp_bot')
        referral_link = f"https://t.me/{bot_username}?start=ref_{blogger.access_key}"
        
        return jsonify({
            "success": True,
            "referral_link": referral_link,
            "access_key": blogger.access_key
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Ошибка при получении ссылки: {str(e)}"}), 500
    finally:
        db_session.close()

@api_bp.route('/blogger/earnings', methods=['GET'])
def get_blogger_earnings():
    """Получение информации о заработке блогера"""
    blogger_id = request.args.get('id') or request.args.get('blogger_id')
    access_key = request.args.get('key') or request.args.get('access_key')
    
    if not blogger_id or not access_key:
        return jsonify({"success": False, "error": "Не указаны параметры id и key или blogger_id и access_key"}), 400
    
    db_session = get_session()
    try:
        # Проверка ключа доступа
        blogger = db_session.query(Blogger).filter_by(id=blogger_id, access_key=access_key).first()
        if not blogger:
            return jsonify({"success": False, "error": "Нет доступа"}), 401
        
        # Получаем общую сумму заработка
        total_earnings = db_session.query(func.sum(BloggerReferral.commission_amount))\
            .filter_by(blogger_id=blogger.id, converted=True)\
            .scalar() or 0
        
        # Получаем сумму уже выплаченных средств
        paid_amount = db_session.query(func.sum(BloggerPayment.amount))\
            .filter_by(blogger_id=blogger.id, status='paid')\
            .scalar() or 0
        
        # Сумма, ожидающая выплаты
        pending_amount = db_session.query(func.sum(BloggerPayment.amount))\
            .filter_by(blogger_id=blogger.id, status='pending')\
            .scalar() or 0
        
        # Доступная к выводу сумма (заработанное минус выплаченное и ожидающее)
        available_amount = total_earnings - paid_amount - pending_amount
        
        # Получаем историю выплат
        payments_history = db_session.query(BloggerPayment)\
            .filter_by(blogger_id=blogger.id)\
            .order_by(desc(BloggerPayment.created_at))\
            .limit(10).all()
        
        payments_data = [{
            "id": payment.id,
            "amount": float(payment.amount),
            "status": payment.status,
            "created_at": payment.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "paid_at": payment.paid_at.strftime("%Y-%m-%d %H:%M:%S") if payment.paid_at else None
        } for payment in payments_history]
        
        return jsonify({
            "success": True,
            "total_earnings": float(total_earnings),
            "paid_amount": float(paid_amount),
            "pending_amount": float(pending_amount),
            "available_amount": float(available_amount),
            "payments_history": payments_data
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Ошибка при получении данных о заработке: {str(e)}"}), 500
    finally:
        db_session.close()

# Добавляем маршрут для проверки соединения
@api_bp.route('/ping', methods=['GET'])
def ping():
    """Проверка доступности API"""
    try:
        return jsonify({
            "success": True,
            "message": "API доступен",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({
            "success": False, 
            "error": f"Ошибка API: {str(e)}"
        }), 500

@api_bp.route('/bot/track-conversion', methods=['POST'])
def track_blogger_conversion():
    """Отслеживает конверсию (покупку) от пользователя, пришедшего по реферальной ссылке блогера"""
    try:
        data = request.json
        print(f"[КОНВЕРСИЯ] Получены данные: {data}")
        
        # Сохраняем все данные запроса для диагностики
        log_filename = "conversion_requests.log"
        with open(log_filename, "a", encoding="utf-8") as log_file:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            log_file.write(f"[{timestamp}] Получен запрос: {json.dumps(data, ensure_ascii=False)}\n")
        
        api_key = data.get('api_key')
        
        # Проверка API ключа
        if api_key != current_app.config.get('API_KEY'):
            print(f"[ОШИБКА КОНВЕРСИИ] Неверный API ключ: {api_key}")
            return jsonify({"success": False, "error": "Неверный API ключ"}), 401
        
        ref_code = data.get('ref_code')
        user_id = data.get('user_id')
        amount = float(data.get('amount', 0))
        purchase_id = data.get('purchase_id')
        
        print(f"[КОНВЕРСИЯ] Параметры: ref_code={ref_code}, user_id={user_id}, amount={amount}, purchase_id={purchase_id}")
        
        if not ref_code:
            print(f"[ОШИБКА КОНВЕРСИИ] Отсутствует ref_code")
            return jsonify({"success": False, "error": "Отсутствует параметр ref_code"}), 400
            
        if not user_id:
            print(f"[ОШИБКА КОНВЕРСИИ] Отсутствует user_id")
            return jsonify({"success": False, "error": "Отсутствует параметр user_id"}), 400
            
        if amount <= 0:
            print(f"[ОШИБКА КОНВЕРСИИ] Некорректная сумма: {amount}")
            return jsonify({"success": False, "error": f"Некорректная сумма: {amount}"}), 400
        
        print(f"[КОНВЕРСИЯ] Получен запрос на регистрацию конверсии: ref_code={ref_code}, user_id={user_id}, amount={amount}")
        
        # Подключаемся к БД
        try:
            conn = get_bloggers_db_connection()
            cursor = conn.cursor()
            print(f"[КОНВЕРСИЯ] Успешное подключение к БД")
        except Exception as db_err:
            print(f"[ОШИБКА КОНВЕРСИИ] Ошибка подключения к БД: {str(db_err)}")
            return jsonify({"success": False, "error": f"Ошибка подключения к БД: {str(db_err)}"}), 500
        
        try:
            # Извлекаем access_key из ref_code
            if ref_code.startswith('ref_'):
                access_key = ref_code.replace('ref_', '')
            else:
                access_key = ref_code
            
            print(f"[КОНВЕРСИЯ] Извлечен access_key: {access_key}")
                
            # Находим блогера
            cursor.execute("SELECT * FROM bloggers WHERE access_key = ?", (access_key,))
            blogger = cursor.fetchone()
            
            if not blogger:
                print(f"[ОШИБКА КОНВЕРСИИ] Блогер с ключом доступа {access_key} не найден")
                return jsonify({"success": False, "error": "Блогер не найден"}), 404
            
            blogger_id = blogger['id']
            print(f"[КОНВЕРСИЯ] Найден блогер: ID={blogger_id}, имя={blogger['name']}")
                
            # Ищем соответствующий реферальный переход
            source_pattern = f"telegram_start_{user_id}"
            cursor.execute("""
                SELECT * FROM blogger_referrals 
                WHERE (blogger_id = ? AND source LIKE ?) AND (converted = 0 OR converted IS NULL)
                ORDER BY created_at DESC LIMIT 1
            """, (blogger_id, f"%{source_pattern}%"))
            
            referral = cursor.fetchone()
        
            # Если переход не найден, создаем новую запись
            if not referral:
                print(f"[КОНВЕРСИЯ] Не найден переход для блогера {blogger_id} и пользователя {user_id}, создаем новый")
                
                # Получаем максимальный ID для генерации нового
                cursor.execute("SELECT MAX(id) as max_id FROM blogger_referrals")
                max_id_result = cursor.fetchone()
                next_id = 1
                if max_id_result and max_id_result['max_id'] is not None:
                    next_id = max_id_result['max_id'] + 1
                
                # Готовим параметры для новой записи
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                referral_source = f"telegram_start_{user_id}"
                
                # Проверяем, какие колонки существуют в таблице
                cursor.execute("PRAGMA table_info(blogger_referrals)")
                columns = [col['name'] for col in cursor.fetchall()]
                print(f"[КОНВЕРСИЯ] Колонки в таблице: {columns}")
                
                # Подготавливаем SQL-запрос на основе существующих колонок
                insert_columns = ["id", "blogger_id", "source"]
                insert_values = [next_id, blogger_id, referral_source]
                
                # Добавляем остальные поля, если они существуют
                column_mapping = {
                    "created_at": current_time,
                    "user_id": user_id,
                    "referral_date": current_time
                }
                
                for col, val in column_mapping.items():
                    if col in columns:
                        insert_columns.append(col)
                        insert_values.append(val)
                
                # Создаем запрос
                placeholders = ", ".join(["?" for _ in insert_values])
                columns_str = ", ".join(insert_columns)
                
                insert_query = f"INSERT INTO blogger_referrals ({columns_str}) VALUES ({placeholders})"
                print(f"[КОНВЕРСИЯ] Вставка нового реферала: {insert_query}")
                print(f"[КОНВЕРСИЯ] Значения: {insert_values}")
                
                cursor.execute(insert_query, insert_values)
                conn.commit()
                
                # Получаем созданную запись
                cursor.execute("SELECT * FROM blogger_referrals WHERE id = ?", (next_id,))
                referral = cursor.fetchone()
                print(f"[КОНВЕРСИЯ] Создан новый реферал: ID={next_id}")
            else:
                print(f"[КОНВЕРСИЯ] Найден существующий реферал: ID={referral['id']}")
            
            # Вычисляем комиссию (20% от суммы)
            commission = amount * 0.2
            print(f"[КОНВЕРСИЯ] Рассчитана комиссия: {commission} (20% от {amount})")
            
            # Определяем, какие поля нужно обновить
            update_fields = []
            update_values = []
            
            # Проверяем доступные поля для обновления
            if 'converted' in referral.keys():
                update_fields.append("converted = ?")
                update_values.append(1)
                
            current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
            field_mappings = {
                "converted_at": current_time,
                "conversion_date": current_time,
                "commission": commission,
                "commission_amount": commission,
                "commission_earned": commission,
                "status": "converted",
                "subscription_amount": amount
            }
            
            for field, value in field_mappings.items():
                if field in referral.keys():
                    update_fields.append(f"{field} = ?")
                    update_values.append(value)
        
            # Добавляем информацию о покупке в источник
            if purchase_id:
                update_fields.append("source = ?")
                current_source = referral['source'] if 'source' in referral.keys() else ""
                new_source = f"{current_source}_purchase_{purchase_id}" if current_source else f"purchase_{purchase_id}"
                update_values.append(new_source)
                
            # Подготавливаем и выполняем запрос на обновление
            update_values.append(referral['id'])
            update_query = f"UPDATE blogger_referrals SET {', '.join(update_fields)} WHERE id = ?"
            
            print(f"[КОНВЕРСИЯ] Обновление реферала: {update_query}")
            print(f"[КОНВЕРСИЯ] Значения: {update_values}")
            
            cursor.execute(update_query, update_values)
            conn.commit()
            
            # Обновляем общую статистику блогера
            if 'total_earned' in blogger.keys() and 'total_conversions' in blogger.keys():
                cursor.execute("""
                    UPDATE bloggers 
                    SET total_earned = total_earned + ?, total_conversions = total_conversions + 1
                    WHERE id = ?
                """, (commission, blogger_id))
                conn.commit()
                print(f"[КОНВЕРСИЯ] Обновлена статистика блогера: +{commission} к заработку, +1 к конверсиям")
                
            print(f"[КОНВЕРСИЯ] Конверсия успешно зарегистрирована для блогера {blogger_id}, комиссия: {commission}")
        
            return jsonify({
                "success": True, 
                "message": "Конверсия успешно зарегистрирована",
                "commission": commission,
                "blogger_id": blogger_id,
                "referral_id": referral['id']
            })
        except Exception as e:
            conn.rollback()
            print(f"[ОШИБКА КОНВЕРСИИ] {str(e)}")
            traceback.print_exc()
            return jsonify({"success": False, "error": f"Ошибка при регистрации конверсии: {str(e)}"}), 500
    except Exception as outer_e:
        print(f"[КРИТИЧЕСКАЯ ОШИБКА КОНВЕРСИИ] {str(outer_e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": f"Критическая ошибка: {str(outer_e)}"}), 500

@api_bp.route('/blogger_statistics/<key>')
def get_blogger_statistics(key):
    """Получение статистики блогера по ключу"""
    try:
        # Подключаемся к базе данных
        conn = sqlite3.connect(BLOGGERS_DB_PATH)
        cursor = conn.cursor()
        
        # Ищем блогера по ключу
        cursor.execute("SELECT id, name FROM bloggers WHERE access_key = ?", (key,))
        blogger = cursor.fetchone()
        
        if not blogger:
            return jsonify({'success': False, 'error': 'Блогер не найден'}), 404
        
        blogger_id, blogger_name = blogger
        
        # Получаем статистику кликов по дням
        # Проверяем структуру таблицы
        cursor.execute("PRAGMA table_info(blogger_referrals)")
        columns = [col[1] for col in cursor.fetchall()]
        
        has_created_at = 'created_at' in columns
        has_converted = 'converted' in columns
        has_commission = 'commission_amount' in columns
        
        # Определяем поле даты
        date_field = "created_at" if has_created_at else "referral_date"
        
        # Запрос на статистику кликов по дням
        date_query = f"SELECT strftime('%Y-%m-%d', {date_field}) as day, COUNT(*) as clicks"
        
        # Добавляем статистику конверсий если доступно
        if has_converted:
            date_query += ", SUM(converted) as conversions"
        
        # Добавляем статистику по комиссиям если доступно
        if has_commission:
            date_query += ", SUM(commission_amount) as earnings"
        
        date_query += f" FROM blogger_referrals WHERE blogger_id = ? GROUP BY day ORDER BY day"
        
        cursor.execute(date_query, (blogger_id,))
        daily_stats = cursor.fetchall()
        
        # Форматируем результаты
        stats = []
        column_names = ['date', 'clicks']
        if has_converted:
            column_names.append('conversions')
        if has_commission:
            column_names.append('earnings')
            
        for row in daily_stats:
            stat_row = {}
            for i, col_name in enumerate(column_names):
                if col_name == 'earnings' and row[i] is not None:
                    # Округляем комиссии до 2 знаков
                    stat_row[col_name] = round(row[i], 2)
                else:
                    stat_row[col_name] = row[i]
            stats.append(stat_row)
        
        # Получаем общую статистику
        total_clicks = sum(item['clicks'] for item in stats)
        total_conversions = sum(item.get('conversions', 0) or 0 for item in stats) if has_converted else 0
        total_earnings = sum(item.get('earnings', 0) or 0 for item in stats) if has_commission else 0
        
        result = {
            'success': True,
            'blogger': {
                'id': blogger_id,
                'name': blogger_name,
                'key': key
            },
            'statistics': {
                'total_clicks': total_clicks,
                'daily': stats
            }
        }
        
        # Добавляем конверсии если доступны
        if has_converted:
            result['statistics']['total_conversions'] = total_conversions
        
        # Добавляем заработок если доступен
        if has_commission:
            result['statistics']['total_earnings'] = round(total_earnings, 2)
        
        conn.close()
        return jsonify(result)
    
    except Exception as e:
        print(f"Ошибка при получении статистики блогера: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': str(e)}), 500 

# Добавим новый API-эндпоинт для ручного тестирования конверсий
@api_bp.route('/blogger/test-conversion', methods=['POST'])
@login_required
def test_blogger_conversion():
    """
    Создает тестовую конверсию для указанного блогера.
    Данный метод предназначен только для тестирования и администрирования.
    """
    try:
        data = request.json or {}
        
        # Проверяем наличие необходимых данных
        blogger_id = data.get('blogger_id')
        if not blogger_id:
            return jsonify({"success": False, "error": "Не указан ID блогера"}), 400
            
        amount = float(data.get('amount', 1000))  # По умолчанию 1000 рублей
        
        # Создаем тестовый ID пользователя
        test_user_id = f"test_user_{int(time.time())}"
        
        # Подключаемся к БД
        conn = get_bloggers_db_connection()
        cursor = conn.cursor()
        
        # Проверяем существование блогера
        cursor.execute("SELECT * FROM bloggers WHERE id = ?", (blogger_id,))
        blogger = cursor.fetchone()
        
        if not blogger:
            conn.close()
            return jsonify({"success": False, "error": "Блогер не найден"}), 404
        
        # Генерируем уникальный ID для новой записи
        cursor.execute("SELECT MAX(id) as max_id FROM blogger_referrals")
        max_id = cursor.fetchone()['max_id'] or 0
        next_id = max_id + 1
        
        # Создаем текущую дату/время
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Создаем запись о реферале
        source = f"test_conversion_{test_user_id}"
        cursor.execute("""
            INSERT INTO blogger_referrals 
            (id, blogger_id, user_id, created_at, referral_date, source)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (next_id, blogger_id, test_user_id, current_time, current_time, source))
        
        # Рассчитываем комиссию (20% от суммы)
        commission = amount * 0.2
        
        # Сразу же конвертируем реферал
        cursor.execute("""
            UPDATE blogger_referrals 
            SET converted = 1, 
                converted_at = ?, 
                conversion_date = ?,
                commission_amount = ?,
                commission = ?,
                status = 'converted',
                subscription_amount = ?
            WHERE id = ?
        """, (current_time, current_time, commission, commission, amount, next_id))
        
        # Пробуем обновить счетчики блогера
        try:
            cursor.execute("""
                UPDATE bloggers 
                SET total_earned = COALESCE(total_earned, 0) + ?, 
                    total_conversions = COALESCE(total_conversions, 0) + 1,
                    total_referrals = COALESCE(total_referrals, 0) + 1
                WHERE id = ?
            """, (commission, blogger_id))
        except sqlite3.OperationalError as e:
            print(f"Ошибка при обновлении счетчиков блогера: {str(e)}")
            # Продолжаем выполнение, даже если счетчики не обновились
        
        conn.commit()
        
        # Получаем обновленную запись
        cursor.execute("SELECT * FROM blogger_referrals WHERE id = ?", (next_id,))
        referral = cursor.fetchone()
        
        # Получаем обновленные данные блогера
        cursor.execute("SELECT * FROM bloggers WHERE id = ?", (blogger_id,))
        updated_blogger = cursor.fetchone()
        
        conn.close()
        
        return jsonify({
            "success": True,
            "message": "Тестовая конверсия успешно создана",
            "referral": dict(referral),
            "blogger": {
                "id": updated_blogger['id'],
                "name": updated_blogger['name'],
                "total_earned": updated_blogger.get('total_earned'),
                "total_conversions": updated_blogger.get('total_conversions'),
                "total_referrals": updated_blogger.get('total_referrals')
            }
        })
    except Exception as e:
        print(f"Ошибка при создании тестовой конверсии: {str(e)}")
        traceback.print_exc()
        
        if 'conn' in locals():
            conn.rollback()
            conn.close()
            
        return jsonify({"success": False, "error": f"Ошибка при создании тестовой конверсии: {str(e)}"}), 500

# Добавим API для проверки состояния БД блогеров
@api_bp.route('/blogger/db-status', methods=['GET'])
@login_required
def check_bloggers_db_status():
    """Проверяет состояние базы данных блогеров"""
    try:
        # Проверяем наличие файла БД
        if not os.path.exists(BLOGGERS_DB_PATH):
            return jsonify({
                "success": False,
                "error": "База данных не найдена",
                "path": BLOGGERS_DB_PATH
            }), 404
            
        # Подключаемся к БД
        conn = get_bloggers_db_connection()
        cursor = conn.cursor()
        
        # Получаем список таблиц
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row['name'] for row in cursor.fetchall()]
        
        db_info = {
            "success": True,
            "path": BLOGGERS_DB_PATH,
            "size": os.path.getsize(BLOGGERS_DB_PATH),
            "tables": {}
        }
        
        # Анализируем каждую таблицу
        for table in tables:
            # Получаем структуру таблицы
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [dict(row) for row in cursor.fetchall()]
            
            # Получаем количество записей
            cursor.execute(f"SELECT COUNT(*) as count FROM {table}")
            record_count = cursor.fetchone()['count']
            
            # Получаем пример данных (1 запись)
            cursor.execute(f"SELECT * FROM {table} LIMIT 1")
            sample_row = cursor.fetchone()
            sample_data = dict(sample_row) if sample_row else {}
            
            db_info["tables"][table] = {
                "columns": [col['name'] for col in columns],
                "record_count": record_count,
                "sample_data": sample_data
            }
            
        conn.close()
        return jsonify(db_info)
    except Exception as e:
        print(f"Ошибка при проверке БД блогеров: {str(e)}")
        traceback.print_exc()
        
        if 'conn' in locals():
            conn.close()
            
        return jsonify({
            "success": False, 
            "error": f"Ошибка при проверке БД: {str(e)}"
        }), 500 