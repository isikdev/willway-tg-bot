from flask import Blueprint, request, jsonify, current_app
from database.models import Blogger, BloggerReferral, User, Payment, BloggerPayment, get_session, generate_access_key
from database.db import db
from sqlalchemy import func, desc
from datetime import datetime, timedelta
import secrets
import re
from functools import wraps

api_bp = Blueprint('api', __name__)

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
    """Проверка ключа доступа блогера"""
    data = request.get_json()
    
    if not data or 'key' not in data:
        return jsonify({"success": False, "error": "Не указан ключ доступа"}), 400
    
    access_key = data['key']
    
    # Используем get_session вместо прямого запроса к модели
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
    """Получение статистики блогера"""
    blogger_id = request.args.get('id')
    access_key = request.args.get('key')
    
    if not blogger_id or not access_key:
        return jsonify({"success": False, "error": "Не указаны параметры доступа"}), 400
    
    db_session = get_session()
    try:
        # Проверка ключа доступа
        blogger = db_session.query(Blogger).filter_by(id=blogger_id, access_key=access_key).first()
        if not blogger:
            return jsonify({"success": False, "error": "Нет доступа"}), 401
        
        # Получаем общее количество переходов
        total_referrals = db_session.query(BloggerReferral).filter_by(blogger_id=blogger.id).count()
        
        # Получаем общее количество конверсий
        total_conversions = db_session.query(BloggerReferral).filter_by(blogger_id=blogger.id, converted=True).count()
        
        # Получаем общую сумму заработка
        total_earnings = db_session.query(func.sum(BloggerReferral.commission_amount))\
            .filter_by(blogger_id=blogger.id, converted=True)\
            .scalar() or 0
        
        # Формируем реферальную ссылку
        bot_username = current_app.config.get('TELEGRAM_BOT_USERNAME', 'your_main_bot')
        referral_link = f"https://t.me/{bot_username}?start=ref_{blogger.access_key}"
        
        # Получаем статистику по дням за последние 30 дней
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=29)
        
        # Запрос для получения данных по дням
        daily_data = []
        current_date = start_date
        
        while current_date <= end_date:
            # Начало и конец текущего дня
            day_start = datetime.combine(current_date, datetime.min.time())
            day_end = datetime.combine(current_date, datetime.max.time())
            
            # Количество переходов за день
            day_referrals = db_session.query(BloggerReferral).filter(
                BloggerReferral.blogger_id == blogger.id,
                BloggerReferral.created_at >= day_start,
                BloggerReferral.created_at <= day_end
            ).count()
            
            # Количество конверсий за день
            day_conversions = db_session.query(BloggerReferral).filter(
                BloggerReferral.blogger_id == blogger.id,
                BloggerReferral.converted == True,
                BloggerReferral.created_at >= day_start,
                BloggerReferral.created_at <= day_end
            ).count()
            
            # Добавляем данные в список
            daily_data.append({
                "date": current_date.strftime("%d.%m"),
                "referrals": day_referrals,
                "conversions": day_conversions
            })
            
            # Переходим к следующему дню
            current_date += timedelta(days=1)
        
        return jsonify({
            "success": True,
            "blogger_id": blogger.id,
            "blogger_name": blogger.name,
            "created_at": blogger.created_at.strftime("%Y-%m-%d"),
            "total_referrals": total_referrals,
            "total_conversions": total_conversions,
            "total_earnings": total_earnings,
            "referral_link": referral_link,
            "daily_stats": daily_data
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Ошибка при получении статистики: {str(e)}"}), 500
    finally:
        db_session.close()

@api_bp.route('/blogger/referrals', methods=['GET'])
def get_blogger_referrals():
    """Получение списка рефералов блогера"""
    blogger_id = request.args.get('id')
    access_key = request.args.get('key')
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 10))
    
    if not blogger_id or not access_key:
        return jsonify({"success": False, "error": "Не указаны параметры доступа"}), 400
    
    db_session = get_session()
    try:
        # Проверка ключа доступа
        blogger = db_session.query(Blogger).filter_by(id=blogger_id, access_key=access_key).first()
        if not blogger:
            return jsonify({"success": False, "error": "Нет доступа"}), 401
        
        # Получаем рефералы, отсортированные по дате (от новых к старым)
        referrals = db_session.query(BloggerReferral)\
            .filter_by(blogger_id=blogger.id)\
            .order_by(desc(BloggerReferral.created_at))\
            .offset(offset).limit(limit).all()
        
        referrals_data = []
        for referral in referrals:
            referral_data = {
                "id": referral.id,
                "source": referral.source,
                "created_at": referral.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                "converted": referral.converted,
                "commission_amount": referral.commission_amount if referral.converted else None
            }
            referrals_data.append(referral_data)
        
        return jsonify({
            "success": True,
            "referrals": referrals_data
        })
    except Exception as e:
        return jsonify({"success": False, "error": f"Ошибка при получении рефералов: {str(e)}"}), 500
    finally:
        db_session.close()

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
        bot_username = current_app.config.get('TELEGRAM_BOT_USERNAME', 'WILLWAY_ReferalBot')
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
                    
                    # Сумма комиссионных за день
                    day_earnings = db_session.query(func.sum(BloggerReferral.commission_amount))\
                        .filter(
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
                "created_at": blogger.created_at.strftime("%Y-%m-%d"),
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
    blogger_id = request.args.get('id')
    access_key = request.args.get('key')
    
    if not blogger_id or not access_key:
        return jsonify({"success": False, "error": "Не указаны параметры доступа"}), 400
    
    db_session = get_session()
    try:
        # Проверка ключа доступа
        blogger = db_session.query(Blogger).filter_by(id=blogger_id, access_key=access_key).first()
        if not blogger:
            return jsonify({"success": False, "error": "Нет доступа"}), 401
        
        # Формируем реферальную ссылку
        bot_username = current_app.config.get('TELEGRAM_BOT_USERNAME', 'WILLWAY_ReferalBot')
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
    blogger_id = request.args.get('id')
    access_key = request.args.get('key')
    
    if not blogger_id or not access_key:
        return jsonify({"success": False, "error": "Не указаны параметры доступа"}), 400
    
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
    data = request.json
    api_key = data.get('api_key')
    
    # Проверка API ключа
    if api_key != current_app.config.get('API_KEY'):
        return jsonify({"success": False, "error": "Неверный API ключ"}), 401
    
    ref_code = data.get('ref_code')
    user_id = data.get('user_id')
    amount = float(data.get('amount', 0))
    purchase_id = data.get('purchase_id')
    
    if not ref_code or not user_id or amount <= 0:
        return jsonify({"success": False, "error": "Отсутствуют обязательные параметры"}), 400
    
    db_session = get_session()
    try:
        # Извлекаем access_key из ref_code
        if ref_code.startswith('ref_'):
            access_key = ref_code.replace('ref_', '')
        else:
            access_key = ref_code
            
        # Находим блогера
        blogger = db_session.query(Blogger).filter_by(access_key=access_key).first()
        if not blogger:
            return jsonify({"success": False, "error": "Блогер не найден"}), 404
            
        # Ищем соответствующий реферальный переход
        referral = db_session.query(BloggerReferral).filter_by(
            blogger_id=blogger.id,
            source=f"telegram_start_{user_id}",
            converted=False
        ).first()
        
        # Если переход не найден, создаем новую запись
        if not referral:
            referral = BloggerReferral(
                blogger_id=blogger.id,
                source=f"telegram_start_{user_id}"
            )
            db_session.add(referral)
            
        # Вычисляем комиссию (20% от суммы)
        commission = amount * 0.2
        
        # Обновляем информацию о конверсии
        referral.converted = True
        referral.converted_at = datetime.now()
        referral.commission_amount = commission
        
        # Добавляем информацию о покупке
        if purchase_id:
            referral.source = f"{referral.source}_purchase_{purchase_id}"
            
        db_session.commit()
        
        return jsonify({
            "success": True, 
            "message": "Конверсия успешно зарегистрирована",
            "commission": commission,
            "blogger_id": blogger.id
        })
    except Exception as e:
        db_session.rollback()
        return jsonify({"success": False, "error": f"Ошибка при регистрации конверсии: {str(e)}"}), 500
    finally:
        db_session.close() 